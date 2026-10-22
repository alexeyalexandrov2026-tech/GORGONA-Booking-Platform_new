"""L2b: guests book a staged service (package L, BEAUTY-01; FAKE data only).

A start is offered when the artist is free in their working stages and every other stage kind has a
free resource in the branch; the hold places every stage with the L2a planner.
"""

import asyncio
import secrets
from datetime import datetime, timedelta
from typing import Any
from uuid import UUID
from zoneinfo import ZoneInfo

import httpx
import psycopg
import pytest

from gorgona_booking.booking.repository import lock_resource_schedule
from gorgona_booking.booking.service import BookingService
from gorgona_booking.db.pool import RuntimePool, tenant_transaction
from tests.integration.booking_support import BookingWorld
from tests.integration.conftest import ProvisionedDatabase
from tests.integration.customer_support import customer_day
from tests.integration.test_l2_booking_api import guest
from tests.integration.test_l2_stage_occupancy import seed_kind, stage_variant
from tests.integration.test_workforce_guards import wait_for_resource_waiters

pytestmark = pytest.mark.anyio
__all__ = ["guest"]
ZONE = ZoneInfo("America/New_York")
DETAILS = {
    "name": "FAKE Colour Guest",
    "email": "colour-guest@example.test",
    "phone": "+1 555 010 4321",
    "accept_policy": True,
}


def local(hour: int, minute: int = 0) -> datetime:
    return datetime.fromisoformat(f"{customer_day()}T{hour:02}:{minute:02}:00").replace(tzinfo=ZONE)


@pytest.fixture
def kit(owner_conn: psycopg.Connection, world: BookingWorld) -> dict[str, UUID]:
    stage_variant(owner_conn, world.a, world.catalog_a.gel_variant_id)
    return {
        "chair": seed_kind(owner_conn, world.a, "chair", "FAKE chair 1"),
        "equipment": seed_kind(owner_conn, world.a, "equipment", "FAKE processor 1"),
    }


def query(world: BookingWorld, artist: UUID | None = None) -> dict[str, object]:
    return {
        "location_id": str(world.a.location_id),
        "variant_id": str(world.catalog_a.gel_variant_id),
        "add_on_ids": [],
        "day": customer_day(),
        "resource_id": str(artist) if artist else None,
    }


async def starts(guest: httpx.AsyncClient, world: BookingWorld, artist: UUID) -> set[datetime]:
    response = await guest.post("/v1/customer/availability", json=query(world, artist))
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["quote"]["version"] == 2
    assert [s["kind"] for s in body["quote"]["stages"]] == ["active", "processing", "finish"]
    return {datetime.fromisoformat(s["start_at"]).astimezone(ZONE) for s in body["slots"]}


async def hold(
    guest: httpx.AsyncClient, world: BookingWorld, artist: UUID, start: datetime, key: str
) -> tuple[httpx.Response, str]:
    body = query(world, artist)
    body.pop("day")
    body["start_at"] = start.isoformat()
    token = secrets.token_urlsafe(32)
    response = await guest.post(
        "/v1/customer/holds",
        json=body,
        headers={"Booking-Token": token, "Idempotency-Key": key},
    )
    return response, token


async def spans(pool: RuntimePool, world: BookingWorld, booking_id: str) -> set[tuple[Any, ...]]:
    async with tenant_transaction(pool, world.a.tenant_id) as conn:
        rows = await (
            await conn.execute(
                "select resource_id, lower(during), upper(during), booking_status "
                "from gba.booking_allocations where booking_id=%s",
                (booking_id,),
            )
        ).fetchall()
    return {(r[0], r[1].astimezone(ZONE), r[2].astimezone(ZONE), r[3]) for r in rows}


# L2-08 ------------------------------------------------------------------------------


async def test_a_staged_start_needs_every_stage_resource(
    guest: httpx.AsyncClient, world: BookingWorld, kit: dict[str, UUID], app_pool: RuntimePool
) -> None:
    free = await starts(guest, world, world.artist_a1)
    assert local(11) in free
    service = BookingService(app_pool)
    # The only processor is busy 12:00-13:00: a visit from 11:00 needs it 11:30-12:30.
    await service.create_confirmed_booking(
        world.a.tenant_id,
        world.request(
            local(12), resource=kit["equipment"], variant=world.catalog_a.base_variant_id
        ),
        actor="test:l2b",
        idempotency_key=None,
    )
    blocked = await starts(guest, world, world.artist_a1)
    assert local(11) not in blocked
    assert local(11, 30) not in blocked  # processor needed 12:00-13:00
    assert local(10) in blocked  # processor needed 10:30-11:30
    assert local(13) in blocked  # processor needed 13:30-14:30


