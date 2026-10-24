"""M2: driver, truck and trailer assignments with periods in the shared occupancy (FAKE data only).

ADR-0029 and docs/plan/PACKAGE_M2_DESIGN_2026-10-24.md: each driver and vehicle has its own lane; a
replacement closes one period and opens the next in one transaction; nothing is ever double-booked.
"""

from datetime import datetime
from typing import Any
from uuid import UUID, uuid7
from zoneinfo import ZoneInfo

import httpx
import psycopg
import pytest

from gorgona_booking.booking.models import ResourceUnavailableError
from gorgona_booking.booking.repository import active_resource_location
from gorgona_booking.db.pool import RuntimePool, tenant_transaction
from tests.integration import test_management_api as shared
from tests.integration.booking_support import BookingWorld
from tests.integration.configuration_support import Config
from tests.integration.conftest import ProvisionedDatabase
from tests.integration.seed import FakeUser
from tests.integration.test_l8b2_finance_races import race
from tests.integration.test_m1_transport_planning import (
    CHICAGO,
    Transport,
    accepted,
    error,
    leg,
    load,
    stop,
    transport,
)
from tests.support.fake_idp import FakeIdp

pytestmark = pytest.mark.anyio
client = shared.client
idp = shared.idp
manager_a = shared.manager_a
manager_b = shared.manager_b
__all__ = ["accepted", "client", "idp", "manager_a", "manager_b", "transport"]


def at(hour: int) -> datetime:
    """A moment on 2031-06-02 in Chicago."""
    return datetime(2031, 6, 2, hour, tzinfo=ZoneInfo(CHICAGO))


def span_stops(start: int, end: int) -> list[dict[str, Any]]:
    return [
        stop("pickup", "FAKE dock, Chicago", CHICAGO, start, start + 1),
        stop("delivery", "FAKE store, Chicago", CHICAGO, end - 2, end),
    ]


async def planned(t: Transport, start: int = 8, end: int = 17) -> tuple[UUID, UUID]:
    """A planned trip whose span is [start, end) in Chicago, carrying one load of 4."""
    item = uuid7()
    saved = await t.order(uuid7(), [load(item, 4)])
    assert saved.status_code == 200, saved.text
    trip = uuid7()
    made = await t.trip(trip, span_stops(start, end), [leg(item, 4, 1, 2)])
    assert made.status_code == 200, made.text
    return trip, item


async def driver(t: Transport, name: str = "FAKE Driver One") -> UUID:
    saved = await t.put(
        f"/drivers/{uuid7()}",
        {"location_id": str(t.world.a.location_id), "display_name": name},
    )
    assert saved.status_code == 200, saved.text
    return UUID(saved.json()["resource_id"])


async def vehicle(t: Transport, kind: str, unit: str) -> UUID:
    saved = await t.put(
        f"/vehicles/{uuid7()}",
        {"location_id": str(t.world.a.location_id), "kind": kind, "unit_number": unit},
    )
    assert saved.status_code == 200, saved.text
    return UUID(saved.json()["resource_id"])


async def assign(
    t: Transport,
    trip: UUID,
    role: str,
    resource: UUID,
    *,
    assignment: UUID | None = None,
    starts: int | None = None,
    replaces: UUID | None = None,
    key: str | None = None,
) -> httpx.Response:
    body: dict[str, Any] = {
        "schema_version": 1,
        "role": role,
        "resource_id": str(resource),
        "replaces": None if replaces is None else str(replaces),
    }
    if starts is not None:
        body["starts_at"] = at(starts).isoformat()
    return await t.client.put(
        f"{t.base}/trips/{trip}/assignments/{assignment or uuid7()}",
        json=body,
        headers={**t.headers, "Idempotency-Key": key or str(uuid7())},
    )


async def end(t: Transport, trip: UUID, assignment: UUID, hour: int) -> httpx.Response:
    return await t.client.post(
        f"{t.base}/trips/{trip}/assignments/{assignment}/end",
        json={"schema_version": 1, "ends_at": at(hour).isoformat()},
        headers={**t.headers, "Idempotency-Key": str(uuid7())},
    )


