"""K6b: events lost on the way are fetched back from the Stripe API into the same inbox.

Owner decisions 2026-10-21 (K6 design defaults; detailed decisions in the K6b section): a
reconciler of one platform namespace lists each admitted connection's events of the window with
the platform key and the connected account, decodes them strictly into the same facts as a
webhook and attests them as `stripe_api_v1`. A local fake Stripe API stands in for the network;
no real key, account or money is involved.
"""

import json
import logging
import secrets
from collections.abc import Iterator
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

import anyio
import psycopg
import pytest
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from pydantic import SecretStr

from gorgona_booking.db.pool import RuntimePool, tenant_transaction
from gorgona_booking.db.provider_receipt_guard import assert_provider_receipt_ready
from gorgona_booking.errors import DatabaseUnavailableError
from gorgona_booking.providers import receipt_worker as worker
from gorgona_booking.providers import reconciliation
from gorgona_booking.providers.reconciliation import StripeApiSource
from tests.integration import test_provider_connection_admissions as admissions
from tests.integration import test_provider_receipt_attestations as attested
from tests.integration import test_provider_receipt_decisions as decided
from tests.integration.conftest import ProvisionedDatabase
from tests.integration.live_server import free_port, live_server
from tests.integration.test_provider_receipt_attestations import Routed
from tests.unit import test_stripe_event_boundary as signed

pytestmark = pytest.mark.anyio
client = decided.client
idp = decided.idp
manager_a = decided.manager_a
manager_b = decided.manager_b
enabled = decided.enabled
inbox = decided.inbox
writer_pool = decided.writer_pool
routed = decided.routed
worker_pool = decided.worker_pool
NOW = datetime.fromtimestamp(signed.NOW, UTC)
ACCOUNT = "acct_FAKEreceipt"
FAST = (0.0, 0.0, 0.0)


@dataclass
class FakeStripe:
    """`GET /v1/events` of connected accounts, newest first, with scripted failures."""

    key: SecretStr = field(
        default_factory=lambda: SecretStr("sk_test_FAKE" + secrets.token_hex(16))
    )
    events: dict[str, list[dict[str, Any]]] = field(default_factory=dict)
    failures: list[int] = field(default_factory=list)
    delay: float = 0.0
    requests: list[dict[str, Any]] = field(default_factory=list)

    def add(self, *raws: bytes, account: str = ACCOUNT, keep_account: bool = True) -> list[str]:
        ids = []
        for raw in raws:
            value: dict[str, Any] = json.loads(raw)
            if not keep_account:
                value.pop("account")
            self.events.setdefault(account, []).append(value)
            ids.append(value["id"])
        self.events[account].sort(key=lambda e: (e["created"], e["id"]), reverse=True)
        return ids

    def app(self) -> FastAPI:
        app = FastAPI()

        @app.get("/v1/events")
        async def events(request: Request) -> Any:
            query = dict(request.query_params)
            self.requests.append(
                {
                    "account": request.headers.get("stripe-account"),
                    "authorized": request.headers.get("authorization")
                    == "Bearer " + self.key.get_secret_value(),
                    "query": query,
                }
            )
            if self.delay:
                await anyio.sleep(self.delay)
            if self.failures:
                code = self.failures.pop(0)
                return JSONResponse(
                    {"error": {"type": "api_error", "message": "FAKE failure"}}, status_code=code
                )
            items = [
                e
                for e in self.events.get(request.headers.get("stripe-account") or "", [])
                if int(query["created[gte]"]) <= e["created"] < int(query["created[lt]"])
            ]
            if "starting_after" in query:
                at = [e["id"] for e in items].index(query["starting_after"])
                items = items[at + 1 :]
            limit = int(query["limit"])
            return {
                "object": "list",
                "url": "/v1/events",
                "has_more": len(items) > limit,
                "data": items[:limit],
            }

        return app


@pytest.fixture
def stripe_api() -> Iterator[tuple[FakeStripe, StripeApiSource]]:
    fake = FakeStripe()
    with live_server(fake.app(), free_port()) as base:
        yield fake, StripeApiSource(fake.key, base_url=base, timeout=0.5)


def event(kind: str = "payment_intent.succeeded", created: int = 0, **changes: Any) -> bytes:
    value: dict[str, Any] = json.loads(decided.stripe(kind, **changes))
    value["created"] = signed.NOW - 100_000 + created
    return signed.body(value)


