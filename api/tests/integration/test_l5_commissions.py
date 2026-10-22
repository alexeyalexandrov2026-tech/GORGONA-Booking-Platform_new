"""L5: commissions and tips through FIN-03 manual accruals (package L, BEAUTY-01; FAKE data only).

Design docs/plan/PACKAGE_L5_DESIGN_2026-10-22.md: a plan per specialist; the commission is accrued
only when the visit invoice is fully paid; tips on a liability account move to the payee's payable.
"""

from dataclasses import dataclass
from uuid import UUID, uuid7

import httpx
import psycopg
import pytest

from gorgona_booking.business import ledger
from gorgona_booking.db.pool import RuntimePool, tenant_transaction
from gorgona_booking.db.provisioning import add_membership
from tests.integration import test_l4_billing as shared
from tests.integration.booking_support import BookingWorld
from tests.integration.seed import seed_user
from tests.integration.test_counterparties import card
from tests.integration.test_external_payments import PaymentWorld
from tests.integration.test_l4_billing import bill, post, visit
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


@dataclass(frozen=True)
class Kit:
    payee: UUID
    accounts: dict[str, UUID]


@pytest.fixture
async def kit(payments: PaymentWorld, app_pool: RuntimePool) -> Kit:
    world = payments.ledger
    payee = uuid7()
    saved = await world.client.put(
        f"/v1/businesses/{world.business}/counterparties/{payee}",
        json=card(display_name="FAKE Specialist", roles=["supplier"]),
        headers=world.headers(),
    )
    assert saved.status_code == 200, saved.text
    async with tenant_transaction(app_pool, world.business) as conn:
        chart = await ledger.list_accounts(conn, world.business, world.book, after=None, limit=100)
    return Kit(payee, {a.code: a.account_id for a in chart.items})


def plan_path(payments: PaymentWorld, world: BookingWorld) -> str:
    return f"/v1/salons/{payments.ledger.business}/staff/{world.artist_a1}/commission"


async def put_plan(
    payments: PaymentWorld,
    world: BookingWorld,
    kit: Kit,
    rules: list[dict[str, object]],
    revision: int = 0,
) -> httpx.Response:
    return await payments.ledger.client.put(
        plan_path(payments, world),
        json={
            "expected_revision": revision,
            "counterparty_id": str(kit.payee),
            "currency": "USD",
            "rules": rules,
        },
        headers=payments.ledger.headers(),
    )


def commission_body(kit: Kit, **changes: object) -> dict[str, object]:
    return {
        "expense_account_id": str(kit.accounts["6000"]),
        "payable_account_id": str(kit.accounts["2200"]),
        "accrual_date": "2026-10-02",
        "number": f"FAKE-C-{uuid7().hex[-6:]}",
        **changes,
    }


async def accrue(
    payments: PaymentWorld,
    booking: UUID,
    body: dict[str, object],
    *,
    key: str | None = None,
    headers: dict[str, str] | None = None,
) -> httpx.Response:
    return await payments.ledger.client.post(
        f"/v1/salons/{payments.ledger.business}/bookings/{booking}/commission",
        json=body,
        headers=headers or payments.ledger.headers(key),
    )


async def paid_visit(
    payments: PaymentWorld,
    world: BookingWorld,
    pool: RuntimePool,
    kit: Kit,
    *,
    pay: str | None = "85.00",
) -> UUID:
    """Base 50.00 + massage 20.00, a 5.00 fee on revenue and a 10.00 tip held on 2300."""
    booking = await visit(world, pool)
    fees = [
        {
            "description": "FAKE booking fee",
            "amount": "5.00",
            "account_id": str(kit.accounts["4100"]),
        },
        {"description": "FAKE tip", "amount": "10.00", "account_id": str(kit.accounts["2300"])},
    ]
    saved = await post(payments, booking, bill(payments, fee_lines=fees))
    assert saved.status_code == 200, saved.text
    issued = await payments.settlements.invoices.issue(UUID(saved.json()["invoice"]["document_id"]))
    assert issued.status_code == 200, issued.text
    if pay is not None:
        obligation = UUID(issued.json()["obligation_id"])
        settlement = await payments.settlements.reserved(obligation, pay)
        confirmed = await payments.confirm(
            settlement, 3, [(obligation, pay)], pay, f"FAKE-PAY-{uuid7().hex[-6:]}"
        )
        assert confirmed.status_code == 200, confirmed.text
    return booking


