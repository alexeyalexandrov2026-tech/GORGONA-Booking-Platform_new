"""L8b1: review fixes R11, R13 and R14 in the finance world (package L, BEAUTY-01; FAKE data only).

Design docs/plan/PACKAGE_L8_DESIGN_2026-10-23.md decisions 64, 66 and 67.
"""

import asyncio
from datetime import UTC, datetime, timedelta
from uuid import uuid7

import httpx
import psycopg
import pytest

from gorgona_booking.booking.models import ReservationRequest
from gorgona_booking.booking.service import BookingService
from gorgona_booking.db.pool import RuntimePool, tenant_transaction
from tests.integration import test_l6_prepaid as shared
from tests.integration.booking_support import BookingWorld
from tests.integration.conftest import ProvisionedDatabase
from tests.integration.test_external_payments import PaymentWorld
from tests.integration.test_l5_commissions import (
    Kit,
    accrue,
    commission_body,
    make_kit,
    paid_visit,
    plan_path,
    put_plan,
)
from tests.integration.test_l6_prepaid import code, salon

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


# L8-12 (R11) ------------------------------------------------------------------------


async def test_without_workforce_commissions_are_not_written(
    payments: PaymentWorld, world: BookingWorld, app_pool: RuntimePool
) -> None:
    bare = await make_kit(payments, app_pool)  # workforce stays off in this business
    saved = await put_plan(payments, world, bare, [{"service_id": None, "percent": "10.00"}])
    assert code(saved) == (409, "MODULE_DISABLED")
    # Reads continue when a module is off: the plan is simply not there.
    read = await payments.ledger.client.get(
        plan_path(payments, world), headers=payments.ledger.headers()
    )
    assert read.status_code == 404, read.text
    assert read.json()["error"]["code"] != "MODULE_DISABLED"
    booking = await paid_visit(payments, world, app_pool, bare)
    assert code(await accrue(payments, booking, commission_body(bare))) == (409, "MODULE_DISABLED")
    async with tenant_transaction(app_pool, world.a.tenant_id) as conn:
        rows = await (await conn.execute("select count(*) from gba.visit_commissions")).fetchone()
    assert rows == (0,)


async def test_an_empty_consumption_still_needs_inventory(
    payments: PaymentWorld, world: BookingWorld, app_pool: RuntimePool
) -> None:
    # This business has no inventory module and the visit uses no material at all.
    start = datetime.now(UTC).replace(second=0, microsecond=0) - timedelta(hours=3)
    booking = (
        await BookingService(app_pool).create_confirmed_booking(
            world.a.tenant_id,
            ReservationRequest(
                resource_id=world.artist_a1,
                variant_id=world.catalog_a.base_variant_id,
                starts_at=start,
            ),
            actor="test:l8b1",
            idempotency_key=None,
        )
    ).booking_id
    base = f"{salon(payments)}/bookings/{booking}"
    done = await payments.ledger.client.post(
        f"{base}/complete", json={}, headers=payments.ledger.headers()
    )
    assert done.status_code == 200, done.text
    posted = await payments.ledger.client.post(
        f"{base}/consumption",
        json={
            "legal_entity_id": str(uuid7()),
            "place_id": str(uuid7()),
            "document_date": start.date().isoformat(),
        },
        headers=payments.ledger.headers(),
    )
    assert code(posted) == (409, "MODULE_DISABLED")
    async with tenant_transaction(app_pool, world.a.tenant_id) as conn:
        row = await (
            await conn.execute(
                "select consumption_posted_at from gba.visit_completions where booking_id = %s",
                (booking,),
            )
        ).fetchone()
    assert row == (None,)


# L8-14 (R13) ------------------------------------------------------------------------


async def test_a_plan_with_an_unknown_payee_or_service_is_refused(
    payments: PaymentWorld, world: BookingWorld, kit: Kit
) -> None:
    stranger = Kit(uuid7(), kit.accounts)
    unknown_payee = await put_plan(
        payments, world, stranger, [{"service_id": None, "amount": "4.00"}]
    )
    assert code(unknown_payee) == (422, "INVALID_REFERENCE")
    unknown_service = await put_plan(
        payments, world, kit, [{"service_id": str(uuid7()), "percent": "10.00"}]
    )
    assert code(unknown_service) == (422, "INVALID_REFERENCE")


async def _wait_for_row_waiter(monitor: psycopg.AsyncConnection) -> None:
    deadline = asyncio.get_running_loop().time() + 8
    while asyncio.get_running_loop().time() < deadline:
        row = await (
            await monitor.execute(
                "select count(*) from pg_locks where locktype = 'transactionid' and not granted"
            )
        ).fetchone()
        if row is not None and row[0] >= 1:
            return
        await asyncio.sleep(0.01)
    pytest.fail("L8-14: no observed waiting transaction lock in pg_locks")


async def test_two_first_plan_saves_leave_one_plan_and_one_conflict(
    payments: PaymentWorld,
    world: BookingWorld,
    kit: Kit,
    app_pool: RuntimePool,
    test_database: ProvisionedDatabase,
) -> None:
    monitor = await psycopg.AsyncConnection.connect(
        test_database.admin_dsn, dbname=test_database.name, autocommit=True
    )
    task: asyncio.Task[httpx.Response] | None = None
    try:
        async with tenant_transaction(app_pool, world.a.tenant_id) as barrier:
            # The first save is in flight and not committed: the second waits on its row.
            await barrier.execute(
                "insert into gba.commission_plans (tenant_id, resource_id, counterparty_id, "
                "currency, revision, updated_by) values (%s, %s, %s, 'USD', 1, %s)",
                (world.a.tenant_id, world.artist_a1, kit.payee, payments.ledger.user.user_id),
            )
            task = asyncio.create_task(
                put_plan(payments, world, kit, [{"service_id": None, "percent": "10.00"}])
            )
            await _wait_for_row_waiter(monitor)
            assert not task.done()
        second = await asyncio.wait_for(task, 15)
        assert code(second) == (409, "COMMISSION_PLAN_REVISION_CONFLICT")
    finally:
        if task is not None and not task.done():
            task.cancel()
        await monitor.close()
    async with tenant_transaction(app_pool, world.a.tenant_id) as conn:
        plans = await (
            await conn.execute(
                "select revision from gba.commission_plans where resource_id = %s",
                (world.artist_a1,),
            )
        ).fetchall()
    assert plans == [(1,)]


# L8-15 (R14) ------------------------------------------------------------------------


async def test_a_package_is_sold_in_its_services_currency(
    payments: PaymentWorld, world: BookingWorld, kit: Kit
) -> None:
    documents = payments.settlements.invoices
    sold = await payments.ledger.client.post(
        f"{salon(payments)}/prepaid",
        json={
            "kind": "package",
            "counterparty_id": str(documents.party),
            "price": "90.00",
            "currency": "EUR",
            "units": 3,
            "variant_id": str(world.catalog_a.base_variant_id),
            "book_id": str(documents.ledger.book),
            "control_account_id": str(documents.control),
            "prepayment_account_id": str(kit.accounts["2100"]),
            "invoice_date": "2026-10-01",
            "number": f"FAKE-P-{uuid7().hex[-6:]}",
        },
        headers=payments.ledger.headers(),
    )
    assert code(sold) == (422, "PREPAID_CURRENCY_MISMATCH")
