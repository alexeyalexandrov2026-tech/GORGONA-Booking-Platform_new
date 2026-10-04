"""Versioned delegation contracts between independent businesses (ADR-0016).

A grant moves no data or ownership. Responses do not imply a service contract, a
regulatory role such as brokerage, or readiness of any industry workflow.
"""

from datetime import UTC, datetime, timedelta
from typing import Literal, Self
from uuid import UUID

from pydantic import AwareDatetime, Field, StrictInt, field_validator, model_validator

from gorgona_booking.auth.permissions import DELEGATION_DEPENDENCIES, Permission
from gorgona_booking.business.contracts import Strict

MAX_REVISION_TERM = timedelta(days=366)

DelegablePermission = Literal["booking.read", "booking.write", "catalog.read", "staff.read"]
GrantState = Literal["active", "revoked"]
EffectiveState = Literal["scheduled", "active", "expired", "revoked"]


def _integer_version(value: object) -> object:
    if type(value) is not int:
        raise ValueError("Version must be an integer")
    return value


class DelegationGrantInput(Strict):
    schema_version: Literal[1] = 1
    expected_revision: StrictInt = Field(ge=0, le=2_147_483_646)
    grantee_business_id: UUID
    purpose: str = Field(min_length=1, max_length=200)
    permissions: tuple[DelegablePermission, ...] = Field(min_length=1, max_length=4)
    location_id: UUID | None = None
    valid_from: AwareDatetime
    valid_until: AwareDatetime

    @field_validator("schema_version", mode="before")
    @classmethod
    def integer_version(cls, value: object) -> object:
        return _integer_version(value)

    @field_validator("valid_from", "valid_until", mode="before")
    @classmethod
    def explicit_instant(cls, value: object) -> object:
        # Numbers would be read as epoch seconds; require an explicit ISO 8601 instant.
        if not isinstance(value, str | datetime):
            raise ValueError("Use an ISO 8601 date and time with a UTC offset")
        return value

    @field_validator("valid_from", "valid_until")
    @classmethod
    def utc_instant(cls, value: datetime) -> datetime:
        return value.astimezone(UTC)

    @field_validator("purpose")
    @classmethod
    def owner_stated_purpose(cls, value: str) -> str:
        purpose = value.strip()
        if not purpose or any(ord(char) < 32 or ord(char) == 127 for char in purpose):
            raise ValueError("Describe the purpose without control characters")
        return purpose

    @field_validator("permissions")
    @classmethod
    def canonical_permissions(
        cls, value: tuple[DelegablePermission, ...]
    ) -> tuple[DelegablePermission, ...]:
        if len(set(value)) != len(value):
            raise ValueError("Select each permission only once")
        return tuple(sorted(value))

    @model_validator(mode="after")
    def validate_terms(self) -> Self:
        granted = {Permission(item) for item in self.permissions}
        for permission, required in DELEGATION_DEPENDENCIES.items():
            if permission in granted and not required <= granted:
                needed = ", ".join(sorted(required))
                raise ValueError(f"{permission} also requires {needed}")
        if self.valid_until <= self.valid_from:
            raise ValueError("The delegation must end after it starts")
        if self.valid_until - self.valid_from > MAX_REVISION_TERM:
            raise ValueError("One delegation revision can last at most 366 days")
        return self


class DelegationRevokeInput(Strict):
    schema_version: Literal[1] = 1
    expected_revision: StrictInt = Field(ge=1, le=2_147_483_646)

    @field_validator("schema_version", mode="before")
    @classmethod
    def integer_version(cls, value: object) -> object:
        return _integer_version(value)


class GrantDelegateView(Strict):
    """A person the serving business designated; names stay inside that business."""

    designation_id: UUID
    user_id: UUID
    designated_at: AwareDatetime


class DelegationGrantView(Strict):
    schema_version: Literal[1] = 1
    business_id: UUID
    grant_id: UUID
    grantee_business_id: UUID
    revision: int = Field(ge=1)
    current_revision: int = Field(ge=1)
    state: GrantState
    effective_state: EffectiveState
    purpose: str
    permissions: tuple[DelegablePermission, ...]
    location_id: UUID | None
    valid_from: AwareDatetime
    valid_until: AwareDatetime
    created_at: AwareDatetime
    # Current designations; empty when an earlier revision is requested.
    delegates: tuple[GrantDelegateView, ...]


class DelegationGrantList(Strict):
    schema_version: Literal[1] = 1
    business_id: UUID
    items: tuple[DelegationGrantView, ...]
    next_cursor: UUID | None


class IncomingDelegateView(Strict):
    designation_id: UUID
    membership_id: UUID
    user_id: UUID
    display_name: str | None
    designated_at: AwareDatetime


class IncomingDelegationView(Strict):
    schema_version: Literal[1] = 1
    business_id: UUID
    grant_id: UUID
    grantor_business_id: UUID
    revision: int = Field(ge=1)
    state: GrantState
    effective_state: EffectiveState
    purpose: str
    permissions: tuple[DelegablePermission, ...]
    location_id: UUID | None
    valid_from: AwareDatetime
    valid_until: AwareDatetime
    delegates: tuple[IncomingDelegateView, ...]


class IncomingDelegationList(Strict):
    schema_version: Literal[1] = 1
    business_id: UUID
    items: tuple[IncomingDelegationView, ...]
    next_cursor: UUID | None


class DelegatedAccessView(Strict):
    """A business the signed-in person may currently serve through a grant."""

    schema_version: Literal[1] = 1
    business_id: UUID
    serving_business_id: UUID
    grant_id: UUID
    revision: int = Field(ge=1)
    purpose: str
    permissions: tuple[DelegablePermission, ...]
    location_id: UUID | None
    valid_until: AwareDatetime
