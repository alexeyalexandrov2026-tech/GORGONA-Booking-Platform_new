"""K2a: attested receipts become permanent decisions without money; synthetic only.

No provider account, real key, network call, ledger, settlement or obligation is involved.
"""

import asyncio
import secrets
from collections.abc import AsyncIterator
from typing import Any
from uuid import UUID, uuid4, uuid7

import psycopg
import pytest
from psycopg.conninfo import conninfo_to_dict, make_conninfo

from gorgona_booking.db.bootstrap import BootstrapSpec, bootstrap
from gorgona_booking.db.pool import (
    RuntimeConnection,
    RuntimePool,
    UnsafeDatabaseRoleError,
    assert_safe_runtime_role,
    create_runtime_pool,
    set_tenant_context,
    tenant_transaction,
)
from gorgona_booking.db.provider_receipt_guard import assert_provider_receipt_ready
from gorgona_booking.errors import DatabaseUnavailableError
from gorgona_booking.providers import receipt_worker as worker
from gorgona_booking.providers.authenticated_receipts import (
    UnsafeReceiptWriterRoleError,
    assert_safe_receipt_writer_role,
)
from gorgona_booking.providers.receipt_worker import ReceiptDecision, UnsafeReceiptWorkerRoleError
from tests.integration import test_provider_event_inbox as archive
from tests.integration import test_provider_receipt_attestations as attested
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
WORKER_ROLE = "gba_test_receipt_worker"
NEW_TABLES = ("provider_operations", "provider_event_leases", "provider_event_decisions")


@pytest.fixture
async def worker_pool(test_database: ProvisionedDatabase) -> AsyncIterator[RuntimePool]:
    owner = conninfo_to_dict(test_database.owner_dsn)
    app = conninfo_to_dict(test_database.app_dsn)
    password = secrets.token_urlsafe(32)
    bootstrap(
        test_database.admin_dsn,
        BootstrapSpec(
            database=test_database.name,
            owner_role=str(owner["user"]),
            owner_password=str(owner["password"]),
            app_role=str(app["user"]),
            app_password=str(app["password"]),
            receipt_worker_role=WORKER_ROLE,
            receipt_worker_password=password,
        ),
    )
    pool = create_runtime_pool(
        make_conninfo(test_database.app_dsn, user=WORKER_ROLE, password=password)
    )
    await pool.open(wait=True)
    try:
        yield pool
    finally:
        await pool.close()


def stripe(
    kind: str,
    *,
    status: str = "succeeded",
    object_id: str | None = None,
    payment_intent: str | None = "pi_FAKEpayment1",
    amount: int = 1000,
    currency: str = "usd",
    **resource: Any,
) -> bytes:
    """One signed-shape event with its own ID; unspecified fields keep the synthetic defaults."""
    value = signed.event(kind)
    value["id"] = "evt_FAKE" + uuid7().hex
    value["account"] = "acct_FAKEreceipt"
    body = value["data"]["object"]
    body.update(status=status, currency=currency, amount=amount)
    if object_id is not None:
        body["id"] = object_id
    if body["object"] == "payment_intent":
        body["amount_received"] = amount if status == "succeeded" else 0
    else:
        body["payment_intent"] = payment_intent
    if body["object"] == "charge":
        body["amount_captured"] = amount if status == "succeeded" else 0
    body.update(resource)
    return signed.body(value)


async def receive_all(writer: RuntimePool, scope: Routed, *raws: bytes) -> list[UUID]:
    return [(await attested.receive(writer, scope, raw)).event_id for raw in raws]


async def decisions(pool: RuntimePool, tenant: UUID) -> dict[UUID, tuple[object, ...]]:
    async with tenant_transaction(pool, tenant) as conn:
        rows = await (
            await conn.execute(
                # The worker may read every company's decisions (discovery); keep this one's.
                "select event_id,outcome,reason,operation_id from gba.provider_event_decisions "
                "where tenant_id=%s",
                (tenant,),
            )
        ).fetchall()
    return {row[0]: tuple(row[1:]) for row in rows}


