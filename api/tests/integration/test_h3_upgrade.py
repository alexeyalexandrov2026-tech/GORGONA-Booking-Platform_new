"""0030 upgrades nonempty 0029 snapshots, or refuses without changing any fact.

Only fake fixture data is copied into dedicated disposable test databases. The
superuser copy suppresses restore-time triggers; every operation under test uses
the ordinary runtime or dedicated migration-owner role. No original DB is edited.
"""

import hashlib
from collections.abc import Iterator
from uuid import uuid7

import psycopg
import pytest
from psycopg import sql
from psycopg.conninfo import conninfo_to_dict, make_conninfo
from psycopg.types.json import Jsonb

from gorgona_booking.db.h3_upgrade import check_h3_upgrade
from gorgona_booking.db.migrate import MigrationError, apply_migrations, load_migrations
from gorgona_booking.db.pool import create_runtime_pool
from tests.integration import test_h3_forward_corrections as shared
from tests.integration.conftest import ProvisionedDatabase
from tests.integration.test_credit_notes import CreditWorld
from tests.integration.test_h3_forward_corrections import (
    _write_out_of_order,
    _write_oversized_credit,
)
from tests.integration.test_payment_corrections import CorrectionWorld

pytestmark = pytest.mark.anyio
client = shared.client
idp = shared.idp
manager_a = shared.manager_a
manager_b = shared.manager_b
enabled = shared.enabled
invoices = shared.invoices
payments = shared.payments
credits = shared.credits
corrections = shared.corrections


@pytest.fixture
def previous_database(test_database: ProvisionedDatabase) -> Iterator[ProvisionedDatabase]:
    name = "gba_h3_upgrade_" + uuid7().hex
    owner = str(conninfo_to_dict(test_database.owner_dsn)["user"])
    with psycopg.connect(test_database.admin_dsn, autocommit=True) as admin:
        admin.execute(
            sql.SQL("create database {} owner {} encoding 'UTF8' template template0").format(
                sql.Identifier(name), sql.Identifier(owner)
            )
        )
        admin.execute(sql.SQL("revoke all on database {} from public").format(sql.Identifier(name)))
        admin.execute(
            sql.SQL("grant connect on database {} to gba_runtime").format(sql.Identifier(name))
        )
    database = ProvisionedDatabase(
        name=name,
        admin_dsn=make_conninfo(test_database.admin_dsn, dbname=name),
        owner_dsn=make_conninfo(test_database.owner_dsn, dbname=name),
        app_dsn=make_conninfo(test_database.app_dsn, dbname=name),
    )
    try:
        apply_migrations(database.owner_dsn, load_migrations()[:29])
        yield database
    finally:
        with psycopg.connect(test_database.admin_dsn, autocommit=True) as admin:
            admin.execute(sql.SQL("drop database {} with (force)").format(sql.Identifier(name)))


def copy_fixture_data(source: ProvisionedDatabase, target: ProvisionedDatabase) -> None:
    """Restore a fake data snapshot to old schema, preserving original transactions."""
    with (
        psycopg.connect(make_conninfo(source.admin_dsn, dbname=source.name)) as before,
        psycopg.connect(target.admin_dsn) as after,
    ):
        source_tables = before.execute(
            "select tablename from pg_catalog.pg_tables where schemaname='gba' order by tablename"
        ).fetchall()
        target_tables = {
            row[0]
            for row in after.execute(
                "select tablename from pg_catalog.pg_tables where schemaname='gba'"
            )
        }
        tables = [row for row in source_tables if row[0] in target_tables]
        after.execute("set local session_replication_role=replica")
        after.execute(
            sql.SQL("truncate {} cascade").format(
                sql.SQL(",").join(sql.Identifier("gba", row[0]) for row in tables)
            )
        )
        for (table,) in tables:
            columns = [
                row[0]
                for row in before.execute(
                    "select attname from pg_catalog.pg_attribute "
                    "where attrelid=pg_catalog.to_regclass(%s) and attnum>0 "
                    "and not attisdropped and attgenerated='' order by attnum",
                    ("gba." + table,),
                ).fetchall()
            ]
            names = sql.SQL(",").join(sql.Identifier(column) for column in columns)
            cursor = before.execute(
                sql.SQL("select {} from {}").format(names, sql.Identifier("gba", table))
            )
            assert cursor.description is not None
            json_columns = {
                index for index, column in enumerate(cursor.description) if column.type_code == 3802
            }
            with after.cursor().copy(
                sql.SQL("copy {} ({}) from stdin").format(sql.Identifier("gba", table), names)
            ) as writer:
                for row in cursor:
                    writer.write_row(
                        tuple(
                            Jsonb(value) if index in json_columns and value is not None else value
                            for index, value in enumerate(row)
                        )
                    )


def snapshot(database: ProvisionedDatabase) -> dict[str, tuple[int, str]]:
    """Stable count and digest of every financial/domain table; secrets stay in DSN."""
    result: dict[str, tuple[int, str]] = {}
    with psycopg.connect(database.admin_dsn) as conn:
        for (table,) in conn.execute(
            "select tablename from pg_catalog.pg_tables where schemaname='gba' order by tablename"
        ).fetchall():
            rows = conn.execute(
                sql.SQL("select to_jsonb(t)::text from {} t order by to_jsonb(t)::text").format(
                    sql.Identifier("gba", table)
                )
            ).fetchall()
            digest = hashlib.sha256("\n".join(row[0] for row in rows).encode("utf-8")).hexdigest()
            result[table] = len(rows), digest
    return result


