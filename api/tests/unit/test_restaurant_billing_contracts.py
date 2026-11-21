"""Unit contract checks for REST-01 Slice 4 split billing and refunds."""

from datetime import UTC, date, datetime
from uuid import uuid7

import pytest
from pydantic import ValidationError

from gorgona_booking.business import restaurant_billing as billing


def test_split_check_input_validation() -> None:
    l1, l2 = uuid7(), uuid7()
    by_items = billing.SplitCheckInput(
        schema_version=1,
        split_mode="by_items",
        shares=[
            billing.SplitShareInput(label="Seat 1", line_ids=[l1]),
            billing.SplitShareInput(label="Seat 2", line_ids=[l2]),
        ],
    )
    assert len(by_items.shares) == 2

    # Duplicate line across shares rejected
    with pytest.raises(ValidationError):
        billing.SplitCheckInput(
            schema_version=1,
            split_mode="by_items",
            shares=[
                billing.SplitShareInput(label="Seat 1", line_ids=[l1]),
                billing.SplitShareInput(label="Seat 2", line_ids=[l1]),
            ],
        )

    # by_amounts requires amount_minor and forbids line_ids
    with pytest.raises(ValidationError):
        billing.SplitCheckInput(
            schema_version=1,
            split_mode="by_amounts",
            shares=[billing.SplitShareInput(label="Half")],
        )

    with pytest.raises(ValidationError):
        billing.SplitCheckInput(
            schema_version=1,
            split_mode="by_amounts",
            shares=[billing.SplitShareInput(label="Half", amount_minor=500, line_ids=[l1])],
        )


def test_bill_and_refund_input_validation() -> None:
    with pytest.raises(ValidationError):
        billing.BillShareInput(
            schema_version=1,
            book_id=uuid7(),
            counterparty_id=uuid7(),
            receivable_account_id=uuid7(),
            revenue_account_id=uuid7(),
            invoice_date=date(2026, 10, 5),
            due_date=date(2026, 10, 1),
            title="Dinner",
            number="INV-1",
        )

    # Credit refund requires credit_date and number
    with pytest.raises(ValidationError):
        billing.RefundCheckInput(
            schema_version=1,
            share_no=1,
            amount_minor=500,
            method="credit",
            reason="Wrong dish",
        )

    # External refund requires reference and refunded_at
    ext = billing.RefundCheckInput(
        schema_version=1,
        share_no=1,
        amount_minor=500,
        method="external",
        reason="Cash adjustment",
        reference="CASH-REF-01",
        refunded_at=datetime(2026, 10, 1, 12, 0, tzinfo=UTC),
    )
    assert ext.reference == "CASH-REF-01"