async def operations(pool: RuntimePool, tenant: UUID) -> dict[UUID, tuple[object, ...]]:
    async with tenant_transaction(pool, tenant) as conn:
        rows = await (
            await conn.execute(
                "select id,kind,provider_object_id,parent_object_id,currency "
                "from gba.provider_operations"
            )
        ).fetchall()
    return {row[0]: tuple(row[1:]) for row in rows}


async def blocked_by(monitor: psycopg.AsyncConnection[Any], pid: int, statement: str) -> None:
    """Return once a backend running `statement` waits on a lock held by `pid`."""
    deadline = asyncio.get_running_loop().time() + 8
    while asyncio.get_running_loop().time() < deadline:
        row = await (
            await monitor.execute(
                "select l.pid from pg_catalog.pg_locks l "
                "join pg_catalog.pg_stat_activity a on a.pid=l.pid "
                "where not l.granted and %s=any(pg_catalog.pg_blocking_pids(l.pid)) "
                "and a.datname=current_database() and a.query like %s",
                (pid, statement + "%"),
            )
        ).fetchone()
        if row is not None:
            return
        await asyncio.sleep(0.01)
    pytest.fail(f"Expected a pg_locks wait behind {pid} for: {statement}")


async def backend(conn: RuntimeConnection) -> int:
    row = await (await conn.execute("select pg_backend_pid()")).fetchone()
    assert row is not None
    return int(row[0])


# W-01 -----------------------------------------------------------------------


async def test_payment_intent_and_its_charge_are_one_payment_operation(
    routed: Routed, writer_pool: RuntimePool, worker_pool: RuntimePool
) -> None:
    first, second = await receive_all(
        writer_pool,
        routed,
        stripe("payment_intent.succeeded"),
        stripe("charge.succeeded", object_id="ch_FAKEcharge1"),
    )
    decided = await worker.process_batch(worker_pool, tenant_id=routed.tenant_id)
    assert {d.event_id for d in decided} == {first, second}
    stored = await decisions(worker_pool, routed.tenant_id)
    assert stored[first][:2] == stored[second][:2] == ("observed", "success")
    assert stored[first][2] == stored[second][2]
    assert list((await operations(worker_pool, routed.tenant_id)).values()) == [
        ("payment", "pi_FAKEpayment1", None, "usd")
    ]


async def test_a_refund_is_its_own_operation_even_when_it_arrives_first(
    routed: Routed, writer_pool: RuntimePool, worker_pool: RuntimePool
) -> None:
    refund, payment = await receive_all(
        writer_pool,
        routed,
        stripe("refund.updated", object_id="re_FAKErefund1", amount=500),
        stripe("payment_intent.succeeded"),
    )
    await worker.process_batch(worker_pool, tenant_id=routed.tenant_id)
    stored = await decisions(worker_pool, routed.tenant_id)
    found = await operations(worker_pool, routed.tenant_id)
    refunded, paid = stored[refund][2], stored[payment][2]
    assert isinstance(refunded, UUID)
    assert isinstance(paid, UUID)
    assert found[refunded] == ("refund", "re_FAKErefund1", "pi_FAKEpayment1", "usd")
    assert found[paid] == ("payment", "pi_FAKEpayment1", None, "usd")
    assert stored[refund][:2] == stored[payment][:2] == ("observed", "success")


# W-02 -----------------------------------------------------------------------


async def test_duplicates_and_repeated_runs_decide_each_event_once(
    routed: Routed, writer_pool: RuntimePool, worker_pool: RuntimePool
) -> None:
    raw = stripe("payment_intent.succeeded")
    event = (await attested.receive(writer_pool, routed, raw)).event_id
    assert (await attested.receive(writer_pool, routed, raw)).disposition == "duplicate"
    assert [
        d.event_id for d in await worker.process_batch(worker_pool, tenant_id=routed.tenant_id)
    ] == [event]
    assert await worker.process_batch(worker_pool, tenant_id=routed.tenant_id) == []
    assert (await attested.receive(writer_pool, routed, raw + b"\n")).event_id == event
    assert await worker.process_batch(worker_pool, tenant_id=routed.tenant_id) == []
    assert list(await decisions(worker_pool, routed.tenant_id)) == [event]


