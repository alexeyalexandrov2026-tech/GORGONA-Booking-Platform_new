"""R3a: assigning a rental unit to a booking on the shared occupancy (package R; FAKE data).

docs/plan/PACKAGE_R3A_DESIGN_2026-11-03.md: every unit has its own occupancy resource; an assignment
holds it for the booking period through one confirmed allocation, so a unit is never issued twice.
"""

from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid7

import httpx
import psycopg
import pytest

from gorgona_booking.db.pool import RuntimePool, tenant_transaction
from gorgona_booking.db.provisioning import owner_tenant_transaction
from tests.integration.configuration_support import Config
from tests.integration.conftest import ProvisionedDatabase
from tests.integration.seed import FakeUser, seed_other_branch
from tests.integration.test_l8b2_finance_races import race
from tests.integration.test_r1_rental_catalog import (
    Rental,
    accepted,
    client,
    error,
    idp,
    manager_a,
    manager_b,
    rental,
)
from tests.integration.test_r2_rental_bookings import at, book, party
from tests.support.fake_idp import FakeIdp

pytestmark = pytest.mark.anyio
__all__ = ["accepted", "client", "idp", "manager_a", "manager_b", "rental"]


async def units(rental: Rental, count: int) -> tuple[UUID, list[UUID]]:
    car = uuid7()
    assert (await rental.klass(car)).status_code == 200
    made = []
    for _ in range(count):
        unit = uuid7()
        assert (await rental.unit(unit, car)).status_code == 200
        made.append(unit)
    return car, made


async def booked(rental: Rental, car: UUID, customer: UUID, starts: str, ends: str) -> str:
    saved = await book(rental, car, customer, starts, ends)
    assert saved.status_code == 200, saved.text
    booking: str = saved.json()["booking_id"]
    return booking


async def assign(
    rental: Rental, booking: str, unit: UUID, headers: dict[str, str] | None = None
) -> httpx.Response:
    return await rental.client.post(
        f"{rental.base}/bookings/{booking}/assignment",
        json={"schema_version": 1, "unit_id": str(unit)},
        headers={**(headers or rental.headers), "Idempotency-Key": str(uuid7())},
    )


def holds(rental: Rental, booking: str) -> list[tuple[Any, ...]]:
    with owner_tenant_transaction(rental.owner_conn, rental.tenant):
        return rental.owner_conn.execute(
            "select a.unit_id, x.state, x.during, x.resource_id = u.resource_id, l.reason "
            "from gba.rental_assignments a "
            "join gba.rental_units u on u.tenant_id = a.tenant_id and u.id = a.unit_id "
            "join gba.resource_allocations x on x.tenant_id = a.tenant_id "
            "and x.source_kind = 'rental_assignment' and x.source_id = a.id "
            "left join gba.rental_assignment_releases l "
            "on l.tenant_id = a.tenant_id and l.assignment_id = a.id "
            "where a.booking_id = %s order by a.assigned_at",
            (booking,),
        ).fetchall()


# R3a-01 -----------------------------------------------------------------------------


async def test_every_unit_has_its_own_rental_resource(rental: Rental) -> None:
    car, (unit,) = await units(rental, 1)
    resource = (
        "select r.kind, r.location_id, r.is_active from gba.rental_units u "
        "join gba.resources r on r.tenant_id = u.tenant_id and r.id = u.resource_id "
        "where u.id = %s"
    )
    with owner_tenant_transaction(rental.owner_conn, rental.tenant):
        row = rental.owner_conn.execute(resource, (unit,)).fetchone()
    assert row == ("rental_unit", rental.world.a.location_id, True)
    retired = await rental.unit(unit, car, revision=1, state="retired")
    assert retired.status_code == 200, retired.text
    with owner_tenant_transaction(rental.owner_conn, rental.tenant):
        row = rental.owner_conn.execute(resource, (unit,)).fetchone()
    assert row == ("rental_unit", rental.world.a.location_id, False)


# R3a-02 -----------------------------------------------------------------------------


