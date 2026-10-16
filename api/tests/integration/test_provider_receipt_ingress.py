"""K1e: raw HTTP receipt ingress for the isolated writer process; synthetic only.

No provider account, real key, process entry point, worker or money. Keys are generated in
memory; requests go to the in-process ASGI application or to a server bound to 127.0.0.1.
"""

import asyncio
import contextlib
import json
import logging
from collections.abc import AsyncIterator, Awaitable, Callable, Mapping
from contextlib import asynccontextmanager
from typing import Any
from uuid import UUID, uuid7

import httpx
import psycopg
import pytest
import uvicorn
from psycopg_pool import AsyncConnectionPool
from pydantic import SecretStr
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from gorgona_booking.db.pool import RuntimeConnection, RuntimePool, tenant_transaction
from gorgona_booking.providers import authenticated_receipts as service
from gorgona_booking.providers.authenticated_receipts import ReceiptAuthority
from gorgona_booking.providers.inbox import ReceiptResult, record_event
from gorgona_booking.providers.receipt_ingress import IngressLimits, create_receipt_ingress_app
from gorgona_booking.providers.stripe_contracts import SignedStripeEvent
from gorgona_booking.providers.stripe_events import MAX_BODY_BYTES
from tests.integration import test_provider_receipt_attestations as attested
from tests.integration import test_provider_receipt_routing as routing
from tests.integration.conftest import ProvisionedDatabase
from tests.unit import test_stripe_event_boundary as signed

pytestmark = pytest.mark.anyio
client = attested.client
idp = attested.idp
manager_a = attested.manager_a
manager_b = attested.manager_b
enabled = attested.enabled
inbox = attested.inbox
writer_pool = attested.writer_pool
routed = attested.routed
Routed = attested.Routed
stored = routing.stored

ACCEPTED = b'{"received":true}'
REFUSED = b'{"error":{"code":"PROVIDER_RECEIPT_REFUSED","message":"Provider receipt was refused"}}'
TOO_LARGE = (
    b'{"error":{"code":"PROVIDER_RECEIPT_TOO_LARGE",'
    b'"message":"Provider receipt body is too large"}}'
)
TIMED_OUT = (
    b'{"error":{"code":"PROVIDER_RECEIPT_TIMEOUT",'
    b'"message":"Provider receipt body was not received in time"}}'
)
UNAVAILABLE = (
    b'{"error":{"code":"PROVIDER_RECEIPT_UNAVAILABLE",'
    b'"message":"Provider receipt storage is unavailable"}}'
)
FAILED = b'{"error":{"code":"PROVIDER_RECEIPT_FAILED","message":"Provider receipt failed"}}'
CHUNK = 65_536


def app_for(
    pool: RuntimePool,
    scope: Routed,
    *,
    key_store: Mapping[str, SecretStr] | None = None,
    **limits: Any,
) -> ASGIApp:
    return create_receipt_ingress_app(
        pool,
        scope.key_store if key_store is None else key_store,
        limits=IngressLimits(**limits),
        now=lambda: attested.NOW,
    )


@asynccontextmanager
async def http(app: ASGIApp) -> AsyncIterator[httpx.AsyncClient]:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://receipts.test") as session:
        yield session


def path(ingress: object) -> str:
    return f"/v1/provider-events/stripe/{ingress}"


def headers(raw: bytes, key: SecretStr, timestamp: int = signed.NOW) -> dict[str, str]:
    return {
        "Stripe-Signature": signed.signed(raw, key, timestamp),
        "Content-Type": "application/json; charset=utf-8",
    }


async def post(
    app: ASGIApp, scope: Routed, raw: bytes, *, timestamp: int = signed.NOW
) -> httpx.Response:
    async with http(app) as session:
        return await session.post(
            path(scope.ingress_id), content=raw, headers=headers(raw, scope.key, timestamp)
        )


def on_response_start(app: ASGIApp, check: Callable[[], Awaitable[None]]) -> ASGIApp:
    """Runs `check` at the moment the application starts its response."""

    async def observed(scope: Scope, receive: Receive, send: Send) -> None:
        async def guarded(message: Message) -> None:
            if message["type"] == "http.response.start":
                await check()
            await send(message)

        await app(scope, receive, guarded)

    return observed