async def test_a_stale_state_after_a_success_is_not_final_and_the_success_stays(
    routed: Routed, writer_pool: RuntimePool, worker_pool: RuntimePool
) -> None:
    success, stale = await receive_all(
        writer_pool,
        routed,
        stripe("payment_intent.succeeded"),
        stripe("payment_intent.processing", status="processing"),
    )
    await worker.process_batch(worker_pool, tenant_id=routed.tenant_id)
    stored = await decisions(worker_pool, routed.tenant_id)
    assert stored[success][:2] == ("observed", "success")
    assert stored[stale][:2] == ("observed", "not_final")
    assert stored[success][2] == stored[stale][2]


# W-03 -----------------------------------------------------------------------

_REVIEW = [
    (
        "different-success-amount",
        [stripe("payment_intent.succeeded"), stripe("charge.succeeded", amount=900)],
        "conflicting_facts",
        True,
    ),
    (
        "different-currency",
        [
            stripe("payment_intent.succeeded"),
            stripe("charge.pending", status="pending", currency="eur"),
        ],
        "conflicting_facts",
        True,
    ),
    (
        "event-type-contradicts-status",
        [stripe("payment_intent.succeeded", status="processing")],
        "conflicting_facts",
        True,
    ),
    (
        "refund-names-another-payment",
        [
            stripe("refund.created", object_id="re_FAKErefund1", status="pending", amount=500),
            stripe(
                "refund.updated",
                object_id="re_FAKErefund1",
                amount=500,
                payment_intent="pi_FAKEpayment2",
            ),
        ],
        "conflicting_facts",
        True,
    ),
    (
        "charge-without-payment",
        [stripe("charge.succeeded", payment_intent=None)],
        "unkeyed_operation",
        False,
    ),
    ("charge-refunded", [stripe("charge.refunded", refunded=True)], "unkeyed_operation", False),
    (
        "refund-without-payment",
        [stripe("refund.updated", object_id="re_FAKErefund1", amount=500, payment_intent=None)],
        "refund_without_payment",
        False,
    ),
]


@pytest.mark.parametrize(
    ("raws", "reason", "keyed"), [pytest.param(r, s, k, id=i) for i, r, s, k in _REVIEW]
)
async def test_conflicts_and_unkeyed_facts_go_to_manual_review(
    routed: Routed,
    writer_pool: RuntimePool,
    worker_pool: RuntimePool,
    raws: list[bytes],
    reason: str,
    keyed: bool,
) -> None:
    events = await receive_all(writer_pool, routed, *raws)
    await worker.process_batch(worker_pool, tenant_id=routed.tenant_id)
    last = (await decisions(worker_pool, routed.tenant_id))[events[-1]]
    assert last[:2] == ("needs_review", reason)
    assert (last[2] is not None) is keyed


async def test_a_conflicting_variant_of_an_event_goes_to_manual_review(
    routed: Routed, writer_pool: RuntimePool, worker_pool: RuntimePool
) -> None:
    raw = stripe("payment_intent.succeeded")
    event = (await attested.receive(writer_pool, routed, raw)).event_id
    variant = raw.replace(b'"amount_received":1000', b'"amount_received":900')
    assert variant != raw
    assert (await attested.receive(writer_pool, routed, variant)).disposition == "conflict"
    await worker.process_batch(worker_pool, tenant_id=routed.tenant_id)
    assert (await decisions(worker_pool, routed.tenant_id))[event][:2] == (
        "needs_review",
        "conflicting_facts",
    )


# W-04 -----------------------------------------------------------------------


