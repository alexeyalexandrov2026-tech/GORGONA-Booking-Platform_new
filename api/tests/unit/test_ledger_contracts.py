"""Money and command boundaries of ADR-0023; no floating-point amounts."""

from datetime import date
from uuid import uuid7

import pytest
from pydantic import ValidationError

from gorgona_booking.business.ledger_contracts import (
    AccountInput,
    BookInput,
    EntryInput,
    JournalEntryList,
    JournalEntryListV2,
    ReopenInput,
    from_minor,
    month,
    to_minor,
)


@pytest.mark.parametrize(
    ("amount", "scale", "minor"),
    [
        ("123", 0, 123),
        ("0.01", 2, 1),
        ("12.3", 2, 1230),
        ("0.001", 3, 1),
        ("999999999999999.999", 3, 999999999999999999),
    ],
)
def test_exact_currency_minor_units(amount: str, scale: int, minor: int) -> None:
    assert to_minor(amount, scale) == minor
    assert to_minor(from_minor(minor, scale), scale) == minor
    assert from_minor(-minor, scale) == "-" + from_minor(minor, scale)


@pytest.mark.parametrize(
    ("amount", "scale"),
    [
        ("0", 2),
        ("-1", 2),
        ("01", 2),
        ("1e2", 2),
        ("1,000", 2),
        ("1.0", 0),
        ("0.001", 2),
        ("1000000000000000", 3),
        ("1.0000", 3),
        (" 1", 2),
        ("NaN", 2),
    ],
)
def test_invalid_or_out_of_range_amounts_are_refused(amount: str, scale: int) -> None:
    with pytest.raises(ValueError, match=r"amount|currency"):
        to_minor(amount, scale)


@pytest.mark.parametrize("value", ["2026-13", "2026-00", "2026-1", "2026-01-01", "0000-01"])
def test_invalid_month(value: str) -> None:
    with pytest.raises(ValueError, match="month"):
        month(value)


def test_command_boundaries() -> None:
    assert month("2026-10") == date(2026, 10, 1)
    with pytest.raises(ValidationError):
        BookInput(
            expected_revision=True,
            legal_entity_id=uuid7(),
            base_currency="USD",
            fiscal_year_start_month=1,
            accounting_start=date(2026, 1, 1),
        )
    for name in ["   ", "bad\nname", "bad\x85name"]:
        with pytest.raises(ValidationError):
            AccountInput(expected_revision=0, code="1000", type="asset", name=name)
    with pytest.raises(ValidationError):
        ReopenInput(expected_sequence=1, reason=" ")
    with pytest.raises(ValidationError):
        EntryInput(
            entry_date=date(2026, 1, 1),
            currency="USD",
            lines=(
                {"account_id": uuid7(), "side": "debit", "amount": 1.25},
                {"account_id": uuid7(), "side": "credit", "amount": "1.25"},
            ),
        )


def test_invoice_origin_is_an_explicit_v2_read_contract() -> None:
    payload = {
        "schema_version": 2,
        "business_id": uuid7(),
        "book_id": uuid7(),
        "items": [
            {
                "entry_id": uuid7(),
                "entry_date": "2026-10-01",
                "period": "2026-10",
                "currency": "USD",
                "source_kind": "invoice",
                "source_id": str(uuid7()),
                "memo": None,
                "total": "100.00",
                "reverses_entry_id": None,
                "reversed_by_entry_id": None,
                "created_at": "2026-10-06T12:00:00Z",
            }
        ],
        "next_cursor": None,
    }
    assert JournalEntryListV2.model_validate(payload).items[0].source_kind == "invoice"
    item: dict[str, object] = payload["items"][0]  # type: ignore[index]
    accrual = {**payload, "items": [{**item, "source_kind": "accrual"}]}
    assert JournalEntryListV2.model_validate(accrual).items[0].source_kind == "accrual"
    with pytest.raises(ValidationError):
        JournalEntryListV2.model_validate({**payload, "items": [{**item, "source_kind": "refund"}]})
    with pytest.raises(ValidationError):
        JournalEntryList.model_validate({**accrual, "schema_version": 1})
    for version in (1, True, 2.0, "2"):
        with pytest.raises(ValidationError):
            JournalEntryListV2.model_validate({**payload, "schema_version": version})
    with pytest.raises(ValidationError):
        JournalEntryList.model_validate({**payload, "schema_version": 1})
