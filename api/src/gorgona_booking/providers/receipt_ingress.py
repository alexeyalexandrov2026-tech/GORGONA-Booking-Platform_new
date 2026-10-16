"""Raw HTTP ingress of the isolated receipt writer process; one route, no admission.

`POST /v1/provider-events/stripe/{ingress_id}` passes the exact bounded bytes and the one
signature header to `receive_routed_receipt` and answers 200 only after its commit. Every
refusal has one fixed body without a reason or identifiers; unavailable storage is retryable.
The application holds the writer pool and the server-held key store, so it never runs inside
the ordinary API process. It grants no operational admission or payment authority.
"""

import asyncio
import json
import logging
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

import psycopg
from pydantic import SecretStr
from starlette.applications import Starlette
from starlette.exceptions import HTTPException
from starlette.middleware import Middleware
from starlette.requests import ClientDisconnect, Request
from starlette.responses import Response
from starlette.routing import Route

from gorgona_booking.api.request_id import RequestIdMiddleware
from gorgona_booking.db.pool import RuntimePool
from gorgona_booking.errors import DatabaseUnavailableError
from gorgona_booking.observability import AccessLogMiddleware
from gorgona_booking.providers.authenticated_receipts import (
    LOCK_TIMEOUT_MS,
    MAX_TIMEOUT_MS,
    STATEMENT_TIMEOUT_MS,
    UnsafeReceiptWriterRoleError,
    receive_routed_receipt,
)
from gorgona_booking.providers.inbox import ReceiptBindingRejectedError
from gorgona_booking.providers.stripe_events import (
    MAX_BODY_BYTES,
    ProviderEventConfigurationError,
    ProviderEventRejectedError,
)

INGRESS_ROUTE = "/v1/provider-events/stripe/{ingress_id}"

logger = logging.getLogger("gorgona_booking.providers.receipt_ingress")


@dataclass(frozen=True, slots=True)
class IngressLimits:
    """Per-process quotas; the database timeouts apply inside each receipt transaction."""

    max_body_bytes: int = MAX_BODY_BYTES
    body_read_seconds: float = 10.0
    max_concurrent: int = 8
    retry_after_seconds: int = 5
    lock_timeout_ms: int = LOCK_TIMEOUT_MS
    statement_timeout_ms: int = STATEMENT_TIMEOUT_MS

    def __post_init__(self) -> None:
        if not (
            1 <= self.max_body_bytes <= MAX_BODY_BYTES
            and 0 < self.body_read_seconds <= 60
            and 1 <= self.max_concurrent <= 64
            and 1 <= self.retry_after_seconds <= 3600
            and 1 <= self.lock_timeout_ms <= MAX_TIMEOUT_MS
            and 1 <= self.statement_timeout_ms <= MAX_TIMEOUT_MS
        ):
            raise ValueError("Receipt ingress limits are out of range")


def _error(code: str, message: str) -> bytes:
    return json.dumps({"error": {"code": code, "message": message}}, separators=(",", ":")).encode()


_ACCEPTED = b'{"received":true}'
_REFUSED = _error("PROVIDER_RECEIPT_REFUSED", "Provider receipt was refused")
_TOO_LARGE = _error("PROVIDER_RECEIPT_TOO_LARGE", "Provider receipt body is too large")
_TIMED_OUT = _error("PROVIDER_RECEIPT_TIMEOUT", "Provider receipt body was not received in time")
_UNAVAILABLE = _error("PROVIDER_RECEIPT_UNAVAILABLE", "Provider receipt storage is unavailable")
_FAILED = _error("PROVIDER_RECEIPT_FAILED", "Provider receipt failed")
_NOT_FOUND = _error("NOT_FOUND", "Not found")
_METHOD_NOT_ALLOWED = _error("METHOD_NOT_ALLOWED", "Method not allowed")

# Storage and guard failures a later delivery can overcome; anything else is a 500.
_RETRYABLE = (
    DatabaseUnavailableError,
    UnsafeReceiptWriterRoleError,
    psycopg.OperationalError,
    psycopg.InterfaceError,
)


class _BodyTooLargeError(Exception):
    pass


