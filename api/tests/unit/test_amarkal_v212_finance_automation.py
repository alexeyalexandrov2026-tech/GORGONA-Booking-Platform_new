"""Unit tests for AMARKAL v2.12.0 B2B finance automation (recurring, aging, CSV, templates)."""

from __future__ import annotations

from datetime import date

from gorgona_booking.business.recurring_aging import (
    AgingItemView,
    advance_run_date,
    classify_aging_bucket,
    payment_terms_days,
    render_cpa_aging_csv,
    summarize_aging_items,
)
from gorgona_booking.notifications.service import TEMPLATES, render_template


def test_advance_run_date_handles_month_end_clamping_and_cadences() -> None:
    assert advance_run_date(date(2026, 1, 31), "monthly") == date(2026, 2, 28)
    assert advance_run_date(date(2026, 1, 31), "quarterly") == date(2026, 4, 30)
    assert advance_run_date(date(2026, 3, 15), "weekly") == date(2026, 3, 22)
    assert advance_run_date(date(2026, 3, 15), "biweekly") == date(2026, 3, 29)
    assert advance_run_date(date(2026, 11, 27), "annual") == date(2027, 11, 27)


def test_aging_buckets_summary_and_cpa_csv_export() -> None:
    assert payment_terms_days("Net 30") == 30
    assert payment_terms_days("Due on receipt") == 0

    as_of = date(2026, 11, 27)
    assert classify_aging_bucket(date(2026, 12, 10), as_of=as_of) == ("current", 0)
    assert classify_aging_bucket(date(2026, 11, 10), as_of=as_of) == ("1_30", 17)
    assert classify_aging_bucket(date(2026, 10, 10), as_of=as_of) == ("31_60", 48)
    assert classify_aging_bucket(date(2026, 9, 10), as_of=as_of) == ("61_90", 78)
    assert classify_aging_bucket(date(2026, 8, 1), as_of=as_of) == ("90_plus", 118)

    items = [
        AgingItemView(
            side="AR",
            doc_type="Commercial Quote",
            reference_number="Q-1001",
            counterparty_name="Apex Freight LLC",
            status="accepted",
            issued_date=date(2026, 10, 1),
            due_date=date(2026, 10, 31),
            days_past_due=27,
            bucket="1_30",
            amount_cents=450_000,
        ),
        AgingItemView(
            side="AP",
            doc_type="Purchase Order",
            reference_number="PO-2001",
            counterparty_name="Midwest Diesel Corp",
            status="matched",
            issued_date=date(2026, 11, 15),
            due_date=date(2026, 12, 15),
            days_past_due=0,
            bucket="current",
            amount_cents=210_000,
        ),
    ]
    ar = summarize_aging_items(items, "AR")
    ap = summarize_aging_items(items, "AP")
    assert ar.days_1_30_cents == 450_000
    assert ar.total_cents == 450_000
    assert ap.current_cents == 210_000

    csv_text = render_cpa_aging_csv(items)
    assert "Side,DocumentType,ReferenceNumber" in csv_text
    assert "AR,Commercial Quote,Q-1001,Apex Freight LLC" in csv_text
    assert "4500.00,USD" in csv_text
    assert "AP,Purchase Order,PO-2001,Midwest Diesel Corp" in csv_text


def test_b2b_email_templates_render_cleanly() -> None:
    assert "commercial_quote_shared" in TEMPLATES
    assert "purchase_order_issued" in TEMPLATES
    assert "recurring_billing_notice" in TEMPLATES
    subj, body = render_template(
        "commercial_quote_shared",
        {
            "business_name": "Apex Freight LLC",
            "reference": "Q-2026-1042",
            "amount": "$7,700.00 USD",
            "action_url": "https://www.amarkal-platform.com/portal/?token=demo",
        },
    )
    assert "Q-2026-1042" in subj
    assert "https://www.amarkal-platform.com/portal/?token=demo" in body
