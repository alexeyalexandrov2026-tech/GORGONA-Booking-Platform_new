"""Integration tests for SPECIAL-02 (0146): consent-gated Healthcare, Veterinary & Social Care,
verifying active consent enforcement, immediate block & note redaction on revocation, and
branch isolation.
"""

from uuid import uuid7

import httpx
import psycopg
import pytest

from gorgona_booking.business import modules
from gorgona_booking.business.readiness_registry import Readiness
from gorgona_booking.db.provisioning import add_membership
from tests.integration import test_management_api as shared
from tests.integration.booking_support import BookingWorld
from tests.integration.configuration_support import Config
from tests.integration.seed import seed_other_branch, seed_user
from tests.integration.test_counterparties import card
from tests.support.fake_idp import FakeIdp

pytestmark = pytest.mark.anyio
client = shared.client
idp = shared.idp


@pytest.fixture
def enable_clinical_care_for_test(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setitem(
        modules.MODULES_BY_ID,
        "clinical_care",
        modules.MODULES_BY_ID["clinical_care"].model_copy(
            update={"enableable": True, "readiness": Readiness.TECHNICALLY_VERIFIED}
        ),
    )


async def test_consent_gated_care_workflow_and_revocation_redaction(
    client: httpx.AsyncClient,
    idp: FakeIdp,
    world: BookingWorld,
    owner_conn: psycopg.Connection,
    enable_clinical_care_for_test: None,
) -> None:
    tenant_a = world.a.tenant_id
    home = world.a.location_id
    branch_b, _ = seed_other_branch(owner_conn, world.a)

    owner = seed_user(owner_conn, f"care-owner-{uuid7()}")
    mgr_b = seed_user(owner_conn, f"care-mgrb-{uuid7()}")
    add_membership(owner_conn, tenant_id=tenant_a, user_id=owner.user_id, role="owner")
    add_membership(
        owner_conn, tenant_id=tenant_a, user_id=mgr_b.user_id, role="manager", location_id=branch_b
    )
    owner_conn.commit()

    cfg = Config(client, idp)
    await cfg.profile(owner, tenant_a, 0, [14, 15, 16])
    await cfg.publish(owner, tenant_a, 0, ["counterparties", "clinical_care"])

    h = idp.bearer(owner.subject, email=owner.email)
    hb = idp.bearer(mgr_b.subject, email=mgr_b.email)
    biz = f"/v1/businesses/{tenant_a}"
    care = f"{biz}/care"

    guardian_id, subj_id, cons_id, plan_id, enc1_id, enc2_id = (
        uuid7(),
        uuid7(),
        uuid7(),
        uuid7(),
        uuid7(),
        uuid7(),
    )
    assert (
        await client.put(
            f"{biz}/counterparties/{guardian_id}",
            headers={**h, "Idempotency-Key": f"care-cp-{uuid7()}"},
            json=card(display_name="Guardian Morgan", roles=["customer"]),
        )
    ).status_code == 200
    assert (
        await client.put(
            f"{care}/subjects/{subj_id}",
            headers={**h, "Idempotency-Key": f"care-sub-{uuid7()}"},
            json={
                "schema_version": 1,
                "expected_revision": 0,
                "location_id": str(home),
                "guardian_counterparty_id": str(guardian_id),
                "subject_kind": "human_patient",
                "code": "PAT_001",
                "display_name": "Jordan Patient",
                "allergies_summary": "Penicillin",
            },
        )
    ).status_code == 200

    # Active consent granted
    assert (
        await client.put(
            f"{care}/consents/{cons_id}",
            headers={**h, "Idempotency-Key": f"care-con1-{uuid7()}"},
            json={
                "schema_version": 1,
                "expected_revision": 0,
                "location_id": str(home),
                "subject_id": str(subj_id),
                "scope": "care_records",
                "status": "active",
                "granted_by_name": "Guardian Morgan",
            },
        )
    ).status_code == 200

    assert (
        await client.put(
            f"{care}/plans/{plan_id}",
            headers={**h, "Idempotency-Key": f"care-pl-{uuid7()}"},
            json={
                "schema_version": 1,
                "expected_revision": 0,
                "location_id": str(home),
                "subject_id": str(subj_id),
                "consent_id": str(cons_id),
                "title": "Rehabilitation Care Plan",
                "status": "active",
            },
        )
    ).status_code == 200

    r_enc = await client.put(
        f"{care}/encounters/{enc1_id}",
        headers={**h, "Idempotency-Key": f"care-e1-{uuid7()}"},
        json={
            "schema_version": 1,
            "location_id": str(home),
            "subject_id": str(subj_id),
            "consent_id": str(cons_id),
            "plan_id": str(plan_id),
            "encounter_date": "2026-11-05",
            "summary": "Initial physical therapy assessment",
            "clinical_notes": "SENSITIVE DIAGNOSIS NOTE ALPHA",
        },
    )
    assert r_enc.status_code == 200, r_enc.text
    assert r_enc.json()["clinical_notes"] == "SENSITIVE DIAGNOSIS NOTE ALPHA"
    assert r_enc.json()["consent_active"] is True

    # Revoke consent -> new encounters blocked (409 CARE_CONSENT_REQUIRED) & notes redacted!
    assert (
        await client.put(
            f"{care}/consents/{cons_id}",
            headers={**h, "Idempotency-Key": f"care-con-rev-{uuid7()}"},
            json={
                "schema_version": 1,
                "expected_revision": 1,
                "location_id": str(home),
                "subject_id": str(subj_id),
                "scope": "care_records",
                "status": "revoked",
                "granted_by_name": "Guardian Morgan",
            },
        )
    ).status_code == 200

    r_blocked = await client.put(
        f"{care}/encounters/{enc2_id}",
        headers={**h, "Idempotency-Key": f"care-e2-{uuid7()}"},
        json={
            "schema_version": 1,
            "location_id": str(home),
            "subject_id": str(subj_id),
            "consent_id": str(cons_id),
            "encounter_date": "2026-11-06",
            "summary": "Blocked follow-up",
            "clinical_notes": "Should not be stored",
        },
    )
    assert r_blocked.status_code == 409
    assert r_blocked.json()["error"]["code"] == "CARE_CONSENT_REQUIRED"

    # Read-back redacts sensitive clinical_notes immediately after revocation
    lst = await client.get(f"{care}/encounters?subject_id={subj_id}", headers=h)
    assert lst.status_code == 200
    items = lst.json()["items"]
    assert len(items) == 1
    assert items[0]["consent_active"] is False
    assert items[0]["clinical_notes"] is None
    assert "SENSITIVE DIAGNOSIS NOTE ALPHA" not in lst.text

    # Branch B isolation: sees 0 encounters from Branch A
    assert (await client.get(f"{care}/encounters", headers=hb)).json()["items"] == []
