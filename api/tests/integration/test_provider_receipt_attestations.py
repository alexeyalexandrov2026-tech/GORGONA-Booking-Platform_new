"""Synthetic raw signatures through an isolated, routed receipt writer; no provider account."""

import asyncio
import re
import secrets
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid7

import psycopg
import pytest
from psycopg import sql
from psycopg.conninfo import conninfo_to_dict, make_conninfo
from pydantic import SecretStr

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
from gorgona_booking.db.provisioning import owner_tenant_transaction
from gorgona_booking.errors import DatabaseUnavailableError
from gorgona_booking.providers import authenticated_receipts as service
from gorgona_booking.providers.authenticated_receipts import (
    AuthenticatedReceiptResult,
    ReceiptAuthority,
    UnsafeReceiptWriterRoleError,
    assert_safe_receipt_writer_role,
    receive_routed_receipt,
)
from gorgona_booking.providers.inbox import ReceiptBindingRejectedError, ReceiptResult
from gorgona_booking.providers.stripe_contracts import SignedStripeEvent, StripeEventPolicy
from gorgona_booking.providers.stripe_events import ProviderEventRejectedError
from tests.integration import test_provider_event_inbox as shared
from tests.integration.conftest import ProvisionedDatabase
from tests.unit import test_stripe_event_boundary as signed

pytestmark = pytest.mark.anyio
client = shared.client
idp = shared.idp
manager_a = shared.manager_a
manager_b = shared.manager_b
enabled = shared.enabled
inbox = shared.inbox
WRITER_ROLE = "gba_test_receipt_writer"
NOW = datetime.fromtimestamp(signed.NOW, UTC)


@pytest.fixture
async def writer_pool(test_database: ProvisionedDatabase) -> AsyncIterator[RuntimePool]:
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
            receipt_writer_role=WRITER_ROLE,
            receipt_writer_password=password,
        ),
    )
    dsn = make_conninfo(test_database.app_dsn, user=WRITER_ROLE, password=password)
    pool = create_runtime_pool(dsn)
    await pool.open(wait=True)
    try:
        yield pool
    finally:
        await pool.close()


@dataclass(frozen=True)
class Routed:
    """Owner-provisioned route and verification config. The key exists only in memory."""

    tenant_id: UUID
    connection_id: UUID
    book_id: UUID
    ingress_id: UUID
    verification_config_id: UUID
    secret_ref: str
    policy: StripeEventPolicy
    key: SecretStr = field(repr=False)

    @property
    def key_store(self) -> dict[str, SecretStr]:
        return {self.secret_ref: self.key}

    def authority(self) -> ReceiptAuthority:
        return ReceiptAuthority(
            tenant_id=self.tenant_id,
            connection_id=self.connection_id,
            book_id=self.book_id,
            verification_config_id=self.verification_config_id,
            secret_ref=self.secret_ref,
            policy=self.policy,
        )


def fake_key() -> SecretStr:
    return SecretStr("whsec_" + secrets.token_urlsafe(32))


def provision_config(
    owner_conn: psycopg.Connection, tenant_id: UUID, connection_id: UUID, secret_ref: str
) -> tuple[UUID, int]:
    config = uuid7()
    with owner_tenant_transaction(owner_conn, tenant_id):
        owner_conn.execute(
            "insert into gba.provider_verification_configs "
            "(tenant_id,id,connection_id,secret_ref) values (%s,%s,%s,%s)",
            (tenant_id, config, connection_id, secret_ref),
        )
        row = owner_conn.execute(
            "select version from gba.provider_verification_configs where tenant_id=%s and id=%s",
            (tenant_id, config),
        ).fetchone()
    assert row is not None
    return config, row[0]


def provision_route(owner_conn: psycopg.Connection, tenant_id: UUID, connection_id: UUID) -> UUID:
    ingress = uuid7()
    with owner_tenant_transaction(owner_conn, tenant_id):
        owner_conn.execute(
            "insert into gba.provider_receipt_routes (ingress_id,tenant_id,connection_id) "
            "values (%s,%s,%s)",
            (ingress, tenant_id, connection_id),
        )
    return ingress


