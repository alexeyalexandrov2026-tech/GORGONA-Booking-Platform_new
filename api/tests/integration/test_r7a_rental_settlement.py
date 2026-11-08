"""R7a: the final settlement invoice of a rental agreement (FAKE data).

docs/plan/PACKAGE_R7A_DESIGN_2026-11-07.md: after the return, one FIN-03 receivable invoice draft
for the booking's customer with the rental total, the meter excess and the late return from frozen
terms; the database rechecks every figure and the document.
"""

from dataclasses import dataclass
from typing import Any
from uuid import UUID, uuid7

import httpx
import psycopg
import pytest

from gorgona_booking.db.pool import RuntimePool, tenant_transaction
from tests.integration.configuration_support import Config
from tests.integration.seed import FakeUser, seed_other_branch
from tests.integration.test_inventory import Inventory
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
from tests.integration.test_r2_rental_bookings import at, party
from tests.integration.test_r3a_rental_assignment import assign, booked, units
from tests.integration.test_r4a_rental_rates import card
from tests.integration.test_r4b_rental_agreements import accept
from tests.integration.test_r4c_rental_extensions import extend
from tests.integration.test_r6a_rental_inspections import inspect
from tests.integration.test_r6b_rental_usage import returned_at
from tests.integration.test_stock import entity_with_book
from tests.support.fake_idp import FakeIdp

pytestmark = pytest.mark.anyio
__all__ = ["accepted", "client", "idp", "manager_a", "manager_b", "rental"]
LATE = "2031-06-03T11:00:01+00:00"


@dataclass(frozen=True)
class Books:
    book: UUID
    chart: dict[str, UUID]


async def books(rental: Rental, app_pool: RuntimePool, idp: FakeIdp, user: FakeUser) -> Books:
    inventory = Inventory(rental.client, rental.world, idp, rental.owner_conn, user, rental.headers)
    _, book, chart = await entity_with_book(inventory, app_pool, "FAKE")
    return Books(book, chart)


async def rented(rental: Rental, rates: dict[str, int], **terms: Any) -> str:
    """A two-day USD booking (at(1) to at(3)) with an agreement and its unit assigned."""
    car, (unit,) = await units(rental, 1)
    home = rental.world.a.location_id
    made = await card(rental, car, home, rates, currency="USD", **terms)
    assert made.is_success, made.text
    customer = await party(rental, "FAKE Renter", ["customer"])
    booking = await booked(rental, car, customer, at(1), at(3))
    assert (await accept(rental, booking, [])).is_success
    assert (await assign(rental, booking, unit)).status_code == 200
    return booking


async def returned(rental: Rental, booking: str, out: int, back: int) -> None:
    assert (await inspect(rental, booking, "handover", meter=out)).status_code == 200
    assert (await inspect(rental, booking, "return", meter=back)).status_code == 200


def body(b: Books, **changes: Any) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "book_id": str(b.book),
        "receivable_account_id": str(b.chart["1200"]),
        "revenue_account_id": str(b.chart["4100"]),
        "invoice_date": "2031-06-04",
        "due_date": "2031-06-30",
        "number": f"FAKE-RS-{uuid7().hex[-8:]}",
        **changes,
    }


async def settle(
    rental: Rental,
    b: Books,
    booking: str,
    headers: dict[str, str] | None = None,
    key: str | None = None,
    **changes: Any,
) -> httpx.Response:
    return await rental.client.post(
        f"{rental.base}/bookings/{booking}/settlement",
        json=body(b, **changes),
        headers={**(headers or rental.headers), "Idempotency-Key": key or str(uuid7())},
    )


async def invoice(rental: Rental, b: Books, document: str) -> dict[str, Any]:
    found = await rental.client.get(
        f"/v1/businesses/{rental.tenant}/financial-documents/books/{b.book}/invoices/{document}",
        headers=rental.headers,
    )
    assert found.status_code == 200, found.text
    shown: dict[str, Any] = found.json()
    return shown


def figures(view: dict[str, Any]) -> tuple[Any, ...]:
    keys = ("currency", "rental_minor", "excess_minor", "late_minor", "late_units", "total_minor")
    return tuple(view[k] for k in keys)


# R7a-01 -----------------------------------------------------------------------------


