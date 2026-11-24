"""Whole-period class booking feasibility (RR-08)."""

import pytest

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
from tests.integration.test_r2_rental_bookings import at, book, party, query
from tests.integration.test_r3a_rental_assignment import assign, booked, units
from tests.integration.test_r3b_rental_blocks import block

pytestmark = pytest.mark.anyio
__all__ = ["accepted", "client", "idp", "manager_a", "manager_b", "rental"]


async def test_alternating_blocks_leave_no_unit_for_the_full_period(rental: Rental) -> None:
    car, (first, second) = await units(rental, 2)
    customer = await party(rental, "FAKE Renter", ["customer"])
    assert (await block(rental, first, at(1), at(2))).is_success
    assert (await block(rental, second, at(2), at(3))).is_success
    response = await book(rental, car, customer, at(1), at(3))
    assert response.status_code == 409, response.text
    assert error(response) == (409, "RENTAL_UNAVAILABLE")
    available = await rental.get(query(car, rental.world.a.location_id, at(1), at(3)))
    assert available.is_success, available.text
    assert available.json()["available"] == 0


async def test_pinning_the_wrong_unit_cannot_strand_an_existing_booking(
    rental: Rental,
) -> None:
    car, (first, second) = await units(rental, 2)
    customer = await party(rental, "FAKE Renter", ["customer"])
    assert (await block(rental, first, at(1), at(2))).is_success
    long = await booked(rental, car, customer, at(1), at(4))
    short = await booked(rental, car, customer, at(2), at(4))
    misplaced = await assign(rental, short, second)
    assert misplaced.status_code == 409, misplaced.text
    assert error(misplaced) == (409, "RENTAL_UNAVAILABLE")
    assert (await assign(rental, short, first)).is_success
    assert (await assign(rental, long, second)).is_success


async def test_another_block_cannot_strand_an_existing_booking(rental: Rental) -> None:
    car, (first, second) = await units(rental, 2)
    customer = await party(rental, "FAKE Renter", ["customer"])
    assert (await block(rental, first, at(1), at(2))).is_success
    await booked(rental, car, customer, at(1), at(3))
    response = await block(rental, second, at(2), at(3))
    assert response.status_code == 409, response.text
    assert error(response) == (409, "RENTAL_UNAVAILABLE")


async def test_feasibility_search_reconsiders_an_individually_valid_choice(
    rental: Rental,
) -> None:
    car, fleet = await units(rental, 3)
    _, second, third = sorted(fleet)
    customer = await party(rental, "FAKE Renter", ["customer"])
    # A can use first/second; B can use first/third; C can use first/third.
    # All overlap. If A takes first, B and C cannot both use third.
    assert (await block(rental, third, at(1), at(2))).is_success
    assert (await block(rental, second, at(4), at(5))).is_success
    await booked(rental, car, customer, at(1), at(4))
    await booked(rental, car, customer, at(2), at(5))
    await booked(rental, car, customer, at(3), at(5))
