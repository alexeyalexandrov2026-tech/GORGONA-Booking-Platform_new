"""R2: rental class bookings and availability (package R, RENT-01; FAKE data only).

docs/plan/PACKAGE_R2_DESIGN_2026-11-03.md: a booking holds a class, never a unit; it is accepted
only while the units of the class at the pickup branch cover the peak of overlapping bookings.
"""

from typing import Any
from uuid import UUID, uuid7

import httpx
import psycopg
import pytest

from gorgona_booking.db.pool import RuntimePool, tenant_transaction
from tests.integration.configuration_support import Config
from tests.integration.conftest import ProvisionedDatabase
from tests.integration.seed import FakeUser, seed_other_branch
from tests.integration.test_counterparties import card
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
from tests.support.fake_idp import FakeIdp

pytestmark = pytest.mark.anyio
__all__ = ["accepted", "client", "idp", "manager_a", "manager_b", "rental"]


def at(day: int, hour: int = 10) -> str:
    return f"2031-06-{day:02d}T{hour:02d}:00:00+00:00"


def query(car: UUID, location: UUID, starts: str, ends: str) -> str:
    return (
        f"/availability?class_id={car}&location_id={location}"
        f"&starts_at={starts.replace('+', '%2B')}&ends_at={ends.replace('+', '%2B')}"
    )


async def party(rental: Rental, name: str, roles: list[str]) -> UUID:
    party_id = uuid7()
    saved = await rental.client.put(
        f"/v1/businesses/{rental.tenant}/counterparties/{party_id}",
        json=card(display_name=name, roles=roles),
        headers={**rental.headers, "Idempotency-Key": str(uuid7())},
    )
    assert saved.status_code == 200, saved.text
    return party_id


async def fleet(rental: Rental, units: int, location: UUID | None = None) -> UUID:
    car = uuid7()
    assert (await rental.klass(car)).status_code == 200
    for _ in range(units):
        unit = await rental.unit(
            uuid7(), car, location_id=str(location or rental.world.a.location_id)
        )
        assert unit.status_code == 200, unit.text
    return car


async def book(
    rental: Rental,
    car: UUID,
    customer: UUID,
    starts: str,
    ends: str,
    headers: dict[str, str] | None = None,
    key: str | None = None,
    **changes: Any,
) -> httpx.Response:
    home = str(rental.world.a.location_id)
    body = {
        "schema_version": 1,
        "class_id": str(car),
        "customer_id": str(customer),
        "pickup_location_id": home,
        "return_location_id": home,
        "starts_at": starts,
        "ends_at": ends,
        "note": "FAKE booking",
        **changes,
    }
    return await rental.client.post(
        f"{rental.base}/bookings",
        json=body,
        headers={**(headers or rental.headers), "Idempotency-Key": key or str(uuid7())},
    )


async def _counts(pool: RuntimePool, tenant: UUID) -> tuple[int, ...]:
    async with tenant_transaction(pool, tenant) as conn:
        row = await (
            await conn.execute(
                "select (select count(*) from gba.rental_bookings), "
                "(select count(*) from gba.rental_booking_cancellations)"
            )
        ).fetchone()
    assert row is not None
    return tuple(int(n) for n in row)


# R2-01 ------------------------------------------------------------------------------


async def test_a_booking_holds_a_class_with_its_references(rental: Rental) -> None:
    car = await fleet(rental, 1)
    customer = await party(rental, "FAKE Renter", ["customer"])
    supplier = await party(rental, "FAKE Garage", ["supplier"])
    saved = await book(rental, car, customer, at(1), at(3))
    assert saved.status_code == 200, saved.text
    view = saved.json()
    assert (view["number"], view["class_id"], view["customer_id"]) == (1, str(car), str(customer))
    assert (view["starts_at"], view["ends_at"]) == ("2031-06-01T10:00:00Z", "2031-06-03T10:00:00Z")
    assert view["cancellation"] is None
    assert "unit_id" not in view
    read = await rental.get(f"/bookings/{view['booking_id']}")
    assert read.json() == view
    bad_periods: list[dict[str, Any]] = [
        {"ends_at": at(4)},
        {"ends_at": "2032-07-03T10:00:00+00:00"},
    ]
    for changes in bad_periods:
        refused = await book(rental, car, customer, at(4), at(5), **changes)
        assert refused.status_code == 422, (changes, refused.text)
    assert error(await book(rental, uuid7(), customer, at(4), at(5))) == (
        422,
        "INVALID_REFERENCE",
    )
    assert error(await book(rental, car, supplier, at(4), at(5))) == (422, "INVALID_REFERENCE")
    assert error(await book(rental, car, uuid7(), at(4), at(5))) == (422, "INVALID_REFERENCE")
    unknown = await book(rental, car, customer, at(4), at(5), return_location_id=str(uuid7()))
    assert error(unknown) == (422, "INVALID_REFERENCE")
    second = await book(rental, car, customer, at(4), at(5))
    assert (second.status_code, second.json()["number"]) == (200, 2), second.text


