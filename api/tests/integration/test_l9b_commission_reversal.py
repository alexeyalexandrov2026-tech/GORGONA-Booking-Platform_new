"""L9b: a refund of a visit reverses its commission (package L, BEAUTY-01; FAKE data only).

Design docs/plan/PACKAGE_L9_DESIGN_2026-10-23.md decisions 81-84.
"""

from typing import Any
from uuid import UUID, uuid7

import httpx
import psycopg
import pytest

from gorgona_booking.db.pool import RuntimePool, tenant_transaction
from tests.integration import test_l6_prepaid as shared
from tests.integration.booking_support import BookingWorld
from tests.integration.conftest import ProvisionedDatabase
from tests.integration.test_credit_notes import CreditWorld
from tests.integration.test_external_payments import PaymentWorld
from tests.integration.test_l5_commissions import (
    Kit,
    accrue,
    commission_body,
    paid_visit,
    put_plan,
)
from tests.integration.test_l6_prepaid import billed_visit, code, pay, redeem, salon, sell
from tests.integration.test_l8b2_finance_races import race

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


def documents(payments: PaymentWorld) -> str:
    ledger = payments.ledger
    return f"/v1/businesses/{ledger.business}/financial-documents/books/{ledger.book}"


async def issue_accrual(payments: PaymentWorld, document: object) -> UUID:
    issued = await payments.ledger.client.post(
        f"{documents(payments)}/accruals/{document}/issue",
        json={
            "schema_version": 1,
            "expected_revision": 1,
            "entry_date": "2026-10-02",
            "attestation": "confirmed_account_treatment",
        },
        headers=payments.ledger.headers(),
    )
    assert issued.status_code == 200, issued.text
    return UUID(issued.json()["obligation_id"])


async def commissioned(
    payments: PaymentWorld,
    world: BookingWorld,
    pool: RuntimePool,
    kit: Kit,
    *,
    issue: bool = True,
    plan: bool = True,
) -> tuple[UUID, dict[str, Any]]:
    """A paid visit (base 50.00 + massage 20.00, fee 5.00, tip 10.00) with its 10 % commission."""
    if plan:
        saved = await put_plan(payments, world, kit, [{"service_id": None, "percent": "10.00"}])
        assert saved.status_code == 200, saved.text
    booking = await paid_visit(payments, world, pool, kit)
    accrued = await accrue(
        payments, booking, commission_body(kit, tips_account_id=str(kit.accounts["2300"]))
    )
    assert accrued.status_code == 200, accrued.text
    view: dict[str, Any] = accrued.json()
    assert view["accrual"]["total"] == "7.00"
    if issue:
        await issue_accrual(payments, view["document_id"])
    return booking, view


async def invoice_lines(
    payments: PaymentWorld, booking: UUID
) -> tuple[UUID, list[tuple[UUID, UUID]]]:
    read = await payments.ledger.client.get(
        f"{salon(payments)}/bookings/{booking}/invoice", headers=payments.ledger.headers()
    )
    assert read.status_code == 200, read.text
    view = read.json()
    return UUID(view["obligation"]["obligation_id"]), [
        (UUID(line["line_id"]), UUID(line["counter_account_id"]))
        for line in view["invoice"]["lines"]
    ]


async def refund(
    payments: PaymentWorld, kit: Kit, booking: UUID, lines: list[tuple[int, str]]
) -> UUID:
    """A FIN-03 credit note of the visit invoice; the paid part becomes a refund obligation."""
    credits = CreditWorld(payments, kit.accounts)
    obligation, ids = await invoice_lines(payments, booking)
    document = uuid7()
    body = credits.draft(obligation, [], number=f"FAKE-RF-{document.hex[-6:]}")
    # Each refunded line goes back to the account of the line it reduces.
    body["lines"] = [
        {
            "line_id": str(uuid7()),
            "credited_line_id": str(ids[index][0]),
            "counter_account_id": str(ids[index][1]),
            "description": "FAKE refund",
            "amount": amount,
        }
        for index, amount in lines
    ]
    saved = await credits.save(document, body)
    assert saved.status_code == 200, saved.text
    issued = await credits.issue(document, refund=kit.accounts["2100"])
    assert issued.status_code == 200, issued.text
    return document


