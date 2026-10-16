"""K1d: owner-provisioned verification authority and writer-only routing; synthetic only.

No provider account, real key, HTTP route, worker or money. Keys are generated in memory.
"""

import asyncio
from datetime import date
from uuid import UUID, uuid7

import httpx
import psycopg
import pytest
from psycopg.conninfo import conninfo_to_dict

from gorgona_booking.business import ledger
from gorgona_booking.business.ledger_contracts import BookInput
from gorgona_booking.db.pool import (
    RuntimeConnection,
    RuntimePool,
    tenant_transaction,
    unscoped_transaction,
)
from gorgona_booking.db.provider_receipt_guard import assert_provider_receipt_ready
from gorgona_booking.db.provisioning import owner_tenant_transaction
from gorgona_booking.errors import DatabaseUnavailableError
from gorgona_booking.providers import authenticated_receipts as service
from gorgona_booking.providers.authenticated_receipts import receive_routed_receipt
from gorgona_booking.providers.inbox import (
    ReceiptBindingRejectedError,
    ReceiptResult,
    record_event,
)
from gorgona_booking.providers.stripe_contracts import SignedStripeEvent
from gorgona_booking.providers.stripe_events import ProviderEventRejectedError
from tests.integration import test_provider_event_inbox as archive
from tests.integration import test_provider_receipt_attestations as attested
from tests.integration.booking_support import BookingWorld
from tests.integration.configuration_support import Config
from tests.integration.conftest import ProvisionedDatabase
from tests.integration.seed import FakeUser
from tests.support.fake_idp import FakeIdp
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


@pytest.fixture
async def other(
    client: httpx.AsyncClient,
    world: BookingWorld,
    manager_b: FakeUser,
    idp: FakeIdp,
    app_pool: RuntimePool,
    owner_conn: psycopg.Connection,
) -> Routed:
    """Company B with its own book, connection, verification config and route."""
    business = world.b.tenant_id
    config = Config(client, idp)
    await config.profile(manager_b, business, 0, [1])
    await config.publish(manager_b, business, 0, ["booking_resources", "finance"])
    entity = uuid7()
    response = await client.put(
        f"/v1/businesses/{business}/legal-entities/{entity}",
        json={"expected_revision": 0, "code": "FAKEB", "legal_name": "FAKE Other LLC"},
        headers=config.headers(manager_b),
    )
    assert response.status_code == 200, response.text
    book = uuid7()
    async with tenant_transaction(app_pool, business) as conn:
        await ledger.save_book(
            conn,
            business_id=business,
            book_id=book,
            user_id=manager_b.user_id,
            actor=f"user:{manager_b.user_id}",
            key=str(uuid7()),
            body=BookInput(
                expected_revision=0,
                legal_entity_id=entity,
                base_currency="USD",
                fiscal_year_start_month=1,
                accounting_start=date(2026, 1, 1),
            ),
        )
    connection = uuid7()
    namespace = "FAKE-receipts-" + uuid7().hex
    with owner_tenant_transaction(owner_conn, business):
        owner_conn.execute(
            "insert into gba.provider_receipt_connections "
            "(tenant_id,id,book_id,namespace,account_id,api_version) "
            "values (%s,%s,%s,%s,'acct_FAKEother','2026-09-30.endive')",
            (business, connection, book, namespace),
        )
    return attested.provision(
        owner_conn,
        tenant_id=business,
        connection_id=connection,
        book_id=book,
        namespace=namespace,
        account_id="acct_FAKEother",
    )


async def stored(pool: RuntimePool, tenant: UUID) -> tuple[int, int, int]:
    async with tenant_transaction(pool, tenant) as conn:
        row = await (
            await conn.execute(
                "select (select count(*) from gba.provider_event_inbox),"
                "(select count(*) from gba.provider_event_deliveries),"
                "(select count(*) from gba.provider_event_attestations)"
            )
        ).fetchone()
    assert row is not None
    return row[0], row[1], row[2]


_REVOKE = {
    "provider_verification_configs": (
        "update gba.provider_verification_configs set revoked=true where id=%s"
    ),
    "provider_receipt_connections": (
        "update gba.provider_receipt_connections set revoked=true where id=%s"
    ),
}


