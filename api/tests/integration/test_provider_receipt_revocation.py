"""K1j (review IR-07): a revocation records why, when and by which login; synthetic only."""

import re
from collections.abc import AsyncIterator
from importlib import resources
from uuid import UUID, uuid7

import psycopg
import pytest
from psycopg import sql
from psycopg.conninfo import conninfo_to_dict, make_conninfo

from gorgona_booking.db.pool import RuntimePool, create_runtime_pool, tenant_transaction
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

CONFIGS = "provider_verification_configs"
CONNECTIONS = "provider_receipt_connections"
GROUP = "gba_receipt_writer"


@pytest.fixture
async def group_pool(writer_pool: RuntimePool) -> AsyncIterator[RuntimePool]:
    """The writer login acting as its group, as after `SET ROLE gba_receipt_writer`."""
    assert isinstance(writer_pool.conninfo, str)
    pool = create_runtime_pool(
        make_conninfo(writer_pool.conninfo, options=f"-c role={GROUP}"), max_size=2
    )
    await pool.open(wait=True)
    try:
        yield pool
    finally:
        await pool.close()


def row_id(scope: Routed, table: str) -> UUID:
    return scope.verification_config_id if table == CONFIGS else scope.connection_id


async def revoke(pool: RuntimePool, scope: Routed, table: str, reason: str) -> None:
    async with tenant_transaction(pool, scope.tenant_id) as conn:
        await conn.execute(
            f"update gba.{table} set revoked=true, revoked_reason=%s where id=%s",
            (reason, row_id(scope, table)),
        )


async def record(pool: RuntimePool, scope: Routed, table: str) -> tuple[object, ...]:
    async with tenant_transaction(pool, scope.tenant_id) as conn:
        row = await (
            await conn.execute(
                f"select revoked,revoked_reason,revoked_at,revoked_by from gba.{table} where id=%s",
                (row_id(scope, table),),
            )
        ).fetchone()
    assert row is not None
    return tuple(row)


async def refused(
    pool: RuntimePool,
    scope: Routed,
    statement: str,
    error: type[Exception],
    match: str | None = None,
) -> None:
    with pytest.raises(error, match=match):
        async with tenant_transaction(pool, scope.tenant_id) as conn:
            await conn.execute(statement.encode(), (row_id(scope, _table(statement)),))


def _table(statement: str) -> str:
    return CONFIGS if CONFIGS in statement else CONNECTIONS


def login(dsn: str) -> str:
    return str(conninfo_to_dict(dsn)["user"])


# J-01 -----------------------------------------------------------------------


@pytest.mark.parametrize("who", ["runtime", "writer"])
@pytest.mark.parametrize(
    ("table", "assignment", "match"),
    [
        (CONFIGS, "revoked=true", "needs a reason"),
        (CONNECTIONS, "revoked=true", "needs a reason"),
        (CONFIGS, "revoked=true, revoked_reason='forgotten'", "_revocation"),
        (CONNECTIONS, "revoked=true, revoked_reason='rotation'", "_revocation"),
    ],
)
async def test_revocation_without_a_valid_reason_is_refused(
    routed: Routed,
    app_pool: RuntimePool,
    writer_pool: RuntimePool,
    who: str,
    table: str,
    assignment: str,
    match: str,
) -> None:
    pool = app_pool if who == "runtime" else writer_pool
    statement = f"update gba.{table} set {assignment} where id=%s"
    await refused(pool, routed, statement, psycopg.errors.CheckViolation, match)
    assert await record(app_pool, routed, table) == (False, None, None, None)


# J-02 -----------------------------------------------------------------------


@pytest.mark.parametrize(
    ("who", "table", "reason"),
    [
        ("runtime", CONFIGS, "rotation"),
        ("runtime", CONNECTIONS, "retired"),
        ("writer", CONFIGS, "compromise"),
        ("group", CONNECTIONS, "compromise"),
        ("group", CONFIGS, "retired"),
    ],
)
async def test_revocation_records_reason_time_and_session_login(
    routed: Routed,
    app_pool: RuntimePool,
    writer_pool: RuntimePool,
    group_pool: RuntimePool,
    test_database: ProvisionedDatabase,
    who: str,
    table: str,
    reason: str,
) -> None:
    pool = {"runtime": app_pool, "writer": writer_pool, "group": group_pool}[who]
    expected = login(test_database.app_dsn) if who == "runtime" else attested.WRITER_ROLE
    async with tenant_transaction(pool, routed.tenant_id) as conn:
        await conn.execute(
            f"update gba.{table} set revoked=true, revoked_reason=%s where id=%s",
            (reason, row_id(routed, table)),
        )
        row = await (
            await conn.execute(
                f"select revoked_at=now(),current_user::text from gba.{table} where id=%s",
                (row_id(routed, table),),
            )
        ).fetchone()
    assert row == (True, GROUP if who == "group" else expected)
    stored = await record(app_pool, routed, table)
    assert (stored[0], stored[1], stored[3]) == (True, reason, expected)
    assert stored[2] is not None


# J-03 -----------------------------------------------------------------------


