"""REST-01 Slice 1: dining areas, tables, independent table reservations, RLS and access."""

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid7

import httpx
import psycopg
import pytest
from psycopg_pool import AsyncConnectionPool

from gorgona_booking.business import modules
from gorgona_booking.business.readiness_registry import Readiness
from gorgona_booking.db.pool import tenant_transaction
from gorgona_booking.db.provisioning import add_membership
from tests.integration.booking_support import BookingWorld
from tests.integration.seed import FakeUser, seed_other_branch, seed_user
from tests.integration.test_counterparties import card
from tests.integration.test_delegations import (
    client,
    idp,
    owner_a,
    owner_b,
)
from tests.support.fake_idp import FakeIdp

pytestmark = pytest.mark.anyio
__all__ = ["client", "idp", "owner_a", "owner_b"]

ENABLED_RESTAURANT = [
    "booking_resources",
    "counterparties",
    "finance",
    "finance_documents",
    "inventory",
    "workforce",
    "restaurant",
]


@dataclass(frozen=True)
class RestaurantEnv:
    client: httpx.AsyncClient
    idp: FakeIdp
    tenant: UUID
    branch_a: UUID
    branch_b: UUID
    owner: FakeUser
    branch_a_mgr: FakeUser
    branch_b_mgr: FakeUser
    front_desk_a: FakeUser
    kitchen_a: FakeUser
    delegate_b: FakeUser
    grant_id: UUID

    def headers(self, user: FakeUser | None = None, *, key: str | None = None) -> dict[str, str]:
        who = user or self.owner
        h = self.idp.bearer(who.subject, email=who.email)
        if key is not None:
            h["Idempotency-Key"] = key
        return h

    def url(self, suffix: str) -> str:
        return f"/v1/businesses/{self.tenant}/restaurant{suffix}"


@pytest.fixture
async def rest_env(
    client: httpx.AsyncClient,
    idp: FakeIdp,
    world: BookingWorld,
    owner_conn: psycopg.Connection,
    owner_a: FakeUser,
    owner_b: FakeUser,
    monkeypatch: pytest.MonkeyPatch,
) -> RestaurantEnv:
    monkeypatch.setitem(
        modules.MODULES_BY_ID,
        "restaurant",
        modules.MODULES_BY_ID["restaurant"].model_copy(
            update={"enableable": True, "readiness": Readiness.TECHNICALLY_VERIFIED}
        ),
    )
    branch_b, _ = seed_other_branch(owner_conn, world.a)
    branch_a_mgr = seed_user(owner_conn, "rest-branch-a-mgr")
    branch_b_mgr = seed_user(owner_conn, "rest-branch-b-mgr")
    front_desk_a = seed_user(owner_conn, "rest-front-desk-a")
    kitchen_a = seed_user(owner_conn, "rest-kitchen-a")
    delegate_b = seed_user(owner_conn, "rest-delegate-b")
    add_membership(
        owner_conn,
        tenant_id=world.a.tenant_id,
        user_id=branch_a_mgr.user_id,
        role="manager",
        location_id=world.a.location_id,
    )
    add_membership(
        owner_conn,
        tenant_id=world.a.tenant_id,
        user_id=branch_b_mgr.user_id,
        role="manager",
        location_id=branch_b,
    )
    add_membership(
        owner_conn,
        tenant_id=world.a.tenant_id,
        user_id=front_desk_a.user_id,
        role="front_desk",
        location_id=world.a.location_id,
    )
    add_membership(
        owner_conn,
        tenant_id=world.a.tenant_id,
        user_id=kitchen_a.user_id,
        role="artist",
        location_id=world.a.location_id,
    )
    add_membership(
        owner_conn,
        tenant_id=world.b.tenant_id,
        user_id=delegate_b.user_id,
        role="manager",
    )

    h_a = idp.bearer(owner_a.subject, email=owner_a.email)
    h_b = idp.bearer(owner_b.subject, email=owner_b.email)
    ba = f"/v1/businesses/{world.a.tenant_id}"
    bb = f"/v1/businesses/{world.b.tenant_id}"
    r = await client.put(
        f"{ba}/profile",
        json={"expected_revision": 0, "industry_ids": [2]},
        headers={**h_a, "Idempotency-Key": str(uuid7())},
    )
    assert r.status_code == 200, r.text
    d = await client.put(
        f"{ba}/configuration/draft",
        json={"expected_version": 0, "profile_revision": 1, "module_ids": ENABLED_RESTAURANT},
        headers={**h_a, "Idempotency-Key": str(uuid7())},
    )
    assert d.status_code == 200, d.text
    ver = d.json()["version"]
    for step, rev in (("validate", 1), ("publish", 2)):
        s = await client.post(
            f"{ba}/configuration/versions/{ver}/{step}",
            json={"expected_revision": rev},
            headers={**h_a, "Idempotency-Key": str(uuid7())},
        )
        assert s.status_code == 200, s.text

    grant_uuid = uuid7()
    g = await client.put(
        f"{ba}/delegations/{grant_uuid}",
        json={
            "schema_version": 1,
            "servicer_business_id": str(world.b.tenant_id),
            "permissions": ["booking.read", "booking.write"],
            "location_id": None,
            "expires_at": (datetime.now(UTC) + timedelta(days=30)).isoformat(),
        },
        headers={**h_a, "Idempotency-Key": str(uuid7())},
    )
    assert g.status_code == 200, g.text
    acc = await client.post(
        f"{bb}/delegations/{grant_uuid}/accept",
        json={
            "schema_version": 1,
            "expected_revision": 1,
            "delegate_user_ids": [str(delegate_b.user_id)],
        },
        headers={**h_b, "Idempotency-Key": str(uuid7())},
    )
    assert acc.status_code == 200, acc.text
    grant = {"grant_id": str(grant_uuid)}
    return RestaurantEnv(
        client=client,
        idp=idp,
        tenant=world.a.tenant_id,
        branch_a=world.a.location_id,
        branch_b=branch_b,
        owner=owner_a,
        branch_a_mgr=branch_a_mgr,
        branch_b_mgr=branch_b_mgr,
        front_desk_a=front_desk_a,
        kitchen_a=kitchen_a,
        delegate_b=delegate_b,
        grant_id=UUID(grant["grant_id"]),
    )