async def test_a_unit_is_assigned_for_the_booking_period(rental: Rental) -> None:
    away, _ = seed_other_branch(rental.owner_conn, rental.world.a)
    car, (unit, spare) = await units(rental, 2)
    _, (stranger,) = await units(rental, 1)
    elsewhere = uuid7()
    assert (await rental.unit(elsewhere, car, location_id=str(away))).status_code == 200
    customer = await party(rental, "FAKE Renter", ["customer"])
    booking = await booked(rental, car, customer, at(1), at(3))
    saved = await assign(rental, booking, unit)
    assert saved.status_code == 200, saved.text
    view = saved.json()
    assert (view["booking_id"], view["unit_id"], view["release"]) == (booking, str(unit), None)
    assert (view["starts_at"], view["ends_at"]) == ("2031-06-01T10:00:00Z", "2031-06-03T10:00:00Z")
    ((held_unit, state, during, own, reason),) = holds(rental, booking)
    assert (held_unit, state, own, reason) == (unit, "confirmed", True, None)
    assert (during.lower, during.upper) == (
        datetime(2031, 6, 1, 10, tzinfo=UTC),
        datetime(2031, 6, 3, 10, tzinfo=UTC),
    )
    # Another class, another branch, an unknown unit, a retired unit: refused.
    for wrong in (stranger, elsewhere, uuid7()):
        refused = await assign(rental, booking, wrong)
        assert error(refused) == (422, "INVALID_REFERENCE"), refused.text
    retired = await rental.unit(spare, car, revision=1, state="retired")
    assert retired.status_code == 200, retired.text
    assert error(await assign(rental, booking, spare)) == (422, "INVALID_REFERENCE")
    listed = await rental.get(f"/bookings/{booking}/assignments")
    assert [a["unit_id"] for a in listed.json()["items"]] == [str(unit)]


# R3a-03 -----------------------------------------------------------------------------


async def test_a_unit_is_never_issued_twice(rental: Rental) -> None:
    car, (unit, _) = await units(rental, 2)
    customer = await party(rental, "FAKE Renter", ["customer"])
    first = await booked(rental, car, customer, at(1), at(3))
    second = await booked(rental, car, customer, at(2), at(4))
    later = await booked(rental, car, customer, at(3), at(5))
    assert (await assign(rental, first, unit)).status_code == 200
    busy = await assign(rental, second, unit)
    assert error(busy) == (409, "RENTAL_UNIT_BUSY"), busy.text
    # Touching periods do not overlap.
    assert (await assign(rental, later, unit)).status_code == 200


async def test_two_racing_assignments_of_one_unit_leave_one(
    rental: Rental, app_pool: RuntimePool, test_database: ProvisionedDatabase
) -> None:
    car, (unit, _) = await units(rental, 2)
    customer = await party(rental, "FAKE Renter", ["customer"])
    first = await booked(rental, car, customer, at(1), at(3))
    second = await booked(rental, car, customer, at(2), at(4))
    answers = await race(
        app_pool,
        test_database,
        rental.tenant,
        "select 1 from gba.rental_units where id = %s for update",
        unit,
        [assign(rental, first, unit), assign(rental, second, unit)],
    )
    assert sorted(a.status_code for a in answers) == [200, 409], [a.text for a in answers]
    (refused,) = [a for a in answers if a.status_code == 409]
    assert error(refused) == (409, "RENTAL_UNIT_BUSY")


# R3a-04 -----------------------------------------------------------------------------


