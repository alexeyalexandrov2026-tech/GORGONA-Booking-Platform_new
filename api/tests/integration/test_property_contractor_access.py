"""PROPERTY-01 5b: single-assignment contractor access via delegation grant (FAKE data).

docs/plan/PACKAGE_PROPERTY01_CONTRACTOR_ACCESS_DESIGN_2026-11-20.md.
"""

from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID, uuid7

import httpx
import psycopg
import pytest

from gorgona_booking.db.pool import RuntimePool, tenant_transaction
from gorgona_booking.db.provisioning import add_membership
from tests.integration import test_property_maintenance as maint
from tests.integration.seed import FakeUser, seed_other_branch, seed_user
from tests.integration.test_property_catalog import Catalog

pytestmark = pytest.mark.anyio
agreements = maint.agreements
catalog = maint.catalog
client = maint.client
enabled = maint.enabled
idp = maint.idp
manager_a = maint.manager_a
manager_b = maint.manager_b
__all__ = ["agreements", "catalog", "client", "enabled", "idp", "manager_a", "manager_b"]


def _owner_headers(c: Catalog, tenant_id: UUID) -> dict[str, str]:
    owner = seed_user(c.owner_conn, f"prop-owner-{uuid7()}")
    add_membership(
        c.owner_conn, tenant_id=tenant_id, user_id=owner.user_id, role="owner", location_id=None
    )
    return c.idp.bearer(owner.subject, email=owner.email)


async def _grant(
    c: Catalog,
    manager_b: FakeUser,
    *,
    owner_a_headers: dict[str, str],
    owner_b_headers: dict[str, str],
    permissions: list[str] | None = None,
    location_id: str | None = None,
    expires_at: str | None = None,
) -> tuple[str, dict[str, str]]:
    """Issue, accept, and assign manager_b as delegate on a grant from company A to company B."""
    b_headers = c.idp.bearer(manager_b.subject, email=manager_b.email)
    exp = expires_at or (datetime.now(UTC) + timedelta(days=30)).isoformat()
    grant_uuid = uuid7()
    issued = await c.client.put(
        f"/v1/businesses/{c.tenant}/delegations/{grant_uuid}",
        json={
            "schema_version": 1,
            "servicer_business_id": str(c.world.b.tenant_id),
            "permissions": permissions or ["property.contractor_work"],
            "location_id": location_id,
            "expires_at": exp,
        },
        headers={**owner_a_headers, "Idempotency-Key": str(uuid7())},
    )
    assert issued.status_code == 200, issued.text
    grant_id = str(issued.json()["grant_id"])

    accepted = await c.client.post(
        f"/v1/businesses/{c.world.b.tenant_id}/delegations/{grant_id}/accept",
        json={
            "schema_version": 1,
            "expected_revision": 1,
            "delegate_user_ids": [str(manager_b.user_id)],
        },
        headers={**owner_b_headers, "Idempotency-Key": str(uuid7())},
    )
    assert accepted.status_code == 200, accepted.text
    return grant_id, b_headers


async def _assigned_request(c: Catalog, object_id: UUID, contractor_cp: str, title: str) -> UUID:
    rid, res = await maint.create_request(c, object_id, title=title)
    assert res.status_code == 200, res.text
    app = await maint.post_event(
        c,
        rid,
        {
            "action": "approve",
            "expected_revision": 1,
            "approved_limit_minor": 40000,
            "currency": "USD",
        },
    )
    assert app.status_code == 200, app.text
    asn = await maint.post_event(
        c,
        rid,
        {"action": "assign", "expected_revision": 2, "contractor_id": contractor_cp},
    )
    assert asn.status_code == 200, asn.text
    return rid


async def _bind(
    c: Catalog,
    request_id: UUID,
    expected_revision: int,
    company_id: str | None,
    *,
    key: str | None = None,
) -> httpx.Response:
    return await c.client.put(
        f"{maint.root(c)}/{request_id}/contractor-company",
        json={
            "schema_version": 1,
            "expected_revision": expected_revision,
            "company_id": company_id,
        },
        headers={**c.headers, "Idempotency-Key": key or str(uuid7())},
    )


