"""Upgrade test: apply 0147_special_assets_field_ops.sql to a populated 0146 DB."""

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
    "managed_assets",
    "asset_inspections",
    "asset_work_orders",
    "asset_safety_incidents",
)


@pytest.mark.anyio
async def test_apply_assets_0147_to_populated_0146(
    world: BookingWorld,
    manager_a: FakeUser,
    test_database: ProvisionedDatabase,
    previous_r7a_database: ProvisionedDatabase,
) -> None:
    migrations = load_migrations()
    prior = previous_r7a_database
    assert apply_migrations(prior.owner_dsn, migrations[:146])[-1].version == 146
    copy_fixture_data(test_database, prior)

    before = snapshot(prior)
    prior_checksums = checksums(prior)
    assert len(prior_checksums) == 146

    assert [m.version for m in apply_migrations(prior.owner_dsn, migrations[:147])] == [147]
    after = snapshot(prior)
    for table in _NEW_TABLES:
        assert after.pop(table)[0] == 0
    assert after == before
    assert checksums(prior)[:146] == prior_checksums
    assert apply_migrations(prior.owner_dsn, migrations[:147]) == []

    # Verify module gate rejects direct runtime insert when assets is disabled
    with psycopg.connect(prior.app_dsn) as conn:
        conn.execute("select set_config('gba.tenant_id', %s, true)", (str(world.a.tenant_id),))
        conn.execute("select set_config('gba.user_id', %s, true)", (str(manager_a.user_id),))
        with pytest.raises(psycopg.DatabaseError, match="the assets module is disabled"):
            conn.execute(
                "insert into gba.managed_assets "
                "(id, tenant_id, location_id, asset_domain, code, name, recorded_by) "
                "values (%s, %s, %s, 'facility_system', 'GATE_1', 'Gate', %s)",
                (uuid7(), world.a.tenant_id, world.a.location_id, manager_a.user_id),
            )
    assert snapshot(prior)["managed_assets"][0] == 0
