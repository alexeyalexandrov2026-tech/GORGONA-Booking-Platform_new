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
    # L9b (0073): the reversal of a visit commission after a refund.
    "visit_commission_reversals",
    # M1 (0074): transport orders, loads, trips, stops and legs.
    "transport_orders",
    "transport_loads",
    "transport_trips",
    "transport_stops",
    "transport_legs",
    # M2 (0075): drivers, vehicles, assignment periods and their ends.
    "transport_drivers",
    "transport_vehicles",
    "transport_assignments",
    "transport_assignment_ends",
    # M3 (0076): stop events and their quantities per leg.
    "transport_stop_events",
    "transport_event_quantities",
    # M5 (0078): hours-of-service profiles, duty records and telematics pings.
    "transport_hos_profiles",
    "transport_duty_records",
    "transport_telematics_pings",
    # M7a (0079): order rates and invoices, pay components and their accruals.
    "transport_order_rates",
    "transport_order_invoices",
    "transport_pay_components",
    "transport_pay_accruals",
    # N1 (0080): broker authority and carrier profiles.
    "transport_broker_authorities",
    "transport_carrier_profiles",
    # N2 (0082): tenders and their answers.
    "transport_tenders",
    "transport_tender_answers",
    # N3 (0083): rate confirmations and their answers.
    "transport_rate_confirmations",
    "transport_rate_confirmation_answers",
    "transport_carrier_companies",
    "transport_tender_accruals",
    # O1 (0087): construction projects and estimates.
    "construction_projects",
    "construction_estimate_versions",
    "construction_estimate_lines",
    # O2 (0088): the contract and change orders.
    "construction_contracts",
    "construction_change_orders",
    "construction_change_order_lines",
    "construction_change_order_decisions",
    # O3a (0089): commitments.
    "construction_commitments",
    "construction_commitment_versions",
    "construction_commitment_lines",
    # O3b (0090): actual cost links.
    "construction_cost_links",
    "construction_cost_reversals",
    # O4a (0091): schedule, daily reports and completed quantities.
    "construction_schedule_versions",
    "construction_schedule_phases",
    "construction_schedule_dependencies",
    "construction_daily_reports",
    "construction_daily_report_crew",
    "construction_daily_report_photos",
    "construction_progress_measurements",
    # O4b (0092): inspections, defects and the punch list.
    "construction_inspections",
    "construction_inspection_photos",
    "construction_quality_items",
    "construction_quality_item_events",
    "construction_quality_item_photos",
    # O5 (0093): retainage rates and pay applications.
    "construction_retainage_rates",
    "construction_pay_applications",
    "construction_pay_application_lines",
    # O6a (0094): stage and final acceptances and retainage releases.
    "construction_acceptances",
    "construction_retainage_releases",
    # O6b (0095): warranty claims, their events and repairs.
    "construction_warranty_claims",
    "construction_warranty_claim_events",
    "construction_warranty_repairs",
    # R1 (0096): rental classes, units and their values.
    "rental_classes",
    "rental_class_attributes",
    "rental_units",
    "rental_unit_values",
    # R2 (0097): rental bookings and their cancellations.
    "rental_bookings",
    "rental_booking_cancellations",
    # R3a (0098): rental assignments and their releases.
    "rental_assignments",
    "rental_assignment_releases",
    # R3b (0099): rental unit blocks and their releases.
    "rental_unit_blocks",
    "rental_unit_block_releases",
    # R4a (0100): rental rate cards and their extras.
    "rental_rate_cards",
    "rental_rate_card_extras",
    # R4b (0101): rental agreements, their versions and extras.
    "rental_agreements",
    "rental_agreement_versions",
    "rental_agreement_version_extras",
    # R4c (0102): rental booking period changes.
    "rental_booking_periods",
    "rental_securities",
    "rental_security_events",
    "rental_security_provider_links",
    "rental_inspections",
    "rental_inspection_marks",
    "rental_settlements",
    "rental_damage_charges",
    "rental_damage_charge_marks",
    "rental_refunds",
    # PROPERTY-01 (0112): the internal catalog and its version history.
    "property_objects",
    "property_revisions",
    "property_parties",
    # PROPERTY-01 (0113): listings of catalog objects.
    "property_listings",
    "property_listing_revisions",
    "property_showing_resources",
    "property_showings",
    "property_leases",
    "property_lease_term_events",
    "property_move_ins",
    "property_move_in_photos",
    "property_showing_cancellations",
    # BUILD-01 (0118): project customer-company association history.
    "construction_customer_companies",
    # RENT-01 (0122): booking customer-company association history.
    "rental_customer_companies",
    "rental_customer_change_offers",
    # RENT-01 (0125): booking problem reports.
    "rental_problem_reports",
    "property_maintenance_requests",
    "property_maintenance_events",
    "property_maintenance_obligations",
    "property_maintenance_contractor_links",
    "property_maintenance_contractor_updates",
    "property_move_outs",
    "property_move_out_photos",
    "restaurant_areas",
    "restaurant_area_revisions",
    "restaurant_tables",
    "restaurant_table_reservations",
    "restaurant_table_reservation_events",
    "restaurant_menu_items",
    "restaurant_menu_item_revisions",
    "restaurant_modifier_groups",
    "restaurant_modifier_options",
    "restaurant_menu_item_modifier_groups",
    "restaurant_recipes",
    "restaurant_recipe_lines",
    "restaurant_checks",
    "restaurant_kitchen_tickets",
    "restaurant_kitchen_ticket_events",
    "restaurant_check_lines",
    "restaurant_check_line_modifiers",
    "restaurant_check_consumptions",
    "restaurant_check_consumption_lines",
    "restaurant_check_splits",
    "restaurant_check_split_shares",
    "restaurant_check_split_share_lines",
    "restaurant_check_bills",
    "restaurant_check_refunds",
    "project_matters",
    "project_matter_members",
    "project_matter_revisions",
    "project_conflict_checks",
    "project_stages",
    "project_tasks",
    "project_task_dependencies",
    "project_matter_files",
    "project_time_entries",
    "project_time_entry_revisions",
    "project_recurring_schedules",
    "project_recurring_runs",
    "project_matter_invoices",
    "project_matter_invoice_items",
    "project_exports",
    "supply_goods_owners",
    "supply_warehouse_bins",
    "supply_lots",
    "supply_lot_balances",
    "supply_serial_units",
    "supply_wms_movements",
    "supply_boms",
    "supply_bom_components",
    "supply_work_orders",
    "supply_work_order_issues",
    "supply_work_order_returns",
    "supply_work_order_qc",
    "supply_work_order_outputs",
    "supply_price_lists",
    "supply_price_list_items",
    "supply_trade_orders",
    "supply_trade_order_lines",
    "supply_order_shipments",
    "supply_order_returns",
    "market_storefronts",
    "market_listings",
    "marketplaces",
    "marketplace_seller_connections",
    "market_baskets",
    "market_orders",
    "market_order_lines",
    "market_operator_fees",
    "enterprise_sso_providers",
    "enterprise_directory_links",
    "enterprise_lifecycle_events",
    "enterprise_group_report_grants",
    "enterprise_group_report_snapshots",
    "special_programs",
    "special_enrollments",
    "special_rooms",
    "special_stays",
    "special_events",
    "special_tickets",
    "care_subjects",
    "care_consents",
    "care_plans",
    "care_encounters",
    "managed_assets",
    "asset_inspections",
    "asset_work_orders",
    "asset_safety_incidents",
    "self_service_signups",
    "notification_outbox",
    "growth_settings",
    "waitlist_entries",
    "api_keys",
    "webhook_endpoints",
    "webhook_deliveries",
    "connector_installations",
    "media_assets",
    "civic_programs",
    "civic_cases",
    "civic_allocations",
    "civic_audit_events",
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
