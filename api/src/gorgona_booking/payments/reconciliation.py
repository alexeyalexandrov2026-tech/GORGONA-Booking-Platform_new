"""Stripe US Live <-> FIN-03 Financial Ledger Reconciliation & AMARKAL SaaS Billing Plans.

- Reconciliation compares live `gba.payment_sessions` (Stripe) against `gba.financial_documents`
  under `FORCE ROW LEVEL SECURITY` with zero silent assumptions.
- SaaS Billing exposes AMARKAL Platform's transparent, 0%-commission US subscription tiers
  backed directly by Stripe Subscriptions Checkout.
"""

from __future__ import annotations

import asyncio
import os
from dataclasses import dataclass
from typing import Any, Literal
from uuid import UUID, uuid7

import stripe
from psycopg import AsyncConnection
from psycopg.rows import dict_row

from gorgona_booking.payments.stripe_service import (
    StripePaymentError,
    StripeRuntimeConfig,
    validate_return_url,
)

SaasPlanId = Literal["starter", "growth", "scale"]


@dataclass(frozen=True)
class SaasPlanSpec:
    id: SaasPlanId
    name: str
    monthly_price_cents: int
    currency: Literal["USD"]
    transaction_commission_bps: Literal[0]
    tagline: str
    features: tuple[str, ...]
    stripe_price_env: str | None = None


AMARKAL_SAAS_PLANS: tuple[SaasPlanSpec, ...] = (
    SaasPlanSpec(
        id="starter",
        name="Starter",
        monthly_price_cents=0,
        currency="USD",
        transaction_commission_bps=0,
        tagline="Launch any US business with 0% commission and zero lock-in.",
        features=(
            "All 39 US NAICS industry presets",
            "0% platform commission — direct Stripe US payouts (Cards, Apple Pay, ACH)",
            "Resend transactional emails & Google Identity auth",
            "1-click Portable Business JSON Export anytime",
        ),
        stripe_price_env=None,
    ),
    SaasPlanSpec(
        id="growth",
        name="Growth",
        monthly_price_cents=4900,
        currency="USD",
        transaction_commission_bps=0,
        tagline="AI-native Business OS with unlimited locations, MCP, and automation.",
        features=(
            "Everything in Starter — still 0% transaction commission forever",
            "Cloudflare Llama 3.3 70B AI Business Architect & Command Copilot",
            "Native MCP Server v2.1 (7 semantic tools for Claude, ChatGPT, Gemini)",
            "Cloudflare R2 brand media, live unit economics & waitlist automation",
        ),
        stripe_price_env="GBA_STRIPE_PRICE_GROWTH",
    ),
    SaasPlanSpec(
        id="scale",
        name="Scale",
        monthly_price_cents=14900,
        currency="USD",
        transaction_commission_bps=0,
        tagline="Multi-entity US enterprise governance without $100K NetSuite fees.",
        features=(
            "Everything in Growth — 0% transaction commission at any volume",
            "Multi-entity holding & franchise governance + delegated staff grants",
            "Double-entry ledger (FIN-01..03) + Stripe <-> Ledger reconciliation",
            "Dedicated webhooks, custom domain onboarding & priority US support",
        ),
        stripe_price_env="GBA_STRIPE_PRICE_SCALE",
    ),
)
PLANS_BY_ID: dict[str, SaasPlanSpec] = {p.id: p for p in AMARKAL_SAAS_PLANS}


@dataclass(frozen=True)
class UnmatchedStripeSession:
    id: UUID
    provider_session_id: str
    amount_cents: int
    reference_kind: str
    reference_id: str | None
    description: str


@dataclass(frozen=True)
class StripeLedgerReconciliation:
    currency: Literal["USD"]
    stripe_paid_count: int
    stripe_paid_cents: int
    stripe_open_count: int
    stripe_open_cents: int
    stripe_refunded_count: int
    stripe_refunded_cents: int
    fin03_issued_invoices_count: int
    fin03_issued_total_cents: int
    matched_invoice_sessions_count: int
    unmatched_paid_sessions: tuple[UnmatchedStripeSession, ...]


