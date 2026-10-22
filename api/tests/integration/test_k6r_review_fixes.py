"""K6r: fixes of the independent K6 review (docs/plan/evidence/2026-10-22-k6-review/REVIEW.md).

R1 a run interrupted mid-way is recorded as failed with balanced counts and never stops the other
connections; R2 failures and runs are visible (log fields, the latest run per connection); R3 the
worker reads only the keys of releases; R5 one run reads at most ten pages; R6 the exact request;
R7 a release race repeats the answer; R8 a retrieved receipt says how it was authenticated; and the
named test gaps. Synthetic only; a local fake Stripe API; no real key, account or money.
"""

import asyncio
import json
import logging
from collections.abc import Iterator
from typing import Any
from uuid import UUID, uuid7

import psycopg
import pytest

from gorgona_booking.db.pool import RuntimePool, set_tenant_context, tenant_transaction
from gorgona_booking.db.provider_receipt_guard import assert_provider_receipt_ready
from gorgona_booking.db.provisioning import owner_tenant_transaction
from gorgona_booking.errors import DatabaseUnavailableError
from gorgona_booking.observability import JsonFormatter
from gorgona_booking.providers import receipt_worker as worker
from gorgona_booking.providers import reconciliation
from gorgona_booking.providers.authenticated_receipts import receive_retrieved_event
from gorgona_booking.providers.reconciliation import StripeApiSource
from gorgona_booking.providers.stripe_events import SUPPORTED_EVENT_TYPES
from tests.integration import test_k6a_bounded_retries as retries
from tests.integration import test_k6b_event_backfill as backfill
from tests.integration import test_provider_connection_admissions as admissions
from tests.integration import test_provider_payments as shared
from tests.integration import test_provider_receipt_attestations as attested
from tests.integration import test_provider_receipt_decisions as decided
from tests.integration.conftest import ProvisionedDatabase
from tests.integration.live_server import free_port, live_server
from tests.integration.test_provider_payments import Money, event
from tests.integration.test_provider_receipt_attestations import Routed

pytestmark = pytest.mark.anyio
client = shared.client
idp = shared.idp
manager_a = shared.manager_a
manager_b = shared.manager_b
enabled = shared.enabled
invoices = shared.invoices
payments = shared.payments
credits = shared.credits
inbox = shared.inbox
writer_pool = shared.writer_pool
routed = shared.routed
worker_pool = shared.worker_pool
money = shared.money
FAST = backfill.FAST
NOTE = "FAKE fixed the cause; try the event again"


@pytest.fixture
def stripe_api() -> Iterator[tuple[backfill.FakeStripe, StripeApiSource]]:
    fake = backfill.FakeStripe()
    with live_server(fake.app(), free_port()) as base:
        yield fake, StripeApiSource(fake.key, base_url=base, timeout=0.5)


def second_connection(owner_conn: psycopg.Connection, scope: Routed, account: str) -> Routed:
    """Another admitted connection of the same company and platform namespace."""
    connection = uuid7()
    with owner_tenant_transaction(owner_conn, scope.tenant_id):
        owner_conn.execute(
            "insert into gba.provider_receipt_connections "
            "(tenant_id,id,book_id,namespace,account_id,api_version) values (%s,%s,%s,%s,%s,%s)",
            (
                scope.tenant_id,
                connection,
                scope.book_id,
                scope.policy.namespace,
                account,
                scope.policy.api_version,
            ),
        )
    return attested.provision(
        owner_conn,
        tenant_id=scope.tenant_id,
        connection_id=connection,
        book_id=scope.book_id,
        namespace=scope.policy.namespace,
        account_id=account,
    )


async def reconcile(pool: RuntimePool, source: Any, scope: Routed) -> dict[UUID, Any]:
    runs = await reconciliation.reconcile(
        pool, source, namespace=scope.policy.namespace, now=backfill.NOW, retry_waits=FAST
    )
    return {run.connection_id: run for run in runs}


def balanced(run: reconciliation.ReconciliationRun) -> bool:
    return run.seen == run.recorded + run.duplicates + run.conflicts + run.refused


# R1 -------------------------------------------------------------------------


