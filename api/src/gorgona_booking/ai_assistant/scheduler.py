"""Autonomous Weekly Proactive Brief & Safe Auto-Pilot Scheduler (AMARKAL v2.23.0).

Designed to run safely as a Cloud Run Job or cron task under `gba_runtime` (no SECURITY DEFINER):
- Resolves target tenants strictly via explicit `--tenant-id`, `GBA_SCHEDULED_TENANT_IDS`, or
  `--host` (using the reviewed `resolve_tenant_by_host` helper — zero cross-company table scans).
- Processes each tenant strictly inside its own isolated `tenant_transaction` (`FORCE RLS`).
- Enforces 6-day idempotency so hourly or daily scheduler triggers never send duplicate briefs.
- Executes LLM narration, SMTP email, and HTTPS webhook broadcasts strictly OUTSIDE DB transactions.

Usage:
    python -m gorgona_booking.ai_assistant.scheduler --tenant-id <uuid> [--dry-run] [--force]
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import os
import sys
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import UUID

from psycopg.rows import dict_row

from gorgona_booking.ai_assistant.autonomy import (
    AutonomyPolicyView,
    BriefWeekday,
    _insert_execution,
    build_predictive_webhook_payload,
    dispatch_predictive_webhook,
    gather_predictive_context,
    get_autonomy_policy,
    list_active_tenant_webhooks,
    persist_predictive_report,
    run_safe_autonomy_cycle,
    synthesize_predictive_narrative,
)
from gorgona_booking.connectors.service import (
    PreparedWebhookTest,
    WebhookProbeOutcome,
    record_webhook_test_delivery,
)
from gorgona_booking.db.pool import (
    RuntimePool,
    create_runtime_pool,
    tenant_transaction,
)
from gorgona_booking.notifications.service import EMAIL_RE, render_template
from gorgona_booking.notifications.transports import resolve_notification_transports
from gorgona_booking.tenancy.resolver import resolve_tenant_by_host

_LOG = logging.getLogger(__name__)

_WEEKDAY_NAMES: tuple[BriefWeekday, ...] = (
    "monday",
    "tuesday",
    "wednesday",
    "thursday",
    "friday",
    "saturday",
    "sunday",
)
MIN_BRIEF_INTERVAL = timedelta(days=6)


@dataclass(frozen=True)
class TenantScheduleOutcome:
    tenant_id: UUID
    due: bool
    dispatched: bool
    emailed: bool
    webhooks_delivered: int
    autonomy_actions_created: int
    reason: str


def utc_weekday_name(now_utc: datetime) -> BriefWeekday:
    return _WEEKDAY_NAMES[now_utc.astimezone(UTC).weekday()]


def is_weekly_brief_due(
    policy: AutonomyPolicyView,
    *,
    last_report_at: datetime | None,
    now_utc: datetime | None = None,
) -> tuple[bool, str]:
    """Pure idempotent schedule check: returns (is_due, human_reason)."""
    now = (now_utc or datetime.now(UTC)).astimezone(UTC)
    if not policy.auto_send_weekly_brief:
        return False, "auto_send_weekly_brief disabled"
    today = utc_weekday_name(now)
    if today != policy.weekly_brief_day:
        return False, f"scheduled for {policy.weekly_brief_day} (today is {today})"
    if last_report_at is not None:
        last_utc = (
            last_report_at.replace(tzinfo=UTC)
            if last_report_at.tzinfo is None
            else last_report_at.astimezone(UTC)
        )
        if now - last_utc < MIN_BRIEF_INTERVAL:
            return False, "weekly brief already generated within last 6 days"
    return True, f"due on {today}"


def parse_target_tenant_ids(cli_ids: list[str], env_csv: str) -> list[UUID]:
    """Parse deduplicated tenant UUIDs from CLI flags and GBA_SCHEDULED_TENANT_IDS."""
    raw_items: list[str] = list(cli_ids)
    if env_csv.strip():
        raw_items.extend(part.strip() for part in env_csv.split(",") if part.strip())
    seen: set[UUID] = set()
    ordered: list[UUID] = []
    for item in raw_items:
        tid = UUID(item.strip())
        if tid not in seen:
            seen.add(tid)
            ordered.append(tid)
    return ordered


async def process_tenant_scheduled_brief(
    pool: RuntimePool,
    *,
    tenant_id: UUID,
    now_utc: datetime | None = None,
    base_url: str = "https://www.amarkal-platform.com",
    environment: str = "production",
    dry_run: bool = False,
    force: bool = False,
) -> TenantScheduleOutcome:
    """Evaluate and optionally dispatch one tenant's proactive weekly brief under FORCE RLS."""
    now = (now_utc or datetime.now(UTC)).astimezone(UTC)
    autonomy_count = 0

    async with tenant_transaction(pool, tenant_id) as conn:
        async with conn.cursor(row_factory=dict_row) as cur:
            await cur.execute(
                "SELECT status FROM gba.tenants WHERE id = %s",
                (tenant_id,),
            )
            trow = await cur.fetchone()
            if trow is None or str(trow["status"]) != "active":
                return TenantScheduleOutcome(
                    tenant_id=tenant_id,
                    due=False,
                    dispatched=False,
                    emailed=False,
                    webhooks_delivered=0,
                    autonomy_actions_created=0,
                    reason="tenant inactive or missing",
                )
            await cur.execute(
                """
                SELECT max(created_at) AS last_at
                FROM gba.predictive_insight_reports
                WHERE tenant_id = %s
                """,
                (tenant_id,),
            )
            rrow = await cur.fetchone()
            last_report_at: datetime | None = rrow["last_at"] if rrow else None

        policy = await get_autonomy_policy(conn, tenant_id=tenant_id)
        due, reason = is_weekly_brief_due(policy, last_report_at=last_report_at, now_utc=now)
        if not due and not force:
            return TenantScheduleOutcome(
                tenant_id=tenant_id,
                due=False,
                dispatched=False,
                emailed=False,
                webhooks_delivered=0,
                autonomy_actions_created=0,
                reason=reason,
            )
        if dry_run:
            return TenantScheduleOutcome(
                tenant_id=tenant_id,
                due=True,
                dispatched=False,
                emailed=False,
                webhooks_delivered=0,
                autonomy_actions_created=0,
                reason=f"dry-run ({reason})",
            )

        ctx = await gather_predictive_context(
            conn,
            tenant_id=tenant_id,
            period_days=7,
            environment=environment,
        )
        tenant_webhooks = await list_active_tenant_webhooks(conn, tenant_id=tenant_id)
        if policy.autonomy_level == "safe_autopilot":
            created_actions = await run_safe_autonomy_cycle(conn, tenant_id=tenant_id, user_id=None)
            autonomy_count = len(created_actions)

    # Strictly OUTSIDE any DB transaction: LLM synthesis, SMTP email, and HTTPS webhooks.
    engine, narrative = await synthesize_predictive_narrative(ctx)
    action_url = f"{base_url.rstrip('/')}/overview/"
    emailed_to: str | None = None
    target_email = (policy.weekly_brief_email or "").strip()
    if target_email and EMAIL_RE.match(target_email):
        subj, text_body = render_template(
            "predictive_weekly_brief",
            {
                "business_name": ctx.business_name,
                "reference": f"Weekly Health {ctx.health_score}/100",
                "amount": narrative,
                "action_url": action_url,
            },
        )
        transports, _ = resolve_notification_transports()
        email_transport = transports.get("email")
        if email_transport is not None:
            try:
                await asyncio.to_thread(
                    email_transport.send,
                    channel="email",
                    recipient=target_email,
                    subject=subj,
                    body=text_body,
                    idempotency_key=f"weekly-brief-{tenant_id}-{now.date().isoformat()}",
                )
                emailed_to = target_email
            except Exception:
                _LOG.warning("Weekly brief email failed for tenant %s", tenant_id, exc_info=True)

    wh_delivered = 0
    recorded_deliveries: list[tuple[UUID, PreparedWebhookTest, WebhookProbeOutcome]] = []
    if tenant_webhooks:
        wh_payload = build_predictive_webhook_payload(
            ctx=ctx,
            engine=engine,
            executive_summary=narrative,
            action_url=action_url,
        )
        for ep_id, ep_url, ep_secret in tenant_webhooks:
            outcome, sig_hdr = await dispatch_predictive_webhook(
                ep_url, wh_payload, signing_secret_hash=ep_secret
            )
            if outcome.status == "delivered":
                wh_delivered += 1
            recorded_deliveries.append(
                (
                    ep_id,
                    PreparedWebhookTest(
                        url=ep_url,
                        payload=wh_payload,
                        signature_header=sig_hdr or "v1=unsigned",
                    ),
                    outcome,
                )
            )
        ctx.metrics_snapshot["webhook_attempted_count"] = len(tenant_webhooks)
        ctx.metrics_snapshot["webhook_delivered_count"] = wh_delivered

    async with tenant_transaction(pool, tenant_id) as conn:
        for ep_id, prepared, outcome in recorded_deliveries:
            await record_webhook_test_delivery(
                conn,
                tenant_id=tenant_id,
                endpoint_id=ep_id,
                prepared=prepared,
                outcome=outcome,
                event_type="ai.predictive_brief.generated",
            )
        report = await persist_predictive_report(
            conn,
            ctx=ctx,
            engine=engine,
            executive_summary=narrative,
            emailed_to_raw=emailed_to,
            user_id=None,
        )
        await _insert_execution(
            conn,
            tenant_id=tenant_id,
            action_kind="dispatch_weekly_brief",
            execution_mode="autonomous_safe",
            target_reference=f"BRIEF-{now.date().isoformat()}",
            summary=(
                f"Automated weekly brief dispatched (Health {report.health_score}/100, "
                f"email={'yes' if emailed_to else 'no'}, webhooks={wh_delivered})."
            ),
            details={
                "report_id": str(report.id),
                "health_score": report.health_score,
                "emailed": bool(emailed_to),
                "webhooks_delivered": wh_delivered,
            },
            status="completed",
            user_id=None,
        )

    return TenantScheduleOutcome(
        tenant_id=tenant_id,
        due=True,
        dispatched=True,
        emailed=bool(emailed_to),
        webhooks_delivered=wh_delivered,
        autonomy_actions_created=autonomy_count,
        reason="dispatched",
    )


