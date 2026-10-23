"""L4: visit billing through FIN-03 (package L, BEAUTY-01; FAKE data only).

Design docs/plan/PACKAGE_L4_DESIGN_2026-10-22.md: the visit invoice is a FIN-03 draft built from the
quote lines plus fee lines; one per visit; a deposit and the rest are settlements of that invoice.
"""

from uuid import UUID, uuid7

import httpx
import psycopg
import pytest

from gorgona_booking.booking.service import BookingService
from gorgona_booking.db.pool import RuntimePool, tenant_transaction
from gorgona_booking.db.provisioning import add_membership
from tests.integration import test_external_payments as shared
from tests.integration.booking_support import BookingWorld, at
from tests.integration.fee_policy_support import publish_fee_policy, soon_visit
from tests.integration.seed import seed_user
from tests.integration.test_external_payments import PaymentWorld
from tests.support.fake_idp import FakeIdp

pytestmark = pytest.mark.anyio
client = shared.client
idp = shared.idp
manager_a = shared.manager_a
manager_b = shared.manager_b
enabled = shared.enabled
invoices = shared.invoices
payments = shared.payments
__all__ = ["client", "enabled", "idp", "invoices", "manager_a", "manager_b", "payments"]


def bill(payments: PaymentWorld, **changes: object) -> dict[str, object]:
    world = payments.settlements.invoices
    return {
        "book_id": str(world.ledger.book),
        "counterparty_id": str(world.party),
        "control_account_id": str(world.control),
        "revenue_account_id": str(world.counter),
        "invoice_date": "2026-10-01",
        "number": f"FAKE-V-{uuid7().hex[-6:]}",
        **changes,
    }


def fee(payments: PaymentWorld, amount: str = "5.00") -> dict[str, object]:
    return {
        "description": "FAKE late cancellation fee",
        "amount": amount,
        "account_id": str(payments.settlements.invoices.counter),
    }


def path(payments: PaymentWorld, booking: UUID) -> str:
    return f"/v1/salons/{payments.ledger.business}/bookings/{booking}/invoice"


async def post(
    payments: PaymentWorld,
    booking: UUID,
    body: dict[str, object],
    *,
    key: str | None = None,
    headers: dict[str, str] | None = None,
) -> httpx.Response:
    return await payments.ledger.client.post(
        path(payments, booking), json=body, headers=headers or payments.ledger.headers(key)
    )


async def visit(world: BookingWorld, pool: RuntimePool, *, cancel: bool = False) -> UUID:
    """A confirmed FAKE visit: base (50.00) and the massage add-on (20.00)."""
    service = BookingService(pool)
    result = await service.create_confirmed_booking(
        world.a.tenant_id,
        world.request(at(10), add_ons=(world.catalog_a.massage_add_on_id,)),
        actor="test:l4",
        idempotency_key=None,
    )
    if cancel:
        await service.cancel(world.a.tenant_id, result.booking_id, actor="test:l4")
    return result.booking_id


# L4-01 / L4-03 ----------------------------------------------------------------------


async def test_a_visit_invoice_has_the_quote_lines_then_fees(
    payments: PaymentWorld, world: BookingWorld, app_pool: RuntimePool
) -> None:
    booking = await visit(world, app_pool)
    body = bill(payments, fee_lines=[fee(payments)])
    saved = await post(payments, booking, body, key="l4-bill-1")
    assert saved.status_code == 200, saved.text
    view = saved.json()
    invoice = view["invoice"]
    assert view["booking_id"] == str(booking)
    assert (invoice["state"], invoice["direction"], invoice["currency"]) == (
        "draft",
        "receivable",
        "USD",
    )
    assert [(line["description"], line["amount"]) for line in invoice["lines"]] == [
        ("FAKE FAKE_BASE", "50.00"),
        ("FAKE FAKE_MASSAGE", "20.00"),
        ("FAKE late cancellation fee", "5.00"),
    ]
    assert invoice["total"] == "75.00"
    assert view["obligation"] is None
    again = await post(payments, booking, body, key="l4-bill-1")
    assert again.status_code == 200, again.text
    assert again.json() == view
    other = await post(payments, booking, bill(payments), key="l4-bill-2")
    assert other.status_code == 409, other.text
    assert other.json()["error"]["code"] == "VISIT_ALREADY_INVOICED"


# L4-02 ------------------------------------------------------------------------------