async def test_single_assignment_isolation_updates_and_revocation(
    enabled: Catalog,
    manager_b: FakeUser,
) -> None:
    parcel = await maint.make_parcel(enabled, "FAKE Contractor Site")
    contractor_cp = await enabled.counterparty()
    req_1 = await _assigned_request(enabled, parcel, contractor_cp, "FAKE Bound Valve Repair")
    req_2 = await _assigned_request(enabled, parcel, contractor_cp, "FAKE Unbound Roof Repair")

    owner_a = _owner_headers(enabled, enabled.tenant)
    owner_b = _owner_headers(enabled, enabled.world.b.tenant_id)
    grant_id, b_headers = await _grant(
        enabled, manager_b, owner_a_headers=owner_a, owner_b_headers=owner_b
    )

    # Before binding, contractor sees neither req_1 nor req_2
    assert (
        await enabled.client.get(
            f"{maint.root(enabled)}/{req_1}/contractor-work/{grant_id}", headers=b_headers
        )
    ).status_code == 403

    # Bind ONLY req_1 to company B
    bound = await _bind(enabled, req_1, 0, str(enabled.world.b.tenant_id), key="bind-req1-rev1")
    assert bound.status_code == 200, bound.text
    assert bound.json()["revision"] == 1
    assert bound.json()["company_id"] == str(enabled.world.b.tenant_id)

    # Company A's own manager cannot call the contractor delegate route
    assert (
        await enabled.client.get(
            f"{maint.root(enabled)}/{req_1}/contractor-work/{grant_id}", headers=enabled.headers
        )
    ).status_code == 403

    # Contractor delegate reads ONLY req_1 and sees NO private/budget/lease fields
    work_1 = await enabled.client.get(
        f"{maint.root(enabled)}/{req_1}/contractor-work/{grant_id}", headers=b_headers
    )
    assert work_1.status_code == 200, work_1.text
    payload: dict[str, Any] = work_1.json()
    assert payload["request_id"] == str(req_1)
    assert payload["object_name"] == "FAKE Contractor Site"
    assert payload["binding_revision"] == 1
    assert payload["state"] == "assigned"
    for forbidden in ("approved_limit_minor", "currency", "lease_id", "owner_id", "manager_id"):
        assert forbidden not in payload

    # Same live grant CANNOT read or update unbound req_2 or company routes
    assert (
        await enabled.client.get(
            f"{maint.root(enabled)}/{req_2}/contractor-work/{grant_id}", headers=b_headers
        )
    ).status_code == 403
    assert (
        await enabled.client.post(
            f"{maint.root(enabled)}/{req_2}/contractor-work/{grant_id}/updates",
            json={"schema_version": 1, "kind": "acknowledged", "note": "FAKE Sneak"},
            headers={**b_headers, "Idempotency-Key": str(uuid7())},
        )
    ).status_code == 403
    assert (
        await enabled.client.get(
            f"/v1/businesses/{enabled.tenant}/property/objects", headers=b_headers
        )
    ).status_code == 403

    # Contractor posts progress update (idempotent + replay + reuse 422)
    upd_1 = await enabled.client.post(
        f"{maint.root(enabled)}/{req_1}/contractor-work/{grant_id}/updates",
        json={"schema_version": 1, "kind": "acknowledged", "note": "FAKE Arriving tomorrow"},
        headers={**b_headers, "Idempotency-Key": "contractor-upd-1"},
    )
    assert upd_1.status_code == 200, upd_1.text
    assert upd_1.json()["number"] == 1
    assert upd_1.json()["kind"] == "acknowledged"
    replay = await enabled.client.post(
        f"{maint.root(enabled)}/{req_1}/contractor-work/{grant_id}/updates",
        json={"schema_version": 1, "kind": "acknowledged", "note": "FAKE Arriving tomorrow"},
        headers={**b_headers, "Idempotency-Key": "contractor-upd-1"},
    )
    assert replay.status_code == 200
    assert replay.json() == upd_1.json()
    reused = await enabled.client.post(
        f"{maint.root(enabled)}/{req_1}/contractor-work/{grant_id}/updates",
        json={"schema_version": 1, "kind": "work_done", "note": "FAKE Different"},
        headers={**b_headers, "Idempotency-Key": "contractor-upd-1"},
    )
    assert reused.status_code == 422

    # Business reads contractor updates with servicer display name
    staff_view = await enabled.client.get(
        f"{maint.root(enabled)}/{req_1}/contractor-updates", headers=enabled.headers
    )
    assert staff_view.status_code == 200, staff_view.text
    assert len(staff_view.json()["items"]) == 1
    assert staff_view.json()["items"][0]["company_id"] == str(enabled.world.b.tenant_id)
    assert staff_view.json()["items"][0]["company_name"]

    # Unbinding immediately blocks GET, POST, and replay
    unbound = await _bind(enabled, req_1, 1, None)
    assert unbound.status_code == 200, unbound.text
    assert unbound.json()["revision"] == 2
    assert unbound.json()["company_id"] is None
    assert (
        await enabled.client.get(
            f"{maint.root(enabled)}/{req_1}/contractor-work/{grant_id}", headers=b_headers
        )
    ).status_code == 403
    assert (
        await enabled.client.post(
            f"{maint.root(enabled)}/{req_1}/contractor-work/{grant_id}/updates",
            json={"schema_version": 1, "kind": "acknowledged", "note": "FAKE Arriving tomorrow"},
            headers={**b_headers, "Idempotency-Key": "contractor-upd-1"},
        )
    ).status_code == 403

    # Rebind restores access, then revoking the grant blocks GET, POST, and replay
    rebound = await _bind(enabled, req_1, 2, str(enabled.world.b.tenant_id))
    assert rebound.status_code == 200
    assert rebound.json()["revision"] == 3
    upd_2 = await enabled.client.post(
        f"{maint.root(enabled)}/{req_1}/contractor-work/{grant_id}/updates",
        json={"schema_version": 1, "kind": "work_done", "note": "FAKE Replaced valve"},
        headers={**b_headers, "Idempotency-Key": "contractor-upd-2"},
    )
    assert upd_2.status_code == 200, upd_2.text
    assert upd_2.json()["binding_revision"] == 3

    revoked = await enabled.client.post(
        f"/v1/businesses/{enabled.tenant}/delegations/{grant_id}/revoke",
        json={"schema_version": 1, "expected_revision": 2},
        headers={**owner_a, "Idempotency-Key": str(uuid7())},
    )
    assert revoked.status_code == 200, revoked.text
    assert (
        await enabled.client.get(
            f"{maint.root(enabled)}/{req_1}/contractor-work/{grant_id}", headers=b_headers
        )
    ).status_code == 403
    assert (
        await enabled.client.post(
            f"{maint.root(enabled)}/{req_1}/contractor-work/{grant_id}/updates",
            json={"schema_version": 1, "kind": "work_done", "note": "FAKE Replaced valve"},
            headers={**b_headers, "Idempotency-Key": "contractor-upd-2"},
        )
    ).status_code == 403


