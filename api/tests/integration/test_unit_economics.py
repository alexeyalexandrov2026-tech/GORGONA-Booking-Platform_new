"""Live Unit Economics (GET /growth/unit-economics) against real PostgreSQL 18.

Revenue is read from CONFIRMED bookings that started inside the trailing 30 days; material cost
is read from stock write-offs posted inside the same window. The route needs company-wide
finance access, and no business ever sees another business's figures.
"""

import datetime as dt
from uuid import uuid7
from zoneinfo import ZoneInfo

import psycopg
import pytest

from gorgona_booking.db.provisioning import add_membership, owner_tenant_transaction
from tests.integration import test_stock as shared
from tests.integration.booking_support import BookingWorld
from tests.integration.seed import seed_user
from tests.integration.test_inventory import Inventory
from tests.integration.test_stock import Stock
from tests.integration.test_stock_returns import back, giving_back, receipt_of
from tests.integration.test_stock_write_offs import write_off

pytestmark = pytest.mark.anyio
stock = shared.stock
inventory = shared.inventory
accepted = shared.accepted
client = shared.client
idp = shared.idp
manager_a = shared.manager_a

EMPTY = {
    "window_days": 30,
    "currency": "USD",
    "bookings_count_30d": 0,
    "gross_revenue_cents": 0,
    "average_ticket_cents": 0,
    "material_cogs_cents": 0,
    "net_margin_cents": 0,
    "margin_percent": 0.0,
}


def book(
    conn: psycopg.Connection,
    world: BookingWorld,
    *,
    days_from_now: int,
    total_cents: int,
    status: str = "CONFIRMED",
) -> None:
    """One booking of business A written by the owner role (FAKE data, no allocations needed)."""
    tenant = world.a.tenant_id
    starts = dt.datetime.now(dt.UTC) + dt.timedelta(days=days_from_now)
    hold_expires = dt.datetime.now(dt.UTC) + dt.timedelta(minutes=10) if status == "HOLD" else None
    with owner_tenant_transaction(conn, tenant):
        row = conn.execute(
            "insert into gba.bookings (tenant_id,location_id,variant_id,status,starts_at,ends_at,"
            "hold_expires_at,total_cents,currency,quote,created_by) "
            "values (%s,%s,%s,%s,%s,%s,%s,%s,'USD','{}','test:unit-economics') returning id",
            (
                tenant,
                world.a.location_id,
                world.catalog_a.base_variant_id,
                "HOLD" if status == "HOLD" else "CONFIRMED",
                starts,
                starts + dt.timedelta(hours=1),
                hold_expires,
                total_cents,
            ),
        ).fetchone()
        assert row is not None
        if status == "CANCELLED":
            conn.execute(
                "update gba.bookings set status = 'CANCELLED' where tenant_id = %s and id = %s",
                (tenant, row[0]),
            )


