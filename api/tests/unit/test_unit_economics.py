"""Live Unit Economics: margin arithmetic, SQL contract and HTTP contract (no database).

The database path (real bookings, stock write-offs, RLS and roles) is covered by
`tests/integration/test_growth_and_ai_assistant.py`; here the money arithmetic is checked in
whole cents, the two SQL statements are checked for their tenant filter and window, and the
route is checked with the authorization and the service replaced by stubs.
"""

import math
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from decimal import Decimal
from types import SimpleNamespace
from typing import Any, Self, cast
from uuid import UUID, uuid4

import httpx
import pytest
from fastapi import FastAPI
from psycopg import AsyncConnection

from gorgona_booking.api import growth as growth_api
from gorgona_booking.api.app import create_app
from gorgona_booking.api.deps import get_principal
from gorgona_booking.auth.permissions import Permission
from gorgona_booking.auth.principal import Principal
from gorgona_booking.config import Settings
from gorgona_booking.growth.service import (
    UNIT_ECONOMICS_WINDOW_DAYS,
    UnitEconomicsRecord,
    build_unit_economics,
    get_unit_economics,
)
from tests.support.fake_idp import FakeIdp

pytestmark = pytest.mark.anyio

TENANT = uuid4()
RESPONSE_FIELDS = {
    "window_days",
    "currency",
    "bookings_count_30d",
    "gross_revenue_cents",
    "average_ticket_cents",
    "material_cogs_cents",
    "net_margin_cents",
    "margin_percent",
}


def _economics(
    *, count: int, gross: int, cogs: int, tenant_id: UUID = TENANT
) -> UnitEconomicsRecord:
    return build_unit_economics(
        tenant_id=tenant_id,
        bookings_count=count,
        gross_revenue_cents=gross,
        material_cogs_cents=cogs,
    )


# --- arithmetic ---------------------------------------------------------------------------


def test_no_bookings_and_no_cost_is_all_zero_in_usd() -> None:
    rec = _economics(count=0, gross=0, cogs=0)
    assert rec.currency == "USD"
    assert rec.window_days == UNIT_ECONOMICS_WINDOW_DAYS == 30
    assert (rec.bookings_count_30d, rec.gross_revenue_cents, rec.material_cogs_cents) == (0, 0, 0)
    assert rec.net_margin_cents == 0
    assert rec.margin_percent == 0.0
    assert rec.average_ticket_cents == 0


def test_margin_is_gross_minus_material_cost() -> None:
    rec = _economics(count=40, gross=1_000_000, cogs=250_000)
    assert rec.net_margin_cents == 750_000
    assert rec.margin_percent == 75.0
    assert rec.average_ticket_cents == 25_000


def test_percent_has_one_decimal_and_rounds_half_up_not_to_even() -> None:
    # 20_000 / 30_000 = 66.666...
    assert _economics(count=1, gross=30_000, cogs=10_000).margin_percent == 66.7
    # 980 / 8_000 = 12.25 exactly: half up gives 12.3 (float round() would give 12.2).
    assert _economics(count=1, gross=8_000, cogs=7_020).margin_percent == 12.3


def test_average_ticket_is_whole_cents_rounded_half_up() -> None:
    assert _economics(count=7, gross=30_000, cogs=0).average_ticket_cents == 4_286  # 4285.71
    assert _economics(count=3, gross=10_000, cogs=0).average_ticket_cents == 3_333  # 3333.33
    assert _economics(count=2, gross=5, cogs=0).average_ticket_cents == 3  # 2.5
    assert _economics(count=3, gross=0, cogs=0).average_ticket_cents == 0  # only free bookings


def test_cost_above_revenue_is_a_real_negative_margin() -> None:
    rec = _economics(count=2, gross=10_000, cogs=12_500)
    assert rec.net_margin_cents == -2_500
    assert rec.margin_percent == -25.0


def test_zero_revenue_with_cost_reports_zero_percent_and_a_negative_net() -> None:
    rec = _economics(count=0, gross=0, cogs=4_200)
    assert rec.net_margin_cents == -4_200
    assert rec.margin_percent == 0.0
    assert rec.average_ticket_cents == 0


def test_a_margin_that_rounds_to_negative_zero_is_plain_zero() -> None:
    rec = _economics(count=1, gross=10_000, cogs=10_001)  # -0.01 %
    assert rec.net_margin_cents == -1
    assert rec.margin_percent == 0.0
    assert math.copysign(1.0, rec.margin_percent) == 1.0


# --- SQL contract -------------------------------------------------------------------------


class _FakeCursor:
    def __init__(self, rows: list[dict[str, Any]]) -> None:
        self._rows = list(rows)
        self.executed: list[tuple[str, tuple[Any, ...]]] = []

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(self, *exc: object) -> None:
        return None

    async def execute(self, sql: str, params: tuple[Any, ...]) -> None:
        self.executed.append((" ".join(sql.split()), params))

    async def fetchone(self) -> dict[str, Any] | None:
        return self._rows.pop(0) if self._rows else None


class _FakeConnection:
    def __init__(self, rows: list[dict[str, Any]]) -> None:
        self.cursor_ = _FakeCursor(rows)

    def cursor(self, **_: Any) -> _FakeCursor:
        return self.cursor_


