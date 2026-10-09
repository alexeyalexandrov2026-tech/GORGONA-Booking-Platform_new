"""Where a resource kind matters today (package I, slice I0; ADR-0025).

Package I plans a resource kind for staff work time. These tests pin what booking,
reservations and staff setup do with the kinds that exist now, so slice I1 changes
each boundary on purpose. A chair or a room is already a resource customers cannot
book; here it stands in for the planned kind and is given everything that makes an
artist bookable.
"""

import secrets
from datetime import datetime
from uuid import UUID, uuid7
from zoneinfo import ZoneInfo

import httpx
import psycopg
import pytest

from gorgona_booking.booking.service import BookingService
from gorgona_booking.db.pool import RuntimePool, tenant_transaction
from gorgona_booking.db.provisioning import owner_tenant_transaction
from tests.integration import test_management_api as shared
from tests.integration import test_workforce as workforce_shared
from tests.integration.booking_support import BookingWorld, at
from tests.integration.customer_support import customer_day
from tests.integration.seed import FAKE_TIMEZONE, FakeUser
from tests.integration.test_customer_api import customer_client, first_slot, hold, selection
from tests.integration.test_resource_reservations import Reservations
from tests.integration.test_workforce import Workforce
from tests.support.fake_idp import FakeIdp

pytestmark = pytest.mark.anyio
__all__ = ["customer_client"]
client = shared.client
idp = shared.idp
manager_a = shared.manager_a
workforce = workforce_shared.workforce
ACTOR = "test:resource-kinds"


async def test_staff_lookalike_never_enters_customer_or_management_booking(
    workforce: Workforce,
    owner_conn: psycopg.Connection,
    world: BookingWorld,
) -> None:
    profile = await workforce.profile()
    resource = str(profile["resource_id"])
    with owner_tenant_transaction(owner_conn, world.a.tenant_id):
        owner_conn.execute(
            "insert into gba.resource_services (tenant_id,resource_id,service_id) "
            "select %s,%s,id from gba.services",
            (world.a.tenant_id, resource),
        )
        for weekday in range(1, 8):
            owner_conn.execute(
                "insert into gba.resource_hours "
                "(tenant_id,resource_id,weekday,opens_minute,closes_minute) "
                "values (%s,%s,%s,600,960)",
                (world.a.tenant_id, resource, weekday),
            )
    # Public and management paths share the already seeded ASGI app.
    public = workforce.client
    public_headers = {"Host": world.a.host}
    boot = await public.get("/v1/customer/bootstrap", headers=public_headers)
    assert resource not in {a["id"] for a in boot.json()["artists"]}
    for path, http, headers in (
        ("/v1/customer/availability", public, public_headers),
        (f"/v1/salons/{world.a.tenant_id}/availability", workforce.client, workforce.headers),
    ):
        response = await http.post(
            path, json={**selection(world), "resource_id": resource}, headers=headers
        )
        assert response.status_code == 404, response.text
    slots = await public.post(
        "/v1/customer/availability", json=selection(world), headers=public_headers
    )
    slot = slots.json()["slots"][0]
    body = selection(world)
    body.pop("day")
    body.update({"resource_id": resource, "start_at": slot["start_at"]})
    held = await public.post(
        "/v1/customer/holds",
        headers={
            **public_headers,
            "Idempotency-Key": str(uuid7()),
            "Booking-Token": secrets.token_urlsafe(32),
        },
        json=body,
    )
    assert held.status_code == 404, held.text

    refused = await workforce.client.post(
        f"/v1/salons/{world.a.tenant_id}/bookings",
        headers=workforce.headers,
        json={
            "location_id": str(world.a.location_id),
            "resource_id": resource,
            "variant_id": str(world.catalog_a.base_variant_id),
            "starts_at": slot["start_at"],
            "customer_name": "FAKE Guest",
            "customer_email": "guest@example.com",
            "customer_phone": "+15550000000",
        },
    )
    assert refused.status_code == 404, refused.text

    with owner_tenant_transaction(owner_conn, world.a.tenant_id):
        assert owner_conn.execute(
            "select count(*) from gba.resource_allocations where resource_id=%s", (resource,)
        ).fetchone() == (0,)


def seed_kind(conn: psycopg.Connection, world: BookingWorld, kind: str) -> UUID:
    salon = world.a
    with owner_tenant_transaction(conn, salon.tenant_id):
        row = conn.execute(
            "insert into gba.resources (tenant_id, location_id, kind, display_name) "
            "values (%s, %s, %s, %s) returning id",
            (salon.tenant_id, salon.location_id, kind, f"FAKE {kind}"),
        ).fetchone()
    assert row is not None
    return UUID(str(row[0]))


