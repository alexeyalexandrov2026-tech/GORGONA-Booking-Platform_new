from dataclasses import dataclass
from uuid import UUID, uuid7

from gorgona_booking.booking.metrics import confirmed_booking_value


@dataclass
class Booking:
    booking_id: UUID
    status: str
    currency: str
    total_cents: int


def test_booking_value_keeps_currencies_separate_and_counts_allocations_once() -> None:
    usd = Booking(uuid7(), "CONFIRMED", "USD", 1000)
    eur = Booking(uuid7(), "CONFIRMED", "EUR", 1500)
    cancelled = Booking(uuid7(), "CANCELLED", "USD", 500)
    amounts = confirmed_booking_value([usd, eur, cancelled, usd])
    assert [(a.currency, a.amount_cents) for a in amounts] == [("EUR", 1500), ("USD", 1000)]


def test_unconfirmed_bookings_do_not_have_confirmed_value() -> None:
    assert confirmed_booking_value([Booking(uuid7(), "HOLD", "USD", 1000)]) == []