@pytest.mark.parametrize("table", [CONFIGS, CONNECTIONS])
async def test_revocation_record_is_permanent_and_written_only_by_the_trigger(
    routed: Routed,
    app_pool: RuntimePool,
    owner_conn: psycopg.Connection,
    table: str,
) -> None:
    def update(assignment: str) -> str:
        return f"update gba.{table} set {assignment} where id=%s"

    # Before revocation the record cannot be filled in alone.
    await refused(
        app_pool,
        routed,
        update("revoked_reason='retired'"),
        psycopg.errors.CheckViolation,
        "need a revocation",
    )
    for assignment in ("revoked_at=now()", "revoked_by='forged'"):
        await refused(app_pool, routed, update(assignment), psycopg.errors.InsufficientPrivilege)
    assert await record(app_pool, routed, table) == (False, None, None, None)
    await revoke(app_pool, routed, table, "retired")
    before = await record(app_pool, routed, table)
    for assignment in (
        "revoked_reason='compromise'",
        "revoked=false",
        "revoked=true, revoked_reason='compromise'",
    ):
        await refused(
            app_pool, routed, update(assignment), psycopg.errors.CheckViolation, "permanent"
        )
    # Not even the owner rewrites who or when.
    with (
        pytest.raises(psycopg.errors.CheckViolation, match="permanent"),
        owner_tenant_transaction(owner_conn, routed.tenant_id),
    ):
        owner_conn.execute(
            update("revoked_by='forged',revoked_at=now()").encode(), (row_id(routed, table),)
        )
    assert await record(app_pool, routed, table) == before


# J-04 -----------------------------------------------------------------------


async def test_attestation_records_the_login_behind_the_group(
    inbox: archive.Inbox,
    routed: Routed,
    group_pool: RuntimePool,
    app_pool: RuntimePool,
) -> None:
    result = await attested.receive(group_pool, routed, attested.delivery())
    assert result.disposition == "recorded"
    rows = await attested.attestations(app_pool, routed.tenant_id)
    assert [row[6] for row in rows] == [attested.WRITER_ROLE]


async def test_config_records_the_login_behind_the_owner_role(
    routed: Routed,
    app_pool: RuntimePool,
    test_database: ProvisionedDatabase,
) -> None:
    owner, operator = login(test_database.owner_dsn), login(test_database.admin_dsn)
    assert operator != owner
    await revoke(app_pool, routed, CONFIGS, "rotation")
    config = uuid7()
    with (
        psycopg.connect(test_database.admin_dsn, dbname=test_database.name) as admin,
        admin.transaction(),
    ):
        admin.execute(sql.SQL("set local role {}").format(sql.Identifier(owner)))
        admin.execute("select set_config('gba.tenant_id',%s,true)", (str(routed.tenant_id),))
        admin.execute(
            "insert into gba.provider_verification_configs "
            "(tenant_id,id,connection_id,secret_ref) values (%s,%s,%s,'test:k1j-next')",
            (routed.tenant_id, config, routed.connection_id),
        )
        row = admin.execute(
            "select version,created_by,current_user::text "
            "from gba.provider_verification_configs where id=%s",
            (config,),
        ).fetchone()
    assert row == (2, operator, owner)


# J-06 -----------------------------------------------------------------------


def _packaged_body(migration: str, name: str) -> str:
    text = (resources.files("gorgona_booking.db") / "migrations" / migration).read_text(
        encoding="utf-8"
    )
    found = re.search(rf"create function gba\.{name}\(\).*?\$\$;", text, re.DOTALL)
    assert found is not None
    return "create or replace function" + found.group(0).removeprefix("create function")


def _drift(admin: psycopg.Connection, case: str) -> tuple[list[str], list[str]]:
    """Damage and repair; the repair restores what the database held before."""
    if case == "revoked-by-grant":
        return (
            [f"grant update (revoked_by) on gba.{CONFIGS} to gba_runtime"],
            [f"revoke update (revoked_by) on gba.{CONFIGS} from gba_runtime"],
        )
    if case == "revocation-check-dropped":
        name = f"{CONNECTIONS}_revocation"
        row = admin.execute(
            "select pg_get_constraintdef(oid) from pg_constraint "
            "where conrelid=%s::regclass and conname=%s",
            (f"gba.{CONNECTIONS}", name),
        ).fetchone()
        assert row is not None
        return (
            [f"alter table gba.{CONNECTIONS} drop constraint {name}"],
            [f"alter table gba.{CONNECTIONS} add constraint {name} {row[0]}"],
        )
    row = admin.execute(
        "select pg_get_functiondef('gba.guard_provider_verification_config()'::regprocedure)"
    ).fetchone()
    assert row is not None
    damage = _packaged_body(
        "0046_provider_receipt_routing.sql", "guard_provider_verification_config"
    )
    return [damage], [row[0]]


@pytest.mark.parametrize(
    "case", ["revoked-by-grant", "revocation-check-dropped", "config-trigger-0046-body"]
)
async def test_revocation_drift_stops_routed_and_runtime_receipts(
    inbox: archive.Inbox,
    routed: Routed,
    writer_pool: RuntimePool,
    app_pool: RuntimePool,
    test_database: ProvisionedDatabase,
    case: str,
) -> None:
    with psycopg.connect(
        test_database.admin_dsn, dbname=test_database.name, autocommit=True
    ) as admin:
        damage, repair = _drift(admin, case)
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
