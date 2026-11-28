"""Unit tests for AMARKAL v2.24.0 Competitor CSV Migration Wizard & Sample Sandbox."""

from __future__ import annotations

from gorgona_booking.api.migration_sandbox import MAX_CSV_ROWS, parse_migration_csv


def test_parse_quickbooks_counterparties_csv_aliases() -> None:
    csv_text = (
        "\ufeffCompany Name,Email Address,Phone Number,Contact Type\n"
        "Midwest Logistics LLC,billing@midwest.us,+1-312-555-0140,Customer\n"
        "Steel Depot Corp,orders@steeldepot.com,312-555-0199,Vendor\n"
        ",missing@name.com,,Customer\n"
    )
    rows, errors = parse_migration_csv("counterparties", csv_text)
    assert len(rows) == 2
    assert len(errors) == 1
    assert errors[0].row_number == 4
    assert rows[0]["display_name"] == "Midwest Logistics LLC"
    assert rows[0]["role"] == "customer"
    assert rows[1]["role"] == "supplier"


def test_parse_odoo_mrp_materials_and_eam_assets_csv() -> None:
    mrp_csv = (
        "Item Code,Product Name,Type,UOM,Qty,Unit Cost,Supplier\n"
        "stl-01,Steel Plate,raw,ton,12.5,$890.00,Nucor Steel\n"
    )
    rows, errors = parse_migration_csv("mrp_materials", mrp_csv)
    assert errors == []
    assert rows[0]["sku"] == "STL-01"
    assert rows[0]["on_hand_milli"] == 12_500
    assert rows[0]["unit_cost_cents"] == 89_000

    eam_csv = (
        "Unit Number,Vehicle,VIN,Yard,Engine Hours\n"
        "trk-22,Volvo VNL 860,4V4NC9EH-DEMO,Dallas Terminal,850.5\n"
    )
    a_rows, a_errs = parse_migration_csv("eam_assets", eam_csv)
    assert a_errs == []
    assert a_rows[0]["asset_tag"] == "TRK-22"
    assert a_rows[0]["engine_hours_milli"] == 850_500


def test_parse_us_payroll_profiles_csv_defaults_ca_rule_and_rejects_bad_state() -> None:
    payroll_csv = (
        "Emp ID,Employee Name,State,Hourly Rate,Union Local\n"
        "emp-10,Jordan Vance,CA,$42.50,IBT Local 705\n"
        "emp-11,Bad State,CALIFORNIA,30,\n"
    )
    rows, errors = parse_migration_csv("payroll_profiles", payroll_csv)
    assert len(rows) == 1
    assert rows[0]["overtime_rule"] == "california_daily_8_12"
    assert rows[0]["base_rate_cents"] == 4250
    assert len(errors) == 1
    assert "work_state" in errors[0].message


def test_parse_migration_csv_enforces_batch_cap() -> None:
    header = "sku,name\n"
    body = "".join(f"SKU-{i:04d},Material {i}\n" for i in range(MAX_CSV_ROWS + 5))
    rows, errors = parse_migration_csv("mrp_materials", header + body)
    assert len(rows) == MAX_CSV_ROWS
    assert len(errors) == 1
    assert str(MAX_CSV_ROWS) in errors[0].message
