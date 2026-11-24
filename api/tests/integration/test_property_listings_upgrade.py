"""Apply 0113 to a populated 0112 database without changing existing facts."""

import pytest

from gorgona_booking.db.migrate import apply_migrations, load_migrations
from tests.integration.booking_support import BookingWorld
from tests.integration.conftest import ProvisionedDatabase
from tests.integration.test_h3_upgrade import copy_fixture_data, snapshot
from tests.integration.test_provider_routing_upgrade import checksums
from tests.integration.test_r7b_upgrade import previous_r7a_database, previous_receipt_database

__all__ = ["previous_r7a_database", "previous_receipt_database"]


@pytest.mark.anyio
async def test_apply_property_listings_to_nonempty_0112(
    world: BookingWorld,
    test_database: ProvisionedDatabase,
    previous_r7a_database: ProvisionedDatabase,
) -> None:
    migrations = load_migrations()
    dsn = previous_r7a_database.owner_dsn
    apply_migrations(dsn, migrations[:112])
    copy_fixture_data(test_database, previous_r7a_database)
    before = snapshot(previous_r7a_database)
    assert before["tenants"][0] >= 2
    prior_checksums = checksums(previous_r7a_database)
    assert len(prior_checksums) == 112

    assert [m.version for m in apply_migrations(dsn, migrations[:113])] == [113]
    after = snapshot(previous_r7a_database)
    added = {"property_listings", "property_listing_revisions"}
    assert {k: v for k, v in after.items() if k not in added} == before
    assert all(after[name][0] == 0 for name in added)
    assert checksums(previous_r7a_database)[:112] == prior_checksums
    assert apply_migrations(dsn, migrations[:113]) == []
