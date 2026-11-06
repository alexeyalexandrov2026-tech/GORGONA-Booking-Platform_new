"""Forward 0100 -> 0101 (R4b): every row stays; 0101 adds rental agreements and their versions."""

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
NEW = {
    "rental_agreements",
    "rental_agreement_versions",
    "rental_agreement_version_extras",
}


@pytest.fixture
def previous_r4a_database(
    previous_receipt_database: ProvisionedDatabase,
) -> ProvisionedDatabase:
    apply_migrations(previous_receipt_database.owner_dsn, load_migrations()[:100])
    return previous_receipt_database


async def test_nonempty_0100_upgrades_keeping_every_row(
    routed: attested.Routed,
    writer_pool: RuntimePool,
    test_database: ProvisionedDatabase,
    previous_r4a_database: ProvisionedDatabase,
) -> None:
    await attested.receive(writer_pool, routed, attested.delivery())
    copy_fixture_data(test_database, previous_r4a_database)
    before = snapshot(previous_r4a_database)
    assert before["provider_event_inbox"][0] >= 1
    applied = checksums(previous_r4a_database)
    assert len(applied) == 100
    upgrade = apply_migrations(previous_r4a_database.owner_dsn, load_migrations()[:101])
    assert [m.version for m in upgrade] == [101]
    after = snapshot(previous_r4a_database)
    assert {k: v for k, v in after.items() if k not in NEW} == before
    assert all(after[table][0] == 0 for table in NEW)
    assert checksums(previous_r4a_database)[:100] == applied
    assert apply_migrations(previous_r4a_database.owner_dsn, load_migrations()[:101]) == []
