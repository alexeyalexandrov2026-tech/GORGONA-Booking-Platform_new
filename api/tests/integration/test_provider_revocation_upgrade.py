"""Forward 0047 -> 0048: every row stays; revocations from before keep an empty record."""

import psycopg
import pytest

from gorgona_booking.db.migrate import apply_migrations, load_migrations
from gorgona_booking.db.pool import RuntimePool
from tests.integration import test_provider_receipt_attestations as attested
from tests.integration import test_provider_receipt_revocation as revocation
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
previous_receipt_database = shared.previous_receipt_database
REVOCABLE = (revocation.CONNECTIONS, revocation.CONFIGS)


@pytest.fixture
def previous_revocation_database(
    previous_receipt_database: ProvisionedDatabase,
) -> ProvisionedDatabase:
    apply_migrations(previous_receipt_database.owner_dsn, load_migrations()[:47])
    return previous_receipt_database


def without_record(database: ProvisionedDatabase) -> dict[str, list[str]]:
    with psycopg.connect(database.admin_dsn) as conn:
        return {
            table: [
                row[0]
                for row in conn.execute(
                    f"select (to_jsonb(t)-array['revoked_reason','revoked_at','revoked_by'])::text "
                    f"from gba.{table} t order by 1"
                ).fetchall()
            ]
            for table in REVOCABLE
        }


async def test_earlier_revocations_upgrade_with_an_empty_record(
    routed: attested.Routed,
    app_pool: RuntimePool,
    test_database: ProvisionedDatabase,
    previous_revocation_database: ProvisionedDatabase,
) -> None:
    await revocation.revoke(app_pool, routed, revocation.CONFIGS, "rotation")
    await revocation.revoke(app_pool, routed, revocation.CONNECTIONS, "retired")
    copy_fixture_data(test_database, previous_revocation_database)
    before = snapshot(previous_revocation_database)
    kept = without_record(previous_revocation_database)
    applied = checksums(previous_revocation_database)
    assert len(applied) == 47
    upgrade = apply_migrations(previous_revocation_database.owner_dsn, load_migrations()[:48])
    assert [m.version for m in upgrade] == [48]
    after = snapshot(previous_revocation_database)
    assert set(after) == set(before)
    assert {n: v for n, v in after.items() if n not in REVOCABLE} == {
        n: v for n, v in before.items() if n not in REVOCABLE
    }
    assert without_record(previous_revocation_database) == kept
    with psycopg.connect(previous_revocation_database.admin_dsn) as conn:
        for table in REVOCABLE:
            row = conn.execute(
                f"select count(*) filter (where revoked),count(*) filter (where "
                f"revoked_reason is not null or revoked_at is not null or revoked_by is not null) "
                f"from gba.{table}"
            ).fetchone()
            assert row is not None
            assert row[0] >= 1, table
            assert row[1] == 0, table
    assert checksums(previous_revocation_database)[:47] == applied
    assert apply_migrations(previous_revocation_database.owner_dsn, load_migrations()[:48]) == []
