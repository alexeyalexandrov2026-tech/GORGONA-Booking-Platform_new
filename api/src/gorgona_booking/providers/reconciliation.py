"""K6b: fetch provider events lost on the way back into the same inbox. Read-only; no money.

Owner decisions 2026-10-21 (K6 design defaults and the K6b detailed decisions). For every receipt
route of one platform namespace whose connection is active and admitted for test access, the
reconciler lists the connected account's events of a time window from the Stripe API with the
platform key, newest first, page by page, and records each through the same inbox as a webhook
(`receive_retrieved_event`). The worker and the finance flow then treat them like any receipt.

Timeouts, rate limits and server errors are retried three times (1, 2, 4 seconds), then the run
fails. A page that did not arrive complete records nothing. Every run leaves one permanent record
of its counts and outcome. No network call is made inside a database transaction, and no key,
account, event ID or payload reaches a log or a row.
"""

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Literal, Protocol
from uuid import UUID

import stripe
from pydantic import SecretStr

from gorgona_booking.business.contracts import Versioned
from gorgona_booking.db.pool import RuntimePool, tenant_transaction, unscoped_transaction
from gorgona_booking.providers.authenticated_receipts import (
    ACTIVE_AUTHORITY,
    assert_safe_receipt_writer_role,
    receive_retrieved_event,
)
from gorgona_booking.providers.inbox import ReceiptBindingRejectedError
from gorgona_booking.providers.stripe_events import (
    SUPPORTED_EVENT_TYPES,
    ProviderEventRejectedError,
    ProviderPageRejectedError,
    decode_event_page,
)

DEFAULT_DAYS = 3
MAX_DAYS = 30
MAX_PAGES = 100
PAGE_SIZE = 100
RETRY_WAITS = (1.0, 2.0, 4.0)
MAX_TIMEOUT_SECONDS = 60.0
# Answers worth asking again: the provider was busy, slow or briefly broken.
_RETRYABLE = (stripe.RateLimitError, stripe.APIConnectionError, stripe.APIError)

logger = logging.getLogger("gorgona_booking.providers.reconciliation")


class PageLimitExceededError(Exception):
    """The window holds more pages than one run may read; the run fails visibly."""


class EventSource(Protocol):
    async def page(
        self, *, account: str, created_gte: int, created_lt: int, starting_after: str | None
    ) -> bytes:
        """One raw `GET /v1/events` page of `account`, newest first."""
        ...


@dataclass(frozen=True, repr=False)
class StripeApiSource:
    """The platform key over the Stripe API; the key lives in memory and is never shown."""

    key: SecretStr = field(repr=False)
    base_url: str | None = None
    timeout: float = 10.0

    def __post_init__(self) -> None:
        if not 0 < self.timeout <= MAX_TIMEOUT_SECONDS:
            raise ValueError(f"Provider timeout must be above 0 and at most {MAX_TIMEOUT_SECONDS}")

    def __repr__(self) -> str:
        return f"StripeApiSource(base_url={self.base_url!r}, timeout={self.timeout!r})"

    async def page(
        self, *, account: str, created_gte: int, created_lt: int, starting_after: str | None
    ) -> bytes:
        return await asyncio.to_thread(self._page, account, created_gte, created_lt, starting_after)

    def _page(
        self, account: str, created_gte: int, created_lt: int, starting_after: str | None
    ) -> bytes:
        client = stripe.StripeClient(
            self.key.get_secret_value(),
            http_client=stripe.RequestsClient(timeout=self.timeout),
            max_network_retries=0,
            base_addresses={"api": self.base_url} if self.base_url else None,
        )
        params: dict[str, object] = {
            "limit": PAGE_SIZE,
            "created": {"gte": created_gte, "lt": created_lt},
            "types": list(SUPPORTED_EVENT_TYPES),
            "stripe_account": account,
        }
        if starting_after is not None:
            params["starting_after"] = starting_after
        response = client.raw_request("get", "/v1/events", **params)
        return str(response.body).encode("utf-8")


class ReconciliationRun(Versioned):
    tenant_id: UUID
    connection_id: UUID
    run_id: UUID
    window_start: datetime
    window_end: datetime
    pages: int
    seen: int
    recorded: int
    duplicates: int
    conflicts: int
    refused: int
    outcome: Literal["completed", "failed"]
    error_class: str | None


@dataclass(frozen=True)
class _Target:
    tenant_id: UUID
    connection_id: UUID
    ingress_id: UUID
    account: str


@dataclass
class _Counts:
    pages: int = 0
    seen: int = 0
    recorded: int = 0
    duplicates: int = 0
    conflicts: int = 0
    refused: int = 0


async def _targets(pool: RuntimePool, namespace: str) -> list[_Target]:
    """Routes of the namespace whose connection is active and admitted; IDs and account only."""
    async with unscoped_transaction(pool) as conn:
        await assert_safe_receipt_writer_role(conn)
        routes = await (
            await conn.execute(
                "select ingress_id,tenant_id,connection_id from gba.provider_receipt_routes "
                "order by tenant_id,connection_id"
            )
        ).fetchall()
    found: list[_Target] = []
    for ingress_id, tenant_id, connection_id in routes:
        async with tenant_transaction(pool, tenant_id) as conn:
            row = await (
                await conn.execute(ACTIVE_AUTHORITY, (tenant_id, connection_id))
            ).fetchone()
        if row is not None and row[3] == namespace:
            found.append(_Target(tenant_id, connection_id, ingress_id, row[4]))
    return found


