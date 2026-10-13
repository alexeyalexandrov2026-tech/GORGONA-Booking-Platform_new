"""J2 contracts: posting rules, receipts, exact decimal counts and the stock journal origin."""

from datetime import date
from typing import get_args
from uuid import uuid7

import pytest
from pydantic import ValidationError

from gorgona_booking.business.ledger_contracts import (
    H_OWNED_SOURCE_KINDS,
    FinancialPosting,
    SourceKindV2,
    StockPosting,
)
from gorgona_booking.business.stock_contracts import (
    MAX_QUANTITY,
    PostingRulesInput,
    ReceiptInput,
    from_count,
    to_count,
)
from gorgona_booking.db import financial_guard

ACCOUNTS = ("inventory", "receipt", "opening", "surplus", "consumption", "loss", "difference")


def test_counts_are_exact_decimal_strings() -> None:
    assert to_count("12.5", 1, MAX_QUANTITY) == 125
    assert to_count("3", 0, MAX_QUANTITY) == 3
    assert to_count("0.001", 3, MAX_QUANTITY) == 1
    assert to_count("999999999999", 0, MAX_QUANTITY) == MAX_QUANTITY
    assert to_count("0", 2, MAX_QUANTITY, zero=True) == 0
    assert [from_count(125, 1), from_count(3, 0), from_count(1, 3)] == ["12.5", "3", "0.001"]
    assert [from_count(0, 2), from_count(3499, 2)] == ["0.00", "34.99"]
    # Extra decimals and zero are refused, never rounded; so is a count above the limit.
    for text, scale in (("1.25", 1), ("1.0", 0), ("0", 1), ("0.0", 1), ("1000000000000", 0)):
        with pytest.raises(ValueError, match=r"decimal|range"):
            to_count(text, scale, MAX_QUANTITY)


def rules(**changes: object) -> dict[str, object]:
    return {
        "expected_revision": 0,
        **{f"{name}_account_id": str(uuid7()) for name in ACCOUNTS},
        **changes,
    }


def test_posting_rules_keep_the_inventory_account_apart() -> None:
    body = rules()
    assert PostingRulesInput.model_validate(body).expected_revision == 0
    # The other accounts may coincide with each other, never with the inventory account.
    PostingRulesInput.model_validate({**body, "loss_account_id": body["difference_account_id"]})
    for name in ACCOUNTS[1:]:
        with pytest.raises(ValidationError):
            PostingRulesInput.model_validate(
                {**body, f"{name}_account_id": body["inventory_account_id"]}
            )
    for change in ({"note": "x"}, {"expected_revision": -1}, {"schema_version": 2}):
        with pytest.raises(ValidationError):
            PostingRulesInput.model_validate({**body, **change})
    with pytest.raises(ValidationError):
        PostingRulesInput.model_validate(
            {name: value for name, value in body.items() if name != "surplus_account_id"}
        )


def receipt(**changes: object) -> dict[str, object]:
    return {
        "kind": "receipt",
        "reason": "purchase",
        "legal_entity_id": str(uuid7()),
        "place_id": str(uuid7()),
        "document_date": "2026-10-01",
        "lines": [{"item_id": str(uuid7()), "quantity": "1.5", "amount": "3.00"}],
        **changes,
    }


def test_receipt_input_accepts_the_documented_shape() -> None:
    body = ReceiptInput.model_validate(
        receipt(supplier_id=str(uuid7()), supplier_document=" INV-7 ")
    )
    assert (body.kind, body.document_date, body.supplier_document) == (
        "receipt",
        date(2026, 10, 1),
        "INV-7",
    )
    assert (body.lines[0].quantity, body.lines[0].amount) == ("1.5", "3.00")
    assert ReceiptInput.model_validate(receipt(reason="surplus")).supplier_id is None


@pytest.mark.parametrize(
    "change",
    [
        {"kind": "write_off"},
        {"reason": "used"},
        {"lines": []},
        {"lines": [{"item_id": str(uuid7()), "quantity": "1", "amount": "1"}] * 101},
        {"lines": [{"item_id": str(uuid7()), "quantity": "-1", "amount": "1"}]},
        {"lines": [{"item_id": str(uuid7()), "quantity": "1e3", "amount": "1"}]},
        {"lines": [{"item_id": str(uuid7()), "quantity": "01", "amount": "1"}]},
        {"lines": [{"item_id": str(uuid7()), "quantity": "1", "amount": "1.0000"}]},
        {"lines": [{"item_id": str(uuid7()), "quantity": "1", "amount": 1}]},
        {"lines": [{"item_id": str(uuid7()), "quantity": "1"}]},
        {"lines": [{"item_id": str(uuid7()), "quantity": "1", "amount": "1", "note": "x"}]},
        {"reason": "surplus", "supplier_id": str(uuid7())},
        {"reason": "opening_balance", "supplier_document": "INV-1"},
        {"supplier_document": "x" * 65},
        {"supplier_document": "two\nlines"},
        {"document_date": "2026-13-01"},
        {"note": "x"},
        {"schema_version": 2},
    ],
)
def test_receipt_input_is_strict(change: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        ReceiptInput.model_validate(receipt(**change))


def test_stock_is_a_journal_origin_with_its_own_posting() -> None:
    assert "stock" in get_args(SourceKindV2)
    # Package H does not own it: the stock guard and the stock service refuse its reversal.
    assert "stock" not in H_OWNED_SOURCE_KINDS
    assert StockPosting in get_args(FinancialPosting)
    posting = StockPosting.model_validate(
        {
            "entry_date": "2026-10-01",
            "currency": "USD",
            "source_id": str(uuid7()),
            "lines": [
                {"account_id": str(uuid7()), "side": "debit", "amount": "1.00"},
                {"account_id": str(uuid7()), "side": "credit", "amount": "1.00"},
            ],
        }
    )
    assert posting.source_kind == "stock"
    approved = {(check.table, check.name): check.expression for check in financial_guard._CHECKS}
    expression = approved[("journal_entries", "journal_entries_source_kind_check")]
    assert expression.endswith("'credit_void'::text, 'stock'::text]))")
