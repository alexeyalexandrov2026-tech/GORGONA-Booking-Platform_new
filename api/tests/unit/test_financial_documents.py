"""H1 strict contracts and exact allocation arithmetic, before persistence."""

from typing import Any
from uuid import uuid7

import pytest
from pydantic import ValidationError

from gorgona_booking.business.financial_contracts import (
    FinancialCommandReference,
    InvoiceDraftInput,
    InvoiceIssueInput,
)
from gorgona_booking.business.financial_math import (
    FinancialAmountError,
    FinancialBalance,
    FinancialCapError,
    FinancialStateError,
    confirm,
    correct_confirmation,
    quantize_invoice,
    release,
    reserve,
    split_credit,
)
from gorgona_booking.business.ledger_contracts import MAX_MINOR


def draft(**changes: Any) -> InvoiceDraftInput:
    return InvoiceDraftInput.model_validate(
        {
            "schema_version": 1,
            "expected_revision": 0,
            "direction": "receivable",
            "counterparty_id": str(uuid7()),
            "counterparty_revision": 1,
            "currency": "USD",
            "invoice_date": "2026-10-06",
            "due_date": "2026-10-16",
            "control_account_id": str(uuid7()),
            "title": " FAKE internal invoice ",
            "number": "FAKE-001",
            "lines": [
                {
                    "line_id": str(uuid7()),
                    "counter_account_id": str(uuid7()),
                    "description": "FAKE line",
                    "amount": "0.10",
                },
                {
                    "line_id": str(uuid7()),
                    "counter_account_id": str(uuid7()),
                    "description": "FAKE line",
                    "amount": "0.20",
                },
            ],
            **changes,
        }
    )


def test_invoice_uses_exact_minor_units_and_preserves_input() -> None:
    body = draft()
    result = quantize_invoice(body, 2)
    assert result.amounts_minor == (10, 20)
    assert result.principal_minor == 30
    assert body.lines[0].amount == "0.10"
    assert body.title == "FAKE internal invoice"


@pytest.mark.parametrize(("scale", "amount", "expected"), [(0, "125", 125), (3, "0.001", 1)])
def test_other_currency_scales(scale: int, amount: str, expected: int) -> None:
    body = draft()
    first = body.lines[0].model_copy(update={"amount": amount})
    body = body.model_copy(update={"lines": (first,)})
    assert quantize_invoice(body, scale).principal_minor == expected


@pytest.mark.parametrize("bad", [True, 1.0, "1", None])
def test_versions_are_real_integers(bad: Any) -> None:
    with pytest.raises(ValidationError):
        draft(schema_version=bad)
    with pytest.raises(ValidationError):
        draft(expected_revision=bad)
    with pytest.raises(ValidationError):
        draft(counterparty_revision=bad)


@pytest.mark.parametrize("bad", ["", "  ", "a\nb", "a\x7fb", "a\x85b"])
def test_financial_text_does_not_accept_blank_or_control_content(bad: str) -> None:
    with pytest.raises(ValidationError):
        draft(title=bad)


def test_invoice_date_and_unique_line_identity() -> None:
    with pytest.raises(ValidationError):
        draft(due_date="2026-10-05")
    first = draft().lines[0].model_dump(mode="json")
    with pytest.raises(ValidationError):
        draft(lines=[first, first])


def test_no_provider_status_extra_money_or_unknown_direction_in_draft() -> None:
    with pytest.raises(ValidationError):
        draft(provider_verified=True)
    with pytest.raises(ValidationError):
        draft(direction="refund")
    with pytest.raises(ValidationError):
        draft(lines=[])


@pytest.mark.parametrize("bad", ["1e2", "-1", "+1", "01", "0", "1.001", "1,00"])
def test_currency_amount_refuses_ambiguous_or_out_of_scale_values(bad: str) -> None:
    body = draft()
    first = body.lines[0].model_dump(mode="json") | {"amount": bad}
    with pytest.raises((ValidationError, FinancialAmountError)):
        quantize_invoice(draft(lines=[first]), 2)


