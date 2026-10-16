"""Real PostgreSQL regression of the test-only historical-copy query.

Minimal synthetic tables isolate the helper's filtering/performance contract;
actual product upgrade schemas remain covered by the existing upgrade tests.
"""

from collections.abc import Iterator
from dataclasses import replace
from uuid import uuid7

import psycopg
import pytest
from psycopg import sql
from psycopg.conninfo import make_conninfo

from tests.integration.conftest import ProvisionedDatabase
from tests.integration.test_h3_upgrade import copy_fixture_data

ROWS = 15_000
DDL = """
create schema gba;
create table gba.stock_documents (
    tenant_id uuid,id integer,kind text,primary key(tenant_id,id));
create table gba.stock_valuations (
    tenant_id uuid,id integer,quantity integer,primary key(tenant_id,id));
create table gba.journal_entries (
    tenant_id uuid,id integer,source_kind text,primary key(tenant_id,id));
create table gba.journal_lines (
    tenant_id uuid,entry_id integer,id integer,primary key(tenant_id,id));
"""


@pytest.fixture
def copy_databases(test_database: ProvisionedDatabase) -> Iterator[tuple[ProvisionedDatabase, ...]]:
    names = ["gba_copy_budget_" + uuid7().hex for _ in range(2)]
    databases = tuple(
        replace(
            test_database,
            name=name,
            admin_dsn=make_conninfo(test_database.admin_dsn, dbname=name),
            owner_dsn=make_conninfo(test_database.owner_dsn, dbname=name),
            app_dsn=make_conninfo(test_database.app_dsn, dbname=name),
        )
        for name in names
    )
    with psycopg.connect(test_database.admin_dsn, autocommit=True) as admin:
        for name in names:
            admin.execute(
                sql.SQL("create database {} template template0").format(sql.Identifier(name))
            )
            admin.execute(
                sql.SQL("revoke all on database {} from public").format(sql.Identifier(name))
            )
    try:
        yield databases
    finally:
        with psycopg.connect(test_database.admin_dsn, autocommit=True) as admin:
            for name in names:
                admin.execute(sql.SQL("drop database {} with (force)").format(sql.Identifier(name)))


def test_historical_copy_excludes_whole_incompatible_tenant_with_a_bounded_query(
    copy_databases: tuple[ProvisionedDatabase, ...],
) -> None:
    source, target = copy_databases
    allowed, incompatible = uuid7(), uuid7()
    for database in copy_databases:
        with psycopg.connect(database.admin_dsn) as conn:
            conn.execute(DDL)
    with psycopg.connect(target.admin_dsn) as conn:
        conn.execute("create table public.gba_schema_migrations(version integer)")
        conn.execute("insert into public.gba_schema_migrations values(38)")
    with psycopg.connect(source.admin_dsn) as conn:
        for tenant, kind in ((allowed, "receipt"), (incompatible, "transfer")):
            conn.execute(
                "insert into gba.stock_documents select %s,g,%s from generate_series(1,%s) g",
                (tenant, kind, ROWS),
            )
            conn.execute(
                "insert into gba.stock_valuations select %s,g,1 from generate_series(1,%s) g",
                (tenant, ROWS),
            )
            conn.execute(
                "insert into gba.journal_entries select %s,g,'stock' from generate_series(1,%s) g",
                (tenant, ROWS),
            )
            conn.execute("insert into gba.journal_entries values(%s,0,'manual')", (tenant,))
            conn.execute(
                "insert into gba.journal_lines select %s,g,g from generate_series(0,%s) g",
                (tenant, ROWS),
            )
        conn.execute("analyze")
    # Reproduce a bad nested-loop plan without depending on autovacuum timing.
    # The timeout limits each source query, not fixture creation or COPY ingestion.
    with psycopg.connect(source.admin_dsn, autocommit=True) as conn:
        for setting, value in (
            ("enable_hashjoin", "off"),
            ("enable_mergejoin", "off"),
            ("work_mem", "64kB"),
            ("statement_timeout", "2s"),
        ):
            conn.execute(
                sql.SQL("alter database {} set {} to {}").format(
                    sql.Identifier(source.name),
                    sql.Identifier(setting),
                    sql.Literal(value),
                )
            )
    copy_fixture_data(source, target)
    with psycopg.connect(target.admin_dsn) as conn:
        assert conn.execute(
            "select tenant_id,count(*) from gba.stock_documents group by tenant_id"
        ).fetchall() == [(allowed, ROWS)]
        assert conn.execute(
            "select tenant_id,count(*) from gba.stock_valuations group by tenant_id"
        ).fetchall() == [(allowed, ROWS)]
        assert conn.execute("select count(*) from gba.journal_entries").fetchone() == (ROWS + 2,)
        assert conn.execute("select count(*) from gba.journal_lines").fetchone() == (ROWS + 2,)
        assert conn.execute(
            "select count(*) from gba.journal_entries where tenant_id=%s and source_kind='manual'",
            (incompatible,),
        ).fetchone() == (1,)
