"""M3: trip stop events as idempotent facts; partial delivery (FAKE data only).

ADR-0030 and docs/plan/PACKAGE_M3_DESIGN_2026-10-24.md: an event is an insert-only fact with a
source event id; a repeat changes nothing; quantities per leg never exceed the plan or the load.
"""

from datetime import datetime
from typing import Any
from uuid import UUID, uuid7

import httpx
import psycopg
import pytest

from gorgona_booking.db.pool import RuntimePool, tenant_transaction
from tests.integration import test_management_api as shared
from tests.integration.configuration_support import Config
from tests.integration.conftest import ProvisionedDatabase
from tests.integration.seed import FakeUser
from tests.integration.test_l8b2_finance_races import race
from tests.integration.test_m1_transport_planning import (
    CHICAGO,
    INDIANAPOLIS,
    NEW_YORK,
    Transport,
    accepted,
    error,
    leg,
    load,
    stop,
    transport,
)
from tests.integration.test_m2_transport_assignments import assign, at, periods, planned, vehicle
from tests.support.fake_idp import FakeIdp

pytestmark = pytest.mark.anyio
client = shared.client
idp = shared.idp
manager_a = shared.manager_a
manager_b = shared.manager_b
__all__ = ["accepted", "client", "idp", "manager_a", "manager_b", "transport"]

INTERSTATE = [
    stop("pickup", "FAKE dock, Chicago", CHICAGO, 8, 10),
    stop("delivery", "FAKE yard, Indianapolis", INDIANAPOLIS, 14, 16),
    stop("delivery", "FAKE store, New York", NEW_YORK, 9, 12),
]


async def interstate(t: Transport) -> UUID:
    """One trip: leg 1 carries 10 pallets to Indianapolis, leg 2 carries 6 crates to New York."""
    first, second = uuid7(), uuid7()
    saved = await t.order(uuid7(), [load(first, 10), load(second, 6, "FAKE crates")])
    assert saved.status_code == 200, saved.text
    trip = uuid7()
    made = await t.trip(trip, INTERSTATE, [leg(first, 10, 1, 2), leg(second, 6, 1, 3)])
    assert made.status_code == 200, made.text
    return trip


async def event(
    t: Transport,
    trip: UUID,
    kind: str,
    stop_position: int,
    *,
    quantities: tuple[tuple[int, int], ...] = (),
    source: str = "telematics",
    source_id: str | None = None,
    hour: int = 9,
    note: str | None = None,
) -> httpx.Response:
    return await t.client.post(
        f"{t.base}/trips/{trip}/events",
        json={
            "schema_version": 1,
            "source": source,
            "source_event_id": source_id or f"FAKE-{uuid7()}",
            "stop_position": stop_position,
            "kind": kind,
            "occurred_at": at(hour).isoformat(),
            "note": note,
            "quantities": [{"leg_position": p, "quantity": q} for p, q in quantities],
        },
        headers={**t.headers, "Idempotency-Key": str(uuid7())},
    )


def progress(view: dict[str, Any]) -> list[tuple[int, ...]]:
    """Per leg: position, planned, loaded, delivered, refused, damaged."""
    return [
        (
            item["position"],
            item["quantity"],
            item["loaded"],
            item["delivered"],
            item["refused"],
            item["damaged"],
        )
        for item in view["legs"]
    ]


async def _counts(pool: RuntimePool, tenant: UUID, location: UUID | None = None) -> tuple[int, int]:
    async with tenant_transaction(pool, tenant) as conn:
        if location is not None:
            await conn.execute(
                "select pg_catalog.set_config('gba.location_id', %s, true)", (str(location),)
            )
        row = await (
            await conn.execute(
                "select (select count(*) from gba.transport_stop_events), "
                "(select count(*) from gba.transport_event_quantities)"
            )
        ).fetchone()
    assert row is not None
    return int(row[0]), int(row[1])


# M3-01, M3-02 -----------------------------------------------------------------------


