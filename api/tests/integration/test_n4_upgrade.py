"""Forward 0083 -> 0084 (N4): every row stays; 0084 adds one table and two columns."""

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
def previous_n3_database(
    previous_receipt_database: ProvisionedDatabase,
) -> ProvisionedDatabase:
    apply_migrations(previous_receipt_database.owner_dsn, load_migrations()[:83])
    return previous_receipt_database


async def test_nonempty_0083_upgrades_keeping_every_row(
    routed: attested.Routed,
    writer_pool: RuntimePool,
    test_database: ProvisionedDatabase,
    previous_n3_database: ProvisionedDatabase,
) -> None:
    await attested.receive(writer_pool, routed, attested.delivery())
    copy_fixture_data(test_database, previous_n3_database)
    before = snapshot(previous_n3_database)
    assert before["provider_event_inbox"][0] >= 1
    applied = checksums(previous_n3_database)
    assert len(applied) == 83
    upgrade = apply_migrations(previous_n3_database.owner_dsn, load_migrations()[:84])
    assert [m.version for m in upgrade] == [84]
    after = snapshot(previous_n3_database)
    new = {"transport_carrier_companies"}
    # The two answer tables gain an empty column: their rows stay, their row digests change.
    widened = {"transport_tender_answers", "transport_rate_confirmation_answers"}
    assert {k: v for k, v in after.items() if k not in new | widened} == {
        k: v for k, v in before.items() if k not in widened
    }
    assert all(after[table][0] == before[table][0] for table in widened)
    assert all(after[table][0] == 0 for table in new)
    assert checksums(previous_n3_database)[:83] == applied
    assert apply_migrations(previous_n3_database.owner_dsn, load_migrations()[:84]) == []
