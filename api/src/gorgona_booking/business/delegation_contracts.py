"""Versioned cross-company delegation grants (ADR-0017); no shared account or data copy."""

from typing import Literal
from uuid import UUID

from pydantic import AwareDatetime, Field, StrictInt, field_validator

from gorgona_booking.business.contracts import Strict

DelegablePermission = Literal["booking.read", "booking.write", "catalog.read", "staff.read"]
GrantStatus = Literal["pending", "active", "declined", "revoked"]


class _Versioned(Strict):
    schema_version: Literal[1] = 1

    @field_validator("schema_version", mode="before")
    @classmethod
    def integer_version(cls, value: object) -> object:
        if type(value) is not int:
            raise ValueError("Version must be an integer")
        return value


class DelegationIssue(_Versioned):
    """Owner terms. They never change after issue; new terms need a new grant."""

    servicer_business_id: UUID
    permissions: tuple[DelegablePermission, ...] = Field(min_length=1, max_length=4)
    location_id: UUID | None
    expires_at: AwareDatetime

    @field_validator("permissions")
    @classmethod
    def distinct_permissions(
        cls, value: tuple[DelegablePermission, ...]
    ) -> tuple[DelegablePermission, ...]:
        if len(set(value)) != len(value):
            raise ValueError("List each permission once")
        return tuple(sorted(value))


class DelegationDecision(_Versioned):
    expected_revision: StrictInt = Field(ge=1, le=2_147_483_646)


class DelegateSelection(DelegationDecision):
    """The servicing business names its own company-wide employees as delegates."""

    delegate_user_ids: tuple[UUID, ...] = Field(min_length=1, max_length=50)

    @field_validator("delegate_user_ids")
    @classmethod
    def distinct_delegates(cls, value: tuple[UUID, ...]) -> tuple[UUID, ...]:
        if len(set(value)) != len(value):
            raise ValueError("List each delegate once")
        return tuple(sorted(value))


class DelegateView(Strict):
    user_id: UUID
    display_name: str
    added_at: AwareDatetime


class DelegationView(Strict):
    schema_version: Literal[1] = 1
    grant_id: UUID
    owner_business_id: UUID
    owner_name: str
    servicer_business_id: UUID
    servicer_name: str | None
    permissions: tuple[DelegablePermission, ...]
    location_id: UUID | None
    expires_at: AwareDatetime
    status: GrantStatus
    expired: bool
    revision: int = Field(ge=1)
    revoked_by_side: Literal["owner", "servicer"] | None
    delegates: tuple[DelegateView, ...]
    created_at: AwareDatetime


class DelegationList(Strict):
    schema_version: Literal[1] = 1
    business_id: UUID
    items: tuple[DelegationView, ...]
    next_cursor: UUID | None