def periods(view: dict[str, Any], role: str) -> list[tuple[UUID, datetime, datetime | None, Any]]:
    """The trip's periods of one role in order: resource, start, end (None while open), replaces."""
    return [
        (
            UUID(item["resource_id"]),
            datetime.fromisoformat(item["starts_at"]),
            None if item["ends_at"] is None else datetime.fromisoformat(item["ends_at"]),
            None if item["replaces"] is None else UUID(item["replaces"]),
        )
        for item in view["assignments"]
        if item["role"] == role
    ]


async def holds(
    pool: RuntimePool, tenant: UUID, resource: UUID
) -> list[tuple[datetime, datetime, str]]:
    async with tenant_transaction(pool, tenant) as conn:
        rows = await (
            await conn.execute(
                "select lower(during), upper(during), state from gba.resource_allocations "
                "where resource_id = %s order by lower(during), upper(during), state",
                (resource,),
            )
        ).fetchall()
    return [(row[0], row[1], row[2]) for row in rows]


FORGED = (
    "insert into gba.resource_allocations (tenant_id, resource_id, source_kind, source_id, "
    "during, state) values (%s, %s, %s, %s, tstzrange(%s, %s, '[)'), 'confirmed')"
)


# M2-01 ------------------------------------------------------------------------------


async def test_without_acceptance_drivers_and_vehicles_are_not_ready(
    client: httpx.AsyncClient, world: BookingWorld, manager_a: FakeUser, idp: FakeIdp
) -> None:
    headers = idp.bearer(manager_a.subject, email=manager_a.email)
    base = f"/v1/businesses/{world.a.tenant_id}/transport"
    refused = await client.put(
        f"{base}/drivers/{uuid7()}",
        json={
            "schema_version": 1,
            "location_id": str(world.a.location_id),
            "display_name": "FAKE Driver",
        },
        headers={**headers, "Idempotency-Key": str(uuid7())},
    )
    assert error(refused) == (409, "MODULE_NOT_READY"), refused.text
    for path in ("/drivers", "/vehicles"):
        read = await client.get(base + path, headers=headers)
        assert (read.status_code, read.json()["items"]) == (200, []), read.text


async def test_drivers_and_vehicles_have_their_own_lanes(
    transport: Transport, app_pool: RuntimePool, world: BookingWorld
) -> None:
    t = transport
    driver_id = uuid7()
    body = {"location_id": str(world.a.location_id), "display_name": "FAKE Driver One"}
    saved = await t.put(f"/drivers/{driver_id}", body)
    assert saved.status_code == 200, saved.text
    view = saved.json()
    assert (view["driver_id"], view["display_name"]) == (str(driver_id), "FAKE Driver One")
    drv = UUID(view["resource_id"])
    replay = await t.put(f"/drivers/{driver_id}", body)
    assert (replay.status_code, replay.json()) == (200, view), replay.text
    truck = await vehicle(t, "truck", "FAKE-T1")
    trailer = await vehicle(t, "trailer", "FAKE-R1")
    taken = await t.put(
        f"/vehicles/{uuid7()}",
        {"location_id": str(world.a.location_id), "kind": "truck", "unit_number": "FAKE-T1"},
    )
    assert error(taken) == (409, "TRANSPORT_REFERENCE_TAKEN"), taken.text
    van = await t.put(
        f"/vehicles/{uuid7()}",
        {"location_id": str(world.a.location_id), "kind": "van", "unit_number": "FAKE-V1"},
    )
    assert van.status_code == 422, van.text
    drivers = (await t.get("/drivers")).json()["items"]
    vehicles = (await t.get("/vehicles")).json()["items"]
    assert [item["resource_id"] for item in drivers] == [str(drv)]
    assert sorted((item["kind"], item["unit_number"]) for item in vehicles) == [
        ("trailer", "FAKE-R1"),
        ("truck", "FAKE-T1"),
    ]
    # The salon staff list never shows them; booking never uses them.
    staff = await t.client.get(f"/v1/salons/{t.tenant}/staff", headers=t.headers)
    assert staff.status_code == 200, staff.text
    shown = {item["id"] for item in staff.json()}
    assert shown.isdisjoint({str(drv), str(truck), str(trailer)})
    async with tenant_transaction(app_pool, t.tenant) as conn:
        with pytest.raises(ResourceUnavailableError):
            await active_resource_location(conn, truck)
    # The database refuses forged occupancy on a transport lane and forged trip holds elsewhere.
    for resource, source in (
        (truck, "reservation"),
        (truck, "trip_assignment"),
        (world.artist_a1, "trip_assignment"),
    ):
        with pytest.raises(psycopg.errors.CheckViolation):
            async with tenant_transaction(app_pool, t.tenant) as conn:
                await conn.execute(FORGED, (t.tenant, resource, source, uuid7(), at(8), at(9)))
    assert await holds(app_pool, t.tenant, truck) == []


