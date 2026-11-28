"""HTTP routes for AMARKAL v2.15.0 AI Smart Autonomy & Proactive Predictive Insights."""

from __future__ import annotations

import asyncio
from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from fastapi import APIRouter, HTTPException, Request, status
from pydantic import BaseModel, ConfigDict, Field

from gorgona_booking.ai_assistant.autonomy import (
    AutonomyActionKind,
    AutonomyExecutionView,
    AutonomyLevel,
    AutonomyPolicyView,
    BriefWeekday,
    ExecutionMode,
    ExecutionStatus,
    PredictiveReportView,
    SignalSeverity,
    build_predictive_webhook_payload,
    decide_autonomy_execution,
    dispatch_predictive_webhook,
    gather_predictive_context,
    get_autonomy_policy,
    list_active_tenant_webhooks,
    list_autonomy_executions,
    list_predictive_reports,
    persist_predictive_report,
    run_safe_autonomy_cycle,
    synthesize_predictive_narrative,
    upsert_autonomy_policy,
)
from gorgona_booking.ai_assistant.service import AiEngine
from gorgona_booking.api.businesses import CurrentPrincipal
from gorgona_booking.api.deps import runtime_pool
from gorgona_booking.api.request_id import get_request_id
from gorgona_booking.auth.permissions import Permission
from gorgona_booking.connectors.service import (
    PreparedWebhookTest,
    WebhookProbeOutcome,
    record_webhook_test_delivery,
    validate_public_webhook_url,
)
from gorgona_booking.notifications.service import EMAIL_RE, render_template
from gorgona_booking.notifications.transports import resolve_notification_transports
from gorgona_booking.tenancy.authorization import authorized_tenant

router = APIRouter(tags=["ai-autonomy"])


class AutonomyPolicyResponse(BaseModel):
    model_config = ConfigDict(frozen=True)
    autonomy_level: AutonomyLevel
    auto_confirm_open_bookings: bool
    auto_send_invoice_reminders: bool
    auto_offer_waitlist_slots: bool
    auto_send_weekly_brief: bool
    weekly_brief_day: BriefWeekday
    weekly_brief_email: str | None = None
    require_human_approval_over_cents: int
    updated_at: datetime | None = None


