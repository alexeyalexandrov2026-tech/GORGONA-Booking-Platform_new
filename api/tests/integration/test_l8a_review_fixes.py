"""L8a: fixes of the package L review findings R1-R7 (BEAUTY-01; FAKE data only).

Design docs/plan/PACKAGE_L8_DESIGN_2026-10-23.md decisions 54-60; findings in
docs/plan/evidence/2026-10-23-l8-review/REVIEW.md.
"""

from uuid import UUID, uuid7

import psycopg
import pytest

from gorgona_booking.booking.service import BookingService
from gorgona_booking.db.pool import RuntimePool, tenant_transaction
from gorgona_booking.db.provisioning import owner_tenant_transaction
from tests.integration import test_l6_prepaid as shared
from tests.integration.booking_support import BookingWorld, at
from tests.integration.test_external_payments import PaymentWorld
from tests.integration.test_l4_billing import bill, fee, post, visit
from tests.integration.test_l5_commissions import Kit, accrue, commission_body, put_plan
from tests.integration.test_l6_prepaid import billed_visit, code, pay, redeem, salon, sell

pytestmark = pytest.mark.anyio
client = shared.client
idp = shared.idp
manager_a = shared.manager_a
manager_b = shared.manager_b
enabled = shared.enabled
invoices = shared.invoices
payments = shared.payments
kit = shared.kit
__all__ = ["client", "enabled", "idp", "invoices", "kit", "manager_a", "manager_b", "payments"]


def seed_variant(
    conn: psycopg.Connection, world: BookingWorld, code_: str, currency: str, price_cents: int
) -> UUID:
    """A published 30-minute variant of the FAKE service in another currency."""
    with owner_tenant_transaction(conn, world.a.tenant_id):
        row = conn.execute(
            "insert into gba.service_variants (tenant_id, service_id, code, name, status, "
            "price_cents, currency, booking_duration_minutes, is_bookable) "
            "select tenant_id, service_id, %s, %s, 'published', %s, %s, 30, true "
            "from gba.service_variants where id = %s returning id",
            (code_, f"FAKE {code_}", price_cents, currency, world.catalog_a.base_variant_id),
        ).fetchone()
    assert row is not None
    return UUID(str(row[0]))


def seed_free_add_on(conn: psycopg.Connection, world: BookingWorld) -> UUID:
    with owner_tenant_transaction(conn, world.a.tenant_id):
        row = conn.execute(
            "insert into gba.add_ons (tenant_id, code, name, status, price_cents, currency, "
            "duration_delta_minutes, is_bookable) "
            "values (%s, 'FAKE_FREE', 'FAKE FAKE_FREE', 'published', 0, 'USD', 5, true) "
            "returning id",
            (world.a.tenant_id,),
        ).fetchone()
    assert row is not None
    return UUID(str(row[0]))


async def confirmed(
    pool: RuntimePool,
    world: BookingWorld,
    hour: int,
    *,
    variant: UUID | None = None,
    add_ons: tuple[UUID, ...] = (),
) -> UUID:
    result = await BookingService(pool).create_confirmed_booking(
        world.a.tenant_id,
        world.request(at(hour), variant=variant, add_ons=add_ons),
        actor="test:l8a",
        idempotency_key=None,
    )
    return result.booking_id


async def issued_invoice(payments: PaymentWorld, booking: UUID, **changes: object) -> UUID:
    saved = await post(payments, booking, bill(payments, **changes))
    assert saved.status_code == 200, saved.text
    issued = await payments.settlements.invoices.issue(UUID(saved.json()["invoice"]["document_id"]))
    assert issued.status_code == 200, issued.text
    return UUID(issued.json()["obligation_id"])


# L8-01 (R1) -------------------------------------------------------------------------


async def test_a_cancelled_visits_fee_earns_no_commission(
    payments: PaymentWorld, world: BookingWorld, kit: Kit, app_pool: RuntimePool
) -> None:
    plan = await put_plan(payments, world, kit, [{"service_id": None, "percent": "40.00"}])
    assert plan.status_code == 200, plan.text
    booking = await visit(world, app_pool, cancel=True)
    obligation = await issued_invoice(payments, booking, fee_lines=[fee(payments, "15.00")])
    await pay(payments, obligation, "15.00")
    refused = await accrue(payments, booking, commission_body(kit))
    assert code(refused) == (409, "VISIT_NOT_COMMISSIONABLE")
    async with tenant_transaction(app_pool, world.a.tenant_id) as conn:
        rows = await (
            await conn.execute(
                "select count(*) from gba.visit_commissions where booking_id = %s", (booking,)
            )
        ).fetchone()
    assert rows == (0,)