async def test_a_second_claimer_waits_for_the_first_and_skips(
    routed: Routed,
    writer_pool: RuntimePool,
    worker_pool: RuntimePool,
    test_database: ProvisionedDatabase,
) -> None:
    (event,) = await receive_all(writer_pool, routed, stripe("payment_intent.succeeded"))
    holder = uuid4()
    follower = None
    monitor = await psycopg.AsyncConnection.connect(
        test_database.admin_dsn, dbname=test_database.name, autocommit=True
    )
    try:
        async with worker_pool.connection() as conn, conn.transaction():
            await set_tenant_context(conn, routed.tenant_id)
            generation = await worker.claim(
                conn, routed.tenant_id, event, holder=holder, lease_seconds=60
            )
            assert generation == 1
            follower = asyncio.create_task(
                worker.process_batch(worker_pool, tenant_id=routed.tenant_id)
            )
            await blocked_by(monitor, await backend(conn), "insert into gba.provider_event_leases")
            assert not follower.done()
        assert await asyncio.wait_for(follower, 15) == []
    finally:
        if follower is not None and not follower.done():
            follower.cancel()
            await asyncio.gather(follower, return_exceptions=True)
        await monitor.close()
    async with tenant_transaction(worker_pool, routed.tenant_id) as conn:
        decision = await worker.decide(
            conn, routed.tenant_id, event, holder=holder, generation=generation
        )
    assert (decision.outcome, decision.reason, decision.generation) == ("observed", "success", 1)
    assert list(await decisions(worker_pool, routed.tenant_id)) == [event]


# W-05 -----------------------------------------------------------------------


async def test_events_of_one_operation_are_decided_in_turn(
    routed: Routed,
    writer_pool: RuntimePool,
    worker_pool: RuntimePool,
    test_database: ProvisionedDatabase,
) -> None:
    first, second = await receive_all(
        writer_pool,
        routed,
        stripe("payment_intent.succeeded"),
        stripe("charge.succeeded", amount=900),
    )
    holder = uuid4()
    claims: dict[UUID, int] = {}
    for event in (first, second):
        async with tenant_transaction(worker_pool, routed.tenant_id) as conn:
            claimed = await worker.claim(
                conn, routed.tenant_id, event, holder=holder, lease_seconds=60
            )
            assert claimed is not None
            claims[event] = claimed

    async def decide_second() -> ReceiptDecision:
        async with tenant_transaction(worker_pool, routed.tenant_id) as conn:
            return await worker.decide(
                conn, routed.tenant_id, second, holder=holder, generation=claims[second]
            )

    follower = None
    monitor = await psycopg.AsyncConnection.connect(
        test_database.admin_dsn, dbname=test_database.name, autocommit=True
    )
    try:
        async with worker_pool.connection() as conn, conn.transaction():
            await set_tenant_context(conn, routed.tenant_id)
            leader = await worker.decide(
                conn, routed.tenant_id, first, holder=holder, generation=claims[first]
            )
            follower = asyncio.create_task(decide_second())
            await blocked_by(
                monitor, await backend(conn), "insert into gba.provider_event_decisions"
            )
            assert not follower.done()
        later = await asyncio.wait_for(follower, 15)
    finally:
        if follower is not None and not follower.done():
            follower.cancel()
            await asyncio.gather(follower, return_exceptions=True)
        await monitor.close()
    assert (leader.outcome, leader.reason) == ("observed", "success")
    assert (later.outcome, later.reason) == ("needs_review", "conflicting_facts")
    assert later.operation_id == leader.operation_id


# W-06 -----------------------------------------------------------------------


async def test_an_expired_lease_cannot_commit_after_a_new_claim(
    routed: Routed, writer_pool: RuntimePool, worker_pool: RuntimePool
) -> None:
    (event,) = await receive_all(writer_pool, routed, stripe("payment_intent.succeeded"))
    stale, fresh = uuid4(), uuid4()
    tenant = routed.tenant_id
    async with tenant_transaction(worker_pool, tenant) as conn:
        assert await worker.claim(conn, tenant, event, holder=stale, lease_seconds=1) == 1
    async with tenant_transaction(worker_pool, tenant) as conn:
        # A held lease is not taken over.
        assert await worker.claim(conn, tenant, event, holder=fresh, lease_seconds=60) is None
    # Wait for the lease to end on the database clock, then let another worker take it over.
    while True:
        async with tenant_transaction(worker_pool, tenant) as conn:
            row = await (
                await conn.execute(
                    "select expires_at < clock_timestamp() from gba.provider_event_leases "
                    "where event_id=%s",
                    (event,),
                )
            ).fetchone()
        if row == (True,):
            break
        await asyncio.sleep(0.05)
    async with tenant_transaction(worker_pool, tenant) as conn:
        assert await worker.claim(conn, tenant, event, holder=fresh, lease_seconds=60) == 2
    for holder, generation in ((stale, 1), (stale, 2), (uuid4(), 2), (fresh, 1)):
        with pytest.raises(psycopg.errors.CheckViolation, match="lease refused"):
            async with tenant_transaction(worker_pool, tenant) as conn:
                await worker.decide(conn, tenant, event, holder=holder, generation=generation)
    async with tenant_transaction(worker_pool, tenant) as conn:
        decision = await worker.decide(conn, tenant, event, holder=fresh, generation=2)
    assert (decision.outcome, decision.generation) == ("observed", 2)


