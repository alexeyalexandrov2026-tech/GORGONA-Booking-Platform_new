"""Integration tests for SPECIAL-04 (0148): Staffing, advisory, organizations & public admin
across profiles 30, 31, 36, 39, verifying dual-review four-eyes enforcement, allocation
approval gating, insert-only audit events and branch isolation.
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
def enable_public_civic_for_test(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setitem(
        modules.MODULES_BY_ID,
        "public_civic",
        modules.MODULES_BY_ID["public_civic"].model_copy(
            update={"enableable": True, "readiness": Readiness.TECHNICALLY_VERIFIED}
        ),
    )


async def test_civic_dual_review_allocation_gate_and_branch_isolation(
    client: httpx.AsyncClient,
    idp: FakeIdp,
    world: BookingWorld,
    owner_conn: psycopg.Connection,
    enable_public_civic_for_test: None,
) -> None:
    tenant_a = world.a.tenant_id
    home = world.a.location_id
    branch_b, _ = seed_other_branch(owner_conn, world.a)

    owner = seed_user(owner_conn, f"civic-owner-{uuid7()}")
    reviewer = seed_user(owner_conn, f"civic-rev-{uuid7()}")
    mgr_b = seed_user(owner_conn, f"civic-mgrb-{uuid7()}")
    add_membership(owner_conn, tenant_id=tenant_a, user_id=owner.user_id, role="owner")
    add_membership(owner_conn, tenant_id=tenant_a, user_id=reviewer.user_id, role="manager")
    add_membership(
        owner_conn, tenant_id=tenant_a, user_id=mgr_b.user_id, role="manager", location_id=branch_b
    )
    owner_conn.commit()

    cfg = Config(client, idp)
    await cfg.profile(owner, tenant_a, 0, [30, 31, 36, 39])
    await cfg.publish(owner, tenant_a, 0, ["counterparties", "public_civic"])

    h = idp.bearer(owner.subject, email=owner.email)
    hr = idp.bearer(reviewer.subject, email=reviewer.email)
    hb = idp.bearer(mgr_b.subject, email=mgr_b.email)
    biz = f"/v1/businesses/{tenant_a}"
    civic = f"{biz}/civic"

    cp_id, prog_id, case_id, alloc_id, ev_id = uuid7(), uuid7(), uuid7(), uuid7(), uuid7()
    assert (
        await client.put(
            f"{biz}/counterparties/{cp_id}",
            headers={**h, "Idempotency-Key": f"civ-cp-{uuid7()}"},
            json=card(display_name="Applicant Rivera", roles=["customer"]),
        )
    ).status_code == 200

    # 1. Create dual-review program
    r_prog = await client.put(
        f"{civic}/programs/{prog_id}",
        headers={**h, "Idempotency-Key": f"civ-prog-{uuid7()}"},
        json={
            "schema_version": 1,
            "expected_revision": 0,
            "location_id": str(home),
            "program_domain": "public_service_program",
            "code": "GRANT-2026",
            "title": "Community Grant Program",
            "status": "active",
            "requires_dual_review": True,
        },
    )
    assert r_prog.status_code == 200
    assert r_prog.json()["requires_dual_review"] is True

    # 2. Submit case as owner; verify allocation blocked while unapproved
    r_case = await client.put(
        f"{civic}/cases/{case_id}",
        headers={**h, "Idempotency-Key": f"civ-case-{uuid7()}"},
        json={
            "schema_version": 1,
            "expected_revision": 0,
            "location_id": str(home),
            "program_id": str(prog_id),
            "subject_counterparty_id": str(cp_id),
            "case_number": "CASE-2026-01",
            "status": "submitted",
            "summary": "Neighborhood library renovation grant",
        },
    )
    assert r_case.status_code == 200

    r_alloc_blk = await client.put(
        f"{civic}/allocations/{alloc_id}",
        headers={**h, "Idempotency-Key": f"civ-alloc-blk-{uuid7()}"},
        json={
            "schema_version": 1,
            "expected_revision": 0,
            "location_id": str(home),
            "case_id": str(case_id),
            "allocation_kind": "grant_award",
            "reference_code": "GRT-001",
            "effective_from": "2026-12-01",
        },
    )
    assert r_alloc_blk.status_code == 409
    assert r_alloc_blk.json()["error"]["code"] == "CIVIC_CASE_NOT_APPROVED"

    # 3. Submitter (owner) cannot self-approve in a dual-review program
    r_self = await client.put(
        f"{civic}/cases/{case_id}",
        headers={**h, "Idempotency-Key": f"civ-self-{uuid7()}"},
        json={
            "schema_version": 1,
            "expected_revision": 1,
            "location_id": str(home),
            "program_id": str(prog_id),
            "subject_counterparty_id": str(cp_id),
            "case_number": "CASE-2026-01",
            "status": "approved",
            "summary": "Neighborhood library renovation grant",
            "decision_notes": "Trying self-approval",
        },
    )
    assert r_self.status_code == 409
    assert r_self.json()["error"]["code"] == "CIVIC_DUAL_REVIEW_REQUIRED"

    # 4. Second reviewer approves -> allocation & insert-only audit event succeed
    r_app = await client.put(
        f"{civic}/cases/{case_id}",
        headers={**hr, "Idempotency-Key": f"civ-app-{uuid7()}"},
        json={
            "schema_version": 1,
            "expected_revision": 1,
            "location_id": str(home),
            "program_id": str(prog_id),
            "subject_counterparty_id": str(cp_id),
            "case_number": "CASE-2026-01",
            "status": "approved",
            "summary": "Neighborhood library renovation grant",
            "decision_notes": "Independently reviewed and approved",
        },
    )
    assert r_app.status_code == 200
    assert r_app.json()["decided_by"] == str(reviewer.user_id)

    r_alloc = await client.put(
        f"{civic}/allocations/{alloc_id}",
        headers={**h, "Idempotency-Key": f"civ-alloc-ok-{uuid7()}"},
        json={
            "schema_version": 1,
            "expected_revision": 0,
            "location_id": str(home),
            "case_id": str(case_id),
            "allocation_kind": "grant_award",
            "reference_code": "GRT-001",
            "effective_from": "2026-12-01",
            "effective_until": "2027-12-01",
        },
    )
    assert r_alloc.status_code == 200
    assert r_alloc.json()["status"] == "active"

    r_ev = await client.put(
        f"{civic}/audit-events/{ev_id}",
        headers={**hr, "Idempotency-Key": f"civ-ev-{uuid7()}"},
        json={
            "schema_version": 1,
            "location_id": str(home),
            "case_id": str(case_id),
            "event_kind": "conflict_disclosure",
            "details": "Reviewer attested no conflict of interest",
        },
    )
    assert r_ev.status_code == 200

    # 5. Branch B manager sees zero records from home branch
    assert (await client.get(f"{civic}/programs", headers=hb)).json()["items"] == []
    assert (await client.get(f"{civic}/cases", headers=hb)).json()["items"] == []
    assert (await client.get(f"{civic}/allocations", headers=hb)).json()["items"] == []
    assert (await client.get(f"{civic}/audit-events", headers=hb)).json()["items"] == []