async def test_a_cancelled_visit_is_billed_for_fees_only(
    payments: PaymentWorld, world: BookingWorld, app_pool: RuntimePool
) -> None:
    before = await visit(world, app_pool, cancel=True)
    nothing = await post(payments, before, bill(payments))
    assert nothing.status_code == 409, nothing.text
    assert nothing.json()["error"]["code"] == "VISIT_NOT_BILLABLE"
    # L9 decision 79: the fee follows the policy in force when the visit was booked.
    ledger = payments.ledger
    published = await publish_fee_policy(
        ledger.client, ledger.business, ledger.headers(), late={"amount": "15.00"}
    )
    assert published.status_code == 200, published.text
    booking = await soon_visit(world, app_pool, hours=2, cancel=True)
    saved = await post(payments, booking, bill(payments))
    assert saved.status_code == 200, saved.text
    invoice = saved.json()["invoice"]
    assert [(line["description"], line["amount"]) for line in invoice["lines"]] == [
        ("Late cancellation fee", "15.00")
    ]


async def test_a_hold_is_not_billable(
    payments: PaymentWorld, world: BookingWorld, app_pool: RuntimePool
) -> None:
    hold = await BookingService(app_pool).create_hold(
        world.a.tenant_id, world.request(at(12)), actor="test:l4", idempotency_key=None
    )
    refused = await post(payments, hold.booking_id, bill(payments, fee_lines=[fee(payments)]))
    assert refused.status_code == 409, refused.text
    assert refused.json()["error"]["code"] == "VISIT_NOT_BILLABLE"


# L4-04 ------------------------------------------------------------------------------


async def test_a_deposit_and_the_rest_settle_the_visit_invoice(
    payments: PaymentWorld, world: BookingWorld, app_pool: RuntimePool
) -> None:
    booking = await visit(world, app_pool)
    saved = await post(payments, booking, bill(payments))
    assert saved.status_code == 200, saved.text
    document = UUID(saved.json()["invoice"]["document_id"])
    issued = await payments.settlements.invoices.issue(document)
    assert issued.status_code == 200, issued.text
    obligation = UUID(issued.json()["obligation_id"])
    seen = await payments.ledger.client.get(path(payments, booking), headers=payments.ledger.auth)
    assert seen.status_code == 200, seen.text
    assert seen.json()["obligation"]["obligation_id"] == str(obligation)
    assert (seen.json()["obligation"]["paid"], seen.json()["obligation"]["available"]) == (
        "0.00",
        "70.00",
    )
    world_settlements = payments.settlements
    deposit = await world_settlements.reserved(obligation, "20.00")
    paid = await payments.confirm(deposit, 3, [(obligation, "20.00")], "20.00", "FAKE-DEPOSIT")
    assert paid.status_code == 200, paid.text
    after_deposit = (
        await payments.ledger.client.get(path(payments, booking), headers=payments.ledger.auth)
    ).json()["obligation"]
    assert (after_deposit["paid"], after_deposit["available"]) == ("20.00", "50.00")
    rest = await world_settlements.reserved(obligation, "50.00")
    settled = await payments.confirm(rest, 3, [(obligation, "50.00")], "50.00", "FAKE-REST")
    assert settled.status_code == 200, settled.text
    final = (
        await payments.ledger.client.get(path(payments, booking), headers=payments.ledger.auth)
    ).json()["obligation"]
    assert (final["paid"], final["available"]) == ("70.00", "0.00")


# L4-05 ------------------------------------------------------------------------------


async def test_without_finance_rights_nothing_is_written(
    payments: PaymentWorld,
    world: BookingWorld,
    app_pool: RuntimePool,
    owner_conn: psycopg.Connection,
    idp: FakeIdp,
) -> None:
    booking = await visit(world, app_pool)
    desk = seed_user(owner_conn, f"l4-desk-{uuid7()}")
    add_membership(owner_conn, tenant_id=world.a.tenant_id, user_id=desk.user_id, role="front_desk")
    headers = {
        **idp.bearer(desk.subject, email=desk.email),
        "Idempotency-Key": str(uuid7()),
    }
    refused = await post(payments, booking, bill(payments), headers=headers)
    assert refused.status_code == 403, refused.text
    async with tenant_transaction(app_pool, world.a.tenant_id) as conn:
        linked = await (
            await conn.execute(
                "select count(*) from gba.visit_invoices where booking_id = %s", (booking,)
            )
        ).fetchone()
    assert linked == (0,)


async def test_the_link_is_permanent_and_company_scoped(
    payments: PaymentWorld, world: BookingWorld, app_pool: RuntimePool
) -> None:
    booking = await visit(world, app_pool)
    assert (await post(payments, booking, bill(payments))).status_code == 200
    for statement in (
        "update gba.visit_invoices set document_id = document_id where booking_id = %s",
        "delete from gba.visit_invoices where booking_id = %s",
    ):
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            async with tenant_transaction(app_pool, world.a.tenant_id) as conn:
                await conn.execute(statement, (booking,))
    async with tenant_transaction(app_pool, world.b.tenant_id) as conn:
        seen = await (
            await conn.execute(
                "select count(*) from gba.visit_invoices where booking_id = %s", (booking,)
            )
        ).fetchone()
    assert seen == (0,)
