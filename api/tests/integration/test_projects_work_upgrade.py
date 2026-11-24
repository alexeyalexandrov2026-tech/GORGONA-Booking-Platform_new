"""Upgrade test: apply 0135_projects_stages_tasks_and_files.sql to a populated 0134 database."""

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
    "project_stages",
    "project_tasks",
    "project_task_dependencies",
    "project_matter_files",
)


@pytest.mark.anyio
async def test_apply_projects_work_0135_to_populated_0134(
    world: BookingWorld,
    manager_a: FakeUser,
    test_database: ProvisionedDatabase,
    previous_r7a_database: ProvisionedDatabase,
) -> None:
    migrations = load_migrations()
    prior = previous_r7a_database
    assert apply_migrations(prior.owner_dsn, migrations[:134])[-1].version == 134
    copy_fixture_data(test_database, prior)

    before = snapshot(prior)
    prior_checksums = checksums(prior)
    assert len(prior_checksums) == 134

    assert [m.version for m in apply_migrations(prior.owner_dsn, migrations[:135])] == [135]
    after = snapshot(prior)
    for table in _NEW_TABLES:
        assert after.pop(table)[0] == 0
    assert after == before
    assert checksums(prior)[:134] == prior_checksums
    assert apply_migrations(prior.owner_dsn, migrations[:135]) == []

    # Verify module gate rejects direct runtime insert when projects is not enabled
    with psycopg.connect(prior.app_dsn) as conn:
        conn.execute("select set_config('gba.tenant_id', %s, true)", (str(world.a.tenant_id),))
        conn.execute("select set_config('gba.user_id', %s, true)", (str(manager_a.user_id),))
        with pytest.raises(psycopg.DatabaseError, match="the projects module is disabled"):
            conn.execute(
                "insert into gba.project_stages "
                "(tenant_id, id, location_id, matter_id, stage_no, title, status, "
                "revision, recorded_by) "
                "values (%s, %s, %s, %s, 1, 'Upgraded Stage', 'open', 1, %s)",
                (world.a.tenant_id, uuid7(), world.a.location_id, uuid7(), manager_a.user_id),
            )
    assert snapshot(prior)["project_stages"][0] == 0
