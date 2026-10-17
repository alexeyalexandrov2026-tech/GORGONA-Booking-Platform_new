"""K1k (review IR-08, IR-09): no TRUNCATE of receipt history, random route IDs; synthetic only."""

import dataclasses
from uuid import UUID, uuid7

import psycopg
import pytest

from gorgona_booking.db.pool import RuntimePool, tenant_transaction, unscoped_transaction
from gorgona_booking.db.provider_receipt_guard import assert_provider_receipt_ready
from gorgona_booking.db.provisioning import owner_tenant_transaction
from gorgona_booking.errors import DatabaseUnavailableError
from gorgona_booking.providers.authenticated_receipts import UnsafeReceiptWriterRoleError
from tests.integration import test_provider_event_inbox as archive
from tests.integration import test_provider_receipt_attestations as attested
from tests.integration import test_provider_receipt_routing as routing
from tests.integration.conftest import ProvisionedDatabase

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

TABLES = (
    "provider_receipt_connections",
    "provider_event_inbox",
    "provider_event_deliveries",
    "provider_event_attestations",
    "provider_verification_configs",
    "provider_receipt_routes",
)


def counts(database: ProvisionedDatabase) -> list[object]:
    with psycopg.connect(database.admin_dsn, dbname=database.name) as admin:
        return [admin.execute(f"select count(*) from gba.{table}").fetchone() for table in TABLES]


# T-01 -----------------------------------------------------------------------


# A plain TRUNCATE of a referenced table already stops at its foreign keys, before any trigger;
# CASCADE passes them, so every table and the ledger book they reference are truncated that way.
STATEMENTS = [f"truncate gba.{table} cascade" for table in (*TABLES, "ledger_books")]


@pytest.mark.parametrize("actor", ["owner", "superuser"])
@pytest.mark.parametrize("statement", STATEMENTS)
async def test_receipt_history_cannot_be_truncated(
    routed: Routed,
    writer_pool: RuntimePool,
    owner_conn: psycopg.Connection,
    test_database: ProvisionedDatabase,
    actor: str,
    statement: str,
) -> None:
    await attested.receive(writer_pool, routed, attested.delivery())
    before = counts(test_database)
    assert (0,) not in before
    with psycopg.connect(test_database.admin_dsn, dbname=test_database.name) as superuser:
        conn = owner_conn if actor == "owner" else superuser
        # Rolled back whatever happens: a missing guard must not empty the shared database.
        with (
            pytest.raises(psycopg.errors.CheckViolation, match="truncate is refused"),
            conn.transaction(force_rollback=True),
        ):
            conn.execute(statement.encode())
    assert counts(test_database) == before


# T-02 -----------------------------------------------------------------------


async def provision_unnamed_route(
    owner_conn: psycopg.Connection, writer_pool: RuntimePool, scope: Routed
) -> Routed:
    connection = routing.second_connection(owner_conn, scope)
    reference = "test:k1k-" + uuid7().hex
    config, _ = attested.provision_config(owner_conn, scope.tenant_id, connection, reference)
    with owner_tenant_transaction(owner_conn, scope.tenant_id):
        owner_conn.execute(
            "insert into gba.provider_receipt_routes (tenant_id,connection_id) values (%s,%s)",
            (scope.tenant_id, connection),
        )
    async with unscoped_transaction(writer_pool) as conn:
        row = await (
            await conn.execute(
                "select ingress_id from gba.provider_receipt_routes "
                "where tenant_id=%s and connection_id=%s",
                (scope.tenant_id, connection),
            )
        ).fetchone()
    assert row is not None
    return dataclasses.replace(
        scope,
        connection_id=connection,
        ingress_id=row[0],
        verification_config_id=config,
        secret_ref=reference,
        key=attested.fake_key(),
    )


async def test_a_route_without_an_id_gets_a_random_one_that_routes(
    routed: Routed,
    owner_conn: psycopg.Connection,
    writer_pool: RuntimePool,
    app_pool: RuntimePool,
) -> None:
    first = await provision_unnamed_route(owner_conn, writer_pool, routed)
    second = await provision_unnamed_route(owner_conn, writer_pool, routed)
    assert first.ingress_id != second.ingress_id
    assert {UUID(str(scope.ingress_id)).version for scope in (first, second)} == {4}
    result = await attested.receive(
        writer_pool, first, attested.delivery(account="acct_FAKEsecond")
    )
    assert result.disposition == "recorded"
    assert result.verification_config_id == first.verification_config_id
    async with tenant_transaction(app_pool, routed.tenant_id) as conn:
        row = await (
            await conn.execute(
                "select connection_id from gba.provider_event_attestations where event_id=%s",
                (result.event_id,),
            )
        ).fetchone()
    assert row == (first.connection_id,)


# T-03 -----------------------------------------------------------------------

_TRIGGER = (
    "create trigger provider_event_inbox_no_truncate before truncate on gba.provider_event_inbox "
    "for each statement execute function gba.reject_provider_receipt_truncate()"
)
_DRIFT = [
    (
        "dropped-truncate-trigger",
        ["drop trigger provider_event_inbox_no_truncate on gba.provider_event_inbox"],
        [_TRIGGER],
    ),
    (
        "disabled-truncate-trigger",
        [
            "alter table gba.provider_event_deliveries "
            "disable trigger provider_event_deliveries_no_truncate"
        ],
        [
            "alter table gba.provider_event_deliveries "
            "enable trigger provider_event_deliveries_no_truncate"
        ],
    ),
    (
        "route-default-removed",
        ["alter table gba.provider_receipt_routes alter column ingress_id drop default"],
        [
            "alter table gba.provider_receipt_routes "
            "alter column ingress_id set default gen_random_uuid()"
        ],
    ),
]


@pytest.mark.parametrize(("damage", "repair"), [pytest.param(d, r, id=i) for i, d, r in _DRIFT])
async def test_truncate_guard_drift_stops_routed_and_runtime_receipts(
    inbox: archive.Inbox,
    routed: Routed,
    writer_pool: RuntimePool,
    app_pool: RuntimePool,
    test_database: ProvisionedDatabase,
    damage: list[str],
    repair: list[str],
) -> None:
    with psycopg.connect(
        test_database.admin_dsn, dbname=test_database.name, autocommit=True
    ) as admin:
        try:
            for statement in damage:
                admin.execute(statement.encode())
            with pytest.raises((DatabaseUnavailableError, UnsafeReceiptWriterRoleError)):
                await attested.receive(writer_pool, routed, attested.delivery())
            with pytest.raises(DatabaseUnavailableError):
                await archive.receive(app_pool, inbox, inbox.event())
        finally:
            for statement in repair:
                admin.execute(statement.encode())
    async with tenant_transaction(app_pool, routed.tenant_id) as conn:
        await assert_provider_receipt_ready(conn)
    assert await routing.stored(app_pool, routed.tenant_id) == (0, 0, 0)
    assert (
        await attested.receive(writer_pool, routed, attested.delivery())
    ).disposition == "recorded"