async def test_a_booking_replays_by_its_key(rental: Rental) -> None:
    car = await fleet(rental, 1)
    customer = await party(rental, "FAKE Renter", ["customer"])
    key = str(uuid7())
    first = await book(rental, car, customer, at(1), at(2), key=key)
    again = await book(rental, car, customer, at(1), at(2), key=key)
    assert (first.status_code, again.status_code) == (200, 200), again.text
    assert again.json() == first.json()
    other = await book(rental, car, customer, at(1), at(3), key=key)
    assert error(other) == (422, "IDEMPOTENCY_KEY_REUSED")


# R2-02 and R2-03 --------------------------------------------------------------------


async def test_availability_is_units_minus_the_peak_of_overlaps(rental: Rental) -> None:
    away, _ = seed_other_branch(rental.owner_conn, rental.world.a)
    car = await fleet(rental, 2)
    # A unit at another branch does not count here.
    assert (await rental.unit(uuid7(), car, location_id=str(away))).status_code == 200
    customer = await party(rental, "FAKE Renter", ["customer"])
    first = await book(rental, car, customer, at(1), at(3))
    assert first.status_code == 200, first.text
    assert (await book(rental, car, customer, at(2), at(4))).status_code == 200
    third = await book(rental, car, customer, at(2, 12), at(2, 13))
    assert error(third) == (409, "RENTAL_UNAVAILABLE"), third.text
    # Touching periods do not overlap: [3, 4) meets only the second booking.
    assert (await book(rental, car, customer, at(3), at(4))).status_code == 200
    assert error(await book(rental, car, customer, at(3, 12), at(3, 13))) == (
        409,
        "RENTAL_UNAVAILABLE",
    )
    home = rental.world.a.location_id
    busy = await rental.get(query(car, home, at(1), at(5)))
    assert busy.status_code == 200, busy.text
    assert (busy.json()["units"], busy.json()["booked"], busy.json()["available"]) == (2, 2, 0)
    free = await rental.get(query(car, home, at(5), at(6)))
    assert (free.json()["units"], free.json()["booked"], free.json()["available"]) == (2, 0, 2)
    # A cancellation frees the class, once.
    path = f"{rental.base}/bookings/{first.json()['booking_id']}/cancellation"
    cancel = {"schema_version": 1, "reason": "FAKE plans changed"}
    cancelled = await rental.client.post(
        path, json=cancel, headers={**rental.headers, "Idempotency-Key": str(uuid7())}
    )
    assert cancelled.status_code == 200, cancelled.text
    assert cancelled.json()["cancellation"]["reason"] == "FAKE plans changed"
    again = await rental.client.post(
        path, json=cancel, headers={**rental.headers, "Idempotency-Key": str(uuid7())}
    )
    assert error(again) == (409, "RENTAL_BOOKING_CANCELLED")
    assert (await book(rental, car, customer, at(2, 12), at(2, 13))).status_code == 200
    listed = await rental.get(f"/bookings?class_id={car}")
    assert [b["number"] for b in listed.json()["items"]] == [1, 2, 3, 4]


# R2-04 ------------------------------------------------------------------------------


