"""L2c: one visit, several services (package L, BEAUTY-01; FAKE data only).

The colour (staged gel, 110 minutes) is followed by a FAKE style (30 minutes, unstaged) of another
service; one artist serves both, the chair and processor are held for the colour's stages only.
"""

import secrets
from datetime import datetime
from typing import Any
from uuid import UUID
from zoneinfo import ZoneInfo

import httpx
import psycopg
import pytest

from gorgona_booking.booking.models import ReservationRequest
from gorgona_booking.db.pool import RuntimePool, tenant_transaction
from gorgona_booking.db.provisioning import owner_tenant_transaction
from tests.integration import test_management_api as shared
from tests.integration.booking_support import BookingWorld
from tests.integration.customer_support import customer_day
from tests.integration.seed import FakeUser
from tests.integration.test_l2_booking_api import guest
from tests.integration.test_l2_stage_occupancy import seed_kind, stage_variant
from tests.support.fake_idp import FakeIdp

pytestmark = pytest.mark.anyio
client = shared.client
idp = shared.idp
manager_a = shared.manager_a
__all__ = ["client", "guest", "idp", "manager_a"]
ZONE = ZoneInfo("America/New_York")


def local(hour: int, minute: int = 0) -> datetime:
    return datetime.fromisoformat(f"{customer_day()}T{hour:02}:{minute:02}:00").replace(tzinfo=ZONE)


def seed_style(conn: psycopg.Connection, world: BookingWorld, artists: tuple[UUID, ...]) -> UUID:
    """A second service (FAKE style, 30 minutes) served only by the given artists."""
    tenant = world.a.tenant_id
    with owner_tenant_transaction(conn, tenant):
        conn.execute(
            "insert into gba.service_components (tenant_id, code, name) "
            "values (%s, 'FAKE_STYLE', 'FAKE_STYLE')",
            (tenant,),
        )
        service = conn.execute(
            "insert into gba.services (tenant_id, code, name) "
            "values (%s, 'FAKE_STYLING', 'FAKE styling') returning id",
            (tenant,),
        ).fetchone()
        assert service is not None
        row = conn.execute(
            "insert into gba.service_variants (tenant_id, service_id, code, name, status, "
            "price_cents, currency, booking_duration_minutes, is_bookable) values "
            "(%s, %s, 'FAKE_STYLE', 'FAKE style', 'published', 3000, 'USD', 30, true) returning id",
            (tenant, service[0]),
        ).fetchone()
        assert row is not None
        conn.execute(
            "insert into gba.variant_components (tenant_id, variant_id, component_code) "
            "values (%s, %s, 'FAKE_STYLE')",
            (tenant, row[0]),
        )
        for artist in artists:
            conn.execute(
                "insert into gba.resource_services (tenant_id, resource_id, service_id) "
                "values (%s, %s, %s)",
                (tenant, artist, service[0]),
            )
    return UUID(str(row[0]))


def make_visit(conn: psycopg.Connection, world: BookingWorld) -> dict[str, UUID]:
    stage_variant(conn, world.a, world.catalog_a.gel_variant_id)
    return {
        "chair": seed_kind(conn, world.a, "chair", "FAKE chair 1"),
        "equipment": seed_kind(conn, world.a, "equipment", "FAKE processor 1"),
        "style": seed_style(conn, world, (world.artist_a1,)),
    }


@pytest.fixture
def visit(
    guest: httpx.AsyncClient, owner_conn: psycopg.Connection, world: BookingWorld
) -> dict[str, UUID]:
    # The guest fixture seeds hours and services first, so the style is linked to A1 only.
    return make_visit(owner_conn, world)


@pytest.fixture
def staff_visit(
    client: httpx.AsyncClient, owner_conn: psycopg.Connection, world: BookingWorld
) -> dict[str, UUID]:
    # The management client seeds the same setup; build the visit after it.
    return make_visit(owner_conn, world)


def extra(visit: dict[str, UUID]) -> list[dict[str, object]]:
    return [{"variant_id": str(visit["style"]), "add_on_ids": []}]


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


def expected(world: BookingWorld, visit: dict[str, UUID], hour: int) -> set[tuple[Any, ...]]:
    # Colour 30 + 60 + 20, then the style 30 right after the finish: the artist's finish and the
    # style join into one interval.
    return {
        (world.artist_a1, local(hour), local(hour, 30)),
        (world.artist_a1, local(hour + 1, 30), local(hour + 2, 20)),
        (visit["chair"], local(hour), local(hour + 1, 50)),
        (visit["equipment"], local(hour, 30), local(hour + 1, 30)),
    }


# L2-14 ------------------------------------------------------------------------------