@pytest.mark.parametrize("bad", [True, False, 1, 2.0, 4, -1])
def test_currency_scale_is_bounded_integer(bad: Any) -> None:
    with pytest.raises(FinancialAmountError):
        quantize_invoice(draft(), bad)


def test_invoice_total_cannot_exceed_the_sql_principal_limit() -> None:
    body = draft()
    lines = [line.model_dump(mode="json") | {"amount": str(MAX_MINOR)} for line in body.lines]
    with pytest.raises(FinancialAmountError):
        quantize_invoice(draft(lines=lines), 0)


def test_issue_attestation_is_explicit_and_reference_recovery_is_minimal() -> None:
    with pytest.raises(ValidationError):
        InvoiceIssueInput.model_validate({"expected_revision": 1, "entry_date": "2026-10-06"})
    command = InvoiceIssueInput(
        expected_revision=1,
        entry_date="2026-10-06",
        attestation="confirmed_account_treatment",
    )
    assert command.expected_revision == 1
    ref = {
        "schema_version": 1,
        "operation": "invoice_issue",
        "book_id": str(uuid7()),
        "subject_id": str(uuid7()),
        "revision": 2,
    }
    assert FinancialCommandReference.model_validate(ref).operation == "invoice_issue"
    for extra in ("amount", "memo", "external_reference", "token"):
        with pytest.raises(ValidationError):
            FinancialCommandReference.model_validate(ref | {extra: "private"})
    with pytest.raises(ValidationError):
        FinancialCommandReference.model_validate(ref | {"operation": "transfer"})


def test_competing_reserves_cannot_spend_one_principal_twice() -> None:
    initial = FinancialBalance(principal_minor=100)
    first = reserve(initial, 70)
    assert first.available_minor == 30
    with pytest.raises(FinancialCapError):
        reserve(first, 70)
    assert initial.available_minor == 100


def test_partial_confirmation_release_and_no_over_confirmation() -> None:
    held = reserve(FinancialBalance(principal_minor=100), 70)
    partial = confirm(held, 40)
    assert (partial.paid_minor, partial.reserved_minor, partial.available_minor) == (40, 30, 30)
    released = release(partial, 10)
    assert (released.paid_minor, released.reserved_minor, released.available_minor) == (40, 20, 40)
    with pytest.raises(FinancialCapError):
        confirm(released, 21)
    with pytest.raises(FinancialCapError):
        release(released, 21)


def test_mixed_credit_preserves_cash_and_creates_separate_refund_amount() -> None:
    paid = confirm(reserve(FinancialBalance(principal_minor=100), 70), 70)
    result = split_credit(paid, 50, uncredited_minor=100)
    assert (result.unpaid_minor, result.refund_minor) == (30, 20)
    assert result.balance.paid_minor == 70
    assert result.balance.credited_minor == 30
    assert result.balance.available_minor == 0
    second = split_credit(result.balance, 50, uncredited_minor=50)
    assert (second.unpaid_minor, second.refund_minor) == (0, 50)


def test_credit_requires_reserve_resolution_and_original_line_capacity() -> None:
    held = reserve(FinancialBalance(principal_minor=100), 1)
    with pytest.raises(FinancialStateError):
        split_credit(held, 50, uncredited_minor=100)
    with pytest.raises(FinancialCapError):
        split_credit(FinancialBalance(principal_minor=100), 51, uncredited_minor=50)


def test_effective_correction_restores_reserve_and_does_not_double_history() -> None:
    confirmed = confirm(reserve(FinancialBalance(principal_minor=100), 70), 70)
    replaced = correct_confirmation(confirmed, old_minor=70, new_minor=50)
    assert (replaced.paid_minor, replaced.reserved_minor, replaced.available_minor) == (50, 20, 30)
    voided = correct_confirmation(confirmed, old_minor=70, new_minor=0)
    assert (voided.paid_minor, voided.reserved_minor) == (0, 70)
    with pytest.raises(FinancialCapError):
        correct_confirmation(confirmed, old_minor=70, new_minor=71)


