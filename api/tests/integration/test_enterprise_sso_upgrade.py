"""Upgrade test: apply 0143_enterprise_sso_and_lifecycle.sql to a populated 0142 database."""

from uuid import uuid7

import psycopg
import pytest

from gorgona_booking.db.migrate import apply_migrations, load_migrations
from tests.integration.booking_support import BookingWorld
from tests.integration.conftest import ProvisionedDatabase
from tests.integration.seed import FakeUser
from tests.integration.test_h3_upgrade import copy_fixture_data, snapshot
from tests.integration.test_property_move_out_upgrade import (
    client,
    idp,
    manager_a,
    previous_r7a_database,
    previous_receipt_database,
)
from tests.integration.test_provider_routing_upgrade import checksums

__all__ = ["client", "idp", "manager_a", "previous_r7a_database", "previous_receipt_database"]

_NEW_TABLES = (
    "enterprise_sso_providers",
    "enterprise_directory_links",
    "enterprise_lifecycle_events",
)


@pytest.mark.anyio
async def test_apply_enterprise_sso_0143_to_populated_0142(
    world: BookingWorld,
    manager_a: FakeUser,
    test_database: ProvisionedDatabase,
    previous_r7a_database: ProvisionedDatabase,
) -> None:
    migrations = load_migrations()
    prior = previous_r7a_database
    assert apply_migrations(prior.owner_dsn, migrations[:142])[-1].version == 142
    copy_fixture_data(test_database, prior)

    before = snapshot(prior)
    prior_checksums = checksums(prior)
    assert len(prior_checksums) == 142

    assert [m.version for m in apply_migrations(prior.owner_dsn, migrations[:143])] == [143]
    after = snapshot(prior)
    for table in _NEW_TABLES:
        assert after.pop(table)[0] == 0
    assert after == before
    assert checksums(prior)[:142] == prior_checksums
    assert apply_migrations(prior.owner_dsn, migrations[:143]) == []

    # Verify module gate rejects direct runtime insert when analytics is not enabled
    with psycopg.connect(prior.app_dsn) as conn:
        conn.execute("select set_config('gba.tenant_id', %s, true)", (str(world.a.tenant_id),))
        conn.execute("select set_config('gba.user_id', %s, true)", (str(manager_a.user_id),))
        with pytest.raises(psycopg.DatabaseError, match="the analytics module is disabled"):
            conn.execute(
                "insert into gba.enterprise_sso_providers "
                "(id, tenant_id, code, display_name, protocol, issuer_url, email_domain, "
                "recorded_by) values (%s, %s, 'GATE', 'Gate IdP', 'oidc', "
                "'https://gate.example.com', 'gate.example', %s)",
                (uuid7(), world.a.tenant_id, manager_a.user_id),
            )
    assert snapshot(prior)["enterprise_sso_providers"][0] == 0