# E-01 -----------------------------------------------------------------------


@pytest.mark.parametrize("kind", ["payment_intent.succeeded", "charge.succeeded", "refund.updated"])
async def test_signed_delivery_is_acknowledged_only_after_its_commit(
    routed: Routed, writer_pool: RuntimePool, app_pool: RuntimePool, kind: str
) -> None:
    raw = attested.delivery(kind)
    async with tenant_transaction(app_pool, routed.tenant_id) as conn:
        before = await (await conn.execute("select count(*) from gba.journal_entries")).fetchone()
    seen: list[tuple[int, int, int]] = []

    async def committed() -> None:
        seen.append(await stored(app_pool, routed.tenant_id))

    app = on_response_start(app_for(writer_pool, routed), committed)
    response = await post(app, routed, raw)
    assert (response.status_code, response.content) == (200, ACCEPTED)
    assert response.headers["content-type"] == "application/json"
    assert seen == [(1, 1, 1)]
    rows = await attested.attestations(app_pool, routed.tenant_id)
    assert rows[0][4] == routed.verification_config_id
    async with tenant_transaction(app_pool, routed.tenant_id) as conn:
        after = await (await conn.execute("select count(*) from gba.journal_entries")).fetchone()
    assert before == after


@asynccontextmanager
async def loopback(app: ASGIApp) -> AsyncIterator[int]:
    """A real HTTP server on an ephemeral 127.0.0.1 port; its own access log is off."""
    config = uvicorn.Config(
        app, host="127.0.0.1", port=0, lifespan="off", access_log=False, log_level="warning"
    )
    server = uvicorn.Server(config)
    task = asyncio.create_task(server.serve())
    try:
        async with asyncio.timeout(15):
            while not server.started:
                if task.done():
                    await task
                await asyncio.sleep(0.01)
        yield int(server.servers[0].sockets[0].getsockname()[1])
    finally:
        server.should_exit = True
        await asyncio.wait_for(task, 15)


async def exchange(port: int, scope: Routed, framing: str, payload: bytes) -> bytes:
    """One raw HTTP/1.1 request; only bytes the server consumes are sent before reading."""
    reader, writer = await asyncio.open_connection("127.0.0.1", port)
    try:
        head = (
            f"POST {path(scope.ingress_id)} HTTP/1.1\r\nHost: 127.0.0.1\r\n"
            f"Stripe-Signature: {signed.signed(b'{}', scope.key)}\r\n{framing}"
            "Connection: close\r\n\r\n"
        )
        writer.write(head.encode() + payload)
        await writer.drain()
        async with asyncio.timeout(15):
            return await reader.read()
    finally:
        writer.close()
        with contextlib.suppress(OSError):
            await writer.wait_closed()


async def test_signed_delivery_and_oversized_bodies_over_a_real_loopback_socket(
    routed: Routed, writer_pool: RuntimePool, app_pool: RuntimePool
) -> None:
    raw = attested.delivery()
    # Four full chunks reach the cap exactly; the last byte, without its CRLF, passes it.
    chunks = b"".join(b"%x\r\n" % CHUNK + b"x" * CHUNK + b"\r\n" for _ in range(4)) + b"1\r\nx"
    assert 4 * CHUNK == MAX_BODY_BYTES
    async with loopback(app_for(writer_pool, routed)) as port:
        async with httpx.AsyncClient(base_url=f"http://127.0.0.1:{port}") as session:
            response = await session.post(
                path(routed.ingress_id), content=raw, headers=headers(raw, routed.key)
            )
        declared = await exchange(port, routed, f"Content-Length: {MAX_BODY_BYTES + 1}\r\n", b"")
        chunked = await exchange(port, routed, "Transfer-Encoding: chunked\r\n", chunks)
    assert (response.status_code, response.content) == (200, ACCEPTED)
    for answer in (declared, chunked):
        assert answer.startswith(b"HTTP/1.1 413 ")
        assert answer.endswith(b"\r\n\r\n" + TOO_LARGE)
    assert await stored(app_pool, routed.tenant_id) == (1, 1, 1)


# E-02 -----------------------------------------------------------------------


