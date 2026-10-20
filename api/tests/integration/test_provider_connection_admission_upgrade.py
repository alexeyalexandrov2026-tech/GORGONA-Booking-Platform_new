"""Forward 0056 -> 0058: every row stays, and no existing connection is admitted by the upgrade."""

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
def previous_money_database(previous_receipt_database: ProvisionedDatabase) -> ProvisionedDatabase:
    apply_migrations(previous_receipt_database.owner_dsn, load_migrations()[:56])
    return previous_receipt_database


async def test_nonempty_0056_upgrades_with_every_row_and_no_admission(
    routed: attested.Routed,
    writer_pool: RuntimePool,
    test_database: ProvisionedDatabase,
    previous_money_database: ProvisionedDatabase,
) -> None:
    await attested.receive(writer_pool, routed, attested.delivery())
    copy_fixture_data(test_database, previous_money_database)
    before = snapshot(previous_money_database)
    assert before["provider_event_attestations"][0] >= 1
    assert "provider_connection_admissions" not in before
    applied = checksums(previous_money_database)
    assert len(applied) == 56
    upgrade = apply_migrations(previous_money_database.owner_dsn, load_migrations()[:58])
    assert [m.version for m in upgrade] == [57, 58]
    after = snapshot(previous_money_database)
    assert {name: after[name] for name in before} == before
    assert set(after) - set(before) == {"provider_connection_admissions"}
    assert after["provider_connection_admissions"][0] == 0
    with psycopg.connect(previous_money_database.admin_dsn) as conn:
        row = conn.execute(
            "select count(*) from gba.provider_receipt_connections where admission<>'not_admitted'"
        ).fetchone()
    assert row == (0,)
    assert checksums(previous_money_database)[:56] == applied
    assert apply_migrations(previous_money_database.owner_dsn, load_migrations()[:58]) == []
