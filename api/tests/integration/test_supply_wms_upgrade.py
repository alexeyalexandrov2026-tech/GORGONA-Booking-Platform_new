"""Upgrade test: apply 0138_supply_wms_owners_and_lots.sql to a populated 0137 database."""

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
    "supply_goods_owners",
    "supply_warehouse_bins",
    "supply_lots",
    "supply_lot_balances",
    "supply_serial_units",
    "supply_wms_movements",
)


@pytest.mark.anyio
async def test_apply_supply_wms_0138_to_populated_0137(
    world: BookingWorld,
    manager_a: FakeUser,
    test_database: ProvisionedDatabase,
    previous_r7a_database: ProvisionedDatabase,
) -> None:
    migrations = load_migrations()
    prior = previous_r7a_database
    assert apply_migrations(prior.owner_dsn, migrations[:137])[-1].version == 137
    copy_fixture_data(test_database, prior)

    before = snapshot(prior)
    prior_checksums = checksums(prior)
    assert len(prior_checksums) == 137

    assert [m.version for m in apply_migrations(prior.owner_dsn, migrations[:138])] == [138]
    after = snapshot(prior)
    for table in _NEW_TABLES:
        assert after.pop(table)[0] == 0
    assert after == before
    assert checksums(prior)[:137] == prior_checksums
    assert apply_migrations(prior.owner_dsn, migrations[:138]) == []

    # Verify module gate rejects direct runtime insert when supply is not enabled
    with psycopg.connect(prior.app_dsn) as conn:
        conn.execute("select set_config('gba.tenant_id', %s, true)", (str(world.a.tenant_id),))
        conn.execute("select set_config('gba.user_id', %s, true)", (str(manager_a.user_id),))
        with pytest.raises(psycopg.DatabaseError, match="the supply module is disabled"):
            conn.execute(
                "insert into gba.supply_goods_owners "
                "(tenant_id, id, location_id, code, display_name, owner_kind, legal_entity_id, "
                "counterparty_id, is_active, revision, recorded_by) "
                "values (%s, %s, %s, 'OWN1', 'Owner 1', 'company_entity', %s, null, true, 1, %s)",
                (world.a.tenant_id, uuid7(), world.a.location_id, uuid7(), manager_a.user_id),
            )
    assert snapshot(prior)["supply_goods_owners"][0] == 0
