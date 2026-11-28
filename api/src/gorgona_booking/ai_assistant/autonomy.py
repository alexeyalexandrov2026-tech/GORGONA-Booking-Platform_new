"""AMARKAL v2.15.0: AI Smart Autonomy (Hybrid Trust Guardrails) & Proactive Predictive Insights.

Invariants:
- Routine, reversible, zero-financial-risk actions (invoice reminders, waitlist outreach,
  open booking verification, weekly executive brief dispatch) can run under `safe_autopilot`
  ONLY when explicitly enabled by the business owner.
- Financial, contractual, payment, refund, and PO approval actions ALWAYS require explicit
  Human-in-the-Loop sign-off (`require_human_approval_over_cents == 0`).
- Predictive Insights are computed deterministically from live PG18 FORCE-RLS tables
  (AR/AP aging, PO 3-way match variances, commercial quotes, Stripe sessions, bookings,
  waitlist, notifications). Optional LLM narration runs strictly OUTSIDE DB transactions
  and honors the tenant's BYOK AI key (v2.14.0) with automatic grounded fallback.
"""

from __future__ import annotations

import asyncio
import re
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any, Literal
from uuid import UUID

from psycopg import AsyncConnection
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from gorgona_booking.ai_assistant.byok import TenantByokAiConfig, load_active_tenant_byok_ai
from gorgona_booking.ai_assistant.service import AiEngine, _synthesize_reply_sync
from gorgona_booking.business.recurring_aging import build_tenant_aging_report
from gorgona_booking.db.pool import RuntimeConnection
from gorgona_booking.notifications.service import EMAIL_RE, validate_and_mask_recipient