async def revoke(pool: RuntimePool, scope: Routed, table: str, row: UUID) -> None:
    async with tenant_transaction(pool, scope.tenant_id) as conn:
        await conn.execute(_REVOKE[table], (row,))


def second_connection(owner_conn: psycopg.Connection, scope: Routed) -> UUID:
    connection = uuid7()
    with owner_tenant_transaction(owner_conn, scope.tenant_id):
        owner_conn.execute(
            "insert into gba.provider_receipt_connections "
            "(tenant_id,id,book_id,namespace,account_id,api_version) "
            "values (%s,%s,%s,%s,'acct_FAKEsecond','2026-09-30.endive')",
            (scope.tenant_id, connection, scope.book_id, "FAKE-receipts-" + uuid7().hex),
        )
    return connection


# D-02 -----------------------------------------------------------------------


@pytest.mark.parametrize(
    "case", ["unknown_ingress", "missing_key", "revoked_config", "revoked_connection"]
)
async def test_routing_and_authority_refusals_store_nothing(
    routed: Routed,
    writer_pool: RuntimePool,
    app_pool: RuntimePool,
    case: str,
) -> None:
    ingress, store = routed.ingress_id, routed.key_store
    if case == "unknown_ingress":
        ingress = uuid7()
    elif case == "missing_key":
        store = {"test:k1d-elsewhere": routed.key}
    elif case == "revoked_config":
        await revoke(
            app_pool, routed, "provider_verification_configs", routed.verification_config_id
        )
    else:
        await revoke(app_pool, routed, "provider_receipt_connections", routed.connection_id)
    raw = attested.delivery()
    with pytest.raises(ReceiptBindingRejectedError) as refused:
        await receive_routed_receipt(
            writer_pool,
            ingress,
            raw,
            signed.signed(raw, routed.key),
            key_store=store,
            now=attested.NOW,
        )
    message = str(refused.value)
    assert all(
        private not in message
        for private in (routed.secret_ref, str(ingress), str(routed.connection_id), "whsec_")
    )
    assert await stored(app_pool, routed.tenant_id) == (0, 0, 0)


# D-03 -----------------------------------------------------------------------


async def test_company_ingress_cannot_store_another_companys_event(
    routed: Routed,
    other: Routed,
    writer_pool: RuntimePool,
    app_pool: RuntimePool,
) -> None:
    raw = attested.delivery(account="acct_FAKEother")
    for key in (routed.key, other.key):
        with pytest.raises(ProviderEventRejectedError):
            await attested.receive(writer_pool, routed, raw, signing_key=key)
    assert await stored(app_pool, routed.tenant_id) == (0, 0, 0)
    assert await stored(app_pool, other.tenant_id) == (0, 0, 0)
    result = await attested.receive(writer_pool, other, raw)
    assert (result.connection_id, result.book_id, result.verification_config_id) == (
        other.connection_id,
        other.book_id,
        other.verification_config_id,
    )
    assert await stored(app_pool, other.tenant_id) == (1, 1, 1)
    assert await stored(app_pool, routed.tenant_id) == (0, 0, 0)


# D-04 -----------------------------------------------------------------------


async def test_rotation_moves_verification_to_the_next_version_only(
    routed: Routed,
    writer_pool: RuntimePool,
    app_pool: RuntimePool,
    owner_conn: psycopg.Connection,
) -> None:
    with pytest.raises(psycopg.errors.UniqueViolation):
        attested.provision_config(
            owner_conn, routed.tenant_id, routed.connection_id, "test:k1d-parallel"
        )
    await revoke(app_pool, routed, "provider_verification_configs", routed.verification_config_id)
    rotated_ref = "test:k1d-rotated-" + uuid7().hex
    rotated_key = attested.fake_key()
    rotated, version = attested.provision_config(
        owner_conn, routed.tenant_id, routed.connection_id, rotated_ref
    )
    assert version == 2
    store = {routed.secret_ref: routed.key, rotated_ref: rotated_key}
    raw = attested.delivery()
    with pytest.raises(ProviderEventRejectedError):
        await receive_routed_receipt(
            writer_pool,
            routed.ingress_id,
            raw,
            signed.signed(raw, routed.key),
            key_store=store,
            now=attested.NOW,
        )
    assert await stored(app_pool, routed.tenant_id) == (0, 0, 0)
    result = await receive_routed_receipt(
        writer_pool,
        routed.ingress_id,
        raw,
        signed.signed(raw, rotated_key),
        key_store=store,
        now=attested.NOW,
    )
    assert result.verification_config_id == rotated
    rows = await attested.attestations(app_pool, routed.tenant_id)
    assert [row[4] for row in rows] == [rotated]