async def test_floor_areas_tables_and_independent_reservations_lifecycle(
    rest_env: RestaurantEnv,
    owner_conn: psycopg.Connection,
    app_pool: AsyncConnectionPool,
) -> None:
    area_id = uuid7()
    area_key = str(uuid7())
    r = await rest_env.client.put(
        rest_env.url(f"/areas/{area_id}"),
        json={
            "schema_version": 1,
            "expected_revision": 0,
            "location_id": str(rest_env.branch_a),
            "name": "Main Dining",
            "service_style": "dining",
        },
        headers=rest_env.headers(rest_env.branch_a_mgr, key=area_key),
    )
    assert r.status_code == 200, r.text
    area = r.json()
    assert area["revision"] == 1
    assert area["name"] == "Main Dining"

    # Idempotent replay returns identical area; mismatched body -> 422
    replay = await rest_env.client.put(
        rest_env.url(f"/areas/{area_id}"),
        json={
            "schema_version": 1,
            "expected_revision": 0,
            "location_id": str(rest_env.branch_a),
            "name": "Main Dining",
            "service_style": "dining",
        },
        headers=rest_env.headers(rest_env.branch_a_mgr, key=area_key),
    )
    assert replay.status_code == 200
    assert replay.json()["revision"] == 1
    bad_replay = await rest_env.client.put(
        rest_env.url(f"/areas/{area_id}"),
        json={
            "schema_version": 1,
            "expected_revision": 0,
            "location_id": str(rest_env.branch_a),
            "name": "Other Name",
            "service_style": "dining",
        },
        headers=rest_env.headers(rest_env.branch_a_mgr, key=area_key),
    )
    assert bad_replay.status_code == 422

    # Update area -> revision 2; stale expected_revision -> 409
    upd = await rest_env.client.put(
        rest_env.url(f"/areas/{area_id}"),
        json={
            "schema_version": 1,
            "expected_revision": 1,
            "location_id": str(rest_env.branch_a),
            "name": "Main Hall",
            "service_style": "dining",
        },
        headers=rest_env.headers(rest_env.branch_a_mgr, key=str(uuid7())),
    )
    assert upd.status_code == 200
    assert upd.json()["revision"] == 2
    stale = await rest_env.client.put(
        rest_env.url(f"/areas/{area_id}"),
        json={
            "schema_version": 1,
            "expected_revision": 1,
            "location_id": str(rest_env.branch_a),
            "name": "Stale",
            "service_style": "dining",
        },
        headers=rest_env.headers(rest_env.branch_a_mgr, key=str(uuid7())),
    )
    assert stale.status_code == 409
    assert stale.json()["error"]["code"] == "RESTAURANT_REVISION_CONFLICT"

    # Create two tables in branch A; duplicate code in same branch -> 409
    t1_id, t2_id = uuid7(), uuid7()
    t1 = await rest_env.client.put(
        rest_env.url(f"/tables/{t1_id}"),
        json={
            "schema_version": 1,
            "expected_revision": 0,
            "location_id": str(rest_env.branch_a),
            "area_id": str(area_id),
            "code": "T1",
            "min_covers": 2,
            "max_covers": 4,
        },
        headers=rest_env.headers(rest_env.branch_a_mgr, key=str(uuid7())),
    )
    assert t1.status_code == 200, t1.text
    t1_data = t1.json()
    assert t1_data["code"] == "T1"
    assert t1_data["revision"] == 1

    dup = await rest_env.client.put(
        rest_env.url(f"/tables/{t2_id}"),
        json={
            "schema_version": 1,
            "expected_revision": 0,
            "location_id": str(rest_env.branch_a),
            "area_id": str(area_id),
            "code": "T1",
            "min_covers": 2,
            "max_covers": 4,
        },
        headers=rest_env.headers(rest_env.branch_a_mgr, key=str(uuid7())),
    )
    assert dup.status_code == 409

    t2 = await rest_env.client.put(
        rest_env.url(f"/tables/{t2_id}"),
        json={
            "schema_version": 1,
            "expected_revision": 0,
            "location_id": str(rest_env.branch_a),
            "area_id": str(area_id),
            "code": "T2",
            "min_covers": 2,
            "max_covers": 6,
        },
        headers=rest_env.headers(rest_env.branch_a_mgr, key=str(uuid7())),
    )
    assert t2.status_code == 200, t2.text

    # Optional guest counterparty link
    guest_cp = uuid7()
    cp_resp = await rest_env.client.put(
        f"/v1/businesses/{rest_env.tenant}/counterparties/{guest_cp}",
        json=card(display_name="FAKE Diner", roles=["customer"]),
        headers=rest_env.headers(rest_env.owner, key=str(uuid7())),
    )
    assert cp_resp.status_code == 200

    # Front desk reserves T1 with ZERO staff shifts scheduled (table is independent of shifts!)
    slot_start = datetime(2030, 7, 15, 19, 0, tzinfo=UTC)
    slot_end = slot_start + timedelta(hours=2)

    # Party size outside min..max covers -> 422
    too_big = await rest_env.client.put(
        rest_env.url(f"/reservations/{uuid7()}"),
        json={
            "schema_version": 1,
            "table_id": str(t1_id),
            "guest_name": "Big Party",
            "party_size": 5,
            "starts_at": slot_start.isoformat(),
            "ends_at": slot_end.isoformat(),
        },
        headers=rest_env.headers(rest_env.front_desk_a, key=str(uuid7())),
    )
    assert too_big.status_code == 422

    res1_id = uuid7()
    res1 = await rest_env.client.put(
        rest_env.url(f"/reservations/{res1_id}"),
        json={
            "schema_version": 1,
            "table_id": str(t1_id),
            "guest_counterparty_id": str(guest_cp),
            "guest_name": "Alex Diner",
            "party_size": 4,
            "starts_at": slot_start.isoformat(),
            "ends_at": slot_end.isoformat(),
            "note": "Anniversary dinner",
        },
        headers=rest_env.headers(rest_env.front_desk_a, key=str(uuid7())),
    )
    assert res1.status_code == 200, res1.text
    assert res1.json()["status"] == "booked"
    assert res1.json()["revision"] == 1

    # Overlapping reservation on T1 -> 409 SLOT_CONFLICT (enforced by CORE-04 exclusion constraint)
    overlap = await rest_env.client.put(
        rest_env.url(f"/reservations/{uuid7()}"),
        json={
            "schema_version": 1,
            "table_id": str(t1_id),
            "guest_name": "Overlap Guest",
            "party_size": 2,
            "starts_at": (slot_start + timedelta(minutes=30)).isoformat(),
            "ends_at": (slot_end + timedelta(minutes=30)).isoformat(),
        },
        headers=rest_env.headers(rest_env.front_desk_a, key=str(uuid7())),
    )
    assert overlap.status_code == 409
    assert overlap.json()["error"]["code"] == "SLOT_CONFLICT"

    # Same interval on T2 succeeds independently
    res_t2 = await rest_env.client.put(
        rest_env.url(f"/reservations/{uuid7()}"),
        json={
            "schema_version": 1,
            "table_id": str(t2_id),
            "guest_name": "Second Table",
            "party_size": 4,
            "starts_at": slot_start.isoformat(),
            "ends_at": slot_end.isoformat(),
        },
        headers=rest_env.headers(rest_env.front_desk_a, key=str(uuid7())),
    )
    assert res_t2.status_code == 200

    # Lifecycle: booked -> seated -> completed; completing releases allocation so slot is free!
    seat = await rest_env.client.post(
        rest_env.url(f"/reservations/{res1_id}/events"),
        json={"schema_version": 1, "expected_revision": 1, "action": "seat"},
        headers=rest_env.headers(rest_env.front_desk_a, key=str(uuid7())),
    )
    assert seat.status_code == 200
    assert seat.json()["status"] == "seated"
    # Cannot mark seated reservation as no_show
    bad_tr = await rest_env.client.post(
        rest_env.url(f"/reservations/{res1_id}/events"),
        json={"schema_version": 1, "expected_revision": 2, "action": "no_show"},
        headers=rest_env.headers(rest_env.front_desk_a, key=str(uuid7())),
    )
    assert bad_tr.status_code == 409
    assert bad_tr.json()["error"]["code"] == "RESTAURANT_STATE_INVALID"

    done = await rest_env.client.post(
        rest_env.url(f"/reservations/{res1_id}/events"),
        json={
            "schema_version": 1,
            "expected_revision": 2,
            "action": "complete",
            "note": "Cleared and sanitized",
        },
        headers=rest_env.headers(rest_env.front_desk_a, key=str(uuid7())),
    )
    assert done.status_code == 200
    assert done.json()["status"] == "completed"
    evs = await rest_env.client.get(
        rest_env.url(f"/reservations/{res1_id}/events"),
        headers=rest_env.headers(rest_env.kitchen_a),
    )
    assert evs.status_code == 200
    assert [e["action"] for e in evs.json()["items"]] == ["seat", "complete"]

    # Slot on T1 is now immediately rebookable and cancellable!
    res3_id = uuid7()
    rebook = await rest_env.client.put(
        rest_env.url(f"/reservations/{res3_id}"),
        json={
            "schema_version": 1,
            "table_id": str(t1_id),
            "guest_name": "Walk-in Turn",
            "party_size": 2,
            "starts_at": slot_start.isoformat(),
            "ends_at": slot_end.isoformat(),
        },
        headers=rest_env.headers(rest_env.front_desk_a, key=str(uuid7())),
    )
    assert rebook.status_code == 200
    cancel = await rest_env.client.post(
        rest_env.url(f"/reservations/{res3_id}/events"),
        json={"schema_version": 1, "expected_revision": 1, "action": "cancel"},
        headers=rest_env.headers(rest_env.front_desk_a, key=str(uuid7())),
    )
    assert cancel.status_code == 200
    assert cancel.json()["status"] == "cancelled"

    # Direct tampering with restaurant_table resource kind is blocked by PostgreSQL trigger
    async with tenant_transaction(app_pool, rest_env.tenant) as conn:
        with pytest.raises(psycopg.errors.CheckViolation):
            await conn.execute(
                "update gba.resources set kind = 'chair' where tenant_id = %s and id = %s",
                (rest_env.tenant, t1_data["resource_id"]),
            )