async def run(
    routed: Routed, writer_pool: RuntimePool, source: StripeApiSource, **kwargs: Any
) -> reconciliation.ReconciliationRun:
    (result,) = await reconciliation.reconcile(
        writer_pool,
        source,
        namespace=routed.policy.namespace,
        now=NOW,
        retry_waits=kwargs.pop("retry_waits", FAST),
        **kwargs,
    )
    assert result.connection_id == routed.connection_id
    return result


async def stored(pool: RuntimePool, routed: Routed) -> dict[str, list[tuple[Any, ...]]]:
    async with tenant_transaction(pool, routed.tenant_id) as conn:
        rows = await (
            await conn.execute(
                "select e.provider_event_id,d.matches_original,a.verifier "
                "from gba.provider_event_inbox e join gba.provider_event_deliveries d "
                "on d.tenant_id=e.tenant_id and d.event_id=e.id "
                "left join gba.provider_event_attestations a on a.tenant_id=d.tenant_id "
                "and a.event_id=d.event_id and a.delivery_sha256=d.delivery_sha256 "
                "where e.tenant_id=%s and e.connection_id=%s order by d.received_at",
                (routed.tenant_id, routed.connection_id),
            )
        ).fetchall()
    found: dict[str, list[tuple[Any, ...]]] = {}
    for event_id, matches, verifier in rows:
        found.setdefault(event_id, []).append((matches, verifier))
    return found


async def runs(pool: RuntimePool, routed: Routed) -> list[tuple[Any, ...]]:
    async with tenant_transaction(pool, routed.tenant_id) as conn:
        return [
            tuple(row)
            for row in await (
                await conn.execute(
                    "select pages,seen,recorded,duplicates,conflicts,refused,outcome,error_class "
                    "from gba.provider_reconciliation_runs where tenant_id=%s and connection_id=%s "
                    "order by finished_at",
                    (routed.tenant_id, routed.connection_id),
                )
            ).fetchall()
        ]


# B-01 -----------------------------------------------------------------------


async def test_lost_events_arrive_through_the_inbox_and_are_decided(
    routed: Routed,
    writer_pool: RuntimePool,
    worker_pool: RuntimePool,
    stripe_api: tuple[FakeStripe, StripeApiSource],
) -> None:
    fake, source = stripe_api
    paid, refunded = fake.add(
        event("payment_intent.succeeded", 10),
        # The list API may leave out `account`; the request names the connected account.
        event("refund.updated", 20, object_id="re_FAKEbackfill1", amount=400),
        keep_account=False,
    )
    result = await run(routed, writer_pool, source)
    assert (result.outcome, result.error_class, result.pages) == ("completed", None, 1)
    assert (result.seen, result.recorded, result.duplicates, result.conflicts) == (2, 2, 0, 0)
    assert await stored(writer_pool, routed) == {
        paid: [(True, "stripe_api_v1")],
        refunded: [(True, "stripe_api_v1")],
    }
    (request,) = fake.requests
    assert request["authorized"]
    assert request["account"] == ACCOUNT
    assert request["query"]["limit"] == "100"
    decisions = await worker.process_batch(worker_pool, tenant_id=routed.tenant_id)
    assert {(d.outcome, d.reason) for d in decisions} == {("observed", "success")}
    assert await runs(writer_pool, routed) == [(1, 2, 2, 0, 0, 0, "completed", None)]


# B-02 -----------------------------------------------------------------------


async def test_a_webhook_and_its_retrieval_are_one_event(
    routed: Routed,
    writer_pool: RuntimePool,
    stripe_api: tuple[FakeStripe, StripeApiSource],
) -> None:
    fake, source = stripe_api
    raw = event("payment_intent.succeeded", 10)
    await attested.receive(writer_pool, routed, raw)
    (event_id,) = fake.add(raw)
    result = await run(routed, writer_pool, source)
    assert (result.recorded, result.duplicates, result.conflicts) == (0, 1, 0)
    assert sorted(await stored(writer_pool, routed)) == [event_id]
    assert sorted((await stored(writer_pool, routed))[event_id]) == [
        (True, "stripe_api_v1"),
        (True, "stripe_snapshot_v1"),
    ]
    # A second run adds nothing: the same canonical digest is an exact retry.
    again = await run(routed, writer_pool, source)
    assert (again.recorded, again.duplicates) == (0, 1)
    assert len((await stored(writer_pool, routed))[event_id]) == 2