@pytest.mark.parametrize("bad", [True, 1.1, "1", 0, -1, MAX_MINOR + 1])
def test_money_allocation_is_a_positive_bounded_integer(bad: Any) -> None:
    initial = FinancialBalance(principal_minor=100)
    with pytest.raises(FinancialAmountError):
        reserve(initial, bad)
    with pytest.raises(FinancialAmountError):
        confirm(initial, bad)
    with pytest.raises(FinancialAmountError):
        release(initial, bad)


@pytest.mark.parametrize(
    "changes",
    [
        {"principal_minor": True},
        {"paid_minor": -1},
        {"paid_minor": 101},
        {"paid_minor": 50, "credited_minor": 25, "reserved_minor": 26},
    ],
)
def test_invalid_balance_is_not_representable(changes: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        FinancialBalance.model_validate({"principal_minor": 100, **changes})


def test_financial_document_gate_follows_fin03_and_requires_explicit_configuration() -> None:
    from gorgona_booking.business.modules import (
        BASELINE_MODULE_IDS,
        MODULE_REGISTRY_VERSION,
        MODULES_BY_ID,
        selection_problems,
    )
    from gorgona_booking.business.readiness_registry import SCENARIOS

    assert MODULE_REGISTRY_VERSION == 2
    scenario = next(item for item in SCENARIOS if item.id == "FIN-03")
    financial = MODULES_BY_ID["finance_documents"]
    assert financial.readiness == scenario.status
    assert not financial.enableable
    assert set(financial.depends_on) == {"finance", "counterparties"}
    assert "finance_documents" not in BASELINE_MODULE_IDS
    assert ("MODULE_NOT_READY", "finance_documents") in [
        (code, module_id)
        for code, module_id, _ in selection_problems(
            ("finance", "counterparties", "finance_documents")
        )
    ]
    assert MODULES_BY_ID["finance"].enableable


def test_financial_recovery_reference_rejects_an_impossible_issue_revision() -> None:
    with pytest.raises(ValidationError):
        FinancialCommandReference(
            operation="invoice_issue",
            book_id=uuid7(),
            subject_id=uuid7(),
            revision=1,
        )


def test_invoice_view_validates_actual_totals_and_issued_references() -> None:
    from datetime import UTC, datetime

    from gorgona_booking.business.financial_contracts import InvoiceDocumentView

    body = draft().model_dump(mode="json")
    body.pop("expected_revision")
    data = {
        **body,
        "business_id": str(uuid7()),
        "book_id": str(uuid7()),
        "document_id": str(uuid7()),
        "revision": 1,
        "state": "draft",
        "minor_units": 2,
        "total": "0.30",
        "entry_id": None,
        "obligation_id": None,
        "issued_on": None,
        "attestation": None,
        "created_at": datetime.now(UTC).isoformat(),
    }
    assert InvoiceDocumentView.model_validate(data).total == "0.30"
    issued = data | {
        "state": "issued",
        "entry_id": str(uuid7()),
        "obligation_id": str(uuid7()),
        "issued_on": "2026-10-06",
        "attestation": "confirmed_account_treatment",
    }
    with pytest.raises(ValidationError):
        InvoiceDocumentView.model_validate(issued)
    assert InvoiceDocumentView.model_validate(issued | {"revision": 2}).state == "issued"
    for changes in (
        {"schema_version": True},
        {"minor_units": True},
        {"total": "0.31"},
        {"state": "issued"},
        {"entry_id": str(uuid7())},
    ):
        with pytest.raises(ValidationError):
            InvoiceDocumentView.model_validate(data | changes)