def seed_lookalike(conn: psycopg.Connection, world: BookingWorld, kind: str) -> UUID:
    """A resource of another kind with every service and the hours of an artist."""
    salon, resource = world.a, seed_kind(conn, world, kind)
    with owner_tenant_transaction(conn, salon.tenant_id):
        conn.execute(
            "insert into gba.resource_services (tenant_id, resource_id, service_id) "
            "select %s, %s, id from gba.services",
            (salon.tenant_id, resource),
        )
        for weekday in range(1, 8):
            conn.execute(
                "insert into gba.resource_hours "
                "(tenant_id, resource_id, weekday, opens_minute, closes_minute) "
                "values (%s, %s, %s, 600, 960)",
                (salon.tenant_id, resource, weekday),
            )
    return resource


async def active_sources(pool: RuntimePool, tenant: UUID, resource: UUID) -> list[str]:
    async with tenant_transaction(pool, tenant) as conn:
        rows = await (
            await conn.execute(
                "select source_kind from gba.resource_allocations "
                "where resource_id = %s and state in ('held', 'confirmed') order by created_at",
                (resource,),
            )
        ).fetchall()
    return [str(row[0]) for row in rows]


@pytest.fixture
def staff(
    client: httpx.AsyncClient, world: BookingWorld, manager_a: FakeUser, idp: FakeIdp
) -> Reservations:
    return Reservations(client, world.a.tenant_id, manager_a, idp)


async def test_customers_are_offered_and_can_hold_only_artists(
    customer_client: httpx.AsyncClient, world: BookingWorld, owner_conn: psycopg.Connection
) -> None:
    chair = seed_lookalike(owner_conn, world, "chair")
    artists = {str(world.artist_a1), str(world.artist_a2)}

    boot = await customer_client.get("/v1/customer/bootstrap")
    assert boot.status_code == 200, boot.text
    assert {artist["id"] for artist in boot.json()["artists"]} == artists

    slots = await customer_client.post("/v1/customer/availability", json=selection(world))
    assert slots.status_code == 200, slots.text
    offered = {slot["resource_id"] for slot in slots.json()["slots"]}
    assert offered
    assert offered <= artists

    asked = await customer_client.post(
        "/v1/customer/availability", json={**selection(world), "resource_id": str(chair)}
    )
    assert asked.status_code == 404, asked.text

    slot = await first_slot(customer_client, world)
    held = await hold(
        customer_client,
        world,
        {**slot, "resource_id": str(chair)},
        secrets.token_urlsafe(32),
        str(uuid7()),
    )
    assert held.status_code == 404, held.text


async def test_staff_can_search_and_book_only_artists(
    client: httpx.AsyncClient,
    world: BookingWorld,
    manager_a: FakeUser,
    idp: FakeIdp,
    owner_conn: psycopg.Connection,
    app_pool: RuntimePool,
) -> None:
    chair = seed_lookalike(owner_conn, world, "chair")
    headers = idp.bearer(manager_a.subject, email=manager_a.email)
    salon = world.a.tenant_id
    starts = datetime.fromisoformat(f"{customer_day()}T11:00:00").replace(
        tzinfo=ZoneInfo(FAKE_TIMEZONE)
    )
    payload = {
        "location_id": str(world.a.location_id),
        "resource_id": str(chair),
        "variant_id": str(world.catalog_a.base_variant_id),
        "starts_at": starts.isoformat(),
        "customer_name": "FAKE Guest",
        "customer_email": "guest@example.com",
        "customer_phone": "+15550000000",
    }

    searched = await client.post(
        f"/v1/salons/{salon}/availability",
        json={**selection(world), "resource_id": str(chair)},
        headers=headers,
    )
    assert searched.status_code == 404, searched.text
    refused = await client.post(f"/v1/salons/{salon}/bookings", json=payload, headers=headers)
    assert refused.status_code == 404, refused.text
    assert await active_sources(app_pool, salon, chair) == []

    booked = await client.post(
        f"/v1/salons/{salon}/bookings",
        json={**payload, "resource_id": str(world.artist_a1)},
        headers=headers,
    )
    assert booked.status_code == 201, booked.text


async def test_the_booking_service_and_sql_do_not_check_the_resource_kind(
    world: BookingWorld, owner_conn: psycopg.Connection, app_pool: RuntimePool
) -> None:
    """Only the API paths filter by kind; slice I1 has to close this for the staff kind."""
    service, tenant = BookingService(app_pool), world.a.tenant_id
    for hour, kind in ((10, "chair"), (12, "room")):
        resource = seed_lookalike(owner_conn, world, kind)
        booked = await service.create_confirmed_booking(
            tenant, world.request(at(hour), resource=resource), actor=ACTOR, idempotency_key=None
        )
        assert (booked.status, booked.resource_id) == ("CONFIRMED", resource)
        assert await active_sources(app_pool, tenant, resource) == ["booking"]