@pytest.mark.parametrize(
    "statement",
    [
        "insert into gba.provider_event_leases (tenant_id,event_id,generation,holder,expires_at) "
        "values (%(tenant)s,%(event)s,1,%(holder)s,now()+interval '11 minutes')",
        "insert into gba.provider_event_leases (tenant_id,event_id,generation,holder,expires_at) "
        "values (%(tenant)s,%(event)s,2,%(holder)s,now()+interval '1 minute')",
        "update gba.provider_event_leases set generation=generation+1,holder=%(holder)s "
        "where event_id=%(event)s",
        "delete from gba.provider_event_leases where event_id=%(event)s",
    ],
)
async def test_leases_change_only_by_a_bounded_claim_or_an_expired_takeover(
    routed: Routed, writer_pool: RuntimePool, worker_pool: RuntimePool, statement: str
) -> None:
    (event,) = await receive_all(writer_pool, routed, stripe("payment_intent.succeeded"))
    tenant = routed.tenant_id
    if not statement.startswith("insert"):
        async with tenant_transaction(worker_pool, tenant) as conn:
            assert await worker.claim(conn, tenant, event, holder=uuid4(), lease_seconds=60) == 1
    params = {"tenant": tenant, "event": event, "holder": uuid4()}
    with pytest.raises((psycopg.errors.CheckViolation, psycopg.errors.InsufficientPrivilege)):
        async with tenant_transaction(worker_pool, tenant) as conn:
            await conn.execute(statement.encode(), params)
    with pytest.raises(ValueError, match="lease"):
        async with tenant_transaction(worker_pool, tenant) as conn:
            await worker.claim(conn, tenant, event, holder=uuid4(), lease_seconds=601)


# W-07 -----------------------------------------------------------------------


def business_counts(database: ProvisionedDatabase) -> dict[str, int]:
    """Every non-receipt table: K2a must not write a journal, settlement or obligation."""
    with psycopg.connect(database.admin_dsn, dbname=database.name) as admin:
        tables = [
            row[0]
            for row in admin.execute(
                "select tablename from pg_catalog.pg_tables where schemaname='gba' "
                "and tablename not like 'provider_%' order by 1"
            ).fetchall()
        ]
        counted: dict[str, int] = {}
        for table in tables:
            row = admin.execute(f"select count(*) from gba.{table}".encode()).fetchone()
            assert row is not None
            counted[table] = int(row[0])
        return counted


async def test_unattested_archive_rows_are_never_processed_and_no_money_moves(
    inbox: archive.Inbox,
    routed: Routed,
    app_pool: RuntimePool,
    writer_pool: RuntimePool,
    worker_pool: RuntimePool,
    test_database: ProvisionedDatabase,
) -> None:
    unattested = (await archive.receive(writer_pool, inbox, inbox.event())).event_id
    (signed_event,) = await receive_all(
        writer_pool, routed, stripe("payment_intent.succeeded", object_id="pi_FAKEpayment9")
    )
    before = business_counts(test_database)
    decided = await worker.process_batch(worker_pool, tenant_id=routed.tenant_id)
    assert [d.event_id for d in decided] == [signed_event]
    assert business_counts(test_database) == before
    with pytest.raises(psycopg.errors.CheckViolation, match="lease refused"):
        async with tenant_transaction(worker_pool, routed.tenant_id) as conn:
            await worker.claim(conn, routed.tenant_id, unattested, holder=uuid4(), lease_seconds=60)
    assert unattested not in await decisions(worker_pool, routed.tenant_id)


