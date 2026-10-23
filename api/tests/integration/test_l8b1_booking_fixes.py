"""L8b1: review fixes R8 and R10 on the management API (package L, BEAUTY-01; FAKE data only).

Design docs/plan/PACKAGE_L8_DESIGN_2026-10-23.md decisions 61 and 63.
"""

from uuid import UUID

import httpx
import pytest

from tests.integration import test_l2c_visits as shared
from tests.integration.booking_support import BookingWorld
from tests.integration.seed import FakeUser
from tests.integration.test_l1_service_stages import COLOUR, put_stages
from tests.integration.test_l2c_visits import extra, local
from tests.support.fake_idp import FakeIdp

pytestmark = pytest.mark.anyio
client = shared.client
idp = shared.idp
manager_a = shared.manager_a
staff_visit = shared.staff_visit
__all__ = ["client", "idp", "manager_a", "staff_visit"]

# The same 90 minutes as COLOUR, split differently.
RESPLIT = [
    {"kind": "active", "minutes": 20, "resources": ["specialist", "chair"]},
    {"kind": "processing", "minutes": 50, "resources": ["chair", "equipment"]},
    {"kind": "finish", "minutes": 20, "resources": ["specialist", "chair"]},
]


# L8-09 (R8) -------------------------------------------------------------------------


async def test_a_stage_save_always_bumps_the_revision(
    client: httpx.AsyncClient, world: BookingWorld, manager_a: FakeUser, idp: FakeIdp
) -> None:
    headers = idp.bearer(manager_a.subject, email=manager_a.email)
    first = await put_stages(client, world, headers, COLOUR)
    assert first.status_code == 200, first.text
    read = first.json()["revision"]
    same_total = await put_stages(client, world, headers, RESPLIT, revision=read)
    assert same_total.status_code == 200, same_total.text
    assert same_total.json()["revision"] > read
    # A second manager still holding the old revision is refused, not silently applied.
    stale = await put_stages(client, world, headers, COLOUR, revision=read)
    assert stale.status_code == 409, stale.text
    assert stale.json()["error"]["code"] == "SERVICE_REVISION_CONFLICT"
    kept = same_total.json()["revision"]
    cleared = await put_stages(client, world, headers, [], revision=kept)
    assert cleared.status_code == 200, cleared.text
    assert cleared.json()["revision"] > kept


# L8-11 (R10) ------------------------------------------------------------------------


async def test_a_visit_moves_only_to_a_specialist_of_every_service(
    client: httpx.AsyncClient,
    world: BookingWorld,
    manager_a: FakeUser,
    idp: FakeIdp,
    staff_visit: dict[str, UUID],
) -> None:
    headers = idp.bearer(manager_a.subject, email=manager_a.email)
    path = f"/v1/salons/{world.a.tenant_id}/bookings"
    created = await client.post(
        path,
        json={
            "location_id": str(world.a.location_id),
            "resource_id": str(world.artist_a1),
            "variant_id": str(world.catalog_a.gel_variant_id),
            "starts_at": local(11).isoformat(),
            "customer_name": "FAKE Visit Client",
            "customer_email": "visit@example.com",
            "customer_phone": "+15551239999",
            "extra_lines": extra(staff_visit),
        },
        headers=headers,
    )
    assert created.status_code == 201, created.text
    booking = created.json()["booking_id"]
    # A2 serves the colour but not the style.
    other = await client.post(
        f"{path}/{booking}/reschedule",
        json={"new_starts_at": local(12).isoformat(), "new_resource_id": str(world.artist_a2)},
        headers=headers,
    )
    assert other.status_code == 404, other.text
    assert other.json()["error"]["code"] == "NOT_FOUND"
    # The same time with the specialist of both services is free: only the specialist was wrong.
    kept = await client.post(
        f"{path}/{booking}/reschedule",
        json={"new_starts_at": local(12).isoformat()},
        headers=headers,
    )
    assert kept.status_code == 200, kept.text
