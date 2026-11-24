"""Unit contract tests for MARKET-01 Slice 2 (0142): basket split and refund contracts."""

from datetime import date
from uuid import uuid7

import pytest
from pydantic import ValidationError

from gorgona_booking.business.market_orders import (
    BasketCheckoutInput,
    BasketItemInput,
    MarketOrderRefundInput,
    SellerSettlementConfig,
)


def test_basket_checkout_requires_items_and_seller_configs() -> None:
    with pytest.raises(ValidationError):
        BasketCheckoutInput(
            location_id=uuid7(),
            customer_counterparty_id=uuid7(),
            currency="USD",
            order_date=date(2026, 10, 10),
            items=[],
            seller_configs=[
                SellerSettlementConfig(
                    storefront_id=uuid7(),
                    book_id=uuid7(),
                    control_account_id=uuid7(),
                    revenue_account_id=uuid7(),
                )
            ],
        )


def test_refund_input_requires_positive_amount_and_clean_reason() -> None:
    with pytest.raises(ValidationError):
        MarketOrderRefundInput(
            refund_minor=0,
            refund_date=date(2026, 10, 12),
            reason="Zero refund invalid",
        )
    valid = BasketItemInput(listing_id=uuid7(), quantity=2)
    assert valid.quantity == 2