async def test_replacement_and_cancellation_release_the_unit(rental: Rental) -> None:
    car, (unit, spare) = await units(rental, 2)
    customer = await party(rental, "FAKE Renter", ["customer"])
    booking = await booked(rental, car, customer, at(1), at(3))
    other = await booked(rental, car, customer, at(2), at(4))
    assert (await assign(rental, booking, unit)).status_code == 200
    swapped = await assign(rental, booking, spare)
    assert swapped.status_code == 200, swapped.text
    assert [(h[0], h[1], h[4]) for h in holds(rental, booking)] == [
        (unit, "released", "replaced"),
        (spare, "confirmed", None),
    ]
    # The released unit is free again for an overlapping booking.
    assert (await assign(rental, other, unit)).status_code == 200
    cancel = await rental.client.post(
        f"{rental.base}/bookings/{booking}/cancellation",
        json={"schema_version": 1, "reason": "FAKE plans changed"},
        headers={**rental.headers, "Idempotency-Key": str(uuid7())},
    )
    assert cancel.status_code == 200, cancel.text
    assert [(h[0], h[1], h[4]) for h in holds(rental, booking)] == [
        (unit, "released", "replaced"),
        (spare, "released", "cancelled"),
    ]
    refused = await assign(rental, booking, unit)
    assert error(refused) == (409, "RENTAL_BOOKING_CANCELLED"), refused.text
    listed = await rental.get(f"/bookings/{booking}/assignments")
    assert [a["release"]["reason"] for a in listed.json()["items"]] == ["replaced", "cancelled"]


# R3a-05 -----------------------------------------------------------------------------


async def test_sql_keeps_assignments_and_their_holds_whole(
    rental: Rental, app_pool: RuntimePool
) -> None:
    car, (unit, _) = await units(rental, 2)
    customer = await party(rental, "FAKE Renter", ["customer"])
    booking = await booked(rental, car, customer, at(1), at(3))
    assert (await assign(rental, booking, unit)).status_code == 200
    tenant = rental.tenant
    for statement in (
        "update gba.rental_assignments set unit_id = unit_id",
        "delete from gba.rental_assignments",
        "update gba.rental_assignment_releases set reason = 'replaced'",
        "delete from gba.rental_assignment_releases",
    ):
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            async with tenant_transaction(app_pool, tenant) as conn:
                await conn.execute(statement)
    forged = (
        "insert into gba.resource_allocations "
        "(tenant_id, resource_id, source_kind, source_id, during, state) "
        "select %s, resource_id, %s, %s, tstzrange('2031-07-01', '2031-07-02', '[)'), "
        "'confirmed' from gba.rental_units where id = %s"
    )
    for kind in ("rental_assignment", "reservation"):
        with pytest.raises(psycopg.errors.CheckViolation):
            async with tenant_transaction(app_pool, tenant) as conn:
                await conn.execute(forged, (tenant, kind, uuid7(), unit))
    with pytest.raises(psycopg.errors.CheckViolation):
        async with tenant_transaction(app_pool, tenant) as conn:
            await conn.execute(
                "update gba.resource_allocations set state = 'released' "
                "where source_kind = 'rental_assignment'"
            )
    assert [h[1] for h in holds(rental, booking)] == ["confirmed"]


async def test_scope_module_and_another_company(
    rental: Rental,
    app_pool: RuntimePool,
    idp: FakeIdp,
    manager_a: FakeUser,
    manager_b: FakeUser,
) -> None:
    world = rental.world
    away, _ = seed_other_branch(rental.owner_conn, world.a)
    car, (unit,) = await units(rental, 1)
    customer = await party(rental, "FAKE Renter", ["customer"])
    booking = await booked(rental, car, customer, at(1), at(2))
    branch = rental.member("manager", away)
    hidden = await assign(rental, booking, unit, headers=branch)
    assert error(hidden) == (404, "NOT_FOUND"), hidden.text
    other = idp.bearer(manager_b.subject, email=manager_b.email)
    foreign = await assign(rental, booking, unit, headers=other)
    assert foreign.status_code in (403, 404), foreign.text
    await Config(rental.client, idp).publish(
        manager_a, rental.tenant, 1, ["booking_resources", "counterparties"]
    )
    off = await assign(rental, booking, unit)
    assert error(off) == (409, "MODULE_DISABLED"), off.text
    assert holds(rental, booking) == []
    async with tenant_transaction(app_pool, world.b.tenant_id) as conn:
        row = await (await conn.execute("select count(*) from gba.rental_assignments")).fetchone()
    assert row == (0,)
