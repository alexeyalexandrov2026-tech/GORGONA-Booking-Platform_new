"""Synthetic receipt storage only: no provider admission, HTTP or money effect."""

import asyncio
import copy
import secrets
from dataclasses import dataclass
from uuid import UUID, uuid7

import psycopg
import pytest
from psycopg import sql
from psycopg.types.json import Jsonb
from pydantic import SecretStr

from gorgona_booking.db.pool import RuntimePool, set_tenant_context, tenant_transaction
from gorgona_booking.db.provider_receipt_guard import assert_provider_receipt_ready
from gorgona_booking.db.provisioning import owner_tenant_transaction
from gorgona_booking.errors import DatabaseUnavailableError
from gorgona_booking.providers.inbox import (
    ReceiptBindingRejectedError,
    ReceiptResult,
    record_event,
)
from gorgona_booking.providers.stripe_contracts import (
    SignedStripeEvent,
    StripeEventPolicy,
    StripePaymentIntent,
)
from tests.integration import test_ledger as shared
from tests.integration.conftest import ProvisionedDatabase
from tests.integration.test_ledger import LedgerWorld
from tests.unit import test_stripe_event_boundary as signed_fixtures

pytestmark = pytest.mark.anyio
client = shared.client
idp = shared.idp
manager_a = shared.manager_a
manager_b = shared.manager_b
enabled = shared.enabled


@dataclass(frozen=True)
class Inbox:
    ledger: LedgerWorld
    connection: UUID
    namespace: str

    def event(self, *, amount: int = 1000, delivery: str = "a") -> SignedStripeEvent:
        return SignedStripeEvent(
            namespace=self.namespace,
            account_id="acct_FAKEreceipt",
            api_version="2026-09-30.endive",
            event_id="evt_FAKEreceipt",
            event_type="payment_intent.succeeded",
            created=1_792_000_000,
            resource=StripePaymentIntent(
                id="pi_FAKEreceipt",
                amount_minor=amount,
                amount_received_minor=amount,
                currency="usd",
                status="succeeded",
            ),
            delivery_sha256=delivery * 64,
        )


@pytest.fixture
def inbox(enabled: LedgerWorld, owner_conn: psycopg.Connection) -> Inbox:
    binding = Inbox(enabled, uuid7(), "FAKE-receipts-" + uuid7().hex)
    with owner_tenant_transaction(owner_conn, enabled.business):
        owner_conn.execute(
            "insert into gba.provider_receipt_connections "
            "(tenant_id,id,book_id,namespace,account_id,api_version) values (%s,%s,%s,%s,%s,%s)",
            (
                enabled.business,
                binding.connection,
                enabled.book,
                binding.namespace,
                "acct_FAKEreceipt",
                "2026-09-30.endive",
            ),
        )
    return binding


async def receive(pool: RuntimePool, fixture: Inbox, event: SignedStripeEvent) -> ReceiptResult:
    async with tenant_transaction(pool, fixture.ledger.business) as conn:
        return await record_event(conn, fixture.connection, event)


async def counts(pool: RuntimePool, fixture: Inbox) -> tuple[int, int]:
    async with tenant_transaction(pool, fixture.ledger.business) as conn:
        row = await (
            await conn.execute(
                "select (select count(*) from gba.provider_event_inbox),"
                "(select count(*) from gba.provider_event_deliveries)"
            )
        ).fetchone()
        assert row is not None
        return row[0], row[1]


async def test_receipt_replay_and_transport_difference_keep_one_identity(
    inbox: Inbox, app_pool: RuntimePool
) -> None:
    first = await receive(app_pool, inbox, inbox.event())
    assert first.disposition == "recorded"
    assert first.authority == "receipt_only_not_admitted"
    assert (await receive(app_pool, inbox, inbox.event())).disposition == "duplicate"
    other_bytes = await receive(app_pool, inbox, inbox.event(delivery="b"))
    assert other_bytes.disposition == "duplicate"
    assert other_bytes.event_id == first.event_id
    assert await counts(app_pool, inbox) == (1, 2)


