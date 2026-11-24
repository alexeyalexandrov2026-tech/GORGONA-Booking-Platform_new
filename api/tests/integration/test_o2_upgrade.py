"""Forward 0087 -> 0088 (O2): every row stays; 0088 adds four construction contract tables."""

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
def previous_o1_database(
    previous_receipt_database: ProvisionedDatabase,
) -> ProvisionedDatabase:
    apply_migrations(previous_receipt_database.owner_dsn, load_migrations()[:87])
    return previous_receipt_database


async def test_nonempty_0087_upgrades_keeping_every_row(
    routed: attested.Routed,
    writer_pool: RuntimePool,
    test_database: ProvisionedDatabase,
    previous_o1_database: ProvisionedDatabase,
) -> None:
    await attested.receive(writer_pool, routed, attested.delivery())
    copy_fixture_data(test_database, previous_o1_database)
    before = snapshot(previous_o1_database)
    assert before["provider_event_inbox"][0] >= 1
    applied = checksums(previous_o1_database)
    assert len(applied) == 87
    upgrade = apply_migrations(previous_o1_database.owner_dsn, load_migrations()[:88])
    assert [m.version for m in upgrade] == [88]
    after = snapshot(previous_o1_database)
    new = {
        "construction_contracts",
        "construction_change_orders",
        "construction_change_order_lines",
        "construction_change_order_decisions",
    }
    assert {k: v for k, v in after.items() if k not in new} == before
    assert all(after[table][0] == 0 for table in new)
    assert checksums(previous_o1_database)[:87] == applied
    assert apply_migrations(previous_o1_database.owner_dsn, load_migrations()[:88]) == []
