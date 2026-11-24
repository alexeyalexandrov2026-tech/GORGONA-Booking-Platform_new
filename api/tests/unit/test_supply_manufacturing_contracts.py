"""Unit contract tests for SUPPLY-01 Slice 2 (Manufacturing BOMs, work orders, issues, returns,
QC, output)."""

from datetime import date
from uuid import uuid7

import pytest
from pydantic import ValidationError

from gorgona_booking.business.supply_manufacturing import (
    BomComponentInput,
    BomInput,
    WorkOrderOutputInput,
    WorkOrderQcInput,
)


def test_bom_input_rejects_self_reference_and_duplicate_components() -> None:
    loc_id, out_id, comp1, comp2 = uuid7(), uuid7(), uuid7(), uuid7()
    valid = BomInput(
        expected_revision=0,
        location_id=loc_id,
        code="bom_valve_assy",
        title="Valve Assembly BOM",
        output_item_id=out_id,
        batch_output_quantity=10,
        standard_labor_minor=5000,
        standard_overhead_minor=2500,
        components=[
            BomComponentInput(component_item_id=comp1, quantity_per_batch=10, scrap_bps=100),
            BomComponentInput(component_item_id=comp2, quantity_per_batch=20, scrap_bps=0),
        ],
    )
    assert valid.code == "BOM_VALVE_ASSY"

    with pytest.raises(ValidationError):
        BomInput(
            expected_revision=0,
            location_id=loc_id,
            code="BOM_DUP",
            title="Duplicate component",
            output_item_id=out_id,
            batch_output_quantity=1,
            components=[
                BomComponentInput(component_item_id=comp1, quantity_per_batch=1),
                BomComponentInput(component_item_id=comp1, quantity_per_batch=2),
            ],
        )

    with pytest.raises(ValidationError):
        BomInput(
            expected_revision=0,
            location_id=loc_id,
            code="BOM_SELF",
            title="Self component",
            output_item_id=out_id,
            batch_output_quantity=1,
            components=[
                BomComponentInput(component_item_id=out_id, quantity_per_batch=1),
            ],
        )


def test_work_order_qc_and_output_contracts() -> None:
    qc = WorkOrderQcInput(passed_quantity=10, scrap_quantity=1, notes="All pressure tests passed")
    assert qc.passed_quantity == 10

    with pytest.raises(ValidationError):
        WorkOrderOutputInput(
            bin_id=uuid7(),
            output_lot_code="FG-LOT-01",
            manufactured_on=date(2026, 11, 21),
            expires_on=date(2026, 10, 21),
        )
    out = WorkOrderOutputInput(
        bin_id=uuid7(),
        output_lot_code="fg_lot_2026_01",
        manufactured_on=date(2026, 11, 21),
        expires_on=date(2027, 11, 21),
    )
    assert out.output_lot_code == "FG_LOT_2026_01"
