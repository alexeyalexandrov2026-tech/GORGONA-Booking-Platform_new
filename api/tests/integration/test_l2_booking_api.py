"""L2a over HTTP: staff booking, reschedule and holds of a staged service; the customer site
refuses a staged service until L2b (FAKE data only)."""

import secrets
from collections.abc import AsyncIterator
from datetime import datetime, timedelta
from typing import Any
from uuid import UUID
from zoneinfo import ZoneInfo

import httpx
import psycopg
import pytest

from gorgona_booking.api.app import create_app
from gorgona_booking.config import Settings
from gorgona_booking.db.pool import RuntimePool, tenant_transaction
from tests.integration import test_management_api as shared
from tests.integration.booking_support import BookingWorld
from tests.integration.customer_support import customer_day, seed_customer_setup
from tests.integration.seed import FakeUser
from tests.integration.test_l2_stage_occupancy import seed_kind, stage_variant
from tests.support.fake_idp import FakeIdp

pytestmark = pytest.mark.anyio
client = shared.client
idp = shared.idp
manager_a = shared.manager_a
ZONE = ZoneInfo("America/New_York")


def local(hour: int, minute: int = 0) -> datetime:
    return datetime.fromisoformat(f"{customer_day()}T{hour:02}:{minute:02}:00").replace(tzinfo=ZONE)


@pytest.fixture
def stage_kit(owner_conn: psycopg.Connection, world: BookingWorld) -> dict[str, UUID]:
    stage_variant(owner_conn, world.a, world.catalog_a.gel_variant_id)
    return {
        "chair": seed_kind(owner_conn, world.a, "chair", "FAKE chair 1"),
        "equipment": seed_kind(owner_conn, world.a, "equipment", "FAKE processor 1"),
    }


def staff_body(
    world: BookingWorld, start: datetime, variant: UUID, **extra: object
) -> dict[str, object]:
    return {
        "location_id": str(world.a.location_id),
        "resource_id": str(world.artist_a1),
        "variant_id": str(variant),
        "starts_at": start.isoformat(),
        "customer_name": "FAKE Colour Client",
        "customer_email": "colour@example.com",
        "customer_phone": "+15551230000",
        **extra,
    }


async def spans(pool: RuntimePool, world: BookingWorld, booking_id: str) -> set[tuple[Any, ...]]:
    async with tenant_transaction(pool, world.a.tenant_id) as conn:
        rows = await (
            await conn.execute(
                "select resource_id, lower(during), upper(during) from gba.booking_allocations "
                "where booking_id=%s",
                (booking_id,),
            )
        ).fetchall()
    return {(r[0], r[1].astimezone(ZONE), r[2].astimezone(ZONE)) for r in rows}


async def test_staff_books_and_reschedules_a_staged_visit(
    client: httpx.AsyncClient,
    world: BookingWorld,
    manager_a: FakeUser,
    idp: FakeIdp,
    stage_kit: dict[str, UUID],
    app_pool: RuntimePool,
) -> None:
    headers = idp.bearer(manager_a.subject, email=manager_a.email)
    path = f"/v1/salons/{world.a.tenant_id}/bookings"
    named = {kind: str(identifier) for kind, identifier in stage_kit.items()}
    created = await client.post(
        path,
        json=staff_body(world, local(11), world.catalog_a.gel_variant_id, stage_resources=named),
        headers=headers,
    )
    assert created.status_code == 201, created.text
    visit = created.json()
    assert visit["resource_id"] == str(world.artist_a1)
    assert datetime.fromisoformat(visit["ends_at"]) == local(12, 50)
    assert await spans(app_pool, world, visit["booking_id"]) == {
        (world.artist_a1, local(11), local(11, 30)),
        (world.artist_a1, local(12, 30), local(12, 50)),
        (stage_kit["chair"], local(11), local(12, 50)),
        (stage_kit["equipment"], local(11, 30), local(12, 30)),
    }
    # The specialist serves someone else while the colour develops.
    gap = await client.post(
        path,
        json=staff_body(world, local(11, 30), world.catalog_a.base_variant_id),
        headers=headers,
    )
    assert gap.status_code == 201, gap.text
    moved = await client.post(
        f"{path}/{visit['booking_id']}/reschedule",
        json={"new_starts_at": local(13).isoformat()},
        headers=headers,
    )
    assert moved.status_code == 200, moved.text
    assert await spans(app_pool, world, moved.json()["booking_id"]) == {
        (world.artist_a1, local(13), local(13, 30)),
        (world.artist_a1, local(14, 30), local(14, 50)),
        (stage_kit["chair"], local(13), local(14, 50)),
        (stage_kit["equipment"], local(13, 30), local(14, 30)),
    }
    # The old visit's intervals are free again.
    again = await client.post(
        path,
        json=staff_body(world, local(11), world.catalog_a.gel_variant_id, stage_resources=named)
        | {"resource_id": str(world.artist_a2)},
        headers=headers,
    )
    assert again.status_code == 201, again.text


