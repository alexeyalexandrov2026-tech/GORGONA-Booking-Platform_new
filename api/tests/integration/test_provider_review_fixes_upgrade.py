"""Forward 0058 -> 0060 (K5b): every row stays; the index, the grants and the trigger are added."""

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
def previous_admission_database(
    previous_receipt_database: ProvisionedDatabase,
) -> ProvisionedDatabase:
    apply_migrations(previous_receipt_database.owner_dsn, load_migrations()[:58])
    return previous_receipt_database


async def test_nonempty_0058_upgrades_with_every_row_unchanged(
    routed: attested.Routed,
    writer_pool: RuntimePool,
    test_database: ProvisionedDatabase,
    previous_admission_database: ProvisionedDatabase,
) -> None:
    await attested.receive(writer_pool, routed, attested.delivery())
    copy_fixture_data(test_database, previous_admission_database)
    before = snapshot(previous_admission_database)
    assert before["provider_event_inbox"][0] >= 1
    applied = checksums(previous_admission_database)
    assert len(applied) == 58
    upgrade = apply_migrations(previous_admission_database.owner_dsn, load_migrations()[:60])
    assert [m.version for m in upgrade] == [59, 60]
    assert snapshot(previous_admission_database) == before
    with psycopg.connect(previous_admission_database.admin_dsn) as conn:
        row = conn.execute(
            "select pg_catalog.has_any_column_privilege("
            "'gba_runtime','gba.provider_event_inbox','INSERT'), "
            "pg_catalog.has_any_column_privilege("
            "'gba_runtime','gba.provider_event_deliveries','INSERT'), "
            "pg_catalog.to_regclass('gba.provider_event_inbox_connection') is not null, "
            "exists (select 1 from pg_catalog.pg_trigger "
            "where tgname='provider_payment_links_require_workflow')"
        ).fetchone()
    assert row == (False, False, True, True)
    assert checksums(previous_admission_database)[:58] == applied
    assert apply_migrations(previous_admission_database.owner_dsn, load_migrations()[:60]) == []
