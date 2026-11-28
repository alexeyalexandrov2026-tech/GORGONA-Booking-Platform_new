"""Unit tests for AMARKAL Platform v2.21.0 cross-module search & AI Copilot wiring."""

from __future__ import annotations

import asyncio
from typing import get_args

from gorgona_booking.ai_assistant.service import (
    CopilotContext,
    build_enterprise_copilot_insights,
    synthesize_owner_copilot,
)
from gorgona_booking.api.search import SearchHitKind, escape_like_pattern


def test_global_search_covers_all_twelve_enterprise_entity_kinds() -> None:
    kinds = set(get_args(SearchHitKind))
    expected = {
        "counterparty",
        "document",
        "invoice",
        "service",
        "payment",
        "quote",
        "purchase_order",
        "mrp_material",
        "eam_asset",
        "inbox_thread",
        "payroll_profile",
        "fx_entry",
    }
    assert expected.issubset(kinds)
    assert escape_like_pattern("TRK_104%\\x") == "%TRK\\_104\\%\\\\x%"


def test_enterprise_copilot_insights_emit_all_five_operational_alerts() -> None:
    insights = build_enterprise_copilot_insights(
        {
            "mrp_shortage_runs_count": 2,
            "eam_open_work_orders_count": 3,
            "inbox_unread_threads_count": 4,
            "draft_payroll_runs_count": 1,
            "fx_open_entries_count": 2,
            "fx_unrealized_gain_loss_cents": -14550,
        }
    )
    categories = [item.category for item in insights]
    assert categories == [
        "mrp_supply_chain",
        "predictive_eam",
        "omnichannel_crm",
        "us_payroll",
        "fx_treasury",
    ]
    assert insights[0].priority == "high"
    assert insights[0].action_path == "/industrial/"
    assert insights[1].action_path == "/industrial/"
    assert insights[2].action_path == "/inbox/"
    assert insights[3].action_path == "/global-finance/"
    assert "loss" in insights[4].title
    assert "$-145.50" in insights[4].title


def test_enterprise_copilot_insights_clean_zero_and_positive_fx_gain() -> None:
    assert build_enterprise_copilot_insights({}) == []
    positive = build_enterprise_copilot_insights(
        {
            "fx_open_entries_count": 1,
            "fx_unrealized_gain_loss_cents": 25000,
        }
    )
    assert len(positive) == 1
    assert "gain" in positive[0].title
    assert "$+250.00" in positive[0].title


def test_synthesize_owner_copilot_surfaces_enterprise_priority_grounded() -> None:
    enterprise_insights = build_enterprise_copilot_insights(
        {
            "mrp_shortage_runs_count": 1,
            "eam_open_work_orders_count": 2,
        }
    )
    ctx = CopilotContext(
        business_name="Midwest Heavy Mfg",
        metrics={
            "upcoming_7d_confirmed_bookings": 2,
            "upcoming_7d_booked_value_cents": 40000,
            "stripe_30d_paid_cents": 95000,
            "waiting_waitlist_count": 0,
            "waitlist_recoverable_value_cents": 0,
            "bookable_services_count": 4,
            "active_staff_count": 6,
            "mrp_shortage_runs_count": 1,
            "eam_open_work_orders_count": 2,
        },
        insights=enterprise_insights,
    )
    res = asyncio.run(synthesize_owner_copilot(ctx, question="What needs urgent attention?"))
    assert res.engine == "grounded"
    assert "Midwest Heavy Mfg" in res.reply
    assert len(res.insights) == 2
    assert res.insights[0].action_path == "/industrial/"
