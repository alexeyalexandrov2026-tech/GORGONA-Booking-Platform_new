"""L2a: stage-by-stage occupancy (package L, BEAUTY-01; FAKE data only).

Design docs/plan/PACKAGE_L2_DESIGN_2026-10-22.md: each stage of a staged variant occupies the
resources of its kinds for its minutes; consecutive stages on one resource join into one interval.
The specialist is free during processing while the chair stays held. All or nothing; a kind left out
of the request is filled with a free resource of that kind in the branch.
"""

import asyncio
from datetime import datetime
from typing import Any
from uuid import UUID

import psycopg
import pytest

from gorgona_booking.booking.models import (
    ReservationRequest,
    SlotConflictError,
    StageResourceError,
)
from gorgona_booking.booking.repository import lock_resource_schedule
from gorgona_booking.booking.service import BookingService
from gorgona_booking.db.pool import RuntimePool, tenant_transaction
from gorgona_booking.db.provisioning import owner_tenant_transaction
from tests.integration.booking_support import BookingWorld, at
from tests.integration.conftest import ProvisionedDatabase
from tests.integration.seed import Salon
from tests.integration.test_workforce_guards import wait_for_resource_waiters

pytestmark = pytest.mark.anyio

# The 90-minute gel variant becomes 110 minutes: the specialist works 30, the colour develops 60
# (the chair and the processor stay held), the specialist finishes 20.
STAGES = (
    ("active", 30, ("specialist", "chair")),
    ("processing", 60, ("chair", "equipment")),
    ("finish", 20, ("specialist", "chair")),
)


def stage_variant(conn: psycopg.Connection, salon: Salon, variant_id: UUID) -> None:
    with owner_tenant_transaction(conn, salon.tenant_id):
        for position, (kind, minutes, resources) in enumerate(STAGES, start=1):
            conn.execute(
                "insert into gba.variant_stages (tenant_id,variant_id,position,kind,minutes,"
                "resources) values (%s,%s,%s,%s,%s,%s)",
                (salon.tenant_id, variant_id, position, kind, minutes, list(resources)),
            )
        conn.execute(
            "update gba.service_variants set booking_duration_minutes=%s where id=%s",
            (sum(minutes for _, minutes, _ in STAGES), variant_id),
        )


def seed_kind(conn: psycopg.Connection, salon: Salon, kind: str, name: str) -> UUID:
    with owner_tenant_transaction(conn, salon.tenant_id):
        row = conn.execute(
            "insert into gba.resources (tenant_id, location_id, kind, display_name) "
            "values (%s, %s, %s, %s) returning id",
            (salon.tenant_id, salon.location_id, kind, name),
        ).fetchone()
    assert row is not None
    return UUID(str(row[0]))


@pytest.fixture
def staged(owner_conn: psycopg.Connection, world: BookingWorld) -> dict[str, UUID]:
    stage_variant(owner_conn, world.a, world.catalog_a.gel_variant_id)
    return {
        "chair": seed_kind(owner_conn, world.a, "chair", "FAKE chair 1"),
        "equipment": seed_kind(owner_conn, world.a, "equipment", "FAKE processor 1"),
    }


def colour(
    world: BookingWorld,
    start: datetime,
    *,
    resource: UUID | None = None,
    stage_resources: dict[str, UUID] | None = None,
) -> ReservationRequest:
    return ReservationRequest(
        resource_id=resource or world.artist_a1,
        variant_id=world.catalog_a.gel_variant_id,
        starts_at=start,
        stage_resources=tuple(sorted((stage_resources or {}).items())),
    )


async def intervals(
    pool: RuntimePool, tenant_id: UUID, booking_id: UUID
) -> list[tuple[UUID, datetime, datetime, str]]:
    async with tenant_transaction(pool, tenant_id) as conn:
        rows = await (
            await conn.execute(
                "select resource_id, lower(during), upper(during), booking_status "
                "from gba.booking_allocations where booking_id=%s order by lower(during), "
                "resource_id",
                (booking_id,),
            )
        ).fetchall()
    return [(r[0], r[1], r[2], r[3]) for r in rows]