def provision(
    owner_conn: psycopg.Connection,
    *,
    tenant_id: UUID,
    connection_id: UUID,
    book_id: UUID,
    namespace: str,
    account_id: str = "acct_FAKEreceipt",
) -> Routed:
    reference = "test:k1d-" + uuid7().hex
    config, version = provision_config(owner_conn, tenant_id, connection_id, reference)
    assert version == 1
    return Routed(
        tenant_id=tenant_id,
        connection_id=connection_id,
        book_id=book_id,
        ingress_id=provision_route(owner_conn, tenant_id, connection_id),
        verification_config_id=config,
        secret_ref=reference,
        policy=StripeEventPolicy(
            namespace=namespace, account_id=account_id, api_version="2026-09-30.endive"
        ),
        key=fake_key(),
    )


@pytest.fixture
def routed(inbox: shared.Inbox, owner_conn: psycopg.Connection) -> Routed:
    return provision(
        owner_conn,
        tenant_id=inbox.ledger.business,
        connection_id=inbox.connection,
        book_id=inbox.ledger.book,
        namespace=inbox.namespace,
    )


def delivery(
    kind: str = "payment_intent.succeeded", amount: int = 1000, account: str = "acct_FAKEreceipt"
) -> bytes:
    value = signed.event(kind)
    value["account"] = account
    value["data"]["object"]["amount"] = amount
    if kind.startswith("payment_intent."):
        value["data"]["object"]["amount_received"] = amount
    return signed.body(value)


async def receive(
    pool: RuntimePool, scope: Routed, raw: bytes, *, signing_key: SecretStr | None = None
) -> AuthenticatedReceiptResult:
    return await receive_routed_receipt(
        pool,
        scope.ingress_id,
        raw,
        signed.signed(raw, signing_key or scope.key),
        key_store=scope.key_store,
        now=NOW,
    )


async def attestations(pool: RuntimePool, tenant: UUID) -> list[tuple[object, ...]]:
    async with tenant_transaction(pool, tenant) as conn:
        return await (
            await conn.execute(
                "select event_id,delivery_sha256,connection_id,book_id,verification_config_id,"
                "verifier,verified_by from gba.provider_event_attestations"
            )
        ).fetchall()


@pytest.mark.parametrize("kind", ["payment_intent.succeeded", "charge.succeeded", "refund.updated"])
async def test_raw_signed_receipt_commits_minimal_attestation_and_no_money(
    routed: Routed,
    inbox: shared.Inbox,
    writer_pool: RuntimePool,
    app_pool: RuntimePool,
    kind: str,
) -> None:
    scope = routed
    raw = delivery(kind)
    async with tenant_transaction(app_pool, scope.tenant_id) as conn:
        before = await (await conn.execute("select count(*) from gba.journal_entries")).fetchone()
    result = await receive(writer_pool, scope, raw)
    assert result.authority == "signature_checked_not_admitted"
    assert result.verification_config_id == scope.verification_config_id
    rows = await attestations(app_pool, scope.tenant_id)
    assert len(rows) == 1
    assert rows[0][0] == result.event_id
    assert rows[0][2:] == (
        scope.connection_id,
        scope.book_id,
        scope.verification_config_id,
        "stripe_snapshot_v1",
        WRITER_ROLE,
    )
    assert await shared.counts(app_pool, inbox) == (1, 1)
    async with tenant_transaction(app_pool, scope.tenant_id) as conn:
        stored = await (
            await conn.execute("select row_to_json(a)::text from gba.provider_event_attestations a")
        ).fetchone()
        assert stored is not None
        assert all(
            word not in stored[0]
            for word in ("whsec_", "email", "metadata", "customer", "v1=", scope.secret_ref)
        )
        assert (
            before
            == await (await conn.execute("select count(*) from gba.journal_entries")).fetchone()
        )


async def test_replays_and_signed_conflicts_keep_separate_attested_delivery(
    routed: Routed,
    writer_pool: RuntimePool,
    app_pool: RuntimePool,
) -> None:
    scope = routed
    first = await receive(writer_pool, scope, delivery())
    assert (await receive(writer_pool, scope, delivery())).disposition == "duplicate"
    conflict = await receive(writer_pool, scope, delivery(amount=2000))
    assert conflict.disposition == "conflict"
    assert conflict.event_id == first.event_id
    assert len(await attestations(app_pool, scope.tenant_id)) == 2


