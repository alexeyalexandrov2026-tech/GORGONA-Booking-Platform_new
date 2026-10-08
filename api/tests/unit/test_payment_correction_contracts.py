"""H3 payment correction contracts: an attested erroneous confirmation, never a refund."""

from typing import Any, get_args
from uuid import uuid7

import pytest
from pydantic import ValidationError

from gorgona_booking.business.financial_contracts import FinancialCommandReference
from gorgona_booking.business.ledger_contracts import (
    H_OWNED_SOURCE_KINDS,
    PaymentCorrectionPosting,
    SourceKindV2,
)
from gorgona_booking.business.settlement_contracts import (
    PaymentCorrectInput,
    PaymentRevisionView,
    PaymentVoidInput,
)


def _void(**changes: object) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "expected_sequence": 4,
        "attestation": "attested_erroneous_confirmation",
        "entry_date": "2026-10-04",
        "reason": "FAKE the bank never received this transfer",
        "evidence_source": "FAKE bank statement",
        **changes,
    }


def _correction(**changes: object) -> dict[str, Any]:
    replacement: dict[str, object] = {
        "amount": "60.00",
        "actual_external_date": "2026-10-03",
        "cash_account_id": str(uuid7()),
        "allocations": [{"obligation_id": str(uuid7()), "amount": "60.00"}],
    }
    return _void(**(replacement | changes))


def test_a_void_states_an_erroneous_confirmation_with_reason_and_evidence() -> None:
    body = PaymentVoidInput.model_validate(_void())
    assert (body.attestation, body.expected_sequence) == ("attested_erroneous_confirmation", 4)
    for bad in (
        {"attestation": "manual_attestation"},
        {"attestation": "attested_no_payment"},
        {"reason": ""},
        {"reason": "   "},
        {"reason": "FAKE\nsecond line"},
        {"evidence_source": "x" * 201},
        {"expected_sequence": 0},
        {"entry_date": "not a date"},
    ):
        with pytest.raises(ValidationError):
            PaymentVoidInput.model_validate(_void(**bad))
    for missing in ("reason", "evidence_source", "attestation", "entry_date"):
        body_without = _void()
        del body_without[missing]
        with pytest.raises(ValidationError):
            PaymentVoidInput.model_validate(body_without)


def test_a_correction_never_carries_a_new_external_identity() -> None:
    body = PaymentCorrectInput.model_validate(_correction())
    assert body.amount == "60.00"
    for identity in (
        {"external_reference": "FAKE-OTHER"},
        {"source_account_alias": "FAKE other bank"},
        {"direction": "payable"},
    ):
        with pytest.raises(ValidationError):
            PaymentCorrectInput.model_validate(_correction(**identity))
    # A void takes no replacement facts.
    with pytest.raises(ValidationError):
        PaymentVoidInput.model_validate(_void(amount="1.00"))


@pytest.mark.parametrize(
    "bad",
    [
        {"amount": "0.5.0"},
        {"amount": 60},
        {"amount": "-1.00"},
        {"allocations": []},
        {"allocations": [{"obligation_id": str(uuid7()), "amount": "1.0000"}]},
        {"actual_external_date": None},
        {"cash_account_id": "cash"},
    ],
)
def test_correction_amounts_are_exact_decimal_strings(bad: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        PaymentCorrectInput.model_validate(_correction(**bad))


def test_a_correction_names_each_obligation_once() -> None:
    obligation = str(uuid7())
    twice = [{"obligation_id": obligation, "amount": "30.00"}] * 2
    with pytest.raises(ValidationError, match="each obligation once"):
        PaymentCorrectInput.model_validate(_correction(allocations=twice))


def test_corrections_are_settlement_commands_after_their_first_event() -> None:
    reference = {"schema_version": 1, "book_id": str(uuid7()), "subject_id": str(uuid7())}
    for operation in ("settlement_payment_void", "settlement_payment_correct"):
        with pytest.raises(ValidationError):
            FinancialCommandReference.model_validate(
                reference | {"operation": operation, "revision": 1}
            )
        later = FinancialCommandReference.model_validate(
            reference | {"operation": operation, "revision": 5}
        )
        assert later.operation == operation


def test_correction_journals_are_their_own_h_owned_origin() -> None:
    assert "payment_correction" in H_OWNED_SOURCE_KINDS
    assert "payment_correction" in get_args(SourceKindV2)
    posting = PaymentCorrectionPosting.model_validate(
        {
            "entry_date": "2026-10-04",
            "currency": "USD",
            "source_id": f"{uuid7()}:2:reversal",
            "lines": [
                {"account_id": str(uuid7()), "side": "debit", "amount": "1.00"},
                {"account_id": str(uuid7()), "side": "credit", "amount": "1.00"},
            ],
        }
    )
    assert posting.source_kind == "payment_correction"


def test_a_voided_revision_has_no_replacement_facts() -> None:
    revision = PaymentRevisionView.model_validate(
        {
            "revision": 2,
            "sequence": 5,
            "kind": "voided",
            "amount": None,
            "actual_external_date": None,
            "entry_date": "2026-10-04",
            "cash_account_id": None,
            "attestation": "attested_erroneous_confirmation",
            "reason": "FAKE",
            "evidence_source": "FAKE",
            "reversal_entry_id": str(uuid7()),
            "entry_id": None,
            "recorded_by": str(uuid7()),
            "recorded_at": "2026-10-04T10:00:00+00:00",
            "allocations": [],
        }
    )
    assert (revision.kind, revision.allocations) == ("voided", ())
    with pytest.raises(ValidationError):
        PaymentRevisionView.model_validate({**revision.model_dump(mode="json"), "revision": 1})
