"""Operational booking value is not payment evidence or recognized revenue."""

from collections.abc import Iterable
from typing import Protocol
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class ValuedBooking(Protocol):
    booking_id: UUID
    status: str
    currency: str
    total_cents: int


class CurrencyAmount(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    currency: str = Field(pattern=r"^[A-Z]{3}$")
    amount_cents: int = Field(ge=0)


def confirmed_booking_value(bookings: Iterable[ValuedBooking]) -> list[CurrencyAmount]:
    """Count a booking once even if a resource join returns multiple allocations."""
    seen: set[UUID] = set()
    amounts: dict[str, int] = {}
    for booking in bookings:
        if booking.booking_id in seen or booking.status != "CONFIRMED":
            continue
        seen.add(booking.booking_id)
        amounts[booking.currency] = amounts.get(booking.currency, 0) + booking.total_cents
    return [CurrencyAmount(currency=k, amount_cents=v) for k, v in sorted(amounts.items())]