async def _fetch(
    source: EventSource,
    target: _Target,
    window: tuple[int, int],
    starting_after: str | None,
    retry_waits: tuple[float, ...],
) -> bytes:
    for wait in (*retry_waits, None):
        try:
            return await source.page(
                account=target.account,
                created_gte=window[0],
                created_lt=window[1],
                starting_after=starting_after,
            )
        except _RETRYABLE:
            if wait is None:
                raise
            await asyncio.sleep(wait)
    raise AssertionError("unreachable")


async def _read_window(
    pool: RuntimePool,
    source: EventSource,
    target: _Target,
    window: tuple[int, int],
    counts: _Counts,
    max_pages: int,
    retry_waits: tuple[float, ...],
) -> None:
    starting_after: str | None = None
    while True:
        if counts.pages >= max_pages:
            raise PageLimitExceededError
        events, has_more = decode_event_page(
            await _fetch(source, target, window, starting_after, retry_waits)
        )
        counts.pages += 1
        for value in events:
            counts.seen += 1
            try:
                result = await receive_retrieved_event(pool, target.ingress_id, value)
            except ProviderEventRejectedError:
                counts.refused += 1
                continue
            if result.disposition == "recorded":
                counts.recorded += 1
            elif result.disposition == "duplicate":
                counts.duplicates += 1
            else:
                counts.conflicts += 1
        if not has_more or not events:
            return
        last = events[-1].get("id")
        if not isinstance(last, str):
            raise ProviderPageRejectedError("Provider page was refused", reason="page_shape")
        starting_after = last


async def _reconcile_one(
    pool: RuntimePool,
    source: EventSource,
    target: _Target,
    window_start: datetime,
    window_end: datetime,
    max_pages: int,
    retry_waits: tuple[float, ...],
) -> ReconciliationRun:
    async with tenant_transaction(pool, target.tenant_id) as conn:
        row = await (await conn.execute("select now()")).fetchone()
    if row is None:
        raise RuntimeError("The database clock is unavailable")
    started_at = row[0]
    counts = _Counts()
    error: str | None = None
    try:
        await _read_window(
            pool,
            source,
            target,
            (int(window_start.timestamp()), int(window_end.timestamp())),
            counts,
            max_pages,
            retry_waits,
        )
    except (
        PageLimitExceededError,
        ProviderPageRejectedError,
        ReceiptBindingRejectedError,
        stripe.StripeError,
    ) as exc:
        error = type(exc).__name__
    outcome: Literal["completed", "failed"] = "failed" if error else "completed"
    async with tenant_transaction(pool, target.tenant_id) as conn:
        recorded = await (
            await conn.execute(
                "insert into gba.provider_reconciliation_runs (tenant_id,connection_id,"
                "window_start,window_end,started_at,pages,seen,recorded,duplicates,conflicts,"
                "refused,outcome,error_class) values (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) "
                "returning id",
                (
                    target.tenant_id,
                    target.connection_id,
                    window_start,
                    window_end,
                    started_at,
                    counts.pages,
                    counts.seen,
                    counts.recorded,
                    counts.duplicates,
                    counts.conflicts,
                    counts.refused,
                    outcome,
                    error,
                ),
            )
        ).fetchone()
    if recorded is None:
        raise RuntimeError("The reconciliation run was not recorded")
    # Counts and the error class only: never a key, account, event ID or payload.
    logger.info(
        "provider reconciliation run",
        extra={
            "outcome": outcome,
            "error": error,
            "pages": counts.pages,
            "seen": counts.seen,
            "recorded": counts.recorded,
            "duplicates": counts.duplicates,
            "conflicts": counts.conflicts,
            "refused": counts.refused,
        },
    )
    return ReconciliationRun(
        tenant_id=target.tenant_id,
        connection_id=target.connection_id,
        run_id=recorded[0],
        window_start=window_start,
        window_end=window_end,
        pages=counts.pages,
        seen=counts.seen,
        recorded=counts.recorded,
        duplicates=counts.duplicates,
        conflicts=counts.conflicts,
        refused=counts.refused,
        outcome=outcome,
        error_class=error,
    )


async def reconcile(
    pool: RuntimePool,
    source: EventSource,
    *,
    namespace: str,
    days: int = DEFAULT_DAYS,
    now: datetime | None = None,
    max_pages: int = MAX_PAGES,
    retry_waits: tuple[float, ...] = RETRY_WAITS,
) -> list[ReconciliationRun]:
    """One run per admitted connection of `namespace` over the last `days` before `now`."""
    if not 1 <= days <= MAX_DAYS:
        raise ValueError(f"Reconciliation window must be 1 to {MAX_DAYS} days")
    if not 1 <= max_pages <= MAX_PAGES:
        raise ValueError(f"Reconciliation may read 1 to {MAX_PAGES} pages")
    window_end = now if now is not None else datetime.now(UTC)
    if window_end.tzinfo is None:
        raise ValueError("Reconciliation needs an aware clock")
    window_start = window_end - timedelta(days=days)
    return [
        await _reconcile_one(pool, source, target, window_start, window_end, max_pages, retry_waits)
        for target in await _targets(pool, namespace)
    ]