AutonomyLevel = Literal["observe_only", "safe_autopilot", "strict_approval"]
BriefWeekday = Literal["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
AutonomyActionKind = Literal[
    "send_invoice_reminder",
    "offer_waitlist_slot",
    "confirm_open_booking",
    "dispatch_weekly_brief",
    "financial_proposal_blocked",
]
ExecutionMode = Literal[
    "autonomous_safe",
    "human_approved",
    "queued_for_approval",
    "blocked_by_policy",
]
ExecutionStatus = Literal["completed", "pending_approval", "rejected", "rolled_back", "failed"]
SignalSeverity = Literal["critical", "high", "medium", "positive"]

# Hard-enforced non-autonomous financial/contractual action names.
HUMAN_ONLY_FINANCIAL_ACTIONS = frozenset(
    {
        "approve_purchase_order",
        "create_stripe_payment_link",
        "issue_refund",
        "sign_contract",
        "post_ledger_adjustment",
        "delete_business_records",
    }
)

_SAFE_EMAIL_RE = re.compile(r"^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$")


@dataclass(frozen=True)
class AutonomyPolicyView:
    tenant_id: UUID
    autonomy_level: AutonomyLevel
    auto_confirm_open_bookings: bool
    auto_send_invoice_reminders: bool
    auto_offer_waitlist_slots: bool
    auto_send_weekly_brief: bool
    weekly_brief_day: BriefWeekday
    weekly_brief_email: str | None
    require_human_approval_over_cents: int
    updated_at: datetime | None


@dataclass(frozen=True)
class AutonomyExecutionView:
    id: UUID
    action_kind: AutonomyActionKind
    execution_mode: ExecutionMode
    target_reference: str
    summary: str
    details: dict[str, Any]
    status: ExecutionStatus
    created_at: datetime
    resolved_at: datetime | None


@dataclass(frozen=True)
class PredictiveSignal:
    severity: SignalSeverity
    category: str
    title: str
    metric_label: str
    recommendation: str
    action_path: str


@dataclass(frozen=True)
class PredictiveContext:
    tenant_id: UUID
    business_name: str
    period_days: int
    health_score: int
    headline: str
    signals: list[PredictiveSignal]
    metrics_snapshot: dict[str, Any]
    byok_config: TenantByokAiConfig | None
    recipient_email: str | None


@dataclass(frozen=True)
class PredictiveReportView:
    id: UUID
    period_days: int
    engine: AiEngine
    headline: str
    executive_summary: str
    health_score: int
    signals: list[PredictiveSignal]
    metrics_snapshot: dict[str, Any]
    emailed_to_masked: str | None
    created_at: datetime


def evaluate_autonomy_decision(
    policy: AutonomyPolicyView,
    *,
    requested_action: str,
    estimated_financial_impact_cents: int = 0,
) -> tuple[ExecutionMode, str]:
    """Deterministic trust-level evaluator: financial/contract mutations ALWAYS require a human."""
    if requested_action in HUMAN_ONLY_FINANCIAL_ACTIONS or estimated_financial_impact_cents > 0:
        return (
            "blocked_by_policy",
            "Human-in-the-Loop is permanently enforced for all financial and contractual mutations "
            "above $0.00.",
        )

    if policy.autonomy_level != "safe_autopilot":
        return (
            "queued_for_approval",
            f"Queued for owner approval under '{policy.autonomy_level}' mode.",
        )

    allow_map = {
        "confirm_open_booking": policy.auto_confirm_open_bookings,
        "send_invoice_reminder": policy.auto_send_invoice_reminders,
        "offer_waitlist_slot": policy.auto_offer_waitlist_slots,
        "dispatch_weekly_brief": policy.auto_send_weekly_brief,
    }
    if allow_map.get(requested_action, False):
        return (
            "autonomous_safe",
            "Approved for Safe Auto-Pilot (routine, reversible, zero financial mutation).",
        )
    return (
        "queued_for_approval",
        f"Routine toggle for '{requested_action}' is disabled; queued for owner review.",
    )


def default_autonomy_policy(tenant_id: UUID) -> AutonomyPolicyView:
    return AutonomyPolicyView(
        tenant_id=tenant_id,
        autonomy_level="observe_only",
        auto_confirm_open_bookings=False,
        auto_send_invoice_reminders=False,
        auto_offer_waitlist_slots=False,
        auto_send_weekly_brief=True,
        weekly_brief_day="monday",
        weekly_brief_email=None,
        require_human_approval_over_cents=0,
        updated_at=None,
    )


def _row_to_policy(r: dict[str, Any]) -> AutonomyPolicyView:
    return AutonomyPolicyView(
        tenant_id=UUID(str(r["tenant_id"])),
        autonomy_level=r["autonomy_level"],
        auto_confirm_open_bookings=bool(r["auto_confirm_open_bookings"]),
        auto_send_invoice_reminders=bool(r["auto_send_invoice_reminders"]),
        auto_offer_waitlist_slots=bool(r["auto_offer_waitlist_slots"]),
        auto_send_weekly_brief=bool(r["auto_send_weekly_brief"]),
        weekly_brief_day=r["weekly_brief_day"],
        weekly_brief_email=str(r["weekly_brief_email"]) if r["weekly_brief_email"] else None,
        require_human_approval_over_cents=int(r["require_human_approval_over_cents"]),
        updated_at=r["updated_at"],
    )


def _row_to_execution(r: dict[str, Any]) -> AutonomyExecutionView:
    return AutonomyExecutionView(
        id=UUID(str(r["id"])),
        action_kind=r["action_kind"],
        execution_mode=r["execution_mode"],
        target_reference=str(r["target_reference"]),
        summary=str(r["summary"]),
        details=dict(r["details"] or {}),
        status=r["status"],
        created_at=r["created_at"],
        resolved_at=r["resolved_at"],
    )


async def get_autonomy_policy(conn: RuntimeConnection, *, tenant_id: UUID) -> AutonomyPolicyView:
    async with conn.cursor(row_factory=dict_row) as cur:
        await cur.execute(
            """
            SELECT tenant_id, autonomy_level, auto_confirm_open_bookings,
                   auto_send_invoice_reminders, auto_offer_waitlist_slots,
                   auto_send_weekly_brief, weekly_brief_day, weekly_brief_email,
                   require_human_approval_over_cents, updated_at
            FROM gba.ai_autonomy_policies
            WHERE tenant_id = %s
            """,
            (tenant_id,),
        )
        row = await cur.fetchone()
    if row is None:
        return default_autonomy_policy(tenant_id)
    return _row_to_policy(dict(row))


async def upsert_autonomy_policy(
    conn: RuntimeConnection,
    *,
    tenant_id: UUID,
    autonomy_level: AutonomyLevel,
    auto_confirm_open_bookings: bool,
    auto_send_invoice_reminders: bool,
    auto_offer_waitlist_slots: bool,
    auto_send_weekly_brief: bool,
    weekly_brief_day: BriefWeekday,
    weekly_brief_email: str | None,
    user_id: UUID | None,
) -> AutonomyPolicyView:
    clean_email: str | None = None
    if weekly_brief_email and weekly_brief_email.strip():
        cand = weekly_brief_email.strip().lower()
        if not _SAFE_EMAIL_RE.match(cand) or len(cand) > 160:
            raise ValueError("Weekly brief email must be a valid email address.")
        clean_email = cand

    async with conn.cursor(row_factory=dict_row) as cur:
        await cur.execute(
            """
            INSERT INTO gba.ai_autonomy_policies
                (tenant_id, autonomy_level, auto_confirm_open_bookings,
                 auto_send_invoice_reminders, auto_offer_waitlist_slots,
                 auto_send_weekly_brief, weekly_brief_day, weekly_brief_email,
                 require_human_approval_over_cents, updated_by_user_id)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, 0, %s)
            ON CONFLICT (tenant_id) DO UPDATE SET
                autonomy_level = EXCLUDED.autonomy_level,
                auto_confirm_open_bookings = EXCLUDED.auto_confirm_open_bookings,
                auto_send_invoice_reminders = EXCLUDED.auto_send_invoice_reminders,
                auto_offer_waitlist_slots = EXCLUDED.auto_offer_waitlist_slots,
                auto_send_weekly_brief = EXCLUDED.auto_send_weekly_brief,
                weekly_brief_day = EXCLUDED.weekly_brief_day,
                weekly_brief_email = EXCLUDED.weekly_brief_email,
                updated_by_user_id = EXCLUDED.updated_by_user_id,
                updated_at = now()
            RETURNING tenant_id, autonomy_level, auto_confirm_open_bookings,
                      auto_send_invoice_reminders, auto_offer_waitlist_slots,
                      auto_send_weekly_brief, weekly_brief_day, weekly_brief_email,
                      require_human_approval_over_cents, updated_at
            """,
            (
                tenant_id,
                autonomy_level,
                auto_confirm_open_bookings,
                auto_send_invoice_reminders,
                auto_offer_waitlist_slots,
                auto_send_weekly_brief,
                weekly_brief_day,
                clean_email,
                user_id,
            ),
        )
        row = await cur.fetchone()
    if row is None:
        raise RuntimeError("Failed to persist AI autonomy policy.")
    return _row_to_policy(dict(row))


async def list_autonomy_executions(
    conn: RuntimeConnection, *, tenant_id: UUID, limit: int = 25
) -> list[AutonomyExecutionView]:
    async with conn.cursor(row_factory=dict_row) as cur:
        await cur.execute(
            """
            SELECT id, action_kind, execution_mode, target_reference, summary,
                   details, status, created_at, resolved_at
            FROM gba.ai_autonomy_executions
            WHERE tenant_id = %s
            ORDER BY created_at DESC
            LIMIT %s
            """,
            (tenant_id, max(1, min(limit, 100))),
        )
        rows = await cur.fetchall()
    return [_row_to_execution(dict(r)) for r in rows]


async def _insert_execution(
    conn: RuntimeConnection,
    *,
    tenant_id: UUID,
    action_kind: AutonomyActionKind,
    execution_mode: ExecutionMode,
    target_reference: str,
    summary: str,
    details: dict[str, Any],
    status: ExecutionStatus,
    user_id: UUID | None,
) -> AutonomyExecutionView:
    async with conn.cursor(row_factory=dict_row) as cur:
        await cur.execute(
            """
            INSERT INTO gba.ai_autonomy_executions
                (tenant_id, action_kind, execution_mode, target_reference,
                 summary, details, status, triggered_by_user_id, resolved_at)
            VALUES (
                %s, %s, %s, %s, %s, %s, %s, %s,
                CASE WHEN %s = 'completed' THEN now() ELSE NULL END
            )
            RETURNING id, action_kind, execution_mode, target_reference, summary,
                      details, status, created_at, resolved_at
            """,
            (
                tenant_id,
                action_kind,
                execution_mode,
                target_reference[:160],
                summary[:500],
                Jsonb(details),
                status,
                user_id,
                status,
            ),
        )
        row = await cur.fetchone()
    if row is None:
        raise RuntimeError("Failed to record AI autonomy execution.")
    return _row_to_execution(dict(row))


async def run_safe_autonomy_cycle(
    conn: RuntimeConnection,
    *,
    tenant_id: UUID,
    user_id: UUID | None,
) -> list[AutonomyExecutionView]:
    """Inspect live overdue AR, waitlist demand, and open holds under tenant trust policy."""
    policy = await get_autonomy_policy(conn, tenant_id=tenant_id)
    created: list[AutonomyExecutionView] = []

    # 1. Overdue AR items (routine payment reminder — zero financial mutation)
    aging = await build_tenant_aging_report(
        conn, tenant_id=tenant_id, as_of=datetime.now(UTC).date()
    )
    overdue_ar = [it for it in aging.items if it.side == "AR" and it.days_past_due > 0][:3]
    for item in overdue_ar:
        mode, reason = evaluate_autonomy_decision(
            policy, requested_action="send_invoice_reminder", estimated_financial_impact_cents=0
        )
        status: ExecutionStatus = "completed" if mode == "autonomous_safe" else "pending_approval"
        usd = item.amount_cents / 100
        summary = (
            f"Overdue AR reminder for {item.reference_number} ({item.counterparty_name}, "
            f"${usd:,.2f}, {item.days_past_due}d past due). {reason}"
        )
        created.append(
            await _insert_execution(
                conn,
                tenant_id=tenant_id,
                action_kind="send_invoice_reminder",
                execution_mode=mode,
                target_reference=item.reference_number,
                summary=summary,
                details={
                    "counterparty": item.counterparty_name,
                    "amount_cents": item.amount_cents,
                    "days_past_due": item.days_past_due,
                },
                status=status,
                user_id=user_id,
            )
        )

    # 2. Waiting waitlist entries (routine slot offer)
    async with conn.cursor(row_factory=dict_row) as cur:
        await cur.execute(
            """
            SELECT id, customer_name, preferred_day
            FROM gba.waitlist_entries
            WHERE tenant_id = %s AND status = 'waiting'
            ORDER BY created_at ASC
            LIMIT 2
            """,
            (tenant_id,),
        )
        wait_rows = await cur.fetchall()
    for wr in wait_rows:
        mode, reason = evaluate_autonomy_decision(
            policy, requested_action="offer_waitlist_slot", estimated_financial_impact_cents=0
        )
        status = "completed" if mode == "autonomous_safe" else "pending_approval"
        ref = f"WL-{str(wr['id'])[:8]}"
        summary = (
            f"Waitlist slot outreach prepared for {wr['customer_name']} "
            f"(preferred {wr['preferred_day']}). {reason}"
        )
        created.append(
            await _insert_execution(
                conn,
                tenant_id=tenant_id,
                action_kind="offer_waitlist_slot",
                execution_mode=mode,
                target_reference=ref,
                summary=summary,
                details={"waitlist_id": str(wr["id"]), "preferred_day": str(wr["preferred_day"])},
                status=status,
                user_id=user_id,
            )
        )

    # 3. Any pending PO approvals (STRICTLY Human-in-the-Loop — never autonomous!)
    async with conn.cursor(row_factory=dict_row) as cur:
        await cur.execute(
            """
            SELECT id, po_number, vendor_name, total_cents
            FROM gba.purchase_orders
            WHERE tenant_id = %s AND status = 'pending_approval'
            ORDER BY created_at DESC
            LIMIT 2
            """,
            (tenant_id,),
        )
        po_rows = await cur.fetchall()
    for pr in po_rows:
        mode, reason = evaluate_autonomy_decision(
            policy,
            requested_action="approve_purchase_order",
            estimated_financial_impact_cents=int(pr["total_cents"]),
        )
        usd = int(pr["total_cents"]) / 100
        summary = (
            f"PO {pr['po_number']} ({pr['vendor_name']}, ${usd:,.2f}) held for human approval. "
            f"{reason}"
        )
        created.append(
            await _insert_execution(
                conn,
                tenant_id=tenant_id,
                action_kind="financial_proposal_blocked",
                execution_mode=mode,
                target_reference=str(pr["po_number"]),
                summary=summary,
                details={"purchase_order_id": str(pr["id"]), "total_cents": int(pr["total_cents"])},
                status="pending_approval",
                user_id=user_id,
            )
        )

    return created


async def decide_autonomy_execution(
    conn: RuntimeConnection,
    *,
    tenant_id: UUID,
    execution_id: UUID,
    decision: Literal["approve", "reject", "rollback"],
) -> AutonomyExecutionView:
    status_map: dict[str, tuple[ExecutionStatus, ExecutionMode | None]] = {
        "approve": ("completed", "human_approved"),
        "reject": ("rejected", None),
        "rollback": ("rolled_back", None),
    }
    next_status, next_mode = status_map[decision]
    async with conn.cursor(row_factory=dict_row) as cur:
        await cur.execute(
            """
            UPDATE gba.ai_autonomy_executions
            SET status = %s,
                execution_mode = COALESCE(%s, execution_mode),
                resolved_at = now()
            WHERE tenant_id = %s AND id = %s
            RETURNING id, action_kind, execution_mode, target_reference, summary,
                      details, status, created_at, resolved_at
            """,
            (next_status, next_mode, tenant_id, execution_id),
        )
        row = await cur.fetchone()
    if row is None:
        raise LookupError("AI autonomy execution record not found.")
    return _row_to_execution(dict(row))


def compute_predictive_health_and_signals(
    *,
    business_name: str,
    period_days: int,
    ar_total_cents: int,
    ar_overdue_cents: int,
    top_overdue_counterparty: str | None,
    po_variance_count: int,
    po_variance_cents: int,
    top_variance_vendor: str | None,
    quotes_sent_count: int,
    quotes_accepted_count: int,
    stale_quotes_count: int,
    stripe_open_count: int,
    stripe_open_cents: int,
    stripe_paid_cents: int,
    bookings_confirmed_count: int,
    bookings_cancelled_count: int,
    waitlist_count: int,
    waitlist_value_cents: int,
    failed_notifications_count: int,
) -> tuple[int, str, list[PredictiveSignal]]:
    """Pure deterministic CFO predictive scoring & anomaly extraction (zero hallucinations)."""
    score = 92
    signals: list[PredictiveSignal] = []

    if ar_overdue_cents > 0:
        overdue_pct = int((ar_overdue_cents * 100) / max(ar_total_cents, 1))
        penalty = 18 if overdue_pct >= 30 else 10
        score -= penalty
        who = f" led by {top_overdue_counterparty}" if top_overdue_counterparty else ""
        signals.append(
            PredictiveSignal(
                severity="critical" if overdue_pct >= 30 else "high",
                category="cashflow_ar",
                title=(
                    f"Overdue Accounts Receivable: ${ar_overdue_cents / 100:,.2f} ({overdue_pct}%)"
                ),
                metric_label=f"${ar_overdue_cents / 100:,.2f} past due",
                recommendation=(
                    f"Prioritize collection{who}. Enable Smart Autonomy invoice reminders "
                    "or resend instant Stripe ACH portal links in Commercial & PO -> Aging."
                ),
                action_path="/commercial/",
            )
        )

    if po_variance_count > 0 or po_variance_cents != 0:
        score -= 14
        vendor_txt = f" with vendor {top_variance_vendor}" if top_variance_vendor else ""
        signals.append(
            PredictiveSignal(
                severity="high",
                category="margin_vendor_cost",
                title=(
                    f"Vendor Cost Variance Detected: {po_variance_count} PO(s), "
                    f"${abs(po_variance_cents) / 100:,.2f} delta"
                ),
                metric_label=f"{po_variance_count} mismatched PO(s)",
                recommendation=(
                    f"3-way match variance detected{vendor_txt}. Audit billed vs. received "
                    "quantities before authorizing settlement or shift volume to alternate vendors."
                ),
                action_path="/commercial/",
            )
        )

    if stripe_open_count > 0 and stripe_open_cents > 0:
        score -= 8
        signals.append(
            PredictiveSignal(
                severity="medium",
                category="payment_conversion",
                title=(
                    f"Uncollected Stripe Checkouts: {stripe_open_count} open link(s) "
                    f"(${stripe_open_cents / 100:,.2f})"
                ),
                metric_label=f"${stripe_open_cents / 100:,.2f} open",
                recommendation=(
                    "Follow up on pending checkout sessions in App Hub -> Stripe US Payments "
                    "to convert open USD balances with 0% AMARKAL commission."
                ),
                action_path="/integrations/",
            )
        )

    total_b = bookings_confirmed_count + bookings_cancelled_count
    if total_b >= 4:
        cancel_pct = int((bookings_cancelled_count * 100) / total_b)
        if cancel_pct >= 20:
            score -= 12
            signals.append(
                PredictiveSignal(
                    severity="high",
                    category="utilization_churn",
                    title=(
                        f"Elevated Cancellation Rate: {cancel_pct}% "
                        f"({bookings_cancelled_count}/{total_b})"
                    ),
                    metric_label=f"{cancel_pct}% cancelled",
                    recommendation=(
                        "Activate 24-hour automated reminders and waitlist backfill in Settings "
                        "to recover lost capacity automatically."
                    ),
                    action_path="/settings/",
                )
            )

    if stale_quotes_count > 0:
        score -= 6
        signals.append(
            PredictiveSignal(
                severity="medium",
                category="sales_velocity",
                title=f"{stale_quotes_count} Commercial Quote(s) Pending > 7 Days",
                metric_label=f"{quotes_accepted_count}/{max(quotes_sent_count, 1)} won",
                recommendation=(
                    "Resend B2B client portal links with electronic sign-off and instant ACH "
                    "option to shorten deal-to-cash cycle time."
                ),
                action_path="/commercial/",
            )
        )

    if waitlist_count > 0:
        signals.append(
            PredictiveSignal(
                severity="positive",
                category="demand_recovery",
                title=(
                    f"Recoverable Waitlist Demand: {waitlist_count} client(s) "
                    f"(${waitlist_value_cents / 100:,.2f})"
                ),
                metric_label=f"${waitlist_value_cents / 100:,.2f} upside",
                recommendation=(
                    "Enable Safe Auto-Pilot waitlist offers or trigger outreach in Settings -> "
                    "Waitlist to convert unmet demand immediately."
                ),
                action_path="/settings/",
            )
        )

    if failed_notifications_count > 0:
        score -= 6
        signals.append(
            PredictiveSignal(
                severity="medium",
                category="ops_reliability",
                title=f"{failed_notifications_count} Failed Outbox Notification(s)",
                metric_label=f"{failed_notifications_count} failed",
                recommendation=(
                    "Inspect Settings -> Notification Outbox to correct invalid recipient emails "
                    "or phone numbers so automated reminders reach clients reliably."
                ),
                action_path="/settings/",
            )
        )

    if not signals:
        signals.append(
            PredictiveSignal(
                severity="positive",
                category="healthy_baseline",
                title="Operations & Cashflow Baseline Healthy",
                metric_label=f"${stripe_paid_cents / 100:,.2f} collected ({period_days}d)",
                recommendation=(
                    f"{business_name} shows zero overdue AR, zero PO cost variances, and clean "
                    "delivery telemetry. Keep recurring retainers and weekly digests active."
                ),
                action_path="/overview/",
            )
        )

    clamped = max(15, min(100, score))
    top_title = signals[0].title
    headline = f"{business_name} ({period_days}d Health {clamped}/100): {top_title}"[:240]
    return clamped, headline, signals


async def gather_predictive_context(
    conn: AsyncConnection[Any],
    *,
    tenant_id: UUID,
    period_days: int = 30,
    environment: str = "local",
) -> PredictiveContext:
    """Gather all cross-domain predictive facts in one short FORCE-RLS read transaction."""
    since = datetime.now(UTC) - timedelta(days=period_days)
    stale_cutoff = datetime.now(UTC) - timedelta(days=7)

    policy = await get_autonomy_policy(conn, tenant_id=tenant_id)
    aging = await build_tenant_aging_report(
        conn, tenant_id=tenant_id, as_of=datetime.now(UTC).date()
    )
    ar_overdue_items = sorted(
        [it for it in aging.items if it.side == "AR" and it.days_past_due > 0],
        key=lambda x: x.amount_cents,
        reverse=True,
    )
    ar_overdue_cents = sum(it.amount_cents for it in ar_overdue_items)
    top_overdue_cp = ar_overdue_items[0].counterparty_name if ar_overdue_items else None

    async with conn.cursor(row_factory=dict_row) as cur:
        await cur.execute("SELECT display_name FROM gba.tenants WHERE id = %s", (tenant_id,))
        trow = await cur.fetchone()
        business_name = str(trow["display_name"]) if trow else "AMARKAL Business"

        await cur.execute(
            """
            SELECT
                count(*) FILTER (
                    WHERE three_way_match_status = 'variance' OR variance_cents <> 0
                ) AS var_cnt,
                coalesce(sum(variance_cents), 0) AS var_cents,
                (
                    SELECT vendor_name FROM gba.purchase_orders
                    WHERE tenant_id = %s
                      AND (three_way_match_status = 'variance' OR variance_cents <> 0)
                    ORDER BY abs(variance_cents) DESC
                    LIMIT 1
                ) AS top_vendor
            FROM gba.purchase_orders
            WHERE tenant_id = %s AND created_at >= %s
            """,
            (tenant_id, tenant_id, since),
        )
        porow = await cur.fetchone() or {"var_cnt": 0, "var_cents": 0, "top_vendor": None}

        await cur.execute(
            """
            SELECT
                count(*) FILTER (WHERE status IN ('sent', 'accepted', 'declined')) AS sent_cnt,
                count(*) FILTER (WHERE status = 'accepted') AS acc_cnt,
                count(*) FILTER (WHERE status = 'sent' AND created_at < %s) AS stale_cnt
            FROM gba.commercial_quotes
            WHERE tenant_id = %s AND created_at >= %s
            """,
            (stale_cutoff, tenant_id, since),
        )
        qrow = await cur.fetchone() or {"sent_cnt": 0, "acc_cnt": 0, "stale_cnt": 0}

        await cur.execute(
            """
            SELECT
                count(*) FILTER (WHERE status = 'open') AS open_cnt,
                coalesce(sum(amount_cents) FILTER (WHERE status = 'open'), 0) AS open_cents,
                coalesce(sum(amount_cents) FILTER (WHERE status = 'paid'), 0) AS paid_cents
            FROM gba.payment_sessions
            WHERE tenant_id = %s AND created_at >= %s
            """,
            (tenant_id, since),
        )
        prow = await cur.fetchone() or {"open_cnt": 0, "open_cents": 0, "paid_cents": 0}

        await cur.execute(
            """
            SELECT
                count(*) FILTER (WHERE status = 'CONFIRMED') AS conf_cnt,
                count(*) FILTER (WHERE status = 'CANCELLED') AS canc_cnt
            FROM gba.bookings
            WHERE tenant_id = %s AND created_at >= %s
            """,
            (tenant_id, since),
        )
        brow = await cur.fetchone() or {"conf_cnt": 0, "canc_cnt": 0}

        await cur.execute(
            """
            SELECT count(*) AS w_cnt, coalesce(sum(v.price_cents), 0) AS w_cents
            FROM gba.waitlist_entries w
            JOIN gba.service_variants v ON v.tenant_id = w.tenant_id AND v.id = w.variant_id
            WHERE w.tenant_id = %s AND w.status = 'waiting'
            """,
            (tenant_id,),
        )
        wrow = await cur.fetchone() or {"w_cnt": 0, "w_cents": 0}

        await cur.execute(
            """
            SELECT count(*) AS fail_cnt
            FROM gba.notification_outbox
            WHERE tenant_id = %s AND status IN ('failed', 'dead_lettered')
              AND created_at >= %s
            """,
            (tenant_id, since),
        )
        nrow = await cur.fetchone() or {"fail_cnt": 0}

    health_score, headline, signals = compute_predictive_health_and_signals(
        business_name=business_name,
        period_days=period_days,
        ar_total_cents=aging.ar.total_cents,
        ar_overdue_cents=ar_overdue_cents,
        top_overdue_counterparty=top_overdue_cp,
        po_variance_count=int(porow["var_cnt"]),
        po_variance_cents=int(porow["var_cents"]),
        top_variance_vendor=str(porow["top_vendor"]) if porow["top_vendor"] else None,
        quotes_sent_count=int(qrow["sent_cnt"]),
        quotes_accepted_count=int(qrow["acc_cnt"]),
        stale_quotes_count=int(qrow["stale_cnt"]),
        stripe_open_count=int(prow["open_cnt"]),
        stripe_open_cents=int(prow["open_cents"]),
        stripe_paid_cents=int(prow["paid_cents"]),
        bookings_confirmed_count=int(brow["conf_cnt"]),
        bookings_cancelled_count=int(brow["canc_cnt"]),
        waitlist_count=int(wrow["w_cnt"]),
        waitlist_value_cents=int(wrow["w_cents"]),
        failed_notifications_count=int(nrow["fail_cnt"]),
    )

    snapshot: dict[str, Any] = {
        "period_days": period_days,
        "ar_total_cents": aging.ar.total_cents,
        "ar_overdue_cents": ar_overdue_cents,
        "ap_total_cents": aging.ap.total_cents,
        "po_variance_count": int(porow["var_cnt"]),
        "po_variance_cents": int(porow["var_cents"]),
        "quotes_sent_count": int(qrow["sent_cnt"]),
        "quotes_accepted_count": int(qrow["acc_cnt"]),
        "stale_quotes_count": int(qrow["stale_cnt"]),
        "stripe_open_cents": int(prow["open_cents"]),
        "stripe_paid_cents": int(prow["paid_cents"]),
        "bookings_confirmed_count": int(brow["conf_cnt"]),
        "bookings_cancelled_count": int(brow["canc_cnt"]),
        "waitlist_count": int(wrow["w_cnt"]),
        "waitlist_value_cents": int(wrow["w_cents"]),
    }

    byok_cfg = await load_active_tenant_byok_ai(conn, tenant_id=tenant_id, environment=environment)
    return PredictiveContext(
        tenant_id=tenant_id,
        business_name=business_name,
        period_days=period_days,
        health_score=health_score,
        headline=headline,
        signals=signals,
        metrics_snapshot=snapshot,
        byok_config=byok_cfg,
        recipient_email=policy.weekly_brief_email,
    )


async def synthesize_predictive_narrative(ctx: PredictiveContext) -> tuple[AiEngine, str]:
    """Synthesize proactive CFO executive narrative strictly OUTSIDE any DB transaction."""
    payload = {
        "business_name": ctx.business_name,
        "period_days": ctx.period_days,
        "health_score": ctx.health_score,
        "metrics": ctx.metrics_snapshot,
        "signals": [
            {
                "severity": s.severity,
                "title": s.title,
                "metric": s.metric_label,
                "recommendation": s.recommendation,
            }
            for s in ctx.signals
        ],
    }
    synthesized = await asyncio.to_thread(
        _synthesize_reply_sync,
        (
            f"You are the Proactive AI CFO Advisor for {ctx.business_name} on AMARKAL Platform. "
            "Write a crisp 3-4 sentence executive predictive brief strictly citing ONLY the "
            "verified numbers and signals provided in JSON. Focus on margin protection, cashflow "
            "collection, and concrete actions for the coming week. Never invent data."
        ),
        payload,
        ctx.byok_config,
    )
    if synthesized:
        return synthesized[0], synthesized[1]

    top = ctx.signals[0]
    fallback = (
        f"AMARKAL Proactive Executive Brief ({ctx.period_days}d · Health {ctx.health_score}/100): "
        f"{top.title}. {top.recommendation} "
        f"Total collected via Stripe: ${ctx.metrics_snapshot['stripe_paid_cents'] / 100:,.2f} USD "
        f"with 0% AMARKAL platform commission."
    )
    return "grounded", fallback


async def persist_predictive_report(
    conn: RuntimeConnection,
    *,
    ctx: PredictiveContext,
    engine: AiEngine,
    executive_summary: str,
    emailed_to_raw: str | None,
    user_id: UUID | None,
) -> PredictiveReportView:
    masked_email: str | None = None
    if emailed_to_raw and EMAIL_RE.match(emailed_to_raw.strip()):
        masked_email, _ = validate_and_mask_recipient("email", emailed_to_raw.strip())
    signals_json = [
        {
            "severity": s.severity,
            "category": s.category,
            "title": s.title,
            "metric_label": s.metric_label,
            "recommendation": s.recommendation,
            "action_path": s.action_path,
        }
        for s in ctx.signals
    ]
    async with conn.cursor(row_factory=dict_row) as cur:
        await cur.execute(
            """
            INSERT INTO gba.predictive_insight_reports
                (tenant_id, period_days, engine, headline, executive_summary,
                 health_score, signals, metrics_snapshot, emailed_to_masked, generated_by_user_id)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING id, period_days, engine, headline, executive_summary, health_score,
                      signals, metrics_snapshot, emailed_to_masked, created_at
            """,
            (
                ctx.tenant_id,
                ctx.period_days,
                engine,
                ctx.headline,
                executive_summary[:2000],
                ctx.health_score,
                Jsonb(signals_json),
                Jsonb(ctx.metrics_snapshot),
                masked_email,
                user_id,
            ),
        )
        row = await cur.fetchone()
    if row is None:
        raise RuntimeError("Failed to persist predictive insight report.")
    return _row_to_report(dict(row))


def _row_to_report(r: dict[str, Any]) -> PredictiveReportView:
    raw_signals = r.get("signals") or []
    sigs = [
        PredictiveSignal(
            severity=s["severity"],
            category=str(s["category"]),
            title=str(s["title"]),
            metric_label=str(s["metric_label"]),
            recommendation=str(s["recommendation"]),
            action_path=str(s["action_path"]),
        )
        for s in raw_signals
        if isinstance(s, dict)
    ]
    return PredictiveReportView(
        id=UUID(str(r["id"])),
        period_days=int(r["period_days"]),
        engine=r["engine"],
        headline=str(r["headline"]),
        executive_summary=str(r["executive_summary"]),
        health_score=int(r["health_score"]),
        signals=sigs,
        metrics_snapshot=dict(r["metrics_snapshot"] or {}),
        emailed_to_masked=str(r["emailed_to_masked"]) if r["emailed_to_masked"] else None,
        created_at=r["created_at"],
    )


async def list_predictive_reports(
    conn: RuntimeConnection, *, tenant_id: UUID, limit: int = 10
) -> list[PredictiveReportView]:
    async with conn.cursor(row_factory=dict_row) as cur:
        await cur.execute(
            """
            SELECT id, period_days, engine, headline, executive_summary, health_score,
                   signals, metrics_snapshot, emailed_to_masked, created_at
            FROM gba.predictive_insight_reports
            WHERE tenant_id = %s
            ORDER BY created_at DESC
            LIMIT %s
            """,
            (tenant_id, max(1, min(limit, 50))),
        )
        rows = await cur.fetchall()
    return [_row_to_report(dict(r)) for r in rows]
