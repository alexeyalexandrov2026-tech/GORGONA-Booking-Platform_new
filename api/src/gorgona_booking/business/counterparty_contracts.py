"""Versioned counterparty contracts (ADR-0020, E1).

A card holds what the business entered: nothing is looked up, completed or invented.
Matching only suggests duplicates; merges, "not a duplicate" decisions, separations and
links to booking customers are each confirmed by a person.
"""

import re
from typing import Annotated, Literal, Self
from uuid import UUID

from pydantic import AwareDatetime, Field, StrictBool, StrictInt, field_validator, model_validator

from gorgona_booking.business.contracts import Strict, Versioned

CounterpartyKind = Literal["person", "organization"]
CounterpartyRole = Literal["customer", "supplier", "contractor", "partner"]
CounterpartyState = Literal["active", "archived", "merged"]
MatchReason = Literal["email", "phone", "tax_id", "registration_number", "name"]
LinkBasis = Literal["email", "phone"]
STRONG_REASONS: frozenset[str] = frozenset({"email", "phone", "tax_id", "registration_number"})

_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_PHONE = re.compile(r"^\+?[0-9 ().-]{7,32}$")
_IDENTIFIER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9 ./-]{0,63}$")
_MAX_REVISION = 2_147_483_646


def _clean_text(value: str) -> str:
    text = value.strip()
    if not text or any(ord(char) < 32 or ord(char) == 127 for char in text):
        raise ValueError("Provide nonblank text without control characters")
    return text


def _clean_email(value: str) -> str:
    email = value.strip()
    if not _EMAIL.fullmatch(email) or any(ord(char) < 32 or ord(char) == 127 for char in email):
        raise ValueError("Provide a valid e-mail address")
    return email


def _clean_phone(value: str) -> str:
    phone = value.strip()
    digits = sum(char.isdigit() for char in phone)
    if not _PHONE.fullmatch(phone) or not 7 <= digits <= 15:
        raise ValueError("Provide a phone number with 7 to 15 digits")
    return phone


def _clean_identifier(value: str) -> str:
    identifier = value.strip()
    if not _IDENTIFIER.fullmatch(identifier):
        raise ValueError("Use letters, digits, spaces, dots, slashes or hyphens (at most 64)")
    return identifier


class ContactInput(Strict):
    name: str = Field(min_length=1, max_length=200)
    job_title: str | None = Field(default=None, min_length=1, max_length=200)
    email: str | None = Field(default=None, min_length=3, max_length=254)
    phone: str | None = Field(default=None, min_length=7, max_length=32)

    @field_validator("name", "job_title")
    @classmethod
    def text(cls, value: str | None) -> str | None:
        return None if value is None else _clean_text(value)

    @field_validator("email")
    @classmethod
    def email_address(cls, value: str | None) -> str | None:
        return None if value is None else _clean_email(value)

    @field_validator("phone")
    @classmethod
    def phone_number(cls, value: str | None) -> str | None:
        return None if value is None else _clean_phone(value)


class CounterpartyInput(Versioned):
    expected_revision: StrictInt = Field(ge=0, le=_MAX_REVISION)
    kind: CounterpartyKind
    display_name: str = Field(min_length=1, max_length=200)
    legal_name: str | None = Field(default=None, min_length=1, max_length=300)
    tax_id: str | None = Field(default=None, min_length=1, max_length=64)
    registration_number: str | None = Field(default=None, min_length=1, max_length=64)
    email: str | None = Field(default=None, min_length=3, max_length=254)
    phone: str | None = Field(default=None, min_length=7, max_length=32)
    roles: tuple[CounterpartyRole, ...] = Field(default=(), max_length=4)
    archived: StrictBool = False
    contacts: tuple[ContactInput, ...] = Field(default=(), max_length=20)

    @field_validator("display_name", "legal_name")
    @classmethod
    def text(cls, value: str | None) -> str | None:
        return None if value is None else _clean_text(value)

    @field_validator("tax_id", "registration_number")
    @classmethod
    def identifier(cls, value: str | None) -> str | None:
        return None if value is None else _clean_identifier(value)

    @field_validator("email")
    @classmethod
    def email_address(cls, value: str | None) -> str | None:
        return None if value is None else _clean_email(value)

    @field_validator("phone")
    @classmethod
    def phone_number(cls, value: str | None) -> str | None:
        return None if value is None else _clean_phone(value)

    @field_validator("roles")
    @classmethod
    def distinct_roles(cls, value: tuple[CounterpartyRole, ...]) -> tuple[CounterpartyRole, ...]:
        if len(set(value)) != len(value):
            raise ValueError("Select each role only once")
        return tuple(sorted(value))