async def test_owner_supplied_version_and_author_are_replaced(
    inbox: archive.Inbox,
    owner_conn: psycopg.Connection,
    app_pool: RuntimePool,
    test_database: ProvisionedDatabase,
) -> None:
    config = uuid7()
    with owner_tenant_transaction(owner_conn, inbox.ledger.business):
        owner_conn.execute(
            "insert into gba.provider_verification_configs "
            "(tenant_id,id,connection_id,secret_ref,version,created_by) "
            "values (%s,%s,%s,'test:k1d-explicit',99,'forged')",
            (inbox.ledger.business, config, inbox.connection),
        )
    async with tenant_transaction(app_pool, inbox.ledger.business) as conn:
        row = await (
            await conn.execute(
                "select version,created_by from gba.provider_verification_configs where id=%s",
                (config,),
            )
        ).fetchone()
    assert row == (1, str(conninfo_to_dict(test_database.owner_dsn)["user"]))


# D-05 -----------------------------------------------------------------------

_CONFIG_INSERT = (
    "insert into gba.provider_verification_configs (tenant_id,id,connection_id,secret_ref) "
    "values (%(tenant)s,%(row)s,%(connection)s,'test:k1d-forged')"
)
_ROUTE_INSERT = (
    "insert into gba.provider_receipt_routes (ingress_id,tenant_id,connection_id) "
    "values (%(row)s,%(tenant)s,%(connection)s)"
)
_REWRITES = [
    _CONFIG_INSERT,
    "update gba.provider_verification_configs set secret_ref='test:k1d-forged'",
    "update gba.provider_verification_configs set connection_id=connection_id",
    "delete from gba.provider_verification_configs",
    "truncate gba.provider_verification_configs",
    _ROUTE_INSERT,
    "update gba.provider_receipt_routes set tenant_id=tenant_id",
    "delete from gba.provider_receipt_routes",
    "truncate gba.provider_receipt_routes",
]


async def _refused(pool: RuntimePool, scope: Routed, statement: str) -> None:
    params = {"tenant": scope.tenant_id, "row": uuid7(), "connection": scope.connection_id}
    with pytest.raises(psycopg.errors.InsufficientPrivilege):
        async with tenant_transaction(pool, scope.tenant_id) as conn:
            await conn.execute(statement, params if "%(" in statement else None)


@pytest.mark.parametrize("statement", [*_REWRITES, "select * from gba.provider_receipt_routes"])
async def test_runtime_cannot_provision_read_routes_or_rewrite_authority(
    routed: Routed, app_pool: RuntimePool, statement: str
) -> None:
    await _refused(app_pool, routed, statement)


@pytest.mark.parametrize("statement", _REWRITES)
async def test_writer_cannot_provision_or_rewrite_authority(
    routed: Routed, writer_pool: RuntimePool, statement: str
) -> None:
    await _refused(writer_pool, routed, statement)


async def test_only_the_writer_resolves_routes_and_only_ids_are_exposed(
    routed: Routed, writer_pool: RuntimePool
) -> None:
    async with unscoped_transaction(writer_pool) as conn:
        rows = await (
            await conn.execute(
                "select to_jsonb(r) - 'created_at' from gba.provider_receipt_routes r "
                "where ingress_id=%s",
                (routed.ingress_id,),
            )
        ).fetchall()
        assert rows == [
            (
                {
                    "ingress_id": str(routed.ingress_id),
                    "tenant_id": str(routed.tenant_id),
                    "connection_id": str(routed.connection_id),
                },
            )
        ]
        assert not await (
            await conn.execute("select * from gba.provider_verification_configs")
        ).fetchall()


