"""R4a: the rental quote is the cheapest cover by the card's units plus extras (pure, no database).

docs/plan/PACKAGE_R4A_DESIGN_2026-11-04.md decision 3.
"""

from datetime import UTC, datetime, timedelta

import pytest

from gorgona_booking.business.rental_quote import Extra, Rates, quote

START = datetime(2031, 6, 1, 10, tzinfo=UTC)


def hours(n: int) -> datetime:
    return START + timedelta(hours=n)


def test_the_cheapest_cover_mixes_units_and_may_exceed_the_period() -> None:
    rates = Rates(hour=1_000, day=5_000, week=30_000, month=None)
    six_days = quote(rates, START, hours(6 * 24), [])
    assert (six_days.rental, six_days.total) == (30_000, 30_000)
    eight_days = quote(rates, START, hours(8 * 24), [])
    assert eight_days.rental == 35_000
    assert eight_days.counts == {"month": 0, "week": 1, "day": 1, "hour": 0}
    # Six hours by the hour cost 6 000; one day covers them for 5 000.
    assert quote(rates, START, hours(6), []).rental == 5_000
    assert quote(rates, START, hours(3), []).rental == 3_000


def test_a_month_covers_a_long_period_and_a_part_hour_counts_whole() -> None:
    rates = Rates(hour=None, day=5_000, week=None, month=100_000)
    assert quote(rates, START, hours(25 * 24), []).rental == 100_000
    only_days = Rates(hour=None, day=5_000, week=None, month=None)
    assert quote(only_days, START, hours(25), []).rental == 10_000
    assert quote(only_days, START, START + timedelta(minutes=1), []).rental == 5_000


def test_extras_count_rental_days_or_once() -> None:
    rates = Rates(hour=None, day=5_000, week=None, month=None)
    seat = Extra(code="child_seat", name="FAKE seat", price=700, unit="per_day")
    driver = Extra(code="driver", name="FAKE driver", price=2_000, unit="per_rental")
    priced = quote(rates, START, hours(25), [(seat, 2), (driver, 1)])
    assert priced.rental_days == 2
    assert priced.extras == [("child_seat", 2, 2_800), ("driver", 1, 2_000)]
    assert priced.total == 10_000 + 2_800 + 2_000


def test_a_period_must_be_positive_and_at_most_366_days() -> None:
    rates = Rates(hour=1_000, day=None, week=None, month=None)
    with pytest.raises(ValueError, match="period"):
        quote(rates, START, START, [])
    with pytest.raises(ValueError, match="period"):
        quote(rates, START, START + timedelta(days=366, seconds=1), [])
    with pytest.raises(ValueError, match="rate"):
        Rates(hour=None, day=None, week=None, month=None)
    with pytest.raises(ValueError, match="rate"):
        Rates(hour=0, day=None, week=None, month=None)
