"""Upgrade existing lease and document history from 0116 to move-in records."""

from datetime import date, timedelta

import psycopg
import pytest

from gorgona_booking.db.migrate import apply_migrations, load_migrations
from tests.integration import test_property_move_in as move_tests
from tests.integration.conftest import ProvisionedDatabase
from tests.integration.seed import FakeUser
from tests.integration.test_agreements import Agreements
from tests.integration.test_h3_upgrade import copy_fixture_data, snapshot
from tests.integration.test_property_catalog import Catalog
from tests.integration.test_property_lease_terms import amend, change
from tests.integration.test_property_move_in import lease_with_evidence
from tests.integration.test_provider_routing_upgrade import checksums
from tests.integration.test_r7b_upgrade import previous_r7a_database, previous_receipt_database

agreements = move_tests.agreements
catalog = move_tests.catalog
client = move_tests.client
enabled = move_tests.enabled
idp = move_tests.idp
manager_a = move_tests.manager_a
manager_b = move_tests.manager_b
__all__ = [
    "agreements",
    "catalog",
    "client",
    "enabled",
    "idp",
    "manager_a",
    "manager_b",
    "previous_r7a_database",
    "previous_receipt_database",
]


@pytest.mark.anyio
async def test_apply_move_in_to_populated_0116(
    enabled: Catalog,
    agreements: Agreements,
    manager_a: FakeUser,
    test_database: ProvisionedDatabase,
    previous_r7a_database: ProvisionedDatabase,
) -> None:
    lease_id, contract, body = await lease_with_evidence(enabled, agreements)
    day = date.fromisoformat(str(body["moved_in_on"]))
    signed_copy = (await agreements.get(f"/agreements/{contract}")).json()["document"][
        "document_id"
    ]
    revision = await amend(
        agreements,
        contract,
        signed_copy,
        effective_from=(day - timedelta(days=30)).isoformat(),
        effective_until=(day + timedelta(days=60)).isoformat(),
    )
    assert (await change(enabled, lease_id, "extend", revision)).is_success

    prior = previous_r7a_database
    migrations = load_migrations()
    apply_migrations(prior.owner_dsn, migrations[:116])
    copy_fixture_data(test_database, prior)
    before = snapshot(prior)
    assert before["property_leases"][0] >= 1
    assert before["property_lease_term_events"][0] >= 1
    assert before["document_files"][0] >= 3
    prior_checksums = checksums(prior)
    assert len(prior_checksums) == 116

    assert [m.version for m in apply_migrations(prior.owner_dsn, migrations[:117])] == [117]
    after = snapshot(prior)
    assert after.pop("property_move_ins")[0] == 0
    assert after.pop("property_move_in_photos")[0] == 0
    assert after == before
    assert checksums(prior)[:116] == prior_checksums
    assert apply_migrations(prior.owner_dsn, migrations[:117]) == []

    report = body["report"]
    photos = body["photos"]
    assert isinstance(report, dict)
    assert isinstance(photos, list)
    with psycopg.connect(prior.app_dsn) as conn:
        conn.execute("select set_config('gba.tenant_id', %s, true)", (str(enabled.tenant),))
        conn.execute(
            "insert into gba.property_move_ins (tenant_id, lease_id, term_revision, "
            "moved_in_on, report_id, report_revision, photo_count, recorded_by) "
            "values (%s,%s,2,%s,%s,1,1,%s)",
            (enabled.tenant, lease_id, day, report["document_id"], manager_a.user_id),
        )
        conn.execute(
            "insert into gba.property_move_in_photos "
            "(tenant_id, lease_id, position, document_id, document_revision) values (%s,%s,1,%s,1)",
            (enabled.tenant, lease_id, photos[0]["document_id"]),
        )
    assert snapshot(prior)["property_move_ins"][0] == 1
