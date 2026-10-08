"""H3 credit-note contracts: explicit treatment, exact split and minimal recovery."""

from datetime import UTC, datetime
from typing import Any
from uuid import uuid7

import pytest
from pydantic import ValidationError

from gorgona_booking.business.financial_contracts import (
    CreditDraftInput,
    CreditIssueInput,
    CreditNoteView,
    FinancialCommandReference,
)
from gorgona_booking.business.ledger_contracts import (
    H_OWNED_SOURCE_KINDS,
    CreditPosting,
    JournalEntrySummary,
    JournalEntrySummaryV2,
)


def line(**changes: Any) -> dict[str, Any]:
    return {
        "line_id": str(uuid7()),
        "credited_line_id": str(uuid7()),
        "counter_account_id": str(uuid7()),
        "description": "FAKE goodwill reduction",
        "amount": "50.00",
        **changes,
    }


def draft(**changes: Any) -> CreditDraftInput:
    return CreditDraftInput.model_validate(
        {
            "schema_version": 1,
            "expected_revision": 0,
            "credited_obligation_id": str(uuid7()),
            "counterparty_revision": 1,
            "credit_date": "2026-10-03",
            "title": " FAKE credit note ",
            "number": "FAKE-CN-001",
            "lines": [line()],
            **changes,
        }
    )


def test_draft_names_the_credited_obligation_and_each_original_line() -> None:
    body = draft()
    assert body.title == "FAKE credit note"
    assert body.lines[0].reason is None
    for missing in ("credited_obligation_id", "counterparty_revision", "credit_date", "lines"):
        data = draft().model_dump(mode="json")
        data.pop(missing)
        with pytest.raises(ValidationError):
            CreditDraftInput.model_validate(data)
    without_origin = line()
    without_origin.pop("credited_line_id")
    with pytest.raises(ValidationError):
        draft(lines=[without_origin])


def test_draft_takes_no_direction_currency_or_control_of_its_own() -> None:
    # They follow the credited obligation; the client cannot choose another.
    for extra in ("direction", "currency", "control_account_id", "counterparty_id"):
        with pytest.raises(ValidationError):
            draft(**{extra: "receivable"})


def test_citation_needs_its_reason_and_text_is_single_line() -> None:
    with pytest.raises(ValidationError):
        draft(lines=[line(reference_entry_id=str(uuid7()))])
    cited = draft(lines=[line(reason=" FAKE recognized ", reference_entry_id=str(uuid7()))])
    assert cited.lines[0].reason == "FAKE recognized"
    for bad in ("", "a\nb", "a\x85b"):
        with pytest.raises(ValidationError):
            draft(lines=[line(reason=bad)])


def test_draft_line_identity_dates_and_size() -> None:
    first = line()
    with pytest.raises(ValidationError):
        draft(lines=[first, first])
    with pytest.raises(ValidationError):
        draft(due_date="2026-10-02")
    assert draft(due_date="2026-10-03").due_date is not None
    # Two control lines must still fit G's 200-line bound.
    with pytest.raises(ValidationError):
        draft(lines=[line() for _ in range(199)])
    assert len(draft(lines=[line() for _ in range(198)]).lines) == 198


@pytest.mark.parametrize("bad", ["1e2", "-1", "01", "1,00", 50])
def test_credit_amount_is_an_exact_decimal_string(bad: Any) -> None:
    # Zero has the decimal form; exact quantization at the currency scale refuses it.
    with pytest.raises(ValidationError):
        draft(lines=[line(amount=bad)])


def test_issue_attests_treatment_and_takes_only_a_refund_account() -> None:
    with pytest.raises(ValidationError):
        CreditIssueInput.model_validate({"expected_revision": 1, "entry_date": "2026-10-03"})
    plain = CreditIssueInput(
        expected_revision=1, entry_date="2026-10-03", attestation="confirmed_account_treatment"
    )
    assert plain.refund_control_account_id is None
    with pytest.raises(ValidationError):
        CreditIssueInput.model_validate(plain.model_dump(mode="json") | {"refund_minor": 2000})


