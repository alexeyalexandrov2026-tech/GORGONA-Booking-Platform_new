"""Manually declared provider-admission metadata; never provider permission.

H4 has no operational approval state and accepts no credential fields. Evidence
references are opaque, manually supplied text; they are never fetched or verified.
"""

import re
from typing import Literal, Self
from uuid import UUID

from pydantic import AwareDatetime, Field, StrictInt, field_validator, model_validator

from gorgona_booking.business.contracts import Strict, Versioned
from gorgona_booking.business.ledger_contracts import single_line_text

AdmissionState = Literal["draft", "submitted", "withdrawn"]
AdmissionAssessment = Literal["not_checked", "suspended", "unsupported"]
RequestedOperation = Literal["charge", "refund", "transfer", "payout"]
AdmissionCommandKind = Literal["admission_draft", "admission_submit", "admission_withdraw"]
MAX_REVISION = 2_147_483_646
# Refuse recognizable credential material; opaque references do not prove eligibility.
# This predicate also lives in the packaged SQL admission_safe_text() CHECK helper.
_CREDENTIAL = re.compile(
    r"((^|[^A-Za-z0-9_])((sk|pk|rk)_|whsec_)|Bearer\s+|-----BEGIN[ -]|"
    r"(password|secret|token|api[_ -]?key|authorization)\s*[:=]|://[^/@\s]+:[^/@\s]+@)",
    re.IGNORECASE,
)


def metadata_text(value: str | None) -> str | None:
    clean = single_line_text(value)
    if clean is not None and _CREDENTIAL.search(clean):
        raise ValueError("Provide a private opaque reference, never credentials or secret material")
    return clean


class OperationalCapabilities(Strict):
    charge: Literal[False] = False
    refund: Literal[False] = False
    transfer: Literal[False] = False
    payout: Literal[False] = False

    @field_validator("charge", "refund", "transfer", "payout", mode="before")
    @classmethod
    def false_boolean_only(cls, value: object) -> object:
        if type(value) is not bool or value:
            raise ValueError("Operational capabilities are false")
        return value


class AdmissionDraftInput(Versioned):
    expected_revision: StrictInt = Field(ge=0, le=MAX_REVISION)
    provider: Literal["stripe_connect"] = "stripe_connect"
    country: str = Field(pattern=r"^[A-Z]{2}$")
    business_activity: str = Field(min_length=1, max_length=500)
    requested_operation: RequestedOperation
    assessment: AdmissionAssessment = "not_checked"
    account_reference: str | None = Field(
        default=None, min_length=1, max_length=160, pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,159}$"
    )
    evidence_references: tuple[str, ...] = Field(default=(), max_length=8)
    notes: str | None = Field(default=None, min_length=1, max_length=2000)

    @field_validator("business_activity", "account_reference", "notes")
    @classmethod
    def safe_text(cls, value: str | None) -> str | None:
        return metadata_text(value)

    @field_validator("evidence_references")
    @classmethod
    def bounded_references(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        cleaned = tuple(metadata_text(reference) for reference in value)
        if any(reference is None or len(reference) > 256 for reference in cleaned):
            raise ValueError("An evidence reference contains 1 to 256 characters")
        result = tuple(reference for reference in cleaned if reference is not None)
        if len(result) != len(set(result)):
            raise ValueError("Provide each evidence reference once")
        return result


class AdmissionActionInput(Versioned):
    expected_revision: StrictInt = Field(ge=1, le=MAX_REVISION)


class AdmissionView(Versioned):
    business_id: UUID
    book_id: UUID
    request_id: UUID
    revision: StrictInt = Field(ge=1, le=MAX_REVISION + 1)
    state: AdmissionState
    provider: Literal["stripe_connect"]
    country: str
    business_activity: str
    requested_operation: RequestedOperation
    assessment: AdmissionAssessment
    account_reference: str | None
    evidence_references: tuple[str, ...]
    notes: str | None
    evidence_status: Literal["manually_provided_unverified"] = "manually_provided_unverified"
    operational_capabilities: OperationalCapabilities = Field(
        default_factory=OperationalCapabilities
    )
    created_at: AwareDatetime


class AdmissionList(Versioned):
    business_id: UUID
    book_id: UUID
    items: tuple[AdmissionView, ...]
    next_after: UUID | None


class AdmissionReceipt(Versioned):
    book_id: UUID
    request_id: UUID
    revision: StrictInt = Field(ge=1, le=MAX_REVISION + 1)


class AdmissionCommandReference(Versioned):
    operation: AdmissionCommandKind
    book_id: UUID
    subject_id: UUID
    revision: StrictInt = Field(ge=1, le=MAX_REVISION + 1)

    @model_validator(mode="after")
    def transition_revision(self) -> Self:
        if self.operation != "admission_draft" and self.revision < 2:
            raise ValueError("A submit or withdrawal follows an existing request revision")
        return self


class AdmissionCommandStatus(Versioned):
    business_id: UUID
    key: str
    operation: AdmissionCommandKind
    state: Literal["committed", "unresolved", "cancelled"]
