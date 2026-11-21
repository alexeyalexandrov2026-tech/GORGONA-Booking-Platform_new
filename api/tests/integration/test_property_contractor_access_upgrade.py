"""Upgrade populated 0127 database to 0128 contractor access tables without data loss."""

import psycopg
import pytest

from gorgona_booking.db.migrate import apply_migrations, load_migrations
from tests.integration import test_property_maintenance as maint
from tests.integration.conftest import ProvisionedDatabase
from tests.integration.seed import FakeUser
from tests.integration.test_h3_upgrade import copy_fixture_data, snapshot
from tests.integration.test_property_catalog import Catalog
from tests.integration.test_provider_routing_upgrade import checksums
from tests.integration.test_r7b_upgrade import previous_r7a_database, previous_receipt_database

agreements = maint.agreements
catalog = maint.catalog
client = maint.client
enabled = maint.enabled
idp = maint.idp
manager_a = maint.manager_a
manager_b = maint.manager_b
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
async def test_apply_property_contractor_access_to_populated_0127(
    enabled: Catalog,
    manager_a: FakeUser,
    test_database: ProvisionedDatabase,
    previous_r7a_database: ProvisionedDatabase,
) -> None:
    parcel = await maint.make_parcel(enabled, "FAKE 0127 Parcel")
    contractor = await enabled.counterparty()
    req_id, res = await maint.create_request(enabled, parcel, title="FAKE 0127 Leak")
    assert res.status_code == 200
    assert (
        await maint.post_event(
            enabled,
            req_id,
            {
                "action": "approve",
                "expected_revision": 1,
                "approved_limit_minor": 10000,
                "currency": "USD",
            },
        )
    ).status_code == 200
    assert (
        await maint.post_event(
            enabled,
            req_id,
            {"action": "assign", "expected_revision": 2, "contractor_id": contractor},
        )
    ).status_code == 200

    prior = previous_r7a_database
    migrations = load_migrations()
    apply_migrations(prior.owner_dsn, migrations[:127])
    copy_fixture_data(test_database, prior)
    before = snapshot(prior)
    assert before["property_maintenance_requests"][0] >= 1
    assert before["property_maintenance_events"][0] >= 2
    prior_checksums = checksums(prior)
    assert len(prior_checksums) == 127

    assert [m.version for m in apply_migrations(prior.owner_dsn, migrations[:128])] == [128]
    after = snapshot(prior)
    assert after.pop("property_maintenance_contractor_links")[0] == 0
    assert after.pop("property_maintenance_contractor_updates")[0] == 0
    assert after == before
    assert checksums(prior)[:127] == prior_checksums
    assert apply_migrations(prior.owner_dsn, migrations[:128]) == []

    with psycopg.connect(prior.app_dsn) as conn:
        conn.execute("select set_config('gba.tenant_id', %s, true)", (str(enabled.tenant),))
        conn.execute("select set_config('gba.user_id', %s, true)", (str(manager_a.user_id),))
        conn.execute(
            "insert into gba.property_maintenance_contractor_links "
            "(tenant_id, request_id, revision, contractor_id, company_id, created_by) "
            "values (%s,%s,1,%s,%s,%s)",
            (enabled.tenant, req_id, contractor, enabled.world.b.tenant_id, manager_a.user_id),
        )
    assert snapshot(prior)["property_maintenance_contractor_links"][0] == 1