def force_flags(database: ProvisionedDatabase) -> list[tuple[bool, bool]]:
    with psycopg.connect(database.admin_dsn) as conn:
        assert conn.execute(
            "select count(*) from pg_catalog.pg_policy where polname='h3_upgrade_owner_read'"
        ).fetchone() == (0,)
        return conn.execute(
            "select relrowsecurity,relforcerowsecurity from pg_catalog.pg_class "
            "where oid=any(array['gba.external_payments'::regclass,"
            "'gba.external_payment_revisions'::regclass,'gba.financial_documents'::regclass,"
            "'gba.financial_document_versions'::regclass]) order by relname"
        ).fetchall()


def test_upgrade_preview_refuses_superuser(test_database: ProvisionedDatabase) -> None:
    with pytest.raises(MigrationError, match="dedicated nonsuperuser owner"):
        check_h3_upgrade(test_database.admin_dsn)


def test_upgrade_preview_refuses_already_applied_target(test_database: ProvisionedDatabase) -> None:
    with pytest.raises(MigrationError, match="exactly the approved 0001-0029"):
        check_h3_upgrade(test_database.owner_dsn)


async def test_nonempty_upgrade_keeps_all_rows_checksums_and_rls(
    credits: CreditWorld,
    corrections: CorrectionWorld,
    test_database: ProvisionedDatabase,
    previous_database: ProvisionedDatabase,
) -> None:
    obligation, (line,) = await credits.invoice()
    await credits.paid(obligation, "70.00", "FAKE-UPGRADE-VALID")
    await credits.credit(obligation, [(line, "50.00")], refund=credits.chart["2100"])
    copy_fixture_data(test_database, previous_database)
    before = snapshot(previous_database)
    assert sum(count for count, _ in before.values()) > 0
    preview = check_h3_upgrade(previous_database.owner_dsn)
    assert preview.target_version == 30
    assert snapshot(previous_database) == before
    assert force_flags(previous_database) == [(True, True)] * 4
    h3_migrations = load_migrations()[:30]
    applied = apply_migrations(previous_database.owner_dsn, h3_migrations)
    assert [migration.version for migration in applied] == [30]
    assert apply_migrations(previous_database.owner_dsn, h3_migrations) == []
    assert snapshot(previous_database) == before
    assert force_flags(previous_database) == [(True, True)] * 4
    with psycopg.connect(previous_database.owner_dsn) as conn:
        checksums: dict[int, str] = dict(
            conn.execute("select version,checksum from public.gba_schema_migrations")
        )
    assert checksums == {migration.version: migration.checksum for migration in h3_migrations}


@pytest.mark.parametrize("conflict", ["identity", "event_order", "credit_lines"])
async def test_preflight_refuses_conflict_without_rewriting_any_fact(
    credits: CreditWorld,
    corrections: CorrectionWorld,
    test_database: ProvisionedDatabase,
    previous_database: ProvisionedDatabase,
    conflict: str,
) -> None:
    obligation, (line,) = await credits.invoice()
    settlement = await corrections.held([(obligation, "100.00")])
    if conflict == "credit_lines":
        assert (await credits.settlements.act(settlement, "release", 3)).status_code == 200
    if conflict == "identity":
        await credits.payments.confirm(
            settlement, 3, [(obligation, "50.00")], "50.00", "FAKE-\u039f\u03a3"
        )
    copy_fixture_data(test_database, previous_database)
    pool = create_runtime_pool(previous_database.app_dsn, min_size=1, max_size=2)
    await pool.open(wait=True)
    try:
        if conflict == "identity":
            await credits.payments.write_directly(
                pool, settlement, 5, obligation, 5000, "fake-\u03bf\u03c2"
            )
        elif conflict == "event_order":
            await _write_out_of_order(credits, pool, obligation, settlement)
        else:
            await _write_oversized_credit(credits, pool, obligation, line)
    finally:
        await pool.close()
    before = snapshot(previous_database)
    with psycopg.connect(previous_database.owner_dsn) as conn:
        original = conn.execute(
            "select prosrc from pg_catalog.pg_proc "
            "where oid='gba.external_identity_key(text,text)'::regprocedure"
        ).fetchone()
    with pytest.raises(psycopg.errors.CheckViolation, match="0030 preflight"):
        check_h3_upgrade(previous_database.owner_dsn)
    assert snapshot(previous_database) == before
    assert force_flags(previous_database) == [(True, True)] * 4
    with pytest.raises(psycopg.errors.CheckViolation, match="0030 preflight"):
        apply_migrations(previous_database.owner_dsn)
    assert snapshot(previous_database) == before
    assert force_flags(previous_database) == [(True, True)] * 4
    with psycopg.connect(previous_database.owner_dsn) as conn:
        assert (
            conn.execute(
                "select prosrc from pg_catalog.pg_proc "
                "where oid='gba.external_identity_key(text,text)'::regprocedure"
            ).fetchone()
            == original
        )
        assert conn.execute(
            "select count(*) from public.gba_schema_migrations where version=30"
        ).fetchone() == (0,)
