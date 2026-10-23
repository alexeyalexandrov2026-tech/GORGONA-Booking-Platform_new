"""Forward 0071 -> 0072 (L9a): every row stays; fee policies and no-shows start empty."""

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
def previous_l6_database(
    previous_receipt_database: ProvisionedDatabase,
) -> ProvisionedDatabase:
    apply_migrations(previous_receipt_database.owner_dsn, load_migrations()[:71])
    return previous_receipt_database


async def test_nonempty_0071_upgrades_keeping_every_row(
    routed: attested.Routed,
    writer_pool: RuntimePool,
    test_database: ProvisionedDatabase,
    previous_l6_database: ProvisionedDatabase,
) -> None:
    await attested.receive(writer_pool, routed, attested.delivery())
    copy_fixture_data(test_database, previous_l6_database)
    before = snapshot(previous_l6_database)
    assert before["provider_event_inbox"][0] >= 1
    applied = checksums(previous_l6_database)
    assert len(applied) == 71
    upgrade = apply_migrations(previous_l6_database.owner_dsn, load_migrations()[:72])
    assert [m.version for m in upgrade] == [72]
    after = snapshot(previous_l6_database)
    new = {"visit_fee_policies", "visit_no_shows"}
    assert {k: v for k, v in after.items() if k not in new} == before
    assert all(after[table][0] == 0 for table in new)
    assert checksums(previous_l6_database)[:71] == applied
    assert apply_migrations(previous_l6_database.owner_dsn, load_migrations()[:72]) == []
