"""Nonempty I3 data upgrades to the I4 branch setting without rewriting facts."""

import psycopg
import pytest

from gorgona_booking.db.migrate import apply_migrations, load_migrations
from gorgona_booking.db.pool import create_runtime_pool, tenant_transaction
from gorgona_booking.db.workforce_guard import WORKFORCE_TABLES, assert_workforce_ready
from tests.integration.booking_support import at
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
previous_setting_database = previous_admission_database
__all__ = ["changes", "client", "idp", "manager_a", "times", "workforce"]


async def test_nonempty_0034_upgrade_preserves_every_fact_and_prior_checksum(
    times: Times, test_database: ProvisionedDatabase, previous_setting_database: ProvisionedDatabase
) -> None:
    shift = await times.changes.shift(times.changes.left_profile)
    proposal = await times.changes.propose("handover", shift)
    assert proposal.status_code == 200, proposal.text
    started = await times.start()
    assert started.status_code == 200, started.text
    closed = await times.command(dict(started.json()), "clock_out", at=at(11).isoformat())
    assert closed.status_code == 200, closed.text
    target = previous_setting_database
    apply_migrations(target.owner_dsn, load_migrations()[:34])
    copy_fixture_data(test_database, target)
    before = snapshot(target)
    # The old schema really holds I2 and I3 facts before the upgrade.
    assert before["time_entry_revisions"][0] >= 2
    assert before["shift_change_requests"][0] >= 1
    with psycopg.connect(target.owner_dsn) as conn:
        prior: dict[int, str] = dict(
            conn.execute("select version,checksum from public.gba_schema_migrations")
        )
    applied = apply_migrations(target.owner_dsn)
    assert [migration.version for migration in applied] == [35]
    assert apply_migrations(target.owner_dsn) == []
    after = snapshot(target)
    assert {table: after[table] for table in before} == before
    assert WORKFORCE_TABLES[14:] == ("work_location_setting_versions",)
    assert set(after) - set(before) == set(WORKFORCE_TABLES[14:])
    assert all(after[table][0] == 0 for table in WORKFORCE_TABLES[14:])
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
    finally:
        await pool.close()