async def reverse(
    payments: PaymentWorld,
    booking: UUID,
    *,
    key: str | None = None,
    refund_account: UUID | None = None,
    number: str | None = None,
) -> httpx.Response:
    return await payments.ledger.client.post(
        f"{salon(payments)}/bookings/{booking}/commission/reversal",
        json={
            "credit_date": "2026-10-04",
            "number": number or f"FAKE-CR-{uuid7().hex[-6:]}",
            "refund_control_account_id": None if refund_account is None else str(refund_account),
        },
        headers=payments.ledger.headers(key),
    )


async def pay_payee(payments: PaymentWorld, kit: Kit, obligation: UUID, amount: str) -> None:
    """Pay the commission to its payee through a payable settlement."""
    world = payments.settlements
    settlement = uuid7()
    prepared = await world.prepare(
        settlement,
        [(obligation, amount)],
        direction="payable",
        counterparty_id=str(kit.payee),
    )
    assert prepared.status_code == 200, prepared.text
    for action, sequence in (("approve", 1), ("reserve", 2)):
        acted = await world.act(settlement, action, sequence)
        assert acted.status_code == 200, acted.text
    confirmed = await payments.confirm(
        settlement, 3, [(obligation, amount)], amount, "FAKE-COMMISSION-PAY"
    )
    assert confirmed.status_code == 200, confirmed.text


async def commission(payments: PaymentWorld, booking: UUID) -> dict[str, Any]:
    read = await payments.ledger.client.get(
        f"{salon(payments)}/bookings/{booking}/commission", headers=payments.ledger.headers()
    )
    assert read.status_code == 200, read.text
    view: dict[str, Any] = read.json()
    return view


# Invoice lines of `paid_visit`: 0 base 50.00, 1 massage 20.00, 2 fee 5.00, 3 tip 10.00.
BASE, MASSAGE, FEE = 0, 1, 2


# L9-07 (decisions 81-82) ------------------------------------------------------------


async def test_a_full_refund_reverses_the_whole_commission(
    payments: PaymentWorld, world: BookingWorld, kit: Kit, app_pool: RuntimePool
) -> None:
    booking, _ = await commissioned(payments, world, app_pool, kit)
    assert (await commission(payments, booking))["to_reverse"] == "0.00"
    document = await refund(payments, kit, booking, [(BASE, "50.00"), (MASSAGE, "20.00")])
    pending = await commission(payments, booking)
    assert pending["to_reverse"] == "7.00"
    reversed_ = await reverse(payments, booking, key="l9b-full-1", number="FAKE-CR-FULL")
    assert reversed_.status_code == 200, reversed_.text
    view = reversed_.json()
    (row,) = view["reversals"]
    assert (row["refund_document_id"], row["amount"]) == (str(document), "7.00")
    assert row["reversal_document_id"] is not None
    assert view["to_reverse"] == "0.00"
    again = await reverse(payments, booking, key="l9b-full-1", number="FAKE-CR-FULL")
    assert again.status_code == 200, again.text
    assert again.json() == view
    assert code(await reverse(payments, booking)) == (409, "VISIT_NOTHING_TO_REVERSE")
    accrual = await payments.settlements.balance(UUID(view["accrual"]["obligation_id"]))
    assert accrual["credited"] == "7.00"


async def test_a_partial_refund_reverses_only_its_share(
    payments: PaymentWorld, world: BookingWorld, kit: Kit, app_pool: RuntimePool
) -> None:
    booking, _ = await commissioned(payments, world, app_pool, kit)
    await refund(payments, kit, booking, [(MASSAGE, "20.00")])
    reversed_ = await reverse(payments, booking)
    assert reversed_.status_code == 200, reversed_.text
    # 7.00 times 20.00 of 70.00 is 2.00.
    assert [r["amount"] for r in reversed_.json()["reversals"]] == ["2.00"]


# L9-08 (decision 82) ----------------------------------------------------------------


async def test_refunds_reverse_cumulatively_and_fees_reverse_nothing(
    payments: PaymentWorld, world: BookingWorld, kit: Kit, app_pool: RuntimePool
) -> None:
    booking, _ = await commissioned(payments, world, app_pool, kit)
    # A refund of the fee only: recorded, nothing to reverse.
    fees = await refund(payments, kit, booking, [(FEE, "5.00")])
    zero = await reverse(payments, booking)
    assert zero.status_code == 200, zero.text
    (row,) = zero.json()["reversals"]
    assert (row["refund_document_id"], row["amount"], row["reversal_document_id"]) == (
        str(fees),
        "0.00",
        None,
    )
    # 10.01 of 70.00 is 1.001 -> 1.00; then 35.03 of 70.00 is 3.503 -> 3.50, so 2.50 more.
    await refund(payments, kit, booking, [(MASSAGE, "10.01")])
    first = await reverse(payments, booking)
    assert first.status_code == 200, first.text
    await refund(payments, kit, booking, [(BASE, "25.02")])
    second = await reverse(payments, booking)
    assert second.status_code == 200, second.text
    amounts = [r["amount"] for r in second.json()["reversals"]]
    assert amounts == ["0.00", "1.00", "2.50"]
    accrual = await payments.settlements.balance(UUID(second.json()["accrual"]["obligation_id"]))
    assert accrual["credited"] == "3.50"


