"""R4b: the rental agreement as the frozen accepted quote, and its change versions (FAKE data).

docs/plan/PACKAGE_R4B_DESIGN_2026-11-06.md: version 1 freezes the quote of the card in force at the
booking with the chosen extras, the source, who accepted and when; a change is the next version
with a reason over the same card and period.
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
from tests.integration.test_r4a_rental_rates import DRIVER, SEAT, card
from tests.support.fake_idp import FakeIdp

pytestmark = pytest.mark.anyio
__all__ = ["accepted", "client", "idp", "manager_a", "manager_b", "rental"]

SIGNED = "2026-11-01T09:00:00+00:00"


async def accept(
    rental: Rental,
    booking: str,
    extras: list[dict[str, Any]],
    headers: dict[str, str] | None = None,
    **fields: Any,
) -> httpx.Response:
    return await rental.client.post(
        f"{rental.base}/bookings/{booking}/agreement",
        json={
            "schema_version": 1,
            "source": "paper",
            "accepted_by": "FAKE Renter",
            "accepted_at": SIGNED,
            "extras": extras,
            **fields,
        },
        headers={**(headers or rental.headers), "Idempotency-Key": str(uuid7())},
    )


async def change(
    rental: Rental, booking: str, extras: list[dict[str, Any]], **fields: Any
) -> httpx.Response:
    return await rental.client.post(
        f"{rental.base}/bookings/{booking}/agreement/versions",
        json={
            "schema_version": 1,
            "reason": "FAKE second seat",
            "source": "email",
            "accepted_by": "FAKE Renter",
            "accepted_at": SIGNED,
            "extras": extras,
            **fields,
        },
        headers={**rental.headers, "Idempotency-Key": str(uuid7())},
    )


async def priced_booking(rental: Rental) -> tuple[UUID, str]:
    home = rental.world.a.location_id
    car = await fleet(rental, 1)
    assert (await card(rental, car, home, {"day": 5_000}, [SEAT, DRIVER])).is_success
    customer = await party(rental, "FAKE Renter", ["customer"])
    return car, await booked(rental, car, customer, at(1), at(3))


# R4b-01 -----------------------------------------------------------------------------


async def test_accepting_freezes_the_quote_with_who_and_how(rental: Rental) -> None:
    car, booking = await priced_booking(rental)
    assert (await card(rental, car, rental.world.a.location_id, {"day": 9_000})).is_success
    one = [{"code": "child_seat", "quantity": 1}, {"code": "driver", "quantity": 1}]
    saved = await accept(rental, booking, one)
    assert saved.status_code == 200, saved.text
    body = saved.json()
    assert (body["booking_id"], body["current_version"]) == (booking, 1)
    first = body["versions"][0]
    assert (first["version"], first["card_version"], first["currency"]) == (1, 1, "EUR")
    assert (first["rental"], first["rental_days"], first["total"]) == (10_000, 2, 13_400)
    assert first["counts"] == {"month": 0, "week": 0, "day": 2, "hour": 0}
    assert [(e["code"], e["price"], e["quantity"], e["amount"]) for e in first["extras"]] == [
        ("child_seat", 700, 1, 1_400),
        ("driver", 2_000, 1, 2_000),
    ]
    who = (first["source"], first["accepted_by"], first["reason"])
    assert who == ("paper", "FAKE Renter", None)
    assert first["accepted_at"] == "2026-11-01T09:00:00Z"
    read = await rental.get(f"/bookings/{booking}/agreement")
    assert read.status_code == 200, read.text
    assert read.json() == body


# R4b-02 -----------------------------------------------------------------------------


async def test_a_change_is_a_new_version_over_the_same_card_and_period(rental: Rental) -> None:
    _, booking = await priced_booking(rental)
    assert (await accept(rental, booking, [{"code": "child_seat", "quantity": 1}])).is_success
    changed = await change(rental, booking, [{"code": "child_seat", "quantity": 2}])
    assert changed.status_code == 200, changed.text
    body = changed.json()
    assert body["current_version"] == 2
    first, second = body["versions"]
    assert (first["version"], first["total"]) == (1, 11_400)
    assert (second["version"], second["total"], second["reason"]) == (2, 12_800, "FAKE second seat")
    assert second["rate_card_id"] == first["rate_card_id"]
    assert (second["starts_at"], second["ends_at"]) == (first["starts_at"], first["ends_at"])
    assert (second["source"], second["card_version"]) == ("email", 1)


# R4b-03 -----------------------------------------------------------------------------


async def test_refusals(rental: Rental) -> None:
    car, booking = await priced_booking(rental)
    assert error(await change(rental, booking, [])) == (404, "NOT_FOUND")
    assert (await accept(rental, booking, [])).is_success
    assert error(await accept(rental, booking, [])) == (409, "RENTAL_AGREEMENT_EXISTS")
    for refused in (
        await change(rental, booking, [{"code": "fuel", "quantity": 1}]),
        await change(rental, booking, [], accepted_at="2099-01-01T00:00:00+00:00"),
        await change(rental, booking, [], reason=" "),
        await change(rental, booking, [], source="phone"),
    ):
        assert refused.status_code == 422, refused.text
    customer = await party(rental, "FAKE Renter", ["customer"])
    gone = await booked(rental, car, customer, at(5), at(6))
    cancelled = await rental.client.post(
        f"{rental.base}/bookings/{gone}/cancellation",
        json={"schema_version": 1, "reason": "FAKE plans changed"},
        headers={**rental.headers, "Idempotency-Key": str(uuid7())},
    )
    assert cancelled.status_code == 200, cancelled.text
    assert error(await accept(rental, gone, [])) == (409, "RENTAL_BOOKING_CANCELLED")
    bare = await fleet(rental, 1)
    unpriced = await booked(rental, bare, customer, at(5), at(6))
    assert error(await accept(rental, unpriced, [])) == (409, "RENTAL_NO_RATE")


# R4b-04 -----------------------------------------------------------------------------


async def test_sql_keeps_agreements_whole(rental: Rental, app_pool: RuntimePool) -> None:
    car, booking = await priced_booking(rental)
    assert (await accept(rental, booking, [{"code": "child_seat", "quantity": 1}])).is_success
    assert (await card(rental, car, rental.world.a.location_id, {"day": 9_000})).is_success
    tenant = rental.tenant
    for statement in (
        "update gba.rental_agreements set created_at = now()",
        "delete from gba.rental_agreements",
        "update gba.rental_agreement_versions set total = 1",
        "delete from gba.rental_agreement_versions",
        "update gba.rental_agreement_version_extras set amount = 1",
        "delete from gba.rental_agreement_version_extras",
    ):
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            async with tenant_transaction(app_pool, tenant) as conn:
                await conn.execute(statement)
    forged = (
        "insert into gba.rental_agreement_versions (tenant_id, agreement_id, version, "
        "rate_card_id, starts_at, ends_at, month_count, week_count, day_count, hour_count, "
        "rental_amount, rental_days, total, source, accepted_by, accepted_at, reason, "
        "recorded_by) select v.tenant_id, v.agreement_id, {version}, {card}, v.starts_at, "
        "{ends}, v.month_count, v.week_count, v.day_count, v.hour_count, v.rental_amount, "
        "v.rental_days, {total}, v.source, v.accepted_by, v.accepted_at, 'FAKE', v.recorded_by "
        "from gba.rental_agreement_versions v join gba.rental_agreements a "
        "on a.tenant_id = v.tenant_id and a.id = v.agreement_id where a.booking_id = %s"
    )
    newer = "(select r.id from gba.rental_rate_cards r where r.class_id = %s and r.version = 2)"
    for version, card_id, ends, total in (
        ("5", "v.rate_card_id", "v.ends_at", "v.rental_amount"),
        ("2", "v.rate_card_id", "v.ends_at", "v.rental_amount + 1"),
        ("2", "v.rate_card_id", "v.ends_at + interval '1 day'", "v.rental_amount"),
        ("2", newer, "v.ends_at", "v.rental_amount"),
    ):
        statement = forged.format(version=version, card=card_id, ends=ends, total=total)
        arguments = (car, booking) if card_id == newer else (booking,)
        with pytest.raises(psycopg.errors.CheckViolation):
            async with tenant_transaction(app_pool, tenant) as conn:
                await conn.execute(statement, arguments)
    late = (
        "insert into gba.rental_agreement_version_extras (tenant_id, agreement_id, version, "
        "code, name, price, unit, quantity, amount) select tenant_id, agreement_id, version, "
        "'driver', 'FAKE driver', 2000, 'per_rental', 1, 2000 "
        "from gba.rental_agreement_versions"
    )
    with pytest.raises(psycopg.errors.CheckViolation):
        async with tenant_transaction(app_pool, tenant) as conn:
            await conn.execute(late)
    read = await rental.get(f"/bookings/{booking}/agreement")
    assert [(v["version"], v["total"]) for v in read.json()["versions"]] == [(1, 11_400)]


async def test_scope_module_and_another_company(
    rental: Rental,
    app_pool: RuntimePool,
    idp: FakeIdp,
    manager_a: FakeUser,
    manager_b: FakeUser,
) -> None:
    away, _ = seed_other_branch(rental.owner_conn, rental.world.a)
    _, booking = await priced_booking(rental)
    branch = rental.member("manager", away)
    hidden = await accept(rental, booking, [], headers=branch)
    assert error(hidden) == (404, "NOT_FOUND"), hidden.text
    other = idp.bearer(manager_b.subject, email=manager_b.email)
    foreign = await accept(rental, booking, [], headers=other)
    assert foreign.status_code in (403, 404), foreign.text
    await Config(rental.client, idp).publish(
        manager_a, rental.tenant, 1, ["booking_resources", "counterparties"]
    )
    off = await accept(rental, booking, [])
    assert error(off) == (409, "MODULE_DISABLED"), off.text
    async with tenant_transaction(app_pool, rental.tenant) as conn:
        mine = await (await conn.execute("select count(*) from gba.rental_agreements")).fetchone()
    assert mine == (0,)
    async with tenant_transaction(app_pool, rental.world.b.tenant_id) as conn:
        row = await (await conn.execute("select count(*) from gba.rental_agreements")).fetchone()
    assert row == (0,)
