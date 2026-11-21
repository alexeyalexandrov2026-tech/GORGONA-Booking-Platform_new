"""Upgrade test: apply 0140_supply_trade_and_3pl_orders.sql to a populated 0139 database."""

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
    "supply_price_lists",
    "supply_price_list_items",
    "supply_trade_orders",
    "supply_trade_order_lines",
    "supply_order_shipments",
    "supply_order_returns",
)


@pytest.mark.anyio
async def test_apply_supply_trade_0140_to_populated_0139(
    world: BookingWorld,
    manager_a: FakeUser,
    test_database: ProvisionedDatabase,
    previous_r7a_database: ProvisionedDatabase,
) -> None:
    migrations = load_migrations()
    prior = previous_r7a_database
    assert apply_migrations(prior.owner_dsn, migrations[:139])[-1].version == 139
    copy_fixture_data(test_database, prior)

    before = snapshot(prior)
    prior_checksums = checksums(prior)
    assert len(prior_checksums) == 139

    assert [m.version for m in apply_migrations(prior.owner_dsn, migrations[:140])] == [140]
    after = snapshot(prior)
    for table in _NEW_TABLES:
        assert after.pop(table)[0] == 0
    assert after == before
    assert checksums(prior)[:139] == prior_checksums
    assert apply_migrations(prior.owner_dsn, migrations[:140]) == []

    # Verify module gate rejects direct runtime insert when supply is not enabled
    with psycopg.connect(prior.app_dsn) as conn:
        conn.execute("select set_config('gba.tenant_id', %s, true)", (str(world.a.tenant_id),))
        conn.execute("select set_config('gba.user_id', %s, true)", (str(manager_a.user_id),))
        with pytest.raises(psycopg.DatabaseError, match="the supply module is disabled"):
            conn.execute(
                "insert into gba.supply_price_lists "
                "(id, tenant_id, location_id, code, title, channel, currency, recorded_by) "
                "values (%s, %s, %s, 'PL_GATE', 'Gate Test', 'wholesale', 'USD', %s)",
                (uuid7(), world.a.tenant_id, world.a.location_id, manager_a.user_id),
            )
    assert snapshot(prior)["supply_price_lists"][0] == 0