class ContactView(Strict):
    position: int = Field(ge=1, le=20)
    name: str
    job_title: str | None
    email: str | None
    phone: str | None


class CounterpartyView(Strict):
    schema_version: Literal[1] = 1
    business_id: UUID
    counterparty_id: UUID
    kind: CounterpartyKind
    revision: int = Field(ge=1)
    display_name: str
    legal_name: str | None
    tax_id: str | None
    registration_number: str | None
    email: str | None
    phone: str | None
    roles: tuple[CounterpartyRole, ...]
    state: CounterpartyState
    merged_into: UUID | None
    contacts: tuple[ContactView, ...]
    created_at: AwareDatetime


class CounterpartySummary(Strict):
    counterparty_id: UUID
    kind: CounterpartyKind
    revision: int = Field(ge=1)
    display_name: str
    roles: tuple[CounterpartyRole, ...]
    state: CounterpartyState
    merged_into: UUID | None


class CounterpartyList(Strict):
    schema_version: Literal[1] = 1
    business_id: UUID
    items: tuple[CounterpartySummary, ...]
    next_cursor: UUID | None


class CounterpartyRevision(Strict):
    revision: int = Field(ge=1)
    state: CounterpartyState
    display_name: str
    created_at: AwareDatetime


class CounterpartyHistory(Strict):
    schema_version: Literal[1] = 1
    business_id: UUID
    counterparty_id: UUID
    items: tuple[CounterpartyRevision, ...]
    next_cursor: int | None


class CounterpartyReceipt(Strict):
    """What a save stores under its key: references only, never personal data."""

    counterparty_id: UUID
    revision: int