async def test_lost_acknowledgement_replays_as_a_duplicate_and_conflicts_are_kept(
    routed: Routed, writer_pool: RuntimePool, app_pool: RuntimePool
) -> None:
    app = app_for(writer_pool, routed)
    raw = attested.delivery()
    first = await post(app, routed, raw)
    # The sender never saw the first response and retries later with a fresh signature.
    retry = await post(app, routed, raw, timestamp=signed.NOW + 60)
    assert [(r.status_code, r.content) for r in (first, retry)] == [(200, ACCEPTED)] * 2
    assert await stored(app_pool, routed.tenant_id) == (1, 1, 1)
    variant = await post(app, routed, attested.delivery(amount=2000))
    assert (variant.status_code, variant.content) == (200, ACCEPTED)
    assert await stored(app_pool, routed.tenant_id) == (1, 2, 2)


# E-03 -----------------------------------------------------------------------

_REFUSALS = [
    "unknown_ingress",
    "malformed_ingress",
    "uppercase_ingress",
    "missing_signature",
    "repeated_signature",
    "bad_signature",
    "stale_signature",
    "future_signature",
    "wrong_key",
    "missing_key",
    "unusable_key",
    "revoked_config",
    "revoked_connection",
    "foreign_account",
    "unsupported_type",
    "empty_body",
]


@pytest.mark.parametrize("case", _REFUSALS)
async def test_every_refusal_has_one_body_and_stores_nothing(
    routed: Routed, writer_pool: RuntimePool, app_pool: RuntimePool, case: str
) -> None:
    raw = attested.delivery()
    target: object = routed.ingress_id
    key_store: Mapping[str, SecretStr] = routed.key_store
    key = routed.key
    timestamp = signed.NOW
    signatures = 1
    match case:
        case "unknown_ingress":
            target = uuid7()
        case "malformed_ingress":
            target = "not-an-ingress"
        case "uppercase_ingress":
            target = str(routed.ingress_id).upper()
        case "missing_signature":
            signatures = 0
        case "repeated_signature":
            signatures = 2
        case "bad_signature":
            raw = raw.replace(b"1000", b"1001", 1)
        case "stale_signature":
            timestamp = signed.NOW - 301
        case "future_signature":
            timestamp = signed.NOW + 301
        case "wrong_key":
            key = attested.fake_key()
        case "missing_key":
            key_store = {}
        case "unusable_key":
            key = SecretStr("whsec_short")
            key_store = {routed.secret_ref: key}
        case "revoked_config":
            await routing.revoke(
                app_pool, routed, "provider_verification_configs", routed.verification_config_id
            )
        case "revoked_connection":
            await routing.revoke(
                app_pool, routed, "provider_receipt_connections", routed.connection_id
            )
        case "foreign_account":
            raw = attested.delivery(account="acct_FAKEother")
        case "unsupported_type":
            value = signed.event()
            value["account"] = "acct_FAKEreceipt"
            value["type"] = "customer.created"
            raw = signed.body(value)
        case "empty_body":
            raw = b""
    header = signed.signed(attested.delivery() if case == "bad_signature" else raw, key, timestamp)
    sent = [("Content-Type", "application/json"), *[("Stripe-Signature", header)] * signatures]
    app = create_receipt_ingress_app(writer_pool, key_store, now=lambda: attested.NOW)
    async with http(app) as session:
        response = await session.post(path(target), content=raw, headers=sent)
    assert (response.status_code, response.content) == (400, REFUSED)
    assert await stored(app_pool, routed.tenant_id) == (0, 0, 0)


# E-04, E-05 -----------------------------------------------------------------


async def test_oversized_bodies_are_refused_before_or_while_reading(
    routed: Routed, writer_pool: RuntimePool, app_pool: RuntimePool
) -> None:
    pulled: list[int] = []

    async def body(chunks: int) -> AsyncIterator[bytes]:
        for _ in range(chunks):
            pulled.append(CHUNK)
            yield b"x" * CHUNK

    sent = headers(b"{}", routed.key)
    async with http(app_for(writer_pool, routed)) as session:
        declared = await session.post(
            path(routed.ingress_id),
            content=body(5),
            headers={**sent, "Content-Length": str(MAX_BODY_BYTES + 1)},
        )
        unread = len(pulled)
        chunked = await session.post(path(routed.ingress_id), content=body(10), headers=sent)
    assert [(r.status_code, r.content) for r in (declared, chunked)] == [(413, TOO_LARGE)] * 2
    assert unread == 0
    assert len(pulled) == MAX_BODY_BYTES // CHUNK + 1
    assert await stored(app_pool, routed.tenant_id) == (0, 0, 0)


