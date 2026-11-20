"""Upgrade populated 0126 database to 0127 property maintenance tables without data loss."""

from uuid import UUID, uuid7

import psycopg
import pytest

from gorgona_booking.db.migrate import apply_migrations, load_migrations
from tests.integration import test_property_move_in as move_tests
from tests.integration.conftest import ProvisionedDatabase
from tests.integration.seed import FakeUser
from tests.integration.test_agreements import Agreements
from tests.integration.test_h3_upgrade import copy_fixture_data, snapshot
from tests.integration.test_property_catalog import Catalog
from tests.integration.test_property_move_in import lease_with_evidence, record_move_in
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
async def test_apply_property_maintenance_to_populated_0126(
    enabled: Catalog,
    agreements: Agreements,
    manager_a: FakeUser,
    test_database: ProvisionedDatabase,
    previous_r7a_database: ProvisionedDatabase,
) -> None:
    lease_id, _, body = await lease_with_evidence(enabled, agreements)
    assert (await record_move_in(enabled, lease_id, body)).is_success
    lease_view = (
        await enabled.client.get(
            f"/v1/businesses/{enabled.tenant}/property/leases/{lease_id}",
            headers=enabled.headers,
        )
    ).json()
    unit_id = UUID(lease_view["object_id"])

    prior = previous_r7a_database
    migrations = load_migrations()
    apply_migrations(prior.owner_dsn, migrations[:126])
    copy_fixture_data(test_database, prior)
    before = snapshot(prior)
    assert before["property_leases"][0] >= 1
    assert before["property_move_ins"][0] >= 1
    prior_checksums = checksums(prior)
    assert len(prior_checksums) == 126

    assert [m.version for m in apply_migrations(prior.owner_dsn, migrations[:127])] == [127]
    after = snapshot(prior)
    assert after.pop("property_maintenance_requests")[0] == 0
    assert after.pop("property_maintenance_events")[0] == 0
    assert after.pop("property_maintenance_obligations")[0] == 0
    assert after == before
    assert checksums(prior)[:126] == prior_checksums
    assert apply_migrations(prior.owner_dsn, migrations[:127]) == []

    req_id = uuid7()
    with psycopg.connect(prior.app_dsn) as conn:
        conn.execute("select set_config('gba.tenant_id', %s, true)", (str(enabled.tenant),))
        conn.execute(
            "insert into gba.property_maintenance_requests "
            "(tenant_id, id, object_id, lease_id, category, priority, "
            "title, description, recorded_by) "
            "values (%s,%s,%s,%s,'plumbing','urgent',"
            "'FAKE Post-upgrade leak','FAKE Upgraded DB check',%s)",
            (enabled.tenant, req_id, unit_id, lease_id, manager_a.user_id),
        )
    assert snapshot(prior)["property_maintenance_requests"][0] == 1