async def test_conflicting_facts_are_retained_without_rewriting_first_event(
    inbox: Inbox, app_pool: RuntimePool
) -> None:
    await receive(app_pool, inbox, inbox.event())
    changed = inbox.event(amount=2000, delivery="b")
    assert (await receive(app_pool, inbox, changed)).disposition == "conflict"
    assert (await receive(app_pool, inbox, changed)).disposition == "conflict"
    async with tenant_transaction(app_pool, inbox.ledger.business) as conn:
        rows = await (
            await conn.execute(
                "select facts->'resource'->>'amount_minor' from gba.provider_event_inbox"
            )
        ).fetchall()
        assert rows == [("1000",)]
        rows = await (
            await conn.execute("select matches_original from gba.provider_event_deliveries")
        ).fetchall()
        assert sorted(rows) == [(False,), (True,)]
    assert await counts(app_pool, inbox) == (1, 2)


async def test_same_delivery_digest_cannot_be_reused_for_different_facts(
    inbox: Inbox, app_pool: RuntimePool
) -> None:
    await receive(app_pool, inbox, inbox.event())
    with pytest.raises(ReceiptBindingRejectedError):
        await receive(app_pool, inbox, inbox.event(amount=2000))
    assert await counts(app_pool, inbox) == (1, 1)


async def test_rollback_before_commit_has_no_receipt_and_replay_can_commit(
    inbox: Inbox, app_pool: RuntimePool
) -> None:
    with pytest.raises(RuntimeError, match="synthetic crash"):  # noqa: PT012 - rollback at exit
        async with tenant_transaction(app_pool, inbox.ledger.business) as conn:
            await record_event(conn, inbox.connection, inbox.event())
            raise RuntimeError("synthetic crash before acknowledgement")
    assert await counts(app_pool, inbox) == (0, 0)
    assert (await receive(app_pool, inbox, inbox.event())).disposition == "recorded"


@pytest.mark.parametrize("kind", ["payment_intent.succeeded", "charge.succeeded", "refund.updated"])
async def test_signed_snapshots_reach_storage_without_customer_data_or_journals(
    inbox: Inbox, app_pool: RuntimePool, kind: str
) -> None:
    payload = signed_fixtures.event(kind)
    payload["account"] = "acct_FAKEreceipt"
    raw = signed_fixtures.body(payload)
    key = SecretStr("whsec_" + secrets.token_urlsafe(32))
    event = signed_fixtures.decode(
        raw,
        signed_fixtures.signed(raw, key),
        StripeEventPolicy(
            namespace=inbox.namespace,
            account_id="acct_FAKEreceipt",
            api_version="2026-09-30.endive",
        ),
        (key,),
    )
    async with tenant_transaction(app_pool, inbox.ledger.business) as conn:
        before = await (await conn.execute("select count(*) from gba.journal_entries")).fetchone()
        result = await record_event(conn, inbox.connection, event)
        assert result.disposition == "recorded"
        stored = await (
            await conn.execute("select facts::text from gba.provider_event_inbox")
        ).fetchone()
        assert stored is not None
        assert all(
            private not in stored[0]
            for private in ("metadata", "customer", "email", "FAKE private")
        )
        assert (
            before
            == await (await conn.execute("select count(*) from gba.journal_entries")).fetchone()
        )


