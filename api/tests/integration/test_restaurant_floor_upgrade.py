"""Upgrade test: apply 0130_restaurant_floor_and_tables.sql to a populated 0129 database."""

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
    "restaurant_areas",
    "restaurant_area_revisions",
    "restaurant_tables",
    "restaurant_table_reservations",
    "restaurant_table_reservation_events",
)


@pytest.mark.anyio
async def test_apply_restaurant_floor_0130_to_populated_0129(
    world: BookingWorld,
    manager_a: FakeUser,
    test_database: ProvisionedDatabase,
    previous_r7a_database: ProvisionedDatabase,
) -> None:
    migrations = load_migrations()
    prior = previous_r7a_database
    assert apply_migrations(prior.owner_dsn, migrations[:129])[-1].version == 129
    copy_fixture_data(test_database, prior)

    before = snapshot(prior)
    prior_checksums = checksums(prior)
    assert len(prior_checksums) == 129

    assert [m.version for m in apply_migrations(prior.owner_dsn, migrations[:130])] == [130]
    after = snapshot(prior)
    for table in _NEW_TABLES:
        assert after.pop(table)[0] == 0
    assert after == before
    assert checksums(prior)[:129] == prior_checksums
    assert apply_migrations(prior.owner_dsn, migrations[:130]) == []

    # Verify module gate rejects direct runtime insert when restaurant is not enabled
    area_id = uuid7()
    with psycopg.connect(prior.app_dsn) as conn:
        conn.execute("select set_config('gba.tenant_id', %s, true)", (str(world.a.tenant_id),))
        with pytest.raises(psycopg.DatabaseError, match="the restaurant module is disabled"):
            conn.execute(
                "insert into gba.restaurant_areas "
                "(tenant_id, id, location_id, name, service_style, "
                "revision, is_active, recorded_by) "
                "values (%s, %s, %s, 'Upgraded Dining', 'dining', 1, true, %s)",
                (world.a.tenant_id, area_id, world.a.location_id, manager_a.user_id),
            )
    assert snapshot(prior)["restaurant_areas"][0] == 0