async def reconcile_stripe_with_fin03(
    conn: AsyncConnection[Any],
    *,
    tenant_id: UUID,
) -> StripeLedgerReconciliation:
    """Compare live Stripe payment sessions with FIN-03 financial documents under FORCE RLS."""
    async with conn.cursor(row_factory=dict_row) as cur:
        await cur.execute(
            """
            SELECT
                count(*) FILTER (WHERE status = 'paid') AS paid_count,
                coalesce(sum(amount_cents) FILTER (WHERE status = 'paid'), 0) AS paid_cents,
                count(*) FILTER (WHERE status = 'open') AS open_count,
                coalesce(sum(amount_cents) FILTER (WHERE status = 'open'), 0) AS open_cents,
                count(*) FILTER (WHERE status = 'refunded') AS refunded_count,
                coalesce(sum(amount_cents) FILTER (WHERE status = 'refunded'), 0) AS refunded_cents
            FROM gba.payment_sessions
            WHERE tenant_id = %s
            """,
            (tenant_id,),
        )
        srow = await cur.fetchone() or {}

        await cur.execute(
            """
            SELECT
                count(*) AS issued_count,
                coalesce(sum(total_minor), 0) AS issued_minor
            FROM gba.financial_documents
            WHERE tenant_id = %s
              AND kind = 'invoice'
              AND status = 'issued'
              AND currency = 'USD'
            """,
            (tenant_id,),
        )
        frow = await cur.fetchone() or {}

        await cur.execute(
            """
            SELECT document_number, id::text AS doc_id
            FROM gba.financial_documents
            WHERE tenant_id = %s AND kind = 'invoice' AND status = 'issued'
            """,
            (tenant_id,),
        )
        invoice_refs: set[str] = set()
        for r in await cur.fetchall():
            if r.get("document_number"):
                invoice_refs.add(str(r["document_number"]).strip().lower())
            if r.get("doc_id"):
                invoice_refs.add(str(r["doc_id"]).strip().lower())

        await cur.execute(
            """
            SELECT id, provider_session_id, amount_cents, reference_kind, reference_id, description
            FROM gba.payment_sessions
            WHERE tenant_id = %s AND status = 'paid'
            ORDER BY created_at DESC
            LIMIT 100
            """,
            (tenant_id,),
        )
        paid_rows = await cur.fetchall()

    matched = 0
    unmatched: list[UnmatchedStripeSession] = []
    for r in paid_rows:
        ref = str(r["reference_id"] or "").strip().lower()
        if ref and ref in invoice_refs:
            matched += 1
        else:
            unmatched.append(
                UnmatchedStripeSession(
                    id=r["id"],
                    provider_session_id=str(r["provider_session_id"]),
                    amount_cents=int(r["amount_cents"]),
                    reference_kind=str(r["reference_kind"]),
                    reference_id=r["reference_id"],
                    description=str(r["description"]),
                )
            )

    return StripeLedgerReconciliation(
        currency="USD",
        stripe_paid_count=int(srow.get("paid_count") or 0),
        stripe_paid_cents=int(srow.get("paid_cents") or 0),
        stripe_open_count=int(srow.get("open_count") or 0),
        stripe_open_cents=int(srow.get("open_cents") or 0),
        stripe_refunded_count=int(srow.get("refunded_count") or 0),
        stripe_refunded_cents=int(srow.get("refunded_cents") or 0),
        fin03_issued_invoices_count=int(frow.get("issued_count") or 0),
        fin03_issued_total_cents=int(frow.get("issued_minor") or 0),
        matched_invoice_sessions_count=matched,
        unmatched_paid_sessions=tuple(unmatched[:25]),
    )


def _create_subscription_checkout_sync(
    *,
    api_key: str,
    plan: SaasPlanSpec,
    tenant_id: UUID,
    customer_email: str | None,
    success_url: str,
    cancel_url: str,
) -> dict[str, Any]:
    price_id = os.environ.get(plan.stripe_price_env or "", "").strip()
    if price_id:
        line_item: dict[str, Any] = {"price": price_id, "quantity": 1}
    else:
        line_item = {
            "price_data": {
                "currency": "usd",
                "unit_amount": plan.monthly_price_cents,
                "recurring": {"interval": "month"},
                "product_data": {
                    "name": f"AMARKAL Platform — {plan.name} Plan (0% Commission)",
                    "description": plan.tagline,
                },
            },
            "quantity": 1,
        }

    metadata = {
        "amarkal_saas_plan": plan.id,
        "gorgona_tenant_id": str(tenant_id),
    }
    params: dict[str, Any] = {
        "mode": "subscription",
        "payment_method_types": ["card"],
        "line_items": [line_item],
        "success_url": success_url,
        "cancel_url": cancel_url,
        "metadata": metadata,
        "subscription_data": {"metadata": metadata},
        "api_key": api_key,
        "idempotency_key": f"amarkal-sub-{tenant_id}-{plan.id}-{uuid7()}",
    }
    if customer_email:
        params["customer_email"] = customer_email
    try:
        session = stripe.checkout.Session.create(**params)
    except stripe.StripeError as exc:
        raise StripePaymentError(
            "STRIPE_SUBSCRIPTION_ERROR",
            exc.user_message or "Stripe could not start the subscription checkout.",
            status_code=502,
        ) from exc
    url = getattr(session, "url", None)
    sid = getattr(session, "id", None)
    if not url or not sid:
        raise StripePaymentError(
            "STRIPE_SUBSCRIPTION_ERROR",
            "Stripe did not return a subscription checkout URL.",
            status_code=502,
        )
    return {
        "session_id": str(sid),
        "checkout_url": str(url),
        "livemode": bool(getattr(session, "livemode", False)),
    }


async def create_saas_subscription_checkout(
    *,
    config: StripeRuntimeConfig,
    tenant_id: UUID,
    plan_id: SaasPlanId,
    customer_email: str | None,
    success_url: str,
    cancel_url: str,
) -> dict[str, Any]:
    plan = PLANS_BY_ID.get(plan_id)
    if plan is None or plan.monthly_price_cents <= 0:
        raise StripePaymentError(
            "INVALID_SAAS_PLAN",
            "Starter plan is free ($0/mo); select Growth or Scale to subscribe via Stripe.",
            status_code=422,
        )
    if not config.configured or not config.secret_key:
        raise StripePaymentError(
            "STRIPE_NOT_CONFIGURED",
            "Stripe billing is not configured in this environment.",
            status_code=503,
        )
    safe_success = validate_return_url(success_url)
    safe_cancel = validate_return_url(cancel_url)
    return await asyncio.to_thread(
        _create_subscription_checkout_sync,
        api_key=config.secret_key,
        plan=plan,
        tenant_id=tenant_id,
        customer_email=customer_email.strip() if customer_email else None,
        success_url=safe_success,
        cancel_url=safe_cancel,
    )
