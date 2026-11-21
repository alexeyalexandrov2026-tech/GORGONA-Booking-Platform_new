"""Upgrade test: apply 0137_projects_billing_and_exports.sql to a populated 0136 database."""

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
    "project_matter_invoices",
    "project_matter_invoice_items",
    "project_exports",
)


@pytest.mark.anyio
async def test_apply_projects_billing_0137_to_populated_0136(
    world: BookingWorld,
    manager_a: FakeUser,
    test_database: ProvisionedDatabase,
    previous_r7a_database: ProvisionedDatabase,
) -> None:
    migrations = load_migrations()
    prior = previous_r7a_database
    assert apply_migrations(prior.owner_dsn, migrations[:136])[-1].version == 136
    copy_fixture_data(test_database, prior)

    before = snapshot(prior)
    prior_checksums = checksums(prior)
    assert len(prior_checksums) == 136

    assert [m.version for m in apply_migrations(prior.owner_dsn, migrations[:137])] == [137]
    after = snapshot(prior)
    for table in _NEW_TABLES:
        assert after.pop(table)[0] == 0
    assert after == before
    assert checksums(prior)[:136] == prior_checksums
    assert apply_migrations(prior.owner_dsn, migrations[:137]) == []

    # Verify module gate rejects direct runtime insert when projects is not enabled
    with psycopg.connect(prior.app_dsn) as conn:
        conn.execute("select set_config('gba.tenant_id', %s, true)", (str(world.a.tenant_id),))
        conn.execute("select set_config('gba.user_id', %s, true)", (str(manager_a.user_id),))
        with pytest.raises(psycopg.DatabaseError, match="the projects module is disabled"):
            conn.execute(
                "insert into gba.project_exports "
                "(tenant_id, id, location_id, scope, matter_id, requested_by, matter_count, "
                "stage_count, task_count, file_count, time_entry_count, recurring_run_count, "
                "invoice_count) "
                "values (%s, %s, %s, 'portfolio', null, %s, 0, 0, 0, 0, 0, 0, 0)",
                (world.a.tenant_id, uuid7(), world.a.location_id, manager_a.user_id),
            )
    assert snapshot(prior)["project_exports"][0] == 0