def _answer(status: int, body: bytes, headers: Mapping[str, str] | None = None) -> Response:
    return Response(body, status_code=status, media_type="application/json", headers=headers)


def _ingress_id(value: str) -> UUID | None:
    """Only the canonical lower-case form the server generated; no aliases."""
    try:
        parsed = UUID(value)
    except ValueError:
        return None
    return parsed if str(parsed) == value else None


async def _read_capped(request: Request, cap: int) -> bytes:
    """The whole raw body, refused as soon as it exceeds the cap (also when chunked)."""
    data = bytearray()
    async for chunk in request.stream():
        data += chunk
        if len(data) > cap:
            raise _BodyTooLargeError
    return bytes(data)


async def _http_error(request: Request, exc: Exception) -> Response:
    status = exc.status_code if isinstance(exc, HTTPException) else 500
    if status == 405:
        return _answer(405, _METHOD_NOT_ALLOWED, {"Allow": "POST"})
    if status == 404:
        return _answer(404, _NOT_FOUND)
    return _answer(500, _FAILED)


def create_receipt_ingress_app(
    pool: RuntimePool,
    key_store: Mapping[str, SecretStr],
    *,
    limits: IngressLimits | None = None,
    now: Callable[[], datetime] | None = None,
) -> Starlette:
    """The writer process's ASGI application. `pool` must use the receipt writer login.

    `now` replaces the clock only in tests. The ordinary application must never mount this.
    """
    bounds = limits or IngressLimits()
    slots = asyncio.Semaphore(bounds.max_concurrent)
    retry = {"Retry-After": str(bounds.retry_after_seconds)}

    async def receive(request: Request) -> Response:
        ingress_id = _ingress_id(request.path_params["ingress_id"])
        if ingress_id is None:
            return _answer(400, _REFUSED)
        if slots.locked():
            return _answer(503, _UNAVAILABLE, retry)
        async with slots:
            return await _receive(request, ingress_id)

    async def _receive(request: Request, ingress_id: UUID) -> Response:
        signatures = request.headers.getlist("stripe-signature")
        lengths = request.headers.getlist("content-length")
        if len(signatures) != 1 or len(lengths) > 1:
            return _answer(400, _REFUSED)
        if lengths:
            if not (lengths[0].isascii() and lengths[0].isdigit()):
                return _answer(400, _REFUSED)
            if int(lengths[0]) > bounds.max_body_bytes:
                return _answer(413, _TOO_LARGE)
        try:
            async with asyncio.timeout(bounds.body_read_seconds):
                payload = await _read_capped(request, bounds.max_body_bytes)
        except TimeoutError:
            return _answer(408, _TIMED_OUT)
        except _BodyTooLargeError:
            return _answer(413, _TOO_LARGE)
        except ClientDisconnect:
            return _answer(400, _REFUSED)
        try:
            await receive_routed_receipt(
                pool,
                ingress_id,
                payload,
                signatures[0],
                key_store=key_store,
                now=None if now is None else now(),
                lock_timeout_ms=bounds.lock_timeout_ms,
                statement_timeout_ms=bounds.statement_timeout_ms,
            )
        except ReceiptBindingRejectedError, ProviderEventRejectedError:
            return _answer(400, _REFUSED)
        except ProviderEventConfigurationError:
            # An operator fault, but the caller still sees the one refusal.
            logger.error("provider receipt key is unusable")
            return _answer(400, _REFUSED)
        except _RETRYABLE as exc:
            logger.warning(
                "provider receipt storage unavailable", extra={"error_type": type(exc).__name__}
            )
            return _answer(503, _UNAVAILABLE, retry)
        except Exception as exc:
            logger.error("provider receipt failed", extra={"error_type": type(exc).__name__})
            return _answer(500, _FAILED)
        return _answer(200, _ACCEPTED)

    app = Starlette(
        routes=[Route(INGRESS_ROUTE, receive, methods=["POST"])],
        middleware=[Middleware(RequestIdMiddleware), Middleware(AccessLogMiddleware)],
        exception_handlers={HTTPException: _http_error},
    )
    app.router.redirect_slashes = False
    return app