# W-08 -----------------------------------------------------------------------


@pytest.mark.parametrize(
    ("statement", "error"),
    [
        ("update gba.provider_event_decisions set reason='success'", "InsufficientPrivilege"),
        ("delete from gba.provider_event_decisions", "InsufficientPrivilege"),
        ("update gba.provider_operations set currency='eur'", "CheckViolation"),
        ("delete from gba.provider_operations", "InsufficientPrivilege"),
        (
            "insert into gba.provider_event_decisions (tenant_id,event_id,generation,holder,"
            "outcome) values (%(tenant)s,%(event)s,1,%(holder)s,'observed')",
            "InsufficientPrivilege",
        ),
        (
            "insert into gba.provider_event_inbox (tenant_id,id) values (%(tenant)s,%(event)s)",
            "InsufficientPrivilege",
        ),
        ("select * from gba.journal_entries", "InsufficientPrivilege"),
        ("select * from gba.provider_receipt_routes", "InsufficientPrivilege"),
    ],
)
async def test_worker_cannot_rewrite_decisions_or_reach_other_tables(
    routed: Routed,
    writer_pool: RuntimePool,
    worker_pool: RuntimePool,
    statement: str,
    error: str,
) -> None:
    (event,) = await receive_all(writer_pool, routed, stripe("payment_intent.succeeded"))
    await worker.process_batch(worker_pool, tenant_id=routed.tenant_id)
    params = {"tenant": routed.tenant_id, "event": event, "holder": uuid4()}
    with pytest.raises(getattr(psycopg.errors, error)):
        async with tenant_transaction(worker_pool, routed.tenant_id) as conn:
            await conn.execute(statement.encode(), params if "%(" in statement else None)


async def test_decisions_and_operations_are_permanent_even_for_owner_and_superuser(
    routed: Routed,
    writer_pool: RuntimePool,
    worker_pool: RuntimePool,
    owner_conn: psycopg.Connection,
    test_database: ProvisionedDatabase,
) -> None:
    await receive_all(writer_pool, routed, stripe("payment_intent.succeeded"))
    await worker.process_batch(worker_pool, tenant_id=routed.tenant_id)
    tenant = routed.tenant_id
    before = (await decisions(worker_pool, tenant), await operations(worker_pool, tenant))
    with psycopg.connect(test_database.admin_dsn, dbname=test_database.name) as superuser:
        for conn in (owner_conn, superuser):
            for statement in (
                "update gba.provider_event_decisions set reason='success'",
                "delete from gba.provider_event_decisions",
                "update gba.provider_operations set currency='eur'",
                "delete from gba.provider_operations",
                *(f"truncate gba.{table} cascade" for table in NEW_TABLES),
            ):
                # Rolled back whatever happens: a missing guard must not change shared rows.
                with conn.transaction(force_rollback=True):
                    conn.execute("select set_config('gba.tenant_id',%s,true)", (str(tenant),))
                    with pytest.raises(psycopg.errors.CheckViolation):
                        conn.execute(statement.encode())
    after = (await decisions(worker_pool, tenant), await operations(worker_pool, tenant))
    assert after == before


@pytest.mark.parametrize("table", NEW_TABLES)
async def test_runtime_and_writer_cannot_read_worker_tables(
    routed: Routed, app_pool: RuntimePool, writer_pool: RuntimePool, table: str
) -> None:
    # K3a (0051): the runtime reads its company's operations and decisions to apply them;
    # leases stay the worker's, and the writer reads none of them.
    readers = (writer_pool,) if table != "provider_event_leases" else (app_pool, writer_pool)
    for pool in readers:
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            async with tenant_transaction(pool, routed.tenant_id) as conn:
                await conn.execute(f"select * from gba.{table}".encode())


async def test_worker_role_is_neither_runtime_nor_writer(worker_pool: RuntimePool) -> None:
    async with worker_pool.connection() as conn:
        await worker.assert_safe_receipt_worker_role(conn)
        with pytest.raises(UnsafeDatabaseRoleError):
            await assert_safe_runtime_role(conn)
        with pytest.raises(UnsafeReceiptWriterRoleError):
            await assert_safe_receipt_writer_role(conn)


