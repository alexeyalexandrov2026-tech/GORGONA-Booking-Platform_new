"""H3 credit void contracts: an attested erroneous credit, never a refund reversal."""

from typing import Any, get_args
from uuid import uuid7

import pytest
from pydantic import ValidationError

from gorgona_booking.business.financial_contracts import (
    CreditNoteView,
    CreditVoidInput,
    FinancialCommandReference,
)
from gorgona_booking.business.ledger_contracts import (
    H_OWNED_SOURCE_KINDS,
    CreditVoidPosting,
    SourceKindV2,
)


def _void(**changes: object) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "expected_revision": 2,
        "entry_date": "2026-10-04",
        "attestation": "attested_erroneous_credit",
        "reason": "FAKE wrong customer",
        "evidence_source": "FAKE ticket",
        **changes,
    }


def test_a_void_needs_an_attestation_reason_and_evidence() -> None:
    assert CreditVoidInput.model_validate(_void()).expected_revision == 2
    for bad in (
        {"expected_revision": 1},
        {"attestation": "confirmed_account_treatment"},
        {"reason": " "},
        {"reason": "FAKE\nsecond line"},
        {"evidence_source": "x" * 201},
        {"refund_control_account_id": str(uuid7())},
    ):
        with pytest.raises(ValidationError):
            CreditVoidInput.model_validate(_void(**bad))


def _view(**changes: object) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "business_id": str(uuid7()),
        "book_id": str(uuid7()),
        "document_id": str(uuid7()),
        "revision": 3,
        "state": "voided",
        "credited_obligation_id": str(uuid7()),
        "direction": "receivable",
        "counterparty_id": str(uuid7()),
        "counterparty_revision": 1,
        "currency": "USD",
        "minor_units": 2,
        "credit_date": "2026-10-03",
        "due_date": None,
        "control_account_id": str(uuid7()),
        "title": "FAKE",
        "number": "FAKE-1",
        "lines": [
            {
                "line_id": str(uuid7()),
                "credited_line_id": str(uuid7()),
                "counter_account_id": str(uuid7()),
                "description": "FAKE",
                "amount": "10.00",
            }
        ],
        "total": "10.00",
        "entry_id": str(uuid7()),
        "issued_on": "2026-10-03",
        "attestation": "confirmed_account_treatment",
        "applied": "10.00",
        "refund": "0.00",
        "refund_control_account_id": None,
        "refund_obligation_id": None,
        "created_at": "2026-10-04T10:00:00+00:00",
        "void_entry_id": str(uuid7()),
        "voided_on": "2026-10-04",
        "void_reason": "FAKE",
        "void_evidence_source": "FAKE",
        **changes,
    }


def test_exactly_a_voided_credit_states_its_void() -> None:
    assert CreditNoteView.model_validate(_view()).state == "voided"
    with pytest.raises(ValidationError, match="void journal"):
        CreditNoteView.model_validate(_view(void_entry_id=None))
    with pytest.raises(ValidationError, match="void journal"):
        CreditNoteView.model_validate(_view(state="issued", revision=2))


def test_a_void_is_a_document_command_and_its_own_journal_origin() -> None:
    reference = {"schema_version": 1, "book_id": str(uuid7()), "subject_id": str(uuid7())}
    with pytest.raises(ValidationError):
        FinancialCommandReference.model_validate(
            reference | {"operation": "credit_void", "revision": 1}
        )
    assert (
        FinancialCommandReference.model_validate(
            reference | {"operation": "credit_void", "revision": 3}
        ).operation
        == "credit_void"
    )
    assert "credit_void" in H_OWNED_SOURCE_KINDS
    assert "credit_void" in get_args(SourceKindV2)
    posting = CreditVoidPosting.model_validate(
        {
            "entry_date": "2026-10-04",
            "currency": "USD",
            "source_id": str(uuid7()),
            "lines": [
                {"account_id": str(uuid7()), "side": "debit", "amount": "1.00"},
                {"account_id": str(uuid7()), "side": "credit", "amount": "1.00"},
            ],
        }
    )
    assert posting.source_kind == "credit_void"