async def test_revocation_waits_for_inflight_receipt_then_blocks_next_delivery(
    inbox: Inbox, app_pool: RuntimePool, test_database: ProvisionedDatabase
) -> None:
    async def revoke() -> None:
        async with tenant_transaction(app_pool, inbox.ledger.business) as conn:
            await conn.execute(
                "update gba.provider_receipt_connections set revoked=true, "
                "revoked_reason='retired' where id=%s",
                (inbox.connection,),
            )

    follower = None
    monitor = await psycopg.AsyncConnection.connect(
        test_database.admin_dsn, dbname=test_database.name, autocommit=True
    )
    try:
        async with tenant_transaction(app_pool, inbox.ledger.business) as leader:
            await record_event(leader, inbox.connection, inbox.event())
            identity = await (
                await leader.execute("select pg_backend_pid(),pg_current_xact_id()::text")
            ).fetchone()
            assert identity is not None
            follower = asyncio.create_task(revoke())
            deadline = asyncio.get_running_loop().time() + 8
            while asyncio.get_running_loop().time() < deadline:
                row = await (
                    await monitor.execute(
                        "select l.pid from pg_catalog.pg_locks l "
                        "join pg_catalog.pg_stat_activity a on a.pid=l.pid "
                        "where not l.granted and l.locktype='transactionid' "
                        "and l.transactionid::text=%s and %s=any(pg_blocking_pids(l.pid)) "
                        "and a.datname=current_database() "
                        "and a.query like 'update gba.provider_receipt_connections%%'",
                        (identity[1], identity[0]),
                    )
                ).fetchone()
                if row is not None:
                    break
                await asyncio.sleep(0.01)
            else:
                pytest.fail("Revocation must wait on the receipt's connection lock in pg_locks")
            assert not follower.done()
        await asyncio.wait_for(follower, 15)
    finally:
        if follower is not None:
            if not follower.done():
                follower.cancel()
            await asyncio.gather(follower, return_exceptions=True)
        await monitor.close()
    with pytest.raises(ReceiptBindingRejectedError):
        await receive(app_pool, inbox, inbox.event(delivery="b"))
    assert await counts(app_pool, inbox) == (1, 1)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("namespace", "FAKE-other"),
        ("account_id", "acct_FAKEother"),
        ("api_version", "2026-08-01.fake"),
    ],
)
async def test_connection_scope_mismatch_never_records(
    inbox: Inbox, app_pool: RuntimePool, field: str, value: str
) -> None:
    body = inbox.event().model_dump(mode="json")
    body[field] = value
    with pytest.raises(ReceiptBindingRejectedError):
        await receive(app_pool, inbox, SignedStripeEvent.model_validate(body))
    assert await counts(app_pool, inbox) == (0, 0)


async def test_revocation_is_permanent_and_history_is_preserved(
    inbox: Inbox, app_pool: RuntimePool
) -> None:
    await receive(app_pool, inbox, inbox.event())
    async with tenant_transaction(app_pool, inbox.ledger.business) as conn:
        await conn.execute(
            "update gba.provider_receipt_connections set revoked=true, "
            "revoked_reason='retired' where id=%s",
            (inbox.connection,),
        )
    with pytest.raises(ReceiptBindingRejectedError):
        await receive(app_pool, inbox, inbox.event(delivery="b"))
    with pytest.raises(psycopg.errors.CheckViolation):
        async with tenant_transaction(app_pool, inbox.ledger.business) as conn:
            await conn.execute(
                "update gba.provider_receipt_connections set revoked=false where id=%s",
                (inbox.connection,),
            )
    assert await counts(app_pool, inbox) == (1, 1)


@pytest.mark.parametrize("scope", ["unscoped", "foreign", "branch"])
async def test_tenant_and_company_scope_fail_closed(
    inbox: Inbox, app_pool: RuntimePool, scope: str
) -> None:
    await receive(app_pool, inbox, inbox.event())
    async with app_pool.connection() as conn, conn.transaction():
        if scope != "unscoped":
            tenant = uuid7() if scope == "foreign" else inbox.ledger.business
            await conn.execute("select set_config('gba.tenant_id',%s,true)", (str(tenant),))
        if scope == "branch":
            await conn.execute("select set_config('gba.location_id',%s,true)", (str(uuid7()),))
        assert await (await conn.execute("select * from gba.provider_event_inbox")).fetchall() == []
        with pytest.raises(ReceiptBindingRejectedError):
            await record_event(conn, inbox.connection, inbox.event())


