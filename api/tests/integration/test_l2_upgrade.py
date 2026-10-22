"""Forward 0066 -> 0067 (L2a): every booking and its occupancy stay; one resource may hold
several intervals of one booking; the mirror matches the interval too."""

import psycopg
import pytest

from gorgona_booking.booking.service import BookingService
from gorgona_booking.db.migrate import apply_migrations, load_migrations
from gorgona_booking.db.pool import RuntimePool
from tests.integration import test_provider_receipt_upgrade as shared
from tests.integration.booking_support import BookingWorld, at
from tests.integration.conftest import ProvisionedDatabase
from tests.integration.test_h3_upgrade import copy_fixture_data, snapshot
from tests.integration.test_provider_routing_upgrade import checksums

pytestmark = pytest.mark.anyio
previous_receipt_database = shared.previous_receipt_database


async def test_nonempty_0066_upgrades_keeping_every_booking(
    world: BookingWorld,
    app_pool: RuntimePool,
    test_database: ProvisionedDatabase,
    previous_receipt_database: ProvisionedDatabase,
) -> None:
    service = BookingService(app_pool)
    confirmed = await service.create_confirmed_booking(
        world.a.tenant_id, world.request(at(10)), actor="test:l2-upgrade", idempotency_key=None
    )
    await service.cancel(world.a.tenant_id, confirmed.booking_id, actor="test:l2-upgrade")
    await service.create_hold(
        world.a.tenant_id, world.request(at(12)), actor="test:l2-upgrade", idempotency_key=None
    )
    target = previous_receipt_database
    apply_migrations(target.owner_dsn, load_migrations()[:66])
    copy_fixture_data(test_database, target)
    before = snapshot(target)
    assert before["booking_allocations"][0] >= 2
    applied = checksums(target)
    upgrade = apply_migrations(target.owner_dsn, load_migrations()[:67])
    assert [m.version for m in upgrade] == [67]
    assert snapshot(target) == before
    with psycopg.connect(target.admin_dsn) as conn:
        names = {
            row[0]
            for row in conn.execute(
                "select conname from pg_catalog.pg_constraint where conrelid in "
                "('gba.booking_allocations'::regclass, 'gba.resource_allocations'::regclass) "
                "and contype='u'"
            )
        }
        mirror = conn.execute(
            "select prosrc like '%r.during = new.during%' from pg_catalog.pg_proc "
            "where proname='mirror_booking_allocation'"
        ).fetchone()
    assert names == {
        "booking_allocations_one_per_interval",
        "resource_allocations_one_per_interval",
    }
    assert mirror == (True,)
    assert checksums(target)[:66] == applied
    assert apply_migrations(target.owner_dsn, load_migrations()[:67]) == []