# L8-02 (R2) -------------------------------------------------------------------------


async def test_prices_are_billed_in_the_currencys_own_minor_units(
    payments: PaymentWorld,
    world: BookingWorld,
    owner_conn: psycopg.Connection,
    app_pool: RuntimePool,
) -> None:
    yen = seed_variant(owner_conn, world, "FAKE_YEN", "JPY", 500000)  # 5000 yen
    dinar = seed_variant(owner_conn, world, "FAKE_DINAR", "KWD", 1000)  # 10.000 dinar
    odd = seed_variant(owner_conn, world, "FAKE_ODD_YEN", "JPY", 12345)  # 123.45 yen
    for hour, variant, amount in ((9, yen, "5000"), (11, dinar, "10.000")):
        booking = await confirmed(app_pool, world, hour, variant=variant)
        saved = await post(payments, booking, bill(payments))
        assert saved.status_code == 200, saved.text
        lines = saved.json()["invoice"]["lines"]
        assert [line["amount"] for line in lines] == [amount]
    booking = await confirmed(app_pool, world, 13, variant=odd)
    assert code(await post(payments, booking, bill(payments))) == (422, "VISIT_PRICE_NOT_EXACT")


# L8-03 (R6) -------------------------------------------------------------------------


async def test_a_free_add_on_gets_no_invoice_line(
    payments: PaymentWorld,
    world: BookingWorld,
    kit: Kit,
    owner_conn: psycopg.Connection,
    app_pool: RuntimePool,
) -> None:
    free = seed_free_add_on(owner_conn, world)
    booking = await confirmed(app_pool, world, 10, add_ons=(free,))
    saved = await post(payments, booking, bill(payments))
    assert saved.status_code == 200, saved.text
    lines = saved.json()["invoice"]["lines"]
    assert [(line["description"], line["amount"]) for line in lines] == [
        ("FAKE FAKE_BASE", "50.00")
    ]
    issued = await payments.settlements.invoices.issue(UUID(saved.json()["invoice"]["document_id"]))
    assert issued.status_code == 200, issued.text
    package = await sell(
        payments,
        kit,
        kind="package",
        price="50.00",
        units=1,
        variant=world.catalog_a.base_variant_id,
    )
    redeemed = await redeem(payments, booking, package["prepaid_id"])
    assert redeemed.status_code == 200, redeemed.text
    (line,) = redeemed.json()["credit"]["lines"]
    assert line["amount"] == "50.00"


# L8-04 (R5) -------------------------------------------------------------------------


async def test_a_package_is_not_spent_on_a_cancelled_visits_fee(
    payments: PaymentWorld, world: BookingWorld, kit: Kit, app_pool: RuntimePool
) -> None:
    package = await sell(
        payments,
        kit,
        kind="package",
        price="45.00",
        units=3,
        variant=world.catalog_a.base_variant_id,
    )
    booking = await visit(world, app_pool, cancel=True)
    await issued_invoice(payments, booking, fee_lines=[fee(payments, "15.00")])
    refused = await redeem(payments, booking, package["prepaid_id"])
    assert code(refused) == (409, "PREPAID_NO_MATCHING_SERVICE")


# L8-05 (R4) -------------------------------------------------------------------------