async def test_a_returned_booking_settles_into_one_receivable_draft(
    rental: Rental, app_pool: RuntimePool, idp: FakeIdp, manager_a: FakeUser
) -> None:
    b = await books(rental, app_pool, idp, manager_a)
    booking = await rented(
        rental, {"day": 5_000, "hour": 300}, meter_allowance_per_day=100, excess_rate=25
    )
    await returned(rental, booking, 1_000, 1_300)
    returned_at(rental, booking, LATE)
    key = str(uuid7())
    sent = body(b)
    made = await rental.client.post(
        f"{rental.base}/bookings/{booking}/settlement",
        json=sent,
        headers={**rental.headers, "Idempotency-Key": key},
    )
    assert made.status_code == 200, made.text
    view = made.json()
    assert figures(view) == ("USD", 10_000, 2_500, 600, 2, 13_100)
    assert view["book_id"] == str(b.book)
    shown = await invoice(rental, b, view["invoice_document_id"])
    assert (shown["direction"], shown["total"], shown["currency"]) == (
        "receivable",
        "131.00",
        "USD",
    )
    assert [(x["counter_account_id"], x["amount"]) for x in shown["lines"]] == [
        (str(b.chart["4100"]), "100.00"),
        (str(b.chart["4100"]), "25.00"),
        (str(b.chart["4100"]), "6.00"),
    ]
    again = await rental.client.post(
        f"{rental.base}/bookings/{booking}/settlement",
        json=sent,
        headers={**rental.headers, "Idempotency-Key": key},
    )
    assert (again.status_code, again.json()) == (200, view)
    read = await rental.get(f"/bookings/{booking}/settlement")
    assert read.json() == view
    edited = await rental.client.put(
        f"/v1/businesses/{rental.tenant}/financial-documents/books/{b.book}/invoices/"
        f"{view['invoice_document_id']}",
        json={
            "schema_version": 1,
            "expected_revision": 1,
            "direction": "receivable",
            "counterparty_id": shown["counterparty_id"],
            "counterparty_revision": 1,
            "currency": "USD",
            "invoice_date": "2031-06-04",
            "control_account_id": str(b.chart["1200"]),
            "title": "FAKE edited here",
            "number": shown["number"],
            "lines": [
                {
                    "line_id": str(uuid7()),
                    "counter_account_id": str(b.chart["4100"]),
                    "description": "FAKE less",
                    "amount": "1.00",
                }
            ],
        },
        headers={**rental.headers, "Idempotency-Key": str(uuid7())},
    )
    assert error(edited) == (409, "FINANCIAL_DOCUMENT_LINKED"), edited.text


# R7a-02 -----------------------------------------------------------------------------


async def test_settlement_follows_the_booking(
    rental: Rental, app_pool: RuntimePool, idp: FakeIdp, manager_a: FakeUser
) -> None:
    b = await books(rental, app_pool, idp, manager_a)
    booking = await rented(rental, {"day": 5_000})
    early = await settle(rental, b, booking)
    assert error(early) == (409, "RENTAL_SETTLEMENT_STATE"), early.text
    assert (await inspect(rental, booking, "handover", meter=0)).status_code == 200
    out = await settle(rental, b, booking)
    assert error(out) == (409, "RENTAL_SETTLEMENT_STATE"), out.text
    assert (await inspect(rental, booking, "return", meter=10)).status_code == 200
    assert (await settle(rental, b, booking)).status_code == 200
    twice = await settle(rental, b, booking)
    assert error(twice) == (409, "RENTAL_SETTLEMENT_STATE"), twice.text
    weekly = await rented(rental, {"week": 30_000})
    await returned(rental, weekly, 0, 10)
    returned_at(rental, weekly, LATE)
    unpriced = await settle(rental, b, weekly)
    assert error(unpriced) == (409, "RENTAL_SETTLEMENT_UNPRICED"), unpriced.text
    car, (unit,) = await units(rental, 1)
    home = rental.world.a.location_id
    assert (await card(rental, car, home, {"day": 5_000}, currency="USD")).is_success
    customer = await party(rental, "FAKE Renter", ["customer"])
    plain = await booked(rental, car, customer, at(1), at(3))
    assert (await assign(rental, plain, unit)).status_code == 200
    unsigned = await settle(rental, b, plain)
    assert error(unsigned) == (409, "RENTAL_SETTLEMENT_STATE"), unsigned.text
    missing = await settle(rental, b, str(uuid7()))
    assert error(missing) == (404, "NOT_FOUND"), missing.text
    none = await rental.client.get(
        f"{rental.base}/bookings/{weekly}/settlement", headers=rental.headers
    )
    assert error(none) == (404, "NOT_FOUND"), none.text
    desk = rental.member("front_desk", rental.world.a.location_id)
    denied = await settle(rental, b, weekly, headers=desk)
    assert denied.status_code == 403, denied.text


