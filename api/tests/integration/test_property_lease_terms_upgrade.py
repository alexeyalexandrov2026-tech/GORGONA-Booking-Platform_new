"""Upgrade legacy lease facts from 0115 to the current-term projection."""

import hashlib

import psycopg
import pytest

from gorgona_booking.db.migrate import apply_migrations, load_migrations
from tests.integration import test_property_lease_terms as term_tests
from tests.integration.conftest import ProvisionedDatabase
from tests.integration.seed import FakeUser
from tests.integration.test_agreements import Agreements
from tests.integration.test_h3_upgrade import copy_fixture_data, snapshot
from tests.integration.test_property_catalog import Catalog
from tests.integration.test_property_lease_terms import amend, registered
from tests.integration.test_property_listings import unit
from tests.integration.test_provider_routing_upgrade import checksums
from tests.integration.test_r7b_upgrade import previous_r7a_database, previous_receipt_database

agreements = term_tests.agreements
catalog = term_tests.catalog
client = term_tests.client
enabled = term_tests.enabled
idp = term_tests.idp
manager_a = term_tests.manager_a
manager_b = term_tests.manager_b
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
async def test_apply_lease_terms_to_populated_0115(
    enabled: Catalog,
    agreements: Agreements,
    manager_a: FakeUser,
    test_database: ProvisionedDatabase,
    previous_r7a_database: ProvisionedDatabase,
) -> None:
    document = (await agreements.create(file_id=await agreements.stored()))["document_id"]
    lease_id, contract = await registered(enabled, agreements, await unit(enabled), document)
    amendment = await amend(agreements, contract, document, effective_until="2027-01-31")

    prior = previous_r7a_database
    migrations = load_migrations()
    apply_migrations(prior.owner_dsn, migrations[:115])
    copy_fixture_data(test_database, prior)
    before = snapshot(prior)
    leases_before = before.pop("property_leases")
    assert leases_before[0] >= 1
    prior_checksums = checksums(prior)
    assert len(prior_checksums) == 115

    assert [m.version for m in apply_migrations(prior.owner_dsn, migrations[:116])] == [116]
    after = snapshot(prior)
    assert after.pop("property_lease_term_events")[0] == 0
    assert after.pop("property_leases")[0] == leases_before[0]
    assert after == before
    assert checksums(prior)[:115] == prior_checksums
    assert apply_migrations(prior.owner_dsn, migrations[:116]) == []

    with psycopg.connect(prior.admin_dsn) as conn:
        before_projection = conn.execute(
            "select (to_jsonb(l) - array['term_revision','occupied_through'])::text "
            "from gba.property_leases l order by 1"
        ).fetchall()
        actual_digest = hashlib.sha256(
            "\n".join(row[0] for row in before_projection).encode()
        ).hexdigest()
        assert actual_digest == leases_before[1]
        assert conn.execute(
            "select count(*) from gba.property_leases "
            "where term_revision <> 1 or occupied_through is not null"
        ).fetchone() == (0,)

    with psycopg.connect(prior.app_dsn) as conn:
        conn.execute("select set_config('gba.tenant_id', %s, true)", (str(enabled.tenant),))
        conn.execute(
            "insert into gba.property_lease_term_events "
            "(tenant_id, lease_id, revision, action, agreement_revision, recorded_by) "
            "values (%s,%s,2,'extend',%s,%s)",
            (enabled.tenant, lease_id, amendment, manager_a.user_id),
        )
        state = conn.execute(
            "select term_revision, occupied_through::text, ends_on::text "
            "from gba.property_leases where id = %s",
            (lease_id,),
        ).fetchone()
        assert state == (2, "2027-01-31", "2026-12-31")