# L9-09 (decisions 81-82) ------------------------------------------------------------


async def test_redemptions_drafts_and_paid_accruals(
    payments: PaymentWorld, world: BookingWorld, kit: Kit, app_pool: RuntimePool
) -> None:
    plan = await put_plan(payments, world, kit, [{"service_id": None, "percent": "10.00"}])
    assert plan.status_code == 200, plan.text
    # A visit settled by a prepaid unit and a payment: the redemption credit is no refund.
    view = await sell(
        payments,
        kit,
        kind="package",
        price="50.00",
        units=1,
        variant=world.catalog_a.base_variant_id,
    )
    redeemed_visit, obligation = await billed_visit(payments, world, app_pool, hour=13)
    assert (await redeem(payments, redeemed_visit, view["prepaid_id"])).status_code == 200
    await pay(payments, obligation, "20.00")
    accrued = await accrue(payments, redeemed_visit, commission_body(kit))
    assert accrued.status_code == 200, accrued.text
    await issue_accrual(payments, accrued.json()["document_id"])
    assert code(await reverse(payments, redeemed_visit)) == (409, "VISIT_NOTHING_TO_REVERSE")
    # A draft accrual is issued first.
    draft_visit, _ = await commissioned(payments, world, app_pool, kit, issue=False, plan=False)
    await refund(payments, kit, draft_visit, [(BASE, "50.00")])
    assert code(await reverse(payments, draft_visit)) == (409, "VISIT_COMMISSION_NOT_ISSUED")


async def test_a_paid_commission_is_reversed_into_a_refund_from_the_payee(
    payments: PaymentWorld, world: BookingWorld, kit: Kit, app_pool: RuntimePool
) -> None:
    booking, view = await commissioned(payments, world, app_pool, kit)
    accrual = (await commission(payments, booking))["accrual"]["obligation_id"]
    await pay_payee(payments, kit, UUID(accrual), "7.00")
    await refund(payments, kit, booking, [(BASE, "50.00"), (MASSAGE, "20.00")])
    missing = await reverse(payments, booking)
    assert code(missing) == (409, "FINANCIAL_REFUND_ACCOUNT_INVALID")
    done = await reverse(payments, booking, refund_account=kit.accounts["1200"])
    assert done.status_code == 200, done.text
    assert [r["amount"] for r in done.json()["reversals"]] == ["7.00"]
    assert view["booking_id"] == str(booking)


# L9-10 (decision 84) ----------------------------------------------------------------


async def test_two_racing_reversals_leave_one_and_lineage_is_permanent(
    payments: PaymentWorld,
    world: BookingWorld,
    kit: Kit,
    app_pool: RuntimePool,
    test_database: ProvisionedDatabase,
) -> None:
    booking, _ = await commissioned(payments, world, app_pool, kit)
    await refund(payments, kit, booking, [(BASE, "50.00")])
    answers = await race(
        app_pool,
        test_database,
        world.a.tenant_id,
        "select 1 from gba.bookings where id = %s for update",
        booking,
        [
            reverse(payments, booking, key="l9b-race-1"),
            reverse(payments, booking, key="l9b-race-2"),
        ],
    )
    assert sorted(a.status_code for a in answers) == [200, 409], [a.text for a in answers]
    (refused,) = [a for a in answers if a.status_code == 409]
    assert code(refused) == (409, "VISIT_NOTHING_TO_REVERSE")
    tenant = world.a.tenant_id
    for statement in (
        "update gba.visit_commission_reversals set reversal_document_id = null",
        "delete from gba.visit_commission_reversals",
    ):
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            async with tenant_transaction(app_pool, tenant) as conn:
                await conn.execute(statement)
    for business, expected in ((tenant, 1), (world.b.tenant_id, 0)):
        async with tenant_transaction(app_pool, business) as conn:
            row = await (
                await conn.execute("select count(*) from gba.visit_commission_reversals")
            ).fetchone()
        assert row == (expected,)