async def test_branch_rls_isolation_and_role_access_matrix(rest_env: RestaurantEnv) -> None:
    area_a = uuid7()
    area_b = uuid7()
    assert (
        await rest_env.client.put(
            rest_env.url(f"/areas/{area_a}"),
            json={
                "schema_version": 1,
                "expected_revision": 0,
                "location_id": str(rest_env.branch_a),
                "name": "Branch A Patio",
                "service_style": "patio",
            },
            headers=rest_env.headers(rest_env.branch_a_mgr, key=str(uuid7())),
        )
    ).status_code == 200
    assert (
        await rest_env.client.put(
            rest_env.url(f"/areas/{area_b}"),
            json={
                "schema_version": 1,
                "expected_revision": 0,
                "location_id": str(rest_env.branch_b),
                "name": "Branch B Bar",
                "service_style": "bar",
            },
            headers=rest_env.headers(rest_env.branch_b_mgr, key=str(uuid7())),
        )
    ).status_code == 200

    # Branch A manager cannot write to Branch B, cannot read Branch B
    cross_write = await rest_env.client.put(
        rest_env.url(f"/areas/{uuid7()}"),
        json={
            "schema_version": 1,
            "expected_revision": 0,
            "location_id": str(rest_env.branch_b),
            "name": "Cross Branch",
            "service_style": "dining",
        },
        headers=rest_env.headers(rest_env.branch_a_mgr, key=str(uuid7())),
    )
    assert cross_write.status_code == 403
    list_a = await rest_env.client.get(
        rest_env.url("/areas"), headers=rest_env.headers(rest_env.branch_a_mgr)
    )
    assert list_a.status_code == 200
    assert [a["area_id"] for a in list_a.json()["items"]] == [str(area_a)]
    cross_get = await rest_env.client.get(
        rest_env.url(f"/areas/{area_b}"), headers=rest_env.headers(rest_env.branch_a_mgr)
    )
    assert cross_get.status_code == 404

    # Company-wide owner sees both branches
    list_all = await rest_env.client.get(
        rest_env.url("/areas"), headers=rest_env.headers(rest_env.owner)
    )
    assert list_all.status_code == 200
    assert {a["area_id"] for a in list_all.json()["items"]} == {str(area_a), str(area_b)}

    # Role matrix: front_desk cannot manage areas (403); kitchen(artist) cannot reserve (403);
    # cross-company delegate cannot access restaurant routes at all (403).
    assert (
        await rest_env.client.put(
            rest_env.url(f"/areas/{uuid7()}"),
            json={
                "schema_version": 1,
                "expected_revision": 0,
                "location_id": str(rest_env.branch_a),
                "name": "Denied",
                "service_style": "dining",
            },
            headers=rest_env.headers(rest_env.front_desk_a, key=str(uuid7())),
        )
    ).status_code == 403
    assert (
        await rest_env.client.put(
            rest_env.url(f"/reservations/{uuid7()}"),
            json={
                "schema_version": 1,
                "table_id": str(uuid7()),
                "guest_name": "Denied",
                "party_size": 2,
                "starts_at": "2030-08-01T18:00:00Z",
                "ends_at": "2030-08-01T20:00:00Z",
            },
            headers=rest_env.headers(rest_env.kitchen_a, key=str(uuid7())),
        )
    ).status_code == 403
    del_headers = {
        **rest_env.headers(rest_env.delegate_b),
        "X-Delegation-Id": str(rest_env.grant_id),
    }
    assert (
        await rest_env.client.get(rest_env.url("/areas"), headers=del_headers)
    ).status_code == 403


