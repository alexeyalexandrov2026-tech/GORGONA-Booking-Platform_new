"""Admission declarations cannot become operational provider permissions."""

from typing import Any
from uuid import uuid7

import pytest
from pydantic import ValidationError

from gorgona_booking.business.provider_admission_contracts import (
    AdmissionActionInput,
    AdmissionCommandReference,
    AdmissionDraftInput,
    AdmissionReceipt,
    OperationalCapabilities,
)


def draft(**changes: Any) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "expected_revision": 0,
        "provider": "stripe_connect",
        "country": "US",
        "business_activity": "FAKE declared activity",
        "requested_operation": "charge",
        "account_reference": "FAKE-private-account",
        "evidence_references": ["FAKE-evidence-1"],
        "notes": "FAKE private note",
        **changes,
    }


def test_admission_declaration_is_bounded_and_never_approved() -> None:
    assert AdmissionDraftInput.model_validate(draft()).assessment == "not_checked"
    assert (
        AdmissionDraftInput.model_validate(draft(assessment="unsupported")).assessment
        == "unsupported"
    )
    cases = (
        {"expected_revision": True},
        {"expected_revision": 1.0},
        {"schema_version": True},
        {"provider": "other"},
        {"country": "usa"},
        {"assessment": "approved"},
        {"assessment": "test_access"},
        {"requested_operation": "enable"},
        {"business_activity": " \t "},
        {"business_activity": "   "},
        {"business_activity": "\u00a0"},
        {"evidence_references": ["FAKE"] * 2},
        {"evidence_references": [str(n) for n in range(9)]},
        {"operational_capabilities": {"charge": True}},
        {"credentials": "FAKE"},
        {"notes": "password=FAKE-password"},
        {"account_reference": "sk_live_FAKE0123456789"},
        {"evidence_references": ["https://fake.invalid/?api_key=FAKE"]},
    )
    for changes in cases:
        with pytest.raises(ValidationError):
            AdmissionDraftInput.model_validate(draft(**changes))


def test_action_and_reference_operations_are_finite() -> None:
    assert AdmissionActionInput(expected_revision=1).expected_revision == 1
    with pytest.raises(ValidationError):
        AdmissionActionInput.model_validate({"expected_revision": 1, "assessment": "approved"})
    reference = {"book_id": str(uuid7()), "subject_id": str(uuid7()), "revision": 1}
    assert AdmissionCommandReference.model_validate({**reference, "operation": "admission_draft"})
    for operation in ("invoice_issue", "settlement_confirm", "provider_enable", "admission_submit"):
        with pytest.raises(ValidationError):
            AdmissionCommandReference.model_validate({**reference, "operation": operation})
    assert AdmissionCommandReference.model_validate(
        {**reference, "revision": 2, "operation": "admission_submit"}
    )


def test_capabilities_and_receipts_carry_no_private_metadata() -> None:
    capabilities = OperationalCapabilities()
    assert capabilities.model_dump() == dict.fromkeys(
        ("charge", "refund", "transfer", "payout"), False
    )
    for value in (True, 0, "false", None):
        with pytest.raises(ValidationError):
            OperationalCapabilities.model_validate({"charge": value})
    receipt = AdmissionReceipt(book_id=uuid7(), request_id=uuid7(), revision=1)
    assert set(receipt.model_dump()) == {"schema_version", "book_id", "request_id", "revision"}
    with pytest.raises(ValidationError):
        AdmissionReceipt.model_validate({**receipt.model_dump(), "notes": "FAKE"})