async def test_a_suspension_mid_run_fails_that_run_and_the_other_connection_goes_on(
    routed: Routed,
    writer_pool: RuntimePool,
    owner_conn: psycopg.Connection,
    stripe_api: tuple[backfill.FakeStripe, StripeApiSource],
) -> None:
    fake, source = stripe_api
    other = second_connection(owner_conn, routed, "acct_FAKEsecond")
    fake.add(
        *(
            backfill.event("payment_intent.succeeded", n, object_id=f"pi_FAKEmid{n}")
            for n in range(1, 151)
        )
    )
    fake.add(
        backfill.event("payment_intent.succeeded", 5, object_id="pi_FAKEother1"),
        account="acct_FAKEsecond",
        keep_account=False,
    )

    class Suspending:
        """The owner suspends the first connection right after its first page arrives."""

        async def page(self, **query: Any) -> bytes:
            page = await source.page(**query)
            if query["account"] == routed.policy.account_id and query["starting_after"] is None:
                admissions.admit(owner_conn, routed, "suspended")
            return page

    runs = await reconcile(writer_pool, Suspending(), routed)
    stopped, went_on = runs[routed.connection_id], runs[other.connection_id]
    assert (stopped.outcome, stopped.error_class) == ("failed", "ReceiptBindingRejectedError")
    assert balanced(stopped)
    assert stopped.recorded == 0  # the suspension refuses every event of the page
    assert (went_on.outcome, went_on.recorded) == ("completed", 1)
    assert balanced(went_on)


async def test_an_unexpected_error_fails_only_its_own_connection(
    routed: Routed,
    writer_pool: RuntimePool,
    owner_conn: psycopg.Connection,
    stripe_api: tuple[backfill.FakeStripe, StripeApiSource],
) -> None:
    fake, source = stripe_api
    other = second_connection(owner_conn, routed, "acct_FAKEbroken")
    fake.add(backfill.event("payment_intent.succeeded", 5))

    class Broken:
        async def page(self, **query: Any) -> bytes:
            if query["account"] == "acct_FAKEbroken":
                raise RuntimeError("FAKE transport fault")
            return await source.page(**query)

    runs = await reconcile(writer_pool, Broken(), routed)
    assert (runs[other.connection_id].outcome, runs[other.connection_id].error_class) == (
        "failed",
        "RuntimeError",
    )
    assert (runs[routed.connection_id].outcome, runs[routed.connection_id].recorded) == (
        "completed",
        1,
    )


# R2 -------------------------------------------------------------------------


def test_the_json_log_line_keeps_counts_and_error_classes() -> None:
    record = logging.LogRecord(
        "gorgona_booking.providers.reconciliation", logging.INFO, __file__, 1, "run", None, None
    )
    fields = {
        "error": "APIError",
        "attempts": 3,
        "parked": False,
        "outcome": "failed",
        "pages": 1,
        "seen": 2,
        "recorded": 1,
        "duplicates": 1,
        "conflicts": 0,
        "refused": 0,
        "runs": 1,
        "decided": 4,
    }
    for name, value in fields.items():
        setattr(record, name, value)
    line = json.loads(JsonFormatter().format(record))
    assert {name: line.get(name) for name in fields} == fields