async def test_restaurant_module_gate_blocks_when_not_enableable(
    client: httpx.AsyncClient,
    idp: FakeIdp,
    world: BookingWorld,
    owner_a: FakeUser,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    url = f"/v1/businesses/{world.a.tenant_id}/restaurant/areas/{uuid7()}"
    payload = {
        "schema_version": 1,
        "expected_revision": 0,
        "location_id": str(world.a.location_id),
        "name": "Blocked",
        "service_style": "dining",
    }
    resp_disabled = await client.put(
        url,
        json=payload,
        headers={
            **idp.bearer(owner_a.subject, email=owner_a.email),
            "Idempotency-Key": str(uuid7()),
        },
    )
    assert resp_disabled.status_code == 409
    assert resp_disabled.json()["error"]["code"] == "MODULE_DISABLED"

    monkeypatch.setitem(
        modules.MODULES_BY_ID,
        "restaurant",
        modules.MODULES_BY_ID["restaurant"].model_copy(
            update={"enableable": False, "readiness": Readiness.IMPLEMENTED}
        ),
    )
    resp = await client.put(
        f"/v1/businesses/{world.a.tenant_id}/restaurant/areas/{uuid7()}",
        json=payload,
        headers={
            **idp.bearer(owner_a.subject, email=owner_a.email),
            "Idempotency-Key": str(uuid7()),
        },
    )
    assert resp.status_code == 409
    assert resp.json()["error"]["code"] == "RESTAURANT_NOT_READY"