# M2-02, M2-03 -----------------------------------------------------------------------


async def test_assignments_hold_the_span_and_a_replacement_keeps_history(
    transport: Transport, app_pool: RuntimePool
) -> None:
    t = transport
    trip, _ = await planned(t)
    drv = await driver(t)
    truck1 = await vehicle(t, "truck", "FAKE-T1")
    truck2 = await vehicle(t, "truck", "FAKE-T2")
    trailer = await vehicle(t, "trailer", "FAKE-R1")
    first_truck = uuid7()
    for role, resource, assignment in (
        ("driver", drv, uuid7()),
        ("truck", truck1, first_truck),
        ("trailer", trailer, uuid7()),
    ):
        made = await assign(t, trip, role, resource, assignment=assignment)
        assert made.status_code == 200, made.text
    view = made.json()
    assert periods(view, "driver") == [(drv, at(8), None, None)]
    assert periods(view, "truck") == [(truck1, at(8), None, None)]
    assert periods(view, "trailer") == [(trailer, at(8), None, None)]
    for resource in (drv, truck1, trailer):
        assert await holds(app_pool, t.tenant, resource) == [(at(8), at(17), "confirmed")]
    key = str(uuid7())
    second_truck = uuid7()
    replaced = await assign(
        t, trip, "truck", truck2, assignment=second_truck, starts=12, replaces=first_truck, key=key
    )
    assert replaced.status_code == 200, replaced.text
    expected = [
        (truck1, at(8), at(12), None),
        (truck2, at(12), None, first_truck),
    ]
    assert periods(replaced.json(), "truck") == expected
    assert await holds(app_pool, t.tenant, truck1) == [
        (at(8), at(12), "confirmed"),
        (at(8), at(17), "released"),
    ]
    assert await holds(app_pool, t.tenant, truck2) == [(at(12), at(17), "confirmed")]
    # A lost answer retried with the same key answers the same and changes nothing.
    again = await assign(
        t, trip, "truck", truck2, assignment=second_truck, starts=12, replaces=first_truck, key=key
    )
    assert again.status_code == 200, again.text
    read = await t.get(f"/trips/{trip}")
    assert periods(read.json(), "truck") == expected
    assert await holds(app_pool, t.tenant, truck2) == [(at(12), at(17), "confirmed")]


# M2-04 ------------------------------------------------------------------------------


async def test_a_replacement_onto_a_busy_truck_changes_nothing(
    transport: Transport, app_pool: RuntimePool
) -> None:
    t = transport
    trip_a, _ = await planned(t)
    trip_b, _ = await planned(t, 10, 16)
    truck1 = await vehicle(t, "truck", "FAKE-T1")
    truck2 = await vehicle(t, "truck", "FAKE-T2")
    first = uuid7()
    assert (await assign(t, trip_a, "truck", truck1, assignment=first)).status_code == 200
    assert (await assign(t, trip_b, "truck", truck2)).status_code == 200
    busy = await assign(t, trip_a, "truck", truck2, starts=12, replaces=first)
    assert error(busy) == (409, "TRANSPORT_RESOURCE_BUSY"), busy.text
    read = await t.get(f"/trips/{trip_a}")
    assert periods(read.json(), "truck") == [(truck1, at(8), None, None)]
    assert await holds(app_pool, t.tenant, truck1) == [(at(8), at(17), "confirmed")]
    assert await holds(app_pool, t.tenant, truck2) == [(at(10), at(16), "confirmed")]
    async with tenant_transaction(app_pool, t.tenant) as conn:
        row = await (
            await conn.execute("select count(*) from gba.transport_assignment_ends")
        ).fetchone()
    assert row == (0,)


# M2-05 ------------------------------------------------------------------------------