async def test_a_body_that_does_not_arrive_in_time_is_refused(
    routed: Routed, writer_pool: RuntimePool, app_pool: RuntimePool
) -> None:
    raw = attested.delivery()
    never = asyncio.Event()

    async def stalled() -> AsyncIterator[bytes]:
        yield raw[:10]
        await never.wait()
        yield raw[10:]

    try:
        async with http(app_for(writer_pool, routed, body_read_seconds=0.2)) as session:
            response = await session.post(
                path(routed.ingress_id), content=stalled(), headers=headers(raw, routed.key)
            )
    finally:
        never.set()
    assert (response.status_code, response.content) == (408, TIMED_OUT)
    assert await stored(app_pool, routed.tenant_id) == (0, 0, 0)


# E-06 -----------------------------------------------------------------------


async def test_an_exhausted_writer_pool_answers_retryable_then_the_retry_records(
    routed: Routed, writer_pool: RuntimePool, app_pool: RuntimePool
) -> None:
    small: RuntimePool = AsyncConnectionPool(
        writer_pool.conninfo,
        min_size=1,
        max_size=1,
        timeout=0.5,
        kwargs={"autocommit": True},
        open=False,
    )
    await small.open(wait=True)
    try:
        app = app_for(small, routed)
        raw = attested.delivery()
        async with small.connection():
            busy = await post(app, routed, raw)
        assert (busy.status_code, busy.content) == (503, UNAVAILABLE)
        assert busy.headers["retry-after"] == "5"
        assert await stored(app_pool, routed.tenant_id) == (0, 0, 0)
        retry = await post(app, routed, raw, timestamp=signed.NOW + 60)
    finally:
        await small.close()
    assert (retry.status_code, retry.content) == (200, ACCEPTED)
    assert await stored(app_pool, routed.tenant_id) == (1, 1, 1)


async def test_a_receipt_connection_lost_while_it_waits_answers_retryable(
    routed: Routed,
    writer_pool: RuntimePool,
    app_pool: RuntimePool,
    test_database: ProvisionedDatabase,
) -> None:
    app = app_for(writer_pool, routed)
    raw = attested.delivery()
    monitor = await psycopg.AsyncConnection.connect(
        test_database.admin_dsn, dbname=test_database.name, autocommit=True
    )
    request: asyncio.Task[httpx.Response] | None = None
    try:
        async with routing.held_revocation(app_pool, routed) as holder:
            request = asyncio.create_task(post(app, routed, raw))
            waiter = await routing.blocked_receipt(monitor, holder)
            await monitor.execute("select pg_catalog.pg_terminate_backend(%s)", (waiter,))
            lost = await asyncio.wait_for(request, 15)
    finally:
        if request is not None and not request.done():
            request.cancel()
            await asyncio.gather(request, return_exceptions=True)
        await monitor.close()
    assert (lost.status_code, lost.content) == (503, UNAVAILABLE)
    assert await stored(app_pool, routed.tenant_id) == (0, 0, 0)
    retry = await post(app, routed, raw, timestamp=signed.NOW + 60)
    assert (retry.status_code, retry.content) == (200, ACCEPTED)
    assert await stored(app_pool, routed.tenant_id) == (1, 1, 1)


# E-07 -----------------------------------------------------------------------


