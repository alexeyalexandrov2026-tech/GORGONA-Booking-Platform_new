"""Versioned agreement contracts (ADR-0020 E3; the interface calls them contracts).

A version holds what the business entered. Signing happens outside the platform:
the business attests it with `signed_outside_platform`; nothing is signed here.
An agreed version is never rewritten: amendments and terminations add versions.
The latest agreed revision stays in force while an amendment is only drafted and
until a recorded termination takes effect on its (possibly future) date.
"""

from datetime import date
from typing import Literal, Self
from uuid import UUID

from pydantic import AwareDatetime, Field, StrictInt, field_validator, model_validator

from gorgona_booking.business.contracts import Strict, Versioned

AgreementState = Literal["draft", "agreed", "terminated"]
Attestation = Literal["signed_outside_platform"]
ATTESTATION: Attestation = "signed_outside_platform"
_MAX_REVISION = 2_147_483_646


def _control(char: str, allowed: str = "") -> bool:
    """C0, DEL and C1 controls, which the database also refuses in single lines."""
    code = ord(char)
    return char not in allowed and (code < 32 or 127 <= code <= 159)


def _line(value: str) -> str:
    text = value.strip()
    if not text or any(_control(char) for char in text):
        raise ValueError("Provide nonblank text without control characters")
    return text


class DocumentReference(Strict):
    """One saved document version, for example the signed copy."""

    document_id: UUID
    revision: StrictInt = Field(ge=1, le=_MAX_REVISION)


class AgreementDraftInput(Versioned):
    expected_revision: StrictInt = Field(ge=0, le=_MAX_REVISION)
    counterparty_id: UUID
    legal_entity_id: UUID | None = None
    title: str = Field(min_length=1, max_length=200)
    number: str | None = Field(default=None, min_length=1, max_length=64)
    summary: str | None = Field(default=None, min_length=1, max_length=2000)
    effective_from: date | None = None
    effective_until: date | None = None
    document: DocumentReference | None = None

    @field_validator("title", "number")
    @classmethod
    def single_line(cls, value: str | None) -> str | None:
        return None if value is None else _line(value)

    @field_validator("summary")
    @classmethod
    def paragraph(cls, value: str | None) -> str | None:
        if value is None:
            return None
        text = value.strip()
        if not text or any(_control(char, "\n\t") for char in text):
            raise ValueError("Provide nonblank text without control characters")
        return text

    @model_validator(mode="after")
    def ordered_dates(self) -> Self:
        if (
            self.effective_from is not None
            and self.effective_until is not None
            and self.effective_until < self.effective_from
        ):
            raise ValueError("The end of the term cannot precede its start")
        return self


class AgreeInput(Versioned):
    expected_revision: StrictInt = Field(ge=1, le=_MAX_REVISION)
    signed_on: date
    # Checked by the command so a missing attestation has its own error code.
    attestation: str | None = Field(default=None, max_length=64)
    # The signed copy; when omitted the draft's document reference is kept.
    document: DocumentReference | None = None


class TerminateInput(Versioned):
    expected_revision: StrictInt = Field(ge=1, le=_MAX_REVISION)
    # The day the termination takes effect; it may be in the future.
    terminated_on: date


class AgreementView(Strict):
    schema_version: Literal[1] = 1
    business_id: UUID
    agreement_id: UUID
    counterparty_id: UUID
    legal_entity_id: UUID | None
    revision: int = Field(ge=1)
    state: AgreementState
    title: str
    number: str | None
    summary: str | None
    effective_from: date | None
    effective_until: date | None
    signed_on: date | None
    attestation: Attestation | None
    document: DocumentReference | None
    terminated_on: date | None
    # The latest agreed revision up to this one: the version in force (for a
    # termination, until `terminated_on`). None while the contract was never agreed.
    in_force_revision: int | None = Field(ge=1)
    # Set on a termination only: the agreed revision it ends.
    terminates_revision: int | None = Field(ge=1)
    created_at: AwareDatetime


class AgreementReceipt(Strict):
    agreement_id: UUID
    revision: int


class AgreementInForce(Strict):
    """The agreed version in force, also while an amendment is only drafted."""

    revision: int = Field(ge=1)
    title: str
    number: str | None
    effective_from: date | None
    effective_until: date | None
    signed_on: date


class AgreementSummary(Strict):
    agreement_id: UUID
    counterparty_id: UUID
    # The latest version; for an open amendment this is the unsigned draft.
    revision: int = Field(ge=1)
    state: AgreementState
    title: str
    number: str | None
    effective_from: date | None
    effective_until: date | None
    terminated_on: date | None
    in_force: AgreementInForce | None
    updated_at: AwareDatetime


class AgreementList(Strict):
    schema_version: Literal[1] = 1
    business_id: UUID
    counterparty_id: UUID
    # Agreements of this card and of duplicates merged into it.
    items: tuple[AgreementSummary, ...]
    next_cursor: UUID | None


class AgreementRevision(Strict):
    revision: int = Field(ge=1)
    state: AgreementState
    title: str
    signed_on: date | None
    terminated_on: date | None
    # A draft closed unsigned by the termination that followed it.
    abandoned: bool
    created_at: AwareDatetime


class AgreementHistory(Strict):
    schema_version: Literal[1] = 1
    business_id: UUID
    agreement_id: UUID
    items: tuple[AgreementRevision, ...]
    next_cursor: int | None
