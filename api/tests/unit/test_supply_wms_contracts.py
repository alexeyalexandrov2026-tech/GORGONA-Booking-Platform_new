"""Unit contract tests for SUPPLY-01 Slice 1 (WMS owners, bins, lots, serials, movements)."""

from datetime import date
from uuid import uuid7

import pytest
from pydantic import ValidationError

from gorgona_booking.business.supply_wms import (
    BinRelocationInput,
    GoodsOwnerInput,
    InboundPutawayInput,
    LotInput,
    OutboundPickInput,
    WarehouseBinInput,
)


def test_goods_owner_input_requires_matching_entity_or_counterparty() -> None:
    loc_id, le_id, cp_id = uuid7(), uuid7(), uuid7()
    valid_entity = GoodsOwnerInput(
        expected_revision=0,
        location_id=loc_id,
        code="own_co_1",
        display_name="Company Owner",
        owner_kind="company_entity",
        legal_entity_id=le_id,
    )
    assert valid_entity.code == "OWN_CO_1"

    valid_3pl = GoodsOwnerInput(
        expected_revision=0,
        location_id=loc_id,
        code="3pl_bailor",
        display_name="3PL Client Bailor",
        owner_kind="counterparty_3pl",
        counterparty_id=cp_id,
    )
    assert valid_3pl.code == "3PL_BAILOR"

    with pytest.raises(ValidationError):
        GoodsOwnerInput(
            expected_revision=0,
            location_id=loc_id,
            code="BAD1",
            display_name="Missing entity",
            owner_kind="company_entity",
            counterparty_id=cp_id,
        )

    with pytest.raises(ValidationError):
        GoodsOwnerInput(
            expected_revision=0,
            location_id=loc_id,
            code="BAD2",
            display_name="Both provided",
            owner_kind="counterparty_3pl",
            legal_entity_id=le_id,
            counterparty_id=cp_id,
        )


def test_lot_and_bin_and_movement_contracts_validate_invariants() -> None:
    loc_id, place_id, owner_id, item_id, lot_id, bin_a, bin_b = (
        uuid7(),
        uuid7(),
        uuid7(),
        uuid7(),
        uuid7(),
        uuid7(),
        uuid7(),
    )
    wb = WarehouseBinInput(
        expected_revision=0,
        location_id=loc_id,
        place_id=place_id,
        zone_code="zone_a",
        bin_code="aisle_01_b02",
        bin_kind="storage",
        dedicated_owner_id=owner_id,
    )
    assert wb.zone_code == "ZONE_A"
    assert wb.bin_code == "AISLE_01_B02"

    with pytest.raises(ValidationError):
        LotInput(
            expected_revision=0,
            location_id=loc_id,
            goods_owner_id=owner_id,
            item_id=item_id,
            lot_code="LOT-01",
            manufactured_on=date(2026, 12, 1),
            expires_on=date(2026, 11, 1),
        )

    # Serial count must equal quantity when serial_codes is non-empty
    with pytest.raises(ValidationError):
        InboundPutawayInput(
            location_id=loc_id,
            bin_id=bin_a,
            goods_owner_id=owner_id,
            item_id=item_id,
            lot_id=lot_id,
            quantity=2,
            serial_codes=["SN-001"],
        )

    # Duplicate serial codes rejected
    with pytest.raises(ValidationError):
        OutboundPickInput(
            location_id=loc_id,
            bin_id=bin_a,
            goods_owner_id=owner_id,
            item_id=item_id,
            lot_id=lot_id,
            quantity=2,
            serial_codes=["sn-001", "SN-001"],
        )

    # Relocation source and destination bin must differ
    with pytest.raises(ValidationError):
        BinRelocationInput(
            location_id=loc_id,
            from_bin_id=bin_a,
            to_bin_id=bin_a,
            goods_owner_id=owner_id,
            item_id=item_id,
            lot_id=lot_id,
            quantity=1,
        )
    rel = BinRelocationInput(
        location_id=loc_id,
        from_bin_id=bin_a,
        to_bin_id=bin_b,
        goods_owner_id=owner_id,
        item_id=item_id,
        lot_id=lot_id,
        quantity=2,
        serial_codes=["sn-1", "sn-2"],
    )
    assert rel.serial_codes == ["SN-1", "SN-2"]