async def test_racing_assignments_leave_one_holder(
    transport: Transport, app_pool: RuntimePool, test_database: ProvisionedDatabase
) -> None:
    t = transport
    trip_a, _ = await planned(t)
    trip_b, _ = await planned(t, 10, 16)
    truck = await vehicle(t, "truck", "FAKE-T1")
    schedule = (
        "select pg_catalog.pg_advisory_xact_lock(pg_catalog.hashtextextended("
        f"'gba:resource:{t.tenant}:' || %s::text, 0))"
    )
    answers = await race(
        app_pool,
        test_database,
        t.tenant,
        schedule,
        truck,
        [assign(t, trip_a, "truck", truck), assign(t, trip_b, "truck", truck)],
    )
    assert sorted(a.status_code for a in answers) == [200, 409], [a.text for a in answers]
    (refused,) = [a for a in answers if a.status_code == 409]
    assert error(refused) == (409, "TRANSPORT_RESOURCE_BUSY")
    confirmed = [h for h in await holds(app_pool, t.tenant, truck) if h[2] == "confirmed"]
    assert len(confirmed) == 1
    (winner,) = [a.json() for a in answers if a.status_code == 200]
    trip = UUID(winner["trip_id"])
    (current,) = [item for item in winner["assignments"] if item["role"] == "truck"]
    truck2 = await vehicle(t, "truck", "FAKE-T2")
    truck3 = await vehicle(t, "truck", "FAKE-T3")
    replacing = UUID(current["assignment_id"])
    answers = await race(
        app_pool,
        test_database,
        t.tenant,
        "select 1 from gba.transport_trips where id = %s for update",
        trip,
        [
            assign(t, trip, "truck", truck2, starts=13, replaces=replacing),
            assign(t, trip, "truck", truck3, starts=13, replaces=replacing),
        ],
    )
    assert sorted(a.status_code for a in answers) == [200, 409], [a.text for a in answers]
    (stale,) = [a for a in answers if a.status_code == 409]
    assert error(stale) == (409, "TRANSPORT_ASSIGNMENT_CONFLICT")
    read = await t.get(f"/trips/{trip}")
    assert [p[2] for p in periods(read.json(), "truck")] == [at(13), None]


# M2-06 ------------------------------------------------------------------------------


async def _stretch_by_sql(pool: RuntimePool, tenant: UUID, trip: UUID) -> None:
    """Move the last delivery window two hours later by direct SQL, bypassing the service."""
    async with tenant_transaction(pool, tenant) as conn:
        await conn.execute("delete from gba.transport_legs where trip_id = %s", (trip,))
        await conn.execute(
            "delete from gba.transport_stops where trip_id = %s and position = 2", (trip,)
        )
        await conn.execute(
            "insert into gba.transport_stops (tenant_id, trip_id, position, kind, place, "
            "time_zone, window_start, window_end) values (%s, %s, 2, 'delivery', "
            "'FAKE store', %s, %s, %s)",
            (tenant, trip, CHICAGO, at(15), at(19)),
        )


async def test_an_open_assignment_freezes_the_span(
    transport: Transport, app_pool: RuntimePool
) -> None:
    t = transport
    trip, item = await planned(t)
    truck = await vehicle(t, "truck", "FAKE-T1")
    assert (await assign(t, trip, "truck", truck)).status_code == 200
    longer = await t.trip(trip, span_stops(8, 19), [leg(item, 4, 1, 2)], revision=1)
    assert error(longer) == (409, "TRANSPORT_TRIP_ASSIGNED"), longer.text
    same_span = await t.trip(trip, span_stops(8, 17), [leg(item, 3, 1, 2)], revision=1)
    assert same_span.status_code == 200, same_span.text
    assert same_span.json()["revision"] == 2
    with pytest.raises(psycopg.errors.CheckViolation):
        await _stretch_by_sql(app_pool, t.tenant, trip)
    assert await holds(app_pool, t.tenant, truck) == [(at(8), at(17), "confirmed")]


# M2-07 ------------------------------------------------------------------------------