class MatchCheckInput(Versioned):
    display_name: str | None = Field(default=None, min_length=1, max_length=200)
    tax_id: str | None = Field(default=None, min_length=1, max_length=64)
    registration_number: str | None = Field(default=None, min_length=1, max_length=64)
    emails: tuple[str, ...] = Field(default=(), max_length=21)
    phones: tuple[str, ...] = Field(default=(), max_length=21)
    exclude_id: UUID | None = None

    @field_validator("display_name")
    @classmethod
    def text(cls, value: str | None) -> str | None:
        return None if value is None else _clean_text(value)

    @field_validator("tax_id", "registration_number")
    @classmethod
    def identifier(cls, value: str | None) -> str | None:
        return None if value is None else _clean_identifier(value)

    @field_validator("emails")
    @classmethod
    def email_addresses(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        return tuple(_clean_email(email) for email in value)

    @field_validator("phones")
    @classmethod
    def phone_numbers(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        return tuple(_clean_phone(phone) for phone in value)

    @model_validator(mode="after")
    def something_to_match(self) -> Self:
        if not (
            self.display_name
            or self.tax_id
            or self.registration_number
            or self.emails
            or self.phones
        ):
            raise ValueError("Provide at least one detail to check")
        return self


class MatchCandidate(Strict):
    counterparty_id: UUID
    kind: CounterpartyKind
    display_name: str
    state: CounterpartyState
    reasons: tuple[MatchReason, ...]
    strength: Literal["strong", "weak"]


class MatchList(Strict):
    schema_version: Literal[1] = 1
    business_id: UUID
    items: tuple[MatchCandidate, ...]


class MergeInput(Versioned):
    decision: Literal["merge"]
    into_id: UUID
    expected_revision: StrictInt = Field(ge=1, le=_MAX_REVISION)
    into_expected_revision: StrictInt = Field(ge=1, le=_MAX_REVISION)


class DistinctInput(Versioned):
    decision: Literal["distinct"]
    other_id: UUID


class SeparateInput(Versioned):
    decision: Literal["separate"]
    decision_id: UUID
    expected_revision: StrictInt = Field(ge=1, le=_MAX_REVISION)


MatchDecisionInput = Annotated[
    MergeInput | DistinctInput | SeparateInput, Field(discriminator="decision")
]


class MatchDecisionView(Strict):
    schema_version: Literal[1] = 1
    business_id: UUID
    decision_id: UUID
    kind: Literal["merged", "distinct", "separated"]
    counterparty_id: UUID
    other_counterparty_id: UUID
    reverses_decision_id: UUID | None
    # The new version of `counterparty_id` written by a merge or separation.
    counterparty_revision: int | None
    reversed: bool
    decided_at: AwareDatetime


class MatchDecisionList(Strict):
    schema_version: Literal[1] = 1
    business_id: UUID
    counterparty_id: UUID
    items: tuple[MatchDecisionView, ...]


class MatchDecisionReceipt(Strict):
    decision_id: UUID
    counterparty_revision: int | None


class LinkBookingsInput(Versioned):
    action: Literal["link"]
    booking_ids: tuple[UUID, ...] = Field(min_length=1, max_length=50)

    @field_validator("booking_ids")
    @classmethod
    def distinct_bookings(cls, value: tuple[UUID, ...]) -> tuple[UUID, ...]:
        if len(set(value)) != len(value):
            raise ValueError("Select each booking only once")
        return value


class UnlinkBookingInput(Versioned):
    action: Literal["unlink"]
    booking_id: UUID
    expected_sequence: StrictInt = Field(ge=1, le=_MAX_REVISION)


BookingLinkInput = Annotated[LinkBookingsInput | UnlinkBookingInput, Field(discriminator="action")]


class BookingLinkView(Strict):
    link_id: UUID
    booking_id: UUID
    sequence: int = Field(ge=1)
    action: Literal["linked", "unlinked"]
    counterparty_id: UUID
    basis: tuple[LinkBasis, ...]
    decided_at: AwareDatetime


class BookingLinkResult(Strict):
    schema_version: Literal[1] = 1
    business_id: UUID
    counterparty_id: UUID
    links: tuple[BookingLinkView, ...]


class BookingLinkReceipt(Strict):
    counterparty_id: UUID
    link_ids: tuple[UUID, ...]


class BookingLinkHistory(Strict):
    schema_version: Literal[1] = 1
    business_id: UUID
    counterparty_id: UUID
    items: tuple[BookingLinkView, ...]
    next_cursor: UUID | None


class BookingSummary(Strict):
    booking_id: UUID
    starts_at: AwareDatetime
    status: str
    customer_name: str | None
    email: str | None
    phone: str | None


class LinkedBooking(Strict):
    booking: BookingSummary
    # The linked record: this counterparty or a duplicate merged into it.
    counterparty_id: UUID
    sequence: int = Field(ge=1)
    basis: tuple[LinkBasis, ...]
    decided_at: AwareDatetime
    still_matches: bool


class LinkedBookingList(Strict):
    schema_version: Literal[1] = 1
    business_id: UUID
    counterparty_id: UUID
    items: tuple[LinkedBooking, ...]
    next_cursor: UUID | None


class BookingCandidate(Strict):
    booking: BookingSummary
    basis: tuple[LinkBasis, ...]


class BookingCandidateList(Strict):
    schema_version: Literal[1] = 1
    business_id: UUID
    counterparty_id: UUID
    items: tuple[BookingCandidate, ...]