class AutonomyPolicyUpdateRequest(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    autonomy_level: AutonomyLevel
    auto_confirm_open_bookings: bool = False
    auto_send_invoice_reminders: bool = False
    auto_offer_waitlist_slots: bool = False
    auto_send_weekly_brief: bool = True
    weekly_brief_day: BriefWeekday = "monday"
    weekly_brief_email: str | None = Field(default=None, max_length=160)


class AutonomyExecutionResponse(BaseModel):
    model_config = ConfigDict(frozen=True)
    id: UUID
    action_kind: AutonomyActionKind
    execution_mode: ExecutionMode
    target_reference: str
    summary: str
    details: dict[str, Any]
    status: ExecutionStatus
    created_at: datetime
    resolved_at: datetime | None = None


class AutonomyDecisionRequest(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    decision: Literal["approve", "reject", "rollback"]


class PredictiveSignalResponse(BaseModel):
    model_config = ConfigDict(frozen=True)
    severity: SignalSeverity
    category: str
    title: str
    metric_label: str
    recommendation: str
    action_path: str


class PredictiveReportResponse(BaseModel):
    model_config = ConfigDict(frozen=True)
    id: UUID
    period_days: int
    engine: AiEngine
    headline: str
    executive_summary: str
    health_score: int
    signals: list[PredictiveSignalResponse]
    metrics_snapshot: dict[str, Any]
    emailed_to_masked: str | None = None
    created_at: datetime


class GeneratePredictiveReportRequest(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    period_days: int = Field(default=30, ge=7, le=90)
    send_email: bool = False
    recipient_email: str | None = Field(default=None, max_length=160)
    webhook_url: str | None = Field(default=None, max_length=500)
    broadcast_to_webhooks: bool = False


def _env_name(request: Request) -> str:
    settings = getattr(request.app.state, "settings", None)
    return settings.environment if settings is not None else "local"


def _base_url(request: Request) -> str:
    host = request.headers.get("host") or request.url.netloc
    hostname = host.split(":", 1)[0].lower()
    raw_scheme = request.headers.get("x-forwarded-proto") or request.url.scheme or "https"
    scheme = raw_scheme if hostname in ("127.0.0.1", "localhost") else "https"
    return f"{scheme}://{host}"


def _policy_resp(p: AutonomyPolicyView) -> AutonomyPolicyResponse:
    return AutonomyPolicyResponse(
        autonomy_level=p.autonomy_level,
        auto_confirm_open_bookings=p.auto_confirm_open_bookings,
        auto_send_invoice_reminders=p.auto_send_invoice_reminders,
        auto_offer_waitlist_slots=p.auto_offer_waitlist_slots,
        auto_send_weekly_brief=p.auto_send_weekly_brief,
        weekly_brief_day=p.weekly_brief_day,
        weekly_brief_email=p.weekly_brief_email,
        require_human_approval_over_cents=p.require_human_approval_over_cents,
        updated_at=p.updated_at,
    )


def _exec_resp(item: AutonomyExecutionView) -> AutonomyExecutionResponse:
    return AutonomyExecutionResponse(
        id=item.id,
        action_kind=item.action_kind,
        execution_mode=item.execution_mode,
        target_reference=item.target_reference,
        summary=item.summary,
        details=item.details,
        status=item.status,
        created_at=item.created_at,
        resolved_at=item.resolved_at,
    )


def _report_resp(r: PredictiveReportView) -> PredictiveReportResponse:
    return PredictiveReportResponse(
        id=r.id,
        period_days=r.period_days,
        engine=r.engine,
        headline=r.headline,
        executive_summary=r.executive_summary,
        health_score=r.health_score,
        signals=[
            PredictiveSignalResponse(
                severity=s.severity,
                category=s.category,
                title=s.title,
                metric_label=s.metric_label,
                recommendation=s.recommendation,
                action_path=s.action_path,
            )
            for s in r.signals
        ],
        metrics_snapshot=r.metrics_snapshot,
        emailed_to_masked=r.emailed_to_masked,
        created_at=r.created_at,
    )


@router.get(
    "/v1/businesses/{business_id}/ai-autonomy/policy",
    response_model=AutonomyPolicyResponse,
)
async def get_ai_autonomy_policy_route(
    business_id: UUID,
    request: Request,
    principal: CurrentPrincipal,
) -> AutonomyPolicyResponse:
    async with authorized_tenant(
        runtime_pool(request),
        principal,
        business_id,
        Permission.BUSINESS_READ,
        request_id=get_request_id(request),
    ) as session:
        policy = await get_autonomy_policy(session.conn, tenant_id=business_id)
    return _policy_resp(policy)


@router.put(
    "/v1/businesses/{business_id}/ai-autonomy/policy",
    response_model=AutonomyPolicyResponse,
)
async def put_ai_autonomy_policy_route(
    business_id: UUID,
    body: AutonomyPolicyUpdateRequest,
    request: Request,
    principal: CurrentPrincipal,
) -> AutonomyPolicyResponse:
    try:
        async with authorized_tenant(
            runtime_pool(request),
            principal,
            business_id,
            Permission.BUSINESS_MANAGE,
            request_id=get_request_id(request),
        ) as session:
            policy = await upsert_autonomy_policy(
                session.conn,
                tenant_id=business_id,
                autonomy_level=body.autonomy_level,
                auto_confirm_open_bookings=body.auto_confirm_open_bookings,
                auto_send_invoice_reminders=body.auto_send_invoice_reminders,
                auto_offer_waitlist_slots=body.auto_offer_waitlist_slots,
                auto_send_weekly_brief=body.auto_send_weekly_brief,
                weekly_brief_day=body.weekly_brief_day,
                weekly_brief_email=body.weekly_brief_email,
                user_id=principal.user_id,
            )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc
    return _policy_resp(policy)


@router.get(
    "/v1/businesses/{business_id}/ai-autonomy/executions",
    response_model=list[AutonomyExecutionResponse],
)
async def get_ai_autonomy_executions_route(
    business_id: UUID,
    request: Request,
    principal: CurrentPrincipal,
) -> list[AutonomyExecutionResponse]:
    async with authorized_tenant(
        runtime_pool(request),
        principal,
        business_id,
        Permission.BUSINESS_READ,
        request_id=get_request_id(request),
    ) as session:
        rows = await list_autonomy_executions(session.conn, tenant_id=business_id)
    return [_exec_resp(item) for item in rows]


@router.post(
    "/v1/businesses/{business_id}/ai-autonomy/run-cycle",
    response_model=list[AutonomyExecutionResponse],
)
async def post_run_ai_autonomy_cycle_route(
    business_id: UUID,
    request: Request,
    principal: CurrentPrincipal,
) -> list[AutonomyExecutionResponse]:
    async with authorized_tenant(
        runtime_pool(request),
        principal,
        business_id,
        Permission.BUSINESS_MANAGE,
        request_id=get_request_id(request),
    ) as session:
        created = await run_safe_autonomy_cycle(
            session.conn, tenant_id=business_id, user_id=principal.user_id
        )
    return [_exec_resp(item) for item in created]


@router.post(
    "/v1/businesses/{business_id}/ai-autonomy/executions/{execution_id}/decision",
    response_model=AutonomyExecutionResponse,
)
async def post_ai_autonomy_decision_route(
    business_id: UUID,
    execution_id: UUID,
    body: AutonomyDecisionRequest,
    request: Request,
    principal: CurrentPrincipal,
) -> AutonomyExecutionResponse:
    try:
        async with authorized_tenant(
            runtime_pool(request),
            principal,
            business_id,
            Permission.BUSINESS_MANAGE,
            request_id=get_request_id(request),
        ) as session:
            item = await decide_autonomy_execution(
                session.conn,
                tenant_id=business_id,
                execution_id=execution_id,
                decision=body.decision,
            )
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    return _exec_resp(item)


@router.get(
    "/v1/businesses/{business_id}/ai-autonomy/predictive-reports",
    response_model=list[PredictiveReportResponse],
)
async def get_predictive_reports_route(
    business_id: UUID,
    request: Request,
    principal: CurrentPrincipal,
) -> list[PredictiveReportResponse]:
    async with authorized_tenant(
        runtime_pool(request),
        principal,
        business_id,
        Permission.BUSINESS_READ,
        request_id=get_request_id(request),
    ) as session:
        rows = await list_predictive_reports(session.conn, tenant_id=business_id)
    return [_report_resp(r) for r in rows]


@router.post(
    "/v1/businesses/{business_id}/ai-autonomy/predictive-reports/generate",
    response_model=PredictiveReportResponse,
    status_code=status.HTTP_201_CREATED,
)
async def post_generate_predictive_report_route(
    business_id: UUID,
    body: GeneratePredictiveReportRequest,
    request: Request,
    principal: CurrentPrincipal,
) -> PredictiveReportResponse:
    env_name = _env_name(request)
    clean_webhook_url: str | None = None
    if body.webhook_url and body.webhook_url.strip():
        try:
            clean_webhook_url = validate_public_webhook_url(
                body.webhook_url.strip(), resolve_dns=False
            )
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
            ) from exc

    tenant_webhooks: list[tuple[UUID, str, str]] = []
    async with authorized_tenant(
        runtime_pool(request),
        principal,
        business_id,
        Permission.BUSINESS_MANAGE,
        request_id=get_request_id(request),
    ) as session:
        ctx = await gather_predictive_context(
            session.conn,
            tenant_id=business_id,
            period_days=body.period_days,
            environment=env_name,
        )
        if body.broadcast_to_webhooks:
            tenant_webhooks = await list_active_tenant_webhooks(session.conn, tenant_id=business_id)

    # Strictly OUTSIDE any DB transaction: run optional LLM synthesis, SMTP, and HTTPS webhooks.
    engine, narrative = await synthesize_predictive_narrative(ctx)
    action_url = f"{_base_url(request)}/overview/"
    emailed_to: str | None = None
    target_email = (body.recipient_email or ctx.recipient_email or "").strip()
    if body.send_email and target_email:
        if not EMAIL_RE.match(target_email):
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Invalid recipient email for executive brief.",
            )
        subj, text_body = render_template(
            "predictive_weekly_brief",
            {
                "business_name": ctx.business_name,
                "reference": f"Health {ctx.health_score}/100",
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
                    idempotency_key=f"predictive-{business_id}-{ctx.health_score}",
                )
                emailed_to = target_email
            except Exception:
                emailed_to = None

    webhook_attempted = 0
    webhook_delivered = 0
    recorded_deliveries: list[tuple[UUID, PreparedWebhookTest, WebhookProbeOutcome]] = []
    if clean_webhook_url or tenant_webhooks:
        wh_payload = build_predictive_webhook_payload(
            ctx=ctx,
            engine=engine,
            executive_summary=narrative,
            action_url=action_url,
        )
        if clean_webhook_url:
            webhook_attempted += 1
            outcome, _ = await dispatch_predictive_webhook(clean_webhook_url, wh_payload)
            if outcome.status == "delivered":
                webhook_delivered += 1
        for ep_id, ep_url, ep_secret in tenant_webhooks:
            webhook_attempted += 1
            outcome, sig_hdr = await dispatch_predictive_webhook(
                ep_url, wh_payload, signing_secret_hash=ep_secret
            )
            if outcome.status == "delivered":
                webhook_delivered += 1
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
    if webhook_attempted > 0:
        ctx.metrics_snapshot["webhook_attempted_count"] = webhook_attempted
        ctx.metrics_snapshot["webhook_delivered_count"] = webhook_delivered

    async with authorized_tenant(
        runtime_pool(request),
        principal,
        business_id,
        Permission.BUSINESS_MANAGE,
        request_id=get_request_id(request),
    ) as session:
        for ep_id, prepared, outcome in recorded_deliveries:
            await record_webhook_test_delivery(
                session.conn,
                tenant_id=business_id,
                endpoint_id=ep_id,
                prepared=prepared,
                outcome=outcome,
                event_type="ai.predictive_brief.generated",
            )
        report = await persist_predictive_report(
            session.conn,
            ctx=ctx,
            engine=engine,
            executive_summary=narrative,
            emailed_to_raw=emailed_to,
            user_id=principal.user_id,
        )
    return _report_resp(report)