async def test_ending_releases_the_rest_and_keeps_history(
    transport: Transport, app_pool: RuntimePool
) -> None:
    t = transport
    trip, _ = await planned(t)
    drv = await driver(t)
    drv2 = await driver(t, "FAKE Driver Two")
    trailer = await vehicle(t, "trailer", "FAKE-R1")
    first = uuid7()
    assert (await assign(t, trip, "driver", drv, assignment=first)).status_code == 200
    ended = await end(t, trip, first, 13)
    assert ended.status_code == 200, ended.text
    assert periods(ended.json(), "driver") == [(drv, at(8), at(13), None)]
    assert await holds(app_pool, t.tenant, drv) == [
        (at(8), at(13), "confirmed"),
        (at(8), at(17), "released"),
    ]
    assert error(await end(t, trip, first, 14)) == (409, "TRANSPORT_ASSIGNMENT_CONFLICT")
    early = await assign(t, trip, "driver", drv2, starts=12)
    assert error(early) == (422, "TRANSPORT_ASSIGNMENT_INVALID"), early.text
    second = uuid7()
    later = await assign(t, trip, "driver", drv2, assignment=second, starts=14)
    assert later.status_code == 200, later.text
    assert periods(later.json(), "driver") == [
        (drv, at(8), at(13), None),
        (drv2, at(14), None, None),
    ]
    for refused in (
        await assign(t, trip, "truck", drv),  # a driver's lane is not a truck
        await assign(t, trip, "trailer", trailer, starts=18),  # outside the span
        await assign(t, trip, "driver", drv2, starts=15, replaces=second),  # same resource
    ):
        assert error(refused) == (422, "TRANSPORT_ASSIGNMENT_INVALID"), refused.text
    unnamed = await assign(t, trip, "driver", drv, starts=15)
    assert error(unnamed) == (409, "TRANSPORT_ASSIGNMENT_CONFLICT"), unnamed.text


# M2-08 ------------------------------------------------------------------------------


COUNTS = (
    "select (select count(*) from gba.transport_drivers), "
    "(select count(*) from gba.transport_vehicles), "
    "(select count(*) from gba.transport_assignments), "
    "(select count(*) from gba.transport_assignment_ends)"
)


async def _counts(pool: RuntimePool, tenant: UUID, location: UUID | None = None) -> tuple[int, ...]:
    async with tenant_transaction(pool, tenant) as conn:
        if location is not None:
            await conn.execute(
                "select pg_catalog.set_config('gba.location_id', %s, true)", (str(location),)
            )
        row = await (await conn.execute(COUNTS)).fetchone()
    assert row is not None
    return tuple(int(n) for n in row)


async def test_without_the_module_writes_are_refused_and_scope_holds(
    transport: Transport,
    app_pool: RuntimePool,
    idp: FakeIdp,
    manager_a: FakeUser,
    manager_b: FakeUser,
) -> None:
    t = transport
    trip, _ = await planned(t)
    drv = await driver(t)
    truck = await vehicle(t, "truck", "FAKE-T1")
    assert (await assign(t, trip, "driver", drv)).status_code == 200
    ending = uuid7()
    assert (await assign(t, trip, "truck", truck, assignment=ending)).status_code == 200
    assert (await end(t, trip, ending, 16)).status_code == 200
    before = await _counts(app_pool, t.tenant)
    assert before == (1, 1, 2, 1)
    for statement in (
        "update gba.transport_assignments set starts_at = starts_at",
        "delete from gba.transport_assignments",
        "delete from gba.transport_assignment_ends",
        "update gba.transport_drivers set display_name = 'FAKE renamed'",
        "delete from gba.transport_vehicles",
    ):
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            async with tenant_transaction(app_pool, t.tenant) as conn:
                await conn.execute(statement)
    with pytest.raises(psycopg.errors.CheckViolation):
        async with tenant_transaction(app_pool, t.tenant) as conn:
            await conn.execute(
                "update gba.resource_allocations set state = 'released' "
                "where resource_id = %s and state = 'confirmed'",
                (drv,),
            )
    assert await _counts(app_pool, t.tenant, location=uuid7()) == (0, 0, 0, 0)
    assert await _counts(app_pool, t.world.b.tenant_id) == (0, 0, 0, 0)
    other = idp.bearer(manager_b.subject, email=manager_b.email)
    foreign = await t.get("/drivers", headers=other)
    assert foreign.status_code in (403, 404), foreign.text
    # Turned off: writes are refused and write nothing; reads continue.
    await Config(t.client, idp).publish(
        manager_a, t.tenant, 1, ["booking_resources", "counterparties"]
    )
    off = await t.put(
        f"/drivers/{uuid7()}",
        {"location_id": str(t.world.a.location_id), "display_name": "FAKE Driver Two"},
    )
    assert error(off) == (409, "MODULE_DISABLED"), off.text
    assert error(await end(t, trip, ending, 15)) == (409, "MODULE_DISABLED")
    assert await _counts(app_pool, t.tenant) == before
    read = await t.get("/drivers")
    assert (read.status_code, len(read.json()["items"])) == (200, 1), read.text