@pytest.mark.parametrize("table", ["provider_event_inbox", "provider_event_deliveries"])
@pytest.mark.parametrize("operation", ["update", "delete", "truncate"])
async def test_runtime_cannot_mutate_receipt_history(
    inbox: Inbox, app_pool: RuntimePool, table: str, operation: str
) -> None:
    await receive(app_pool, inbox, inbox.event())
    statement = (
        sql.SQL("update gba.{} set facts=facts").format(sql.Identifier(table))
        if operation == "update"
        else sql.SQL(operation + " {} gba.{}").format(
            sql.SQL("from" if operation == "delete" else "table"), sql.Identifier(table)
        )
    )
    with pytest.raises(psycopg.errors.InsufficientPrivilege):
        async with tenant_transaction(app_pool, inbox.ledger.business) as conn:
            await conn.execute(statement)


async def test_runtime_cannot_provision_a_connection_or_grant_admission(
    inbox: Inbox, app_pool: RuntimePool
) -> None:
    with pytest.raises(psycopg.errors.InsufficientPrivilege):
        async with tenant_transaction(app_pool, inbox.ledger.business) as conn:
            await conn.execute(
                "insert into gba.provider_receipt_connections "
                "(tenant_id,id,book_id,namespace,account_id,api_version) "
                "values (%s,%s,%s,'FAKE-forged','acct_FAKE','2026-09-30.endive')",
                (inbox.ledger.business, uuid7(), inbox.ledger.book),
            )


@pytest.mark.parametrize("tamper", ["extra", "mode", "amount", "event_type", "null", "string"])
async def test_direct_sql_rejects_untyped_or_private_facts(
    inbox: Inbox, app_pool: RuntimePool, tamper: str
) -> None:
    facts = inbox.event().model_dump(mode="json", exclude={"delivery_sha256"})
    facts = copy.deepcopy(facts)
    if tamper == "extra":
        facts["resource"]["customer_email"] = "fake@example.test"
    elif tamper == "mode":
        facts["livemode"] = True
    elif tamper == "amount":
        facts["resource"]["amount_minor"] = -1
    elif tamper == "event_type":
        facts["event_type"] = "refund.created"
    elif tamper == "null":
        facts["resource"]["currency"] = None
    else:
        facts["resource"]["amount_minor"] = "1000"
    with pytest.raises(psycopg.errors.CheckViolation):
        async with tenant_transaction(app_pool, inbox.ledger.business) as conn:
            await conn.execute(
                "insert into gba.provider_event_inbox (tenant_id,id,connection_id,facts) "
                "values (%s,%s,%s,%s)",
                (inbox.ledger.business, uuid7(), inbox.connection, Jsonb(facts)),
            )


@pytest.mark.parametrize("rollback", [False, True])
async def test_duplicate_writers_wait_on_the_uncommitted_event_insert(
    inbox: Inbox, app_pool: RuntimePool, test_database: ProvisionedDatabase, rollback: bool
) -> None:
    follower = None
    monitor = await psycopg.AsyncConnection.connect(
        test_database.admin_dsn, dbname=test_database.name, autocommit=True
    )
    try:
        async with app_pool.connection() as leader, leader.transaction(force_rollback=rollback):
            await set_tenant_context(leader, inbox.ledger.business)
            identity = await (
                await leader.execute("select pg_backend_pid(),pg_current_xact_id()::text")
            ).fetchone()
            assert identity is not None
            original = await record_event(leader, inbox.connection, inbox.event())
            follower = asyncio.create_task(receive(app_pool, inbox, inbox.event(delivery="b")))
            deadline = asyncio.get_running_loop().time() + 8
            while asyncio.get_running_loop().time() < deadline:
                waiting = await (
                    await monitor.execute(
                        "select l.pid from pg_catalog.pg_locks l "
                        "join pg_catalog.pg_stat_activity a on a.pid=l.pid "
                        "where not l.granted and l.locktype='transactionid' "
                        "and l.transactionid::text=%s and %s=any(pg_blocking_pids(l.pid)) "
                        "and a.datname=current_database() "
                        "and a.query like 'insert into gba.provider_event_inbox%%'",
                        (identity[1], identity[0]),
                    )
                ).fetchone()
                if waiting is not None:
                    break
                await asyncio.sleep(0.01)
            else:
                pytest.fail("Follower must wait on the inbox insert in pg_locks")
            assert not follower.done()
        replay = await asyncio.wait_for(follower, 15)
        assert replay.disposition == ("recorded" if rollback else "duplicate")
        assert (replay.event_id == original.event_id) is not rollback
        assert await counts(app_pool, inbox) == (1, 1 if rollback else 2)
    finally:
        if follower is not None:
            if not follower.done():
                follower.cancel()
            await asyncio.gather(follower, return_exceptions=True)
        await monitor.close()


