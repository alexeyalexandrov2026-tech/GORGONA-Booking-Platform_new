"""Upgrade test: apply 0134_projects_matters_and_acl.sql to a populated 0133 database."""

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
    "project_matters",
    "project_matter_members",
    "project_matter_revisions",
    "project_conflict_checks",
)


@pytest.mark.anyio
async def test_apply_projects_matters_0134_to_populated_0133(
    world: BookingWorld,
    manager_a: FakeUser,
    test_database: ProvisionedDatabase,
    previous_r7a_database: ProvisionedDatabase,
) -> None:
    migrations = load_migrations()
    prior = previous_r7a_database
    assert apply_migrations(prior.owner_dsn, migrations[:133])[-1].version == 133
    copy_fixture_data(test_database, prior)

    before = snapshot(prior)
    prior_checksums = checksums(prior)
    assert len(prior_checksums) == 133

    assert [m.version for m in apply_migrations(prior.owner_dsn, migrations[:134])] == [134]
    after = snapshot(prior)
    for table in _NEW_TABLES:
        assert after.pop(table)[0] == 0
    assert after == before
    assert checksums(prior)[:133] == prior_checksums
    assert apply_migrations(prior.owner_dsn, migrations[:134]) == []

    # Verify module gate rejects direct runtime insert when projects is not enabled
    matter_id = uuid7()
    with psycopg.connect(prior.app_dsn) as conn:
        conn.execute("select set_config('gba.tenant_id', %s, true)", (str(world.a.tenant_id),))
        conn.execute("select set_config('gba.user_id', %s, true)", (str(manager_a.user_id),))
        with pytest.raises(psycopg.DatabaseError, match="the projects module is disabled"):
            conn.execute(
                "insert into gba.project_matters "
                "(tenant_id, id, location_id, code, title, kind, status, access_mode, "
                "client_counterparty_id, currency, opened_on, revision, created_by, recorded_by) "
                "values (%s, %s, %s, 'UPG-1', 'Upgrade Test', 'project', 'active', 'branch', "
                "%s, 'USD', '2026-11-21', 1, %s, %s)",
                (
                    world.a.tenant_id,
                    matter_id,
                    world.a.location_id,
                    uuid7(),
                    manager_a.user_id,
                    manager_a.user_id,
                ),
            )
    assert snapshot(prior)["project_matters"][0] == 0
