"""Nonempty0044 archive remains unauthenticated after the forward0045 upgrade."""

import psycopg
import pytest

from gorgona_booking.db.migrate import apply_migrations, load_migrations
from gorgona_booking.db.pool import RuntimePool
from tests.integration import test_provider_event_inbox as archive
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


@pytest.fixture
def previous_attestation_database(
    previous_receipt_database: ProvisionedDatabase,
) -> ProvisionedDatabase:
    apply_migrations(previous_receipt_database.owner_dsn, load_migrations()[:44])
    return previous_receipt_database


async def test_nonempty_0044_upgrade_preserves_rows_and_never_backfills_authentication(
    enabled: LedgerWorld,
    inbox: archive.Inbox,
    app_pool: RuntimePool,
    test_database: ProvisionedDatabase,
    previous_attestation_database: ProvisionedDatabase,
) -> None:
    assert (await enabled.post(enabled.entry())).status_code == 200
    await archive.receive(app_pool, inbox, inbox.event())
    copy_fixture_data(test_database, previous_attestation_database)
    before = snapshot(previous_attestation_database)
    assert before["provider_event_inbox"][0] > 0
    assert before["provider_event_deliveries"][0] > 0
    with psycopg.connect(previous_attestation_database.owner_dsn) as conn:
        checksums = conn.execute(
            "select version,checksum from public.gba_schema_migrations order by version"
        ).fetchall()
    assert len(checksums) == 44
    upgrade = apply_migrations(previous_attestation_database.owner_dsn, load_migrations()[:45])
    assert [m.version for m in upgrade] == [45]
    after = snapshot(previous_attestation_database)
    assert {name: after[name] for name in before} == before
    assert set(after) - set(before) == {"provider_event_attestations"}
    assert after["provider_event_attestations"][0] == 0
    with psycopg.connect(previous_attestation_database.owner_dsn) as conn:
        assert (
            conn.execute(
                "select version,checksum from public.gba_schema_migrations "
                "where version<=44 order by version"
            ).fetchall()
            == checksums
        )
    assert apply_migrations(previous_attestation_database.owner_dsn, load_migrations()[:45]) == []
