"""Governed Human-in-the-Loop AI Action Proposals for Owner AI Command Copilot.

Every proposal is strictly deterministic, scoped by `Permission.BUSINESS_MANAGE` + `FORCE RLS`,
and executes ONLY after explicit owner confirmation via `POST .../copilot/execute-action`.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal
from uuid import UUID

from psycopg import AsyncConnection

from gorgona_booking.ai_assistant.service import CopilotContext
from gorgona_booking.connectors.service import create_api_key
from gorgona_booking.growth.service import (
    export_business_snapshot,
    get_growth_settings,
    upsert_growth_settings,
)
from gorgona_booking.payments.stripe_service import (
    StripeRuntimeConfig,
    create_stripe_checkout_session,
)

ActionKind = Literal[
    "enable_growth_automation",
    "create_mcp_api_key",
    "create_stripe_payment_link",
    "export_business_snapshot",
]


@dataclass(frozen=True)
class ActionProposal:
    id: str
    kind: ActionKind
    title: str
    description: str
    impact_summary: str
    requires_permission: str
    params: dict[str, Any]


@dataclass(frozen=True)
class ActionExecutionResult:
    kind: ActionKind
    executed: bool
    summary: str
    result: dict[str, Any]


def build_action_proposals(ctx: CopilotContext) -> list[ActionProposal]:
    """Generate concrete, reversible, human-approved actions from live business metrics."""
    proposals: list[ActionProposal] = []
    m = ctx.metrics

    if not m.get("ai_assistant_enabled", True):
        proposals.append(
            ActionProposal(
                id="act-enable-growth-automation",
                kind="enable_growth_automation",
                title="Activate Growth Automation & AI Booking Assistant",
                description=(
                    "Enable 24h automated reminders, 28d rebooking cadence, waitlist auto-offer, "
                    "and the customer AI Booking Assistant in one click."
                ),
                impact_summary="Updates growth_settings for this business (reversible anytime).",
                requires_permission="business.manage",
                params={
                    "reminder_hours_before": 24,
                    "rebooking_days_after": 28,
                    "waitlist_auto_offer": True,
                    "ai_assistant_enabled": True,
                },
            )
        )

    if int(m.get("active_mcp_keys_count") or 0) == 0:
        proposals.append(
            ActionProposal(
                id="act-create-mcp-key",
                kind="create_mcp_api_key",
                title="Generate Native MCP API Key (Claude / ChatGPT / Agents)",
                description=(
                    "Issue a scoped FORCE-RLS API key (mcp:read, catalog:read, bookings:read) "
                    "so your AI agents can query live business data via /v1/mcp."
                ),
                impact_summary="Creates 1 revocable scoped API key in App Hub.",
                requires_permission="business.manage",
                params={
                    "name": "AMARKAL AI Agent MCP",
                    "scopes": ["mcp:read", "catalog:read", "bookings:read"],
                },
            )
        )

    proposals.append(
        ActionProposal(
            id="act-create-stripe-link",
            kind="create_stripe_payment_link",
            title="Create Live Stripe US Payment Link ($150.00)",
            description=(
                "Generate an instant USD Stripe Checkout link supporting Cards, Apple Pay, "
                "Google Pay, and US Bank ACH with 0% AMARKAL platform commission."
            ),
            impact_summary="Creates 1 open Stripe Checkout session under this business.",
            requires_permission="finance.manage",
            params={
                "amount_cents": 15000,
                "description": f"{ctx.business_name} — Direct Service Payment",
                "allow_ach": True,
            },
        )
    )

    proposals.append(
        ActionProposal(
            id="act-export-snapshot",
            kind="export_business_snapshot",
            title="Export Portable Zero-Lock-In Business JSON",
            description=(
                "Generate a full portable JSON snapshot of your business profile, locations, "
                "services, staff, Stripe summary, and connectors."
            ),
            impact_summary="Read-only export; zero secrets included.",
            requires_permission="business.manage",
            params={},
        )
    )
    return proposals


async def execute_governed_action(
    conn: AsyncConnection[Any],
    *,
    tenant_id: UUID,
    user_id: UUID,
    kind: ActionKind,
    params: dict[str, Any],
    return_base_url: str,
) -> ActionExecutionResult:
    """Execute one explicitly approved Copilot action inside an authorized tenant transaction."""
    if kind == "enable_growth_automation":
        current = await get_growth_settings(conn, tenant_id=tenant_id)
        updated = await upsert_growth_settings(
            conn,
            tenant_id=tenant_id,
            google_review_url=current.google_review_url,
            reminder_hours_before=int(params.get("reminder_hours_before", 24)),
            review_delay_hours=current.review_delay_hours,
            rebooking_days_after=int(params.get("rebooking_days_after", 28)),
            waitlist_auto_offer=True,
            ai_assistant_enabled=True,
            ai_assistant_tone="warm_professional",
            updated_by_user_id=user_id,
        )
        return ActionExecutionResult(
            kind=kind,
            executed=True,
            summary=(
                f"Growth automation activated: {updated.reminder_hours_before}h reminders, "
                f"{updated.rebooking_days_after}d rebooking, waitlist auto-offer & AI Assistant ON."
            ),
            result={
                "reminder_hours_before": updated.reminder_hours_before,
                "rebooking_days_after": updated.rebooking_days_after,
                "waitlist_auto_offer": updated.waitlist_auto_offer,
                "ai_assistant_enabled": updated.ai_assistant_enabled,
            },
        )

    if kind == "create_mcp_api_key":
        key_name = str(params.get("name") or "AMARKAL AI Agent MCP").strip()[:120]
        raw_scopes = params.get("scopes")
        scopes = (
            [str(s) for s in raw_scopes]
            if isinstance(raw_scopes, list) and raw_scopes
            else ["mcp:read", "catalog:read", "bookings:read"]
        )
        row, raw_secret = await create_api_key(
            conn,
            tenant_id=tenant_id,
            name=key_name,
            scopes=scopes,
            user_id=user_id,
        )
        return ActionExecutionResult(
            kind=kind,
            executed=True,
            summary=(
                f"Created Native MCP API key '{row['name']}'. Copy your secret token once — "
                "it will not be shown again."
            ),
            result={
                "key_id": str(row["id"]),
                "name": str(row["name"]),
                "scopes": list(row["scopes"]),
                "secret_token": raw_secret,
                "mcp_endpoint": f"{return_base_url.rstrip('/')}/v1/mcp",
            },
        )

    if kind == "create_stripe_payment_link":
        cfg = StripeRuntimeConfig.from_env()
        amount_cents = int(params.get("amount_cents", 15000))
        desc = str(params.get("description") or "AMARKAL Direct Payment").strip()[:300]
        allow_ach = bool(params.get("allow_ach", True))
        rec = await create_stripe_checkout_session(
            conn,
            config=cfg,
            tenant_id=tenant_id,
            amount_cents=amount_cents,
            description=desc,
            reference_kind="custom",
            reference_id=None,
            customer_name="",
            customer_email=None,
            success_url=f"{return_base_url.rstrip('/')}/integrations/?payment=success",
            cancel_url=f"{return_base_url.rstrip('/')}/integrations/?payment=cancelled",
            allow_ach=allow_ach,
            connected_account_id=None,
            created_by_user_id=user_id,
        )
        return ActionExecutionResult(
            kind=kind,
            executed=True,
            summary=(
                f"Stripe Checkout link created for ${rec.amount_cents / 100:,.2f} USD "
                f"({'Live' if rec.livemode else 'Test'} mode)."
            ),
            result={
                "session_id": str(rec.id),
                "amount_cents": rec.amount_cents,
                "livemode": rec.livemode,
                "checkout_url": rec.checkout_url,
            },
        )

    if kind == "export_business_snapshot":
        cfg = StripeRuntimeConfig.from_env()
        snapshot = await export_business_snapshot(
            conn,
            tenant_id=tenant_id,
            stripe_configured=cfg.configured,
            stripe_livemode=cfg.livemode,
        )
        return ActionExecutionResult(
            kind=kind,
            executed=True,
            summary=(
                f"Exported portable snapshot for {snapshot['business']['display_name']} "
                f"({len(snapshot['services'])} services, {len(snapshot['staff'])} staff)."
            ),
            result={"snapshot": snapshot},
        )

    raise ValueError(f"Unsupported action kind: {kind}")