async def test_a_failed_commit_is_never_acknowledged(
    routed: Routed,
    writer_pool: RuntimePool,
    app_pool: RuntimePool,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original = service._attest_event

    async def switch_context(
        conn: RuntimeConnection,
        authority: ReceiptAuthority,
        event: SignedStripeEvent,
        result: ReceiptResult,
    ) -> None:
        await original(conn, authority, event, result)
        await conn.execute("select set_config('gba.location_id',%s,true)", (str(uuid7()),))

    monkeypatch.setattr(service, "_attest_event", switch_context)
    response = await post(app_for(writer_pool, routed), routed, attested.delivery())
    assert (response.status_code, response.content) == (500, FAILED)
    assert await stored(app_pool, routed.tenant_id) == (0, 0, 0)


# E-08 -----------------------------------------------------------------------


async def test_a_full_concurrency_quota_answers_retryable_without_reading_the_body(
    routed: Routed, writer_pool: RuntimePool, app_pool: RuntimePool
) -> None:
    raw = attested.delivery()
    reading, release = asyncio.Event(), asyncio.Event()
    pulled: list[int] = []

    async def slow() -> AsyncIterator[bytes]:
        yield raw[:10]
        reading.set()
        await release.wait()
        yield raw[10:]

    async def counted() -> AsyncIterator[bytes]:
        pulled.append(len(raw))
        yield raw

    async with http(app_for(writer_pool, routed, max_concurrent=1)) as session:
        first = asyncio.create_task(
            session.post(path(routed.ingress_id), content=slow(), headers=headers(raw, routed.key))
        )
        try:
            await asyncio.wait_for(reading.wait(), 15)
            busy = await session.post(
                path(routed.ingress_id), content=counted(), headers=headers(raw, routed.key)
            )
        finally:
            release.set()
        done = await asyncio.wait_for(first, 15)
    assert (busy.status_code, busy.content, pulled) == (503, UNAVAILABLE, [])
    assert busy.headers["retry-after"] == "5"
    assert (done.status_code, done.content) == (200, ACCEPTED)
    assert await stored(app_pool, routed.tenant_id) == (1, 1, 1)


async def test_a_receipt_waiting_past_its_lock_timeout_answers_retryable(
    routed: Routed,
    writer_pool: RuntimePool,
    app_pool: RuntimePool,
    test_database: ProvisionedDatabase,
) -> None:
    app = app_for(writer_pool, routed, lock_timeout_ms=2000)
    monitor = await psycopg.AsyncConnection.connect(
        test_database.admin_dsn, dbname=test_database.name, autocommit=True
    )
    request: asyncio.Task[httpx.Response] | None = None
    try:
        async with routing.held_revocation(app_pool, routed) as holder:
            request = asyncio.create_task(post(app, routed, attested.delivery()))
            await routing.blocked_receipt(monitor, holder)
            waited = await asyncio.wait_for(request, 15)
    finally:
        if request is not None and not request.done():
            request.cancel()
            await asyncio.gather(request, return_exceptions=True)
        await monitor.close()
    assert (waited.status_code, waited.content) == (503, UNAVAILABLE)
    assert await stored(app_pool, routed.tenant_id) == (0, 0, 0)


async def test_a_receipt_statement_past_its_timeout_answers_retryable(
    routed: Routed,
    writer_pool: RuntimePool,
    app_pool: RuntimePool,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original = record_event

    async def slow(
        conn: RuntimeConnection, connection_id: UUID, event: SignedStripeEvent
    ) -> ReceiptResult:
        await conn.execute("select pg_catalog.pg_sleep(2)")
        return await original(conn, connection_id, event)

    monkeypatch.setattr(service, "record_event", slow)
    app = app_for(writer_pool, routed, statement_timeout_ms=200)
    response = await post(app, routed, attested.delivery())
    assert (response.status_code, response.content) == (503, UNAVAILABLE)
    assert await stored(app_pool, routed.tenant_id) == (0, 0, 0)


@pytest.mark.parametrize(
    "limits",
    [
        {"max_body_bytes": 0},
        {"max_body_bytes": MAX_BODY_BYTES + 1},
        {"body_read_seconds": 0},
        {"body_read_seconds": 61},
        {"max_concurrent": 0},
        {"max_concurrent": 65},
        {"retry_after_seconds": 0},
        {"lock_timeout_ms": 0},
        {"statement_timeout_ms": 60_001},
    ],
)
async def test_ingress_limits_refuse_unbounded_values(limits: dict[str, Any]) -> None:
    with pytest.raises(ValueError, match="limit"):
        IngressLimits(**limits)


# E-09 -----------------------------------------------------------------------


@pytest.mark.parametrize(
    ("damage", "repair"),
    [
        pytest.param(
            "grant select on gba.journal_entries to gba_receipt_writer;",
            "revoke select on gba.journal_entries from gba_receipt_writer;",
            id="writer-reads-journals",
        ),
        pytest.param(
            "grant select on gba.provider_receipt_routes to gba_runtime;",
            "revoke select on gba.provider_receipt_routes from gba_runtime;",
            id="runtime-reads-routes",
        ),
    ],
)
async def test_schema_or_writer_role_drift_answers_retryable(
    routed: Routed,
    writer_pool: RuntimePool,
    app_pool: RuntimePool,
    owner_conn: psycopg.Connection,
    damage: str,
    repair: str,
) -> None:
    owner_conn.execute(damage.encode())
    try:
        response = await post(app_for(writer_pool, routed), routed, attested.delivery())
    finally:
        owner_conn.execute(repair.encode())
    assert (response.status_code, response.content) == (503, UNAVAILABLE)
    assert await stored(app_pool, routed.tenant_id) == (0, 0, 0)


# E-10 -----------------------------------------------------------------------


async def test_only_post_on_the_one_route_and_the_ordinary_app_has_none(
    routed: Routed,
    writer_pool: RuntimePool,
    app_pool: RuntimePool,
    client: httpx.AsyncClient,
) -> None:
    raw = attested.delivery()
    sent = headers(raw, routed.key)
    async with http(app_for(writer_pool, routed)) as session:
        read = await session.get(path(routed.ingress_id), headers=sent)
        put = await session.put(path(routed.ingress_id), content=raw, headers=sent)
        bare = await session.post("/v1/provider-events/stripe", content=raw, headers=sent)
        nested = await session.post(path(routed.ingress_id) + "/x", content=raw, headers=sent)
        schema = await session.get("/openapi.json")
    assert [r.status_code for r in (read, put)] == [405, 405]
    assert {r.json()["error"]["code"] for r in (read, put)} == {"METHOD_NOT_ALLOWED"}
    assert [r.status_code for r in (bare, nested, schema)] == [404, 404, 404]
    assert {r.json()["error"]["code"] for r in (bare, nested, schema)} == {"NOT_FOUND"}
    ordinary = await client.post(path(routed.ingress_id), content=raw, headers=sent)
    assert ordinary.status_code in (404, 405)
    assert await stored(app_pool, routed.tenant_id) == (0, 0, 0)


# E-11 -----------------------------------------------------------------------


async def test_rows_and_logs_hold_no_raw_body_signature_key_or_ingress(
    routed: Routed,
    writer_pool: RuntimePool,
    app_pool: RuntimePool,
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.DEBUG)
    raw = attested.delivery()
    good = headers(raw, routed.key)
    bad = headers(raw, attested.fake_key())
    async with http(app_for(writer_pool, routed)) as session:
        accepted = await session.post(path(routed.ingress_id), content=raw, headers=good)
        refused = await session.post(path(routed.ingress_id), content=raw, headers=bad)
    assert [accepted.status_code, refused.status_code] == [200, 400]
    hidden = [
        str(routed.ingress_id),
        good["Stripe-Signature"],
        bad["Stripe-Signature"],
        routed.key.get_secret_value(),
        raw.decode(),
        "v1=",
    ]
    # The test client logs its own request URLs; only server-side records are judged.
    logged = [
        json.dumps(record.__dict__, default=str)
        for record in caplog.records
        if not record.name.startswith(("httpx", "httpcore"))
    ]
    assert any("/v1/provider-events/stripe/{ingress_id}" in line for line in logged)
    assert not [value for value in hidden for line in logged if value in line]
    async with tenant_transaction(app_pool, routed.tenant_id) as conn:
        rows = await (
            await conn.execute(
                "select row_to_json(i)::text from gba.provider_event_inbox i union all "
                "select row_to_json(d)::text from gba.provider_event_deliveries d union all "
                "select row_to_json(a)::text from gba.provider_event_attestations a"
            )
        ).fetchall()
    assert len(rows) == 3
    assert not [value for value in hidden for (row,) in rows if value in row]