async def test_unit_economics_reads_live_revenue_and_material_cost_for_finance_members(
    stock: Stock,
) -> None:
    inv = stock.inventory
    url = f"/v1/businesses/{stock.tenant}/growth/unit-economics"

    # 1. Nothing booked and nothing consumed: every figure is zero, in USD.
    empty = await inv.client.get(url, headers=inv.headers)
    assert empty.status_code == 200, empty.text
    assert empty.json() == EMPTY

    # 2. Only CONFIRMED bookings that started in the last 30 days are revenue.
    book(inv.owner_conn, inv.world, days_from_now=-2, total_cents=8_000)
    book(inv.owner_conn, inv.world, days_from_now=-29, total_cents=12_000)
    book(inv.owner_conn, inv.world, days_from_now=-45, total_cents=5_000)  # before the window
    book(inv.owner_conn, inv.world, days_from_now=3, total_cents=7_000)  # not earned yet
    book(inv.owner_conn, inv.world, days_from_now=-1, total_cents=9_000, status="HOLD")
    book(inv.owner_conn, inv.world, days_from_now=-1, total_cents=6_000, status="CANCELLED")
    revenue_only = await inv.client.get(url, headers=inv.headers)
    assert revenue_only.status_code == 200, revenue_only.text
    assert revenue_only.json() == {
        "window_days": 30,
        "currency": "USD",
        "bookings_count_30d": 2,
        "gross_revenue_cents": 20_000,
        "average_ticket_cents": 10_000,
        "material_cogs_cents": 0,
        "net_margin_cents": 20_000,
        "margin_percent": 100.0,
    }

    # 3. Material cost: 10.0 ml bought for 10.00; 4.0 ml used (4.00) and 1.0 ml damaged (1.00)
    #    yesterday leave at the moving average. A return to the supplier moves 2.0 ml out as
    #    well, but it is not a cost, and a write-off 45 days ago is outside the window.
    assert (await stock.set_rules()).status_code == 200
    dye = (await inv.item(code="DYE", unit="ml", quantity_scale=1))["item_id"]
    source = await receipt_of(stock, dye, "10.0", "10.00")
    today = dt.datetime.now(ZoneInfo("America/New_York")).date()
    yesterday = (today - dt.timedelta(days=1)).isoformat()
    long_ago = (today - dt.timedelta(days=45)).isoformat()
    for response in (
        await stock.post(
            write_off(stock, [{"item_id": dye, "quantity": "4.0"}], document_date=yesterday)
        ),
        await stock.post(
            write_off(
                stock,
                [{"item_id": dye, "quantity": "1.0"}],
                reason="damaged",
                document_date=yesterday,
            )
        ),
        await stock.post(giving_back(stock, source, [back(1, "2.0")], document_date=yesterday)),
        await stock.post(
            write_off(
                stock,
                [{"item_id": dye, "quantity": "1.0"}],
                reason="other",
                document_date=long_ago,
            )
        ),
    ):
        assert response.status_code == 200, response.text
    # The premise of the exclusion: the supplier return really is an outbound valuation.
    (returned,) = stock.rows(
        "select count(*), coalesce(sum(v.amount_minor), 0) from gba.stock_valuations v "
        "join gba.stock_documents d on d.tenant_id = v.tenant_id and d.id = v.document_id "
        "where d.kind = 'return' and v.direction = 'out'"
    )
    assert returned[0] == 1
    assert int(str(returned[1])) > 0

    live = await inv.client.get(url, headers=inv.headers)
    assert live.status_code == 200, live.text
    assert live.json() == {
        "window_days": 30,
        "currency": "USD",
        "bookings_count_30d": 2,
        "gross_revenue_cents": 20_000,
        "average_ticket_cents": 10_000,
        "material_cogs_cents": 500,
        "net_margin_cents": 19_500,
        "margin_percent": 97.5,
    }
    alias = await inv.client.get(
        f"/v1/salons/{stock.tenant}/growth/unit-economics", headers=inv.headers
    )
    assert alias.status_code == 200
    assert alias.json() == live.json()


async def test_unit_economics_needs_finance_access_and_never_crosses_businesses(
    inventory: Inventory,
) -> None:
    inv = inventory
    url = f"/v1/businesses/{inv.tenant}/growth/unit-economics"
    book(inv.owner_conn, inv.world, days_from_now=-2, total_cents=8_000)

    # A signed-in caller is required.
    assert (await inv.client.get(url)).status_code == 401

    # Cost amounts are finance data: company-wide front desk staff may read the growth
    # settings of their business (business.read) but not its margin (finance.read).
    _, front_desk = inv.member("front_desk")
    settings = await inv.client.get(
        f"/v1/businesses/{inv.tenant}/growth/settings", headers=front_desk
    )
    assert settings.status_code == 200, settings.text
    assert (await inv.client.get(url, headers=front_desk)).status_code == 403
    # A location-limited manager cannot see company-wide amounts either.
    _, branch_manager = inv.member("manager", inv.world.a.location_id)
    assert (await inv.client.get(url, headers=branch_manager)).status_code == 403
    # A company-wide manager can.
    _, manager = inv.member("manager")
    allowed = await inv.client.get(url, headers=manager)
    assert allowed.status_code == 200, allowed.text
    assert allowed.json()["bookings_count_30d"] == 1
    assert allowed.json()["gross_revenue_cents"] == 8_000

    # The owner of business B can neither read A's figures nor see them in their own.
    user_b = seed_user(inv.owner_conn, f"unit-economics-owner-b-{uuid7().hex[:6]}")
    add_membership(
        inv.owner_conn, tenant_id=inv.world.b.tenant_id, user_id=user_b.user_id, role="owner"
    )
    headers_b = inv.idp.bearer(user_b.subject, email=user_b.email)
    assert (await inv.client.get(url, headers=headers_b)).status_code == 403
    own = await inv.client.get(
        f"/v1/businesses/{inv.world.b.tenant_id}/growth/unit-economics", headers=headers_b
    )
    assert own.status_code == 200, own.text
    assert own.json() == EMPTY
