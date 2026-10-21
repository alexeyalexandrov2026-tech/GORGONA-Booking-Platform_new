"""Forward 0062 -> 0063 (K6a): every row stays; failures and releases start empty."""

import psycopg
import pytest

from gorgona_booking.db.migrate import apply_migrations, load_migrations
from gorgona_booking.db.pool import RuntimePool
from tests.integration import test_provider_receipt_attestations as attested
from tests.integration import test_provider_receipt_upgrade as shared
from tests.integration.conftest import ProvisionedDatabase
from tests.integration.test_h3_upgrade import copy_fixture_data, snapshot
from tests.integration.test_provider_routing_upgrade import checksums

pytestmark = pytest.mark.anyio
client = attested.client
idp = attested.idp
manager_a = attested.manager_a
manager_b = attested.manager_b
enabled = attested.enabled
inbox = attested.inbox
routed = attested.routed
writer_pool = attested.writer_pool
previous_receipt_database = shared.previous_receipt_database


@pytest.fixture
def previous_k5r_database(
    previous_receipt_database: ProvisionedDatabase,
) -> ProvisionedDatabase:
    apply_migrations(previous_receipt_database.owner_dsn, load_migrations()[:62])
    return previous_receipt_database


async def test_nonempty_0062_upgrades_keeping_every_row(
    routed: attested.Routed,
    writer_pool: RuntimePool,
    test_database: ProvisionedDatabase,
    previous_k5r_database: ProvisionedDatabase,
) -> None:
    await attested.receive(writer_pool, routed, attested.delivery())
    copy_fixture_data(test_database, previous_k5r_database)
    before = snapshot(previous_k5r_database)
    assert before["provider_event_inbox"][0] >= 1
    applied = checksums(previous_k5r_database)
    assert len(applied) == 62
    upgrade = apply_migrations(previous_k5r_database.owner_dsn, load_migrations()[:63])
    assert [m.version for m in upgrade] == [63]
    after = snapshot(previous_k5r_database)
    new = ("provider_event_failures", "provider_event_releases")
    assert {k: v for k, v in after.items() if k not in new} == before
    with psycopg.connect(previous_k5r_database.admin_dsn) as conn:
        row = conn.execute(
            "select (select count(*) from gba.provider_event_failures),"
            "(select count(*) from gba.provider_event_releases),"
            "pg_catalog.pg_get_functiondef('gba.guard_provider_event_lease()'::regprocedure) "
            "like '%provider event is parked%'"
        ).fetchone()
    assert row == (0, 0, True)
    assert checksums(previous_k5r_database)[:62] == applied
    assert apply_migrations(previous_k5r_database.owner_dsn, load_migrations()[:63]) == []
