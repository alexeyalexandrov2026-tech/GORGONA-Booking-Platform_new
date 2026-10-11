"""Nonempty I1 data upgrades to I2 without rewriting any historical row."""

import psycopg
import pytest

from gorgona_booking.db.migrate import apply_migrations, load_migrations
from gorgona_booking.db.pool import create_runtime_pool, tenant_transaction
from gorgona_booking.db.workforce_guard import WORKFORCE_TABLES, assert_workforce_ready
from gorgona_booking.errors import DatabaseUnavailableError
from tests.integration.conftest import ProvisionedDatabase
from tests.integration.test_h3_upgrade import copy_fixture_data, snapshot
from tests.integration.test_provider_admission_upgrade import previous_admission_database
from tests.integration.test_shift_changes import Changes, changes, client, idp, manager_a, workforce

pytestmark = pytest.mark.anyio
previous_changes_database = previous_admission_database
__all__ = ["changes", "client", "idp", "manager_a", "workforce"]


async def test_nonempty_0032_upgrade_preserves_every_row_and_prior_checksum(
    changes: Changes,
    test_database: ProvisionedDatabase,
    previous_changes_database: ProvisionedDatabase,
) -> None:
    shift = await changes.shift(changes.left_profile)
    assert shift["assignment_id"]
    target = previous_changes_database
    apply_migrations(target.owner_dsn, load_migrations()[:32])
    copy_fixture_data(test_database, target)
    before = snapshot(target)
    with psycopg.connect(target.owner_dsn) as conn:
        prior: dict[int, str] = dict(
            conn.execute("select version,checksum from public.gba_schema_migrations")
        )
    i2_migrations = load_migrations()[:33]
    applied = apply_migrations(target.owner_dsn, i2_migrations)
    assert [m.version for m in applied] == [33]
    assert apply_migrations(target.owner_dsn, i2_migrations) == []
    after = snapshot(target)
    assert {table: after[table] for table in before} == before
    assert set(after) - set(before) == set(WORKFORCE_TABLES[8:11])
    with psycopg.connect(target.owner_dsn) as conn:
        current: dict[int, str] = dict(
            conn.execute("select version,checksum from public.gba_schema_migrations")
        )
    assert {number: current[number] for number in prior} == prior
    pool = create_runtime_pool(target.app_dsn, min_size=1, max_size=2)
    await pool.open()
    try:
        async with tenant_transaction(pool, changes.workforce.world.a.tenant_id) as conn:
            with pytest.raises(DatabaseUnavailableError):
                await assert_workforce_ready(conn)
    finally:
        await pool.close()