async def test_live_query_filters_by_tenant_and_window_and_reads_whole_cents() -> None:
    # SUM(bigint) is numeric in PostgreSQL, so the cost arrives as a Decimal.
    fake = _FakeConnection(
        [
            {"bookings_count": 12, "gross_revenue_cents": 96_000},
            {"material_cogs_cents": Decimal("21_600")},
        ]
    )
    rec = await get_unit_economics(cast("AsyncConnection[Any]", fake), tenant_id=TENANT)

    assert rec == UnitEconomicsRecord(
        tenant_id=TENANT,
        window_days=30,
        currency="USD",
        bookings_count_30d=12,
        gross_revenue_cents=96_000,
        average_ticket_cents=8_000,
        material_cogs_cents=21_600,
        net_margin_cents=74_400,
        margin_percent=77.5,
    )
    assert isinstance(rec.material_cogs_cents, int)

    (bookings_sql, bookings_params), (stock_sql, stock_params) = fake.cursor_.executed
    # Explicit tenant filter on every statement (FORCE RLS is the second line of defence).
    assert bookings_params == (TENANT, 30)
    assert stock_params == (TENANT, 30)
    assert "FROM gba.bookings WHERE tenant_id = %s" in bookings_sql
    assert "status = 'CONFIRMED'" in bookings_sql
    assert "sum(total_cents)" in bookings_sql
    # A closed window: an upcoming booking is not earned yet, so it is not revenue.
    assert "starts_at >= now() - (%s::int * interval '1 day')" in bookings_sql
    assert "starts_at < now()" in bookings_sql
    assert "FROM gba.stock_valuations v JOIN gba.stock_documents d" in stock_sql
    assert "ON d.tenant_id = v.tenant_id AND d.id = v.document_id" in stock_sql
    assert "WHERE v.tenant_id = %s" in stock_sql
    assert "sum(v.amount_minor)" in stock_sql
    assert "v.direction = 'out'" in stock_sql
    # A return to the supplier moves stock out as well, but it is not a material cost.
    assert "d.kind = 'write_off'" in stock_sql
    assert "d.document_date >= current_date - %s::int" in stock_sql


async def test_an_unreadable_aggregate_is_an_error_not_a_zero() -> None:
    fake = _FakeConnection([{"bookings_count": 0, "gross_revenue_cents": 0}])
    with pytest.raises(RuntimeError, match="Failed to read unit economics"):
        await get_unit_economics(cast("AsyncConnection[Any]", fake), tenant_id=TENANT)


# --- HTTP contract ------------------------------------------------------------------------


def _client(app: FastAPI) -> httpx.AsyncClient:
    transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
    return httpx.AsyncClient(transport=transport, base_url="http://testserver")


async def test_route_serves_both_aliases_behind_finance_access_and_never_cached(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    principal = Principal(user_id=uuid4(), display_name="Test Owner", platform_roles=frozenset())
    connection = object()
    seen: list[dict[str, Any]] = []

    @asynccontextmanager
    async def fake_authorized_tenant(
        pool: object,
        who: Principal,
        salon_id: UUID,
        permission: Permission,
        **kwargs: Any,
    ) -> AsyncIterator[SimpleNamespace]:
        seen.append({"who": who, "salon_id": salon_id, "permission": permission, **kwargs})
        yield SimpleNamespace(conn=connection)

    async def fake_get_unit_economics(conn: object, *, tenant_id: UUID) -> UnitEconomicsRecord:
        seen.append({"conn": conn, "tenant_id": tenant_id})
        return _economics(count=40, gross=1_000_000, cogs=250_000, tenant_id=tenant_id)

    monkeypatch.setattr(growth_api, "runtime_pool", lambda request: object())
    monkeypatch.setattr(growth_api, "authorized_tenant", fake_authorized_tenant)
    monkeypatch.setattr(growth_api, "get_unit_economics", fake_get_unit_economics)
    app = create_app(Settings())
    app.dependency_overrides[get_principal] = lambda: principal

    async with _client(app) as client:
        responses = [
            await client.get(f"/v1/{prefix}/{TENANT}/growth/unit-economics")
            for prefix in ("businesses", "salons")
        ]

    for response in responses:
        assert response.status_code == 200, response.text
        # The framing middleware keeps every /v1/ response out of shared caches.
        assert "no-store" in response.headers["cache-control"]
        assert response.json() == {
            "window_days": 30,
            "currency": "USD",
            "bookings_count_30d": 40,
            "gross_revenue_cents": 1_000_000,
            "average_ticket_cents": 25_000,
            "material_cogs_cents": 250_000,
            "net_margin_cents": 750_000,
            "margin_percent": 75.0,
        }
    # Cost amounts come from stock valuations, which the stock API gates at FINANCE_READ.
    guards = [entry for entry in seen if "permission" in entry]
    assert len(guards) == 2
    for guard in guards:
        assert guard["permission"] is Permission.FINANCE_READ
        assert guard["who"] is principal
        assert guard["salon_id"] == TENANT
    reads = [entry for entry in seen if "conn" in entry]
    assert [(entry["conn"], entry["tenant_id"]) for entry in reads] == [(connection, TENANT)] * 2


async def test_route_requires_authentication() -> None:
    app = create_app(Settings(environment="test"), token_verifier=FakeIdp().verifier())
    async with _client(app) as client:
        response = await client.get(f"/v1/businesses/{TENANT}/growth/unit-economics")
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "AUTHENTICATION_REQUIRED"


def test_openapi_documents_both_aliases_and_the_usd_only_contract() -> None:
    spec = create_app(Settings()).openapi()
    for prefix in ("businesses", "salons"):
        operation = spec["paths"][f"/v1/{prefix}/{{salon_id}}/growth/unit-economics"]["get"]
        schema = operation["responses"]["200"]["content"]["application/json"]["schema"]
        assert schema["$ref"].endswith("/UnitEconomicsResponse")
    model = spec["components"]["schemas"]["UnitEconomicsResponse"]
    assert set(model["properties"]) == RESPONSE_FIELDS
    assert set(model["required"]) == RESPONSE_FIELDS
    currency = model["properties"]["currency"]
    assert currency.get("const") == "USD" or currency.get("enum") == ["USD"]
