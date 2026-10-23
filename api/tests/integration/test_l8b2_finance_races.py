"""L8b2: accrual and redemption races and module refusals (package L, BEAUTY-01; FAKE data only).

Design docs/plan/PACKAGE_L8_DESIGN_2026-10-23.md decisions 69 and 71.
"""

import asyncio
from collections.abc import Awaitable
from uuid import UUID

import httpx
import psycopg
import pytest

from gorgona_booking.db.pool import RuntimePool, tenant_transaction
from tests.integration import test_l6_prepaid as shared
from tests.integration.booking_support import BookingWorld
from tests.integration.configuration_support import Config
from tests.integration.conftest import ProvisionedDatabase
from tests.integration.test_external_payments import PaymentWorld
from tests.integration.test_l4_billing import bill, post, visit
from tests.integration.test_l5_commissions import (
    MODULES,
    Kit,
    accrue,
    commission_body,
    paid_visit,
    put_plan,
)
from tests.integration.test_l6_prepaid import billed_visit, code, redeem, salon, sell
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


async def wait_for_waiters(monitor: psycopg.AsyncConnection, count: int) -> None:
    """Every request is in flight: at least `count` lock requests are not granted."""
    deadline = asyncio.get_running_loop().time() + 8
    while asyncio.get_running_loop().time() < deadline:
        row = await (
            await monitor.execute("select count(*) from pg_locks where not granted")
        ).fetchone()
        if row is not None and row[0] >= count:
            return
        await asyncio.sleep(0.01)
    pytest.fail(f"L8-17: fewer than {count} waiting lock requests observed in pg_locks")


async def race(
    pool: RuntimePool,
    database: ProvisionedDatabase,
    tenant: UUID,
    lock_sql: str,
    row_id: UUID,
    calls: list[Awaitable[httpx.Response]],
) -> list[httpx.Response]:
    """Hold the row the service locks, start every call, observe them wait, then let go."""
    monitor = await psycopg.AsyncConnection.connect(
        database.admin_dsn, dbname=database.name, autocommit=True
    )
    tasks: list[asyncio.Future[httpx.Response]] = []
    try:
        async with tenant_transaction(pool, tenant) as barrier:
            await barrier.execute(lock_sql, (row_id,))
            tasks = [asyncio.ensure_future(call) for call in calls]
            await wait_for_waiters(monitor, len(calls))
            assert not any(task.done() for task in tasks)
        return list(await asyncio.wait_for(asyncio.gather(*tasks), 20))
    finally:
        for task in tasks:
            if not task.done():
                task.cancel()
        await monitor.close()


# L8-17 (decision 69) ----------------------------------------------------------------


async def test_two_racing_accruals_leave_one_commission(
    payments: PaymentWorld,
    world: BookingWorld,
    kit: Kit,
    app_pool: RuntimePool,
    test_database: ProvisionedDatabase,
) -> None:
    plan = await put_plan(payments, world, kit, [{"service_id": None, "percent": "10.00"}])
    assert plan.status_code == 200, plan.text
    booking = await paid_visit(payments, world, app_pool, kit)
    body = commission_body(kit, tips_account_id=str(kit.accounts["2300"]))
    answers = await race(
        app_pool,
        test_database,
        world.a.tenant_id,
        "select 1 from gba.bookings where id = %s for update",
        booking,
        [
            accrue(payments, booking, {**body, "number": "FAKE-C-RACE-1"}, key="l8b2-acc-1"),
            accrue(payments, booking, {**body, "number": "FAKE-C-RACE-2"}, key="l8b2-acc-2"),
        ],
    )
    assert sorted(a.status_code for a in answers) == [200, 409], [a.text for a in answers]
    (refused,) = [a for a in answers if a.status_code == 409]
    assert code(refused) == (409, "VISIT_ALREADY_COMMISSIONED")
    async with tenant_transaction(app_pool, world.a.tenant_id) as conn:
        rows = await (
            await conn.execute(
                "select count(*) from gba.visit_commissions where booking_id = %s", (booking,)
            )
        ).fetchone()
    assert rows == (1,)


