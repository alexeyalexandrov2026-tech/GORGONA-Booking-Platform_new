"""AMARKAL v2.25.0: Advanced BI & Executive Dashboards Read-Only Aggregation API.

Security & architectural invariants:
- Strictly read-only aggregation inside `authorized_tenant(..., Permission.BUSINESS_READ)`
  under PostgreSQL 18 `ENABLE + FORCE ROW LEVEL SECURITY`.
- Zero database migrations required: reads live operational records across Double-Entry
  FIN-03 invoices, Stripe live payments, B2B Commercial Quotes & POs, US Payroll runs,
  MRP II production runs, Predictive EAM work orders & assets, No-Code Kanban boards,
  Omnichannel Inbox, and Multi-Currency FX Ledger.
- All KPI, funnel, monthly series, Gantt timeline, and FX exposure calculations are pure
  deterministic functions with zero-division guards.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import UTC, date, datetime, timedelta
from typing import Annotated, Any, Literal
from uuid import UUID

from fastapi import APIRouter, Query, Request
from psycopg.rows import dict_row
from pydantic import BaseModel, ConfigDict

from gorgona_booking.api.businesses import CurrentPrincipal
from gorgona_booking.api.deps import runtime_pool
from gorgona_booking.api.request_id import get_request_id
from gorgona_booking.auth.permissions import Permission
from gorgona_booking.tenancy.authorization import authorized_tenant

router = APIRouter(tags=["analytics-bi"])

FunnelStageKey = Literal[
    "draft_review",
    "sent_active",
    "won_accepted",
    "invoiced_converted",
]
GanttSourceKind = Literal["mrp_run", "eam_wo", "kanban_card"]

_MONTH_NAMES = (
    "Jan",
    "Feb",
    "Mar",
    "Apr",
    "May",
    "Jun",
    "Jul",
    "Aug",
    "Sep",
    "Oct",
    "Nov",
    "Dec",
)


class BiKpiSummary(BaseModel):
    model_config = ConfigDict(frozen=True)
    total_inflow_cents: int
    total_outflow_cents: int
    net_cashflow_cents: int
    gross_margin_pct: float
    quote_pipeline_cents: int
    quote_win_rate_pct: float
    commission_saved_cents: int
    fx_net_gain_loss_cents: int
    fleet_avg_health_score: int
    assets_at_risk_count: int
    open_inbox_threads: int
    unread_inbox_messages: int


class MonthlyCashflowPoint(BaseModel):
    model_config = ConfigDict(frozen=True)
    month_key: str
    month_label: str
    inflow_cents: int
    outflow_cents: int
    net_cents: int


class SalesFunnelStage(BaseModel):
    model_config = ConfigDict(frozen=True)
    stage_key: FunnelStageKey
    label: str
    count: int
    value_cents: int
    conversion_pct: float


class GanttTimelineItem(BaseModel):
    model_config = ConfigDict(frozen=True)
    id: str
    source: GanttSourceKind
    code: str
    title: str
    status: str
    priority: str
    start_date: str
    end_date: str
    progress_pct: int
    module_href: str


class FxCurrencyExposure(BaseModel):
    model_config = ConfigDict(frozen=True)
    currency: str
    entry_count: int
    receivable_usd_cents: int
    payable_usd_cents: int
    cash_usd_cents: int
    net_exposure_usd_cents: int
    unrealized_fx_cents: int
    realized_fx_cents: int


class BiDashboardResponse(BaseModel):
    model_config = ConfigDict(frozen=True)
    period_days: int
    period_start: str
    period_end: str
    generated_at: str
    kpis: BiKpiSummary
    monthly_cashflow: list[MonthlyCashflowPoint]
    sales_funnel: list[SalesFunnelStage]
    gantt_items: list[GanttTimelineItem]
    fx_exposure: list[FxCurrencyExposure]


def _month_keys_between(start_d: date, end_d: date) -> list[str]:
    keys: list[str] = []
    cur_y, cur_m = start_d.year, start_d.month
    end_pair = (end_d.year, end_d.month)
    while (cur_y, cur_m) <= end_pair:
        keys.append(f"{cur_y:04d}-{cur_m:02d}")
        if cur_m == 12:
            cur_y += 1
            cur_m = 1
        else:
            cur_m += 1
    return keys


def _format_month_label(month_key: str) -> str:
    year_str, month_str = month_key.split("-", 1)
    month_idx = max(1, min(12, int(month_str))) - 1
    return f"{_MONTH_NAMES[month_idx]} {year_str}"


def build_monthly_cashflow(
    start_d: date,
    end_d: date,
    inflow_by_month: dict[str, int],
    outflow_by_month: dict[str, int],
) -> list[MonthlyCashflowPoint]:
    """Assemble continuous monthly cashflow points with zero-filled months."""
    points: list[MonthlyCashflowPoint] = []
    for key in _month_keys_between(start_d, end_d):
        inflow = max(0, int(inflow_by_month.get(key, 0)))
        outflow = max(0, int(outflow_by_month.get(key, 0)))
        points.append(
            MonthlyCashflowPoint(
                month_key=key,
                month_label=_format_month_label(key),
                inflow_cents=inflow,
                outflow_cents=outflow,
                net_cents=inflow - outflow,
            )
        )
    return points


def build_sales_funnel(quotes: list[dict[str, Any]]) -> list[SalesFunnelStage]:
    """Build cumulative B2B CPQ sales funnel stages with deterministic conversion rates."""
    non_void = [q for q in quotes if str(q.get("status", "")) != "void"]
    total_count = len(non_void)

    draft_statuses = {"draft", "pending_approval", "approved"}
    sent_statuses = {"sent", "accepted", "converted"}
    won_statuses = {"accepted", "converted"}
    invoiced_statuses = {"converted"}

    # Stage 1 represents all active quotes entering the funnel; subsequent stages are cumulative
    # conversions through Sent -> Won -> Invoiced so executive conversion percentages are monotonic.
    stage_defs: list[tuple[FunnelStageKey, str, list[dict[str, Any]]]] = [
        (
            "draft_review",
            "Qualified & Drafted",
            [
                q
                for q in non_void
                if str(q.get("status", "")) in draft_statuses | sent_statuses | {"declined"}
            ],
        ),
        (
            "sent_active",
            "Sent to Client",
            [q for q in non_void if str(q.get("status", "")) in sent_statuses],
        ),
        (
            "won_accepted",
            "Accepted / Won",
            [q for q in non_void if str(q.get("status", "")) in won_statuses],
        ),
        (
            "invoiced_converted",
            "Converted to Invoice",
            [q for q in non_void if str(q.get("status", "")) in invoiced_statuses],
        ),
    ]

    stages: list[SalesFunnelStage] = []
    for key, label, items in stage_defs:
        count = len(items)
        value_cents = sum(max(0, int(q.get("total_cents") or 0)) for q in items)
        conv = round((count / total_count) * 100.0, 1) if total_count > 0 else 0.0
        stages.append(
            SalesFunnelStage(
                stage_key=key,
                label=label,
                count=count,
                value_cents=value_cents,
                conversion_pct=conv,
            )
        )
    return stages


def _coerce_date(val: Any, fallback: date) -> date:
    if isinstance(val, datetime):
        return val.date()
    if isinstance(val, date):
        return val
    if isinstance(val, str) and len(val) >= 10:
        try:
            return date.fromisoformat(val[:10])
        except ValueError:
            return fallback
    return fallback


def _status_progress(source: GanttSourceKind, status_str: str) -> int:
    s = status_str.strip().lower()
    if source == "mrp_run":
        mapping = {
            "planned": 15,
            "reserved": 40,
            "in_progress": 70,
            "completed": 100,
        }
        return mapping.get(s, 20)
    if source == "eam_wo":
        mapping = {
            "open": 15,
            "scheduled": 35,
            "in_progress": 70,
            "completed": 100,
        }
        return mapping.get(s, 20)
    # kanban_card lane heuristics
    if any(tok in s for tok in ("done", "complete", "closed", "shipped", "paid")):
        return 100
    if any(tok in s for tok in ("review", "qa", "approv", "verify")):
        return 80
    if any(tok in s for tok in ("progress", "active", "doing", "build", "work")):
        return 50
    return 15


def build_gantt_timeline(
    mrp_runs: list[dict[str, Any]],
    eam_orders: list[dict[str, Any]],
    kanban_cards: list[dict[str, Any]],
    today: date,
) -> list[GanttTimelineItem]:
    """Merge MRP II runs, Predictive EAM work orders, and Kanban cards into a Gantt timeline."""
    items: list[GanttTimelineItem] = []

    for row in mrp_runs:
        start_d = _coerce_date(row.get("created_at"), today)
        raw_end = _coerce_date(
            row.get("completed_at") or row.get("scheduled_date"),
            start_d + timedelta(days=5),
        )
        end_d = raw_end if raw_end >= start_d else start_d + timedelta(days=2)
        status_str = str(row.get("status") or "planned")
        shortage = int(row.get("shortage_count") or 0)
        priority = "high" if shortage > 0 else "normal"
        items.append(
            GanttTimelineItem(
                id=str(row.get("id", "")),
                source="mrp_run",
                code=str(row.get("run_number") or "MRP"),
                title=str(row.get("recipe_name") or "Production Run"),
                status=status_str,
                priority=priority,
                start_date=start_d.isoformat(),
                end_date=end_d.isoformat(),
                progress_pct=max(0, min(100, _status_progress("mrp_run", status_str))),
                module_href="/industrial/",
            )
        )

    for row in eam_orders:
        start_d = _coerce_date(row.get("created_at"), today)
        raw_end = _coerce_date(
            row.get("completed_at") or row.get("due_at"),
            start_d + timedelta(days=3),
        )
        end_d = raw_end if raw_end >= start_d else start_d + timedelta(days=1)
        status_str = str(row.get("status") or "open")
        asset_tag = str(row.get("asset_tag") or "").strip()
        base_title = str(row.get("title") or "Maintenance Work Order")
        full_title = f"[{asset_tag}] {base_title}" if asset_tag else base_title
        items.append(
            GanttTimelineItem(
                id=str(row.get("id", "")),
                source="eam_wo",
                code=str(row.get("wo_number") or "WO"),
                title=full_title[:160],
                status=status_str,
                priority=str(row.get("priority") or "high"),
                start_date=start_d.isoformat(),
                end_date=end_d.isoformat(),
                progress_pct=max(0, min(100, _status_progress("eam_wo", status_str))),
                module_href="/industrial/",
            )
        )

    for row in kanban_cards:
        start_d = _coerce_date(row.get("created_at"), today)
        raw_end = _coerce_date(row.get("due_date"), start_d + timedelta(days=7))
        end_d = raw_end if raw_end >= start_d else start_d + timedelta(days=2)
        lane = str(row.get("lane_id") or "backlog")
        board_title = str(row.get("board_title") or "Board")
        items.append(
            GanttTimelineItem(
                id=str(row.get("id", "")),
                source="kanban_card",
                code=board_title[:24],
                title=str(row.get("title") or "Task")[:160],
                status=lane,
                priority=str(row.get("priority") or "medium"),
                start_date=start_d.isoformat(),
                end_date=end_d.isoformat(),
                progress_pct=max(0, min(100, _status_progress("kanban_card", lane))),
                module_href="/workspace/",
            )
        )

    items.sort(key=lambda it: (it.start_date, it.end_date, it.code))
    return items[:24]


def build_fx_exposure(entries: list[dict[str, Any]]) -> list[FxCurrencyExposure]:
    """Aggregate multi-currency receivables, payables, cash, and unrealized/realized FX P&L."""
    buckets: dict[str, dict[str, int]] = defaultdict(
        lambda: {
            "count": 0,
            "receivable": 0,
            "payable": 0,
            "cash": 0,
            "unrealized": 0,
            "realized": 0,
        }
    )
    for row in entries:
        ccy = str(row.get("currency") or "USD").upper()
        b = buckets[ccy]
        b["count"] += 1
        kind = str(row.get("entry_kind") or "receivable")
        revalued = max(0, int(row.get("revalued_usd_cents") or 0))
        status_str = str(row.get("status") or "open")
        if status_str == "open":
            if kind == "receivable":
                b["receivable"] += revalued
            elif kind == "payable":
                b["payable"] += revalued
            else:
                b["cash"] += revalued
            b["unrealized"] += int(row.get("fx_gain_loss_cents") or 0)
        else:
            b["realized"] += int(row.get("realized_fx_gain_loss_cents") or 0)

    result: list[FxCurrencyExposure] = []
    for ccy, b in sorted(
        buckets.items(),
        key=lambda kv: abs(kv[1]["receivable"] + kv[1]["cash"] - kv[1]["payable"]),
        reverse=True,
    ):
        net_exp = b["receivable"] + b["cash"] - b["payable"]
        result.append(
            FxCurrencyExposure(
                currency=ccy,
                entry_count=b["count"],
                receivable_usd_cents=b["receivable"],
                payable_usd_cents=b["payable"],
                cash_usd_cents=b["cash"],
                net_exposure_usd_cents=net_exp,
                unrealized_fx_cents=b["unrealized"],
                realized_fx_cents=b["realized"],
            )
        )
    return result


def compute_bi_kpis(
    *,
    monthly_points: list[MonthlyCashflowPoint],
    stripe_paid_cents: int,
    quotes: list[dict[str, Any]],
    fx_exposure: list[FxCurrencyExposure],
    fleet_avg_health_score: int,
    assets_at_risk_count: int,
    open_inbox_threads: int,
    unread_inbox_messages: int,
) -> BiKpiSummary:
    """Compute executive BI KPIs with strict zero-division protection."""
    total_inflow = sum(p.inflow_cents for p in monthly_points)
    total_outflow = sum(p.outflow_cents for p in monthly_points)
    net_cashflow = total_inflow - total_outflow
    gross_margin_pct = round((net_cashflow / total_inflow) * 100.0, 1) if total_inflow > 0 else 0.0

    active_quotes = [q for q in quotes if str(q.get("status", "")) not in ("void", "declined")]
    pipeline_cents = sum(max(0, int(q.get("total_cents") or 0)) for q in active_quotes)

    decided_quotes = [
        q
        for q in quotes
        if str(q.get("status", "")) in ("sent", "accepted", "converted", "declined")
    ]
    won_quotes = [
        q for q in decided_quotes if str(q.get("status", "")) in ("accepted", "converted")
    ]
    win_rate_pct = (
        round((len(won_quotes) / len(decided_quotes)) * 100.0, 1) if decided_quotes else 0.0
    )

    # AMARKAL charges 0% platform transaction fee vs standard 2.5% marketplace take-rate.
    commission_saved_cents = round(max(0, stripe_paid_cents) * 0.025)
    fx_net = sum(f.unrealized_fx_cents + f.realized_fx_cents for f in fx_exposure)

    return BiKpiSummary(
        total_inflow_cents=total_inflow,
        total_outflow_cents=total_outflow,
        net_cashflow_cents=net_cashflow,
        gross_margin_pct=gross_margin_pct,
        quote_pipeline_cents=pipeline_cents,
        quote_win_rate_pct=win_rate_pct,
        commission_saved_cents=commission_saved_cents,
        fx_net_gain_loss_cents=fx_net,
        fleet_avg_health_score=max(0, min(100, int(fleet_avg_health_score))),
        assets_at_risk_count=max(0, int(assets_at_risk_count)),
        open_inbox_threads=max(0, int(open_inbox_threads)),
        unread_inbox_messages=max(0, int(unread_inbox_messages)),
    )


@router.get(
    "/v1/businesses/{business_id}/analytics/bi",
    response_model=BiDashboardResponse,
)
async def get_executive_bi_dashboard(
    business_id: UUID,
    request: Request,
    principal: CurrentPrincipal,
    period_days: Annotated[int, Query(ge=7, le=365)] = 90,
) -> BiDashboardResponse:
    """Read-only executive BI aggregation across finance, CPQ, MRP II, EAM, Kanban, and FX."""
    now_utc = datetime.now(UTC)
    today = now_utc.date()
    start_date = today - timedelta(days=period_days)
    start_dt = datetime.combine(start_date, datetime.min.time(), tzinfo=UTC)

    async with (
        authorized_tenant(
            runtime_pool(request),
            principal,
            business_id,
            Permission.BUSINESS_READ,
            request_id=get_request_id(request),
        ) as session,
        session.conn.cursor(row_factory=dict_row) as cur,
    ):
        inflow_by_month: dict[str, int] = defaultdict(int)
        outflow_by_month: dict[str, int] = defaultdict(int)

        # 1. Stripe live paid sessions
        await cur.execute(
            """
            SELECT to_char(COALESCE(paid_at, created_at) AT TIME ZONE 'UTC', 'YYYY-MM') AS ym,
                   COALESCE(SUM(amount_cents), 0)::bigint AS total_cents
            FROM gba.payment_sessions
            WHERE tenant_id = %s
              AND status = 'paid'
              AND COALESCE(paid_at, created_at) >= %s
            GROUP BY ym
            """,
            (business_id, start_dt),
        )
        stripe_paid_total = 0
        for row in await cur.fetchall():
            amt = int(row["total_cents"] or 0)
            inflow_by_month[str(row["ym"])] += amt
            stripe_paid_total += amt

        # 2. Issued Double-Entry FIN-03 financial documents (latest revision per doc)
        await cur.execute(
            """
            WITH latest_docs AS (
                SELECT DISTINCT ON (book_id, document_id)
                    direction,
                    state,
                    invoice_date,
                    principal_minor
                FROM gba.financial_document_versions
                WHERE tenant_id = %s
                ORDER BY book_id, document_id, revision DESC
            )
            SELECT direction,
                   to_char(invoice_date, 'YYYY-MM') AS ym,
                   COALESCE(SUM(principal_minor), 0)::bigint AS total_minor
            FROM latest_docs
            WHERE state = 'issued'
              AND invoice_date >= %s
            GROUP BY direction, ym
            """,
            (business_id, start_date),
        )
        for row in await cur.fetchall():
            amt = int(row["total_minor"] or 0)
            ym = str(row["ym"])
            if row["direction"] == "receivable":
                inflow_by_month[ym] += amt
            else:
                outflow_by_month[ym] += amt

        # 3. Active B2B Purchase Orders (procurement commitments / spend)
        await cur.execute(
            """
            SELECT to_char(created_at AT TIME ZONE 'UTC', 'YYYY-MM') AS ym,
                   COALESCE(SUM(total_cents), 0)::bigint AS total_cents
            FROM gba.purchase_orders
            WHERE tenant_id = %s
              AND status != 'cancelled'
              AND created_at >= %s
            GROUP BY ym
            """,
            (business_id, start_dt),
        )
        for row in await cur.fetchall():
            outflow_by_month[str(row["ym"])] += int(row["total_cents"] or 0)

        # 4. US Payroll runs (gross + employer taxes)
        await cur.execute(
            """
            SELECT to_char(pay_date, 'YYYY-MM') AS ym,
                   COALESCE(SUM(total_gross_cents + total_employer_taxes_cents), 0)::bigint
                       AS total_cents
            FROM gba.payroll_runs
            WHERE tenant_id = %s
              AND status != 'void'
              AND pay_date >= %s
            GROUP BY ym
            """,
            (business_id, start_date),
        )
        for row in await cur.fetchall():
            outflow_by_month[str(row["ym"])] += int(row["total_cents"] or 0)

        # 5. B2B Commercial Quotes for Sales Funnel
        await cur.execute(
            """
            SELECT status, total_cents
            FROM gba.commercial_quotes
            WHERE tenant_id = %s
              AND created_at >= %s
            """,
            (business_id, start_dt),
        )
        quotes = [dict(r) for r in await cur.fetchall()]

        # 6. MRP II Production Runs for Executive Gantt Timeline
        await cur.execute(
            """
            SELECT r.id,
                   r.run_number,
                   rec.name AS recipe_name,
                   r.status,
                   r.scheduled_date,
                   r.completed_at,
                   r.shortage_count,
                   r.created_at
            FROM gba.mrp_production_runs r
            JOIN gba.mrp_recipes rec
              ON rec.tenant_id = r.tenant_id AND rec.id = r.recipe_id
            WHERE r.tenant_id = %s
              AND r.status != 'cancelled'
            ORDER BY r.created_at DESC
            LIMIT 10
            """,
            (business_id,),
        )
        mrp_runs = [dict(r) for r in await cur.fetchall()]

        # 7. Predictive EAM Work Orders for Executive Gantt Timeline
        await cur.execute(
            """
            SELECT w.id,
                   w.wo_number,
                   w.title,
                   w.status,
                   w.priority,
                   w.due_at,
                   w.completed_at,
                   w.created_at,
                   a.asset_tag
            FROM gba.eam_predictive_work_orders w
            JOIN gba.eam_assets a
              ON a.tenant_id = w.tenant_id AND a.id = w.asset_id
            WHERE w.tenant_id = %s
              AND w.status != 'cancelled'
            ORDER BY w.created_at DESC
            LIMIT 10
            """,
            (business_id,),
        )
        eam_orders = [dict(r) for r in await cur.fetchall()]

        # 8. No-Code Kanban Board Cards for Executive Gantt Timeline
        await cur.execute(
            """
            SELECT c.id,
                   c.title,
                   c.lane_id,
                   c.priority,
                   c.due_date,
                   c.created_at,
                   b.title AS board_title
            FROM gba.workspace_board_cards c
            JOIN gba.workspace_boards b
              ON b.tenant_id = c.tenant_id AND b.id = c.board_id
            WHERE c.tenant_id = %s
            ORDER BY c.created_at DESC
            LIMIT 10
            """,
            (business_id,),
        )
        kanban_cards = [dict(r) for r in await cur.fetchall()]

        # 9. Multi-Currency FX Ledger Exposure
        await cur.execute(
            """
            SELECT currency,
                   entry_kind,
                   revalued_usd_cents,
                   fx_gain_loss_cents,
                   realized_fx_gain_loss_cents,
                   status
            FROM gba.fx_ledger_entries
            WHERE tenant_id = %s
            """,
            (business_id,),
        )
        fx_rows = [dict(r) for r in await cur.fetchall()]

        # 10. Fleet / Equipment Asset Health Summary
        await cur.execute(
            """
            SELECT COALESCE(ROUND(AVG(health_score)), 100)::int AS avg_health,
                   COUNT(*) FILTER (
                       WHERE status IN ('warning', 'maintenance_due', 'out_of_service')
                   )::int AS at_risk_count
            FROM gba.eam_assets
            WHERE tenant_id = %s
            """,
            (business_id,),
        )
        eam_summary = await cur.fetchone() or {"avg_health": 100, "at_risk_count": 0}

        # 11. Omnichannel Client Inbox Backlog
        await cur.execute(
            """
            SELECT COUNT(*) FILTER (WHERE status IN ('open', 'pending'))::int AS open_threads,
                   COALESCE(SUM(unread_count), 0)::int AS unread_messages
            FROM gba.omnichannel_threads
            WHERE tenant_id = %s
            """,
            (business_id,),
        )
        inbox_summary = await cur.fetchone() or {"open_threads": 0, "unread_messages": 0}

    monthly_cashflow = build_monthly_cashflow(start_date, today, inflow_by_month, outflow_by_month)
    sales_funnel = build_sales_funnel(quotes)
    gantt_items = build_gantt_timeline(mrp_runs, eam_orders, kanban_cards, today)
    fx_exposure = build_fx_exposure(fx_rows)
    kpis = compute_bi_kpis(
        monthly_points=monthly_cashflow,
        stripe_paid_cents=stripe_paid_total,
        quotes=quotes,
        fx_exposure=fx_exposure,
        fleet_avg_health_score=int(eam_summary["avg_health"]),
        assets_at_risk_count=int(eam_summary["at_risk_count"]),
        open_inbox_threads=int(inbox_summary["open_threads"]),
        unread_inbox_messages=int(inbox_summary["unread_messages"]),
    )

    return BiDashboardResponse(
        period_days=period_days,
        period_start=start_date.isoformat(),
        period_end=today.isoformat(),
        generated_at=now_utc.isoformat(),
        kpis=kpis,
        monthly_cashflow=monthly_cashflow,
        sales_funnel=sales_funnel,
        gantt_items=gantt_items,
        fx_exposure=fx_exposure,
    )
