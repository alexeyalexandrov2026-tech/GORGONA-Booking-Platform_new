"""R4c: rental extensions and shortened periods on the shared occupancy (FAKE data).

docs/plan/PACKAGE_R4C_DESIGN_2026-11-06.md: a period change is an insert-only row with the next
agreement version; availability, assignments and agreements use the current period; the unit's
hold moves by releasing and assigning the same unit again.
"""

from typing import Any
from uuid import UUID, uuid7

import httpx
import psycopg
import pytest

from gorgona_booking.db.pool import RuntimePool, tenant_transaction
from gorgona_booking.db.provisioning import owner_tenant_transaction
from tests.integration.configuration_support import Config
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
from tests.integration.test_r2_rental_bookings import at, book, party
from tests.integration.test_r3a_rental_assignment import assign, booked, units
from tests.integration.test_r3b_rental_blocks import block
from tests.integration.test_r4a_rental_rates import SEAT, card
from tests.integration.test_r4b_rental_agreements import SIGNED, accept
from tests.support.fake_idp import FakeIdp

pytestmark = pytest.mark.anyio
__all__ = ["accepted", "client", "idp", "manager_a", "manager_b", "rental"]

LONGER = "FAKE kept the car longer"


async def extend(
    rental: Rental,
    booking: str,
    starts: str,
    ends: str,
    extras: list[dict[str, Any]] | None = None,
    headers: dict[str, str] | None = None,
    **fields: Any,
) -> httpx.Response:
    return await rental.client.post(
        f"{rental.base}/bookings/{booking}/agreement/period",
        json={
            "schema_version": 1,
            "starts_at": starts,
            "ends_at": ends,
            "reason": LONGER,
            "source": "email",
            "accepted_by": "FAKE Renter",
            "accepted_at": SIGNED,
            "extras": extras or [],
            **fields,
        },
        headers={**(headers or rental.headers), "Idempotency-Key": str(uuid7())},
    )


async def agreed(rental: Rental, count: int) -> tuple[UUID, list[UUID], UUID, str]:
    car, made = await units(rental, count)
    home = rental.world.a.location_id
    assert (await card(rental, car, home, {"day": 5_000}, [SEAT])).is_success
    customer = await party(rental, "FAKE Renter", ["customer"])
    booking = await booked(rental, car, customer, at(1), at(3))
    assert (await accept(rental, booking, [])).is_success
    return car, made, customer, booking


def holds(rental: Rental, booking: str) -> list[tuple[Any, ...]]:
    with owner_tenant_transaction(rental.owner_conn, rental.tenant):
        return rental.owner_conn.execute(
            "select x.state, lower(x.during), upper(x.during) from gba.rental_assignments a "
            "join gba.resource_allocations x on x.tenant_id = a.tenant_id "
            "and x.source_kind = 'rental_assignment' and x.source_id = a.id "
            "where a.booking_id = %s order by a.assigned_at",
            (booking,),
        ).fetchall()


# R4c-01 -----------------------------------------------------------------------------


async def test_an_extension_moves_the_period_the_agreement_and_the_hold(rental: Rental) -> None:
    _, (unit,), _, booking = await agreed(rental, 1)
    assert (await assign(rental, booking, unit)).status_code == 200
    seat = [{"code": "child_seat", "quantity": 1}]
    moved = await extend(rental, booking, at(1), at(4), seat)
    assert moved.status_code == 200, moved.text
    body = moved.json()
    assert body["current_version"] == 2
    first, second = body["versions"]
    assert (first["ends_at"], first["total"]) == ("2031-06-03T10:00:00Z", 10_000)
    period = (second["starts_at"], second["ends_at"])
    assert period == ("2031-06-01T10:00:00Z", "2031-06-04T10:00:00Z")
    assert (second["rental"], second["rental_days"], second["total"]) == (15_000, 3, 17_100)
    assert (second["reason"], second["rate_card_id"]) == (LONGER, first["rate_card_id"])
    current = await rental.get(f"/bookings/{booking}")
    assert current.json()["ends_at"] == "2031-06-04T10:00:00Z", current.text
    listed = (await rental.get(f"/bookings/{booking}/assignments")).json()["items"]
    assert [(a["unit_id"], a["ends_at"], a["release"] is None) for a in listed] == [
        (str(unit), "2031-06-03T10:00:00Z", False),
        (str(unit), "2031-06-04T10:00:00Z", True),
    ]
    assert [h[0] for h in holds(rental, booking)] == ["released", "confirmed"]


# R4c-02 -----------------------------------------------------------------------------