# R7a-03 -----------------------------------------------------------------------------


async def test_day_rates_extensions_and_returns_on_time(
    rental: Rental, app_pool: RuntimePool, idp: FakeIdp, manager_a: FakeUser
) -> None:
    b = await books(rental, app_pool, idp, manager_a)
    daily = await rented(rental, {"day": 5_000}, meter_allowance_per_day=100, excess_rate=25)
    await returned(rental, daily, 0, 150)
    returned_at(rental, daily, LATE)
    late = (await settle(rental, b, daily)).json()
    assert figures(late) == ("USD", 10_000, 0, 5_000, 1, 15_000)
    on_time = await rented(rental, {"day": 5_000}, meter_allowance_per_day=100, excess_rate=25)
    await returned(rental, on_time, 0, 200)
    view = (await settle(rental, b, on_time)).json()
    assert figures(view) == ("USD", 10_000, 0, 0, 0, 10_000)
    shown = await invoice(rental, b, view["invoice_document_id"])
    assert [x["amount"] for x in shown["lines"]] == ["100.00"]
    longer = await rented(rental, {"day": 5_000})
    assert (await extend(rental, longer, at(1), at(4))).is_success
    await returned(rental, longer, 0, 10)
    returned_at(rental, longer, LATE)
    extended = (await settle(rental, b, longer)).json()
    assert figures(extended) == ("USD", 15_000, 0, 0, 0, 15_000)
    assert extended["agreement_version"] == 2


# R7a-04 -----------------------------------------------------------------------------


async def test_sql_keeps_settlements_whole(
    rental: Rental, app_pool: RuntimePool, idp: FakeIdp, manager_a: FakeUser
) -> None:
    b = await books(rental, app_pool, idp, manager_a)
    booking = await rented(rental, {"day": 5_000})
    await returned(rental, booking, 0, 10)
    assert (await settle(rental, b, booking)).status_code == 200
    tenant = rental.tenant
    for statement in (
        "update gba.rental_settlements set total_minor = total_minor + 1",
        "delete from gba.rental_settlements",
    ):
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            async with tenant_transaction(app_pool, tenant) as conn:
                await conn.execute(statement)
    other = await rented(rental, {"day": 5_000})
    await returned(rental, other, 0, 10)
    forged = (
        "insert into gba.rental_settlements (tenant_id, booking_id, agreement_version, "
        "rental_minor, excess_minor, late_minor, late_units, total_minor, book_id, "
        "invoice_document_id, settled_by) select tenant_id, %s, agreement_version, "
        "{rental}, excess_minor, late_minor, late_units, {total}, book_id, "
        "invoice_document_id, settled_by from gba.rental_settlements where booking_id = %s"
    )
    for rental_minor, total in ((10_000, 10_000), (9_000, 9_000)):
        with pytest.raises(psycopg.errors.CheckViolation):
            async with tenant_transaction(app_pool, tenant) as conn:
                await conn.execute(
                    forged.format(rental=rental_minor, total=total), (other, booking)
                )
    view = (await rental.get(f"/bookings/{booking}/settlement")).json()
    assert figures(view) == ("USD", 10_000, 0, 0, 0, 10_000)


async def test_scope_module_and_another_company(
    rental: Rental,
    app_pool: RuntimePool,
    idp: FakeIdp,
    manager_a: FakeUser,
    manager_b: FakeUser,
) -> None:
    b = await books(rental, app_pool, idp, manager_a)
    away, _ = seed_other_branch(rental.owner_conn, rental.world.a)
    booking = await rented(rental, {"day": 5_000})
    await returned(rental, booking, 0, 10)
    hidden = await settle(rental, b, booking, headers=rental.member("manager", away))
    assert error(hidden) == (404, "NOT_FOUND"), hidden.text
    other = idp.bearer(manager_b.subject, email=manager_b.email)
    foreign = await settle(rental, b, booking, headers=other)
    assert foreign.status_code in (403, 404), foreign.text
    await Config(rental.client, idp).publish(
        manager_a, rental.tenant, 1, ["booking_resources", "counterparties"]
    )
    off = await settle(rental, b, booking)
    assert error(off) == (409, "MODULE_DISABLED"), off.text
    count = "select count(*) from gba.rental_settlements"
    async with tenant_transaction(app_pool, rental.tenant) as conn:
        mine = await (await conn.execute(count)).fetchone()
    assert mine == (0,)
    async with tenant_transaction(app_pool, rental.world.b.tenant_id) as conn:
        row = await (await conn.execute(count)).fetchone()
    assert row == (0,)
