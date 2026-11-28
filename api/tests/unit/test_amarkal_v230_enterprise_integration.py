"""Unit tests for AMARKAL v2.30.0 Cross-Module Enterprise Integration."""

from __future__ import annotations

from typing import get_args

from gorgona_booking.ai_assistant.autonomy import compute_predictive_health_and_signals
from gorgona_booking.ai_assistant.service import build_enterprise_copilot_insights
from gorgona_booking.api.search import SearchHitKind


def test_global_search_covers_all_16_enterprise_record_kinds() -> None:
    kinds = set(get_args(SearchHitKind))
    assert len(kinds) == 16
    assert {
        "bank_transaction",
        "holding_subsidiary",
        "intercompany_tx",
        "marketplace_plugin",
    }.issubset(kinds)


def test_copilot_insights_surface_bank_feeds_and_intercompany_actions() -> None:
    insights = build_enterprise_copilot_insights(
        {
            "bank_unreconciled_count": 12,
            "bank_suggested_count": 7,
            "intercompany_uneliminated_count": 2,
            "intercompany_uneliminated_cents": 4_905_000,
        }
    )
    by_cat = {i.category: i for i in insights}
    assert "bank_reconciliation" in by_cat
    assert by_cat["bank_reconciliation"].priority == "high"
    assert by_cat["bank_reconciliation"].action_path == "/banking/"
    assert "7 auto-match ready" in by_cat["bank_reconciliation"].title

    assert "holding_consolidation" in by_cat
    assert by_cat["holding_consolidation"].action_path == "/holding/"
    assert "$49,050.00" in by_cat["holding_consolidation"].title


def test_predictive_cfo_signals_include_bank_feeds_and_holding_eliminations() -> None:
    score, headline, signals = compute_predictive_health_and_signals(
        business_name="Alexey AAA Holdings LLC",
        period_days=30,
        ar_total_cents=0,
        ar_overdue_cents=0,
        top_overdue_counterparty=None,
        po_variance_count=0,
        po_variance_cents=0,
        top_variance_vendor=None,
        quotes_sent_count=0,
        quotes_accepted_count=0,
        stale_quotes_count=0,
        stripe_open_count=0,
        stripe_open_cents=0,
        stripe_paid_cents=500_000,
        bookings_confirmed_count=0,
        bookings_cancelled_count=0,
        waitlist_count=0,
        waitlist_value_cents=0,
        failed_notifications_count=0,
        bank_unreconciled_count=11,
        bank_suggested_count=5,
        intercompany_uneliminated_count=1,
        intercompany_uneliminated_cents=3_815_000,
    )
    assert score == 92 - 8 - 6
    assert "Alexey AAA Holdings LLC" in headline
    by_cat = {s.category: s for s in signals}
    assert by_cat["bank_reconciliation"].severity == "high"
    assert by_cat["bank_reconciliation"].action_path == "/banking/"
    assert by_cat["holding_consolidation"].action_path == "/holding/"
    assert "$38,150.00" in by_cat["holding_consolidation"].title
