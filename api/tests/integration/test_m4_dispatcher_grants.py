"""M4: an independent dispatcher works within each carrier's grant (TMS-02; FAKE data only).

ADR-0031 and docs/plan/PACKAGE_M4_DESIGN_2026-10-24.md: transport rights are granted per action
through the cross-company delegation of ADR-0017; fleet registration is never delegated;
revocation, removal and expiry block the next command while earlier facts stay with their
executor.
"""

import asyncio
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from uuid import uuid7

import httpx
import psycopg
import pytest

from gorgona_booking.db.pool import RuntimePool, tenant_transaction
from gorgona_booking.db.provisioning import owner_tenant_transaction
from tests.integration import test_management_api as shared
from tests.integration.booking_support import BookingWorld
from tests.integration.seed import FakeUser, seed_other_branch, seed_salon
from tests.integration.test_delegations import (
    ALL,
    Parties,
    _member,
    owner_a,
    owner_b,
    parties,
)
from tests.integration.test_m1_transport_planning import (
    Transport,
    accepted,
    leg,
    load,
    transport,
)
from tests.integration.test_m2_transport_assignments import (
    assign,
    planned,
    span_stops,
    vehicle,
)
from tests.integration.test_m3_transport_events import event

pytestmark = pytest.mark.anyio
client = shared.client
idp = shared.idp
manager_a = shared.manager_a
__all__ = ["accepted", "client", "idp", "manager_a", "owner_a", "owner_b", "parties", "transport"]

TRANSPORT = ["transport.read", "transport.plan", "transport.assign", "transport.events"]
WATCH = ["transport.read", "transport.events"]


@pytest.fixture
def dispatcher(world: BookingWorld, owner_conn: psycopg.Connection) -> FakeUser:
    """A company-wide manager of the independent dispatch company (business B)."""
    return _member(owner_conn, world.b.tenant_id, "manager", "transport-dispatcher")


def acting(t: Transport, parties: Parties, user: FakeUser) -> Transport:
    """The same carrier's transport API, called by another person."""
    return replace(t, headers=parties.idp.bearer(user.subject, email=user.email))


# M4-01 ------------------------------------------------------------------------------


async def test_transport_rights_are_grantable_but_fleet_registration_never(
    transport: Transport,
    client: httpx.AsyncClient,
    parties: Parties,
    owner_a: FakeUser,
    owner_b: FakeUser,
    dispatcher: FakeUser,
) -> None:
    await parties.active_grant(owner_a, owner_b, [dispatcher], permissions=[*ALL, *TRANSPORT])
    me = await client.get(
        "/v1/me", headers=parties.idp.bearer(dispatcher.subject, email=dispatcher.email)
    )
    assert me.status_code == 200, me.text
    (delegation,) = me.json()["delegations"]
    assert sorted(delegation["permissions"]) == sorted([*ALL, *TRANSPORT])
    for permissions in (["transport.manage"], [*ALL, *TRANSPORT, "transport.manage"]):
        refused = await parties.issue(owner_a, uuid7(), terms={"permissions": permissions})
        assert refused.status_code == 422, refused.text


# M4-02, M4-05 -----------------------------------------------------------------------


async def test_a_dispatcher_acts_only_within_the_granted_actions(
    transport: Transport,
    parties: Parties,
    owner_a: FakeUser,
    owner_b: FakeUser,
    dispatcher: FakeUser,
    owner_conn: psycopg.Connection,
    world: BookingWorld,
) -> None:
    t = transport
    trip, _ = await planned(t)
    truck = await vehicle(t, "truck", "FAKE-T1")
    grant = await parties.active_grant(owner_a, owner_b, [dispatcher], permissions=WATCH)
    d = acting(t, parties, dispatcher)
    listed = await d.get("/trips")
    assert listed.status_code == 200, listed.text
    assert [item["trip_id"] for item in listed.json()["items"]] == [str(trip)]
    recorded = await event(d, trip, "loaded", 1, quantities=((1, 4),))
    assert recorded.status_code == 200, recorded.text
    for refused in (
        await assign(d, trip, "truck", truck),
        await d.order(uuid7(), [load(uuid7(), 1)]),
        await d.put(
            f"/vehicles/{uuid7()}",
            {"location_id": str(world.a.location_id), "kind": "truck", "unit_number": "FAKE-T9"},
        ),
    ):
        assert refused.status_code == 403, refused.text
    unnamed = _member(owner_conn, world.b.tenant_id, "manager", "transport-unnamed")
    for user in (unnamed, owner_b):
        assert (await acting(t, parties, user).get("/trips")).status_code == 403
    # Every delegated request is audited in the carrier's company with the grant used.
    with owner_tenant_transaction(owner_conn, world.a.tenant_id):
        rows = owner_conn.execute(
            "select details from gba.audit_events "
            "where action = 'delegation.access' and target_id = %s",
            (str(grant),),
        ).fetchall()
    assert {row[0]["permission"] for row in rows} >= set(WATCH)
    assert {row[0]["servicer_business_id"] for row in rows} == {str(world.b.tenant_id)}


