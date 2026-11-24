"""Unit contract tests for SUPPLY-01 Slice 3 (0140): price lists, trade & 3PL orders,
shipments, and customer returns.
"""

from datetime import date
from uuid import uuid7

import pytest
from pydantic import ValidationError

from gorgona_booking.business.supply_trade import (
    OrderReturnInput,
    OrderShipmentInput,
    PriceListInput,
    PriceListItemInput,
    TradeOrderInput,
    TradeOrderLineInput,
)


def test_price_list_input_rejects_duplicate_item_min_quantity_tiers() -> None:
    item_id = uuid7()
    with pytest.raises(ValidationError, match="Duplicate"):
        PriceListInput(
            expected_revision=0,
            location_id=uuid7(),
            code="PL_WHOLESALE",
            title="Wholesale Tiered List",
            channel="wholesale",
            currency="USD",
            items=[
                PriceListItemInput(item_id=item_id, min_quantity=10, unit_price_minor=4500),
                PriceListItemInput(item_id=item_id, min_quantity=10, unit_price_minor=4200),
            ],
        )


def test_trade_order_input_requires_all_financial_fields_together() -> None:
    with pytest.raises(
        ValidationError, match="book_id, control_account_id, and revenue_account_id"
    ):
        TradeOrderInput(
            expected_revision=0,
            location_id=uuid7(),
            code="ORD_001",
            order_kind="wholesale_sale",
            goods_owner_id=uuid7(),
            customer_counterparty_id=uuid7(),
            currency="USD",
            book_id=uuid7(),
            lines=[TradeOrderLineInput(item_id=uuid7(), ordered_quantity=5, unit_price_minor=9000)],
        )


def test_shipment_and_return_reject_duplicate_serial_codes() -> None:
    with pytest.raises(ValidationError, match="Duplicate serial_code"):
        OrderShipmentInput(
            order_line_id=uuid7(),
            bin_id=uuid7(),
            lot_id=uuid7(),
            quantity=2,
            serial_codes=["sn-100", "SN-100"],
            document_date=date(2026, 10, 10),
        )
    with pytest.raises(ValidationError, match="Duplicate serial_code"):
        OrderReturnInput(
            shipment_id=uuid7(),
            bin_id=uuid7(),
            quantity=2,
            serial_codes=["sn-200", "SN-200"],
            document_date=date(2026, 10, 11),
            reason="Damaged seal on arrival",
        )