async def mirror(pool: RuntimePool, tenant_id: UUID, booking_id: UUID) -> list[tuple[Any, ...]]:
    async with tenant_transaction(pool, tenant_id) as conn:
        rows = await (
            await conn.execute(
                "select resource_id, lower(during), upper(during), state "
                "from gba.resource_allocations where source_kind='booking' and source_id=%s "
                "order by lower(during), resource_id",
                (booking_id,),
            )
        ).fetchall()
        mismatches = await (
            await conn.execute("select gba.booking_occupancy_mismatches()")
        ).fetchone()
    assert mismatches == (0,)
    return [tuple(r) for r in rows]


STATE = {"HOLD": "held", "CONFIRMED": "confirmed", "CANCELLED": "released", "EXPIRED": "released"}


async def assert_mirrored(pool: RuntimePool, tenant_id: UUID, booking_id: UUID) -> None:
    own = await intervals(pool, tenant_id, booking_id)
    shared = await mirror(pool, tenant_id, booking_id)
    assert shared == [(r, s, e, STATE[status]) for r, s, e, status in own]


# L2-01 ------------------------------------------------------------------------------


async def test_the_specialist_is_held_only_while_working(
    world: BookingWorld, staged: dict[str, UUID], app_pool: RuntimePool
) -> None:
    service = BookingService(app_pool)
    result = await service.create_confirmed_booking(
        world.a.tenant_id,
        colour(world, at(10), stage_resources=staged),
        actor="test:l2",
        idempotency_key=None,
    )
    assert result.resource_id == world.artist_a1  # the specialist is the primary resource
    assert (result.starts_at, result.ends_at) == (at(10), at(11, 50))
    rows = await intervals(app_pool, world.a.tenant_id, result.booking_id)
    assert sorted((r, s, e) for r, s, e, _ in rows) == sorted(
        [
            (world.artist_a1, at(10), at(10, 30)),
            (world.artist_a1, at(11, 30), at(11, 50)),
            (staged["chair"], at(10), at(11, 50)),
            (staged["equipment"], at(10, 30), at(11, 30)),
        ]
    )
    await assert_mirrored(app_pool, world.a.tenant_id, result.booking_id)
    # Another client takes the specialist while the colour develops.
    other = await service.create_confirmed_booking(
        world.a.tenant_id,
        world.request(at(10, 30)),
        actor="test:l2",
        idempotency_key=None,
    )
    assert (other.starts_at, other.ends_at) == (at(10, 30), at(11, 30))
    # But not across the finish.
    with pytest.raises(SlotConflictError):
        await service.create_confirmed_booking(
            world.a.tenant_id, world.request(at(11, 31)), actor="test:l2", idempotency_key=None
        )


# L2-02 ------------------------------------------------------------------------------


async def test_a_busy_chair_refuses_the_whole_booking(
    world: BookingWorld, staged: dict[str, UUID], app_pool: RuntimePool
) -> None:
    service = BookingService(app_pool)
    # An unstaged booking on the chair itself, inside the processing stage.
    await service.create_confirmed_booking(
        world.a.tenant_id,
        world.request(at(11), resource=staged["chair"], variant=world.catalog_a.base_variant_id),
        actor="test:l2",
        idempotency_key=None,
    )
    with pytest.raises(SlotConflictError):
        await service.create_confirmed_booking(
            world.a.tenant_id,
            colour(world, at(10), stage_resources=staged),
            actor="test:l2",
            idempotency_key=None,
        )
    async with tenant_transaction(app_pool, world.a.tenant_id) as conn:
        written = await (
            await conn.execute(
                "select count(*) from gba.booking_allocations where resource_id = any(%s)",
                ([world.artist_a1, staged["equipment"]],),
            )
        ).fetchone()
    assert written == (0,)


# L2-03 ------------------------------------------------------------------------------


