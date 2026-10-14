"""Nonempty I4 data upgrades to the inventory tables of J1 and J2 without rewriting facts."""

import psycopg
import pytest

from gorgona_booking.db.inventory_guard import INVENTORY_TABLES, assert_inventory_ready
from gorgona_booking.db.migrate import apply_migrations, load_migrations
from gorgona_booking.db.pool import create_runtime_pool, tenant_transaction
from gorgona_booking.db.workforce_guard import assert_workforce_ready
from tests.integration.conftest import ProvisionedDatabase
from tests.integration.test_h3_upgrade import copy_fixture_data, snapshot
from tests.integration.test_provider_admission_upgrade import previous_admission_database
from tests.integration.test_timesheets import (
    Times,
    changes,
    client,
    idp,
    manager_a,
    times,
    workforce,
)

pytestmark = pytest.mark.anyio
previous_inventory_database = previous_admission_database
__all__ = ["changes", "client", "idp", "manager_a", "times", "workforce"]


async def test_nonempty_0035_upgrade_preserves_every_fact_and_prior_checksum(
    times: Times,
    test_database: ProvisionedDatabase,
    previous_inventory_database: ProvisionedDatabase,
) -> None:
    started = await times.start()
    assert started.status_code == 200, started.text
    target = previous_inventory_database
    apply_migrations(target.owner_dsn, load_migrations()[:35])
    copy_fixture_data(test_database, target)
    before = snapshot(target)
    # The old schema really holds workforce facts before the upgrade.
    assert before["time_entry_revisions"][0] >= 1
    with psycopg.connect(target.owner_dsn) as conn:
        prior: dict[int, str] = dict(
            conn.execute("select version,checksum from public.gba_schema_migrations")
        )
    inventory_migrations = load_migrations()[:41]
    applied = apply_migrations(target.owner_dsn, inventory_migrations)
    assert [migration.version for migration in applied] == [36, 37, 38, 39, 40, 41]
    assert apply_migrations(target.owner_dsn, inventory_migrations) == []
    after = snapshot(target)
    assert {table: after[table] for table in before} == before
    assert set(after) - set(before) == set(INVENTORY_TABLES)
    assert all(after[table][0] == 0 for table in INVENTORY_TABLES)
    with psycopg.connect(target.owner_dsn) as conn:
        current: dict[int, str] = dict(
            conn.execute("select version,checksum from public.gba_schema_migrations")
        )
    assert {number: current[number] for number in prior} == prior
    pool = create_runtime_pool(target.app_dsn, min_size=1, max_size=2)
    await pool.open()
    try:
        async with tenant_transaction(pool, times.changes.workforce.world.a.tenant_id) as conn:
            await assert_workforce_ready(conn)
            await assert_inventory_ready(conn)
    finally:
        await pool.close()
