"""Nonempty I4 data upgrades to the inventory tables of J1 and J2 without rewriting facts."""

import psycopg
import pytest

from gorgona_booking.db.inventory_guard import INVENTORY_TABLES, assert_inventory_ready
from gorgona_booking.db.migrate import apply_migrations, load_migrations
from gorgona_booking.db.pool import create_runtime_pool, tenant_transaction
from gorgona_booking.db.workforce_guard import assert_workforce_ready
from tests.integration.conftest import ProvisionedDatabase
from tests.integration.test_h3_upgrade import copy_fixture_data, snapshot
from tests.integration.test_provider_admission_upgrade import previous_admission_database
from tests.integration.test_timesheets import (
    Times,
    changes,
    client,
    idp,
    manager_a,
    times,
    workforce,
)

pytestmark = pytest.mark.anyio
# Package K tables of migrations 0044-0046, 0050 and 0052, which the upgrade to the latest state
# creates.
K_TABLES = {
    "provider_receipt_connections",
    "provider_event_inbox",
    "provider_event_deliveries",
    "provider_event_attestations",
    "provider_verification_configs",
    "provider_receipt_routes",
    "provider_operations",
    "provider_event_leases",
    "provider_event_decisions",
    # K3a (0052): the clearing account and the provenance of provider payments.
    "provider_clearing_accounts",
    "external_payment_provenance",
    # K4b (0053): acknowledgements of decisions without an operation.
    "provider_event_acknowledgements",
    # K3b (0054): links of manual payments to provider operations.
    "provider_payment_links",
    # K0b (0057): the owner's admissions of receipt connections.
    "provider_connection_admissions",
    # K6a (0063): failed decisions and releases of parked events.
    "provider_event_failures",
    "provider_event_releases",
    # K6b (0064): one record per reconciliation run.
    "provider_reconciliation_runs",
    # L1 (0066): the stages of a service variant (not a K table; created by the same upgrade).
    "variant_stages",
    # L3 (0068): recipes, visit completions and their material uses.
    "variant_materials",
    "add_on_materials",
    "visit_completions",
    "visit_material_uses",
    # L4 (0069): the link of a visit to its invoice.
    "visit_invoices",
    # L5 (0070): commission plans, rules and the visit commission link.
    "commission_plans",
    "commission_rules",
    "visit_commissions",
    # L6 (0071): prepaid balances and their redemptions.
    "prepaid_balances",
    "prepaid_redemptions",
    # L9a (0072): the published fee policy versions and the no-show facts.
    "visit_fee_policies",
    "visit_no_shows",
}
previous_inventory_database = previous_admission_database
__all__ = ["changes", "client", "idp", "manager_a", "times", "workforce"]


async def test_nonempty_0035_upgrade_preserves_every_fact_and_prior_checksum(
    times: Times,
    test_database: ProvisionedDatabase,
    previous_inventory_database: ProvisionedDatabase,
) -> None:
    started = await times.start()
    assert started.status_code == 200, started.text
    target = previous_inventory_database
    apply_migrations(target.owner_dsn, load_migrations()[:35])
    copy_fixture_data(test_database, target)
    before = snapshot(target)
    # The old schema really holds workforce facts before the upgrade.
    assert before["time_entry_revisions"][0] >= 1
    with psycopg.connect(target.owner_dsn) as conn:
        prior: dict[int, str] = dict(
            conn.execute("select version,checksum from public.gba_schema_migrations")
        )
    # Every migration: the packaged guards approve only the latest state (K1i added 0047).
    inventory_migrations = load_migrations()
    applied = apply_migrations(target.owner_dsn, inventory_migrations)
    assert [migration.version for migration in applied] == list(
        range(36, len(inventory_migrations) + 1)
    )
    assert apply_migrations(target.owner_dsn, inventory_migrations) == []
    after = snapshot(target)
    assert {table: after[table] for table in before} == before
    assert set(after) - set(before) == set(INVENTORY_TABLES) | K_TABLES
    assert all(after[table][0] == 0 for table in INVENTORY_TABLES)
    with psycopg.connect(target.owner_dsn) as conn:
        current: dict[int, str] = dict(
            conn.execute("select version,checksum from public.gba_schema_migrations")
        )
    assert {number: current[number] for number in prior} == prior
    pool = create_runtime_pool(target.app_dsn, min_size=1, max_size=2)
    await pool.open()
    try:
        async with tenant_transaction(pool, times.changes.workforce.world.a.tenant_id) as conn:
            await assert_workforce_ready(conn)
            await assert_inventory_ready(conn)
    finally:
        await pool.close()
