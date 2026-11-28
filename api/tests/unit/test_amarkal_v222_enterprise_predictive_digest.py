"""Unit tests for AMARKAL v2.22.0 Enterprise Predictive Insights & Slack/Webhook Digest."""

from __future__ import annotations

import asyncio
from uuid import uuid4

from gorgona_booking.ai_assistant.autonomy import (
    PredictiveContext,
    build_predictive_webhook_payload,
    compute_predictive_health_and_signals,
    dispatch_predictive_webhook,
)


def test_predictive_health_captures_all_five_enterprise_signals_and_fx_loss() -> None:
    score, headline, signals = compute_predictive_health_and_signals(
        business_name="Midwest Industrial Group",
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
        stripe_paid_cents=450_000,
        bookings_confirmed_count=0,
        bookings_cancelled_count=0,
        waitlist_count=0,
        waitlist_value_cents=0,
        failed_notifications_count=0,
        mrp_shortage_runs_count=2,
        eam_open_work_orders_count=3,
        inbox_unread_threads_count=5,
        draft_payroll_runs_count=1,
        fx_open_entries_count=2,
        fx_unrealized_gain_loss_cents=-75_000,
    )
    cats = [s.category for s in signals]
    assert cats == [
        "mrp_supply_chain",
        "predictive_eam",
        "omnichannel_crm",
        "us_payroll",
        "fx_treasury",
    ]
    assert score == 92 - 10 - 10 - 6 - 4 - 8
    assert "Midwest Industrial Group" in headline
    assert signals[4].severity == "high"
    assert "$-750.00" in signals[4].title


def test_predictive_health_reports_positive_fx_gain() -> None:
    score, _, signals = compute_predictive_health_and_signals(
        business_name="Global Freight LLC",
        period_days=7,
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
        stripe_paid_cents=100_000,
        bookings_confirmed_count=0,
        bookings_cancelled_count=0,
        waitlist_count=0,
        waitlist_value_cents=0,
        failed_notifications_count=0,
        fx_open_entries_count=3,
        fx_unrealized_gain_loss_cents=42_000,
    )
    assert score == 92
    assert len(signals) == 1
    assert signals[0].severity == "positive"
    assert "$+420.00" in signals[0].title


def test_build_predictive_webhook_payload_supports_slack_teams_and_zapier() -> None:
    score, headline, signals = compute_predictive_health_and_signals(
        business_name="Apex Fabrication",
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
        stripe_paid_cents=250_000,
        bookings_confirmed_count=0,
        bookings_cancelled_count=0,
        waitlist_count=0,
        waitlist_value_cents=0,
        failed_notifications_count=0,
        mrp_shortage_runs_count=1,
    )
    ctx = PredictiveContext(
        tenant_id=uuid4(),
        business_name="Apex Fabrication",
        period_days=30,
        health_score=score,
        headline=headline,
        signals=signals,
        metrics_snapshot={"mrp_shortage_runs_count": 1, "stripe_paid_cents": 250_000},
        byok_config=None,
        recipient_email=None,
    )
    payload = build_predictive_webhook_payload(
        ctx=ctx,
        engine="grounded",
        executive_summary="1 production run blocked by raw-material shortage.",
        action_url="https://www.amarkal-platform.com/overview/",
    )
    assert payload["event"] == "ai.predictive_brief.generated"
    assert payload["health_score"] == 82
    assert "AMARKAL Proactive Brief" in payload["text"]
    assert len(payload["blocks"]) == 3
    assert payload["signals"][0]["action_path"] == "/industrial/"


def test_dispatch_predictive_webhook_blocks_ssrf_targets() -> None:
    outcome_http, sig1 = asyncio.run(
        dispatch_predictive_webhook("http://hooks.slack.com/services/T/B/X", {"text": "hi"})
    )
    assert outcome_http.status == "failed"
    assert sig1 is None

    outcome_priv, sig2 = asyncio.run(
        dispatch_predictive_webhook("https://169.254.169.254/latest/meta-data/", {"text": "hi"})
    )
    assert outcome_priv.status == "failed"
    assert sig2 is None
