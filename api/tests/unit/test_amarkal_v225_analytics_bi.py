"""Unit tests for AMARKAL v2.25.0 Advanced BI & Executive Dashboards helpers."""

from __future__ import annotations

from datetime import UTC, date, datetime

from gorgona_booking.api.analytics_bi import (
    build_fx_exposure,
    build_gantt_timeline,
    build_monthly_cashflow,
    build_sales_funnel,
    compute_bi_kpis,
)


def test_build_monthly_cashflow_fills_missing_months_and_computes_net() -> None:
    points = build_monthly_cashflow(
        date(2026, 9, 10),
        date(2026, 11, 28),
        inflow_by_month={"2026-09": 500_000, "2026-11": 820_000},
        outflow_by_month={"2026-10": 150_000, "2026-11": 310_000},
    )
    assert [p.month_key for p in points] == ["2026-09", "2026-10", "2026-11"]
    assert [p.month_label for p in points] == ["Sep 2026", "Oct 2026", "Nov 2026"]
    assert points[0].net_cents == 500_000
    assert points[1].inflow_cents == 0
    assert points[1].net_cents == -150_000
    assert points[2].net_cents == 510_000


def test_build_sales_funnel_monotonic_conversion_and_ignores_void() -> None:
    quotes = [
        {"status": "draft", "total_cents": 100_000},
        {"status": "sent", "total_cents": 200_000},
        {"status": "accepted", "total_cents": 300_000},
        {"status": "converted", "total_cents": 400_000},
        {"status": "void", "total_cents": 999_999},
    ]
    funnel = build_sales_funnel(quotes)
    assert [s.stage_key for s in funnel] == [
        "draft_review",
        "sent_active",
        "won_accepted",
        "invoiced_converted",
    ]
    assert [s.count for s in funnel] == [4, 3, 2, 1]
    assert [s.conversion_pct for s in funnel] == [100.0, 75.0, 50.0, 25.0]
    assert funnel[0].value_cents == 1_000_000
    assert funnel[3].value_cents == 400_000


def test_build_sales_funnel_empty_zero_division_safe() -> None:
    funnel = build_sales_funnel([])
    assert len(funnel) == 4
    assert all(s.count == 0 and s.conversion_pct == 0.0 for s in funnel)


def test_build_gantt_timeline_merges_and_clamps_dates_and_progress() -> None:
    today = date(2026, 11, 28)
    mrp = [
        {
            "id": "m1",
            "run_number": "RUN-101",
            "recipe_name": "Asphalt Mix Batch",
            "status": "in_progress",
            "scheduled_date": date(2026, 12, 2),
            "shortage_count": 2,
            "created_at": datetime(2026, 11, 25, 10, 0, tzinfo=UTC),
        }
    ]
    eam = [
        {
            "id": "e1",
            "wo_number": "WO-55",
            "title": "Hydraulic Pump Bearing Swap",
            "status": "completed",
            "priority": "critical",
            "asset_tag": "TRK-04",
            "due_at": datetime(2026, 11, 20, 9, 0, tzinfo=UTC),  # earlier than created_at
            "created_at": datetime(2026, 11, 26, 9, 0, tzinfo=UTC),
        }
    ]
    kanban = [
        {
            "id": "k1",
            "title": "Q4 Fleet Insurance Renewal",
            "lane_id": "in_progress",
            "priority": "high",
            "due_date": date(2026, 12, 5),
            "board_title": "Ops HQ",
            "created_at": datetime(2026, 11, 24, 8, 0, tzinfo=UTC),
        }
    ]
    items = build_gantt_timeline(mrp, eam, kanban, today)
    assert len(items) == 3
    by_id = {it.id: it for it in items}
    assert by_id["m1"].priority == "high"
    assert by_id["m1"].progress_pct == 70
    assert by_id["m1"].module_href == "/industrial/"
    # End date before start date is clamped forward
    assert by_id["e1"].end_date >= by_id["e1"].start_date
    assert by_id["e1"].progress_pct == 100
    assert "[TRK-04]" in by_id["e1"].title
    assert by_id["k1"].progress_pct == 50
    assert by_id["k1"].module_href == "/workspace/"


def test_build_fx_exposure_and_compute_bi_kpis() -> None:
    fx_rows = [
        {
            "currency": "EUR",
            "entry_kind": "receivable",
            "revalued_usd_cents": 450_000,
            "fx_gain_loss_cents": 12_000,
            "realized_fx_gain_loss_cents": 0,
            "status": "open",
        },
        {
            "currency": "EUR",
            "entry_kind": "payable",
            "revalued_usd_cents": 150_000,
            "fx_gain_loss_cents": -3_000,
            "realized_fx_gain_loss_cents": 0,
            "status": "open",
        },
        {
            "currency": "GBP",
            "entry_kind": "receivable",
            "revalued_usd_cents": 200_000,
            "fx_gain_loss_cents": 0,
            "realized_fx_gain_loss_cents": 8_500,
            "status": "settled",
        },
    ]
    fx_exposure = build_fx_exposure(fx_rows)
    by_ccy = {f.currency: f for f in fx_exposure}
    assert by_ccy["EUR"].net_exposure_usd_cents == 300_000
    assert by_ccy["EUR"].unrealized_fx_cents == 9_000
    assert by_ccy["GBP"].realized_fx_cents == 8_500

    points = build_monthly_cashflow(
        date(2026, 11, 1),
        date(2026, 11, 28),
        inflow_by_month={"2026-11": 1_000_000},
        outflow_by_month={"2026-11": 400_000},
    )
    kpis = compute_bi_kpis(
        monthly_points=points,
        stripe_paid_cents=600_000,
        quotes=[
            {"status": "sent", "total_cents": 100_000},
            {"status": "accepted", "total_cents": 250_000},
            {"status": "declined", "total_cents": 50_000},
        ],
        fx_exposure=fx_exposure,
        fleet_avg_health_score=92,
        assets_at_risk_count=1,
        open_inbox_threads=4,
        unread_inbox_messages=7,
    )
    assert kpis.net_cashflow_cents == 600_000
    assert kpis.gross_margin_pct == 60.0
    assert kpis.quote_pipeline_cents == 350_000
    assert kpis.quote_win_rate_pct == 33.3
    assert kpis.commission_saved_cents == 15_000
    assert kpis.fx_net_gain_loss_cents == 17_500
    assert kpis.fleet_avg_health_score == 92
    assert kpis.assets_at_risk_count == 1
    assert kpis.open_inbox_threads == 4
    assert kpis.unread_inbox_messages == 7
