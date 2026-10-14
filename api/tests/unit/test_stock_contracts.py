"""J2 to J4 contracts: posting rules, receipts, write-offs, transfers, returns, exact counts
and the stock origin.
"""

from datetime import date
from fractions import Fraction
from math import floor
from typing import get_args
from uuid import uuid7

import pytest
from pydantic import TypeAdapter, ValidationError

from gorgona_booking.business.ledger_contracts import (
    H_OWNED_SOURCE_KINDS,
    FinancialPosting,
    SourceKindV2,
    StockPosting,
)
from gorgona_booking.business.stock_contracts import (
    MAX_QUANTITY,
    DocumentInput,
    PostingRulesInput,
    ReceiptInput,
    ReturnInput,
    TransferInput,
    WriteOffInput,
    from_count,
    issue_value,
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


def test_an_issue_leaves_at_the_exact_moving_average() -> None:
    # value * quantity / held, half up; the whole quantity takes the whole value.
    assert issue_value(2001, 150, 40) == 534
    assert issue_value(1000, 3, 1) == 333
    assert issue_value(667, 2, 1) == 334
    assert issue_value(1, 2, 1) == 1
    assert issue_value(1, 3, 1) == 0
    assert issue_value(0, 5, 2) == 0
    assert issue_value(1000, 5, 5) == 1000
    # Exact where floating point is not: values and quantities at their limits.
    assert issue_value(10**18 - 1, 3, 1) == 333_333_333_333_333_333
    assert issue_value(10**18 - 1, 10**15 - 1, 10**12 - 1) == floor(
        Fraction((10**18 - 1) * (10**12 - 1), 10**15 - 1) + Fraction(1, 2)
    )
    # Every small case agrees with exact fractions and never takes more than there is.
    for held in range(1, 13):
        for value in range(31):
            assert issue_value(value, held, held) == value
            for quantity in range(1, held):
                amount = issue_value(value, held, quantity)
                assert amount == floor(Fraction(value * quantity, held) + Fraction(1, 2))
                assert 0 <= amount <= value


def write_off(**changes: object) -> dict[str, object]:
    return {
        "kind": "write_off",
        "reason": "used",
        "legal_entity_id": str(uuid7()),
        "place_id": str(uuid7()),
        "document_date": "2026-10-01",
        "lines": [{"item_id": str(uuid7()), "quantity": "1.5"}],
        **changes,
    }


def test_write_off_input_accepts_the_documented_shape() -> None:
    body = WriteOffInput.model_validate(write_off())
    assert (body.kind, body.reason, body.document_date) == ("write_off", "used", date(2026, 10, 1))
    assert body.lines[0].quantity == "1.5"
    for reason in ("damaged", "lost", "expired", "other"):
        assert WriteOffInput.model_validate(write_off(reason=reason)).reason == reason


@pytest.mark.parametrize(
    "change",
    [
        {"kind": "receipt"},
        {"reason": "purchase"},
        {"reason": "entry_error"},
        {"lines": []},
        {"lines": [{"item_id": str(uuid7()), "quantity": "1"}] * 101},
        {"lines": [{"item_id": str(uuid7()), "quantity": "-1"}]},
        {"lines": [{"item_id": str(uuid7()), "quantity": 1}]},
        # The database values a write-off; the command carries no amount.
        {"lines": [{"item_id": str(uuid7()), "quantity": "1", "amount": "1.00"}]},
        {"supplier_id": str(uuid7())},
        {"supplier_document": "INV-1"},
        {"document_date": "2026-13-01"},
        {"note": "x"},
        {"schema_version": 2},
    ],
)
def test_write_off_input_is_strict(change: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        WriteOffInput.model_validate(write_off(**change))


def transfer(**changes: object) -> dict[str, object]:
    return {
        "kind": "transfer",
        "legal_entity_id": str(uuid7()),
        "place_id": str(uuid7()),
        "to_place_id": str(uuid7()),
        "document_date": "2026-10-01",
        "lines": [{"item_id": str(uuid7()), "quantity": "1.5"}],
        **changes,
    }


def test_transfer_input_accepts_the_documented_shape() -> None:
    body = TransferInput.model_validate(transfer())
    assert (body.kind, body.document_date) == ("transfer", date(2026, 10, 1))
    assert body.place_id != body.to_place_id
    assert body.lines[0].quantity == "1.5"


@pytest.mark.parametrize(
    "change",
    [
        {"kind": "write_off"},
        {"lines": []},
        {"lines": [{"item_id": str(uuid7()), "quantity": "1"}] * 101},
        {"lines": [{"item_id": str(uuid7()), "quantity": "-1"}]},
        # A transfer moves no money and has one fixed reason of its own.
        {"lines": [{"item_id": str(uuid7()), "quantity": "1", "amount": "1.00"}]},
        {"reason": "relocation"},
        {"supplier_id": str(uuid7())},
        {"document_date": "2026-13-01"},
        {"note": "x"},
        {"schema_version": 2},
    ],
)
def test_transfer_input_is_strict(change: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        TransferInput.model_validate(transfer(**change))


def test_a_transfer_names_two_different_places() -> None:
    same = str(uuid7())
    with pytest.raises(ValidationError):
        TransferInput.model_validate(transfer(place_id=same, to_place_id=same))
    with pytest.raises(ValidationError):
        TransferInput.model_validate(
            {name: value for name, value in transfer().items() if name != "to_place_id"}
        )


def returned(**changes: object) -> dict[str, object]:
    return {
        "kind": "return",
        "reason": "supplier_return",
        "legal_entity_id": str(uuid7()),
        "place_id": str(uuid7()),
        "document_date": "2026-10-01",
        "source_document_id": str(uuid7()),
        "lines": [{"source_line_no": 1, "quantity": "1.5"}],
        **changes,
    }


def test_return_input_accepts_the_documented_shape() -> None:
    body = ReturnInput.model_validate(
        returned(supplier_id=str(uuid7()), supplier_document=" CN-1 ")
    )
    assert (body.kind, body.reason, body.supplier_document) == (
        "return",
        "supplier_return",
        "CN-1",
    )
    assert (body.lines[0].source_line_no, body.lines[0].quantity) == (1, "1.5")
    for reason in ("unused", "entry_error"):
        assert ReturnInput.model_validate(returned(reason=reason)).supplier_id is None
    several = returned(lines=[{"source_line_no": number, "quantity": "1"} for number in (3, 1, 2)])
    assert [line.source_line_no for line in ReturnInput.model_validate(several).lines] == [3, 1, 2]


@pytest.mark.parametrize(
    "change",
    [
        {"kind": "receipt"},
        {"reason": "purchase"},
        {"reason": "used"},
        {"lines": []},
        # One return names a source line once.
        {"lines": [{"source_line_no": 1, "quantity": "1"}] * 2},
        {"lines": [{"source_line_no": 0, "quantity": "1"}]},
        {"lines": [{"source_line_no": 101, "quantity": "1"}]},
        {"lines": [{"source_line_no": 1, "quantity": "-1"}]},
        {"lines": [{"quantity": "1"}]},
        # The material and the amounts come from the source line, never from the command.
        {"lines": [{"source_line_no": 1, "quantity": "1", "amount": "1.00"}]},
        {"lines": [{"source_line_no": 1, "quantity": "1", "item_id": str(uuid7())}]},
        # Only a return to the supplier names a supplier.
        {"reason": "unused", "supplier_id": str(uuid7())},
        {"reason": "entry_error", "supplier_document": "CN-1"},
        {"to_place_id": str(uuid7())},
        {"document_date": "2026-13-01"},
        {"note": "x"},
        {"schema_version": 2},
    ],
)
def test_return_input_is_strict(change: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        ReturnInput.model_validate(returned(**change))


def test_a_return_names_its_source_document() -> None:
    with pytest.raises(ValidationError):
        ReturnInput.model_validate(
            {name: value for name, value in returned().items() if name != "source_document_id"}
        )


def test_shares_of_a_source_line_add_up_to_its_amount() -> None:
    # Every return takes its share of what is left of the line, so however a line is
    # returned in parts, no share exceeds what is left and the parts give back its amount.
    for quantity in range(1, 9):
        for amount in range(40):
            for step in range(1, quantity + 1):
                left_quantity, left_amount, shares = quantity, amount, []
                while left_quantity:
                    part = min(step, left_quantity)
                    share = issue_value(left_amount, left_quantity, part)
                    assert 0 <= share <= left_amount
                    left_quantity, left_amount = left_quantity - part, left_amount - share
                    shares.append(share)
                assert sum(shares) == amount


def test_a_document_command_names_its_kind() -> None:
    command: TypeAdapter[ReceiptInput | WriteOffInput | TransferInput | ReturnInput] = TypeAdapter(
        DocumentInput
    )
    assert isinstance(command.validate_python(receipt()), ReceiptInput)
    assert isinstance(command.validate_python(write_off()), WriteOffInput)
    assert isinstance(command.validate_python(transfer()), TransferInput)
    assert isinstance(command.validate_python(returned()), ReturnInput)
    unnamed = {name: value for name, value in receipt().items() if name != "kind"}
    for body in (unnamed, receipt(kind="return"), write_off(kind="receipt"), transfer(kind="x")):
        with pytest.raises(ValidationError):
            command.validate_python(body)


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