async def test_staff_booking_refuses_a_stage_resource_of_another_kind(
    client: httpx.AsyncClient,
    world: BookingWorld,
    manager_a: FakeUser,
    idp: FakeIdp,
    stage_kit: dict[str, UUID],
) -> None:
    headers = idp.bearer(manager_a.subject, email=manager_a.email)
    response = await client.post(
        f"/v1/salons/{world.a.tenant_id}/bookings",
        json=staff_body(
            world,
            local(11),
            world.catalog_a.gel_variant_id,
            stage_resources={"chair": str(world.artist_a2)},
        ),
        headers=headers,
    )
    assert response.status_code == 422, response.text
    assert response.json()["error"]["code"] == "STAGE_RESOURCE_INVALID"


@pytest.fixture
async def guest(
    world: BookingWorld, owner_conn: psycopg.Connection, app_pool: RuntimePool
) -> AsyncIterator[httpx.AsyncClient]:
    seed_customer_setup(owner_conn, world)
    app = create_app(Settings(environment="test"), pool=app_pool)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url=f"http://{world.a.host}"
    ) as http:
        yield http


async def test_the_customer_site_refuses_a_staged_service_until_l2b(
    guest: httpx.AsyncClient, world: BookingWorld, stage_kit: dict[str, UUID]
) -> None:
    query: dict[str, object] = {
        "location_id": str(world.a.location_id),
        "variant_id": str(world.catalog_a.gel_variant_id),
        "add_on_ids": [],
        "day": customer_day(),
        "resource_id": None,
    }
    available = await guest.post("/v1/customer/availability", json=query)
    assert available.status_code == 422, available.text
    assert available.json()["error"]["code"] == "STAGED_SERVICE_NOT_ONLINE"
    body = dict(query)
    body.pop("day")
    body.update({"resource_id": str(world.artist_a1), "start_at": local(11).isoformat()})
    held = await guest.post(
        "/v1/customer/holds",
        json=body,
        headers={"Booking-Token": secrets.token_urlsafe(32), "Idempotency-Key": "l2-guest-1"},
    )
    assert held.status_code == 422, held.text
    assert held.json()["error"]["code"] == "STAGED_SERVICE_NOT_ONLINE"
    # Unstaged services stay online.
    plain = await guest.post(
        "/v1/customer/availability",
        json=query | {"variant_id": str(world.catalog_a.base_variant_id)},
    )
    assert plain.status_code == 200, plain.text


async def test_the_hold_api_takes_stage_resources(
    guest: httpx.AsyncClient, world: BookingWorld, stage_kit: dict[str, UUID]
) -> None:
    start = local(11) + timedelta(days=1)
    response = await guest.post(
        "/v1/holds",
        json={
            "resource_id": str(world.artist_a1),
            "variant_id": str(world.catalog_a.gel_variant_id),
            "start_at": start.isoformat(),
            "stage_resources": {kind: str(identifier) for kind, identifier in stage_kit.items()},
        },
        headers={"Idempotency-Key": "l2-hold-api-1"},
    )
    assert response.status_code == 201, response.text
    assert response.json()["resource_id"] == str(world.artist_a1)
    assert datetime.fromisoformat(response.json()["end_at"]) == start + timedelta(minutes=110)
