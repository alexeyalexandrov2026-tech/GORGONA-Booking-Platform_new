"""Upgrade test: apply 0136_projects_time_and_recurring.sql to a populated 0135 database."""

from uuid import uuid7

import psycopg
import pytest

from gorgona_booking.db.migrate import apply_migrations, load_migrations
from tests.integration.booking_support import BookingWorld
from tests.integration.conftest import ProvisionedDatabase
from tests.integration.seed import FakeUser
from tests.integration.test_h3_upgrade import copy_fixture_data, snapshot
from tests.integration.test_property_move_out_upgrade import (
    client,
    idp,
    manager_a,
    previous_r7a_database,
    previous_receipt_database,
)
from tests.integration.test_provider_routing_upgrade import checksums

__all__ = ["client", "idp", "manager_a", "previous_r7a_database", "previous_receipt_database"]

_NEW_TABLES = (
    "project_time_entries",
    "project_time_entry_revisions",
    "project_recurring_schedules",
    "project_recurring_runs",
)


@pytest.mark.anyio
async def test_apply_projects_time_0136_to_populated_0135(
    world: BookingWorld,
    manager_a: FakeUser,
    test_database: ProvisionedDatabase,
    previous_r7a_database: ProvisionedDatabase,
) -> None:
    migrations = load_migrations()
    prior = previous_r7a_database
    assert apply_migrations(prior.owner_dsn, migrations[:135])[-1].version == 135
    copy_fixture_data(test_database, prior)

    before = snapshot(prior)
    prior_checksums = checksums(prior)
    assert len(prior_checksums) == 135

    assert [m.version for m in apply_migrations(prior.owner_dsn, migrations[:136])] == [136]
    after = snapshot(prior)
    for table in _NEW_TABLES:
        assert after.pop(table)[0] == 0
    assert after == before
    assert checksums(prior)[:135] == prior_checksums
    assert apply_migrations(prior.owner_dsn, migrations[:136]) == []

    # Verify module gate rejects direct runtime insert when projects is not enabled
    with psycopg.connect(prior.app_dsn) as conn:
        conn.execute("select set_config('gba.tenant_id', %s, true)", (str(world.a.tenant_id),))
        conn.execute("select set_config('gba.user_id', %s, true)", (str(manager_a.user_id),))
        with pytest.raises(psycopg.DatabaseError, match="the projects module is disabled"):
            conn.execute(
                "insert into gba.project_time_entries "
                "(tenant_id, id, location_id, matter_id, staff_user_id, work_date, "
                "duration_minutes, hourly_rate_minor, currency, billable, amount_minor, "
                "description, status, revision, recorded_by) "
                "values (%s, %s, %s, %s, %s, '2026-11-21', 30, 10000, 'USD', true, 5000, "
                "'Upgrade check', 'draft', 1, %s)",
                (
                    world.a.tenant_id,
                    uuid7(),
                    world.a.location_id,
                    uuid7(),
                    manager_a.user_id,
                    manager_a.user_id,
                ),
            )
    assert snapshot(prior)["project_time_entries"][0] == 0
