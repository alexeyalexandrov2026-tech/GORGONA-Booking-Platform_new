"""Staff reservations of resources (ADR-0022): typed, versioned API contracts."""

import unicodedata
from datetime import timedelta
from typing import Literal, Self
from uuid import UUID

from pydantic import AwareDatetime, Field, field_validator, model_validator

from gorgona_booking.business.contracts import Strict, Versioned

ReservationStatus = Literal["active", "cancelled"]
MAX_RESOURCES = 10
MAX_DURATION = timedelta(days=31)


class ReservationInput(Versioned):
    location_id: UUID
    resource_ids: tuple[UUID, ...] = Field(min_length=1, max_length=MAX_RESOURCES)
    starts_at: AwareDatetime
    ends_at: AwareDatetime
    purpose: str | None = Field(default=None, min_length=1, max_length=200)

    @field_validator("purpose")
    @classmethod
    def single_line(cls, value: str | None) -> str | None:
        if value is None:
            return None
        text = value.strip()
        # Control characters and line/paragraph separators, as the database refuses.
        if not text or any(unicodedata.category(c) in ("Cc", "Zl", "Zp") for c in text):
            raise ValueError("Provide nonblank text without control characters")
        return text

    @model_validator(mode="after")
    def bounded(self) -> Self:
        if len(set(self.resource_ids)) != len(self.resource_ids):
            raise ValueError("Name each resource once")
        if self.ends_at <= self.starts_at:
            raise ValueError("The end must follow the start")
        if self.ends_at - self.starts_at > MAX_DURATION:
            raise ValueError("A reservation lasts at most 31 days")
        return self


class CancelInput(Versioned):
    pass


class ReservationView(Strict):
    schema_version: Literal[1] = 1
    business_id: UUID
    reservation_id: UUID
    location_id: UUID
    resource_ids: tuple[UUID, ...]
    starts_at: AwareDatetime
    ends_at: AwareDatetime
    purpose: str | None
    status: ReservationStatus
    created_at: AwareDatetime
    cancelled_at: AwareDatetime | None


class ReservationList(Strict):
    schema_version: Literal[1] = 1
    business_id: UUID
    items: tuple[ReservationView, ...]


class ReservationReceipt(Strict):
    reservation_id: UUID
