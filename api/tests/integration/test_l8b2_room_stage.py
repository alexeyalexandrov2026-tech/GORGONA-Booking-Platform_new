"""L8b2: a room is a stage resource in the shared occupancy (package L, BEAUTY-01; FAKE data only).

Design docs/plan/PACKAGE_L8_DESIGN_2026-10-23.md decision 72: a stage that needs a room holds it;
a staff reservation of that room for an overlapping time is refused, while the specialist stays
free during processing.
"""

from uuid import uuid7

import psycopg
import pytest

from gorgona_booking.booking.models import ReservationRequest
from gorgona_booking.booking.service import BookingService
from gorgona_booking.db.pool import RuntimePool
from gorgona_booking.db.provisioning import owner_tenant_transaction
from tests.integration import test_resource_reservations as shared
from tests.integration.booking_support import BookingWorld, at
from tests.integration.test_l2_stage_occupancy import intervals, seed_kind
from tests.integration.test_resource_reservations import Reservations

pytestmark = pytest.mark.anyio
client = shared.client
idp = shared.idp
manager_a = shared.manager_a
manager_b = shared.manager_b
staff = shared.staff
__all__ = ["client", "idp", "manager_a", "manager_b", "staff"]

# A 110-minute treatment: the specialist works 30 minutes in the room, the room alone is held for
# 60 minutes of processing, the specialist finishes in it for 20.
ROOM_STAGES = (
    ("active", 30, ["specialist", "room"]),
    ("processing", 60, ["room"]),
    ("finish", 20, ["specialist", "room"]),
)


async def test_a_room_stage_holds_the_room_against_staff_reservations(
    staff: Reservations,
    world: BookingWorld,
    owner_conn: psycopg.Connection,
    app_pool: RuntimePool,
) -> None:
    variant = world.catalog_a.gel_variant_id
    with owner_tenant_transaction(owner_conn, world.a.tenant_id):
        for position, (kind, minutes, resources) in enumerate(ROOM_STAGES, start=1):
            owner_conn.execute(
                "insert into gba.variant_stages (tenant_id,variant_id,position,kind,minutes,"
                "resources) values (%s,%s,%s,%s,%s,%s)",
                (world.a.tenant_id, variant, position, kind, minutes, resources),
            )
        owner_conn.execute(
            "update gba.service_variants set booking_duration_minutes=110 where id=%s", (variant,)
        )
    room = seed_kind(owner_conn, world.a, "room", "FAKE room 1")
    booked = await BookingService(app_pool).create_confirmed_booking(
        world.a.tenant_id,
        ReservationRequest(resource_id=world.artist_a1, variant_id=variant, starts_at=at(10)),
        actor="test:l8b2",
        idempotency_key=None,
    )
    rows = await intervals(app_pool, world.a.tenant_id, booked.booking_id)
    assert sorted((r, s, e) for r, s, e, _ in rows) == sorted(
        [
            (world.artist_a1, at(10), at(10, 30)),
            (world.artist_a1, at(11, 30), at(11, 50)),
            (room, at(10), at(11, 50)),
        ]
    )
    location = world.a.location_id
    # The room is held through processing: a staff reservation of it is refused.
    refused = await staff.put(uuid7(), staff.body(location, [room], at(10, 45), at(11, 15)))
    assert (refused.status_code, refused.json()["error"]["code"]) == (409, "SLOT_CONFLICT")
    # The specialist is free while the room works alone.
    free = await staff.put(uuid7(), staff.body(location, [world.artist_a1], at(10, 45), at(11, 15)))
    assert free.status_code == 200, free.text
    # After the visit the room is free again.
    after = await staff.put(uuid7(), staff.body(location, [room], at(11, 50), at(12, 30)))
    assert after.status_code == 200, after.text
