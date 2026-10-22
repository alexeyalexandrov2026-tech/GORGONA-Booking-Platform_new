"""L6: prepaid packages and gift certificates (package L, BEAUTY-01; FAKE data only).

Design docs/plan/PACKAGE_L6_DESIGN_2026-10-22.md: a balance is sold by an invoice line on the
prepayment liability and usable once paid; redemption is a FIN-03 credit note of the visit invoice.
"""

from uuid import UUID, uuid7

import httpx
import psycopg
import pytest

from gorgona_booking.booking.service import BookingService
from gorgona_booking.db.pool import RuntimePool
from gorgona_booking.db.provisioning import add_membership
from tests.integration import test_l5_commissions as shared
from tests.integration.booking_support import BookingWorld, at
from tests.integration.seed import seed_user
from tests.integration.test_counterparties import card
from tests.integration.test_external_payments import PaymentWorld
from tests.integration.test_l4_billing import bill, post
from tests.integration.test_l5_commissions import Kit
from tests.support.fake_idp import FakeIdp

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


def salon(payments: PaymentWorld) -> str:
    return f"/v1/salons/{payments.ledger.business}"


async def pay(payments: PaymentWorld, obligation: UUID, amount: str) -> None:
    settlement = await payments.settlements.reserved(obligation, amount)
    confirmed = await payments.confirm(
        settlement, 3, [(obligation, amount)], amount, f"FAKE-PAY-{uuid7().hex[-6:]}"
    )
    assert confirmed.status_code == 200, confirmed.text


async def sell(
    payments: PaymentWorld,
    kit: Kit,
    *,
    kind: str,
    price: str,
    units: int | None = None,
    variant: UUID | None = None,
    party: UUID | None = None,
    paid: bool = True,
) -> dict[str, object]:
    world = payments.settlements.invoices
    body: dict[str, object] = {
        "kind": kind,
        "counterparty_id": str(party or world.party),
        "price": price,
        "currency": "USD",
        "book_id": str(world.ledger.book),
        "control_account_id": str(world.control),
        "prepayment_account_id": str(kit.accounts["2100"]),
        "invoice_date": "2026-10-01",
        "number": f"FAKE-P-{uuid7().hex[-6:]}",
    }
    if units is not None:
        body["units"] = units
    if variant is not None:
        body["variant_id"] = str(variant)
    sold = await payments.ledger.client.post(
        f"{salon(payments)}/prepaid", json=body, headers=payments.ledger.headers()
    )
    assert sold.status_code == 200, sold.text
    view: dict[str, object] = sold.json()
    assert view["usable"] is False
    sale = view["sale"]
    assert isinstance(sale, dict)
    issued = await world.issue(UUID(str(sale["document_id"])))
    assert issued.status_code == 200, issued.text
    if paid:
        await pay(payments, UUID(issued.json()["obligation_id"]), price)
    return view


async def billed_visit(
    payments: PaymentWorld,
    world: BookingWorld,
    pool: RuntimePool,
    party: UUID | None = None,
    *,
    hour: int = 10,
) -> tuple[UUID, UUID]:
    """A visit (base 50.00 + massage 20.00) at `hour` with its issued, unpaid invoice."""
    booking = (
        await BookingService(pool).create_confirmed_booking(
            world.a.tenant_id,
            world.request(at(hour), add_ons=(world.catalog_a.massage_add_on_id,)),
            actor="test:l6",
            idempotency_key=None,
        )
    ).booking_id
    changes = {} if party is None else {"counterparty_id": str(party)}
    saved = await post(payments, booking, bill(payments, **changes))
    assert saved.status_code == 200, saved.text
    issued = await payments.settlements.invoices.issue(UUID(saved.json()["invoice"]["document_id"]))
    assert issued.status_code == 200, issued.text
    return booking, UUID(issued.json()["obligation_id"])


async def redeem(
    payments: PaymentWorld,
    booking: UUID,
    prepaid: object,
    *,
    key: str | None = None,
    headers: dict[str, str] | None = None,
    number: str | None = None,
) -> httpx.Response:
    return await payments.ledger.client.post(
        f"{salon(payments)}/bookings/{booking}/redeem",
        json={
            "prepaid_id": str(prepaid),
            "credit_date": "2026-10-02",
            "number": number or f"FAKE-R-{uuid7().hex[-6:]}",
        },
        headers=headers or payments.ledger.headers(key),
    )


def code(response: httpx.Response) -> tuple[int, str]:
    return response.status_code, response.json()["error"]["code"]


# L6-01 ------------------------------------------------------------------------------


async def test_a_sale_is_a_liability_line_usable_once_paid(
    payments: PaymentWorld, world: BookingWorld, kit: Kit, app_pool: RuntimePool
) -> None:
    view = await sell(
        payments,
        kit,
        kind="package",
        price="100.00",
        units=3,
        variant=world.catalog_a.base_variant_id,
        paid=False,
    )
    sale = view["sale"]
    assert isinstance(sale, dict)
    assert [(x["amount"], x["counter_account_id"]) for x in sale["lines"]] == [
        ("100.00", str(kit.accounts["2100"]))
    ]
    booking, _ = await billed_visit(payments, world, app_pool)
    assert code(await redeem(payments, booking, view["prepaid_id"])) == (409, "PREPAID_NOT_PAID")


