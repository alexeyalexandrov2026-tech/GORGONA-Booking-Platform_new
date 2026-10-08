"""Settlement contracts are finite, exact and carry no financial body in receipts."""

from typing import Any
from uuid import uuid7

import pytest
from pydantic import ValidationError

from gorgona_booking.business.financial_contracts import FinancialCommandReference
from gorgona_booking.business.settlement_contracts import (
    PaymentConfirmInput,
    SettlementActionInput,
    SettlementCancelInput,
    SettlementPrepareInput,
    SettlementReceipt,
    SettlementReleaseInput,
)
from gorgona_booking.business.settlements import _FOLLOWS, _phase


def prepare(**changes: Any) -> dict[str, Any]:
    return {
        "expected_sequence": 0,
        "direction": "receivable",
        "counterparty_id": str(uuid7()),
        "currency": "USD",
        "allocations": [{"obligation_id": str(uuid7()), "amount": "70.00"}],
        **changes,
    }


def test_prepare_is_a_single_strict_creation() -> None:
    body = SettlementPrepareInput.model_validate(prepare())
    assert body.allocations[0].amount == "70.00"
    obligation = str(uuid7())
    cases: tuple[dict[str, Any], ...] = (
        {"expected_sequence": 1},
        {"expected_sequence": True},
        {"direction": "transfer"},
        {"currency": "usd"},
        {"allocations": []},
        {"allocations": [{"obligation_id": obligation, "amount": 70}]},
        {"allocations": [{"obligation_id": obligation, "amount": "-1"}]},
        {"allocations": [{"obligation_id": obligation, "amount": "1e3"}]},
        {"allocations": [{"obligation_id": obligation, "amount": "1"}] * 2},
        {"provider_status": "paid"},
        {"schema_version": "1"},
    )
    for changes in cases:
        with pytest.raises(ValidationError):
            SettlementPrepareInput.model_validate(prepare(**changes))


def test_actions_need_the_expected_sequence_and_nothing_else() -> None:
    assert SettlementActionInput(expected_sequence=1).expected_sequence == 1
    for bad in (0, True, "1", 1.0):
        with pytest.raises(ValidationError):
            SettlementActionInput.model_validate({"expected_sequence": bad})
    with pytest.raises(ValidationError):
        SettlementActionInput.model_validate({"expected_sequence": 1, "amount": "1.00"})
    assert (
        SettlementCancelInput(expected_sequence=1, reason=" FAKE reason ").reason == "FAKE reason"
    )


def test_an_attested_release_states_reason_and_evidence_together() -> None:
    assert SettlementReleaseInput(expected_sequence=3).resolution is None
    complete = SettlementReleaseInput(
        expected_sequence=4,
        resolution="attested_no_payment",
        reason="FAKE rejected by the bank",
        evidence_source="FAKE statement",
    )
    assert complete.evidence_source == "FAKE statement"
    for changes in (
        {"resolution": "attested_no_payment"},
        {"resolution": "attested_no_payment", "reason": "FAKE"},
        {"reason": "FAKE"},
        {"evidence_source": "FAKE"},
        {"resolution": "timeout", "reason": "FAKE", "evidence_source": "FAKE"},
        {"resolution": "attested_no_payment", "reason": "a\nb", "evidence_source": "FAKE"},
    ):
        with pytest.raises(ValidationError):
            SettlementReleaseInput.model_validate({"expected_sequence": 4, **changes})


def test_settlement_recovery_references_are_minimal_and_possible() -> None:
    reference = {"book_id": str(uuid7()), "subject_id": str(uuid7())}
    first = FinancialCommandReference.model_validate(
        reference | {"operation": "settlement_prepare", "revision": 1}
    )
    assert first.operation == "settlement_prepare"
    with pytest.raises(ValidationError):
        FinancialCommandReference.model_validate(
            reference | {"operation": "settlement_prepare", "revision": 2}
        )
    for operation in (
        "settlement_approve",
        "settlement_reserve",
        "settlement_sent",
        "settlement_confirm",
        "settlement_release",
        "settlement_cancel",
        "settlement_payment_void",
        "settlement_payment_correct",
    ):
        with pytest.raises(ValidationError):
            FinancialCommandReference.model_validate(
                reference | {"operation": operation, "revision": 1}
            )
        later = FinancialCommandReference.model_validate(
            reference | {"operation": operation, "revision": 2}
        )
        assert later.revision == 2
    with pytest.raises(ValidationError):
        FinancialCommandReference.model_validate(
            reference | {"operation": "settlement_pay", "revision": 2}
        )
    receipt = SettlementReceipt(book_id=uuid7(), settlement_id=uuid7(), sequence=3)
    assert set(receipt.model_dump()) == {"book_id", "settlement_id", "sequence"}


def test_phase_follows_the_strongest_recorded_fact() -> None:
    assert _phase(["prepared"]) == "prepared"
    assert _phase(["prepared", "approved"]) == "approved"
    assert _phase(["prepared", "approved", "reserved"]) == "reserved"
    assert _phase(["prepared", "approved", "reserved", "sent"]) == "sent"
    assert _phase(["prepared", "approved", "reserved", "sent", "released"]) == "released"
    assert _phase(["prepared", "cancelled"]) == "cancelled"
    # A reserve is released from reserved or sent only. Nothing follows a cancel; after a
    # release only an erroneous payment can be voided, never corrected or confirmed.
    assert _FOLLOWS["released"] == ("reserved", "sent")
    assert _FOLLOWS["cancelled"] == ("prepared", "approved")
    assert all("cancelled" not in states for states in _FOLLOWS.values())
    assert [kind for kind, states in _FOLLOWS.items() if "released" in states] == ["payment_voided"]
    assert _FOLLOWS["payment_corrected"] == ("reserved", "sent")


def test_a_confirmation_is_a_manual_attestation_with_exact_allocations() -> None:
    obligation = str(uuid7())
    confirmation: dict[str, Any] = {
        "expected_sequence": 3,
        "amount": "40.00",
        "actual_external_date": "2026-10-02",
        "entry_date": "2026-10-02",
        "cash_account_id": str(uuid7()),
        "source_account_alias": " FAKE bank account ",
        "external_reference": "FAKE-TXN-1",
        "attestation": "manual_attestation",
        "allocations": [{"obligation_id": obligation, "amount": "40.00"}],
    }
    body = PaymentConfirmInput.model_validate(confirmation)
    assert body.source_account_alias == "FAKE bank account"
    cases: tuple[dict[str, Any], ...] = (
        {"attestation": "provider_verified"},
        {"attestation": None},
        {"external_reference": " "},
        {"external_reference": "a\nb"},
        {"source_account_alias": ""},
        {"amount": 40},
        {"amount": "40.0000"},
        {"allocations": []},
        {"allocations": [{"obligation_id": obligation, "amount": "20.00"}] * 2},
        {"expected_sequence": 0},
        {"provider_charge_id": "ch_FAKE"},
        {"fx_rate": "1.1"},
    )
    for changes in cases:
        with pytest.raises(ValidationError):
            PaymentConfirmInput.model_validate(confirmation | changes)
    for field in ("attestation", "external_reference", "source_account_alias", "entry_date"):
        with pytest.raises(ValidationError):
            PaymentConfirmInput.model_validate(
                {key: value for key, value in confirmation.items() if key != field}
            )