async def test_events_start_the_trip_and_record_partial_delivery(transport: Transport) -> None:
    t = transport
    trip = await interstate(t)
    arrived = await event(t, trip, "arrived", 1, hour=8)
    assert arrived.status_code == 200, arrived.text
    assert arrived.json()["status"] == "in_transit"
    for kind, position, quantities in (
        ("loaded", 1, ((1, 10), (2, 6))),
        ("departed", 1, ()),
        ("arrived", 2, ()),
        ("delivered", 2, ((1, 7),)),
        ("refused", 2, ((1, 2),)),
        ("damaged", 2, ((1, 1),)),
        ("delivered", 3, ((2, 4),)),
    ):
        recorded = await event(t, trip, kind, position, quantities=quantities, note="FAKE note")
        assert recorded.status_code == 200, recorded.text
    view = recorded.json()
    assert progress(view) == [(1, 10, 10, 7, 2, 1), (2, 6, 6, 4, 0, 0)]
    kinds = [(item["kind"], item["stop_position"]) for item in view["events"]]
    assert kinds[:3] == [("arrived", 1), ("loaded", 1), ("departed", 1)]
    assert len(kinds) == 8
    first = view["events"][0]
    assert datetime.fromisoformat(first["occurred_at"]) == at(8)
    assert first["occurred_at"].endswith(("Z", "+00:00"))
    loaded = view["events"][1]
    assert sorted((q["leg_position"], q["quantity"]) for q in loaded["quantities"]) == [
        (1, 10),
        (2, 6),
    ]


# M3-03 ------------------------------------------------------------------------------


async def test_a_repeated_event_changes_nothing(
    transport: Transport, app_pool: RuntimePool
) -> None:
    t = transport
    trip = await interstate(t)
    assert (await event(t, trip, "loaded", 1, quantities=((1, 10),))).status_code == 200
    first = await event(t, trip, "delivered", 2, quantities=((1, 5),), source_id="FAKE-POD-1")
    assert first.status_code == 200, first.text
    before = await _counts(app_pool, t.tenant)
    again = await event(t, trip, "delivered", 2, quantities=((1, 5),), source_id="FAKE-POD-1")
    assert again.status_code == 200, again.text
    assert progress(again.json()) == progress(first.json())
    assert await _counts(app_pool, t.tenant) == before
    other = await event(t, trip, "delivered", 2, quantities=((1, 4),), source_id="FAKE-POD-1")
    assert error(other) == (409, "TRANSPORT_EVENT_CONFLICT"), other.text
    # The same id from another source is another fact.
    dispatcher = await event(
        t, trip, "delivered", 2, quantities=((1, 1),), source="dispatcher", source_id="FAKE-POD-1"
    )
    assert dispatcher.status_code == 200, dispatcher.text
    assert progress(dispatcher.json())[0] == (1, 10, 10, 6, 0, 0)


# M3-04 ------------------------------------------------------------------------------


async def test_quantities_never_exceed_the_plan_or_the_load(
    transport: Transport, app_pool: RuntimePool
) -> None:
    t = transport
    trip = await interstate(t)
    for kind, position, quantities, expected in (
        ("loaded", 1, ((1, 11),), (409, "TRANSPORT_QUANTITY_EXCEEDED")),
        ("delivered", 2, ((1, 1),), (409, "TRANSPORT_QUANTITY_EXCEEDED")),
        ("loaded", 2, ((1, 1),), (422, "TRANSPORT_EVENT_INVALID")),
        ("delivered", 3, ((1, 1),), (422, "TRANSPORT_EVENT_INVALID")),
        ("arrived", 1, ((1, 1),), (422, "TRANSPORT_EVENT_INVALID")),
        ("delivered", 2, (), (422, "TRANSPORT_EVENT_INVALID")),
        ("loaded", 1, ((9, 1),), (422, "TRANSPORT_EVENT_INVALID")),
        ("arrived", 9, (), (422, "TRANSPORT_EVENT_INVALID")),
    ):
        refused = await event(t, trip, kind, position, quantities=quantities)
        assert error(refused) == expected, (kind, position, quantities, refused.text)
    assert await _counts(app_pool, t.tenant) == (0, 0)
    read = await t.get(f"/trips/{trip}")
    assert read.json()["status"] == "planned"
    assert (await event(t, trip, "loaded", 1, quantities=((1, 4),))).status_code == 200
    over = await event(t, trip, "delivered", 2, quantities=((1, 3),), hour=15)
    assert over.status_code == 200, over.text
    beyond = await event(t, trip, "damaged", 2, quantities=((1, 2),))
    assert error(beyond) == (409, "TRANSPORT_QUANTITY_EXCEEDED")


