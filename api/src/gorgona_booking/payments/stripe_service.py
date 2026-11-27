"""Stripe US Live/Test Checkout, sync, refunds, and HMAC-verified webhooks (FORCE RLS)."""

from __future__ import annotations

import asyncio
import json
import os
import re
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Literal
from urllib.parse import urlparse
from uuid import UUID, uuid7

import stripe
from psycopg import AsyncConnection
from psycopg.rows import dict_row

PaymentProvider = Literal["stripe", "paypal"]
PaymentReferenceKind = Literal["invoice", "order", "deposit", "service", "custom"]
PaymentSessionStatus = Literal["open", "paid", "expired", "failed", "refunded"]

_STRIPE_KEY_PREFIXES = ("sk_live_", "rk_live_", "sk_test_", "rk_test_")
_STRIPE_PUB_PREFIXES = ("pk_live_", "pk_test_")
_CONNECTED_ACCOUNT_RE = re.compile(r"^acct_[A-Za-z0-9]{6,64}$")
_WEBHOOK_TOLERANCE_SECONDS = 300


class StripePaymentError(RuntimeError):
    """Safe domain error raised for Stripe configuration, validation, or API failures."""

    def __init__(self, code: str, message: str, *, status_code: int = 400) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code


@dataclass(frozen=True)
class StripeRuntimeConfig:
    secret_key: str | None
    publishable_key: str | None
    webhook_secret: str | None
    paypal_configured: bool

    @property
    def configured(self) -> bool:
        return bool(self.secret_key and self.secret_key.startswith(_STRIPE_KEY_PREFIXES))

    @property
    def livemode(self) -> bool:
        return bool(self.secret_key and self.secret_key.startswith(("sk_live_", "rk_live_")))

    @property
    def webhook_configured(self) -> bool:
        return bool(self.webhook_secret and self.webhook_secret.startswith("whsec_"))

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None) -> StripeRuntimeConfig:
        source = os.environ if env is None else env
        raw_secret = (
            source.get("GBA_STRIPE_SECRET_KEY") or source.get("STRIPE_SECRET_KEY") or ""
        ).strip()
        raw_pub = (
            source.get("GBA_STRIPE_PUBLISHABLE_KEY") or source.get("STRIPE_PUBLISHABLE_KEY") or ""
        ).strip()
        raw_wh = (
            source.get("GBA_STRIPE_WEBHOOK_SECRET") or source.get("STRIPE_WEBHOOK_SECRET") or ""
        ).strip()
        raw_pp = (source.get("GBA_PAYPAL_CLIENT_ID") or "").strip()
        secret_key = raw_secret if raw_secret.startswith(_STRIPE_KEY_PREFIXES) else None
        publishable_key = raw_pub if raw_pub.startswith(_STRIPE_PUB_PREFIXES) else None
        webhook_secret = raw_wh if raw_wh.startswith("whsec_") else None
        return cls(
            secret_key=secret_key,
            publishable_key=publishable_key,
            webhook_secret=webhook_secret,
            paypal_configured=bool(raw_pp),
        )


@dataclass(frozen=True)
class PaymentSessionRecord:
    id: UUID
    tenant_id: UUID
    provider: PaymentProvider
    livemode: bool
    provider_session_id: str
    provider_payment_intent_id: str | None
    connected_account_id: str | None
    reference_kind: PaymentReferenceKind
    reference_id: str | None
    customer_name: str
    customer_email: str | None
    description: str
    amount_cents: int
    currency: Literal["USD"]
    status: PaymentSessionStatus
    checkout_url: str
    paid_at: datetime | None
    refunded_at: datetime | None
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True)
class ParsedStripeWebhook:
    event_id: str
    event_type: str
    livemode: bool
    tenant_id: UUID | None
    provider_session_id: str | None
    provider_payment_intent_id: str | None
    target_status: PaymentSessionStatus | None


def validate_return_url(url: str) -> str:
    cleaned = url.strip()
    parsed = urlparse(cleaned)
    if parsed.scheme not in ("https", "http") or not parsed.netloc:
        raise StripePaymentError("INVALID_RETURN_URL", "Return URL must be a valid HTTP(S) URL.")
    if parsed.scheme == "http" and parsed.hostname not in ("127.0.0.1", "localhost"):
        raise StripePaymentError("INVALID_RETURN_URL", "Return URL must use HTTPS.")
    if len(cleaned) > 1000:
        raise StripePaymentError("INVALID_RETURN_URL", "Return URL is too long.")
    return cleaned