async def test_branch_scoped_grant_and_db_trigger_recheck_without_privileged_sql(
    enabled: Catalog,
    manager_b: FakeUser,
    app_pool: RuntimePool,
) -> None:
    parcel = await maint.make_parcel(enabled, "FAKE Branch Site")
    contractor_cp = await enabled.counterparty()
    req = await _assigned_request(enabled, parcel, contractor_cp, "FAKE Branch Heater")
    assert (await _bind(enabled, req, 0, str(enabled.world.b.tenant_id))).status_code == 200

    away_branch, _ = seed_other_branch(enabled.owner_conn, enabled.world.a)
    owner_a = _owner_headers(enabled, enabled.tenant)
    owner_b = _owner_headers(enabled, enabled.world.b.tenant_id)

    async def revoke(grant_id: str) -> None:
        r = await enabled.client.post(
            f"/v1/businesses/{enabled.tenant}/delegations/{grant_id}/revoke",
            json={"schema_version": 1, "expected_revision": 2},
            headers={**owner_a, "Idempotency-Key": str(uuid7())},
        )
        assert r.status_code == 200, r.text

    # Wrong branch refused
    away_grant, b_headers = await _grant(
        enabled,
        manager_b,
        owner_a_headers=owner_a,
        owner_b_headers=owner_b,
        location_id=str(away_branch),
    )
    assert (
        await enabled.client.get(
            f"{maint.root(enabled)}/{req}/contractor-work/{away_grant}", headers=b_headers
        )
    ).status_code == 403
    await revoke(away_grant)

    # Wrong permission refused
    wrong_perm_grant, _ = await _grant(
        enabled,
        manager_b,
        owner_a_headers=owner_a,
        owner_b_headers=owner_b,
        permissions=["booking.read"],
    )
    assert (
        await enabled.client.get(
            f"{maint.root(enabled)}/{req}/contractor-work/{wrong_perm_grant}", headers=b_headers
        )
    ).status_code == 403
    await revoke(wrong_perm_grant)

    # Home branch grant works end-to-end
    home_grant, _ = await _grant(
        enabled,
        manager_b,
        owner_a_headers=owner_a,
        owner_b_headers=owner_b,
        location_id=str(enabled.world.a.location_id),
    )

    # Home branch grant works end-to-end
    ok = await enabled.client.post(
        f"{maint.root(enabled)}/{req}/contractor-work/{home_grant}/updates",
        json={"schema_version": 1, "kind": "in_progress", "note": "FAKE On site"},
        headers={**b_headers, "Idempotency-Key": str(uuid7())},
    )
    assert ok.status_code == 200, ok.text

    # Once completed by company A, contractor can still read work order but cannot post updates
    done = await maint.post_event(
        enabled, req, {"action": "complete", "expected_revision": 3, "note": "FAKE Verified"}
    )
    assert done.status_code == 200, done.text
    read_done = await enabled.client.get(
        f"{maint.root(enabled)}/{req}/contractor-work/{home_grant}", headers=b_headers
    )
    assert read_done.status_code == 200
    assert read_done.json()["state"] == "completed"
    post_done = await enabled.client.post(
        f"{maint.root(enabled)}/{req}/contractor-work/{home_grant}/updates",
        json={"schema_version": 1, "kind": "work_done", "note": "FAKE Late note"},
        headers={**b_headers, "Idempotency-Key": str(uuid7())},
    )
    assert post_done.status_code == 409

    # Revoke home_grant, then verify direct SQL insert inside a branch-scoped session is rejected!
    rev = await enabled.client.post(
        f"/v1/businesses/{enabled.tenant}/delegations/{home_grant}/revoke",
        json={"schema_version": 1, "expected_revision": 2},
        headers={**owner_a, "Idempotency-Key": str(uuid7())},
    )
    assert rev.status_code == 200, rev.text
    async with tenant_transaction(app_pool, enabled.tenant) as conn:
        await conn.execute(
            "select set_config('gba.location_id', %s, true)",
            (str(enabled.world.a.location_id),),
        )
        await conn.execute(
            "select set_config('gba.user_id', %s, true)",
            (str(manager_b.user_id),),
        )
        with pytest.raises(psycopg.errors.CheckViolation) as exc_info:
            await conn.execute(
                "insert into gba.property_maintenance_contractor_updates "
                "(tenant_id, request_id, number, kind, note, company_id, grant_id, "
                "binding_revision, recorded_by) "
                "values (%s,%s,2,'work_done','FAKE forged',%s,%s,1,%s)",
                (
                    enabled.tenant,
                    req,
                    enabled.world.b.tenant_id,
                    UUID(home_grant),
                    manager_b.user_id,
                ),
            )
    assert exc_info.value.diag.constraint_name == "property_maintenance_contractor_updates_scope"
