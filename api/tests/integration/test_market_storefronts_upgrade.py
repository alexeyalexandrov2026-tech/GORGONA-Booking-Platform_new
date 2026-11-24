"""Upgrade test: apply 0141_market_storefronts_and_publishing.sql to a populated 0140 database."""

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
    "market_storefronts",
    "market_listings",
    "marketplaces",
    "marketplace_seller_connections",
)


@pytest.mark.anyio
async def test_apply_market_storefronts_0141_to_populated_0140(
    world: BookingWorld,
    manager_a: FakeUser,
    test_database: ProvisionedDatabase,
    previous_r7a_database: ProvisionedDatabase,
) -> None:
    migrations = load_migrations()
    prior = previous_r7a_database
    assert apply_migrations(prior.owner_dsn, migrations[:140])[-1].version == 140
    copy_fixture_data(test_database, prior)

    before = snapshot(prior)
    prior_checksums = checksums(prior)
    assert len(prior_checksums) == 140

    assert [m.version for m in apply_migrations(prior.owner_dsn, migrations[:141])] == [141]
    after = snapshot(prior)
    for table in _NEW_TABLES:
        assert after.pop(table)[0] == 0
    assert after == before
    assert checksums(prior)[:140] == prior_checksums
    assert apply_migrations(prior.owner_dsn, migrations[:141]) == []

    # Verify module gate rejects direct runtime insert when storefronts is not enabled
    with psycopg.connect(prior.app_dsn) as conn:
        conn.execute("select set_config('gba.tenant_id', %s, true)", (str(world.a.tenant_id),))
        conn.execute("select set_config('gba.user_id', %s, true)", (str(manager_a.user_id),))
        with pytest.raises(psycopg.DatabaseError, match="the storefronts module is disabled"):
            conn.execute(
                "insert into gba.marketplaces "
                "(id, tenant_id, location_id, slug, title, recorded_by) "
                "values (%s, %s, %s, 'gate-mp', 'Gate Test', %s)",
                (uuid7(), world.a.tenant_id, world.a.location_id, manager_a.user_id),
            )
    assert snapshot(prior)["marketplaces"][0] == 0
