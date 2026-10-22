"""K6a: bounded retries of the receipt worker, parked events and their release; synthetic only.

Owner decisions 2026-10-21 (all defaults of the K6 design): an event whose decision fails is
recorded, retried after 1, 2, 4 and 8 waits, and parked after 5 failures; a finance user releases
it with a note. Only event-level database errors count; an outage stops the batch uncounted.
No provider account, real key, network call, ledger, settlement or obligation is involved.
"""

import asyncio
from collections.abc import Awaitable, Callable
from itertools import pairwise
from typing import Any
from uuid import UUID, uuid4, uuid7

import httpx
import psycopg
import pytest

from gorgona_booking.db.pool import RuntimeConnection, RuntimePool, tenant_transaction
from gorgona_booking.db.provider_receipt_guard import assert_provider_receipt_ready
from gorgona_booking.db.provisioning import add_membership, owner_tenant_transaction
from gorgona_booking.errors import DatabaseUnavailableError
from gorgona_booking.providers import receipt_worker as worker
from tests.integration import test_provider_payments as shared
from tests.integration import test_provider_receipt_decisions as decided
from tests.integration.booking_support import BookingWorld
from tests.integration.conftest import ProvisionedDatabase
from tests.integration.seed import FakeUser, seed_user
from tests.integration.test_provider_payments import Money, event
from tests.integration.test_provider_receipt_attestations import Routed
from tests.support.fake_idp import FakeIdp

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
NOTE = "FAKE fixed the cause; try the event again"
NEW_TABLES = ("provider_event_failures", "provider_event_releases")

Decide = Callable[..., Awaitable[worker.ReceiptDecision]]


def failing(monkeypatch: pytest.MonkeyPatch, bad: set[UUID], *statements: str) -> None:
    """The decision of each `bad` event first runs `statements` on its real connection."""
    real: Decide = worker.decide

    async def decide(
        conn: RuntimeConnection, tenant_id: UUID, event_id: UUID, **kwargs: Any
    ) -> worker.ReceiptDecision:
        if event_id in bad:
            for statement in statements or ("select 1/0",):
                await conn.execute(statement.encode())
        return await real(conn, tenant_id, event_id, **kwargs)

    monkeypatch.setattr(worker, "decide", decide)


async def failures(pool: RuntimePool, tenant: UUID, event_id: UUID) -> list[tuple[Any, ...]]:
    async with tenant_transaction(pool, tenant) as conn:
        rows = await (
            await conn.execute(
                "select generation,round,error_class,failed_at from gba.provider_event_failures "
                "where tenant_id=%s and event_id=%s order by failed_at,generation",
                (tenant, event_id),
            )
        ).fetchall()
    return [tuple(row) for row in rows]


async def fail(pool: RuntimePool, tenant: UUID, event_id: UUID, times: int) -> None:
    """Claim with a one-second lease and record a failure, `times` times in a row."""
    holder = uuid4()
    for _ in range(times):
        async with tenant_transaction(pool, tenant) as conn:
            generation = await worker.claim(conn, tenant, event_id, holder=holder, lease_seconds=1)
        assert generation is not None
        async with tenant_transaction(pool, tenant) as conn:
            await worker.record_failure(
                conn,
                tenant,
                event_id,
                holder=holder,
                generation=generation,
                error_class="DivisionByZero",
            )
        await asyncio.sleep(1.05)


# A-01 -----------------------------------------------------------------------