async def test_a_left_out_kind_is_filled_with_a_free_resource(
    owner_conn: psycopg.Connection,
    world: BookingWorld,
    staged: dict[str, UUID],
    app_pool: RuntimePool,
) -> None:
    second_chair = seed_kind(owner_conn, world.a, "chair", "FAKE chair 2")
    service = BookingService(app_pool)

    async def used(booking_id: UUID) -> set[UUID]:
        return {r for r, *_ in await intervals(app_pool, world.a.tenant_id, booking_id)}

    first = await service.create_confirmed_booking(
        world.a.tenant_id, colour(world, at(10)), actor="test:l2", idempotency_key=None
    )
    first_used = await used(first.booking_id)
    assert staged["equipment"] in first_used
    assert len(first_used & {staged["chair"], second_chair}) == 1
    # Another specialist at the same time: a chair is free, the only processor is not.
    with pytest.raises(SlotConflictError):
        await service.create_confirmed_booking(
            world.a.tenant_id,
            colour(world, at(10), resource=world.artist_a2),
            actor="test:l2",
            idempotency_key=None,
        )
    second_processor = seed_kind(owner_conn, world.a, "equipment", "FAKE processor 2")
    second = await service.create_confirmed_booking(
        world.a.tenant_id,
        colour(world, at(10), resource=world.artist_a2),
        actor="test:l2",
        idempotency_key=None,
    )
    second_used = await used(second.booking_id)
    assert second_processor in second_used
    assert (first_used | second_used) >= {staged["chair"], second_chair}
    # No chair is left for a third specialist.
    third_artist = seed_kind(owner_conn, world.a, "artist", "FAKE artist A3")
    with pytest.raises(SlotConflictError):
        await service.create_confirmed_booking(
            world.a.tenant_id,
            colour(world, at(10), resource=third_artist),
            actor="test:l2",
            idempotency_key=None,
        )


@pytest.mark.parametrize("wrong", ["artist_as_chair", "other_branch_kind", "unknown_kind"])
async def test_a_named_stage_resource_must_fit_its_kind(
    world: BookingWorld, staged: dict[str, UUID], app_pool: RuntimePool, wrong: str
) -> None:
    resources = dict(staged)
    if wrong == "artist_as_chair":
        resources["chair"] = world.artist_a2
    elif wrong == "other_branch_kind":
        resources["chair"] = world.artist_b1
    else:
        resources["desk"] = staged["chair"]
    with pytest.raises(StageResourceError):
        await BookingService(app_pool).create_confirmed_booking(
            world.a.tenant_id,
            colour(world, at(10), stage_resources=resources),
            actor="test:l2",
            idempotency_key=None,
        )


async def test_the_specialist_must_be_an_artist(
    world: BookingWorld, staged: dict[str, UUID], app_pool: RuntimePool
) -> None:
    with pytest.raises(StageResourceError):
        await BookingService(app_pool).create_confirmed_booking(
            world.a.tenant_id,
            colour(world, at(10), resource=staged["chair"]),
            actor="test:l2",
            idempotency_key=None,
        )


# L2-05 ------------------------------------------------------------------------------


async def test_confirm_and_cancel_move_every_interval(
    world: BookingWorld, staged: dict[str, UUID], app_pool: RuntimePool
) -> None:
    service = BookingService(app_pool)
    hold = await service.create_hold(
        world.a.tenant_id,
        colour(world, at(10), stage_resources=staged),
        actor="test:l2",
        idempotency_key="l2-hold-1",
    )
    assert {s for *_, s in await intervals(app_pool, world.a.tenant_id, hold.booking_id)} == {
        "HOLD"
    }
    await assert_mirrored(app_pool, world.a.tenant_id, hold.booking_id)
    confirmed = await service.confirm(world.a.tenant_id, hold.booking_id, actor="test:l2")
    assert confirmed.status == "CONFIRMED"
    assert confirmed.resource_id == world.artist_a1
    rows = await intervals(app_pool, world.a.tenant_id, hold.booking_id)
    assert len(rows) == 4
    assert {s for *_, s in rows} == {"CONFIRMED"}
    await assert_mirrored(app_pool, world.a.tenant_id, hold.booking_id)
    await service.cancel(world.a.tenant_id, hold.booking_id, actor="test:l2")
    assert {s for *_, s in await intervals(app_pool, world.a.tenant_id, hold.booking_id)} == {
        "CANCELLED"
    }
    await assert_mirrored(app_pool, world.a.tenant_id, hold.booking_id)
    # Everything is free again.
    again = await service.create_confirmed_booking(
        world.a.tenant_id,
        colour(world, at(10), stage_resources=staged),
        actor="test:l2",
        idempotency_key=None,
    )
    assert again.status == "CONFIRMED"


