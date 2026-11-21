"""Upgrade test: apply 0139_supply_manufacturing_and_costing.sql to a populated 0138 database."""

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
    "supply_boms",
    "supply_bom_components",
    "supply_work_orders",
    "supply_work_order_issues",
    "supply_work_order_returns",
    "supply_work_order_qc",
    "supply_work_order_outputs",
)


@pytest.mark.anyio
async def test_apply_supply_manufacturing_0139_to_populated_0138(
    world: BookingWorld,
    manager_a: FakeUser,
    test_database: ProvisionedDatabase,
    previous_r7a_database: ProvisionedDatabase,
) -> None:
    migrations = load_migrations()
    prior = previous_r7a_database
    assert apply_migrations(prior.owner_dsn, migrations[:138])[-1].version == 138
    copy_fixture_data(test_database, prior)

    before = snapshot(prior)
    prior_checksums = checksums(prior)
    assert len(prior_checksums) == 138

    assert [m.version for m in apply_migrations(prior.owner_dsn, migrations[:139])] == [139]
    after = snapshot(prior)
    for table in _NEW_TABLES:
        assert after.pop(table)[0] == 0
    assert after == before
    assert checksums(prior)[:138] == prior_checksums
    assert apply_migrations(prior.owner_dsn, migrations[:139]) == []

    # Verify module gate rejects direct runtime insert when supply is not enabled
    with psycopg.connect(prior.app_dsn) as conn:
        conn.execute("select set_config('gba.tenant_id', %s, true)", (str(world.a.tenant_id),))
        conn.execute("select set_config('gba.user_id', %s, true)", (str(manager_a.user_id),))
        with pytest.raises(psycopg.DatabaseError, match="the supply module is disabled"):
            conn.execute(
                "insert into gba.supply_boms "
                "(tenant_id, id, location_id, code, title, output_item_id, "
                "batch_output_quantity, "
                "standard_labor_minor, standard_overhead_minor, is_active, revision, "
                "recorded_by) "
                "values (%s, %s, %s, 'BOM1', 'BOM 1', %s, 1, 0, 0, true, 1, %s)",
                (world.a.tenant_id, uuid7(), world.a.location_id, uuid7(), manager_a.user_id),
            )
    assert snapshot(prior)["supply_boms"][0] == 0