@pytest.mark.parametrize("pool_name", ["runtime", "writer"])
async def test_config_revocation_is_permanent(
    routed: Routed,
    app_pool: RuntimePool,
    writer_pool: RuntimePool,
    pool_name: str,
) -> None:
    pool = app_pool if pool_name == "runtime" else writer_pool
    await revoke(pool, routed, "provider_verification_configs", routed.verification_config_id)
    with pytest.raises(psycopg.errors.CheckViolation):
        async with tenant_transaction(pool, routed.tenant_id) as conn:
            await conn.execute(
                "update gba.provider_verification_configs set revoked=false where id=%s",
                (routed.verification_config_id,),
            )


@pytest.mark.parametrize("config", ["missing", "foreign", "revoked"])
async def test_writer_cannot_attest_with_a_missing_foreign_or_revoked_config(
    inbox: archive.Inbox,
    routed: Routed,
    writer_pool: RuntimePool,
    app_pool: RuntimePool,
    owner_conn: psycopg.Connection,
    config: str,
) -> None:
    config_id = uuid7()
    if config == "foreign":
        second = second_connection(owner_conn, routed)
        config_id, _ = attested.provision_config(
            owner_conn, routed.tenant_id, second, "test:k1d-" + uuid7().hex
        )
    elif config == "revoked":
        config_id = routed.verification_config_id
        await revoke(app_pool, routed, "provider_verification_configs", config_id)
    event = inbox.event()

    async def attest() -> None:
        async with tenant_transaction(writer_pool, routed.tenant_id) as conn:
            result = await record_event(conn, routed.connection_id, event)
            await conn.execute(
                "insert into gba.provider_event_attestations "
                "(tenant_id,event_id,delivery_sha256,verification_config_id) values (%s,%s,%s,%s)",
                (routed.tenant_id, result.event_id, event.delivery_sha256, config_id),
            )

    with pytest.raises(psycopg.errors.CheckViolation):
        await attest()
    assert await stored(app_pool, routed.tenant_id) == (0, 0, 0)


_SECRET_LIKE = [
    "whsec_FAKE",
    "test:whsec_FAKE",
    "kv:sk_test_FAKE",
    "kv:path/RK_LIVE_FAKE",
    "kv:pk_test_FAKE",
    "plain-name",
    "kv:",
    "Upper:name",
    "kv:with space",
]


@pytest.mark.parametrize(
    "case", ["unscoped", "branch", "revoked_connection", "pre_revoked", *_SECRET_LIKE]
)
async def test_owner_config_needs_company_scope_live_connection_and_opaque_reference(
    inbox: archive.Inbox,
    owner_conn: psycopg.Connection,
    app_pool: RuntimePool,
    case: str,
) -> None:
    tenant, reference, revoked = inbox.ledger.business, "test:k1d-" + uuid7().hex, False
    if case in _SECRET_LIKE:
        reference = case
    elif case == "revoked_connection":
        async with tenant_transaction(app_pool, tenant) as conn:
            await conn.execute(
                "update gba.provider_receipt_connections set revoked=true where id=%s",
                (inbox.connection,),
            )
    elif case == "pre_revoked":
        revoked = True

    def provision() -> None:
        with owner_conn.transaction():
            if case != "unscoped":
                owner_conn.execute("select set_config('gba.tenant_id',%s,true)", (str(tenant),))
            if case == "branch":
                owner_conn.execute("select set_config('gba.location_id',%s,true)", (str(uuid7()),))
            owner_conn.execute(
                "insert into gba.provider_verification_configs "
                "(tenant_id,id,connection_id,secret_ref,revoked) values (%s,%s,%s,%s,%s)",
                (tenant, uuid7(), inbox.connection, reference, revoked),
            )

    with pytest.raises(psycopg.errors.CheckViolation):
        provision()
    async with tenant_transaction(app_pool, tenant) as conn:
        assert not await (
            await conn.execute("select * from gba.provider_verification_configs")
        ).fetchall()