async def test_unsigned_archive_cannot_be_promoted_by_ordinary_runtime(
    inbox: shared.Inbox,
    routed: Routed,
    app_pool: RuntimePool,
) -> None:
    result = await shared.receive(app_pool, inbox, inbox.event())
    assert not await attestations(app_pool, inbox.ledger.business)
    with pytest.raises(psycopg.errors.InsufficientPrivilege):
        async with tenant_transaction(app_pool, inbox.ledger.business) as conn:
            await conn.execute(
                "insert into gba.provider_event_attestations (tenant_id,event_id,delivery_sha256,"
                "verification_config_id) values (%s,%s,%s,%s)",
                (inbox.ledger.business, result.event_id, "a" * 64, routed.verification_config_id),
            )
    with pytest.raises(UnsafeReceiptWriterRoleError):
        await receive(app_pool, routed, delivery())
    assert not await attestations(app_pool, inbox.ledger.business)


@pytest.mark.parametrize("role", ["gba_receipt_writer", WRITER_ROLE])
async def test_runtime_cannot_assume_receipt_writer_role(
    writer_pool: RuntimePool,
    app_pool: RuntimePool,
    role: str,
) -> None:
    with pytest.raises(psycopg.errors.InsufficientPrivilege):
        async with app_pool.connection() as conn, conn.transaction():
            await conn.execute(sql.SQL("set role {}").format(sql.Identifier(role)))


@pytest.mark.parametrize(
    "statement",
    [
        "select * from gba.journal_entries",
        "select * from gba.tenants",
        "insert into gba.ledger_books (tenant_id,id) values (null,null)",
        "update gba.provider_event_attestations set verifier='forged'",
        "delete from gba.provider_event_attestations",
    ],
)
async def test_writer_cannot_access_other_business_tables_or_rewrite_history(
    writer_pool: RuntimePool,
    statement: str,
) -> None:
    async with writer_pool.connection() as conn:
        await assert_safe_receipt_writer_role(conn)
    with pytest.raises(psycopg.errors.InsufficientPrivilege):
        async with writer_pool.connection() as conn, conn.transaction():
            await conn.execute(statement.encode())
    async with writer_pool.connection() as conn:
        with pytest.raises(UnsafeDatabaseRoleError):
            await assert_safe_runtime_role(conn)


class _Traced:
    """Delegates to a pooled connection and records each SQL text it is asked to run."""

    def __init__(self, conn: RuntimeConnection, log: list[str]) -> None:
        self._conn = conn
        self._log = log

    def __getattr__(self, name: str) -> Any:
        return getattr(self._conn, name)

    async def execute(self, query: Any, params: Any = None) -> Any:
        self._log.append(str(query))
        return await self._conn.execute(query, params)


@pytest.mark.parametrize("signature", ["wrong-key", "missing"])
async def test_bad_signature_is_refused_after_reading_only_authority_rows(
    inbox: shared.Inbox,
    routed: Routed,
    writer_pool: RuntimePool,
    app_pool: RuntimePool,
    monkeypatch: pytest.MonkeyPatch,
    signature: str,
) -> None:
    statements: list[str] = []
    original = writer_pool.connection

    @asynccontextmanager
    async def traced() -> AsyncIterator[Any]:
        async with original() as conn:
            yield _Traced(conn, statements)

    monkeypatch.setattr(writer_pool, "connection", traced)
    raw = delivery()
    header = signed.signed(raw, fake_key()) if signature == "wrong-key" else None
    with pytest.raises(ProviderEventRejectedError):
        await receive_routed_receipt(
            writer_pool, routed.ingress_id, raw, header, key_store=routed.key_store, now=NOW
        )
    touched = {
        table
        for statement in statements
        for table in re.findall(r"\b(?:from|join|into|update)\s+gba\.(\w+)", statement, re.I)
    }
    assert touched == {
        "provider_receipt_routes",
        "provider_verification_configs",
        "provider_receipt_connections",
    }
    monkeypatch.undo()
    assert await shared.counts(app_pool, inbox) == (0, 0)
    assert not await attestations(app_pool, inbox.ledger.business)


