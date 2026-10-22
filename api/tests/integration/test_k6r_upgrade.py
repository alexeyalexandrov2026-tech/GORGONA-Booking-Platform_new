"""Forward 0064 -> 0065 (K6r): every row stays; the worker keeps only the keys of releases."""

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
def previous_k6b_database(
    previous_receipt_database: ProvisionedDatabase,
) -> ProvisionedDatabase:
    apply_migrations(previous_receipt_database.owner_dsn, load_migrations()[:64])
    return previous_receipt_database


async def test_nonempty_0064_upgrades_keeping_every_row(
    routed: attested.Routed,
    writer_pool: RuntimePool,
    test_database: ProvisionedDatabase,
    previous_k6b_database: ProvisionedDatabase,
) -> None:
    await attested.receive(writer_pool, routed, attested.delivery())
    copy_fixture_data(test_database, previous_k6b_database)
    before = snapshot(previous_k6b_database)
    assert before["provider_event_inbox"][0] >= 1
    applied = checksums(previous_k6b_database)
    assert len(applied) == 64
    upgrade = apply_migrations(previous_k6b_database.owner_dsn, load_migrations()[:65])
    assert [m.version for m in upgrade] == [65]
    after = snapshot(previous_k6b_database)
    assert after == before
    with psycopg.connect(previous_k6b_database.admin_dsn) as conn:
        row = conn.execute(
            "select pg_catalog.has_table_privilege('gba_receipt_worker',"
            "'gba.provider_event_releases','SELECT'),"
            "pg_catalog.has_column_privilege('gba_receipt_worker',"
            "'gba.provider_event_releases','round','SELECT'),"
            "pg_catalog.has_column_privilege('gba_receipt_worker',"
            "'gba.provider_event_releases','note','SELECT')"
        ).fetchone()
    assert row == (False, True, False)
    assert checksums(previous_k6b_database)[:64] == applied
    assert apply_migrations(previous_k6b_database.owner_dsn, load_migrations()[:65]) == []