@pytest.mark.parametrize(
    ("case", "error"),
    [
        ("unscoped", psycopg.errors.InsufficientPrivilege),
        ("branch", psycopg.errors.InsufficientPrivilege),
        ("duplicate", psycopg.errors.UniqueViolation),
        ("unknown_connection", psycopg.errors.ForeignKeyViolation),
    ],
)
async def test_owner_route_needs_company_scope_and_one_known_connection(
    routed: Routed,
    owner_conn: psycopg.Connection,
    case: str,
    error: type[Exception],
) -> None:
    connection = uuid7() if case == "unknown_connection" else routed.connection_id

    def provision() -> None:
        with owner_conn.transaction():
            if case != "unscoped":
                owner_conn.execute(
                    "select set_config('gba.tenant_id',%s,true)", (str(routed.tenant_id),)
                )
            if case == "branch":
                owner_conn.execute("select set_config('gba.location_id',%s,true)", (str(uuid7()),))
            owner_conn.execute(
                "insert into gba.provider_receipt_routes (ingress_id,tenant_id,connection_id) "
                "values (%s,%s,%s)",
                (uuid7(), routed.tenant_id, connection),
            )

    with pytest.raises(error):
        provision()


async def test_authority_rows_are_permanent_even_for_owner_and_superuser(
    routed: Routed,
    writer_pool: RuntimePool,
    owner_conn: psycopg.Connection,
    test_database: ProvisionedDatabase,
) -> None:
    for statement in (
        "update gba.provider_verification_configs set secret_ref='test:k1d-moved' where id=%s",
        "delete from gba.provider_verification_configs where id=%s",
    ):
        with (
            pytest.raises(psycopg.errors.CheckViolation),
            owner_tenant_transaction(owner_conn, routed.tenant_id),
        ):
            owner_conn.execute(statement, (routed.verification_config_id,))
    with owner_tenant_transaction(owner_conn, routed.tenant_id):
        moved = owner_conn.execute(
            "update gba.provider_receipt_routes set connection_id=connection_id"
        )
        assert moved.rowcount == 0
    with psycopg.connect(test_database.admin_dsn, dbname=test_database.name) as admin:
        for statement in (
            "update gba.provider_receipt_routes set connection_id=connection_id",
            "delete from gba.provider_receipt_routes",
        ):
            with pytest.raises(psycopg.errors.CheckViolation), admin.transaction():
                admin.execute(statement)
    result = await attested.receive(writer_pool, routed, attested.delivery())
    assert result.verification_config_id == routed.verification_config_id


# D-06 -----------------------------------------------------------------------