async def test_receiver_refuses_a_borrowed_connection_with_an_outer_transaction(
    routed: Routed,
    writer_pool: RuntimePool,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async with writer_pool.connection() as conn, conn.transaction():

        @asynccontextmanager
        async def already_borrowed() -> AsyncIterator[RuntimeConnection]:
            yield conn

        monkeypatch.setattr(writer_pool, "connection", already_borrowed)
        with pytest.raises(ReceiptBindingRejectedError):
            await receive(writer_pool, routed, delivery())


@pytest.mark.parametrize("scope_kind", ["foreign", "branch", "unscoped"])
async def test_attestation_reads_remain_tenant_and_company_scoped(
    inbox: shared.Inbox,
    routed: Routed,
    writer_pool: RuntimePool,
    app_pool: RuntimePool,
    scope_kind: str,
) -> None:
    await receive(writer_pool, routed, delivery())
    async with app_pool.connection() as conn, conn.transaction():
        if scope_kind != "unscoped":
            await set_tenant_context(
                conn, uuid7() if scope_kind == "foreign" else inbox.ledger.business
            )
        if scope_kind == "branch":
            await conn.execute("select set_config('gba.location_id',%s,true)", (str(uuid7()),))
        assert not await (
            await conn.execute("select * from gba.provider_event_attestations")
        ).fetchall()


async def test_revocation_refuses_next_receipt_but_keeps_authenticated_history(
    inbox: shared.Inbox,
    routed: Routed,
    writer_pool: RuntimePool,
    app_pool: RuntimePool,
) -> None:
    scope = routed
    await receive(writer_pool, scope, delivery())
    async with tenant_transaction(app_pool, scope.tenant_id) as conn:
        await conn.execute(
            "update gba.provider_receipt_connections set revoked=true, "
            "revoked_reason='retired' where id=%s",
            (scope.connection_id,),
        )
    with pytest.raises(ReceiptBindingRejectedError):
        await receive(writer_pool, scope, delivery() + b"\n")
    assert len(await attestations(app_pool, scope.tenant_id)) == 1
    assert await shared.counts(app_pool, inbox) == (1, 1)


@pytest.mark.parametrize("poison", [False, True])
async def test_only_a_new_verified_delivery_can_attest_a_preexisting_untrusted_archive(
    inbox: shared.Inbox,
    routed: Routed,
    writer_pool: RuntimePool,
    app_pool: RuntimePool,
    poison: bool,
) -> None:
    scope = routed
    raw = delivery()
    event = signed.decode(raw, signed.signed(raw, scope.key), scope.policy, (scope.key,))
    untrusted = event
    if poison:
        untrusted = event.model_copy(
            update={
                "resource": event.resource.model_copy(update={"amount_minor": 2000}),
                "delivery_sha256": "f" * 64,
            }
        )
    first = await shared.receive(app_pool, inbox, untrusted)
    assert not await attestations(app_pool, scope.tenant_id)
    checked = await receive(writer_pool, scope, raw)
    assert checked.event_id == first.event_id
    assert checked.disposition == ("conflict" if poison else "duplicate")
    async with tenant_transaction(app_pool, scope.tenant_id) as conn:
        rows = await (
            await conn.execute(
                "select d.facts->'resource'->>'amount_minor',d.matches_original "
                "from gba.provider_event_attestations a join gba.provider_event_deliveries d "
                "using (tenant_id,event_id,delivery_sha256)"
            )
        ).fetchall()
        assert rows == [("1000", not poison)]


@pytest.mark.parametrize("rollback", [False, True])
async def test_attestation_duplicate_waits_on_observed_insert_then_survives_leader_outcome(
    inbox: shared.Inbox,
    routed: Routed,
    writer_pool: RuntimePool,
    app_pool: RuntimePool,
    test_database: ProvisionedDatabase,
    rollback: bool,
) -> None:
    scope = routed
    raw = delivery()
    event = signed.decode(raw, signed.signed(raw, scope.key), scope.policy, (scope.key,))
    archived = await shared.receive(app_pool, inbox, event)
    follower = None
    monitor = await psycopg.AsyncConnection.connect(
        test_database.admin_dsn,
        dbname=test_database.name,
        autocommit=True,
    )
    try:
        async with writer_pool.connection() as leader, leader.transaction(force_rollback=rollback):
            await set_tenant_context(leader, scope.tenant_id)
            await service._attest_event(leader, scope.authority(), event, archived)
            identity = await (
                await leader.execute("select pg_backend_pid(),pg_current_xact_id()::text")
            ).fetchone()
            assert identity is not None
            follower = asyncio.create_task(receive(writer_pool, scope, raw))
            deadline = asyncio.get_running_loop().time() + 8
            while asyncio.get_running_loop().time() < deadline:
                waiting = await (
                    await monitor.execute(
                        "select l.pid from pg_catalog.pg_locks l "
                        "join pg_catalog.pg_stat_activity a on a.pid=l.pid "
                        "where not l.granted and l.locktype='transactionid' "
                        "and l.transactionid::text=%s and %s=any(pg_blocking_pids(l.pid)) "
                        "and a.datname=current_database() "
                        "and a.query like 'insert into gba.provider_event_attestations%%'",
                        (identity[1], identity[0]),
                    )
                ).fetchone()
                if waiting is not None:
                    break
                await asyncio.sleep(0.01)
            else:
                pytest.fail("Attestation follower must wait on its INSERT in pg_locks")
            assert not follower.done()
        result = await asyncio.wait_for(follower, 15)
        assert result.event_id == archived.event_id
        assert len(await attestations(app_pool, scope.tenant_id)) == 1
    finally:
        if follower is not None:
            if not follower.done():
                follower.cancel()
            await asyncio.gather(follower, return_exceptions=True)
        await monitor.close()


async def test_commit_failure_rolls_back_archive_and_attestation_before_return(
    inbox: shared.Inbox,
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
    with pytest.raises(psycopg.errors.CheckViolation):
        await receive(writer_pool, routed, delivery())
    assert await shared.counts(app_pool, inbox) == (0, 0)
    assert not await attestations(app_pool, inbox.ledger.business)


async def test_writer_with_financial_privilege_drift_is_refused(
    inbox: shared.Inbox,
    routed: Routed,
    writer_pool: RuntimePool,
    app_pool: RuntimePool,
    owner_conn: psycopg.Connection,
) -> None:
    owner_conn.execute("grant select on gba.journal_entries to gba_receipt_writer")
    try:
        with pytest.raises(UnsafeReceiptWriterRoleError):
            await receive(writer_pool, routed, delivery())
    finally:
        owner_conn.execute("revoke select on gba.journal_entries from gba_receipt_writer")
    assert await shared.counts(app_pool, inbox) == (0, 0)


async def test_schema_damage_is_refused_before_authenticating_receipt(
    inbox: shared.Inbox,
    routed: Routed,
    writer_pool: RuntimePool,
    app_pool: RuntimePool,
    owner_conn: psycopg.Connection,
) -> None:
    owner_conn.execute(
        "alter table gba.provider_event_attestations "
        "disable trigger provider_event_attestations_check"
    )
    try:
        with pytest.raises(DatabaseUnavailableError):
            await receive(writer_pool, routed, delivery())
    finally:
        owner_conn.execute(
            "alter table gba.provider_event_attestations "
            "enable trigger provider_event_attestations_check"
        )
    assert await shared.counts(app_pool, inbox) == (0, 0)


async def test_mixed_runtime_login_cannot_hide_behind_set_role_to_attest(
    inbox: shared.Inbox,
    routed: Routed,
    writer_pool: RuntimePool,
    app_pool: RuntimePool,
    test_database: ProvisionedDatabase,
) -> None:
    scope = routed
    archived = await shared.receive(app_pool, inbox, inbox.event())
    app_role = str(conninfo_to_dict(test_database.app_dsn)["user"])
    async with await psycopg.AsyncConnection.connect(
        test_database.admin_dsn, autocommit=True
    ) as admin:
        await admin.execute(
            sql.SQL("grant gba_receipt_writer to {} with inherit false").format(
                sql.Identifier(app_role)
            )
        )
        try:
            async with app_pool.connection() as conn:
                with pytest.raises(UnsafeDatabaseRoleError):
                    await assert_safe_runtime_role(conn)
            async with app_pool.connection() as conn, conn.transaction(force_rollback=True):
                await set_tenant_context(conn, scope.tenant_id)
                await conn.execute("set local role gba_receipt_writer")
                with pytest.raises(psycopg.errors.CheckViolation):
                    await service._attest_event(conn, scope.authority(), inbox.event(), archived)
        finally:
            await admin.execute(
                sql.SQL("revoke gba_receipt_writer from {}").format(sql.Identifier(app_role))
            )


async def test_noninherited_dangerous_parent_role_is_also_refused(
    routed: Routed,
    writer_pool: RuntimePool,
    test_database: ProvisionedDatabase,
) -> None:
    async with await psycopg.AsyncConnection.connect(
        test_database.admin_dsn, autocommit=True
    ) as admin:
        await admin.execute("create role gba_test_dangerous_parent nologin createrole")
        await admin.execute(
            sql.SQL("grant gba_test_dangerous_parent to {} with inherit false").format(
                sql.Identifier(WRITER_ROLE)
            )
        )
        try:
            with pytest.raises(UnsafeReceiptWriterRoleError):
                await receive(writer_pool, routed, delivery())
        finally:
            await admin.execute(
                sql.SQL("revoke gba_test_dangerous_parent from {}").format(
                    sql.Identifier(WRITER_ROLE)
                )
            )
            await admin.execute("drop role gba_test_dangerous_parent")