async def test_a_different_fact_under_the_same_id_is_a_visible_conflict(
    routed: Routed,
    writer_pool: RuntimePool,
    worker_pool: RuntimePool,
    stripe_api: tuple[FakeStripe, StripeApiSource],
) -> None:
    fake, source = stripe_api
    raw = event("payment_intent.succeeded", 10)
    await attested.receive(writer_pool, routed, raw)
    changed: dict[str, Any] = json.loads(raw)
    changed["data"]["object"]["amount_received"] = 999
    fake.add(signed.body(changed))
    result = await run(routed, writer_pool, source)
    assert (result.recorded, result.duplicates, result.conflicts) == (0, 0, 1)
    (decision,) = await worker.process_batch(worker_pool, tenant_id=routed.tenant_id)
    assert (decision.outcome, decision.reason) == ("needs_review", "conflicting_facts")


# B-03 -----------------------------------------------------------------------


@pytest.mark.parametrize(
    "change",
    [
        {"api_version": "2025-01-27.acacia"},
        {"account": "acct_FAKEsomeoneelse"},
        {"livemode": True},
        {"type": "customer.created"},
    ],
)
async def test_another_version_account_mode_or_type_is_refused_and_counted(
    routed: Routed,
    writer_pool: RuntimePool,
    stripe_api: tuple[FakeStripe, StripeApiSource],
    change: dict[str, Any],
) -> None:
    fake, source = stripe_api
    value: dict[str, Any] = json.loads(event("payment_intent.succeeded", 10))
    value.update(change)
    fake.add(signed.body(value), event("payment_intent.succeeded", 5, object_id="pi_FAKEgood1"))
    result = await run(routed, writer_pool, source)
    assert (result.outcome, result.seen, result.recorded, result.refused) == ("completed", 2, 1, 1)
    assert len(await stored(writer_pool, routed)) == 1


async def test_a_malformed_event_is_refused_and_a_malformed_page_fails_the_run(
    routed: Routed,
    writer_pool: RuntimePool,
    stripe_api: tuple[FakeStripe, StripeApiSource],
) -> None:
    fake, source = stripe_api
    fake.add(event("payment_intent.succeeded", 10))
    fake.events[ACCOUNT][0]["data"] = "not an object"  # decoded only after the page parses
    result = await run(routed, writer_pool, source)
    assert (result.seen, result.recorded, result.refused) == (1, 0, 1)

    @dataclass
    class Broken:
        async def page(self, **_: Any) -> bytes:
            return b'{"object":"list","data":[],"data":[],"has_more":false}'

    (broken,) = await reconciliation.reconcile(
        writer_pool, Broken(), namespace=routed.policy.namespace, now=NOW, retry_waits=FAST
    )
    assert (broken.outcome, broken.error_class, broken.recorded) == (
        "failed",
        "ProviderPageRejectedError",
        0,
    )


# B-04 -----------------------------------------------------------------------


async def test_every_page_of_the_window_is_read_and_a_second_run_adds_nothing(
    routed: Routed,
    writer_pool: RuntimePool,
    stripe_api: tuple[FakeStripe, StripeApiSource],
) -> None:
    fake, source = stripe_api
    fake.add(
        *(event("payment_intent.succeeded", n, object_id=f"pi_FAKEpage{n}") for n in range(1, 251))
    )
    # Outside the window: older than three days and not before `now`.
    fake.add(
        event("payment_intent.succeeded", -300_000, object_id="pi_FAKEold1"),
        event("payment_intent.succeeded", 200_000, object_id="pi_FAKEfuture1"),
    )
    first = await run(routed, writer_pool, source)
    assert (first.pages, first.seen, first.recorded) == (3, 250, 250)
    assert first.window_end == NOW
    assert (first.window_end - first.window_start).days == 3
    second = await run(routed, writer_pool, source)
    assert (second.pages, second.seen, second.recorded, second.duplicates) == (3, 250, 0, 250)
    queries = [r["query"] for r in fake.requests]
    assert [q.get("starting_after") is None for q in queries] == [True, False, False] * 2


async def test_a_window_with_more_pages_than_allowed_fails_visibly(
    routed: Routed,
    writer_pool: RuntimePool,
    stripe_api: tuple[FakeStripe, StripeApiSource],
) -> None:
    fake, source = stripe_api
    fake.add(
        *(event("payment_intent.succeeded", n, object_id=f"pi_FAKEmany{n}") for n in range(1, 251))
    )
    result = await run(routed, writer_pool, source, max_pages=2)
    assert (result.outcome, result.error_class, result.pages, result.recorded) == (
        "failed",
        "PageLimitExceededError",
        2,
        200,
    )


# B-05 -----------------------------------------------------------------------


