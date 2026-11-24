"""R4a: rental rate cards and quotes (package R; FAKE data).

docs/plan/PACKAGE_R4A_DESIGN_2026-11-04.md: rate cards are insert-only versions per class and
branch; the quote is the cheapest cover by the card's units plus extras; a booking is quoted from
the card in force when it was made.
"""

from typing import Any
from uuid import UUID, uuid7

import httpx
import psycopg
import pytest

from gorgona_booking.db.pool import RuntimePool, tenant_transaction
from tests.integration.configuration_support import Config
from tests.integration.seed import FakeUser, seed_other_branch
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
from tests.integration.test_r2_rental_bookings import at, fleet, party
from tests.integration.test_r3a_rental_assignment import booked
from tests.support.fake_idp import FakeIdp

pytestmark = pytest.mark.anyio
__all__ = ["accepted", "client", "idp", "manager_a", "manager_b", "rental"]

SEAT = {"code": "child_seat", "name": "FAKE seat", "price": 700, "unit": "per_day"}
DRIVER = {"code": "driver", "name": "FAKE driver", "price": 2_000, "unit": "per_rental"}


async def card(
    rental: Rental,
    car: UUID,
    location: UUID,
    rates: dict[str, int],
    extras: list[dict[str, Any]] | None = None,
    headers: dict[str, str] | None = None,
    **fields: Any,
) -> httpx.Response:
    return await rental.client.post(
        f"{rental.base}/classes/{car}/rate-cards",
        json={
            "schema_version": 1,
            "location_id": str(location),
            "currency": "EUR",
            "rates": rates,
            "extras": extras or [],
            **fields,
        },
        headers={**(headers or rental.headers), "Idempotency-Key": str(uuid7())},
    )


async def priced(
    rental: Rental,
    car: UUID,
    location: UUID,
    starts: str,
    ends: str,
    extras: list[dict[str, Any]] | None = None,
) -> httpx.Response:
    return await rental.client.post(
        f"{rental.base}/quotes",
        json={
            "schema_version": 1,
            "class_id": str(car),
            "location_id": str(location),
            "starts_at": starts,
            "ends_at": ends,
            "extras": extras or [],
        },
        headers=rental.headers,
    )


async def klass(rental: Rental) -> UUID:
    car = uuid7()
    assert (await rental.klass(car)).status_code == 200
    return car


# R4a-01 -----------------------------------------------------------------------------


async def test_rate_cards_are_versions_per_class_and_branch(rental: Rental) -> None:
    away, _ = seed_other_branch(rental.owner_conn, rental.world.a)
    home = rental.world.a.location_id
    car = await klass(rental)
    first = await card(rental, car, home, {"day": 5_000, "week": 30_000}, [SEAT])
    assert first.status_code == 200, first.text
    view = first.json()
    assert (view["version"], view["currency"], view["location_id"]) == (1, "EUR", str(home))
    assert view["rates"] == {"hour": None, "day": 5_000, "week": 30_000, "month": None}
    assert [e["code"] for e in view["extras"]] == ["child_seat"]
    second = await card(rental, car, home, {"day": 6_000})
    assert second.json()["version"] == 2, second.text
    there = await card(rental, car, away, {"day": 4_000})
    assert there.json()["version"] == 1, there.text
    listed = await rental.get(f"/classes/{car}/rate-cards?location_id={home}")
    assert [c["version"] for c in listed.json()["items"]] == [1, 2], listed.text
    cases: tuple[tuple[dict[str, int], dict[str, Any]], ...] = (
        ({"day": 5_000}, {"effective_from": "2020-01-01T00:00:00+00:00"}),
        ({}, {}),
        ({"day": 0}, {}),
        ({"day": 5_000}, {"currency": "eur"}),
    )
    for rates, fields in cases:
        refused = await card(rental, car, home, rates, **fields)
        assert refused.status_code == 422, refused.text
    twice = await card(rental, car, home, {"day": 5_000}, [SEAT, SEAT])
    assert twice.status_code == 422, twice.text
    assert error(await card(rental, uuid7(), home, {"day": 1})) == (404, "NOT_FOUND")
    assert error(await card(rental, car, uuid7(), {"day": 1})) == (404, "NOT_FOUND")


# R4a-02 -----------------------------------------------------------------------------


async def test_a_quote_is_the_cheapest_cover_plus_extras(rental: Rental) -> None:
    home = rental.world.a.location_id
    car = await klass(rental)
    rates = {"day": 5_000, "week": 30_000}
    assert (await card(rental, car, home, rates, [SEAT, DRIVER])).is_success
    later: dict[str, Any] = {"effective_from": "2030-01-01T00:00:00+00:00"}
    assert (await card(rental, car, home, {"day": 50_000}, **later)).is_success
    extras = [{"code": "child_seat", "quantity": 2}, {"code": "driver", "quantity": 1}]
    quoted = await priced(rental, car, home, at(1), at(9), extras)
    assert quoted.status_code == 200, quoted.text
    body = quoted.json()
    assert (body["version"], body["currency"], body["rental"]) == (1, "EUR", 35_000)
    assert body["counts"] == {"month": 0, "week": 1, "day": 1, "hour": 0}
    assert body["rental_days"] == 8
    assert body["extras"] == [
        {"code": "child_seat", "quantity": 2, "amount": 11_200},
        {"code": "driver", "quantity": 1, "amount": 2_000},
    ]
    assert body["total"] == 35_000 + 11_200 + 2_000
    unknown = await priced(rental, car, home, at(1), at(2), [{"code": "fuel", "quantity": 1}])
    assert unknown.status_code == 422, unknown.text
    bare = await klass(rental)
    assert error(await priced(rental, bare, home, at(1), at(2))) == (409, "RENTAL_NO_RATE")


