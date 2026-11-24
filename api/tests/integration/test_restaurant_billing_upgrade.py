"""Upgrade test: apply 0133_restaurant_split_billing_and_refunds.sql to populated 0132 DB."""

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
    "restaurant_check_splits",
    "restaurant_check_split_shares",
    "restaurant_check_split_share_lines",
    "restaurant_check_bills",
    "restaurant_check_refunds",
)


@pytest.mark.anyio
async def test_apply_restaurant_billing_0133_to_populated_0132(
    world: BookingWorld,
    manager_a: FakeUser,
    test_database: ProvisionedDatabase,
    previous_r7a_database: ProvisionedDatabase,
) -> None:
    migrations = load_migrations()
    prior = previous_r7a_database
    assert apply_migrations(prior.owner_dsn, migrations[:132])[-1].version == 132
    copy_fixture_data(test_database, prior)

    before = snapshot(prior)
    prior_checksums = checksums(prior)
    assert len(prior_checksums) == 132

    assert [m.version for m in apply_migrations(prior.owner_dsn, migrations[:133])] == [133]
    after = snapshot(prior)
    for table in _NEW_TABLES:
        assert after.pop(table)[0] == 0
    assert after == before
    assert checksums(prior)[:132] == prior_checksums
    assert apply_migrations(prior.owner_dsn, migrations[:133]) == []

    # Verify module gate rejects direct runtime insert when restaurant is not enabled
    with psycopg.connect(prior.app_dsn) as conn:
        conn.execute("select set_config('gba.tenant_id', %s, true)", (str(world.a.tenant_id),))
        with pytest.raises(psycopg.DatabaseError, match="the restaurant module is disabled"):
            conn.execute(
                "insert into gba.restaurant_check_splits "
                "(tenant_id, check_id, location_id, split_mode, share_count, "
                "total_minor, recorded_by) "
                "values (%s, %s, %s, 'by_amounts', 1, 100, %s)",
                (world.a.tenant_id, uuid7(), world.a.location_id, manager_a.user_id),
            )
    assert snapshot(prior)["restaurant_check_splits"][0] == 0