async def test_rate_limits_and_server_errors_are_retried_then_succeed(
    routed: Routed,
    writer_pool: RuntimePool,
    stripe_api: tuple[FakeStripe, StripeApiSource],
) -> None:
    fake, source = stripe_api
    fake.add(event("payment_intent.succeeded", 10))
    fake.failures = [429, 500, 503]
    result = await run(routed, writer_pool, source)
    assert (result.outcome, result.recorded) == ("completed", 1)
    assert len(fake.requests) == 4


@pytest.mark.parametrize(
    ("failures", "delay", "error_class", "requests"),
    [
        ([500, 500, 500, 500], 0.0, "APIError", 4),
        ([429, 429, 429, 429], 0.0, "RateLimitError", 4),
        ([401], 0.0, "AuthenticationError", 1),
        ([400], 0.0, "InvalidRequestError", 1),
        ([], 2.0, "APIConnectionError", 4),
    ],
)
async def test_a_failing_provider_never_fabricates_a_receipt(
    routed: Routed,
    writer_pool: RuntimePool,
    stripe_api: tuple[FakeStripe, StripeApiSource],
    failures: list[int],
    delay: float,
    error_class: str,
    requests: int,
) -> None:
    fake, source = stripe_api
    fake.add(event("payment_intent.succeeded", 10))
    fake.failures, fake.delay = list(failures), delay
    result = await run(routed, writer_pool, source)
    assert (result.outcome, result.error_class, result.seen, result.recorded) == (
        "failed",
        error_class,
        0,
        0,
    )
    assert len(fake.requests) == requests
    assert await stored(writer_pool, routed) == {}
    assert await runs(writer_pool, routed) == [(0, 0, 0, 0, 0, 0, "failed", error_class)]


# B-06 -----------------------------------------------------------------------


async def test_a_suspended_connection_is_never_asked(
    routed: Routed,
    writer_pool: RuntimePool,
    owner_conn: psycopg.Connection,
    stripe_api: tuple[FakeStripe, StripeApiSource],
) -> None:
    fake, source = stripe_api
    fake.add(event("payment_intent.succeeded", 10))
    admissions.admit(owner_conn, routed, "suspended")
    assert (
        await reconciliation.reconcile(
            writer_pool, source, namespace=routed.policy.namespace, now=NOW, retry_waits=FAST
        )
        == []
    )
    assert fake.requests == []


async def test_only_the_namespace_of_the_key_is_reconciled(
    routed: Routed,
    writer_pool: RuntimePool,
    stripe_api: tuple[FakeStripe, StripeApiSource],
) -> None:
    fake, source = stripe_api
    fake.add(event("payment_intent.succeeded", 10))
    assert (
        await reconciliation.reconcile(
            writer_pool, source, namespace="FAKE-another-platform", now=NOW, retry_waits=FAST
        )
        == []
    )
    assert fake.requests == []


# B-07 -----------------------------------------------------------------------


async def test_logs_and_rows_hold_no_key_account_or_event(
    routed: Routed,
    writer_pool: RuntimePool,
    stripe_api: tuple[FakeStripe, StripeApiSource],
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.DEBUG)
    fake, source = stripe_api
    (event_id,) = fake.add(event("payment_intent.succeeded", 10))
    fake.failures = [500]
    await run(routed, writer_pool, source)
    shown = "\n".join(
        f"{r.getMessage()} {r.__dict__}"
        for r in caplog.records
        if not r.name.startswith(("httpx", "httpcore", "uvicorn", "stripe", "urllib3"))
    )
    assert fake.key.get_secret_value() not in shown
    assert ACCOUNT not in shown
    assert event_id not in shown
    assert fake.key.get_secret_value() not in repr(source)
    async with tenant_transaction(writer_pool, routed.tenant_id) as conn:
        row = await (
            await conn.execute(
                "select row_to_json(r)::text from gba.provider_reconciliation_runs r "
                "where tenant_id=%s",
                (routed.tenant_id,),
            )
        ).fetchone()
    assert row is not None
    assert fake.key.get_secret_value() not in row[0]
    assert ACCOUNT not in row[0]


# B-08 -----------------------------------------------------------------------


