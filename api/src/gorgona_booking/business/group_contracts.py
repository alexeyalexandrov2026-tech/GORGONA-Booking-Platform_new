"""Explicit group ownership, invitations and independently owned consent (ADR-0018)."""

from typing import Literal
from uuid import UUID

from pydantic import AwareDatetime, Field, StrictInt, field_validator

from gorgona_booking.business.contracts import Strict
from gorgona_booking.business.delegation_contracts import _integer_version


class GroupInput(Strict):
    schema_version: Literal[1] = 1
    expected_revision: StrictInt = Field(ge=0, le=2_147_483_646)
    code: str = Field(min_length=1, max_length=64, pattern=r"^[A-Z0-9][A-Z0-9_-]*$")
    name: str = Field(min_length=1, max_length=200)
    integer_version = field_validator("schema_version", mode="before")(_integer_version)

    @field_validator("name")
    @classmethod
    def owner_provided_name(cls, value: str) -> str:
        name = value.strip()
        if not name or any(ord(char) < 32 or ord(char) == 127 for char in name):
            raise ValueError("Provide a nonblank group name without control characters")
        return name


class GroupView(Strict):
    schema_version: Literal[1] = 1
    business_id: UUID
    group_id: UUID
    code: str
    name: str
    revision: int = Field(ge=1)
    created_at: AwareDatetime


class GroupList(Strict):
    schema_version: Literal[1] = 1
    business_id: UUID
    items: tuple[GroupView, ...]
    next_cursor: str | None


class InvitationInput(Strict):
    schema_version: Literal[1] = 1
    participant_business_id: UUID
    integer_version = field_validator("schema_version", mode="before")(_integer_version)


class ConsentInput(Strict):
    schema_version: Literal[1] = 1
    expected_revision: StrictInt = Field(ge=0, le=2_147_483_646)
    state: Literal["accepted", "withdrawn"]
    integer_version = field_validator("schema_version", mode="before")(_integer_version)


class InvitationView(Strict):
    schema_version: Literal[1] = 1
    business_id: UUID
    operator_business_id: UUID
    participant_business_id: UUID
    group_id: UUID
    group_name: str
    invitation_id: UUID
    state: Literal["active", "withdrawn"]
    revision: Literal[1, 2]
    consent_state: Literal["accepted", "withdrawn"] | None
    consent_revision: int = Field(ge=0)
    created_at: AwareDatetime


class InvitationList(Strict):
    schema_version: Literal[1] = 1
    business_id: UUID
    items: tuple[InvitationView, ...]
    next_cursor: UUID | None


class BookingReportRow(Strict):
    owner_business_id: UUID
    legal_entity_id: None = None
    legal_entity_assignment: Literal["unassigned"] = "unassigned"
    location_id: UUID
    status: Literal["HOLD", "CONFIRMED", "CANCELLED", "EXPIRED"]
    booking_count: int = Field(ge=0)


class ReportSource(Strict):
    owner_business_id: UUID
    grant_id: UUID
    grant_revision: int = Field(ge=1)
    location_id: UUID | None


class GroupBookingReport(Strict):
    schema_version: Literal[1] = 1
    business_id: UUID
    group_id: UUID
    from_at: AwareDatetime
    until_at: AwareDatetime
    items: tuple[BookingReportRow, ...]
    sources: tuple[ReportSource, ...]
    excluded_business_ids: tuple[UUID, ...]
    next_cursor: UUID | None