# M4-03 ------------------------------------------------------------------------------


async def test_each_carrier_grant_limits_only_its_own_business(
    transport: Transport,
    client: httpx.AsyncClient,
    parties: Parties,
    owner_a: FakeUser,
    owner_b: FakeUser,
    dispatcher: FakeUser,
    owner_conn: psycopg.Connection,
    world: BookingWorld,
) -> None:
    t = transport
    trip, _ = await planned(t)
    carrier_c = seed_salon(owner_conn, "carrier-c")
    owner_c = _member(owner_conn, carrier_c.tenant_id, "owner", "owner-c")
    await parties.active_grant(owner_a, owner_b, [dispatcher], permissions=WATCH)
    headers = parties.idp.bearer(dispatcher.subject, email=dispatcher.email)
    base_c = f"/v1/businesses/{carrier_c.tenant_id}/transport"
    assert (await client.get(base_c + "/trips", headers=headers)).status_code == 403
    c_grant = uuid7()
    issued = await parties.issue(
        owner_c, c_grant, business=carrier_c.tenant_id, terms={"permissions": ["transport.read"]}
    )
    assert issued.status_code == 200, issued.text
    accepted = await parties.act(owner_b, world.b.tenant_id, c_grant, "accept", 1, [dispatcher])
    assert accepted.status_code == 200, accepted.text
    read = await client.get(base_c + "/trips", headers=headers)
    assert (read.status_code, read.json()["items"]) == (200, [])
    refused = await client.post(
        f"{base_c}/trips/{trip}/events",
        json={
            "schema_version": 1,
            "source": "dispatcher",
            "source_event_id": "FAKE-C-1",
            "stop_position": 1,
            "kind": "arrived",
            "occurred_at": datetime.now(UTC).isoformat(),
            "quantities": [],
        },
        headers={**headers, "Idempotency-Key": str(uuid7())},
    )
    assert refused.status_code == 403, refused.text
    # Carrier A's grant still decides what happens in carrier A.
    allowed = await event(acting(t, parties, dispatcher), trip, "arrived", 1)
    assert allowed.status_code == 200, allowed.text


# M4-04 ------------------------------------------------------------------------------