async def test_a_unit_worth_more_than_the_line_or_the_open_amount_is_refused(
    payments: PaymentWorld, world: BookingWorld, kit: Kit, app_pool: RuntimePool
) -> None:
    base = world.catalog_a.base_variant_id
    # A unit worth 60.00 against a 50.00 service line.
    rich = await sell(payments, kit, kind="package", price="180.00", units=3, variant=base)
    booking, obligation = await billed_visit(payments, world, app_pool, hour=9)
    assert code(await redeem(payments, booking, rich["prepaid_id"])) == (
        409,
        "PREPAID_UNIT_EXCEEDS_LINE",
    )
    # A unit worth 30.00 when only 20.00 of the invoice is still open.
    plain = await sell(payments, kit, kind="package", price="90.00", units=3, variant=base)
    await pay(payments, obligation, "50.00")
    assert code(await redeem(payments, booking, plain["prepaid_id"])) == (
        409,
        "PREPAID_UNIT_EXCEEDS_LINE",
    )
    # Nothing was used on either balance.
    listed = await payments.ledger.client.get(
        f"{salon(payments)}/prepaid", headers=payments.ledger.headers()
    )
    assert listed.status_code == 200, listed.text
    left = {item["prepaid_id"]: item["remaining_units"] for item in listed.json()["items"]}
    assert left[rich["prepaid_id"]] == 3
    assert left[plain["prepaid_id"]] == 3


# L8-06 (R7) -------------------------------------------------------------------------


async def test_linked_drafts_are_frozen(
    payments: PaymentWorld, world: BookingWorld, kit: Kit, app_pool: RuntimePool
) -> None:
    documents = payments.settlements.invoices
    booking = await visit(world, app_pool)
    billed = await post(payments, booking, bill(payments))
    assert billed.status_code == 200, billed.text
    visit_invoice = UUID(billed.json()["invoice"]["document_id"])
    rewritten = await documents.save(
        document=visit_invoice,
        body=documents.draft_body(expected_revision=1, number="FAKE-EDITED"),
    )
    assert code(rewritten) == (409, "FINANCIAL_DOCUMENT_LINKED")

    sold = await payments.ledger.client.post(
        f"{salon(payments)}/prepaid",
        json={
            "kind": "certificate",
            "counterparty_id": str(documents.party),
            "price": "300.00",
            "currency": "USD",
            "book_id": str(documents.ledger.book),
            "control_account_id": str(documents.control),
            "prepayment_account_id": str(kit.accounts["2100"]),
            "invoice_date": "2026-10-01",
            "number": f"FAKE-P-{uuid7().hex[-6:]}",
        },
        headers=payments.ledger.headers(),
    )
    assert sold.status_code == 200, sold.text
    sale = UUID(sold.json()["sale"]["document_id"])
    cheaper = documents.draft_body(expected_revision=1, number="FAKE-CHEAP")
    assert code(await documents.save(document=sale, body=cheaper)) == (
        409,
        "FINANCIAL_DOCUMENT_LINKED",
    )
    # An unlinked draft still saves as before.
    free = await documents.save(body=documents.draft_body(number="FAKE-FREE"))
    assert free.status_code == 200, free.text


# L8-07 (R3) -------------------------------------------------------------------------


async def test_a_recorded_visit_cannot_be_cancelled(
    payments: PaymentWorld, world: BookingWorld, app_pool: RuntimePool
) -> None:
    booking = await visit(world, app_pool)
    billed = await post(payments, booking, bill(payments))
    assert billed.status_code == 200, billed.text
    cancelled = await payments.ledger.client.post(
        f"{salon(payments)}/bookings/{booking}/cancel", json={}, headers=payments.ledger.headers()
    )
    assert cancelled.status_code == 409, cancelled.text
    assert code(cancelled) == (409, "VISIT_ALREADY_RECORDED")
    # An untouched confirmed visit is cancelled as before.
    other = await confirmed(app_pool, world, 16)
    free = await payments.ledger.client.post(
        f"{salon(payments)}/bookings/{other}/cancel", json={}, headers=payments.ledger.headers()
    )
    assert free.status_code == 200, free.text


async def test_a_recorded_visit_cannot_be_moved(
    payments: PaymentWorld, world: BookingWorld, app_pool: RuntimePool
) -> None:
    # The recorded-visit refusal comes before any check of the new time (decision 60).
    booking = await visit(world, app_pool)
    billed = await post(payments, booking, bill(payments))
    assert billed.status_code == 200, billed.text
    moved = await payments.ledger.client.post(
        f"{salon(payments)}/bookings/{booking}/reschedule",
        json={"new_starts_at": at(15).isoformat()},
        headers=payments.ledger.headers(),
    )
    assert moved.status_code == 409, moved.text
    assert code(moved) == (409, "VISIT_ALREADY_RECORDED")
