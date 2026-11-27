"""Unit tests for AMARKAL v2.10.0 Deal-to-Cash B2B Engine."""

from __future__ import annotations

import httpx
import pytest
from fastapi import FastAPI

from gorgona_booking.api import connectors as connectors_api
from gorgona_booking.business.commercial import (
    QuoteLineInput,
    calculate_quote_totals,
    evaluate_approval_requirement,
    evaluate_three_way_match,
    generate_portal_token,
    hash_portal_token,
)
from gorgona_booking.connectors.service import ALLOWED_WEBHOOK_EVENTS

pytestmark = pytest.mark.anyio


def test_calculate_quote_totals_exact_integer_usd_cents() -> None:
    lines, subtotal, discount, tax, total = calculate_quote_totals(
        [
            QuoteLineInput(
                description="Dedicated Linehaul Freight",
                sku="FRT-500",
                quantity=2,
                unit_price_cents=125_000,
            ),
            QuoteLineInput(
                description="Liftgate Delivery",
                quantity=1,
                unit_price_cents=15_000,
            ),
        ],
        discount_cents=15_000,
        tax_rate_bps=825,
    )
    assert len(lines) == 2
    assert lines[0].line_total_cents == 250_000
    assert subtotal == 265_000
    assert discount == 15_000
    # Taxable = 250,000; 8.25% = 20,625 cents
    assert tax == 20_625
    assert total == 270_625


def test_evaluate_approval_requirement_respects_threshold_and_auto_approve() -> None:
    assert (
        evaluate_approval_requirement(
            100_000, threshold_cents=250_000, auto_approve_below_threshold=True
        )
        is False
    )
    assert (
        evaluate_approval_requirement(
            250_001, threshold_cents=250_000, auto_approve_below_threshold=True
        )
        is True
    )
    assert (
        evaluate_approval_requirement(
            50_000, threshold_cents=250_000, auto_approve_below_threshold=False
        )
        is True
    )


def test_evaluate_three_way_match_detects_matched_variance_and_unmatched() -> None:
    assert evaluate_three_way_match(
        po_total_cents=500_000, received_total_cents=500_000, vendor_bill_cents=None
    ) == ("unmatched", 0)

    # Exact match within $1 tolerance
    status_ok, var_ok = evaluate_three_way_match(
        po_total_cents=500_000, received_total_cents=500_000, vendor_bill_cents=500_050
    )
    assert status_ok == "matched"
    assert var_ok == 50

    # Vendor overbilled by $120 vs received goods
    status_var, var_cents = evaluate_three_way_match(
        po_total_cents=500_000, received_total_cents=450_000, vendor_bill_cents=462_000
    )
    assert status_var == "variance"
    assert var_cents == 12_000

    # Bill arrived before goods receipt -> variance until received
    status_early, _ = evaluate_three_way_match(
        po_total_cents=500_000, received_total_cents=0, vendor_bill_cents=500_000
    )
    assert status_early == "variance"


def test_portal_token_generation_and_deterministic_sha256_hash() -> None:
    raw, prefix, digest = generate_portal_token()
    assert raw.startswith("amk_ptl_")
    assert raw.startswith(prefix)
    assert len(digest) == 64
    assert hash_portal_token(raw) == digest
    assert hash_portal_token(raw + "x") != digest


async def test_v210_webhook_events_and_a2a_agent_card_capabilities() -> None:
    assert {
        "quote.created",
        "quote.accepted",
        "purchase_order.issued",
        "purchase_order.matched",
    } <= (ALLOWED_WEBHOOK_EVENTS)
    app = FastAPI()
    app.include_router(connectors_api.router)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        res = await client.get("/.well-known/agent.json")
    assert res.status_code == 200
    caps = res.json()["capabilities"]
    assert "list_commercial_quotes" in caps
    assert "list_purchase_orders" in caps
    assert len(caps) == 11