@pytest.mark.parametrize(
    ("damage", "repair"),
    [
        (
            "alter table gba.provider_event_inbox disable trigger provider_event_inbox_check",
            "alter table gba.provider_event_inbox enable trigger provider_event_inbox_check",
        ),
        (
            "alter table gba.provider_event_inbox alter column facts drop not null",
            "alter table gba.provider_event_inbox alter column facts set not null",
        ),
        (
            "alter table gba.provider_event_inbox alter column received_at "
            "set default '2000-01-01'::timestamptz",
            "alter table gba.provider_event_inbox alter column received_at set default now()",
        ),
        (
            "grant update(facts) on gba.provider_event_inbox to gba_runtime",
            "revoke update(facts) on gba.provider_event_inbox from gba_runtime",
        ),
        (
            "alter policy provider_event_inbox_tenant on gba.provider_event_inbox "
            "using (true) with check (true)",
            "alter policy provider_event_inbox_tenant on gba.provider_event_inbox "
            "using (tenant_id=gba.current_tenant_id()) "
            "with check (tenant_id=gba.current_tenant_id())",
        ),
    ],
)
async def test_schema_damage_refuses_receipt(
    inbox: Inbox, app_pool: RuntimePool, owner_conn: psycopg.Connection, damage: str, repair: str
) -> None:
    async with tenant_transaction(app_pool, inbox.ledger.business) as conn:
        await assert_provider_receipt_ready(conn)
    owner_conn.execute(damage)
    try:
        with pytest.raises(DatabaseUnavailableError):
            await receive(app_pool, inbox, inbox.event())
    finally:
        owner_conn.execute(repair)


@pytest.mark.parametrize("switch", ["company", "branch"])
async def test_orphan_event_cannot_hide_from_deferred_check_by_switching_scope(
    inbox: Inbox, app_pool: RuntimePool, switch: str
) -> None:
    with pytest.raises(psycopg.errors.CheckViolation):  # noqa: PT012 - deferred check at exit
        async with tenant_transaction(app_pool, inbox.ledger.business) as conn:
            await conn.execute(
                "insert into gba.provider_event_inbox (tenant_id,id,connection_id,facts) "
                "values (%s,%s,%s,%s)",
                (
                    inbox.ledger.business,
                    uuid7(),
                    inbox.connection,
                    Jsonb(inbox.event().model_dump(mode="json", exclude={"delivery_sha256"})),
                ),
            )
            setting = "gba.tenant_id" if switch == "company" else "gba.location_id"
            await conn.execute("select set_config(%s,%s,true)", (setting, str(uuid7())))
    assert await counts(app_pool, inbox) == (0, 0)


async def test_missing_connection_does_not_write(inbox: Inbox, app_pool: RuntimePool) -> None:
    async with tenant_transaction(app_pool, inbox.ledger.business) as conn:
        with pytest.raises(ReceiptBindingRejectedError):
            await record_event(conn, uuid7(), inbox.event())
    assert await counts(app_pool, inbox) == (0, 0)


async def test_receipt_requires_explicit_read_committed_transaction(
    inbox: Inbox, app_pool: RuntimePool
) -> None:
    async with app_pool.connection() as conn:
        with pytest.raises(ReceiptBindingRejectedError):
            await record_event(conn, inbox.connection, inbox.event())
    async with app_pool.connection() as conn, conn.transaction():
        await conn.execute("set transaction isolation level repeatable read")
        await conn.execute(
            "select set_config('gba.tenant_id',%s,true)", (str(inbox.ledger.business),)
        )
        with pytest.raises(ReceiptBindingRejectedError):
            await record_event(conn, inbox.connection, inbox.event())
    assert await counts(app_pool, inbox) == (0, 0)
