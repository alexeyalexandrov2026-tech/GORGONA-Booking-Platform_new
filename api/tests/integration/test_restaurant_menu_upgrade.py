"""Upgrade test: apply 0131_restaurant_menu_and_recipes.sql to a populated 0130 database."""

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
    "restaurant_menu_items",
    "restaurant_menu_item_revisions",
    "restaurant_modifier_groups",
    "restaurant_modifier_options",
    "restaurant_menu_item_modifier_groups",
    "restaurant_recipes",
    "restaurant_recipe_lines",
)


@pytest.mark.anyio
async def test_apply_restaurant_menu_0131_to_populated_0130(
    world: BookingWorld,
    manager_a: FakeUser,
    test_database: ProvisionedDatabase,
    previous_r7a_database: ProvisionedDatabase,
) -> None:
    migrations = load_migrations()
    prior = previous_r7a_database
    assert apply_migrations(prior.owner_dsn, migrations[:130])[-1].version == 130
    copy_fixture_data(test_database, prior)

    before = snapshot(prior)
    prior_checksums = checksums(prior)
    assert len(prior_checksums) == 130

    assert [m.version for m in apply_migrations(prior.owner_dsn, migrations[:131])] == [131]
    after = snapshot(prior)
    for table in _NEW_TABLES:
        assert after.pop(table)[0] == 0
    assert after == before
    assert checksums(prior)[:130] == prior_checksums
    assert apply_migrations(prior.owner_dsn, migrations[:131]) == []

    # Verify module gate rejects direct runtime insert when restaurant is not enabled
    item_id = uuid7()
    with psycopg.connect(prior.app_dsn) as conn:
        conn.execute("select set_config('gba.tenant_id', %s, true)", (str(world.a.tenant_id),))
        with pytest.raises(psycopg.DatabaseError, match="the restaurant module is disabled"):
            conn.execute(
                "insert into gba.restaurant_menu_items "
                "(tenant_id, id, location_id, code, name, category, kitchen_station, "
                "price_minor, currency, revision, is_active, recorded_by) "
                "values (%s, %s, %s, 'UPG_01', 'Upgraded Dish', 'Mains', 'hot', "
                "1200, 'USD', 1, true, %s)",
                (world.a.tenant_id, item_id, world.a.location_id, manager_a.user_id),
            )
    assert snapshot(prior)["restaurant_menu_items"][0] == 0