async def test_revocation_removal_and_expiry_block_the_next_transport_command(
    transport: Transport,
    parties: Parties,
    owner_a: FakeUser,
    owner_b: FakeUser,
    dispatcher: FakeUser,
    app_pool: RuntimePool,
    owner_conn: psycopg.Connection,
    world: BookingWorld,
) -> None:
    t = transport
    truck = await vehicle(t, "truck", "FAKE-T1")
    grant = await parties.active_grant(owner_a, owner_b, [dispatcher], permissions=TRANSPORT)
    d = acting(t, parties, dispatcher)
    item, trip = uuid7(), uuid7()
    assert (await d.order(uuid7(), [load(item, 4)])).status_code == 200
    planned_trip = await d.trip(trip, span_stops(8, 17), [leg(item, 4, 1, 2)])
    assert planned_trip.status_code == 200, planned_trip.text
    assert (await assign(d, trip, "truck", truck)).status_code == 200
    key = str(uuid7())
    body = {
        "schema_version": 1,
        "source": "dispatcher",
        "source_event_id": "FAKE-LOAD-1",
        "stop_position": 1,
        "kind": "loaded",
        "occurred_at": datetime.now(UTC).isoformat(),
        "quantities": [{"leg_position": 1, "quantity": 4}],
    }
    url = f"{d.base}/trips/{trip}/events"
    loaded = await d.client.post(url, json=body, headers={**d.headers, "Idempotency-Key": key})
    assert loaded.status_code == 200, loaded.text
    revoked = await parties.act(owner_a, world.a.tenant_id, grant, "revoke", 2)
    assert revoked.status_code == 200, revoked.text
    assert (await event(d, trip, "arrived", 2)).status_code == 403
    replay = await d.client.post(url, json=body, headers={**d.headers, "Idempotency-Key": key})
    assert replay.status_code == 403
    assert str(trip) not in replay.text
    # Earlier facts stay, recorded with the person who did them.
    async with tenant_transaction(app_pool, t.tenant) as conn:
        row = await (
            await conn.execute(
                "select (select array_agg(distinct recorded_by) from gba.transport_stop_events "
                "where trip_id = %s), (select array_agg(distinct created_by) "
                "from gba.transport_assignments where trip_id = %s)",
                (trip, trip),
            )
        ).fetchone()
    assert row == ([dispatcher.user_id], [dispatcher.user_id])
    # The servicer removes a delegate, ends the relationship; expiry ends access by itself.
    second = _member(owner_conn, world.b.tenant_id, "manager", "transport-second")
    other = await parties.active_grant(owner_a, owner_b, [dispatcher, second], permissions=WATCH)
    assert (await acting(t, parties, second).get("/trips")).status_code == 200
    removed = await parties.act(owner_b, world.b.tenant_id, other, "delegates", 2, [second])
    assert removed.status_code == 200, removed.text
    assert (await d.get("/trips")).status_code == 403
    ended = await parties.act(owner_b, world.b.tenant_id, other, "revoke", 3)
    assert ended.status_code == 200, ended.text
    assert (await acting(t, parties, second).get("/trips")).status_code == 403
    await parties.active_grant(
        owner_a,
        owner_b,
        [second],
        permissions=WATCH,
        expires_at=(datetime.now(UTC) + timedelta(seconds=3)).isoformat(),
    )
    assert (await acting(t, parties, second).get("/trips")).status_code == 200
    await asyncio.sleep(3.5)
    assert (await acting(t, parties, second).get("/trips")).status_code == 403


# M4-06 ------------------------------------------------------------------------------


async def test_a_location_limited_grant_keeps_other_branches_out(
    transport: Transport,
    parties: Parties,
    owner_a: FakeUser,
    owner_b: FakeUser,
    dispatcher: FakeUser,
    owner_conn: psycopg.Connection,
    world: BookingWorld,
) -> None:
    t = transport
    main_trip, _ = await planned(t)
    other_location, _ = seed_other_branch(owner_conn, world.a)
    item = uuid7()
    assert (await t.order(uuid7(), [load(item, 4)])).status_code == 200
    other_trip = uuid7()
    made = await t.put(
        f"/trips/{other_trip}",
        {
            "expected_revision": 0,
            "location_id": str(other_location),
            "reference": f"FAKE-TR-{other_trip.hex[-8:]}",
            "stops": span_stops(8, 17),
            "legs": [leg(item, 4, 1, 2)],
        },
    )
    assert made.status_code == 200, made.text
    await parties.active_grant(
        owner_a, owner_b, [dispatcher], permissions=WATCH, location_id=str(world.a.location_id)
    )
    d = acting(t, parties, dispatcher)
    listed = await d.get("/trips")
    assert [item["trip_id"] for item in listed.json()["items"]] == [str(main_trip)]
    assert (await d.get(f"/trips/{other_trip}")).status_code == 404
    hidden = await event(d, other_trip, "loaded", 1, quantities=((1, 4),))
    assert hidden.status_code == 404, hidden.text
    shown = await event(d, main_trip, "loaded", 1, quantities=((1, 4),))
    assert shown.status_code == 200, shown.text
