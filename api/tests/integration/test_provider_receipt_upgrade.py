"""Forward-only 0043 -> 0044 upgrade of a nonempty synthetic snapshot."""

from collections.abc import Iterator
from uuid import uuid7

import psycopg
import pytest
from psycopg import sql
from psycopg.conninfo import conninfo_to_dict, make_conninfo

from gorgona_booking.db.migrate import apply_migrations, load_migrations
from tests.integration import test_ledger as shared
from tests.integration.conftest import ProvisionedDatabase
from tests.integration.test_h3_upgrade import copy_fixture_data, snapshot
from tests.integration.test_ledger import LedgerWorld

pytestmark = pytest.mark.anyio
client = shared.client
idp = shared.idp
manager_a = shared.manager_a
manager_b = shared.manager_b
enabled = shared.enabled


@pytest.fixture
def previous_receipt_database(test_database: ProvisionedDatabase) -> Iterator[ProvisionedDatabase]:
    name = "gba_k1b_upgrade_" + uuid7().hex
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
        apply_migrations(database.owner_dsn, load_migrations()[:43])
        yield database
    finally:
        with psycopg.connect(test_database.admin_dsn, autocommit=True) as admin:
            admin.execute(sql.SQL("drop database {} with (force)").format(sql.Identifier(name)))


async def test_nonempty_0043_upgrade_preserves_all_existing_facts_and_checksums(
    enabled: LedgerWorld,
    test_database: ProvisionedDatabase,
    previous_receipt_database: ProvisionedDatabase,
) -> None:
    posted = await enabled.post(enabled.entry())
    assert posted.status_code == 200, posted.text
    copy_fixture_data(test_database, previous_receipt_database)
    before = snapshot(previous_receipt_database)
    assert sum(count for count, _ in before.values()) > 0
    with psycopg.connect(previous_receipt_database.owner_dsn) as conn:
        checksums = conn.execute(
            "select version,checksum from public.gba_schema_migrations order by version"
        ).fetchall()
    assert len(checksums) == 43
    applied = apply_migrations(previous_receipt_database.owner_dsn, load_migrations()[:44])
    assert [m.version for m in applied] == [44]
    after = snapshot(previous_receipt_database)
    assert {name: after[name] for name in before} == before
    assert set(after) - set(before) == {
        "provider_receipt_connections",
        "provider_event_inbox",
        "provider_event_deliveries",
    }
    assert all(after[name][0] == 0 for name in set(after) - set(before))
    with psycopg.connect(previous_receipt_database.owner_dsn) as conn:
        assert (
            conn.execute(
                "select version,checksum from public.gba_schema_migrations "
                "where version<=43 order by version"
            ).fetchall()
            == checksums
        )
    assert apply_migrations(previous_receipt_database.owner_dsn, load_migrations()[:44]) == []
