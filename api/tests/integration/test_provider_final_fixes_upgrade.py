"""Forward 0060 -> 0062 (K5r): every row stays; the operation index and a grant are added."""

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
def previous_k5b_database(
    previous_receipt_database: ProvisionedDatabase,
) -> ProvisionedDatabase:
    apply_migrations(previous_receipt_database.owner_dsn, load_migrations()[:60])
    return previous_receipt_database


async def test_nonempty_0060_upgrades_keeping_every_row(
    routed: attested.Routed,
    writer_pool: RuntimePool,
    test_database: ProvisionedDatabase,
    previous_k5b_database: ProvisionedDatabase,
) -> None:
    await attested.receive(writer_pool, routed, attested.delivery())
    copy_fixture_data(test_database, previous_k5b_database)
    before = snapshot(previous_k5b_database)
    assert before["provider_event_inbox"][0] >= 1
    applied = checksums(previous_k5b_database)
    assert len(applied) == 60
    upgrade = apply_migrations(previous_k5b_database.owner_dsn, load_migrations()[:62])
    assert [m.version for m in upgrade] == [61, 62]
    after = snapshot(previous_k5b_database)
    # Every other table is byte-identical; the inbox keeps its rows and gains the stored key.
    inbox = "provider_event_inbox"
    assert {k: v for k, v in after.items() if k != inbox} == {
        k: v for k, v in before.items() if k != inbox
    }
    assert after[inbox][0] == before[inbox][0]
    with psycopg.connect(previous_k5b_database.admin_dsn) as conn:
        row = conn.execute(
            "select pg_catalog.to_regclass('gba.provider_event_inbox_operation') is not null, "
            "pg_catalog.has_function_privilege('gba_receipt_writer', "
            "'gba.provider_receipt_operation(jsonb)', 'EXECUTE'), "
            "(select count(*) from gba.provider_event_inbox e where e.operation_kind is "
            "distinct from (gba.provider_receipt_operation(e.facts)).kind or e.operation_object_id "
            "is distinct from (gba.provider_receipt_operation(e.facts)).object_id)"
        ).fetchone()
    assert row == (True, True, 0)
    assert checksums(previous_k5b_database)[:60] == applied
    assert apply_migrations(previous_k5b_database.owner_dsn, load_migrations()[:62]) == []