async def test_the_artist_may_be_busy_while_the_colour_develops(
    guest: httpx.AsyncClient, world: BookingWorld, kit: dict[str, UUID], app_pool: RuntimePool
) -> None:
    # The artist has a one-hour client 12:00-13:00.
    await BookingService(app_pool).create_confirmed_booking(
        world.a.tenant_id,
        world.request(local(12)),
        actor="test:l2b",
        idempotency_key=None,
    )
    free = await starts(guest, world, world.artist_a1)
    # From 11:30 the artist works 11:30-12:00 and 13:00-13:20: the client fits the processing.
    assert local(11, 30) in free
    # From 11:00 the artist must finish 12:30-12:50, inside the other client.
    assert local(11) not in free


async def test_no_chair_in_the_branch_offers_nothing(
    guest: httpx.AsyncClient, owner_conn: psycopg.Connection, world: BookingWorld
) -> None:
    stage_variant(owner_conn, world.a, world.catalog_a.gel_variant_id)
    seed_kind(owner_conn, world.a, "equipment", "FAKE processor only")
    assert await starts(guest, world, world.artist_a1) == set()


# L2-09 ------------------------------------------------------------------------------


async def test_a_guest_holds_and_confirms_every_stage(
    guest: httpx.AsyncClient, world: BookingWorld, kit: dict[str, UUID], app_pool: RuntimePool
) -> None:
    held, token = await hold(guest, world, world.artist_a1, local(11), "l2b-guest-hold-1")
    assert held.status_code == 201, held.text
    booking = held.json()
    assert booking["resource_id"] == str(world.artist_a1)
    assert booking["quote"]["version"] == 2
    expected = {
        (world.artist_a1, local(11), local(11, 30)),
        (world.artist_a1, local(12, 30), local(12, 50)),
        (kit["chair"], local(11), local(12, 50)),
        (kit["equipment"], local(11, 30), local(12, 30)),
    }
    assert {s[:3] for s in await spans(app_pool, world, booking["booking_id"])} == expected
    confirmed = await guest.post(
        f"/v1/customer/bookings/{booking['booking_id']}/confirm",
        json=DETAILS,
        headers={"Booking-Token": token, "Idempotency-Key": "l2b-guest-confirm-1"},
    )
    assert confirmed.status_code == 200, confirmed.text
    rows = await spans(app_pool, world, booking["booking_id"])
    assert {s[:3] for s in rows} == expected
    assert {s[3] for s in rows} == {"CONFIRMED"}
    # The same start is gone for every artist: the only chair is taken.
    assert local(11) not in await starts(guest, world, world.artist_a2)


# L2-10 ------------------------------------------------------------------------------


async def test_two_guests_racing_for_the_last_chair_leave_one_hold(
    guest: httpx.AsyncClient,
    world: BookingWorld,
    kit: dict[str, UUID],
    app_pool: RuntimePool,
    test_database: ProvisionedDatabase,
) -> None:
    async def attempt(artist: UUID, index: int) -> int:
        response, _ = await hold(guest, world, artist, local(11), f"l2b-race-{index}")
        return response.status_code

    monitor = await psycopg.AsyncConnection.connect(
        test_database.admin_dsn, dbname=test_database.name, autocommit=True
    )
    tasks: list[asyncio.Task[int]] = []
    try:
        async with tenant_transaction(app_pool, world.a.tenant_id) as barrier:
            # The chair is in both lock sets; whoever comes second waits behind the first.
            await lock_resource_schedule(barrier, world.a.tenant_id, kit["chair"])
            tasks = [
                asyncio.create_task(attempt(world.artist_a1, 1)),
                asyncio.create_task(attempt(world.artist_a2, 2)),
            ]
            await wait_for_resource_waiters(monitor, 2)
            assert all(not task.done() for task in tasks)
        assert sorted(await asyncio.wait_for(asyncio.gather(*tasks), 15)) == [201, 409]
    finally:
        for task in tasks:
            if not task.done():
                task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        await monitor.close()


async def test_an_unstaged_guest_booking_is_unchanged(
    guest: httpx.AsyncClient, world: BookingWorld, kit: dict[str, UUID], app_pool: RuntimePool
) -> None:
    body = query(world, world.artist_a1) | {"variant_id": str(world.catalog_a.base_variant_id)}
    available = await guest.post("/v1/customer/availability", json=body)
    assert available.status_code == 200, available.text
    assert available.json()["quote"]["version"] == 1
    assert "stages" not in available.json()["quote"]
    slot = available.json()["slots"][0]
    body.pop("day")
    body["start_at"] = slot["start_at"]
    held = await guest.post(
        "/v1/customer/holds",
        json=body,
        headers={"Booking-Token": secrets.token_urlsafe(32), "Idempotency-Key": "l2b-plain-1"},
    )
    assert held.status_code == 201, held.text
    rows = await spans(app_pool, world, held.json()["booking_id"])
    start = datetime.fromisoformat(slot["start_at"]).astimezone(ZONE)
    assert {s[:3] for s in rows} == {(world.artist_a1, start, start + timedelta(minutes=60))}