# R4a-03 -----------------------------------------------------------------------------


async def test_a_booking_is_quoted_from_the_card_in_force_when_it_was_made(rental: Rental) -> None:
    home = rental.world.a.location_id
    car = await fleet(rental, 1)
    customer = await party(rental, "FAKE Renter", ["customer"])
    unpriced = await booked(rental, car, customer, at(20), at(21))
    assert (await card(rental, car, home, {"day": 5_000})).is_success
    early = await booked(rental, car, customer, at(1), at(3))
    assert (await card(rental, car, home, {"day": 9_000})).is_success
    late = await booked(rental, car, customer, at(5), at(6))
    first = await rental.get(f"/bookings/{early}/quote")
    assert first.status_code == 200, first.text
    view = first.json()
    assert (view["booking_id"], view["version"], view["total"]) == (early, 1, 10_000)
    second = await rental.get(f"/bookings/{late}/quote")
    assert (second.json()["version"], second.json()["total"]) == (2, 9_000), second.text
    assert error(await rental.get(f"/bookings/{unpriced}/quote")) == (409, "RENTAL_NO_RATE")


# R4a-04 -----------------------------------------------------------------------------


async def test_sql_keeps_rate_cards_whole(rental: Rental, app_pool: RuntimePool) -> None:
    home = rental.world.a.location_id
    car = await klass(rental)
    assert (await card(rental, car, home, {"day": 5_000}, [SEAT])).is_success
    tenant = rental.tenant
    for statement in (
        "update gba.rental_rate_cards set day_rate = 1",
        "delete from gba.rental_rate_cards",
        "update gba.rental_rate_card_extras set price = 1",
        "delete from gba.rental_rate_card_extras",
    ):
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            async with tenant_transaction(app_pool, tenant) as conn:
                await conn.execute(statement)
    forged = (
        "insert into gba.rental_rate_cards (tenant_id, id, class_id, location_id, version, "
        "currency, effective_from, day_rate, created_by) select tenant_id, %s, class_id, "
        "location_id, {version}, currency, {effective}, 1, created_by from gba.rental_rate_cards "
        "where class_id = %s"
    )
    for version, effective in (("5", "now()"), ("2", "timestamptz '2020-01-01'")):
        statement = forged.format(version=version, effective=effective)
        with pytest.raises(psycopg.errors.CheckViolation):
            async with tenant_transaction(app_pool, tenant) as conn:
                await conn.execute(statement, (uuid7(), car))
    with pytest.raises(psycopg.errors.CheckViolation):
        async with tenant_transaction(app_pool, tenant) as conn:
            await conn.execute(
                "insert into gba.rental_rate_card_extras (tenant_id, card_id, code, name, price, "
                "unit) select tenant_id, id, 'late', 'FAKE', 1, 'per_rental' "
                "from gba.rental_rate_cards "
                "where class_id = %s",
                (car,),
            )
    listed = await rental.get(f"/classes/{car}/rate-cards?location_id={home}")
    assert [(c["version"], len(c["extras"])) for c in listed.json()["items"]] == [(1, 1)]


async def test_scope_module_and_another_company(
    rental: Rental,
    app_pool: RuntimePool,
    idp: FakeIdp,
    manager_a: FakeUser,
    manager_b: FakeUser,
) -> None:
    away, _ = seed_other_branch(rental.owner_conn, rental.world.a)
    home = rental.world.a.location_id
    car = await klass(rental)
    branch = rental.member("manager", away)
    hidden = await card(rental, car, home, {"day": 1}, headers=branch)
    assert error(hidden) == (404, "NOT_FOUND"), hidden.text
    other = idp.bearer(manager_b.subject, email=manager_b.email)
    foreign = await card(rental, car, home, {"day": 1}, headers=other)
    assert foreign.status_code in (403, 404), foreign.text
    await Config(rental.client, idp).publish(
        manager_a, rental.tenant, 1, ["booking_resources", "counterparties"]
    )
    off = await card(rental, car, home, {"day": 1})
    assert error(off) == (409, "MODULE_DISABLED"), off.text
    async with tenant_transaction(app_pool, rental.tenant) as conn:
        mine = await (await conn.execute("select count(*) from gba.rental_rate_cards")).fetchone()
    assert mine == (0,)
    async with tenant_transaction(app_pool, rental.world.b.tenant_id) as conn:
        row = await (await conn.execute("select count(*) from gba.rental_rate_cards")).fetchone()
    assert row == (0,)
