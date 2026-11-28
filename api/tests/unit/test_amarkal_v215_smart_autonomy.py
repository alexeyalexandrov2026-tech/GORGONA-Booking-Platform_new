"""Unit tests for AMARKAL v2.15.0: AI Smart Autonomy & Proactive Predictive Insights."""

from __future__ import annotations

from uuid import uuid7

from gorgona_booking.ai_assistant.autonomy import (
    AutonomyPolicyView,
    compute_predictive_health_and_signals,
    default_autonomy_policy,
    evaluate_autonomy_decision,
)
from gorgona_booking.notifications.service import render_template


def test_smart_autonomy_always_blocks_financial_mutations_even_in_safe_autopilot() -> None:
    tid = uuid7()
    policy = AutonomyPolicyView(
        tenant_id=tid,
        autonomy_level="safe_autopilot",
        auto_confirm_open_bookings=True,
        auto_send_invoice_reminders=True,
        auto_offer_waitlist_slots=True,
        auto_send_weekly_brief=True,
        weekly_brief_day="monday",
        weekly_brief_email="cfo@acme.us",
        require_human_approval_over_cents=0,
        updated_at=None,
    )

    # Routine zero-financial actions run autonomously when enabled
    mode, _ = evaluate_autonomy_decision(policy, requested_action="send_invoice_reminder")
    assert mode == "autonomous_safe"

    mode_wl, _ = evaluate_autonomy_decision(policy, requested_action="offer_waitlist_slot")
    assert mode_wl == "autonomous_safe"

    # Financial / contractual actions are ALWAYS blocked for Human-in-the-Loop
    mode_po, reason_po = evaluate_autonomy_decision(
        policy, requested_action="approve_purchase_order", estimated_financial_impact_cents=250_000
    )
    assert mode_po == "blocked_by_policy"
    assert "Human-in-the-Loop" in reason_po

    mode_refund, _ = evaluate_autonomy_decision(
        policy, requested_action="issue_refund", estimated_financial_impact_cents=100
    )
    assert mode_refund == "blocked_by_policy"

    # Any non-zero financial impact is blocked even on a routine action name
    mode_nonzero, _ = evaluate_autonomy_decision(
        policy, requested_action="send_invoice_reminder", estimated_financial_impact_cents=1
    )
    assert mode_nonzero == "blocked_by_policy"


def test_observe_only_and_strict_approval_queue_all_routine_actions() -> None:
    policy = default_autonomy_policy(uuid7())
    assert policy.autonomy_level == "observe_only"
    assert policy.require_human_approval_over_cents == 0

    mode, _ = evaluate_autonomy_decision(policy, requested_action="send_invoice_reminder")
    assert mode == "queued_for_approval"


def test_predictive_insights_detects_overdue_ar_vendor_variance_and_churn() -> None:
    score, headline, signals = compute_predictive_health_and_signals(
        business_name="Acme US Freight LLC",
        period_days=30,
        ar_total_cents=2_000_000,
        ar_overdue_cents=800_000,
        top_overdue_counterparty="Midwest Steel Corp",
        po_variance_count=2,
        po_variance_cents=145_000,
        top_variance_vendor="Diesel Fleet Supply",
        quotes_sent_count=10,
        quotes_accepted_count=4,
        stale_quotes_count=3,
        stripe_open_count=2,
        stripe_open_cents=320_000,
        stripe_paid_cents=1_500_000,
        bookings_confirmed_count=12,
        bookings_cancelled_count=4,
        waitlist_count=5,
        waitlist_value_cents=95_000,
        failed_notifications_count=1,
    )
    assert 15 <= score < 60
    assert "Acme US Freight LLC" in headline
    categories = {s.category for s in signals}
    assert {
        "cashflow_ar",
        "margin_vendor_cost",
        "payment_conversion",
        "utilization_churn",
        "sales_velocity",
        "demand_recovery",
        "ops_reliability",
    } <= categories
    assert any("Midwest Steel Corp" in s.recommendation for s in signals)
    assert any("Diesel Fleet Supply" in s.recommendation for s in signals)


def test_predictive_insights_healthy_baseline_scores_high() -> None:
    score, headline, signals = compute_predictive_health_and_signals(
        business_name="Clean Ops Co",
        period_days=30,
        ar_total_cents=500_000,
        ar_overdue_cents=0,
        top_overdue_counterparty=None,
        po_variance_count=0,
        po_variance_cents=0,
        top_variance_vendor=None,
        quotes_sent_count=5,
        quotes_accepted_count=5,
        stale_quotes_count=0,
        stripe_open_count=0,
        stripe_open_cents=0,
        stripe_paid_cents=500_000,
        bookings_confirmed_count=20,
        bookings_cancelled_count=0,
        waitlist_count=0,
        waitlist_value_cents=0,
        failed_notifications_count=0,
    )
    assert score == 92
    assert len(signals) == 1
    assert signals[0].severity == "positive"
    assert "Healthy" in headline


def test_predictive_weekly_brief_email_template_renders() -> None:
    subj, body = render_template(
        "predictive_weekly_brief",
        {
            "business_name": "Acme US Freight LLC",
            "reference": "Health 84/100",
            "amount": "Margin steady; 2 overdue invoices detected.",
            "action_url": "https://www.amarkal-platform.com/overview/",
        },
    )
    assert "AMARKAL Weekly Predictive Brief" in subj
    assert "Acme US Freight LLC" in subj
    assert "Margin steady" in body