def view(**changes: Any) -> dict[str, Any]:
    body = draft().model_dump(mode="json")
    body.pop("expected_revision")
    return {
        **body,
        "business_id": str(uuid7()),
        "book_id": str(uuid7()),
        "document_id": str(uuid7()),
        "revision": 1,
        "state": "draft",
        "direction": "receivable",
        "counterparty_id": str(uuid7()),
        "currency": "USD",
        "minor_units": 2,
        "due_date": None,
        "control_account_id": str(uuid7()),
        "total": "50.00",
        "entry_id": None,
        "issued_on": None,
        "attestation": None,
        "applied": None,
        "refund": None,
        "refund_control_account_id": None,
        "refund_obligation_id": None,
        "created_at": datetime.now(UTC).isoformat(),
        **changes,
    }


def issued(**changes: Any) -> dict[str, Any]:
    values: dict[str, Any] = {
        "revision": 2,
        "state": "issued",
        "entry_id": str(uuid7()),
        "issued_on": "2026-10-03",
        "attestation": "confirmed_account_treatment",
        "applied": "30.00",
        "refund": "20.00",
        "refund_control_account_id": str(uuid7()),
        "refund_obligation_id": str(uuid7()),
    }
    return view(**(values | changes))


def test_view_states_the_exact_split_and_its_refund_obligation() -> None:
    assert CreditNoteView.model_validate(view()).applied is None
    mixed = CreditNoteView.model_validate(issued())
    assert (mixed.applied, mixed.refund) == ("30.00", "20.00")
    unpaid = issued(
        applied="50.00", refund="0.00", refund_control_account_id=None, refund_obligation_id=None
    )
    assert CreditNoteView.model_validate(unpaid).refund == "0.00"
    for bad in (
        view(applied="50.00"),
        view(refund_obligation_id=str(uuid7())),
        issued(revision=1),
        issued(applied="30.00", refund="10.00"),
        issued(refund_obligation_id=None),
        issued(applied="50.00", refund="0.00"),
        issued(applied="30.0", refund="20.00"),
        issued(total="50.01"),
        issued(kind="credit_note"),
    ):
        with pytest.raises(ValidationError):
            CreditNoteView.model_validate(bad)


def test_recovery_reference_knows_credit_commands() -> None:
    reference = {
        "schema_version": 1,
        "operation": "credit_issue",
        "book_id": str(uuid7()),
        "subject_id": str(uuid7()),
        "revision": 2,
    }
    assert FinancialCommandReference.model_validate(reference).operation == "credit_issue"
    with pytest.raises(ValidationError):
        FinancialCommandReference.model_validate(reference | {"revision": 1})
    drafted = FinancialCommandReference.model_validate(
        reference | {"operation": "credit_draft", "revision": 1}
    )
    assert drafted.revision == 1
    with pytest.raises(ValidationError):
        FinancialCommandReference.model_validate(reference | {"amount": "20.00"})


def test_credit_journals_are_owned_by_h_and_need_view_version_two() -> None:
    assert "credit" in H_OWNED_SOURCE_KINDS
    posting = CreditPosting.model_validate(
        {
            "entry_date": "2026-10-03",
            "currency": "USD",
            "source_id": str(uuid7()),
            "lines": [
                {"account_id": str(uuid7()), "side": "debit", "amount": "1.00"},
                {"account_id": str(uuid7()), "side": "credit", "amount": "1.00"},
            ],
        }
    )
    assert posting.source_kind == "credit"
    summary = {
        "entry_id": str(uuid7()),
        "entry_date": "2026-10-03",
        "period": "2026-10",
        "currency": "USD",
        "source_kind": "credit",
        "source_id": "FAKE",
        "memo": None,
        "total": "1.00",
        "reverses_entry_id": None,
        "reversed_by_entry_id": None,
        "created_at": datetime.now(UTC).isoformat(),
    }
    assert JournalEntrySummaryV2.model_validate(summary).source_kind == "credit"
    with pytest.raises(ValidationError):
        JournalEntrySummary.model_validate(summary)
