"""A nonempty 0031 company upgrades forward with every prior fact/checksum preserved."""

import psycopg
import pytest

from gorgona_booking.db.migrate import apply_migrations, load_migrations
from gorgona_booking.db.pool import create_runtime_pool, tenant_transaction
from gorgona_booking.db.provisioning import owner_tenant_transaction
from gorgona_booking.db.schema_guard import assert_location_scope_ready
from gorgona_booking.db.workforce_guard import WORKFORCE_TABLES, assert_workforce_ready
from gorgona_booking.errors import DatabaseUnavailableError
from tests.integration.booking_support import at
from tests.integration.conftest import ProvisionedDatabase
from tests.integration.seed import seed_fake_catalog, seed_resource, seed_salon
from tests.integration.test_h3_upgrade import snapshot
from tests.integration.test_provider_admission_upgrade import previous_admission_database

pytestmark = pytest.mark.anyio
previous_workforce_database = previous_admission_database


async def test_nonempty_0031_upgrade_preserves_booking_occupancy_and_checksums(
    previous_workforce_database: ProvisionedDatabase,
) -> None:
    database = previous_workforce_database
    apply_migrations(database.owner_dsn, load_migrations()[:31])
    with psycopg.connect(database.owner_dsn, autocommit=True) as owner:
        salon = seed_salon(owner, "i1-upgrade")
        catalog = seed_fake_catalog(owner, salon)
        resource = seed_resource(owner, salon, "FAKE upgrade resource")
        with owner_tenant_transaction(owner, salon.tenant_id):
            booking = owner.execute(
                "insert into gba.bookings "
                "(tenant_id,location_id,variant_id,status,starts_at,ends_at,"
                "total_cents,currency,quote,created_by) "
                "values "
                "(%s,%s,%s,'CONFIRMED',%s,%s,5000,'USD','{}','test:i1-upgrade') "
                "returning id",
                (salon.tenant_id, salon.location_id, catalog.base_variant_id, at(10), at(11)),
            ).fetchone()
            assert booking is not None
            owner.execute(
                "insert into gba.booking_allocations "
                "(tenant_id,booking_id,booking_status,resource_id,during) "
                "values (%s,%s,'CONFIRMED',%s,tstzrange(%s,%s,'[)'))",
                (salon.tenant_id, booking[0], resource, at(10), at(11)),
            )
        old: dict[int, str] = dict(
            owner.execute("select version,checksum from public.gba_schema_migrations")
        )
    before = snapshot(database)
    i1_migrations = load_migrations()[:32]
    applied = apply_migrations(database.owner_dsn, i1_migrations)
    assert [m.version for m in applied] == [32]
    assert apply_migrations(database.owner_dsn, i1_migrations) == []
    after = snapshot(database)
    assert {table: after[table] for table in before} == before
    assert set(after) - set(before) == set(WORKFORCE_TABLES[:8])
    assert all(after[table][0] == 0 for table in WORKFORCE_TABLES[:8])
    with psycopg.connect(database.owner_dsn) as owner:
        current: dict[int, str] = dict(
            owner.execute("select version,checksum from public.gba_schema_migrations")
        )
    assert {version: current[version] for version in old} == old
    pool = create_runtime_pool(database.app_dsn, min_size=1, max_size=2)
    await pool.open()
    try:
        async with tenant_transaction(pool, salon.tenant_id) as conn:
            await assert_location_scope_ready(conn)
            # The CURRENT application requires I2 as well; a preserved I1-only
            # upgrade remains a valid historical step, not current readiness.
            with pytest.raises(DatabaseUnavailableError):
                await assert_workforce_ready(conn)
    finally:
        await pool.close()