async def test_a_failing_event_is_recorded_and_the_batch_goes_on(
    routed: Routed,
    writer_pool: RuntimePool,
    worker_pool: RuntimePool,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    bad, good = await decided.receive_all(
        writer_pool,
        routed,
        decided.stripe("payment_intent.succeeded", object_id="pi_FAKEpoison1"),
        decided.stripe("payment_intent.succeeded", object_id="pi_FAKEhealthy1"),
    )
    failing(monkeypatch, {bad})
    result = await worker.process_batch(worker_pool, tenant_id=routed.tenant_id)
    assert [d.event_id for d in result] == [good]
    stored = await decided.decisions(worker_pool, routed.tenant_id)
    assert bad not in stored
    assert stored[good][:2] == ("observed", "success")
    assert [row[:3] for row in await failures(worker_pool, routed.tenant_id, bad)] == [
        (1, 0, "DivisionByZero")
    ]


# A-02 -----------------------------------------------------------------------


@pytest.mark.parametrize(
    ("statements", "error"),
    [
        # A cancelled statement (an outage of the database's time budget).
        (("set local statement_timeout=1", "select pg_sleep(0.2)"), psycopg.errors.QueryCanceled),
        # Damaged privileges: the worker reaches a table it may not read.
        (("select 1 from gba.journal_entries limit 1",), psycopg.errors.InsufficientPrivilege),
    ],
)
async def test_an_outage_or_damage_stops_the_batch_without_counting(
    routed: Routed,
    writer_pool: RuntimePool,
    worker_pool: RuntimePool,
    monkeypatch: pytest.MonkeyPatch,
    statements: tuple[str, ...],
    error: type[Exception],
) -> None:
    (only,) = await decided.receive_all(
        writer_pool, routed, decided.stripe("payment_intent.succeeded")
    )
    real = worker.decide
    failing(monkeypatch, {only}, *statements)
    with pytest.raises(error):
        await worker.process_batch(worker_pool, tenant_id=routed.tenant_id, lease_seconds=1)
    assert await failures(worker_pool, routed.tenant_id, only) == []
    monkeypatch.setattr(worker, "decide", real)
    await asyncio.sleep(1.05)
    result = await worker.process_batch(worker_pool, tenant_id=routed.tenant_id, lease_seconds=1)
    assert [d.event_id for d in result] == [only]


# A-03 -----------------------------------------------------------------------


async def test_retries_wait_longer_each_time_then_the_event_is_parked(
    routed: Routed,
    writer_pool: RuntimePool,
    worker_pool: RuntimePool,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    (bad,) = await decided.receive_all(
        writer_pool, routed, decided.stripe("payment_intent.succeeded")
    )
    failing(monkeypatch, {bad})
    loop = asyncio.get_running_loop()
    deadline = loop.time() + 60
    while loop.time() < deadline:
        await worker.process_batch(
            worker_pool, tenant_id=routed.tenant_id, lease_seconds=1, retry_seconds=1
        )
        if len(await failures(worker_pool, routed.tenant_id, bad)) >= worker.MAX_FAILURES:
            break
        await asyncio.sleep(0.2)
    rows = await failures(worker_pool, routed.tenant_id, bad)
    assert [(row[0], row[1]) for row in rows] == [(n, 0) for n in range(1, 6)]
    gaps = [(b[3] - a[3]).total_seconds() for a, b in pairwise(rows)]
    # Waits of 1, 2, 4 and 8 retry units (one second here) after the 1st to the 4th failure.
    assert all(gap >= 2**n for n, gap in enumerate(gaps)), gaps
    for _ in range(3):
        await asyncio.sleep(1.1)
        assert (
            await worker.process_batch(
                worker_pool, tenant_id=routed.tenant_id, lease_seconds=1, retry_seconds=1
            )
            == []
        )
    assert len(await failures(worker_pool, routed.tenant_id, bad)) == worker.MAX_FAILURES
    assert bad not in await decided.decisions(worker_pool, routed.tenant_id)


# A-04 -----------------------------------------------------------------------


async def test_sql_keeps_failures_fenced_and_bounded_and_refuses_a_parked_claim(
    routed: Routed, writer_pool: RuntimePool, worker_pool: RuntimePool
) -> None:
    tenant = routed.tenant_id
    (only,) = await decided.receive_all(
        writer_pool, routed, decided.stripe("payment_intent.succeeded")
    )
    holder = uuid4()
    async with tenant_transaction(worker_pool, tenant) as conn:
        generation = await worker.claim(conn, tenant, only, holder=holder, lease_seconds=1)
    assert generation == 1
    forged: list[dict[str, Any]] = [
        {"holder": uuid4(), "generation": 1, "error_class": "DivisionByZero"},
        {"holder": holder, "generation": 2, "error_class": "DivisionByZero"},
        {"holder": holder, "generation": 1, "error_class": "not a class"},
    ]
    for values in forged:
        with pytest.raises(psycopg.errors.CheckViolation):
            async with tenant_transaction(worker_pool, tenant) as conn:
                await worker.record_failure(conn, tenant, only, **values)
    async with tenant_transaction(worker_pool, tenant) as conn:
        await worker.record_failure(
            conn, tenant, only, holder=holder, generation=1, error_class="DivisionByZero"
        )
    await asyncio.sleep(1.05)
    # The lease expired: a late failure of this holder is refused, like a late decision.
    with pytest.raises(psycopg.errors.CheckViolation):
        async with tenant_transaction(worker_pool, tenant) as conn:
            await worker.record_failure(
                conn, tenant, only, holder=holder, generation=1, error_class="DivisionByZero"
            )
    await fail(worker_pool, tenant, only, worker.MAX_FAILURES - 1)
    # Parked: neither the worker's claim nor any SQL may take a lease again.
    with pytest.raises(psycopg.errors.CheckViolation):
        async with tenant_transaction(worker_pool, tenant) as conn:
            await worker.claim(conn, tenant, only, holder=uuid4(), lease_seconds=1)
    assert len(await failures(worker_pool, tenant, only)) == worker.MAX_FAILURES


# A-05 -----------------------------------------------------------------------


@pytest.mark.parametrize(
    ("pool_name", "statement"),
    [
        (
            "app",
            "insert into gba.provider_event_failures (tenant_id,event_id,generation,holder,"
            "error_class) values (%(tenant)s,%(event)s,9,%(holder)s,'X')",
        ),
        (
            "worker",
            "insert into gba.provider_event_releases (tenant_id,event_id,note,released_by) "
            "values (%(tenant)s,%(event)s,'x',%(holder)s)",
        ),
        ("writer", "select * from gba.provider_event_failures"),
        ("writer", "select * from gba.provider_event_releases"),
        ("app", "update gba.provider_event_failures set error_class='X'"),
        ("worker", "delete from gba.provider_event_failures"),
    ],
)
async def test_only_the_worker_records_failures_and_only_the_runtime_releases(
    routed: Routed,
    app_pool: RuntimePool,
    writer_pool: RuntimePool,
    worker_pool: RuntimePool,
    pool_name: str,
    statement: str,
) -> None:
    (only,) = await decided.receive_all(
        writer_pool, routed, decided.stripe("payment_intent.succeeded")
    )
    pool = {"app": app_pool, "writer": writer_pool, "worker": worker_pool}[pool_name]
    params = {"tenant": routed.tenant_id, "event": only, "holder": uuid4()}
    with pytest.raises(psycopg.errors.InsufficientPrivilege):
        async with tenant_transaction(pool, routed.tenant_id) as conn:
            await conn.execute(statement.encode(), params if "%(" in statement else None)


async def test_failures_and_releases_are_permanent_even_for_owner_and_superuser(
    money: Money,
    owner_conn: psycopg.Connection,
    test_database: ProvisionedDatabase,
) -> None:
    (bad,) = await decided.receive_all(
        money.writer, money.routed, event("payment_intent.succeeded")
    )
    await fail(money.worker, money.routed.tenant_id, bad, worker.MAX_FAILURES)
    assert (await release(money, bad)).status_code == 200
    tenant = money.routed.tenant_id
    with psycopg.connect(test_database.admin_dsn, dbname=test_database.name) as superuser:
        for conn in (owner_conn, superuser):
            for statement in (
                "update gba.provider_event_failures set error_class='X'",
                "delete from gba.provider_event_failures",
                "update gba.provider_event_releases set note='X'",
                "delete from gba.provider_event_releases",
                *(f"truncate gba.{table} cascade" for table in NEW_TABLES),
            ):
                with conn.transaction(force_rollback=True):
                    conn.execute("select set_config('gba.tenant_id',%s,true)", (str(tenant),))
                    with pytest.raises(psycopg.errors.CheckViolation):
                        conn.execute(statement.encode())
    assert len(await failures(money.worker, tenant, bad)) == worker.MAX_FAILURES


# A-06 -----------------------------------------------------------------------


async def attention(money: Money, auth: dict[str, str] | None = None) -> dict[str, Any]:
    response = await money.http.get(
        f"{money.root}/provider-attention", headers=auth or money.credits.ledger.auth
    )
    assert response.status_code == 200, response.text
    return {item["event_id"]: item for item in response.json()["items"]}


async def release(
    money: Money, event_id: UUID, note: object = NOTE, auth: dict[str, str] | None = None
) -> httpx.Response:
    return await money.http.put(
        f"{money.root}/provider-attention/{event_id}/release",
        json={"schema_version": 1, "note": note},
        headers=auth or money.credits.ledger.headers(),
    )


async def test_a_parked_event_is_shown_and_a_release_lets_the_worker_try_again(
    money: Money, owner_conn: psycopg.Connection
) -> None:
    tenant = money.routed.tenant_id
    bad, waiting = await decided.receive_all(
        money.writer,
        money.routed,
        event("payment_intent.succeeded"),
        event("payment_intent.succeeded", object_id="pi_FAKEwaiting1"),
    )
    await fail(money.worker, tenant, bad, worker.MAX_FAILURES)
    await fail(money.worker, tenant, waiting, 1)
    listed = await attention(money)
    parked = listed[str(bad)]
    assert parked["kind"] == "failed"
    assert parked["failure"]["attempts"] == worker.MAX_FAILURES
    assert parked["failure"]["error_class"] == "DivisionByZero"
    assert parked["failure"]["last_failed_at"]
    assert listed[str(waiting)]["kind"] == "undecided"
    assert listed[str(waiting)]["failure"]["attempts"] == 1
    # A waiting event is not parked and takes no release.
    refused = await release(money, waiting)
    assert refused.status_code == 409, refused.text
    assert refused.json()["error"]["code"] == "PROVIDER_ATTENTION_NOT_NEEDED"
    for note in ("", " ", "a\u0007b", "x" * 501, 5):
        assert (await release(money, bad, note)).status_code == 422
    given = await release(money, bad)
    assert given.status_code == 200, given.text
    item = given.json()["item"]
    assert (item["kind"], item["failure"]) == ("undecided", None)
    # The same note again repeats the answer; another note is refused.
    assert (await release(money, bad)).json()["item"] == item
    other = await release(money, bad, "FAKE another note")
    assert other.status_code == 409, other.text
    assert other.json()["error"]["code"] == "PROVIDER_EVENT_RELEASED"
    result = await worker.process_batch(money.worker, tenant_id=tenant)
    assert bad in {d.event_id for d in result}
    assert str(bad) not in await attention(money)
    # K6r (review R3): the worker reads only the keys of a release; the owner reads the note.
    with owner_tenant_transaction(owner_conn, tenant):
        rows = owner_conn.execute(
            "select round,note from gba.provider_event_releases where event_id=%s", (bad,)
        ).fetchall()
    assert [tuple(r) for r in rows] == [(1, NOTE)]


async def test_a_second_parking_needs_a_second_release(money: Money) -> None:
    tenant = money.routed.tenant_id
    (bad,) = await decided.receive_all(
        money.writer, money.routed, event("payment_intent.succeeded")
    )
    await fail(money.worker, tenant, bad, worker.MAX_FAILURES)
    assert (await release(money, bad)).status_code == 200
    await fail(money.worker, tenant, bad, worker.MAX_FAILURES)
    rows = await failures(money.worker, tenant, bad)
    assert [row[1] for row in rows] == [0] * 5 + [1] * 5
    assert (await attention(money))[str(bad)]["kind"] == "failed"
    second = await release(money, bad, "FAKE second release")
    assert second.status_code == 200, second.text


@pytest.mark.parametrize(
    ("role", "branch", "expected"),
    [
        ("owner", False, 200),
        ("front_desk", False, 403),
        ("artist", False, 403),
        ("manager", True, 403),
    ],
)
async def test_a_release_needs_company_finance_rights(
    money: Money,
    owner_conn: psycopg.Connection,
    world: BookingWorld,
    idp: FakeIdp,
    role: str,
    branch: bool,
    expected: int,
) -> None:
    (bad,) = await decided.receive_all(
        money.writer, money.routed, event("payment_intent.succeeded")
    )
    await fail(money.worker, money.routed.tenant_id, bad, worker.MAX_FAILURES)
    member = seed_user(owner_conn, f"FAKE-K6a-{role}-{uuid7()}")
    add_membership(
        owner_conn,
        tenant_id=money.credits.ledger.business,
        user_id=member.user_id,
        role=role,
        location_id=world.a.location_id if branch else None,
    )
    auth = idp.bearer(member.subject, email=member.email)
    given = await release(money, bad, auth=auth)
    assert given.status_code == expected, given.text


async def test_another_company_cannot_release(
    money: Money, manager_b: FakeUser, idp: FakeIdp
) -> None:
    (bad,) = await decided.receive_all(
        money.writer, money.routed, event("payment_intent.succeeded")
    )
    await fail(money.worker, money.routed.tenant_id, bad, worker.MAX_FAILURES)
    auth = idp.bearer(manager_b.subject, email=manager_b.email)
    refused = await release(money, bad, auth=auth)
    assert refused.status_code in (403, 404), refused.text


# A-07 -----------------------------------------------------------------------


@pytest.mark.parametrize(
    ("damage", "repair"),
    [
        (
            "grant update (error_class) on gba.provider_event_failures to gba_receipt_worker",
            "revoke update (error_class) on gba.provider_event_failures from gba_receipt_worker",
        ),
        (
            "grant insert (round) on gba.provider_event_releases to gba_runtime",
            "revoke insert (round) on gba.provider_event_releases from gba_runtime",
        ),
        (
            "alter table gba.provider_event_failures disable trigger provider_event_failures_check",
            "alter table gba.provider_event_failures enable trigger provider_event_failures_check",
        ),
    ],
)
async def test_the_guard_refuses_drift_in_the_new_tables(
    routed: Routed,
    app_pool: RuntimePool,
    worker_pool: RuntimePool,
    owner_conn: psycopg.Connection,
    damage: str,
    repair: str,
) -> None:
    for pool in (app_pool, worker_pool):
        async with tenant_transaction(pool, routed.tenant_id) as conn:
            await assert_provider_receipt_ready(conn)
    owner_conn.execute(damage.encode())
    try:
        for pool in (app_pool, worker_pool):
            with pytest.raises(DatabaseUnavailableError):
                async with tenant_transaction(pool, routed.tenant_id) as conn:
                    await assert_provider_receipt_ready(conn)
    finally:
        owner_conn.execute(repair.encode())
    async with tenant_transaction(worker_pool, routed.tenant_id) as conn:
        await assert_provider_receipt_ready(conn)