@pytest.mark.parametrize(
    ("pool_name", "statement"),
    [
        (
            "app",
            "insert into gba.provider_reconciliation_runs (tenant_id,connection_id) "
            "values (%(tenant)s,%(connection)s)",
        ),
        (
            "worker",
            "insert into gba.provider_reconciliation_runs (tenant_id,connection_id) "
            "values (%(tenant)s,%(connection)s)",
        ),
        ("writer", "update gba.provider_reconciliation_runs set pages=0"),
        ("writer", "delete from gba.provider_reconciliation_runs"),
        ("worker", "select * from gba.provider_reconciliation_runs"),
    ],
)
async def test_only_the_writer_records_runs(
    routed: Routed,
    app_pool: RuntimePool,
    writer_pool: RuntimePool,
    worker_pool: RuntimePool,
    pool_name: str,
    statement: str,
) -> None:
    pool = {"app": app_pool, "writer": writer_pool, "worker": worker_pool}[pool_name]
    params = {"tenant": routed.tenant_id, "connection": routed.connection_id}
    with pytest.raises(psycopg.errors.InsufficientPrivilege):
        async with tenant_transaction(pool, routed.tenant_id) as conn:
            await conn.execute(statement.encode(), params if "%(" in statement else None)


async def test_runs_are_permanent_and_consistent(
    routed: Routed,
    writer_pool: RuntimePool,
    owner_conn: psycopg.Connection,
    test_database: ProvisionedDatabase,
    stripe_api: tuple[FakeStripe, StripeApiSource],
) -> None:
    _, source = stripe_api
    await run(routed, writer_pool, source)
    with psycopg.connect(test_database.admin_dsn, dbname=test_database.name) as superuser:
        for conn in (owner_conn, superuser):
            for statement in (
                "update gba.provider_reconciliation_runs set pages=9",
                "delete from gba.provider_reconciliation_runs",
                "truncate gba.provider_reconciliation_runs",
            ):
                with conn.transaction(force_rollback=True):
                    conn.execute(
                        "select set_config('gba.tenant_id',%s,true)", (str(routed.tenant_id),)
                    )
                    with pytest.raises(psycopg.errors.CheckViolation):
                        conn.execute(statement.encode())
    # The counts must add up and a failed run must name its error class.
    for values in (
        {"seen": 2, "recorded": 1},
        {"outcome": "failed"},
        {"outcome": "completed", "error_class": "APIError"},
    ):
        row = {
            "pages": 1,
            "seen": 1,
            "recorded": 1,
            "duplicates": 0,
            "conflicts": 0,
            "refused": 0,
            "outcome": "completed",
            "error_class": None,
            **values,
        }
        with pytest.raises(psycopg.errors.CheckViolation):
            async with tenant_transaction(writer_pool, routed.tenant_id) as writer:
                await writer.execute(
                    "insert into gba.provider_reconciliation_runs (tenant_id,connection_id,"
                    "window_start,window_end,started_at,pages,seen,recorded,duplicates,"
                    "conflicts,refused,outcome,error_class) values (%(tenant)s,%(connection)s,"
                    "now()-interval '1 day',now(),now(),%(pages)s,%(seen)s,%(recorded)s,"
                    "%(duplicates)s,%(conflicts)s,%(refused)s,%(outcome)s,%(error_class)s)",
                    {"tenant": routed.tenant_id, "connection": routed.connection_id, **row},
                )


@pytest.mark.parametrize(
    ("damage", "repair"),
    [
        (
            "grant update (pages) on gba.provider_reconciliation_runs to gba_receipt_writer",
            "revoke update (pages) on gba.provider_reconciliation_runs from gba_receipt_writer",
        ),
        (
            "revoke insert (verifier) on gba.provider_event_attestations from gba_receipt_writer",
            "grant insert (verifier) on gba.provider_event_attestations to gba_receipt_writer",
        ),
    ],
)
async def test_the_guard_refuses_drift_in_the_reconciliation_schema(
    routed: Routed,
    writer_pool: RuntimePool,
    owner_conn: psycopg.Connection,
    damage: str,
    repair: str,
) -> None:
    owner_conn.execute(damage.encode())
    try:
        with pytest.raises(DatabaseUnavailableError):
            async with tenant_transaction(writer_pool, routed.tenant_id) as conn:
                await assert_provider_receipt_ready(conn)
    finally:
        owner_conn.execute(repair.encode())
    async with tenant_transaction(writer_pool, routed.tenant_id) as conn:
        await assert_provider_receipt_ready(conn)


def test_the_key_is_never_shown() -> None:
    key = SecretStr("sk_test_FAKE" + secrets.token_hex(16))
    source = StripeApiSource(key, base_url="http://127.0.0.1:9", timeout=1)
    assert key.get_secret_value() not in repr(source) + str(source)
    with pytest.raises(ValueError, match="timeout"):
        StripeApiSource(key, timeout=0)