async def test_config_revocation_waits_for_an_inflight_receipt_then_refuses_the_next(
    routed: Routed,
    writer_pool: RuntimePool,
    app_pool: RuntimePool,
    test_database: ProvisionedDatabase,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    held, release = asyncio.Event(), asyncio.Event()
    identity: list[tuple[int, str]] = []
    original = record_event

    async def paused(
        conn: RuntimeConnection, connection_id: UUID, event: SignedStripeEvent
    ) -> ReceiptResult:
        row = await (
            await conn.execute("select pg_backend_pid(),pg_current_xact_id()::text")
        ).fetchone()
        assert row is not None
        identity.append((row[0], row[1]))
        held.set()
        await release.wait()
        return await original(conn, connection_id, event)

    monkeypatch.setattr(service, "record_event", paused)
    receipt = asyncio.create_task(attested.receive(writer_pool, routed, attested.delivery()))
    revocation = None
    monitor = await psycopg.AsyncConnection.connect(
        test_database.admin_dsn, dbname=test_database.name, autocommit=True
    )
    try:
        await asyncio.wait_for(held.wait(), 15)
        revocation = asyncio.create_task(
            revoke(app_pool, routed, "provider_verification_configs", routed.verification_config_id)
        )
        deadline = asyncio.get_running_loop().time() + 8
        while asyncio.get_running_loop().time() < deadline:
            waiting = await (
                await monitor.execute(
                    "select l.pid from pg_catalog.pg_locks l "
                    "join pg_catalog.pg_stat_activity a on a.pid=l.pid "
                    "where not l.granted and l.locktype='transactionid' "
                    "and l.transactionid::text=%s and %s=any(pg_blocking_pids(l.pid)) "
                    "and a.datname=current_database() "
                    "and a.query like 'update gba.provider_verification_configs%%'",
                    (identity[0][1], identity[0][0]),
                )
            ).fetchone()
            if waiting is not None:
                break
            await asyncio.sleep(0.01)
        else:
            pytest.fail("Config revocation must wait on the in-flight receipt in pg_locks")
        assert not revocation.done()
        release.set()
        result = await asyncio.wait_for(receipt, 15)
        await asyncio.wait_for(revocation, 15)
    finally:
        release.set()
        for task in (receipt, revocation):
            if task is not None and not task.done():
                task.cancel()
        await asyncio.gather(
            *(task for task in (receipt, revocation) if task is not None), return_exceptions=True
        )
        await monitor.close()
    assert result.verification_config_id == routed.verification_config_id
    monkeypatch.undo()
    with pytest.raises(ReceiptBindingRejectedError):
        await attested.receive(writer_pool, routed, attested.delivery() + b"\n")
    assert await stored(app_pool, routed.tenant_id) == (1, 1, 1)


# D-08 -----------------------------------------------------------------------

_ACTIVE_INDEX = (
    "create unique index provider_verification_configs_active "
    "on gba.provider_verification_configs (tenant_id,connection_id) where not revoked;"
)
_CONFIG_KEY = (
    "alter table gba.provider_event_attestations add constraint "
    "provider_event_attestations_config_fkey foreign key "
    "(tenant_id,connection_id,verification_config_id) references "
    "gba.provider_verification_configs (tenant_id,connection_id,id);"
)


@pytest.mark.parametrize(
    ("damage", "repair"),
    [
        pytest.param(
            "grant select on gba.provider_receipt_routes to gba_runtime;",
            "revoke select on gba.provider_receipt_routes from gba_runtime;",
            id="runtime-reads-routes",
        ),
        pytest.param(
            "grant insert on gba.provider_receipt_routes to gba_receipt_writer;",
            "revoke insert on gba.provider_receipt_routes from gba_receipt_writer;",
            id="writer-inserts-routes",
        ),
        pytest.param(
            "drop index gba.provider_verification_configs_active;",
            _ACTIVE_INDEX,
            id="missing-active-index",
        ),
        pytest.param(
            "alter policy provider_receipt_routes_resolve on gba.provider_receipt_routes "
            "to public;",
            "alter policy provider_receipt_routes_resolve on gba.provider_receipt_routes "
            "to gba_receipt_writer;",
            id="route-policy-widened",
        ),
        pytest.param(
            "alter table gba.provider_verification_configs "
            "disable trigger provider_verification_configs_guard;",
            "alter table gba.provider_verification_configs "
            "enable trigger provider_verification_configs_guard;",
            id="config-trigger-disabled",
        ),
        pytest.param(
            "alter table gba.provider_event_attestations "
            "drop constraint provider_event_attestations_config_fkey;",
            _CONFIG_KEY,
            id="config-key-dropped",
        ),
    ],
)
async def test_authority_schema_drift_stops_routed_and_runtime_receipts(
    inbox: archive.Inbox,
    routed: Routed,
    writer_pool: RuntimePool,
    app_pool: RuntimePool,
    owner_conn: psycopg.Connection,
    damage: str,
    repair: str,
) -> None:
    owner_conn.execute(damage.encode())
    try:
        with pytest.raises(DatabaseUnavailableError):
            await attested.receive(writer_pool, routed, attested.delivery())
        with pytest.raises(DatabaseUnavailableError):
            await archive.receive(app_pool, inbox, inbox.event())
    finally:
        owner_conn.execute(repair.encode())
    async with tenant_transaction(app_pool, routed.tenant_id) as conn:
        await assert_provider_receipt_ready(conn)
    assert await stored(app_pool, routed.tenant_id) == (0, 0, 0)