async def test_a_reservation_accepts_every_resource_kind(
    staff: Reservations,
    world: BookingWorld,
    owner_conn: psycopg.Connection,
    app_pool: RuntimePool,
) -> None:
    resources = [world.artist_a1, seed_kind(owner_conn, world, "chair")]
    resources.append(seed_kind(owner_conn, world, "room"))
    body = staff.body(world.a.location_id, resources, at(14), at(15), purpose="FAKE setup")

    created = await staff.put(uuid7(), body)

    assert created.status_code == 200, created.text
    assert created.json()["resource_ids"] == sorted(str(resource) for resource in resources)
    for resource in resources:
        assert await active_sources(app_pool, world.a.tenant_id, resource) == ["reservation"]


async def test_the_staff_list_and_the_overview_count_every_resource_kind(
    client: httpx.AsyncClient,
    world: BookingWorld,
    manager_a: FakeUser,
    idp: FakeIdp,
    owner_conn: psycopg.Connection,
) -> None:
    chair, room = seed_kind(owner_conn, world, "chair"), seed_kind(owner_conn, world, "room")
    headers = idp.bearer(manager_a.subject, email=manager_a.email)
    salon = world.a.tenant_id

    listed = await client.get(f"/v1/salons/{salon}/staff", headers=headers)
    assert listed.status_code == 200, listed.text
    assert {row["id"]: row["kind"] for row in listed.json()} == {
        str(world.artist_a1): "artist",
        str(world.artist_a2): "artist",
        str(chair): "chair",
        str(room): "room",
    }

    overview = await client.get(f"/v1/salons/{salon}/overview", headers=headers)
    assert overview.status_code == 200, overview.text
    assert overview.json()["stats"]["active_staff_count"] == 4


async def test_staff_setup_accepts_a_resource_that_is_not_an_artist(
    client: httpx.AsyncClient,
    world: BookingWorld,
    manager_a: FakeUser,
    idp: FakeIdp,
    owner_conn: psycopg.Connection,
) -> None:
    room = seed_kind(owner_conn, world, "room")
    headers = idp.bearer(manager_a.subject, email=manager_a.email)
    base = f"/v1/salons/{world.a.tenant_id}"

    hours = [{"weekday": day, "opens_minute": 600, "closes_minute": 960} for day in range(1, 8)]
    scheduled = await client.put(
        f"{base}/staff/{room}/schedule", json={"hours": hours}, headers=headers
    )
    assert scheduled.status_code == 200, scheduled.text
    services = await client.get(f"{base}/services", headers=headers)
    service_ids = sorted({row["service_id"] for row in services.json()})
    linked = await client.put(
        f"{base}/staff/{room}/services", json={"service_ids": service_ids}, headers=headers
    )
    assert linked.status_code == 200, linked.text
    renamed = await client.patch(
        f"{base}/staff/{room}", json={"display_name": "FAKE room B"}, headers=headers
    )
    assert renamed.status_code == 200, renamed.text

    # Hours and services do not make it bookable: the kind still decides.
    searched = await client.post(
        f"{base}/availability",
        json={**selection(world), "resource_id": str(room)},
        headers=headers,
    )
    assert searched.status_code == 404, searched.text


async def test_the_staff_api_and_the_schema_know_three_resource_kinds(
    client: httpx.AsyncClient,
    world: BookingWorld,
    manager_a: FakeUser,
    idp: FakeIdp,
    owner_conn: psycopg.Connection,
) -> None:
    headers = idp.bearer(manager_a.subject, email=manager_a.email)
    url = f"/v1/salons/{world.a.tenant_id}/staff"

    def body(kind: str) -> dict[str, str]:
        return {
            "display_name": f"FAKE new {kind}",
            "location_id": str(world.a.location_id),
            "kind": kind,
        }

    for kind in ("artist", "chair", "room"):
        created = await client.post(url, json=body(kind), headers=headers)
        assert created.status_code == 201, created.text
        assert created.json()["kind"] == kind
    assert (await client.post(url, json=body("staff"), headers=headers)).status_code == 422

    with (
        pytest.raises(psycopg.errors.CheckViolation, match="staff resource requires its profile"),
        owner_tenant_transaction(owner_conn, world.a.tenant_id),
    ):
        owner_conn.execute(
            "insert into gba.resources (tenant_id, location_id, kind, display_name) "
            "values (%s, %s, 'staff', 'FAKE staff')",
            (world.a.tenant_id, world.a.location_id),
        )