# L6-02 / L6-04 / L6-05 --------------------------------------------------------------


async def test_package_units_use_up_the_price_exactly(
    payments: PaymentWorld, world: BookingWorld, kit: Kit, app_pool: RuntimePool
) -> None:
    view = await sell(
        payments,
        kit,
        kind="package",
        price="100.00",
        units=3,
        variant=world.catalog_a.base_variant_id,
    )
    prepaid = view["prepaid_id"]
    credited: list[str] = []
    for index in range(3):
        booking, obligation = await billed_visit(payments, world, app_pool, hour=9 + 2 * index)
        redeemed = await redeem(
            payments, booking, prepaid, key=f"l6-unit-{index}", number=f"FAKE-R-{index}"
        )
        assert redeemed.status_code == 200, redeemed.text
        credit = redeemed.json()["credit"]
        assert credit["state"] == "issued"
        (line,) = credit["lines"]
        assert line["counter_account_id"] == str(kit.accounts["2100"])
        assert line["reason"] == "Prepaid redemption"
        credited.append(line["amount"])
        balance = await payments.settlements.balance(obligation)
        assert balance["credited"] == line["amount"]
        if index == 0:
            again = await redeem(payments, booking, prepaid, key="l6-unit-0", number="FAKE-R-0")
            assert again.status_code == 200, again.text
            assert again.json() == redeemed.json()
            assert code(await redeem(payments, booking, prepaid)) == (409, "PREPAID_ALREADY_USED")
    assert credited == ["33.33", "33.33", "33.34"]
    last = redeemed.json()["prepaid"]
    assert (last["remaining_units"], last["remaining_value"]) == (0, "0.00")
    booking, _ = await billed_visit(payments, world, app_pool, hour=15)
    assert code(await redeem(payments, booking, prepaid)) == (409, "PREPAID_EXHAUSTED")


# L6-03 ------------------------------------------------------------------------------


async def test_a_certificate_credits_lines_in_order(
    payments: PaymentWorld, world: BookingWorld, kit: Kit, app_pool: RuntimePool
) -> None:
    view = await sell(payments, kit, kind="certificate", price="60.00")
    booking, obligation = await billed_visit(payments, world, app_pool)
    redeemed = await redeem(payments, booking, view["prepaid_id"])
    assert redeemed.status_code == 200, redeemed.text
    assert [x["amount"] for x in redeemed.json()["credit"]["lines"]] == ["50.00", "10.00"]
    assert redeemed.json()["prepaid"]["remaining_value"] == "0.00"
    balance = await payments.settlements.balance(obligation)
    assert (balance["credited"], balance["available"]) == ("60.00", "10.00")


# L6-04 ------------------------------------------------------------------------------


async def test_another_customer_another_service_or_a_paid_visit_is_refused(
    payments: PaymentWorld, world: BookingWorld, kit: Kit, app_pool: RuntimePool
) -> None:
    gel = await sell(
        payments,
        kit,
        kind="package",
        price="90.00",
        units=1,
        variant=world.catalog_a.gel_variant_id,
    )
    booking, obligation = await billed_visit(payments, world, app_pool)
    assert code(await redeem(payments, booking, gel["prepaid_id"])) == (
        409,
        "PREPAID_NO_MATCHING_SERVICE",
    )
    certificate = await sell(payments, kit, kind="certificate", price="20.00")
    await pay(payments, obligation, "70.00")
    assert code(await redeem(payments, booking, certificate["prepaid_id"])) == (
        409,
        "VISIT_NOTHING_UNPAID",
    )
    other = uuid7()
    saved = await payments.ledger.client.put(
        f"/v1/businesses/{payments.ledger.business}/counterparties/{other}",
        json=card(display_name="FAKE Other Customer"),
        headers=payments.ledger.headers(),
    )
    assert saved.status_code == 200, saved.text
    foreign_visit, _ = await billed_visit(payments, world, app_pool, party=other, hour=13)
    assert code(await redeem(payments, foreign_visit, certificate["prepaid_id"])) == (
        409,
        "PREPAID_OTHER_CUSTOMER",
    )


# L6-06 ------------------------------------------------------------------------------


async def test_without_finance_rights_nothing_is_written(
    payments: PaymentWorld,
    world: BookingWorld,
    kit: Kit,
    app_pool: RuntimePool,
    owner_conn: psycopg.Connection,
    idp: FakeIdp,
) -> None:
    certificate = await sell(payments, kit, kind="certificate", price="20.00")
    booking, obligation = await billed_visit(payments, world, app_pool)
    desk = seed_user(owner_conn, f"l6-desk-{uuid7()}")
    add_membership(owner_conn, tenant_id=world.a.tenant_id, user_id=desk.user_id, role="front_desk")
    headers = {**idp.bearer(desk.subject, email=desk.email), "Idempotency-Key": str(uuid7())}
    refused = await redeem(payments, booking, certificate["prepaid_id"], headers=headers)
    assert refused.status_code == 403, refused.text
    balance = await payments.settlements.balance(obligation)
    assert balance["credited"] == "0.00"
