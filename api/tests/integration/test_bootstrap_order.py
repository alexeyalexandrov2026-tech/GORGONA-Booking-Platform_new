"""K1f (review IR-06): writer login from the CLI, and bootstrap before migrate. Synthetic only."""

import secrets
from collections.abc import Iterator

import psycopg
import pytest
from psycopg import sql
from psycopg.conninfo import conninfo_to_dict, make_conninfo

from gorgona_booking.db import cli
from gorgona_booking.db.migrate import MigrationError, apply_migrations, load_migrations
from tests.integration.conftest import ProvisionedDatabase

HIDDEN = "gba_receipt_writer_k1f_hidden"


@pytest.fixture
def scratch(test_database: ProvisionedDatabase) -> Iterator[dict[str, str]]:
    """Unique database and role names on the shared cluster; dropped afterwards."""
    suffix = secrets.token_hex(4)
    names = {
        "database": f"gba_k1f_{suffix}",
        "owner": f"gba_k1f_owner_{suffix}",
        "app": f"gba_k1f_app_{suffix}",
        "writer": f"gba_k1f_writer_{suffix}",
    }
    yield names
    with psycopg.connect(test_database.admin_dsn, autocommit=True) as admin:
        admin.execute(
            sql.SQL("drop database if exists {} with (force)").format(
                sql.Identifier(names["database"])
            )
        )
        for role in ("writer", "app", "owner"):
            admin.execute(sql.SQL("drop role if exists {}").format(sql.Identifier(names[role])))


def _is_member(admin: psycopg.Connection, member: str, role: str) -> bool:
    row = admin.execute(
        "select pg_catalog.pg_has_role(%s, %s, 'MEMBER')", (member, role)
    ).fetchone()
    return bool(row and row[0])


def _cli_environment(
    monkeypatch: pytest.MonkeyPatch, test_database: ProvisionedDatabase, names: dict[str, str]
) -> None:
    for name, value in {
        "GBA_ADMIN_DATABASE_URL": test_database.admin_dsn,
        "GBA_DATABASE_NAME": names["database"],
        "GBA_OWNER_ROLE": names["owner"],
        "GBA_OWNER_PASSWORD": secrets.token_urlsafe(24),
        "GBA_APP_ROLE": names["app"],
        "GBA_APP_PASSWORD": secrets.token_urlsafe(24),
    }.items():
        monkeypatch.setenv(name, value)


def test_cli_bootstrap_creates_a_separate_writer_login(
    test_database: ProvisionedDatabase,
    scratch: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _cli_environment(monkeypatch, test_database, scratch)
    password = secrets.token_urlsafe(24)
    monkeypatch.setenv("GBA_RECEIPT_WRITER_ROLE", scratch["writer"])
    monkeypatch.setenv("GBA_RECEIPT_WRITER_PASSWORD", password)
    cli.main(["bootstrap"])
    printed = capsys.readouterr().out
    assert scratch["writer"] in printed
    assert password not in printed
    with psycopg.connect(test_database.admin_dsn, autocommit=True) as admin:
        assert _is_member(admin, scratch["writer"], "gba_receipt_writer")
        assert not _is_member(admin, scratch["writer"], "gba_runtime")
        assert not _is_member(admin, scratch["writer"], scratch["owner"])
        assert not _is_member(admin, scratch["app"], "gba_receipt_writer")
    writer = make_conninfo(
        test_database.admin_dsn,
        dbname=scratch["database"],
        user=scratch["writer"],
        password=password,
    )
    with psycopg.connect(writer) as conn:
        row = conn.execute("select current_user").fetchone()
    assert row == (scratch["writer"],)


def test_cli_bootstrap_without_writer_variables_creates_no_writer(
    test_database: ProvisionedDatabase,
    scratch: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _cli_environment(monkeypatch, test_database, scratch)
    monkeypatch.delenv("GBA_RECEIPT_WRITER_ROLE", raising=False)
    monkeypatch.delenv("GBA_RECEIPT_WRITER_PASSWORD", raising=False)
    cli.main(["bootstrap"])
    with psycopg.connect(test_database.admin_dsn, autocommit=True) as admin:
        row = admin.execute(
            "select count(*) from pg_catalog.pg_roles where rolname = %s", (scratch["writer"],)
        ).fetchone()
    assert row == (0,)


def test_migrate_refuses_before_bootstrap_created_the_writer_group(
    test_database: ProvisionedDatabase, scratch: dict[str, str]
) -> None:
    owner = str(conninfo_to_dict(test_database.owner_dsn)["user"])
    target = make_conninfo(test_database.owner_dsn, dbname=scratch["database"])
    with psycopg.connect(test_database.admin_dsn, autocommit=True) as admin:
        admin.execute(
            sql.SQL("create database {} owner {} encoding 'UTF8' template template0").format(
                sql.Identifier(scratch["database"]), sql.Identifier(owner)
            )
        )
        admin.execute(
            sql.SQL("alter role gba_receipt_writer rename to {}").format(sql.Identifier(HIDDEN))
        )
        try:
            with pytest.raises(MigrationError, match="gba-db bootstrap"):
                apply_migrations(target)
        finally:
            admin.execute(
                sql.SQL("alter role {} rename to gba_receipt_writer").format(sql.Identifier(HIDDEN))
            )
    with psycopg.connect(target, autocommit=True) as conn:
        row = conn.execute(
            "select pg_catalog.to_regclass('public.gba_schema_migrations'),"
            "pg_catalog.to_regnamespace('gba')"
        ).fetchone()
    assert row == (None, None)
    applied = apply_migrations(target)
    assert [m.version for m in applied] == [m.version for m in load_migrations()]
