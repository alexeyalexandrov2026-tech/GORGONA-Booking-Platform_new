"""L8c: direct SQL refusals and company scope of the commission and prepaid tables (L-09).

Design docs/plan/PACKAGE_L8_DESIGN_2026-10-23.md decision 73; FAKE data only. L3 and L4 prove
the same for their tables.
"""

from uuid import UUID

import psycopg
import pytest

from gorgona_booking.db.pool import RuntimePool, tenant_transaction
from tests.integration import test_l6_prepaid as shared
from tests.integration.booking_support import BookingWorld
from tests.integration.test_external_payments import PaymentWorld
from tests.integration.test_l5_commissions import (
    Kit,
    accrue,
    commission_body,
    paid_visit,
    put_plan,
)
from tests.integration.test_l6_prepaid import billed_visit, redeem, sell

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


async def refused(
    pool: RuntimePool,
    tenant: UUID,
    statement: str,
    args: tuple[object, ...],
    error: type[psycopg.Error],
) -> None:
    with pytest.raises(error):
        async with tenant_transaction(pool, tenant) as conn:
            await conn.execute(statement, args)


async def seen_by(pool: RuntimePool, tenant: UUID, statement: str, args: tuple[object, ...]) -> int:
    async with tenant_transaction(pool, tenant) as conn:
        row = await (await conn.execute(statement, args)).fetchone()
    assert row is not None
    return int(row[0])


async def test_commissions_and_plans_are_permanent_and_company_scoped(
    payments: PaymentWorld, world: BookingWorld, kit: Kit, app_pool: RuntimePool
) -> None:
    plan = await put_plan(payments, world, kit, [{"service_id": None, "percent": "10.00"}])
    assert plan.status_code == 200, plan.text
    booking = await paid_visit(payments, world, app_pool, kit)
    body = commission_body(kit, tips_account_id=str(kit.accounts["2300"]))
    accrued = await accrue(payments, booking, body)
    assert accrued.status_code == 200, accrued.text
    tenant, artist = world.a.tenant_id, world.artist_a1
    for statement, args in (
        ("update gba.visit_commissions set tips_minor = 0 where booking_id = %s", (booking,)),
        ("delete from gba.visit_commissions where booking_id = %s", (booking,)),
        ("update gba.commission_rules set percent_bp = 0 where resource_id = %s", (artist,)),
        ("delete from gba.commission_plans where resource_id = %s", (artist,)),
    ):
        await refused(app_pool, tenant, statement, args, psycopg.errors.InsufficientPrivilege)
    other = world.b.tenant_id
    for statement, args in (
        ("select count(*) from gba.visit_commissions where booking_id = %s", (booking,)),
        ("select count(*) from gba.commission_plans where resource_id = %s", (artist,)),
        ("select count(*) from gba.commission_rules where resource_id = %s", (artist,)),
    ):
        assert await seen_by(app_pool, tenant, statement, args) >= 1
        assert await seen_by(app_pool, other, statement, args) == 0


async def test_prepaid_sales_and_redemptions_are_permanent_and_company_scoped(
    payments: PaymentWorld, world: BookingWorld, kit: Kit, app_pool: RuntimePool
) -> None:
    view = await sell(
        payments,
        kit,
        kind="package",
        price="100.00",
        units=2,
        variant=world.catalog_a.base_variant_id,
    )
    prepaid = UUID(str(view["prepaid_id"]))
    booking, _ = await billed_visit(payments, world, app_pool, hour=10)
    redeemed = await redeem(payments, booking, prepaid)
    assert redeemed.status_code == 200, redeemed.text
    tenant = world.a.tenant_id
    for statement, args, error in (
        # The sale itself is never rewritten.
        (
            "update gba.prepaid_balances set price_minor = 1 where id = %s",
            (prepaid,),
            psycopg.errors.InsufficientPrivilege,
        ),
        (
            "delete from gba.prepaid_balances where id = %s",
            (prepaid,),
            psycopg.errors.InsufficientPrivilege,
        ),
        (
            "update gba.prepaid_redemptions set amount_minor = 1 where prepaid_id = %s",
            (prepaid,),
            psycopg.errors.InsufficientPrivilege,
        ),
        (
            "delete from gba.prepaid_redemptions where prepaid_id = %s",
            (prepaid,),
            psycopg.errors.InsufficientPrivilege,
        ),
        # What is used never goes back, and never moves without its redemption.
        (
            "update gba.prepaid_balances set used_units = 0, used_minor = 0 where id = %s",
            (prepaid,),
            psycopg.errors.CheckViolation,
        ),
        (
            "update gba.prepaid_balances set used_units = 2, used_minor = 10000 where id = %s",
            (prepaid,),
            psycopg.errors.CheckViolation,
        ),
    ):
        await refused(app_pool, tenant, statement, args, error)
    used = await seen_by(
        app_pool, tenant, "select used_units from gba.prepaid_balances where id = %s", (prepaid,)
    )
    assert used == 1
    other = world.b.tenant_id
    for statement in (
        "select count(*) from gba.prepaid_balances where id = %s",
        "select count(*) from gba.prepaid_redemptions where prepaid_id = %s",
    ):
        assert await seen_by(app_pool, tenant, statement, (prepaid,)) == 1
        assert await seen_by(app_pool, other, statement, (prepaid,)) == 0