async def test_each_run_is_counted_by_outcome_and_error_class(
    routed: Routed,
    writer_pool: RuntimePool,
    stripe_api: tuple[backfill.FakeStripe, StripeApiSource],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake, source = stripe_api
    seen: list[tuple[str, str | None]] = []
    monkeypatch.setattr(
        reconciliation,
        "record_provider_reconciliation",
        lambda outcome, error_class, tenant: seen.append((outcome, error_class)),
    )
    fake.failures = [400]
    await reconcile(writer_pool, source, routed)
    await reconcile(writer_pool, source, routed)
    assert seen == [("failed", "InvalidRequestError"), ("completed", None)]


async def test_the_connection_list_shows_its_latest_reconciliation(
    money: Money, stripe_api: tuple[backfill.FakeStripe, StripeApiSource]
) -> None:
    fake, source = stripe_api

    async def latest() -> Any:
        response = await money.http.get(
            f"{money.root}/provider-connections", headers=money.credits.ledger.auth
        )
        assert response.status_code == 200, response.text
        (item,) = [
            x
            for x in response.json()["items"]
            if x["connection_id"] == str(money.routed.connection_id)
        ]
        return item["last_reconciliation"]

    assert await latest() is None
    fake.add(backfill.event("payment_intent.succeeded", 5))
    await reconcile(money.writer, source, money.routed)
    shown = await latest()
    assert (shown["outcome"], shown["error_class"], shown["recorded"]) == ("completed", None, 1)
    fake.failures = [401]
    await reconcile(money.writer, source, money.routed)
    shown = await latest()
    assert (shown["outcome"], shown["error_class"], shown["recorded"]) == (
        "failed",
        "AuthenticationError",
        0,
    )
    assert shown["finished_at"]


# R3 -------------------------------------------------------------------------


async def test_the_worker_reads_only_the_keys_of_releases(
    money: Money, owner_conn: psycopg.Connection
) -> None:
    tenant = money.routed.tenant_id
    (bad,) = await decided.receive_all(
        money.writer, money.routed, event("payment_intent.succeeded")
    )
    await retries.fail(money.worker, tenant, bad, worker.MAX_FAILURES)
    assert (await retries.release(money, bad)).status_code == 200
    async with tenant_transaction(money.worker, tenant) as conn:
        rows = await (
            await conn.execute(
                "select tenant_id,event_id,round from gba.provider_event_releases "
                "where event_id=%s",
                (bad,),
            )
        ).fetchall()
    assert [row[2] for row in rows] == [1]
    for column in ("note", "released_by", "released_at", "*"):
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            async with tenant_transaction(money.worker, tenant) as conn:
                await conn.execute(f"select {column} from gba.provider_event_releases".encode())
    owner_conn.execute("grant select on gba.provider_event_releases to gba_receipt_worker")
    try:
        with pytest.raises(DatabaseUnavailableError):
            async with tenant_transaction(money.worker, tenant) as conn:
                await assert_provider_receipt_ready(conn)
    finally:
        owner_conn.execute("revoke select on gba.provider_event_releases from gba_receipt_worker")
        owner_conn.execute(
            "grant select (tenant_id,event_id,round) on gba.provider_event_releases "
            "to gba_receipt_worker"
        )
    async with tenant_transaction(money.worker, tenant) as conn:
        await assert_provider_receipt_ready(conn)


# R5 / R6 --------------------------------------------------------------------


def test_one_run_reads_at_most_ten_pages_as_the_owner_approved() -> None:
    assert reconciliation.MAX_PAGES == 10
    assert reconciliation.PAGE_SIZE == 100


async def test_the_request_names_the_account_window_types_and_page_size(
    routed: Routed,
    writer_pool: RuntimePool,
    stripe_api: tuple[backfill.FakeStripe, StripeApiSource],
) -> None:
    fake, source = stripe_api
    fake.add(backfill.event("payment_intent.succeeded", 5))
    await reconcile(writer_pool, source, routed)
    (request,) = fake.requests
    assert request["authorized"]
    assert request["account"] == routed.policy.account_id
    items: list[tuple[str, str]] = request["items"]
    keys = [key for key, _ in items]
    assert sorted(value for key, value in items if key.startswith("types")) == sorted(
        SUPPORTED_EVENT_TYPES
    )
    assert all(key == f"types[{n}]" for n, key in enumerate(k for k in keys if k[:5] == "types"))
    window = dict(items)
    assert int(window["created[lt]"]) == int(backfill.NOW.timestamp())
    assert int(window["created[lt]"]) - int(window["created[gte]"]) == 3 * 86_400
    assert window["limit"] == "100"
    assert "starting_after" not in window


# R7 and the release test gaps ------------------------------------------------


async def user_id(owner_conn: psycopg.Connection, money: Money) -> UUID:
    with owner_tenant_transaction(owner_conn, money.routed.tenant_id):
        row = owner_conn.execute(
            "select user_id from gba.memberships where tenant_id=%s limit 1",
            (money.routed.tenant_id,),
        ).fetchone()
    assert row is not None
    return UUID(str(row[0]))


async def test_sql_refuses_a_release_of_a_waiting_or_decided_event(
    money: Money, app_pool: RuntimePool, owner_conn: psycopg.Connection
) -> None:
    tenant = money.routed.tenant_id
    waiting, done = await decided.receive_all(
        money.writer,
        money.routed,
        event("payment_intent.succeeded", object_id="pi_FAKEwaitingr1"),
        event("payment_intent.succeeded", object_id="pi_FAKEdecidedr1"),
    )
    await retries.fail(money.worker, tenant, waiting, 1)
    await worker.process_batch(money.worker, tenant_id=tenant, retry_seconds=3600)
    user = await user_id(owner_conn, money)
    for event_id in (waiting, done):
        with pytest.raises(psycopg.errors.CheckViolation):
            async with tenant_transaction(app_pool, tenant) as conn:
                await conn.execute(
                    "insert into gba.provider_event_releases "
                    "(tenant_id,event_id,note,released_by) values (%s,%s,%s,%s)",
                    (tenant, event_id, NOTE, user),
                )


async def test_two_concurrent_releases_wait_one_wins_and_the_same_note_repeats(
    money: Money,
    app_pool: RuntimePool,
    owner_conn: psycopg.Connection,
    test_database: ProvisionedDatabase,
) -> None:
    tenant = money.routed.tenant_id
    (bad,) = await decided.receive_all(
        money.writer, money.routed, event("payment_intent.succeeded")
    )
    await retries.fail(money.worker, tenant, bad, worker.MAX_FAILURES)
    user = await user_id(owner_conn, money)
    insert = (
        "insert into gba.provider_event_releases (tenant_id,event_id,note,released_by) "
        "values (%s,%s,%s,%s)"
    )

    async def second() -> None:
        async with tenant_transaction(app_pool, tenant) as conn:
            await conn.execute(insert, (tenant, bad, NOTE, user))

    follower = None
    monitor = await psycopg.AsyncConnection.connect(
        test_database.admin_dsn, dbname=test_database.name, autocommit=True
    )
    try:
        async with app_pool.connection() as conn, conn.transaction():
            await set_tenant_context(conn, tenant)
            await conn.execute(insert, (tenant, bad, NOTE, user))
            follower = asyncio.create_task(second())
            await decided.blocked_by(
                monitor, await decided.backend(conn), "insert into gba.provider_event_releases"
            )
        with pytest.raises(psycopg.errors.UniqueViolation):
            await asyncio.wait_for(follower, 15)
    finally:
        if follower is not None and not follower.done():
            follower.cancel()
            await asyncio.gather(follower, return_exceptions=True)
        await monitor.close()
    again = await retries.release(money, bad)
    assert again.status_code == 200, again.text
    assert again.json()["item"]["kind"] == "undecided"


# R8 -------------------------------------------------------------------------


async def test_a_retrieved_receipt_says_it_was_retrieved(
    routed: Routed, writer_pool: RuntimePool
) -> None:
    raw = backfill.event("payment_intent.succeeded", 5)
    retrieved = await receive_retrieved_event(writer_pool, routed.ingress_id, json.loads(raw))
    assert retrieved.authority == "retrieved_not_admitted"
    signed = await attested.receive(writer_pool, routed, raw)
    assert signed.authority == "signature_checked_not_admitted"


# Run record trigger -----------------------------------------------------------


async def test_a_run_of_another_company_or_from_the_future_is_refused(
    routed: Routed, writer_pool: RuntimePool
) -> None:
    for tenant, started in ((uuid7(), "now()"), (routed.tenant_id, "now()+interval '1 hour'")):
        with pytest.raises(psycopg.errors.CheckViolation):
            async with tenant_transaction(writer_pool, routed.tenant_id) as conn:
                await conn.execute(
                    (
                        "insert into gba.provider_reconciliation_runs (tenant_id,connection_id,"
                        "window_start,window_end,started_at,pages,seen,recorded,duplicates,"
                        "conflicts,refused,outcome,error_class) values (%s,%s,now()-interval "
                        f"'1 day',now(),{started},0,0,0,0,0,0,'completed',null)"
                    ).encode(),
                    (tenant, routed.connection_id),
                )
