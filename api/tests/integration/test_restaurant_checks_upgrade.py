"""Upgrade test: apply 0132_restaurant_checks_and_kitchen.sql to a populated 0131 database."""

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
    "restaurant_checks",
    "restaurant_kitchen_tickets",
    "restaurant_kitchen_ticket_events",
    "restaurant_check_lines",
    "restaurant_check_line_modifiers",
    "restaurant_check_consumptions",
    "restaurant_check_consumption_lines",
)


@pytest.mark.anyio
async def test_apply_restaurant_checks_0132_to_populated_0131(
    world: BookingWorld,
    manager_a: FakeUser,
    test_database: ProvisionedDatabase,
    previous_r7a_database: ProvisionedDatabase,
) -> None:
    migrations = load_migrations()
    prior = previous_r7a_database
    assert apply_migrations(prior.owner_dsn, migrations[:131])[-1].version == 131
    copy_fixture_data(test_database, prior)

    before = snapshot(prior)
    prior_checksums = checksums(prior)
    assert len(prior_checksums) == 131

    assert [m.version for m in apply_migrations(prior.owner_dsn, migrations[:132])] == [132]
    after = snapshot(prior)
    for table in _NEW_TABLES:
        assert after.pop(table)[0] == 0
    assert after == before
    assert checksums(prior)[:131] == prior_checksums
    assert apply_migrations(prior.owner_dsn, migrations[:132]) == []

    # Verify module gate rejects direct runtime insert when restaurant is not enabled
    check_id = uuid7()
    with psycopg.connect(prior.app_dsn) as conn:
        conn.execute("select set_config('gba.tenant_id', %s, true)", (str(world.a.tenant_id),))
        with pytest.raises(psycopg.DatabaseError, match="the restaurant module is disabled"):
            conn.execute(
                "insert into gba.restaurant_checks "
                "(tenant_id, id, location_id, service_mode, currency, status, "
                "subtotal_minor, revision, opened_by, recorded_by) "
                "values (%s, %s, %s, 'takeout', 'USD', 'open', 0, 1, %s, %s)",
                (
                    world.a.tenant_id,
                    check_id,
                    world.a.location_id,
                    manager_a.user_id,
                    manager_a.user_id,
                ),
            )
    assert snapshot(prior)["restaurant_checks"][0] == 0