# L5-01 ------------------------------------------------------------------------------


async def test_a_plan_is_replaced_whole_with_its_revision(
    payments: PaymentWorld, world: BookingWorld, kit: Kit, app_pool: RuntimePool
) -> None:
    service = await _service_of(app_pool, world)
    saved = await put_plan(
        payments,
        world,
        kit,
        [{"service_id": str(service), "percent": "12.50"}, {"service_id": None, "amount": "4.00"}],
    )
    assert saved.status_code == 200, saved.text
    assert saved.json()["revision"] == 1
    assert saved.json()["rules"] == [
        {"service_id": str(service), "percent": "12.50", "amount": None},
        {"service_id": None, "percent": None, "amount": "4.00"},
    ]
    stale = await put_plan(payments, world, kit, [], revision=0)
    assert stale.status_code == 409, stale.text
    invalid: tuple[list[dict[str, object]], ...] = (
        [{"service_id": None, "percent": "12.345"}],
        [{"service_id": None, "percent": "10", "amount": "1.00"}],
        [{"service_id": None}],
        [{"service_id": None, "percent": "10"}, {"service_id": None, "amount": "1.00"}],
        [{"service_id": None, "percent": "100.01"}],
    )
    for rules in invalid:
        refused = await put_plan(payments, world, kit, rules, revision=1)
        assert refused.status_code == 422, (rules, refused.text)


async def _service_of(pool: RuntimePool, world: BookingWorld) -> UUID:
    async with tenant_transaction(pool, world.a.tenant_id) as conn:
        row = await (
            await conn.execute(
                "select service_id from gba.service_variants where id = %s",
                (world.catalog_a.base_variant_id,),
            )
        ).fetchone()
    assert row is not None
    return UUID(str(row[0]))


# L5-02 ------------------------------------------------------------------------------


@pytest.mark.parametrize("pay", [None, "40.00"])
async def test_an_unpaid_or_partly_paid_visit_accrues_nothing(
    payments: PaymentWorld,
    world: BookingWorld,
    kit: Kit,
    app_pool: RuntimePool,
    pay: str | None,
) -> None:
    assert (
        await put_plan(payments, world, kit, [{"service_id": None, "percent": "10"}])
    ).status_code == 200
    booking = await paid_visit(payments, world, app_pool, kit, pay=pay)
    refused = await accrue(payments, booking, commission_body(kit))
    assert refused.status_code == 409, refused.text
    assert refused.json()["error"]["code"] == "VISIT_NOT_PAID"


async def test_a_visit_without_an_invoice_accrues_nothing(
    payments: PaymentWorld, world: BookingWorld, kit: Kit, app_pool: RuntimePool
) -> None:
    booking = await visit(world, app_pool)
    refused = await accrue(payments, booking, commission_body(kit))
    assert refused.status_code == 409, refused.text
    assert refused.json()["error"]["code"] == "VISIT_NOT_PAID"


# L5-03 / L5-04 / L5-05 --------------------------------------------------------------


async def test_a_paid_visit_accrues_the_commission_and_the_tips_once(
    payments: PaymentWorld, world: BookingWorld, kit: Kit, app_pool: RuntimePool
) -> None:
    service = await _service_of(app_pool, world)
    # 33.35 % of the service with its add-on (70.00) is 23.345: half up to 23.35.
    plan = await put_plan(payments, world, kit, [{"service_id": str(service), "percent": "33.35"}])
    assert plan.status_code == 200, plan.text
    booking = await paid_visit(payments, world, app_pool, kit)
    body = commission_body(kit, tips_account_id=str(kit.accounts["2300"]))
    accrued = await accrue(payments, booking, body, key="l5-accrue-1")
    assert accrued.status_code == 200, accrued.text
    view = accrued.json()
    accrual = view["accrual"]
    assert (accrual["kind"], accrual["direction"], accrual["state"]) == (
        "manual_accrual",
        "payable",
        "draft",
    )
    assert accrual["counterparty_id"] == str(kit.payee)
    assert accrual["control_account_id"] == str(kit.accounts["2200"])
    assert [(x["description"], x["amount"], x["counter_account_id"]) for x in accrual["lines"]] == [
        ("Commission: FAKE FAKE_BASE", "23.35", str(kit.accounts["6000"])),
    ]
    assert accrual["total"] == "23.35"
    # The tip stays a liability held for the specialist (never revenue); it is reported here.
    assert (view["tips_account_id"], view["tips"]) == (str(kit.accounts["2300"]), "10.00")
    again = await accrue(payments, booking, body, key="l5-accrue-1")
    assert again.status_code == 200, again.text
    assert again.json() == view
    other = await accrue(payments, booking, body, key="l5-accrue-2")
    assert other.status_code == 409, other.text
    assert other.json()["error"]["code"] == "VISIT_ALREADY_COMMISSIONED"
    issued = await payments.ledger.client.post(
        f"/v1/businesses/{payments.ledger.business}/financial-documents/books/"
        f"{payments.ledger.book}/accruals/{accrual['document_id']}/issue",
        json={
            "schema_version": 1,
            "expected_revision": 1,
            "entry_date": "2026-10-02",
            "attestation": "confirmed_account_treatment",
        },
        headers=payments.ledger.headers(),
    )
    assert issued.status_code == 200, issued.text
    obligation = await payments.settlements.balance(UUID(issued.json()["obligation_id"]))
    assert (obligation["direction"], obligation["principal"]) == ("payable", "23.35")


