"""A nonempty 0030 snapshot upgrades only forward, preserving all existing facts."""

from collections.abc import Iterator
from uuid import uuid7

import psycopg
import pytest
from psycopg import sql
from psycopg.conninfo import conninfo_to_dict, make_conninfo

from gorgona_booking.db.migrate import apply_migrations, load_migrations
from gorgona_booking.db.provider_admission_guard import ADMISSION_TABLES
from tests.integration import test_provider_admission as shared
from tests.integration.conftest import ProvisionedDatabase
from tests.integration.test_h3_upgrade import copy_fixture_data, snapshot
from tests.integration.test_provider_admission import AdmissionWorld

pytestmark = pytest.mark.anyio
client = shared.client
idp = shared.idp
manager_a = shared.manager_a
manager_b = shared.manager_b
enabled = shared.enabled
admission = shared.admission


@pytest.fixture
def previous_admission_database(
    test_database: ProvisionedDatabase,
) -> Iterator[ProvisionedDatabase]:
    name = "gba_h4_upgrade_" + uuid7().hex
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
        apply_migrations(database.owner_dsn, load_migrations()[:30])
        yield database
    finally:
        with psycopg.connect(test_database.admin_dsn, autocommit=True) as admin:
            admin.execute(sql.SQL("drop database {} with (force)").format(sql.Identifier(name)))


async def test_nonempty_0030_upgrade_keeps_all_rows_and_prior_checksums(
    admission: AdmissionWorld,
    test_database: ProvisionedDatabase,
    previous_admission_database: ProvisionedDatabase,
) -> None:
    # Real accepted G journal and domain/configuration rows, all fake fixture facts.
    posted = await admission.ledger.post(admission.ledger.entry())
    assert posted.status_code == 200, posted.text
    copy_fixture_data(test_database, previous_admission_database)
    before = snapshot(previous_admission_database)
    assert sum(count for count, _ in before.values()) > 0
    with psycopg.connect(previous_admission_database.owner_dsn) as owner:
        old: dict[int, str] = dict(
            owner.execute("select version,checksum from public.gba_schema_migrations")
        )
    applied = apply_migrations(previous_admission_database.owner_dsn)
    assert [migration.version for migration in applied] == [31]
    assert apply_migrations(previous_admission_database.owner_dsn) == []
    after = snapshot(previous_admission_database)
    assert {table: after[table] for table in before} == before
    assert set(after) - set(before) == set(ADMISSION_TABLES)
    assert all(after[table][0] == 0 for table in ADMISSION_TABLES)
    with psycopg.connect(previous_admission_database.owner_dsn) as owner:
        current: dict[int, str] = dict(
            owner.execute("select version,checksum from public.gba_schema_migrations")
        )
    assert {version: current[version] for version in old} == old
    assert current == {migration.version: migration.checksum for migration in load_migrations()}
