"""R3b: rental unit blocks, moves between branches and availability (package R; FAKE data).

docs/plan/PACKAGE_R3B_DESIGN_2026-11-03.md: a block holds its unit on the shared occupancy
and counts in availability; a unit with a current or future hold does not change its branch.
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
from tests.integration.test_r2_rental_bookings import at, book, party, query
from tests.integration.test_r3a_rental_assignment import assign, booked, units
from tests.support.fake_idp import FakeIdp

pytestmark = pytest.mark.anyio
__all__ = ["accepted", "client", "idp", "manager_a", "manager_b", "rental"]


async def block(
    rental: Rental,
    unit: UUID,
    starts: str,
    ends: str,
    headers: dict[str, str] | None = None,
    kind: str = "maintenance",
) -> httpx.Response:
    return await rental.client.post(
        f"{rental.base}/units/{unit}/blocks",
        json={
            "schema_version": 1,
            "kind": kind,
            "reason": "FAKE service",
            "starts_at": starts,
            "ends_at": ends,
        },
        headers={**(headers or rental.headers), "Idempotency-Key": str(uuid7())},
    )


async def release(rental: Rental, unit: UUID, block_id: str) -> httpx.Response:
    return await rental.client.post(
        f"{rental.base}/units/{unit}/blocks/{block_id}/release",
        json={"schema_version": 1, "reason": "FAKE done early"},
        headers={**rental.headers, "Idempotency-Key": str(uuid7())},
    )


def block_holds(rental: Rental, unit: UUID) -> list[tuple[Any, ...]]:
    with owner_tenant_transaction(rental.owner_conn, rental.tenant):
        return rental.owner_conn.execute(
            "select x.state, x.resource_id = u.resource_id from gba.rental_unit_blocks b "
            "join gba.rental_units u on u.tenant_id = b.tenant_id and u.id = b.unit_id "
            "join gba.resource_allocations x on x.tenant_id = b.tenant_id "
            "and x.source_kind = 'rental_block' and x.source_id = b.id "
            "where b.unit_id = %s order by b.created_at",
            (unit,),
        ).fetchall()


# R3b-01 -----------------------------------------------------------------------------


async def test_a_block_holds_its_unit_and_never_meets_an_assignment(rental: Rental) -> None:
    car, (first, second) = await units(rental, 2)
    customer = await party(rental, "FAKE Renter", ["customer"])
    held = await block(rental, first, at(1), at(3))
    assert held.status_code == 200, held.text
    view = held.json()
    assert (view["unit_id"], view["kind"], view["release"]) == (str(first), "maintenance", None)
    assert (view["starts_at"], view["ends_at"]) == ("2031-06-01T10:00:00Z", "2031-06-03T10:00:00Z")
    assert block_holds(rental, first) == [("confirmed", True)]
    booking = await booked(rental, car, customer, at(2), at(4))
    assert error(await assign(rental, booking, first)) == (409, "RENTAL_UNIT_BUSY")
    assert (await assign(rental, booking, second)).status_code == 200
    overlap = await block(rental, second, at(3), at(5))
    assert error(overlap) == (409, "RENTAL_UNIT_BUSY"), overlap.text
    released = await release(rental, first, view["block_id"])
    assert released.status_code == 200, released.text
    assert released.json()["release"]["reason"] == "FAKE done early"
    assert block_holds(rental, first) == [("released", True)]
    again = await release(rental, first, view["block_id"])
    assert error(again) == (409, "RENTAL_BLOCK_RELEASED"), again.text
    assert (await assign(rental, booking, first)).status_code == 200
    listed = await rental.get(f"/units/{first}/blocks")
    assert [b["block_id"] for b in listed.json()["items"]] == [view["block_id"]]
    bad = await block(rental, first, at(5), at(4))
    assert bad.status_code == 422, bad.text
    assert (await block(rental, first, at(6), at(7), kind="fuel")).status_code == 422


# R3b-02 -----------------------------------------------------------------------------


async def test_availability_counts_blocked_units(rental: Rental) -> None:
    car, (unit,) = await units(rental, 1)
    customer = await party(rental, "FAKE Renter", ["customer"])
    await booked(rental, car, customer, at(1), at(3))
    assert (await block(rental, unit, at(5), at(6))).status_code == 200
    starved = await block(rental, unit, at(2), at(4))
    assert error(starved) == (409, "RENTAL_UNAVAILABLE"), starved.text
    refused = await book(rental, car, customer, at(5), at(6))
    assert error(refused) == (409, "RENTAL_UNAVAILABLE"), refused.text
    home = rental.world.a.location_id
    busy = await rental.get(query(car, home, at(5), at(6)))
    assert (busy.json()["units"], busy.json()["booked"], busy.json()["available"]) == (1, 1, 0)


# R3b-03 -----------------------------------------------------------------------------


async def test_a_held_unit_does_not_move(rental: Rental) -> None:
    away, _ = seed_other_branch(rental.owner_conn, rental.world.a)
    car, (unit,) = await units(rental, 1)
    held = await block(rental, unit, at(1), at(3))
    assert held.status_code == 200, held.text
    moved = await rental.unit(unit, car, revision=1, location_id=str(away))
    assert error(moved) == (409, "RENTAL_UNIT_HELD"), moved.text
    assert (await release(rental, unit, held.json()["block_id"])).status_code == 200
    moved = await rental.unit(unit, car, revision=1, location_id=str(away))
    assert moved.status_code == 200, moved.text
    with owner_tenant_transaction(rental.owner_conn, rental.tenant):
        where = rental.owner_conn.execute(
            "select r.location_id from gba.rental_units u join gba.resources r "
            "on r.tenant_id = u.tenant_id and r.id = u.resource_id where u.id = %s",
            (unit,),
        ).fetchone()
    assert where == (away,)


# R3b-04 -----------------------------------------------------------------------------


async def test_sql_keeps_blocks_and_their_holds_whole(
    rental: Rental, app_pool: RuntimePool
) -> None:
    _, (unit,) = await units(rental, 1)
    assert (await block(rental, unit, at(1), at(3))).status_code == 200
    tenant = rental.tenant
    for statement in (
        "update gba.rental_unit_blocks set reason = 'FAKE'",
        "delete from gba.rental_unit_blocks",
        "update gba.rental_unit_block_releases set reason = 'FAKE'",
        "delete from gba.rental_unit_block_releases",
    ):
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            async with tenant_transaction(app_pool, tenant) as conn:
                await conn.execute(statement)
    with pytest.raises(psycopg.errors.CheckViolation):
        async with tenant_transaction(app_pool, tenant) as conn:
            await conn.execute(
                "insert into gba.resource_allocations "
                "(tenant_id, resource_id, source_kind, source_id, during, state) "
                "select %s, resource_id, 'rental_block', %s, "
                "tstzrange('2031-07-01', '2031-07-02', '[)'), 'confirmed' "
                "from gba.rental_units where id = %s",
                (tenant, uuid7(), unit),
            )
    with pytest.raises(psycopg.errors.CheckViolation):
        async with tenant_transaction(app_pool, tenant) as conn:
            await conn.execute(
                "update gba.resource_allocations set state = 'released' "
                "where source_kind = 'rental_block'"
            )
    assert block_holds(rental, unit) == [("confirmed", True)]


async def test_scope_module_and_another_company(
    rental: Rental,
    app_pool: RuntimePool,
    idp: FakeIdp,
    manager_a: FakeUser,
    manager_b: FakeUser,
) -> None:
    away, _ = seed_other_branch(rental.owner_conn, rental.world.a)
    _, (unit,) = await units(rental, 1)
    branch = rental.member("manager", away)
    hidden = await block(rental, unit, at(1), at(2), headers=branch)
    assert error(hidden) == (404, "NOT_FOUND"), hidden.text
    other = idp.bearer(manager_b.subject, email=manager_b.email)
    foreign = await block(rental, unit, at(1), at(2), headers=other)
    assert foreign.status_code in (403, 404), foreign.text
    await Config(rental.client, idp).publish(
        manager_a, rental.tenant, 1, ["booking_resources", "counterparties"]
    )
    off = await block(rental, unit, at(1), at(2))
    assert error(off) == (409, "MODULE_DISABLED"), off.text
    assert block_holds(rental, unit) == []
    async with tenant_transaction(app_pool, rental.world.b.tenant_id) as conn:
        row = await (await conn.execute("select count(*) from gba.rental_unit_blocks")).fetchone()
    assert row == (0,)