async def test_a_replayed_key_returns_the_same_staged_booking(
    world: BookingWorld, staged: dict[str, UUID], app_pool: RuntimePool
) -> None:
    service = BookingService(app_pool)
    request = colour(world, at(10), stage_resources=staged)
    first = await service.create_hold(
        world.a.tenant_id, request, actor="test:l2", idempotency_key="l2-replay-1"
    )
    second = await service.create_hold(
        world.a.tenant_id, request, actor="test:l2", idempotency_key="l2-replay-1"
    )
    assert second.replayed
    assert second.booking_id == first.booking_id
    assert request.fingerprint("x") != colour(world, at(10)).fingerprint("x")


# L2-06 ------------------------------------------------------------------------------


async def test_an_unstaged_booking_keeps_one_allocation(
    world: BookingWorld, staged: dict[str, UUID], app_pool: RuntimePool
) -> None:
    result = await BookingService(app_pool).create_confirmed_booking(
        world.a.tenant_id, world.request(at(14)), actor="test:l2", idempotency_key=None
    )
    rows = await intervals(app_pool, world.a.tenant_id, result.booking_id)
    assert [(r, s, e) for r, s, e, _ in rows] == [(world.artist_a1, at(14), at(15))]
    await assert_mirrored(app_pool, world.a.tenant_id, result.booking_id)


async def test_stage_resources_are_refused_for_an_unstaged_variant(
    world: BookingWorld, staged: dict[str, UUID], app_pool: RuntimePool
) -> None:
    request = ReservationRequest(
        resource_id=world.artist_a1,
        variant_id=world.catalog_a.base_variant_id,
        starts_at=at(14),
        stage_resources=(("chair", staged["chair"]),),
    )
    with pytest.raises(StageResourceError):
        await BookingService(app_pool).create_confirmed_booking(
            world.a.tenant_id, request, actor="test:l2", idempotency_key=None
        )


# L2-04 ------------------------------------------------------------------------------


async def test_two_racing_visits_leave_one_after_an_observed_wait(
    world: BookingWorld,
    staged: dict[str, UUID],
    app_pool: RuntimePool,
    test_database: ProvisionedDatabase,
) -> None:
    service = BookingService(app_pool)

    async def visit(index: int) -> str:
        try:
            await service.create_confirmed_booking(
                world.a.tenant_id,
                colour(world, at(10, index), stage_resources=staged),
                actor=f"test:l2-race-{index}",
                idempotency_key=None,
            )
        except SlotConflictError:
            return "conflict"
        return "success"

    monitor = await psycopg.AsyncConnection.connect(
        test_database.admin_dsn, dbname=test_database.name, autocommit=True
    )
    tasks: list[asyncio.Task[str]] = []
    try:
        async with tenant_transaction(app_pool, world.a.tenant_id) as barrier:
            # The first lock either visit takes: the lowest resource id it uses.
            first = min(world.artist_a1, staged["chair"], staged["equipment"])
            await lock_resource_schedule(barrier, world.a.tenant_id, first)
            tasks = [asyncio.create_task(visit(index)) for index in range(2)]
            await wait_for_resource_waiters(monitor, 2)
            assert all(not task.done() for task in tasks)
        assert sorted(await asyncio.wait_for(asyncio.gather(*tasks), 10)) == [
            "conflict",
            "success",
        ]
    finally:
        for task in tasks:
            if not task.done():
                task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        await monitor.close()
    async with tenant_transaction(app_pool, world.a.tenant_id) as conn:
        overlaps = await (
            await conn.execute(
                "select count(*) from gba.booking_allocations x join gba.booking_allocations y "
                "on x.resource_id=y.resource_id and x.id<y.id and x.during && y.during "
                "where x.booking_status='CONFIRMED' and y.booking_status='CONFIRMED'"
            )
        ).fetchone()
    assert overlaps == (0,)
