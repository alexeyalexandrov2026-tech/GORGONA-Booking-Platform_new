"""Versioned company-group contracts (ADR-0018); membership grants no data access."""

from typing import Literal
from uuid import UUID

from pydantic import AwareDatetime, Field, StrictInt, field_validator

from gorgona_booking.business.contracts import Strict, Versioned

MembershipStatus = Literal["invited", "active", "declined", "left", "removed"]


class GroupCreate(Versioned):
    code: str = Field(min_length=1, max_length=64, pattern=r"^[A-Z0-9][A-Z0-9_-]*$")
    name: str = Field(min_length=1, max_length=200)

    @field_validator("name")
    @classmethod
    def owner_provided_name(cls, value: str) -> str:
        name = value.strip()
        if not name or any(ord(char) < 32 or ord(char) == 127 for char in name):
            raise ValueError("Provide a nonblank group name without control characters")
        return name


class GroupInvite(Versioned):
    """An invitation states nothing but the parties; it confers no access."""


class GroupDecision(Versioned):
    expected_revision: StrictInt = Field(ge=1, le=2_147_483_646)


class GroupMembershipView(Strict):
    membership_id: UUID
    member_business_id: UUID
    member_name: str | None
    status: MembershipStatus
    revision: int = Field(ge=1)
    invited_at: AwareDatetime
    decided_at: AwareDatetime | None
    ended_at: AwareDatetime | None


class BusinessGroupView(Strict):
    schema_version: Literal[1] = 1
    group_id: UUID
    organizer_business_id: UUID
    organizer_name: str
    code: str
    name: str
    role: Literal["organizer", "member"]
    # The organizer sees every membership; a member sees only its own.
    memberships: tuple[GroupMembershipView, ...]
    created_at: AwareDatetime


class BusinessGroupList(Strict):
    schema_version: Literal[1] = 1
    business_id: UUID
    items: tuple[BusinessGroupView, ...]
    next_cursor: UUID | None
