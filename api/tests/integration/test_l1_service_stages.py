"""L1: service stages and equipment (package L, BEAUTY-01; FAKE data only).

Owner's delegation 2026-10-22 and the package L decisions 1-2: a variant may list ordered stages
(active, processing, finish), each with minutes and the resource kinds it occupies; its booking
duration is then the sum of the stages, which the database checks. A variant without stages behaves
exactly as before. Equipment is a resource kind. Booking a staged variant still takes one resource
for the whole time until L2.
"""

from typing import Any
from uuid import UUID

import httpx
import psycopg
import pytest

from gorgona_booking.booking.service import BookingService
from gorgona_booking.db.pool import RuntimePool, tenant_transaction
from tests.integration import test_management_api as shared
from tests.integration.booking_support import BookingWorld, at
from tests.integration.seed import FakeUser
from tests.support.fake_idp import FakeIdp

pytestmark = pytest.mark.anyio
client = shared.client
idp = shared.idp
manager_a = shared.manager_a
manager_b = shared.manager_b
COLOUR = [
    {"kind": "active", "minutes": 30, "resources": ["specialist", "chair"]},
    {"kind": "processing", "minutes": 40, "resources": ["chair", "equipment"]},
    {"kind": "finish", "minutes": 20, "resources": ["specialist", "chair"]},
]


async def put_stages(
    client: httpx.AsyncClient,
    world: BookingWorld,
    headers: dict[str, str],
    stages: object,
    revision: int | None = None,
    variant: UUID | None = None,
) -> httpx.Response:
    variant_id = variant or world.catalog_a.base_variant_id
    if revision is None:
        listed = await client.get(f"/v1/salons/{world.a.tenant_id}/services", headers=headers)
        (current,) = [s for s in listed.json() if s["id"] == str(variant_id)]
        revision = current["revision"]
    return await client.put(
        f"/v1/salons/{world.a.tenant_id}/services/{variant_id}/stages",
        json={"expected_revision": revision, "stages": stages},
        headers=headers,
    )


# L-01 -----------------------------------------------------------------------


async def test_stages_set_the_duration_and_bump_the_revision(
    client: httpx.AsyncClient, world: BookingWorld, manager_a: FakeUser, idp: FakeIdp
) -> None:
    headers = idp.bearer(manager_a.subject, email=manager_a.email)
    response = await put_stages(client, world, headers, COLOUR, revision=None)
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["booking_duration_minutes"] == 90
    assert [(s["position"], s["kind"], s["minutes"], s["resources"]) for s in body["stages"]] == [
        (1, "active", 30, ["specialist", "chair"]),
        (2, "processing", 40, ["chair", "equipment"]),
        (3, "finish", 20, ["specialist", "chair"]),
    ]
    listed = await client.get(f"/v1/salons/{world.a.tenant_id}/services", headers=headers)
    (shown,) = [s for s in listed.json() if s["id"] == str(world.catalog_a.base_variant_id)]
    assert shown["stages"] == body["stages"]
    assert shown["revision"] == body["revision"]
    # The same request with the old revision is a conflict, not a second change.
    again = await put_stages(client, world, headers, COLOUR, revision=body["revision"] - 1)
    assert again.status_code == 409, again.text
    assert again.json()["error"]["code"] == "SERVICE_REVISION_CONFLICT"


async def test_clearing_stages_keeps_the_duration_and_the_old_meaning(
    client: httpx.AsyncClient, world: BookingWorld, manager_a: FakeUser, idp: FakeIdp
) -> None:
    headers = idp.bearer(manager_a.subject, email=manager_a.email)
    assert (await put_stages(client, world, headers, COLOUR)).status_code == 200
    cleared = await put_stages(client, world, headers, [])
    assert cleared.status_code == 200, cleared.text
    assert (cleared.json()["stages"], cleared.json()["booking_duration_minutes"]) == ([], 90)
    # Without stages the duration may be changed freely again.
    patched = await client.patch(
        f"/v1/salons/{world.a.tenant_id}/services/{world.catalog_a.base_variant_id}",
        json={"booking_duration_minutes": 45},
        headers=headers,
    )
    assert patched.status_code == 200, patched.text
    assert patched.json()["booking_duration_minutes"] == 45


async def test_unchanged_variants_list_no_stages(
    client: httpx.AsyncClient, world: BookingWorld, manager_a: FakeUser, idp: FakeIdp
) -> None:
    headers = idp.bearer(manager_a.subject, email=manager_a.email)
    listed = await client.get(f"/v1/salons/{world.a.tenant_id}/services", headers=headers)
    assert listed.status_code == 200, listed.text
    assert all(s["stages"] == [] for s in listed.json())


# Rules ------------------------------------------------------------------------


