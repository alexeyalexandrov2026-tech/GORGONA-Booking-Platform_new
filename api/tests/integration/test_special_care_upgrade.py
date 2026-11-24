"""Upgrade test: apply 0146_special_clinical_vet_social_care.sql to a populated 0145 DB."""

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
    "care_subjects",
    "care_consents",
    "care_plans",
    "care_encounters",
)


@pytest.mark.anyio
async def test_apply_clinical_care_0146_to_populated_0145(
    world: BookingWorld,
    manager_a: FakeUser,
    test_database: ProvisionedDatabase,
    previous_r7a_database: ProvisionedDatabase,
) -> None:
    migrations = load_migrations()
    prior = previous_r7a_database
    assert apply_migrations(prior.owner_dsn, migrations[:145])[-1].version == 145
    copy_fixture_data(test_database, prior)

    before = snapshot(prior)
    prior_checksums = checksums(prior)
    assert len(prior_checksums) == 145

    assert [m.version for m in apply_migrations(prior.owner_dsn, migrations[:146])] == [146]
    after = snapshot(prior)
    for table in _NEW_TABLES:
        assert after.pop(table)[0] == 0
    assert after == before
    assert checksums(prior)[:145] == prior_checksums
    assert apply_migrations(prior.owner_dsn, migrations[:146]) == []

    # Verify module gate rejects direct runtime insert when clinical_care is disabled
    with psycopg.connect(prior.app_dsn) as conn:
        conn.execute("select set_config('gba.tenant_id', %s, true)", (str(world.a.tenant_id),))
        conn.execute("select set_config('gba.user_id', %s, true)", (str(manager_a.user_id),))
        with pytest.raises(psycopg.DatabaseError, match="the clinical_care module is disabled"):
            conn.execute(
                "insert into gba.care_subjects "
                "(id, tenant_id, location_id, guardian_counterparty_id, subject_kind, code, "
                "display_name, recorded_by) "
                "values (%s, %s, %s, %s, 'human_patient', 'GATE_1', 'Gate', %s)",
                (uuid7(), world.a.tenant_id, world.a.location_id, uuid7(), manager_a.user_id),
            )
    assert snapshot(prior)["care_subjects"][0] == 0