async def run_weekly_brief_scheduler(
    *,
    conninfo: str,
    base_url: str,
    environment: str,
    tenant_ids: list[UUID],
    hosts: list[str] | None = None,
    dry_run: bool = False,
    force: bool = False,
) -> list[TenantScheduleOutcome]:
    pool = create_runtime_pool(conninfo, min_size=1, max_size=4)
    await pool.open()
    try:
        resolved: list[UUID] = list(tenant_ids)
        seen = set(resolved)
        for raw_host in hosts or []:
            tid = await resolve_tenant_by_host(pool, raw_host)
            if tid not in seen:
                seen.add(tid)
                resolved.append(tid)
        outcomes: list[TenantScheduleOutcome] = []
        for tid in resolved:
            try:
                res = await process_tenant_scheduled_brief(
                    pool,
                    tenant_id=tid,
                    base_url=base_url,
                    environment=environment,
                    dry_run=dry_run,
                    force=force,
                )
                outcomes.append(res)
            except Exception:
                _LOG.exception("Scheduled weekly brief failed for tenant %s", tid)
        return outcomes
    finally:
        await pool.close()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Run AMARKAL autonomous weekly predictive brief scheduler."
    )
    parser.add_argument("--dry-run", action="store_true", help="Evaluate schedules without sending")
    parser.add_argument(
        "--force",
        action="store_true",
        help="Dispatch immediately regardless of weekday or 6-day cooldown",
    )
    parser.add_argument(
        "--tenant-id",
        action="append",
        default=[],
        help="Target tenant UUID (repeatable; or set GBA_SCHEDULED_TENANT_IDS)",
    )
    parser.add_argument(
        "--host",
        action="append",
        default=[],
        help="Target live business hostname resolved via tenant_hosts (repeatable)",
    )
    args = parser.parse_args(argv)
    conninfo = os.environ.get("GBA_DATABASE_URL", "").strip()
    if not conninfo:
        sys.stderr.write("GBA_DATABASE_URL is required.\n")
        return 2
    base_url = os.environ.get("GBA_PUBLIC_BASE_URL", "https://www.amarkal-platform.com").strip()
    environment = os.environ.get("GBA_ENVIRONMENT", "production").strip() or "production"
    target_ids = parse_target_tenant_ids(
        list(args.tenant_id), os.environ.get("GBA_SCHEDULED_TENANT_IDS", "")
    )
    target_hosts = [h.strip() for h in args.host if h.strip()]
    if not target_ids and not target_hosts:
        sys.stderr.write("Provide --tenant-id, --host, or GBA_SCHEDULED_TENANT_IDS.\n")
        return 2
    outcomes = asyncio.run(
        run_weekly_brief_scheduler(
            conninfo=conninfo,
            base_url=base_url,
            environment=environment,
            tenant_ids=target_ids,
            hosts=target_hosts,
            dry_run=args.dry_run,
            force=args.force,
        )
    )
    dispatched = sum(1 for o in outcomes if o.dispatched)
    due = sum(1 for o in outcomes if o.due)
    sys.stdout.write(
        f"AMARKAL weekly brief scheduler complete: scanned={len(outcomes)} "
        f"due={due} dispatched={dispatched}\n"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
