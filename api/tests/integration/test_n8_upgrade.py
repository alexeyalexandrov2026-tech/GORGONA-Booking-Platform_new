"""Forward 0085 -> 0086 (N8): every row stays; 0086 adds triggers only."""

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
def previous_n5_database(
    previous_receipt_database: ProvisionedDatabase,
) -> ProvisionedDatabase:
    apply_migrations(previous_receipt_database.owner_dsn, load_migrations()[:85])
    return previous_receipt_database


async def test_nonempty_0085_upgrades_keeping_every_row(
    routed: attested.Routed,
    writer_pool: RuntimePool,
    test_database: ProvisionedDatabase,
    previous_n5_database: ProvisionedDatabase,
) -> None:
    await attested.receive(writer_pool, routed, attested.delivery())
    copy_fixture_data(test_database, previous_n5_database)
    before = snapshot(previous_n5_database)
    assert before["provider_event_inbox"][0] >= 1
    applied = checksums(previous_n5_database)
    assert len(applied) == 85
    upgrade = apply_migrations(previous_n5_database.owner_dsn, load_migrations()[:86])
    assert [m.version for m in upgrade] == [86]
    after = snapshot(previous_n5_database)
    assert after == before
    assert checksums(previous_n5_database)[:85] == applied
    assert apply_migrations(previous_n5_database.owner_dsn, load_migrations()[:86]) == []