# M3-05 ------------------------------------------------------------------------------


async def test_a_started_trip_keeps_its_plan_and_can_change_its_truck(
    transport: Transport, app_pool: RuntimePool
) -> None:
    t = transport
    trip, item = await planned(t)
    truck1 = await vehicle(t, "truck", "FAKE-T1")
    truck2 = await vehicle(t, "truck", "FAKE-T2")
    first = uuid7()
    assert (await assign(t, trip, "truck", truck1, assignment=first)).status_code == 200
    assert (await event(t, trip, "loaded", 1, quantities=((1, 4),))).status_code == 200
    stops = [
        stop("pickup", "FAKE dock, Chicago", CHICAGO, 8, 9),
        stop("delivery", "FAKE store, Chicago", CHICAGO, 15, 17),
    ]
    replanned = await t.trip(trip, stops, [leg(item, 3, 1, 2)], revision=1)
    assert error(replanned) == (409, "TRANSPORT_TRIP_STARTED"), replanned.text
    for statement in (
        "delete from gba.transport_legs where trip_id = %s",
        "delete from gba.transport_stops where trip_id = %s and position = 2",
        "update gba.transport_trips set status = 'planned' where id = %s",
    ):
        with pytest.raises(psycopg.errors.CheckViolation):
            async with tenant_transaction(app_pool, t.tenant) as conn:
                await conn.execute(statement, (trip,))
    replaced = await assign(t, trip, "truck", truck2, starts=12, replaces=first)
    assert replaced.status_code == 200, replaced.text
    assert [p[0] for p in periods(replaced.json(), "truck")] == [truck1, truck2]
    assert replaced.json()["status"] == "in_transit"


# M3-06 ------------------------------------------------------------------------------


async def test_racing_deliveries_never_exceed_the_load(
    transport: Transport, app_pool: RuntimePool, test_database: ProvisionedDatabase
) -> None:
    t = transport
    trip, _ = await planned(t)
    assert (await event(t, trip, "loaded", 1, quantities=((1, 4),))).status_code == 200
    answers = await race(
        app_pool,
        test_database,
        t.tenant,
        "select 1 from gba.transport_trips where id = %s for update",
        trip,
        [
            event(t, trip, "delivered", 2, quantities=((1, 3),)),
            event(t, trip, "delivered", 2, quantities=((1, 3),)),
        ],
    )
    assert sorted(a.status_code for a in answers) == [200, 409], [a.text for a in answers]
    (refused,) = [a for a in answers if a.status_code == 409]
    assert error(refused) == (409, "TRANSPORT_QUANTITY_EXCEEDED")
    read = await t.get(f"/trips/{trip}")
    assert progress(read.json()) == [(1, 4, 4, 3, 0, 0)]


# M3-07 ------------------------------------------------------------------------------


async def test_without_the_module_events_are_refused_and_scope_holds(
    transport: Transport,
    app_pool: RuntimePool,
    idp: FakeIdp,
    manager_a: FakeUser,
    manager_b: FakeUser,
) -> None:
    t = transport
    trip, _ = await planned(t)
    assert (await event(t, trip, "loaded", 1, quantities=((1, 4),))).status_code == 200
    before = await _counts(app_pool, t.tenant)
    assert before == (1, 1)
    for statement in (
        "update gba.transport_stop_events set note = 'FAKE changed'",
        "delete from gba.transport_stop_events",
        "update gba.transport_event_quantities set quantity = 1",
        "delete from gba.transport_event_quantities",
    ):
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            async with tenant_transaction(app_pool, t.tenant) as conn:
                await conn.execute(statement)
    assert await _counts(app_pool, t.tenant, location=uuid7()) == (0, 0)
    assert await _counts(app_pool, t.world.b.tenant_id) == (0, 0)
    other = idp.bearer(manager_b.subject, email=manager_b.email)
    foreign = await t.get(f"/trips/{trip}", headers=other)
    assert foreign.status_code in (403, 404), foreign.text
    await Config(t.client, idp).publish(
        manager_a, t.tenant, 1, ["booking_resources", "counterparties"]
    )
    off = await event(t, trip, "delivered", 2, quantities=((1, 1),))
    assert error(off) == (409, "MODULE_DISABLED"), off.text
    assert await _counts(app_pool, t.tenant) == before