@pytest.mark.parametrize(
    "stages",
    [
        [{"kind": "active", "minutes": 30, "resources": ["chair"]}],  # active without specialist
        [{"kind": "finish", "minutes": 30, "resources": []}],  # finish without specialist
        [
            {"kind": "active", "minutes": 10, "resources": ["specialist"]},
            {"kind": "processing", "minutes": 10, "resources": ["specialist"]},
        ],  # processing keeps the specialist busy
        [{"kind": "processing", "minutes": 30, "resources": ["chair"]}],  # no active stage
        [{"kind": "active", "minutes": 0, "resources": ["specialist"]}],
        [{"kind": "active", "minutes": 721, "resources": ["specialist"]}],
        [{"kind": "active", "minutes": 30, "resources": ["specialist", "specialist"]}],
        [{"kind": "active", "minutes": 30, "resources": ["specialist", "desk"]}],
        [{"kind": "rest", "minutes": 30, "resources": ["specialist"]}],
        [{"kind": "active", "minutes": 400, "resources": ["specialist"]}] * 2,  # over 720
        [{"kind": "active", "minutes": 1, "resources": ["specialist"]}] * 11,  # over 10 stages
        [{"kind": "active", "minutes": 30, "resources": ["specialist"], "price_cents": 1}],
    ],
)
async def test_invalid_stages_are_refused(
    client: httpx.AsyncClient,
    world: BookingWorld,
    manager_a: FakeUser,
    idp: FakeIdp,
    stages: list[dict[str, Any]],
) -> None:
    headers = idp.bearer(manager_a.subject, email=manager_a.email)
    response = await put_stages(client, world, headers, stages)
    assert response.status_code == 422, response.text


async def test_patching_the_duration_of_a_staged_variant_is_refused(
    client: httpx.AsyncClient, world: BookingWorld, manager_a: FakeUser, idp: FakeIdp
) -> None:
    headers = idp.bearer(manager_a.subject, email=manager_a.email)
    assert (await put_stages(client, world, headers, COLOUR)).status_code == 200
    patched = await client.patch(
        f"/v1/salons/{world.a.tenant_id}/services/{world.catalog_a.base_variant_id}",
        json={"booking_duration_minutes": 60},
        headers=headers,
    )
    assert patched.status_code == 422, patched.text
    assert patched.json()["error"]["details"]["constraint"] == "service_variants_duration_of_stages"


async def test_sql_refuses_stages_that_disagree_with_the_duration(
    world: BookingWorld, app_pool: RuntimePool
) -> None:
    with pytest.raises(psycopg.errors.CheckViolation):
        async with tenant_transaction(app_pool, world.a.tenant_id) as conn:
            await conn.execute(
                "insert into gba.variant_stages (tenant_id,variant_id,position,kind,minutes,"
                "resources) values (%s,%s,1,'active',15,array['specialist'])",
                (world.a.tenant_id, world.catalog_a.base_variant_id),
            )


async def test_another_company_cannot_read_or_change_stages(
    client: httpx.AsyncClient,
    world: BookingWorld,
    manager_a: FakeUser,
    manager_b: FakeUser,
    idp: FakeIdp,
    app_pool: RuntimePool,
) -> None:
    headers = idp.bearer(manager_a.subject, email=manager_a.email)
    assert (await put_stages(client, world, headers, COLOUR)).status_code == 200
    foreign = idp.bearer(manager_b.subject, email=manager_b.email)
    refused = await client.put(
        f"/v1/salons/{world.a.tenant_id}/services/{world.catalog_a.base_variant_id}/stages",
        json={"expected_revision": 1, "stages": COLOUR},
        headers=foreign,
    )
    assert refused.status_code in (403, 404), refused.text
    async with tenant_transaction(app_pool, world.b.tenant_id) as conn:
        rows = await (
            await conn.execute(
                "select count(*) from gba.variant_stages where variant_id=%s",
                (world.catalog_a.base_variant_id,),
            )
        ).fetchone()
    assert rows == (0,)


# L-04 -----------------------------------------------------------------------


async def test_equipment_is_a_resource_kind(
    client: httpx.AsyncClient, world: BookingWorld, manager_a: FakeUser, idp: FakeIdp
) -> None:
    headers = idp.bearer(manager_a.subject, email=manager_a.email)
    created = await client.post(
        f"/v1/salons/{world.a.tenant_id}/staff",
        json={
            "display_name": "FAKE colour processor",
            "kind": "equipment",
            "location_id": str(world.a.location_id),
        },
        headers=headers,
    )
    assert created.status_code == 201, created.text
    assert created.json()["kind"] == "equipment"


# L1 compatibility ---------------------------------------------------------------


async def test_a_staged_variant_still_books_one_resource_for_the_whole_time(
    client: httpx.AsyncClient,
    world: BookingWorld,
    manager_a: FakeUser,
    idp: FakeIdp,
    app_pool: RuntimePool,
) -> None:
    headers = idp.bearer(manager_a.subject, email=manager_a.email)
    assert (await put_stages(client, world, headers, COLOUR)).status_code == 200
    service = BookingService(app_pool)
    result = await service.create_confirmed_booking(
        world.a.tenant_id,
        world.request(at(10), add_ons=(world.catalog_a.massage_add_on_id,)),
        actor="test:l1",
        idempotency_key=None,
    )
    async with tenant_transaction(app_pool, world.a.tenant_id) as conn:
        row = await (
            await conn.execute(
                "select ends_at-starts_at,quote from gba.bookings where id=%s",
                (result.booking_id,),
            )
        ).fetchone()
    assert row is not None
    minutes = int(row[0].total_seconds() // 60)
    quote = row[1]
    assert quote["version"] == 2
    stages = quote["stages"]
    assert [s["kind"] for s in stages] == ["active", "processing", "finish"]
    # The add-on's minutes join the last active stage; the booking lasts the whole visit.
    assert minutes == sum(s["minutes"] for s in stages)
    assert stages[0]["minutes"] == 30 + minutes - 90