async def test_staff_books_a_two_service_visit(
    client: httpx.AsyncClient,
    world: BookingWorld,
    manager_a: FakeUser,
    idp: FakeIdp,
    staff_visit: dict[str, UUID],
    app_pool: RuntimePool,
) -> None:
    visit = staff_visit
    headers = idp.bearer(manager_a.subject, email=manager_a.email)
    created = await client.post(
        f"/v1/salons/{world.a.tenant_id}/bookings",
        json={
            "location_id": str(world.a.location_id),
            "resource_id": str(world.artist_a1),
            "variant_id": str(world.catalog_a.gel_variant_id),
            "starts_at": local(11).isoformat(),
            "customer_name": "FAKE Visit Client",
            "customer_email": "visit@example.com",
            "customer_phone": "+15551239999",
            "extra_lines": extra(visit),
        },
        headers=headers,
    )
    assert created.status_code == 201, created.text
    booking = created.json()
    assert booking["variant_id"] == str(world.catalog_a.gel_variant_id)
    assert datetime.fromisoformat(booking["ends_at"]) == local(13, 20)
    assert booking["total_cents"] == 6500 + 3000
    assert await spans(app_pool, world, booking["booking_id"]) == expected(world, visit, 11)


async def test_a_guest_sees_and_holds_a_two_service_visit(
    guest: httpx.AsyncClient, world: BookingWorld, visit: dict[str, UUID], app_pool: RuntimePool
) -> None:
    query: dict[str, object] = {
        "location_id": str(world.a.location_id),
        "variant_id": str(world.catalog_a.gel_variant_id),
        "add_on_ids": [],
        "day": customer_day(),
        "resource_id": None,
        "extra_lines": extra(visit),
    }
    available = await guest.post("/v1/customer/availability", json=query)
    assert available.status_code == 200, available.text
    body = available.json()
    assert [line["code"] for line in body["quote"]["lines"]] == ["FAKE_GEL", "FAKE_STYLE"]
    assert body["quote"]["booking_duration_minutes"] == 140
    # Only A1 serves the style.
    assert {slot["resource_id"] for slot in body["slots"]} == {str(world.artist_a1)}
    hold = dict(query)
    hold.pop("day")
    hold.update({"resource_id": str(world.artist_a1), "start_at": local(11).isoformat()})
    held = await guest.post(
        "/v1/customer/holds",
        json=hold,
        headers={"Booking-Token": secrets.token_urlsafe(32), "Idempotency-Key": "l2c-guest-1"},
    )
    assert held.status_code == 201, held.text
    assert await spans(app_pool, world, held.json()["booking_id"]) == expected(world, visit, 11)


async def test_the_hold_api_takes_extra_lines(
    guest: httpx.AsyncClient, world: BookingWorld, visit: dict[str, UUID], app_pool: RuntimePool
) -> None:
    held = await guest.post(
        "/v1/holds",
        json={
            "resource_id": str(world.artist_a1),
            "variant_id": str(world.catalog_a.gel_variant_id),
            "start_at": local(13).isoformat(),
            "extra_lines": extra(visit),
        },
        headers={"Idempotency-Key": "l2c-hold-api-1"},
    )
    assert held.status_code == 201, held.text
    assert await spans(app_pool, world, held.json()["booking_id"]) == expected(world, visit, 13)


async def test_a_component_twice_across_services_is_refused(
    guest: httpx.AsyncClient, world: BookingWorld, visit: dict[str, UUID]
) -> None:
    # Base and gel both provide the FAKE pedicure.
    response = await guest.post(
        "/v1/holds",
        json={
            "resource_id": str(world.artist_a1),
            "variant_id": str(world.catalog_a.gel_variant_id),
            "start_at": local(13).isoformat(),
            "extra_lines": [{"variant_id": str(world.catalog_a.base_variant_id), "add_on_ids": []}],
        },
        headers={"Idempotency-Key": "l2c-duplicate-1"},
    )
    assert response.status_code == 422, response.text
    assert response.json()["error"]["code"] == "INCOMPATIBLE_SELECTION"


# L2-15 ------------------------------------------------------------------------------


def test_a_one_service_request_keeps_its_fingerprint(world: BookingWorld) -> None:
    single = world.request(datetime(2031, 6, 2, 10, tzinfo=ZONE))
    assert single.extra_lines == ()
    widened = ReservationRequest(
        resource_id=single.resource_id,
        variant_id=single.variant_id,
        starts_at=single.starts_at,
        extra_lines=((world.catalog_a.base_variant_id, ()),),
    )
    assert widened.fingerprint("x") != single.fingerprint("x")
    # The fingerprint of a one-service request is the one stored before L2c.
    assert single.fingerprint("x") == ReservationRequest(
        resource_id=single.resource_id, variant_id=single.variant_id, starts_at=single.starts_at
    ).fingerprint("x")