def validate_connected_account(account_id: str | None) -> str | None:
    if account_id is None:
        return None
    cleaned = account_id.strip()
    if not cleaned:
        return None
    if not _CONNECTED_ACCOUNT_RE.fullmatch(cleaned):
        raise StripePaymentError(
            "INVALID_CONNECTED_ACCOUNT",
            "Connected Stripe account ID must start with acct_.",
        )
    return cleaned


def _row_to_record(row: dict[str, Any]) -> PaymentSessionRecord:
    return PaymentSessionRecord(
        id=row["id"],
        tenant_id=row["tenant_id"],
        provider=row["provider"],
        livemode=bool(row["livemode"]),
        provider_session_id=str(row["provider_session_id"]),
        provider_payment_intent_id=row["provider_payment_intent_id"],
        connected_account_id=row["connected_account_id"],
        reference_kind=row["reference_kind"],
        reference_id=row["reference_id"],
        customer_name=str(row["customer_name"] or ""),
        customer_email=row["customer_email"],
        description=str(row["description"]),
        amount_cents=int(row["amount_cents"]),
        currency="USD",
        status=row["status"],
        checkout_url=str(row["checkout_url"]),
        paid_at=row["paid_at"],
        refunded_at=row["refunded_at"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


def _create_stripe_session_sync(
    *,
    api_key: str,
    record_id: UUID,
    tenant_id: UUID,
    amount_cents: int,
    description: str,
    reference_kind: PaymentReferenceKind,
    reference_id: str | None,
    customer_email: str | None,
    success_url: str,
    cancel_url: str,
    allow_ach: bool,
    connected_account_id: str | None,
    automatic_tax: bool = False,
) -> dict[str, Any]:
    methods: list[str] = ["card", "us_bank_account"] if allow_ach else ["card"]
    metadata: dict[str, str] = {
        "gorgona_tenant_id": str(tenant_id),
        "gorgona_session_record_id": str(record_id),
        "gorgona_reference_kind": reference_kind,
    }
    if reference_id:
        metadata["gorgona_reference_id"] = reference_id[:120]

    params: dict[str, Any] = {
        "mode": "payment",
        "payment_method_types": methods,
        "line_items": [
            {
                "price_data": {
                    "currency": "usd",
                    "unit_amount": amount_cents,
                    "product_data": {"name": description},
                },
                "quantity": 1,
            }
        ],
        "success_url": success_url,
        "cancel_url": cancel_url,
        "metadata": metadata,
        "payment_intent_data": {"metadata": metadata},
        "api_key": api_key,
        "idempotency_key": f"gorgona-cs-{record_id}",
    }
    if customer_email:
        params["customer_email"] = customer_email
    if connected_account_id:
        params["stripe_account"] = connected_account_id
    if automatic_tax:
        params["automatic_tax"] = {"enabled": True}

    try:
        session = stripe.checkout.Session.create(**params)
    except stripe.StripeError as exc:
        raise StripePaymentError(
            "STRIPE_API_ERROR",
            exc.user_message or "Stripe rejected the checkout session request.",
            status_code=502,
        ) from exc

    url = getattr(session, "url", None)
    sid = getattr(session, "id", None)
    if not url or not sid:
        raise StripePaymentError(
            "STRIPE_API_ERROR",
            "Stripe did not return a checkout session URL.",
            status_code=502,
        )
    pi = getattr(session, "payment_intent", None)
    return {
        "id": str(sid),
        "url": str(url),
        "livemode": bool(getattr(session, "livemode", False)),
        "payment_intent": str(pi) if isinstance(pi, str) and pi else None,
    }


def _retrieve_stripe_session_sync(
    *,
    api_key: str,
    provider_session_id: str,
    connected_account_id: str | None,
) -> dict[str, Any]:
    params: dict[str, Any] = {"api_key": api_key}
    if connected_account_id:
        params["stripe_account"] = connected_account_id
    try:
        session = stripe.checkout.Session.retrieve(provider_session_id, **params)
    except stripe.StripeError as exc:
        raise StripePaymentError(
            "STRIPE_API_ERROR",
            exc.user_message or "Could not retrieve session status from Stripe.",
            status_code=502,
        ) from exc
    pi = getattr(session, "payment_intent", None)
    return {
        "status": str(getattr(session, "status", "") or ""),
        "payment_status": str(getattr(session, "payment_status", "") or ""),
        "payment_intent": str(pi) if isinstance(pi, str) and pi else None,
    }


def _create_stripe_refund_sync(
    *,
    api_key: str,
    payment_intent_id: str,
    record_id: UUID,
    connected_account_id: str | None,
    reason: str | None,
) -> str:
    params: dict[str, Any] = {
        "payment_intent": payment_intent_id,
        "api_key": api_key,
        "idempotency_key": f"gorgona-ref-{record_id}",
    }
    if reason in ("duplicate", "fraudulent", "requested_by_customer"):
        params["reason"] = reason
    if connected_account_id:
        params["stripe_account"] = connected_account_id
    try:
        refund = stripe.Refund.create(**params)
    except stripe.StripeError as exc:
        raise StripePaymentError(
            "STRIPE_REFUND_ERROR",
            exc.user_message or "Stripe refused the refund request.",
            status_code=502,
        ) from exc
    return str(getattr(refund, "id", ""))


def map_stripe_session_status(
    *, stripe_status: str, payment_status: str, current_status: PaymentSessionStatus
) -> PaymentSessionStatus:
    if current_status == "refunded":
        return "refunded"
    if payment_status == "paid":
        return "paid"
    if stripe_status == "expired":
        return "expired"
    return "open"


async def verify_tenant_connected_account(
    conn: AsyncConnection[Any],
    *,
    tenant_id: UUID,
    connected_account_id: str | None,
) -> str | None:
    """Prevent cross-tenant Stripe Connect spoofing via tenant connector config."""
    safe_account = validate_connected_account(connected_account_id)
    if safe_account is None:
        return None
    async with conn.cursor(row_factory=dict_row) as cur:
        await cur.execute(
            """
            SELECT config_masked
            FROM gba.connector_installations
            WHERE tenant_id = %s
              AND connector_id = 'stripe_ach_pos'
              AND status = 'installed'
            """,
            (tenant_id,),
        )
        row = await cur.fetchone()
    stored = (
        str((row["config_masked"] or {}).get("stripe_account_id", "")).strip()
        if row and isinstance(row.get("config_masked"), dict)
        else ""
    )
    if not stored or stored != safe_account:
        raise StripePaymentError(
            "CONNECTED_ACCOUNT_NOT_AUTHORIZED",
            "Requested Stripe connected account is not verified for this business. "
            "Configure your Stripe account ID in App Hub -> Stripe US first.",
            status_code=403,
        )
    return safe_account


async def create_stripe_checkout_session(
    conn: AsyncConnection[Any],
    *,
    config: StripeRuntimeConfig,
    tenant_id: UUID,
    amount_cents: int,
    description: str,
    reference_kind: PaymentReferenceKind,
    reference_id: str | None,
    customer_name: str,
    customer_email: str | None,
    success_url: str,
    cancel_url: str,
    allow_ach: bool,
    connected_account_id: str | None,
    created_by_user_id: UUID | None,
    automatic_tax: bool = False,
) -> PaymentSessionRecord:
    if not config.configured or not config.secret_key:
        raise StripePaymentError(
            "STRIPE_NOT_CONFIGURED",
            "Stripe API key is not configured on this server yet.",
            status_code=503,
        )
    if not 50 <= amount_cents <= 99_999_999:
        raise StripePaymentError(
            "INVALID_AMOUNT",
            "Amount must be between $0.50 and $999,999.99 USD.",
            status_code=422,
        )
    clean_desc = description.strip()
    if not clean_desc or len(clean_desc) > 300:
        raise StripePaymentError(
            "INVALID_DESCRIPTION",
            "Description must be between 1 and 300 characters.",
            status_code=422,
        )
    safe_success = validate_return_url(success_url)
    safe_cancel = validate_return_url(cancel_url)
    safe_account = await verify_tenant_connected_account(
        conn, tenant_id=tenant_id, connected_account_id=connected_account_id
    )
    record_id = uuid7()

    created = await asyncio.to_thread(
        _create_stripe_session_sync,
        api_key=config.secret_key,
        record_id=record_id,
        tenant_id=tenant_id,
        amount_cents=amount_cents,
        description=clean_desc,
        reference_kind=reference_kind,
        reference_id=reference_id.strip() if reference_id else None,
        customer_email=customer_email.strip() if customer_email else None,
        success_url=safe_success,
        cancel_url=safe_cancel,
        allow_ach=allow_ach,
        connected_account_id=safe_account,
        automatic_tax=automatic_tax,
    )

    async with conn.cursor(row_factory=dict_row) as cur:
        await cur.execute(
            """
            INSERT INTO gba.payment_sessions (
                id, tenant_id, provider, livemode, provider_session_id,
                provider_payment_intent_id, connected_account_id,
                reference_kind, reference_id, customer_name, customer_email,
                description, amount_cents, currency, status, checkout_url,
                created_by_user_id
            )
            VALUES (
                %s, %s, 'stripe', %s, %s,
                %s, %s,
                %s, %s, %s, %s,
                %s, %s, 'USD', 'open', %s,
                %s
            )
            RETURNING *
            """,
            (
                record_id,
                tenant_id,
                created["livemode"],
                created["id"],
                created["payment_intent"],
                safe_account,
                reference_kind,
                reference_id.strip() if reference_id else None,
                customer_name.strip()[:160],
                customer_email.strip()[:160] if customer_email else None,
                clean_desc,
                amount_cents,
                created["url"],
                created_by_user_id,
            ),
        )
        row = await cur.fetchone()
    if row is None:
        raise RuntimeError("Failed to persist payment session")
    return _row_to_record(row)


async def list_payment_sessions(
    conn: AsyncConnection[Any],
    *,
    tenant_id: UUID,
    limit: int = 50,
) -> list[PaymentSessionRecord]:
    capped = max(1, min(limit, 200))
    async with conn.cursor(row_factory=dict_row) as cur:
        await cur.execute(
            """
            SELECT *
            FROM gba.payment_sessions
            WHERE tenant_id = %s
            ORDER BY created_at DESC
            LIMIT %s
            """,
            (tenant_id, capped),
        )
        rows = await cur.fetchall()
    return [_row_to_record(r) for r in rows]


async def sync_stripe_payment_session(
    conn: AsyncConnection[Any],
    *,
    config: StripeRuntimeConfig,
    tenant_id: UUID,
    session_record_id: UUID,
) -> PaymentSessionRecord:
    if not config.configured or not config.secret_key:
        raise StripePaymentError(
            "STRIPE_NOT_CONFIGURED",
            "Stripe API key is not configured on this server yet.",
            status_code=503,
        )
    async with conn.cursor(row_factory=dict_row) as cur:
        await cur.execute(
            """
            SELECT *
            FROM gba.payment_sessions
            WHERE tenant_id = %s AND id = %s AND provider = 'stripe'
            """,
            (tenant_id, session_record_id),
        )
        existing = await cur.fetchone()
    if existing is None:
        raise LookupError("Payment session not found")

    remote = await asyncio.to_thread(
        _retrieve_stripe_session_sync,
        api_key=config.secret_key,
        provider_session_id=str(existing["provider_session_id"]),
        connected_account_id=existing["connected_account_id"],
    )
    next_status = map_stripe_session_status(
        stripe_status=remote["status"],
        payment_status=remote["payment_status"],
        current_status=existing["status"],
    )
    next_intent = remote["payment_intent"] or existing["provider_payment_intent_id"]

    async with conn.cursor(row_factory=dict_row) as cur:
        await cur.execute(
            """
            UPDATE gba.payment_sessions
            SET status = %s,
                provider_payment_intent_id = COALESCE(%s, provider_payment_intent_id),
                paid_at = CASE
                    WHEN %s = 'paid' AND paid_at IS NULL THEN now()
                    ELSE paid_at
                END,
                updated_at = now()
            WHERE tenant_id = %s AND id = %s
            RETURNING *
            """,
            (next_status, next_intent, next_status, tenant_id, session_record_id),
        )
        updated = await cur.fetchone()
    if updated is None:
        raise LookupError("Payment session not found")
    return _row_to_record(updated)


async def refund_stripe_payment_session(
    conn: AsyncConnection[Any],
    *,
    config: StripeRuntimeConfig,
    tenant_id: UUID,
    session_record_id: UUID,
    reason: str | None = None,
) -> PaymentSessionRecord:
    if not config.configured or not config.secret_key:
        raise StripePaymentError(
            "STRIPE_NOT_CONFIGURED",
            "Stripe API key is not configured on this server yet.",
            status_code=503,
        )
    async with conn.cursor(row_factory=dict_row) as cur:
        await cur.execute(
            """
            SELECT *
            FROM gba.payment_sessions
            WHERE tenant_id = %s AND id = %s AND provider = 'stripe'
            """,
            (tenant_id, session_record_id),
        )
        existing = await cur.fetchone()
    if existing is None:
        raise LookupError("Payment session not found")
    if existing["status"] == "refunded":
        return _row_to_record(existing)
    if existing["status"] != "paid" or not existing["provider_payment_intent_id"]:
        raise StripePaymentError(
            "REFUND_NOT_ALLOWED",
            "Only paid sessions with a Stripe PaymentIntent can be refunded.",
            status_code=409,
        )

    await asyncio.to_thread(
        _create_stripe_refund_sync,
        api_key=config.secret_key,
        payment_intent_id=str(existing["provider_payment_intent_id"]),
        record_id=session_record_id,
        connected_account_id=existing["connected_account_id"],
        reason=reason,
    )

    async with conn.cursor(row_factory=dict_row) as cur:
        await cur.execute(
            """
            UPDATE gba.payment_sessions
            SET status = 'refunded',
                refunded_at = COALESCE(refunded_at, now()),
                updated_at = now()
            WHERE tenant_id = %s AND id = %s
            RETURNING *
            """,
            (tenant_id, session_record_id),
        )
        updated = await cur.fetchone()
    if updated is None:
        raise LookupError("Payment session not found")
    return _row_to_record(updated)


def verify_and_parse_stripe_webhook(
    payload: bytes,
    sig_header: str,
    webhook_secret: str,
) -> ParsedStripeWebhook:
    if not sig_header.strip():
        raise StripePaymentError("MISSING_SIGNATURE", "Missing Stripe-Signature header.")
    try:
        payload_text = payload.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise StripePaymentError("INVALID_PAYLOAD", "Webhook body must be UTF-8.") from exc

    try:
        stripe.WebhookSignature.verify_header(
            payload_text,
            sig_header,
            webhook_secret,
            tolerance=_WEBHOOK_TOLERANCE_SECONDS,
        )
    except stripe.SignatureVerificationError as exc:
        raise StripePaymentError(
            "INVALID_SIGNATURE", "Stripe webhook signature verification failed."
        ) from exc

    try:
        raw = json.loads(payload_text)
    except json.JSONDecodeError as exc:
        raise StripePaymentError("INVALID_JSON", "Webhook body is not valid JSON.") from exc
    if not isinstance(raw, dict):
        raise StripePaymentError("INVALID_JSON", "Webhook payload must be a JSON object.")

    event_id = str(raw.get("id") or "").strip()
    event_type = str(raw.get("type") or "").strip()
    if not event_id or not event_type:
        raise StripePaymentError("INVALID_EVENT", "Stripe event is missing id or type.")
    livemode = bool(raw.get("livemode", False))

    data = raw.get("data")
    obj = data.get("object") if isinstance(data, dict) else None
    obj_dict = obj if isinstance(obj, dict) else {}
    raw_metadata = obj_dict.get("metadata")
    metadata = raw_metadata if isinstance(raw_metadata, dict) else {}

    tenant_id: UUID | None = None
    raw_tenant = metadata.get("gorgona_tenant_id")
    if isinstance(raw_tenant, str) and raw_tenant.strip():
        try:
            tenant_id = UUID(raw_tenant.strip())
        except ValueError:
            tenant_id = None

    provider_session_id: str | None = None
    provider_payment_intent_id: str | None = None
    target_status: PaymentSessionStatus | None = None

    if event_type in (
        "checkout.session.completed",
        "checkout.session.async_payment_succeeded",
    ):
        sid = obj_dict.get("id")
        if isinstance(sid, str) and sid:
            provider_session_id = sid
        pi = obj_dict.get("payment_intent")
        if isinstance(pi, str) and pi:
            provider_payment_intent_id = pi
        payment_status = str(obj_dict.get("payment_status") or "")
        if event_type == "checkout.session.async_payment_succeeded" or payment_status == "paid":
            target_status = "paid"
    elif event_type == "checkout.session.async_payment_failed":
        sid = obj_dict.get("id")
        if isinstance(sid, str) and sid:
            provider_session_id = sid
        target_status = "failed"
    elif event_type == "checkout.session.expired":
        sid = obj_dict.get("id")
        if isinstance(sid, str) and sid:
            provider_session_id = sid
        target_status = "expired"
    elif event_type == "charge.refunded":
        pi = obj_dict.get("payment_intent")
        if isinstance(pi, str) and pi:
            provider_payment_intent_id = pi
        if bool(obj_dict.get("refunded", False)):
            target_status = "refunded"
    elif event_type == "payment_intent.succeeded":
        pi = obj_dict.get("id")
        if isinstance(pi, str) and pi:
            provider_payment_intent_id = pi
        target_status = "paid"
    elif event_type == "payment_intent.payment_failed":
        pi = obj_dict.get("id")
        if isinstance(pi, str) and pi:
            provider_payment_intent_id = pi
        target_status = "failed"

    return ParsedStripeWebhook(
        event_id=event_id,
        event_type=event_type,
        livemode=livemode,
        tenant_id=tenant_id,
        provider_session_id=provider_session_id,
        provider_payment_intent_id=provider_payment_intent_id,
        target_status=target_status,
    )


async def apply_stripe_webhook_event(
    conn: AsyncConnection[Any],
    *,
    event: ParsedStripeWebhook,
) -> bool:
    if event.tenant_id is None:
        return False

    async with conn.cursor(row_factory=dict_row) as cur:
        await cur.execute(
            """
            INSERT INTO gba.payment_webhook_events (
                tenant_id, provider, event_id, event_type, livemode, provider_session_id
            )
            VALUES (%s, 'stripe', %s, %s, %s, %s)
            ON CONFLICT (tenant_id, provider, event_id) DO NOTHING
            RETURNING event_id
            """,
            (
                event.tenant_id,
                event.event_id,
                event.event_type,
                event.livemode,
                event.provider_session_id,
            ),
        )
        inserted = await cur.fetchone()
        if inserted is None:
            return False

        if event.target_status is None:
            return True

        if event.provider_session_id:
            await cur.execute(
                """
                UPDATE gba.payment_sessions
                SET status = CASE
                        WHEN status = 'refunded' THEN 'refunded'
                        ELSE %s
                    END,
                    provider_payment_intent_id = COALESCE(%s, provider_payment_intent_id),
                    paid_at = CASE
                        WHEN %s = 'paid' AND paid_at IS NULL THEN now()
                        ELSE paid_at
                    END,
                    refunded_at = CASE
                        WHEN %s = 'refunded' AND refunded_at IS NULL THEN now()
                        ELSE refunded_at
                    END,
                    updated_at = now()
                WHERE tenant_id = %s
                  AND provider = 'stripe'
                  AND provider_session_id = %s
                """,
                (
                    event.target_status,
                    event.provider_payment_intent_id,
                    event.target_status,
                    event.target_status,
                    event.tenant_id,
                    event.provider_session_id,
                ),
            )
        elif event.provider_payment_intent_id:
            await cur.execute(
                """
                UPDATE gba.payment_sessions
                SET status = CASE
                        WHEN status = 'refunded' THEN 'refunded'
                        ELSE %s
                    END,
                    paid_at = CASE
                        WHEN %s = 'paid' AND paid_at IS NULL THEN now()
                        ELSE paid_at
                    END,
                    refunded_at = CASE
                        WHEN %s = 'refunded' AND refunded_at IS NULL THEN now()
                        ELSE refunded_at
                    END,
                    updated_at = now()
                WHERE tenant_id = %s
                  AND provider = 'stripe'
                  AND provider_payment_intent_id = %s
                """,
                (
                    event.target_status,
                    event.target_status,
                    event.target_status,
                    event.tenant_id,
                    event.provider_payment_intent_id,
                ),
            )
    return True