async def test_runtime_and_writer_are_not_workers(
    app_pool: RuntimePool, writer_pool: RuntimePool
) -> None:
    for pool in (app_pool, writer_pool):
        with pytest.raises(UnsafeReceiptWorkerRoleError):
            await worker.process_batch(pool)


# W-09 / W-10 ----------------------------------------------------------------

_DECIDE = (
    "create trigger provider_event_decisions_decide before insert on gba.provider_event_decisions "
    "for each row execute function gba.decide_provider_event()"
)
_DRIFT = [
    (
        "runtime-login-in-worker-group",
        ["grant gba_receipt_worker to {app}"],
        ["revoke gba_receipt_worker from {app}"],
    ),
    (
        "worker-login-in-writer-group",
        [f"grant gba_receipt_writer to {WORKER_ROLE}"],
        [f"revoke gba_receipt_writer from {WORKER_ROLE}"],
    ),
    # K3a (0051) gives the runtime decisions and operations; leases stay the worker's.
    (
        "runtime-reads-leases",
        ["grant select on gba.provider_event_leases to gba_runtime"],
        ["revoke select on gba.provider_event_leases from gba_runtime"],
    ),
    (
        "runtime-loses-decisions",
        ["revoke select on gba.provider_event_decisions from gba_runtime"],
        ["grant select on gba.provider_event_decisions to gba_runtime"],
    ),
    (
        "decision-trigger-dropped",
        ["drop trigger provider_event_decisions_decide on gba.provider_event_decisions"],
        [_DECIDE],
    ),
    (
        "lease-trigger-disabled",
        ["alter table gba.provider_event_leases disable trigger provider_event_leases_guard"],
        ["alter table gba.provider_event_leases enable trigger provider_event_leases_guard"],
    ),
]


@pytest.mark.parametrize(("damage", "repair"), [pytest.param(d, r, id=i) for i, d, r in _DRIFT])
async def test_worker_drift_stops_the_worker_the_writer_and_the_runtime_archive(
    inbox: archive.Inbox,
    routed: Routed,
    app_pool: RuntimePool,
    writer_pool: RuntimePool,
    worker_pool: RuntimePool,
    test_database: ProvisionedDatabase,
    damage: list[str],
    repair: list[str],
) -> None:
    app = str(conninfo_to_dict(test_database.app_dsn)["user"])
    with psycopg.connect(
        test_database.admin_dsn, dbname=test_database.name, autocommit=True
    ) as admin:
        try:
            for statement in damage:
                admin.execute(statement.format(app=app).encode())
            with pytest.raises((DatabaseUnavailableError, UnsafeReceiptWorkerRoleError)):
                await worker.process_batch(worker_pool, tenant_id=routed.tenant_id)
            with pytest.raises((DatabaseUnavailableError, UnsafeReceiptWriterRoleError)):
                await attested.receive(writer_pool, routed, stripe("payment_intent.succeeded"))
            with pytest.raises(DatabaseUnavailableError):
                await archive.receive(app_pool, inbox, inbox.event())
        finally:
            for statement in repair:
                admin.execute(statement.format(app=app).encode())
    async with tenant_transaction(app_pool, routed.tenant_id) as conn:
        await assert_provider_receipt_ready(conn)
    (event,) = await receive_all(writer_pool, routed, stripe("payment_intent.succeeded"))
    assert [
        d.event_id for d in await worker.process_batch(worker_pool, tenant_id=routed.tenant_id)
    ] == [event]


async def test_runtime_role_refuses_worker_membership(
    app_pool: RuntimePool, test_database: ProvisionedDatabase
) -> None:
    app = str(conninfo_to_dict(test_database.app_dsn)["user"])
    with psycopg.connect(test_database.admin_dsn, autocommit=True) as admin:
        admin.execute(f"grant gba_receipt_worker to {app}".encode())
        try:
            async with app_pool.connection() as conn:
                with pytest.raises(UnsafeDatabaseRoleError, match="worker"):
                    await assert_safe_runtime_role(conn)
        finally:
            admin.execute(f"revoke gba_receipt_worker from {app}".encode())