async def test_occupancy_refuses_a_longer_period_and_frees_a_shorter_one(rental: Rental) -> None:
    car, _, customer, booking = await agreed(rental, 1)
    assert (await book(rental, car, customer, at(4), at(5))).status_code == 200
    longer = await extend(rental, booking, at(1), at(5))
    assert error(longer) == (409, "RENTAL_UNAVAILABLE"), longer.text
    shorter = await extend(rental, booking, at(1), at(2))
    assert shorter.status_code == 200, shorter.text
    assert (await book(rental, car, customer, at(2), at(3))).status_code == 200
    _, (first, _), _, other = await agreed(rental, 2)
    assert (await assign(rental, other, first)).status_code == 200
    assert (await block(rental, first, at(4), at(5))).status_code == 200
    busy = await extend(rental, other, at(1), at(5))
    assert error(busy) == (409, "RENTAL_UNIT_BUSY"), busy.text
    assert [h[0] for h in holds(rental, other)] == ["confirmed"]


# R4c-03 -----------------------------------------------------------------------------


async def test_refusals(rental: Rental) -> None:
    car, _, customer, booking = await agreed(rental, 2)
    plain = await booked(rental, car, customer, at(10), at(11))
    assert error(await extend(rental, plain, at(10), at(12))) == (404, "NOT_FOUND")
    for refused in (
        await extend(rental, booking, at(1), at(4), reason=" "),
        await extend(rental, booking, at(3), at(1)),
        await extend(rental, booking, at(1), "2032-06-03T10:00:00+00:00"),
    ):
        assert refused.status_code == 422, refused.text
    cancelled = await rental.client.post(
        f"{rental.base}/bookings/{booking}/cancellation",
        json={"schema_version": 1, "reason": "FAKE plans changed"},
        headers={**rental.headers, "Idempotency-Key": str(uuid7())},
    )
    assert cancelled.status_code == 200, cancelled.text
    gone = await extend(rental, booking, at(1), at(4))
    assert error(gone) == (409, "RENTAL_BOOKING_CANCELLED"), gone.text


# R4c-04 -----------------------------------------------------------------------------


async def test_sql_keeps_period_changes_whole(rental: Rental, app_pool: RuntimePool) -> None:
    _, (unit,), _, booking = await agreed(rental, 1)
    assert (await extend(rental, booking, at(1), at(4))).status_code == 200
    tenant = rental.tenant
    for statement in (
        "update gba.rental_booking_periods set ends_at = ends_at + interval '1 day'",
        "delete from gba.rental_booking_periods",
    ):
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            async with tenant_transaction(app_pool, tenant) as conn:
                await conn.execute(statement)
    forged = (
        "insert into gba.rental_booking_periods (tenant_id, booking_id, sequence, starts_at, "
        "ends_at, recorded_by) select tenant_id, booking_id, 3, starts_at, "
        "ends_at + interval '1 hour', recorded_by from gba.rental_booking_periods "
        "where booking_id = %s"
    )
    with pytest.raises(psycopg.errors.CheckViolation):
        async with tenant_transaction(app_pool, tenant) as conn:
            await conn.execute(forged, (booking,))
    stale = (
        "insert into gba.rental_assignments (tenant_id, id, booking_id, unit_id, starts_at, "
        "ends_at, assigned_by) select tenant_id, %s, id, %s, starts_at, ends_at, booked_by "
        "from gba.rental_bookings where id = %s"
    )
    with pytest.raises(psycopg.errors.CheckViolation):
        async with tenant_transaction(app_pool, tenant) as conn:
            await conn.execute(stale, (uuid7(), unit, booking))
    current = await rental.get(f"/bookings/{booking}")
    assert current.json()["ends_at"] == "2031-06-04T10:00:00Z", current.text


async def test_scope_module_and_another_company(
    rental: Rental,
    app_pool: RuntimePool,
    idp: FakeIdp,
    manager_a: FakeUser,
    manager_b: FakeUser,
) -> None:
    away, _ = seed_other_branch(rental.owner_conn, rental.world.a)
    _, _, _, booking = await agreed(rental, 1)
    branch = rental.member("manager", away)
    hidden = await extend(rental, booking, at(1), at(4), headers=branch)
    assert error(hidden) == (404, "NOT_FOUND"), hidden.text
    other = idp.bearer(manager_b.subject, email=manager_b.email)
    foreign = await extend(rental, booking, at(1), at(4), headers=other)
    assert foreign.status_code in (403, 404), foreign.text
    await Config(rental.client, idp).publish(
        manager_a, rental.tenant, 1, ["booking_resources", "counterparties"]
    )
    off = await extend(rental, booking, at(1), at(4))
    assert error(off) == (409, "MODULE_DISABLED"), off.text
    count = "select count(*) from gba.rental_booking_periods"
    async with tenant_transaction(app_pool, rental.tenant) as conn:
        mine = await (await conn.execute(count)).fetchone()
    assert mine == (0,)
    async with tenant_transaction(app_pool, rental.world.b.tenant_id) as conn:
        row = await (await conn.execute(count)).fetchone()
    assert row == (0,)
