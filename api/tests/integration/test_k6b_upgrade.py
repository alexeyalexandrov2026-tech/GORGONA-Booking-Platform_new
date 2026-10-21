"""Forward 0063 -> 0064 (K6b): every row stays; the run record starts empty."""

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
def previous_k6a_database(
    previous_receipt_database: ProvisionedDatabase,
) -> ProvisionedDatabase:
    apply_migrations(previous_receipt_database.owner_dsn, load_migrations()[:63])
    return previous_receipt_database


async def test_nonempty_0063_upgrades_keeping_every_row(
    routed: attested.Routed,
    writer_pool: RuntimePool,
    test_database: ProvisionedDatabase,
    previous_k6a_database: ProvisionedDatabase,
) -> None:
    await attested.receive(writer_pool, routed, attested.delivery())
    copy_fixture_data(test_database, previous_k6a_database)
    before = snapshot(previous_k6a_database)
    assert before["provider_event_inbox"][0] >= 1
    applied = checksums(previous_k6a_database)
    assert len(applied) == 63
    upgrade = apply_migrations(previous_k6a_database.owner_dsn, load_migrations()[:64])
    assert [m.version for m in upgrade] == [64]
    after = snapshot(previous_k6a_database)
    new = ("provider_reconciliation_runs",)
    assert {k: v for k, v in after.items() if k not in new} == before
    with psycopg.connect(previous_k6a_database.admin_dsn) as conn:
        row = conn.execute(
            "select (select count(*) from gba.provider_reconciliation_runs),"
            "(select count(*) from gba.provider_event_attestations "
            "where verifier<>'stripe_snapshot_v1'),"
            "pg_catalog.has_column_privilege('gba_receipt_writer',"
            "'gba.provider_event_attestations','verifier','INSERT')"
        ).fetchone()
    assert row == (0, 0, True)
    assert checksums(previous_k6a_database)[:63] == applied
    assert apply_migrations(previous_k6a_database.owner_dsn, load_migrations()[:64]) == []
