"""Forward 0045 -> 0046: archives stay unchanged; an unanchored attestation stops the upgrade."""

import psycopg
import pytest

from gorgona_booking.db.migrate import apply_migrations, load_migrations
from gorgona_booking.db.pool import RuntimePool
from tests.integration import test_provider_event_inbox as archive
from tests.integration import test_provider_receipt_attestations as attested
from tests.integration import test_provider_receipt_upgrade as shared
from tests.integration.conftest import ProvisionedDatabase
from tests.integration.test_h3_upgrade import copy_fixture_data, snapshot
from tests.integration.test_ledger import LedgerWorld

pytestmark = pytest.mark.anyio
client = shared.client
idp = shared.idp
manager_a = shared.manager_a
manager_b = shared.manager_b
enabled = shared.enabled
previous_receipt_database = shared.previous_receipt_database
inbox = archive.inbox
writer_pool = attested.writer_pool
routed = attested.routed
NEW_TABLES = {"provider_verification_configs", "provider_receipt_routes"}


@pytest.fixture
def previous_routing_database(
    previous_receipt_database: ProvisionedDatabase,
) -> ProvisionedDatabase:
    apply_migrations(previous_receipt_database.owner_dsn, load_migrations()[:45])
    return previous_receipt_database


def checksums(database: ProvisionedDatabase) -> list[tuple[object, ...]]:
    with psycopg.connect(database.owner_dsn) as conn:
        return conn.execute(
            "select version,checksum from public.gba_schema_migrations order by version"
        ).fetchall()


async def test_nonempty_0045_without_attestations_upgrades_with_rows_unchanged(
    enabled: LedgerWorld,
    inbox: archive.Inbox,
    app_pool: RuntimePool,
    writer_pool: RuntimePool,
    test_database: ProvisionedDatabase,
    previous_routing_database: ProvisionedDatabase,
) -> None:
    assert (await enabled.post(enabled.entry())).status_code == 200
    await archive.receive(writer_pool, inbox, inbox.event())
    copy_fixture_data(test_database, previous_routing_database)
    # The shared test database may already hold attestations from earlier tests.
    with psycopg.connect(previous_routing_database.admin_dsn) as admin:
        admin.execute("truncate gba.provider_event_attestations")
    before = snapshot(previous_routing_database)
    assert before["provider_event_inbox"][0] > 0
    assert before["provider_event_attestations"][0] == 0
    applied = checksums(previous_routing_database)
    assert len(applied) == 45
    upgrade = apply_migrations(previous_routing_database.owner_dsn, load_migrations()[:46])
    assert [m.version for m in upgrade] == [46]
    after = snapshot(previous_routing_database)
    assert {name: after[name] for name in before} == before
    assert set(after) - set(before) == NEW_TABLES
    assert all(after[name][0] == 0 for name in NEW_TABLES)
    assert checksums(previous_routing_database)[:45] == applied
    assert apply_migrations(previous_routing_database.owner_dsn, load_migrations()[:46]) == []


async def test_existing_unanchored_attestation_stops_the_upgrade_without_changes(
    enabled: LedgerWorld,
    routed: attested.Routed,
    writer_pool: RuntimePool,
    test_database: ProvisionedDatabase,
    previous_routing_database: ProvisionedDatabase,
) -> None:
    await attested.receive(writer_pool, routed, attested.delivery())
    copy_fixture_data(test_database, previous_routing_database)
    before = snapshot(previous_routing_database)
    # No 0045 database has configs, so every copied attestation lacks its authority.
    assert before["provider_event_attestations"][0] >= 1
    assert not NEW_TABLES & set(before)
    applied = checksums(previous_routing_database)
    with pytest.raises(psycopg.errors.CheckViolation, match="no verification authority"):
        apply_migrations(previous_routing_database.owner_dsn, load_migrations()[:46])
    assert snapshot(previous_routing_database) == before
    assert checksums(previous_routing_database) == applied
