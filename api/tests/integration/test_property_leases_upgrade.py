"""Upgrade existing property and signed document rows from migration 0114."""

from uuid import uuid7

import psycopg
import pytest

from gorgona_booking.db.migrate import apply_migrations, load_migrations
from tests.integration import test_property_leases as lease_tests
from tests.integration.conftest import ProvisionedDatabase
from tests.integration.seed import FakeUser
from tests.integration.test_agreements import Agreements
from tests.integration.test_h3_upgrade import copy_fixture_data, snapshot
from tests.integration.test_property_catalog import Catalog
from tests.integration.test_property_listings import unit
from tests.integration.test_provider_routing_upgrade import checksums
from tests.integration.test_r7b_upgrade import previous_r7a_database, previous_receipt_database

agreements = lease_tests.agreements
catalog = lease_tests.catalog
client = lease_tests.client
enabled = lease_tests.enabled
idp = lease_tests.idp
manager_a = lease_tests.manager_a
manager_b = lease_tests.manager_b
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
async def test_apply_property_leases_to_nonempty_0114(
    enabled: Catalog,
    agreements: Agreements,
    manager_a: FakeUser,
    test_database: ProvisionedDatabase,
    previous_r7a_database: ProvisionedDatabase,
) -> None:
    document = (await agreements.create(file_id=await agreements.stored()))["document_id"]
    subject = await lease_tests.signed(agreements, document)
    object_id = await unit(enabled)

    migrations = load_migrations()
    dsn = previous_r7a_database.owner_dsn
    apply_migrations(dsn, migrations[:114])
    copy_fixture_data(test_database, previous_r7a_database)
    before = snapshot(previous_r7a_database)
    assert before["property_objects"][0] >= 2
    assert before["agreement_versions"][0] >= 2
    assert before["document_files"][0] >= 1
    prior_checksums = checksums(previous_r7a_database)
    assert len(prior_checksums) == 114

    assert [m.version for m in apply_migrations(dsn, migrations[:115])] == [115]
    after = snapshot(previous_r7a_database)
    assert after.pop("property_leases")[0] == 0
    assert after == before
    assert checksums(previous_r7a_database)[:114] == prior_checksums
    assert apply_migrations(dsn, migrations[:115]) == []

    with psycopg.connect(previous_r7a_database.app_dsn) as conn:
        conn.execute("select set_config('gba.tenant_id', %s, true)", (str(enabled.tenant),))
        row = conn.execute(
            "insert into gba.property_leases (tenant_id, id, object_id, agreement_id, "
            "agreement_revision, recorded_by) values (%s,%s,%s,%s,2,%s) "
            "returning starts_on::text, ends_on::text",
            (enabled.tenant, uuid7(), object_id, subject, manager_a.user_id),
        ).fetchone()
        assert row == ("2026-01-01", "2026-12-31")
