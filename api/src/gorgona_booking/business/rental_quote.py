"""R4a (package R, RENT-01): the rental quote, computed and never typed.

docs/plan/PACKAGE_R4A_DESIGN_2026-11-04.md decision 3. The rental charge is the cheapest cover of
the period by whole hours, days, weeks (7 days) and months (30 days) of the rates a card has; a
cover may exceed the period. Each extra adds its price times the quantity, per rental day for
`per_day`.
Amounts are integers in minor units.
"""

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from math import ceil
from typing import Literal

LONGEST = timedelta(days=366)
HOURS = {"month": 30 * 24, "week": 7 * 24, "day": 24, "hour": 1}


@dataclass(frozen=True)
class Rates:
    hour: int | None
    day: int | None
    week: int | None
    month: int | None

    def __post_init__(self) -> None:
        present = [r for r in (self.hour, self.day, self.week, self.month) if r is not None]
        if not present or any(r <= 0 for r in present):
            raise ValueError("a rate card has at least one rate and every rate is above zero")

    def by_unit(self) -> dict[str, int]:
        found = {"month": self.month, "week": self.week, "day": self.day, "hour": self.hour}
        return {unit: rate for unit, rate in found.items() if rate is not None}


@dataclass(frozen=True)
class Extra:
    code: str
    name: str
    price: int
    unit: Literal["per_day", "per_rental"]


@dataclass(frozen=True)
class Quote:
    counts: dict[str, int]
    rental: int
    rental_days: int
    extras: list[tuple[str, int, int]] = field(default_factory=list)

    @property
    def total(self) -> int:
        return self.rental + sum(amount for _, _, amount in self.extras)


def _cover(rates: Rates, hours: int) -> tuple[int, dict[str, int]]:
    """The cheapest cover of at least `hours` whole hours by the card's units."""
    units = rates.by_unit()
    cost = [0] * (hours + 1)
    choice = [""] * (hours + 1)
    for h in range(1, hours + 1):
        best: tuple[int, str] | None = None
        for unit, rate in units.items():
            candidate = rate + cost[max(0, h - HOURS[unit])]
            if best is None or candidate < best[0]:
                best = (candidate, unit)
        assert best is not None  # noqa: S101 - Rates has at least one rate
        cost[h], choice[h] = best
    counts = dict.fromkeys(HOURS, 0)
    h = hours
    while h > 0:
        counts[choice[h]] += 1
        h = max(0, h - HOURS[choice[h]])
    return cost[hours], counts


def quote(rates: Rates, starts: datetime, ends: datetime, extras: list[tuple[Extra, int]]) -> Quote:
    period = ends - starts
    if period <= timedelta(0) or period > LONGEST:
        raise ValueError("a period ends after it starts and lasts at most 366 days")
    seconds = period.total_seconds()
    rental, counts = _cover(rates, ceil(seconds / 3600))
    days = ceil(seconds / 86400)
    lines = [
        (extra.code, quantity, extra.price * quantity * (days if extra.unit == "per_day" else 1))
        for extra, quantity in extras
    ]
    return Quote(counts=counts, rental=rental, rental_days=days, extras=lines)