async def test_two_racing_redemptions_of_one_unit_leave_one(
    payments: PaymentWorld,
    world: BookingWorld,
    kit: Kit,
    app_pool: RuntimePool,
    test_database: ProvisionedDatabase,
) -> None:
    view = await sell(
        payments,
        kit,
        kind="package",
        price="50.00",
        units=1,
        variant=world.catalog_a.base_variant_id,
    )
    prepaid = UUID(str(view["prepaid_id"]))
    first, _ = await billed_visit(payments, world, app_pool, hour=10)
    second, _ = await billed_visit(payments, world, app_pool, hour=13)
    answers = await race(
        app_pool,
        test_database,
        world.a.tenant_id,
        "select 1 from gba.prepaid_balances where id = %s for update",
        prepaid,
        [
            redeem(payments, first, prepaid, key="l8b2-red-1", number="FAKE-R-RACE-1"),
            redeem(payments, second, prepaid, key="l8b2-red-2", number="FAKE-R-RACE-2"),
        ],
    )
    assert sorted(a.status_code for a in answers) == [200, 409], [a.text for a in answers]
    (refused,) = [a for a in answers if a.status_code == 409]
    assert code(refused) == (409, "PREPAID_EXHAUSTED")
    async with tenant_transaction(app_pool, world.a.tenant_id) as conn:
        rows = await (
            await conn.execute(
                "select count(*) from gba.prepaid_redemptions where prepaid_id = %s", (prepaid,)
            )
        ).fetchone()
        used = await (
            await conn.execute(
                "select used_units from gba.prepaid_balances where id = %s", (prepaid,)
            )
        ).fetchone()
    assert (rows, used) == ((1,), (1,))


# L8-19 (decision 71) ----------------------------------------------------------------


async def _counts(pool: RuntimePool, tenant: UUID) -> tuple[int, ...]:
    async with tenant_transaction(pool, tenant) as conn:
        row = await (
            await conn.execute(
                "select (select count(*) from gba.visit_invoices), "
                "(select count(*) from gba.prepaid_balances), "
                "(select count(*) from gba.prepaid_redemptions), "
                "(select count(*) from gba.financial_documents)"
            )
        ).fetchone()
    assert row is not None
    return tuple(int(n) for n in row)


async def test_without_invoices_billing_and_prepaid_are_not_written(
    payments: PaymentWorld,
    world: BookingWorld,
    kit: Kit,
    app_pool: RuntimePool,
    idp: FakeIdp,
) -> None:
    # Prepared while the module is on: a paid package and an issued visit invoice.
    view = await sell(
        payments,
        kit,
        kind="package",
        price="50.00",
        units=1,
        variant=world.catalog_a.base_variant_id,
    )
    billed, _ = await billed_visit(payments, world, app_pool, hour=13)
    unbilled = await visit(world, app_pool)  # 10:00
    ledger = payments.ledger
    off = [m for m in [*MODULES, "workforce"] if m != "finance_documents"]
    await Config(ledger.client, idp).publish(ledger.user, ledger.business, 3, off)
    before = await _counts(app_pool, world.a.tenant_id)
    assert code(await post(payments, unbilled, bill(payments))) == (409, "MODULE_DISABLED")
    documents = payments.settlements.invoices
    sold = await ledger.client.post(
        f"{salon(payments)}/prepaid",
        json={
            "kind": "certificate",
            "counterparty_id": str(documents.party),
            "price": "20.00",
            "currency": "USD",
            "book_id": str(documents.ledger.book),
            "control_account_id": str(documents.control),
            "prepayment_account_id": str(kit.accounts["2100"]),
            "invoice_date": "2026-10-01",
            "number": "FAKE-P-OFF",
        },
        headers=ledger.headers(),
    )
    assert code(sold) == (409, "MODULE_DISABLED")
    assert code(await redeem(payments, billed, view["prepaid_id"])) == (409, "MODULE_DISABLED")
    assert await _counts(app_pool, world.a.tenant_id) == before
