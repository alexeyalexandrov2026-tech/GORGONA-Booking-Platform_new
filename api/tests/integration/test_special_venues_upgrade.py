"""Upgrade test: apply 0145_special_hospitality_events_education_fitness.sql to 0144 DB."""

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
    "special_programs",
    "special_enrollments",
    "special_rooms",
    "special_stays",
    "special_events",
    "special_tickets",
)


@pytest.mark.anyio
async def test_apply_special_venues_0145_to_populated_0144(
    world: BookingWorld,
    manager_a: FakeUser,
    test_database: ProvisionedDatabase,
    previous_r7a_database: ProvisionedDatabase,
) -> None:
    migrations = load_migrations()
    prior = previous_r7a_database
    assert apply_migrations(prior.owner_dsn, migrations[:144])[-1].version == 144
    copy_fixture_data(test_database, prior)

    before = snapshot(prior)
    prior_checksums = checksums(prior)
    assert len(prior_checksums) == 144

    assert [m.version for m in apply_migrations(prior.owner_dsn, migrations[:145])] == [145]
    after = snapshot(prior)
    for table in _NEW_TABLES:
        assert after.pop(table)[0] == 0
    assert after == before
    assert checksums(prior)[:144] == prior_checksums
    assert apply_migrations(prior.owner_dsn, migrations[:145]) == []

    # Verify module gate rejects direct runtime insert when hospitality_events is disabled
    with psycopg.connect(prior.app_dsn) as conn:
        conn.execute("select set_config('gba.tenant_id', %s, true)", (str(world.a.tenant_id),))
        conn.execute("select set_config('gba.user_id', %s, true)", (str(manager_a.user_id),))
        with pytest.raises(
            psycopg.DatabaseError, match="the hospitality_events module is disabled"
        ):
            conn.execute(
                "insert into gba.special_rooms "
                "(id, tenant_id, location_id, room_number, room_type, currency, recorded_by) "
                "values (%s, %s, %s, '101', 'Std', 'USD', %s)",
                (uuid7(), world.a.tenant_id, world.a.location_id, manager_a.user_id),
            )
    assert snapshot(prior)["special_rooms"][0] == 0