async def test_the_default_rule_and_a_fixed_amount(
    payments: PaymentWorld, world: BookingWorld, kit: Kit, app_pool: RuntimePool
) -> None:
    plan = await put_plan(payments, world, kit, [{"service_id": None, "amount": "7.00"}])
    assert plan.status_code == 200, plan.text
    booking = await paid_visit(payments, world, app_pool, kit)
    accrued = await accrue(payments, booking, commission_body(kit))
    assert accrued.status_code == 200, accrued.text
    lines = accrued.json()["accrual"]["lines"]
    # Without a tips account no tip is reported; the fee is never in the base.
    assert [(x["description"], x["amount"]) for x in lines] == [
        ("Commission: FAKE FAKE_BASE", "7.00")
    ]


async def test_a_revenue_tips_account_is_refused(
    payments: PaymentWorld, world: BookingWorld, kit: Kit, app_pool: RuntimePool
) -> None:
    assert (
        await put_plan(payments, world, kit, [{"service_id": None, "percent": "10"}])
    ).status_code == 200
    booking = await paid_visit(payments, world, app_pool, kit)
    refused = await accrue(
        payments, booking, commission_body(kit, tips_account_id=str(kit.accounts["4100"]))
    )
    assert refused.status_code == 422, refused.text
    assert refused.json()["error"]["code"] == "TIPS_ACCOUNT_NOT_LIABILITY"


async def test_a_specialist_without_a_plan_accrues_nothing(
    payments: PaymentWorld, world: BookingWorld, kit: Kit, app_pool: RuntimePool
) -> None:
    booking = await paid_visit(payments, world, app_pool, kit)
    refused = await accrue(payments, booking, commission_body(kit))
    assert refused.status_code == 409, refused.text
    assert refused.json()["error"]["code"] == "COMMISSION_PLAN_MISSING"


# L5-06 ------------------------------------------------------------------------------


async def test_without_finance_rights_nothing_is_written(
    payments: PaymentWorld,
    world: BookingWorld,
    kit: Kit,
    app_pool: RuntimePool,
    owner_conn: psycopg.Connection,
    idp: FakeIdp,
) -> None:
    desk = seed_user(owner_conn, f"l5-desk-{uuid7()}")
    add_membership(owner_conn, tenant_id=world.a.tenant_id, user_id=desk.user_id, role="front_desk")
    headers = {**idp.bearer(desk.subject, email=desk.email), "Idempotency-Key": str(uuid7())}
    refused_plan = await payments.ledger.client.put(
        plan_path(payments, world),
        json={
            "expected_revision": 0,
            "counterparty_id": str(kit.payee),
            "currency": "USD",
            "rules": [{"service_id": None, "percent": "10"}],
        },
        headers=headers,
    )
    assert refused_plan.status_code == 403, refused_plan.text
    async with tenant_transaction(app_pool, world.b.tenant_id) as conn:
        foreign = await (
            await conn.execute(
                "select count(*) from gba.commission_plans where resource_id = %s",
                (world.artist_a1,),
            )
        ).fetchone()
    assert foreign == (0,)
