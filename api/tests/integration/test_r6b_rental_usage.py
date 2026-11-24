"""R6b: overdue time and meter excess of a rental booking, derived on read (FAKE data).

docs/plan/PACKAGE_R6B_DESIGN_2026-11-07.md: the latest agreement version and its rate card with the
R6a inspections give the state, the overdue time and the meter excess; nothing is stored.
"""

from typing import Any
from uuid import uuid7

import httpx
import pytest

from gorgona_booking.db.provisioning import owner_tenant_transaction
from tests.integration.seed import FakeUser, seed_other_branch
from tests.integration.test_r1_rental_catalog import (
    Rental,
    accepted,
    client,
    error,
    idp,
    manager_a,
    manager_b,
    rental,
)
from tests.integration.test_r2_rental_bookings import at, party
from tests.integration.test_r3a_rental_assignment import assign, booked, units
from tests.integration.test_r4a_rental_rates import SEAT, card
from tests.integration.test_r4b_rental_agreements import accept
from tests.integration.test_r4c_rental_extensions import extend
from tests.integration.test_r6a_rental_inspections import inspect
from tests.support.fake_idp import FakeIdp

pytestmark = pytest.mark.anyio
__all__ = ["accepted", "client", "idp", "manager_a", "manager_b", "rental"]


async def rented(rental: Rental, meter: str = "odometer", **terms: Any) -> str:
    """A two-day booking (at(1) to at(3)) with an agreement on a card and its unit assigned."""
    if meter == "odometer":
        car, (unit,) = await units(rental, 1)
    else:
        car, unit = uuid7(), uuid7()
        assert (await rental.klass(car, meter_kind=meter)).status_code == 200
        assert (await rental.unit(unit, car)).status_code == 200
    home = rental.world.a.location_id
    made = await card(rental, car, home, {"day": 5_000}, [SEAT], **terms)
    assert made.is_success, made.text
    customer = await party(rental, "FAKE Renter", ["customer"])
    booking = await booked(rental, car, customer, at(1), at(3))
    assert (await accept(rental, booking, [])).is_success
    assert (await assign(rental, booking, unit)).status_code == 200
    return booking


async def usage(
    rental: Rental, booking: str, headers: dict[str, str] | None = None
) -> httpx.Response:
    return await rental.client.get(
        f"{rental.base}/bookings/{booking}/usage", headers=headers or rental.headers
    )


def figures(body: dict[str, Any]) -> tuple[Any, ...]:
    keys = ("state", "overdue_hours", "distance", "allowance", "excess", "excess_amount")
    return tuple(body[k] for k in keys)


def returned_at(rental: Rental, booking: str, moment: str) -> None:
    """FAKE time: move the recorded return as an owner, to a moment after the period."""
    with owner_tenant_transaction(rental.owner_conn, rental.tenant):
        rental.owner_conn.execute(
            "update gba.rental_inspections set inspected_at = %s "
            "where booking_id = %s and kind = 'return'",
            (moment, booking),
        )


# R6b-01 -----------------------------------------------------------------------------


async def test_usage_follows_the_inspections(rental: Rental) -> None:
    booking = await rented(rental, meter_allowance_per_day=100, excess_rate=25)
    before = await usage(rental, booking)
    assert before.status_code == 200, before.text
    assert figures(before.json()) == ("not_handed_over", 0, None, 200, None, None)
    assert (await inspect(rental, booking, "handover", meter=1_000)).status_code == 200
    out = (await usage(rental, booking)).json()
    assert figures(out) == ("out", 0, None, 200, None, None)
    assert out["as_of"] < out["period_end"]
    assert (await inspect(rental, booking, "return", meter=1_300)).status_code == 200
    back = (await usage(rental, booking)).json()
    assert figures(back) == ("returned", 0, 300, 200, 100, 2_500)
    assert (back["currency"], back["rental_days"], back["overdue_seconds"]) == ("EUR", 2, 0)


# R6b-02 -----------------------------------------------------------------------------


async def test_a_late_return_counts_started_hours(rental: Rental) -> None:
    booking = await rented(rental, meter_allowance_per_day=100, excess_rate=25)
    assert (await inspect(rental, booking, "handover", meter=1_000)).status_code == 200
    assert (await inspect(rental, booking, "return", meter=1_100)).status_code == 200
    returned_at(rental, booking, "2031-06-03T11:00:01+00:00")
    late = (await usage(rental, booking)).json()
    assert (late["overdue_seconds"], late["overdue_hours"]) == (3_601, 2)
    assert (late["excess"], late["excess_amount"]) == (0, 0)


# R6b-03 -----------------------------------------------------------------------------


async def test_cards_meters_and_extensions(rental: Rental) -> None:
    bare = await rented(rental)
    assert (await inspect(rental, bare, "handover", meter=10)).status_code == 200
    assert (await inspect(rental, bare, "return", meter=510)).status_code == 200
    assert figures((await usage(rental, bare)).json()) == ("returned", 0, 500, None, None, None)
    unpriced = await rented(rental, meter_allowance_per_day=100)
    assert (await inspect(rental, unpriced, "handover", meter=0)).status_code == 200
    assert (await inspect(rental, unpriced, "return", meter=250)).status_code == 200
    got = (await usage(rental, unpriced)).json()
    assert figures(got) == ("returned", 0, 250, 200, 50, None)
    plain = await rented(rental, "none", meter_allowance_per_day=100, excess_rate=25)
    assert (await inspect(rental, plain, "handover", meter=None)).status_code == 200
    assert (await inspect(rental, plain, "return", meter=None)).status_code == 200
    assert figures((await usage(rental, plain)).json()) == ("returned", 0, None, None, None, None)
    longer = await rented(rental, meter_allowance_per_day=100, excess_rate=25)
    moved = await extend(rental, longer, at(1), at(4))
    assert moved.is_success, moved.text
    assert (await inspect(rental, longer, "handover", meter=0)).status_code == 200
    assert (await inspect(rental, longer, "return", meter=350)).status_code == 200
    returned_at(rental, longer, "2031-06-03T11:00:01+00:00")
    extended = (await usage(rental, longer)).json()
    assert figures(extended) == ("returned", 0, 350, 300, 50, 1_250)
    assert extended["period_end"].startswith("2031-06-04T10:00:00")


# R6b-04 -----------------------------------------------------------------------------


async def test_scope_and_another_company(rental: Rental, idp: FakeIdp, manager_b: FakeUser) -> None:
    away, _ = seed_other_branch(rental.owner_conn, rental.world.a)
    booking = await rented(rental)
    hidden = await usage(rental, booking, rental.member("manager", away))
    assert error(hidden) == (404, "NOT_FOUND"), hidden.text
    other = idp.bearer(manager_b.subject, email=manager_b.email)
    foreign = await usage(rental, booking, other)
    assert foreign.status_code in (403, 404), foreign.text
    missing = await usage(rental, str(uuid7()))
    assert error(missing) == (404, "NOT_FOUND"), missing.text