async def test_two_racing_bookings_for_the_last_unit_leave_one(
    rental: Rental, app_pool: RuntimePool, test_database: ProvisionedDatabase
) -> None:
    car = await fleet(rental, 1)
    customer = await party(rental, "FAKE Renter", ["customer"])
    answers = await race(
        app_pool,
        test_database,
        rental.tenant,
        "select 1 from gba.rental_classes where id = %s for update",
        car,
        [
            book(rental, car, customer, at(1), at(3)),
            book(rental, car, customer, at(2), at(4)),
        ],
    )
    assert sorted(a.status_code for a in answers) == [200, 409], [a.text for a in answers]
    (refused,) = [a for a in answers if a.status_code == 409]
    assert error(refused) == (409, "RENTAL_UNAVAILABLE")
    assert await _counts(app_pool, rental.tenant) == (1, 0)


# R2-05 ------------------------------------------------------------------------------


async def test_sql_keeps_bookings_whole(rental: Rental, app_pool: RuntimePool) -> None:
    car = await fleet(rental, 1)
    customer = await party(rental, "FAKE Renter", ["customer"])
    saved = await book(rental, car, customer, at(1), at(3))
    assert saved.status_code == 200, saved.text
    tenant = rental.tenant
    for statement in (
        "update gba.rental_bookings set ends_at = ends_at",
        "delete from gba.rental_bookings",
        "update gba.rental_booking_cancellations set reason = 'FAKE'",
        "delete from gba.rental_booking_cancellations",
    ):
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            async with tenant_transaction(app_pool, tenant) as conn:
                await conn.execute(statement)
    home = rental.world.a.location_id
    with pytest.raises(psycopg.errors.CheckViolation):
        async with tenant_transaction(app_pool, tenant) as conn:
            await conn.execute(
                "insert into gba.rental_bookings (tenant_id, id, number, class_id, customer_id, "
                "pickup_location_id, return_location_id, starts_at, ends_at, booked_by) "
                "select %s, %s, 2, %s, %s, %s, %s, %s, %s, booked_by "
                "from gba.rental_bookings limit 1",
                (tenant, uuid7(), car, customer, home, home, at(2), at(4)),
            )
    assert await _counts(app_pool, tenant) == (1, 0)


async def test_scope_module_and_another_company(
    rental: Rental,
    app_pool: RuntimePool,
    idp: FakeIdp,
    manager_a: FakeUser,
    manager_b: FakeUser,
) -> None:
    world = rental.world
    home = world.a.location_id
    away, _ = seed_other_branch(rental.owner_conn, world.a)
    car = await fleet(rental, 1)
    assert (await rental.unit(uuid7(), car, location_id=str(away))).status_code == 200
    customer = await party(rental, "FAKE Renter", ["customer"])
    here = await book(rental, car, customer, at(1), at(2))
    elsewhere: dict[str, Any] = {"pickup_location_id": str(away), "return_location_id": str(away)}
    there = await book(rental, car, customer, at(1), at(2), **elsewhere)
    assert (here.status_code, there.status_code) == (200, 200), there.text
    branch = rental.member("manager", home)
    seen = await rental.get("/bookings", headers=branch)
    assert [b["booking_id"] for b in seen.json()["items"]] == [here.json()["booking_id"]]
    hidden = await rental.get(f"/bookings/{there.json()['booking_id']}", headers=branch)
    assert error(hidden) == (404, "NOT_FOUND")
    outside = await book(rental, car, customer, at(3), at(4), headers=branch, **elsewhere)
    assert error(outside) == (422, "INVALID_REFERENCE"), outside.text
    other = idp.bearer(manager_b.subject, email=manager_b.email)
    foreign = await rental.get("/bookings", headers=other)
    assert foreign.status_code in (403, 404), foreign.text
    assert await _counts(app_pool, world.b.tenant_id) == (0, 0)
    tenant = rental.tenant
    before = await _counts(app_pool, tenant)
    await Config(rental.client, idp).publish(
        manager_a, tenant, 1, ["booking_resources", "counterparties"]
    )
    off = await book(rental, car, customer, at(5), at(6))
    assert error(off) == (409, "MODULE_DISABLED"), off.text
    assert await _counts(app_pool, tenant) == before
    read = await rental.get(f"/bookings/{here.json()['booking_id']}")
    assert read.status_code == 200, read.text
