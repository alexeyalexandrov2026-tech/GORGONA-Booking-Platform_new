"""Staff reservations as the second consumer of shared occupancy (ADR-0022, CORE-04)."""

import asyncio
from collections import Counter
from collections.abc import Mapping
from datetime import datetime, timedelta
from uuid import UUID, uuid7

import httpx
import psycopg
import pytest

from gorgona_booking.booking.models import BookingResult, SlotConflictError
from gorgona_booking.booking.repository import is_slot_conflict
from gorgona_booking.booking.service import BookingService
from gorgona_booking.db.pool import (
    RuntimeConnection,
    RuntimePool,
    set_tenant_context,
    tenant_transaction,
)
from gorgona_booking.db.provisioning import add_membership, owner_tenant_transaction
from gorgona_booking.occupancy.reservation_contracts import ReservationInput
from gorgona_booking.occupancy.reservations import create_reservation
from tests.integration import test_management_api as shared
from tests.integration.booking_support import BookingWorld, at
from tests.integration.conftest import ProvisionedDatabase
from tests.integration.seed import FakeUser, seed_other_branch, seed_user
from tests.integration.test_customer_api import customer_client, selection
from tests.integration.test_documents import Documents
from tests.support.fake_idp import FakeIdp

pytestmark = pytest.mark.anyio
__all__ = ["customer_client"]
client = shared.client
idp = shared.idp
manager_a = shared.manager_a
manager_b = shared.manager_b
ACTOR = "test:reservations"


class Reservations(Documents):
    def body(
        self, location: UUID, resources: list[UUID], start: datetime, end: datetime, **extra: object
    ) -> dict[str, object]:
        return {
            "schema_version": 1,
            "location_id": str(location),
            "resource_ids": [str(r) for r in resources],
            "starts_at": start.isoformat(),
            "ends_at": end.isoformat(),
            **extra,
        }

    async def put(
        self, subject: UUID | str, body: Mapping[str, object], key: str | None = None
    ) -> httpx.Response:
        return await self.client.put(
            f"{self.base}/resource-reservations/{subject}",
            json=dict(body),
            headers=self.headers(key),
        )

    async def cancel(self, subject: UUID | str, key: str | None = None) -> httpx.Response:
        return await self.client.post(
            f"{self.base}/resource-reservations/{subject}/cancel",
            json={"schema_version": 1},
            headers=self.headers(key),
        )


@pytest.fixture
def staff(
    client: httpx.AsyncClient, world: BookingWorld, manager_a: FakeUser, idp: FakeIdp
) -> Reservations:
    return Reservations(client, world.a.tenant_id, manager_a, idp)


async def _active(pool: RuntimePool, tenant: UUID, resource: UUID) -> list[tuple[object, ...]]:
    async with tenant_transaction(pool, tenant) as conn:
        return await (
            await conn.execute(
                "select source_kind, source_id from gba.resource_allocations "
                "where resource_id = %s and state in ('held', 'confirmed') order by created_at",
                (resource,),
            )
        ).fetchall()


async def test_reservation_takes_every_resource_and_its_cancellation_frees_them(
    staff: Reservations, world: BookingWorld, app_pool: RuntimePool
) -> None:
    service = BookingService(app_pool)
    tenant, a1, a2 = world.a.tenant_id, world.artist_a1, world.artist_a2
    subject, key = uuid7(), str(uuid7())
    body = staff.body(world.a.location_id, [a2, a1], at(14), at(15), purpose="FAKE training")
    created = await staff.put(subject, body, key)
    assert created.status_code == 200, created.text
    view = created.json()
    assert view["status"] == "active"
    assert view["resource_ids"] == sorted([str(a1), str(a2)])
    assert (await staff.put(subject, body, key)).json() == view
    assert (await staff.put(subject, {**body, "purpose": "FAKE other"}, key)).status_code == 422
    for resource in (a1, a2):
        assert await _active(app_pool, tenant, resource) == [("reservation", subject)]
    # Booking cannot take a reserved resource; the slot conflict is the usual one.
    with pytest.raises(SlotConflictError):
        await service.create_hold(tenant, world.request(at(14)), actor=ACTOR, idempotency_key=None)
    listed = await staff.get(
        "/resource-reservations", starts=at(13).isoformat(), ends=at(16).isoformat()
    )
    assert [r["reservation_id"] for r in listed.json()["items"]] == [str(subject)]
    cancel_key = str(uuid7())
    cancelled = await staff.cancel(subject, cancel_key)
    assert cancelled.status_code == 200, cancelled.text
    assert cancelled.json()["status"] == "cancelled"
    assert (await staff.cancel(subject, cancel_key)).json() == cancelled.json()
    assert await _active(app_pool, tenant, a1) == []
    held: BookingResult = await service.create_hold(
        tenant, world.request(at(14)), actor=ACTOR, idempotency_key=None
    )
    assert held.starts_at == at(14)
    async with tenant_transaction(app_pool, tenant) as conn:
        audits = await (
            await conn.execute(
                "select action, details from gba.audit_events "
                "where action like 'resource_reservation.%%' order by occurred_at"
            )
        ).fetchall()
        receipts = await (
            await conn.execute(
                "select response_body from gba.idempotency_keys "
                "where operation like 'business.reservation.%%'"
            )
        ).fetchall()
    assert [row[0] for row in audits] == [
        "resource_reservation.created",
        "resource_reservation.cancelled",
    ]
    assert "FAKE" not in str(audits)
    assert all(set(row[0]) == {"reservation_id"} for row in receipts)


async def test_core_04_booking_and_reservation_race_for_one_resource(
    staff: Reservations, world: BookingWorld, app_pool: RuntimePool
) -> None:
    """CORE-04: the booking path and a reservation want one resource at once."""
    service = BookingService(app_pool)
    tenant, a1, a2 = world.a.tenant_id, world.artist_a1, world.artist_a2

    async def book() -> str:
        try:
            await service.create_hold(
                tenant, world.request(at(10)), actor=ACTOR, idempotency_key=None
            )
        except SlotConflictError:
            return "booking_conflict"
        return "booking"

    async def reserve() -> str:
        response = await staff.put(
            uuid7(), staff.body(world.a.location_id, [a1, a2], at(10), at(11))
        )
        if response.status_code == 409:
            assert response.json()["error"]["code"] == "SLOT_CONFLICT", response.text
            return "reservation_conflict"
        assert response.status_code == 200, response.text
        return "reservation"

    outcomes = Counter(await asyncio.gather(*(f() for _ in range(5) for f in (book, reserve))))
    assert outcomes["booking"] + outcomes["reservation"] == 1, outcomes
    assert outcomes["booking_conflict"] + outcomes["reservation_conflict"] == 9, outcomes
    assert len(await _active(app_pool, tenant, a1)) == 1
    # A failed multi-resource reservation leaves nothing behind: a2 is taken by a
    # booking at 12:00, so the reservation of a1 and a2 at 12:00 takes neither.
    await service.create_hold(
        tenant, world.request(at(12), resource=a2), actor=ACTOR, idempotency_key=None
    )
    refused = await staff.put(uuid7(), staff.body(world.a.location_id, [a1, a2], at(12), at(13)))
    assert (refused.status_code, refused.json()["error"]["code"]) == (409, "SLOT_CONFLICT")
    async with tenant_transaction(app_pool, tenant) as conn:
        left = await (
            await conn.execute(
                "select count(*) from gba.resource_allocations where resource_id = %s "
                "and source_kind = 'reservation' and lower(during) = %s",
                (a1, at(12)),
            )
        ).fetchone()
        reservations = await (
            await conn.execute(
                "select count(*) from gba.resource_reservations where starts_at = %s", (at(12),)
            )
        ).fetchone()
    assert (left, reservations) == ((0,), (0,))


async def test_reservation_sees_booking_allocations_that_were_not_copied_yet(
    staff: Reservations, world: BookingWorld, app_pool: RuntimePool, owner_conn: psycopg.Connection
) -> None:
    service = BookingService(app_pool)
    trigger = "booking_allocations_mirror_occupancy"
    owner_conn.execute(f"alter table gba.booking_allocations disable trigger {trigger}")
    try:
        await service.create_hold(
            world.a.tenant_id, world.request(at(16)), actor=ACTOR, idempotency_key=None
        )
    finally:
        owner_conn.execute(f"alter table gba.booking_allocations enable trigger {trigger}")
    refused = await staff.put(
        uuid7(), staff.body(world.a.location_id, [world.artist_a1], at(16), at(17))
    )
    assert (refused.status_code, refused.json()["error"]["code"]) == (409, "SLOT_CONFLICT")


async def test_reservations_refuse_invalid_input_and_stop_with_the_booking_module(
    staff: Reservations, world: BookingWorld
) -> None:
    location, a1 = world.a.location_id, world.artist_a1
    for invalid in (
        staff.body(location, [a1], at(15), at(14)),
        staff.body(location, [a1, a1], at(14), at(15)),
        staff.body(location, [], at(14), at(15)),
        staff.body(location, [a1], at(14), at(15), purpose="FAKE\u0085x"),
        staff.body(location, [a1], at(14), at(15), purpose="FAKE\u2028x"),
        {**staff.body(location, [a1], at(14), at(15)), "starts_at": "2026-10-06T14:00:00"},
    ):
        assert (await staff.put(uuid7(), invalid)).status_code == 422, invalid
    unknown = await staff.put(uuid7(), staff.body(location, [world.artist_b1], at(14), at(15)))
    assert (unknown.status_code, unknown.json()["error"]["code"]) == (422, "INVALID_REFERENCE")
    window = await staff.get(
        "/resource-reservations", starts=at(10).isoformat(), ends=at(9).isoformat()
    )
    assert window.status_code == 422
    subject = uuid7()
    assert (await staff.put(subject, staff.body(location, [a1], at(14), at(15)))).status_code == 200
    taken = await staff.put(subject, staff.body(location, [a1], at(16), at(17)))
    assert taken.status_code == 409
    # Turning booking off stops new reservations; reads and cancellations continue.
    await staff.enable(["counterparties"])
    stopped = await staff.put(uuid7(), staff.body(location, [a1], at(18), at(19)))
    assert (stopped.status_code, stopped.json()["error"]["code"]) == (409, "MODULE_DISABLED")
    assert (await staff.get(f"/resource-reservations/{subject}")).status_code == 200
    assert (await staff.cancel(subject)).status_code == 200


async def test_reservation_access_is_staff_management_within_the_branch(
    staff: Reservations,
    world: BookingWorld,
    owner_conn: psycopg.Connection,
    client: httpx.AsyncClient,
    idp: FakeIdp,
    manager_b: FakeUser,
) -> None:
    other_location, other_resource = seed_other_branch(owner_conn, world.a)
    subject = uuid7()
    assert (
        await staff.put(subject, staff.body(world.a.location_id, [world.artist_a1], at(9), at(10)))
    ).status_code == 200
    branch = seed_user(owner_conn, f"FAKE-branch-manager-{uuid7()}")
    add_membership(
        owner_conn,
        tenant_id=world.a.tenant_id,
        user_id=branch.user_id,
        role="manager",
        location_id=other_location,
    )
    at_branch = Reservations(client, world.a.tenant_id, branch, idp)
    # A branch manager works in the own branch only and never sees the other one.
    assert (
        await at_branch.put(
            uuid7(), at_branch.body(other_location, [other_resource], at(9), at(10))
        )
    ).status_code == 200
    assert (
        await at_branch.put(
            uuid7(), at_branch.body(world.a.location_id, [world.artist_a1], at(11), at(12))
        )
    ).status_code == 403
    assert (await at_branch.get(f"/resource-reservations/{subject}")).status_code == 404
    assert (await at_branch.cancel(subject)).status_code == 404
    for role in ("artist", "front_desk"):
        member = seed_user(owner_conn, f"FAKE-reservation-{role}-{uuid7()}")
        add_membership(owner_conn, tenant_id=world.a.tenant_id, user_id=member.user_id, role=role)
        outsider = Reservations(client, world.a.tenant_id, member, idp)
        assert (
            await outsider.put(
                uuid7(), outsider.body(world.a.location_id, [world.artist_a1], at(13), at(14))
            )
        ).status_code == 403
        assert (await outsider.cancel(subject)).status_code == 403
    foreign = Reservations(client, world.a.tenant_id, manager_b, idp)
    assert (await foreign.get(f"/resource-reservations/{subject}")).status_code == 403


async def test_direct_sql_cannot_forge_or_bend_reservations(
    staff: Reservations,
    world: BookingWorld,
    app_pool: RuntimePool,
    owner_conn: psycopg.Connection,
    client: httpx.AsyncClient,
) -> None:
    tenant = world.a.tenant_id
    subject = uuid7()
    created = await staff.put(
        subject, staff.body(world.a.location_id, [world.artist_a1], at(9), at(10))
    )
    assert created.status_code == 200
    other_location, other_resource = seed_other_branch(owner_conn, world.a)
    for statement, params in (
        # A second allocation outside the reservation's interval or branch.
        (
            "insert into gba.resource_allocations (tenant_id, resource_id, source_kind, "
            "source_id, during, state) values (%s, %s, 'reservation', %s, "
            "tstzrange(%s, %s, '[)'), 'confirmed')",
            (tenant, world.artist_a2, subject, at(9), at(11)),
        ),
        (
            "insert into gba.resource_allocations (tenant_id, resource_id, source_kind, "
            "source_id, during, state) values (%s, %s, 'reservation', %s, "
            "tstzrange(%s, %s, '[)'), 'confirmed')",
            (tenant, other_resource, subject, at(9), at(10)),
        ),
        # Releasing without the cancellation, rewriting or deleting the reservation.
        (
            "update gba.resource_allocations set state = 'released' where source_id = %s",
            (subject,),
        ),
        (
            "update gba.resource_reservations set purpose = 'FAKE changed' where id = %s",
            (subject,),
        ),
    ):
        with pytest.raises(psycopg.Error):
            async with tenant_transaction(app_pool, tenant) as conn:
                await conn.execute(statement, params)
    with owner_tenant_transaction(owner_conn, tenant):
        for statement in (
            "delete from gba.resource_reservations",
            "update gba.resource_reservations set ends_at = ends_at + interval '1 hour'",
        ):
            with pytest.raises(psycopg.errors.CheckViolation), owner_conn.transaction():
                owner_conn.execute(statement)
    # A reservation without resources cannot be committed.
    with pytest.raises(psycopg.errors.CheckViolation, match="requires its resources"):
        async with tenant_transaction(app_pool, tenant) as conn:
            await conn.execute(
                "insert into gba.resource_reservations (tenant_id, id, location_id, starts_at, "
                "ends_at, resource_count, created_by) values (%s, %s, %s, %s, %s, 1, %s)",
                (tenant, uuid7(), other_location, at(9), at(10), staff.user.user_id),
            )
    trigger = "resource_reservations_release"
    try:
        owner_conn.execute(f"alter table gba.resource_reservations disable trigger {trigger}")
        assert (await client.get("/health/ready")).status_code == 503
    finally:
        owner_conn.execute(f"alter table gba.resource_reservations enable trigger {trigger}")
    assert (await client.get("/health/ready")).status_code == 200


async def test_customers_never_see_a_reserved_resource_as_available(
    customer_client: httpx.AsyncClient,
    world: BookingWorld,
    app_pool: RuntimePool,
    owner_conn: psycopg.Connection,
) -> None:
    query = {**selection(world), "resource_id": str(world.artist_a1)}

    async def starts() -> list[str]:
        response = await customer_client.post("/v1/customer/availability", json=query)
        assert response.status_code == 200, response.text
        return [slot["start_at"] for slot in response.json()["slots"]]

    offered = await starts()
    assert offered
    first = datetime.fromisoformat(offered[0])
    manager = seed_user(owner_conn, f"FAKE-reservation-availability-{uuid7()}")
    add_membership(owner_conn, tenant_id=world.a.tenant_id, user_id=manager.user_id, role="manager")
    async with tenant_transaction(app_pool, world.a.tenant_id) as conn:
        await create_reservation(
            conn,
            business_id=world.a.tenant_id,
            reservation_id=uuid7(),
            user_id=manager.user_id,
            actor=ACTOR,
            key=str(uuid7()),
            body=ReservationInput(
                location_id=world.a.location_id,
                resource_ids=(world.artist_a1,),
                starts_at=first,
                ends_at=first + timedelta(hours=1),
            ),
            request_id=None,
        )
    assert offered[0] not in await starts()


async def test_core_04_raw_sql_without_locks_admits_one_booking_or_reservation(
    test_database: ProvisionedDatabase,
    world: BookingWorld,
    app_pool: RuntimePool,
    manager_a: FakeUser,
) -> None:
    """No application locks: the shared exclusion constraint alone decides."""
    tenant, resource = world.a.tenant_id, world.artist_a1

    async def booking(conn: RuntimeConnection, barrier: asyncio.Barrier) -> str:
        start, end = slot
        async with conn.transaction():
            await set_tenant_context(conn, tenant)
            row = await (
                await conn.execute(
                    "insert into gba.bookings (tenant_id, location_id, variant_id, status, "
                    "starts_at, ends_at, total_cents, currency, quote, created_by) "
                    "values (%s, %s, %s, 'CONFIRMED', %s, %s, 5000, 'USD', '{}'::jsonb, %s) "
                    "returning id",
                    (
                        tenant,
                        world.a.location_id,
                        world.catalog_a.base_variant_id,
                        start,
                        end,
                        ACTOR,
                    ),
                )
            ).fetchone()
            assert row is not None
            await barrier.wait()
            await conn.execute(
                "insert into gba.booking_allocations (tenant_id, booking_id, booking_status, "
                "resource_id, during) values (%s, %s, 'CONFIRMED', %s, tstzrange(%s, %s, '[)'))",
                (tenant, row[0], resource, start, end),
            )
        return "booking"

    async def reservation(conn: RuntimeConnection, barrier: asyncio.Barrier) -> str:
        start, end = slot
        subject = uuid7()
        async with conn.transaction():
            await set_tenant_context(conn, tenant)
            await conn.execute(
                "insert into gba.resource_reservations (tenant_id, id, location_id, starts_at, "
                "ends_at, resource_count, created_by) values (%s, %s, %s, %s, %s, 1, %s)",
                (tenant, subject, world.a.location_id, start, end, manager_a.user_id),
            )
            await barrier.wait()
            await conn.execute(
                "insert into gba.resource_allocations (tenant_id, resource_id, source_kind, "
                "source_id, during, state) values (%s, %s, 'reservation', %s, "
                "tstzrange(%s, %s, '[)'), 'confirmed')",
                (tenant, resource, subject, start, end),
            )
        return "reservation"

    outcomes: Counter[str] = Counter()
    for round_number, hour in enumerate((8, 10, 12, 14, 16), start=1):
        slot = (at(hour), at(hour + 1))
        barrier = asyncio.Barrier(2)
        connections = [
            await psycopg.AsyncConnection.connect(test_database.app_dsn, autocommit=True)
            for _ in range(2)
        ]
        results: list[str] = []
        try:
            for outcome in await asyncio.gather(
                booking(connections[0], barrier),
                reservation(connections[1], barrier),
                return_exceptions=True,
            ):
                if isinstance(outcome, psycopg.errors.ExclusionViolation):
                    results.append("conflict" if is_slot_conflict(outcome) else "other")
                elif isinstance(outcome, psycopg.errors.DeadlockDetected):
                    results.append("deadlock")
                elif isinstance(outcome, str):
                    results.append(outcome)
                else:
                    raise AssertionError(outcome)
        finally:
            for conn in connections:
                await conn.close()
        assert results.count("conflict") + results.count("deadlock") == 1, results
        assert len(await _active(app_pool, tenant, resource)) == round_number
        outcomes.update(results)
    assert set(outcomes) <= {"booking", "reservation", "conflict", "deadlock"}, outcomes


async def test_reservations_never_overlap_each_other(
    staff: Reservations, world: BookingWorld
) -> None:
    first = await staff.put(
        uuid7(), staff.body(world.a.location_id, [world.artist_a1], at(9), at(11))
    )
    assert first.status_code == 200
    second = await staff.put(
        uuid7(),
        staff.body(world.a.location_id, [world.artist_a2, world.artist_a1], at(10), at(12)),
    )
    assert (second.status_code, second.json()["error"]["code"]) == (409, "SLOT_CONFLICT")
    adjacent = await staff.put(
        uuid7(), staff.body(world.a.location_id, [world.artist_a1], at(11), at(12))
    )
    assert adjacent.status_code == 200


async def test_concurrent_cancels_and_a_moved_resource_never_leave_a_resource_blocked(
    staff: Reservations,
    world: BookingWorld,
    app_pool: RuntimePool,
    owner_conn: psycopg.Connection,
    client: httpx.AsyncClient,
    idp: FakeIdp,
) -> None:
    subject = uuid7()
    body = staff.body(world.a.location_id, [world.artist_a1, world.artist_a2], at(9), at(10))
    assert (await staff.put(subject, body)).status_code == 200
    # Two people cancel at once with different keys: both see a cancelled reservation.
    both = await asyncio.gather(staff.cancel(subject), staff.cancel(subject))
    assert [r.status_code for r in both] == [200, 200]
    async with tenant_transaction(app_pool, world.a.tenant_id) as conn:
        audits = await (
            await conn.execute(
                "select count(*) from gba.audit_events "
                "where action = 'resource_reservation.cancelled' and target_id = %s",
                (str(subject),),
            )
        ).fetchone()
    assert audits == (1,)
    # A resource moved to another branch: the branch session cannot release it, so
    # the cancellation fails closed; a company-wide session releases everything.
    moved = uuid7()
    assert (
        await staff.put(moved, staff.body(world.a.location_id, [world.artist_a1], at(13), at(14)))
    ).status_code == 200
    branch = seed_user(owner_conn, f"FAKE-branch-cancel-{uuid7()}")
    add_membership(
        owner_conn,
        tenant_id=world.a.tenant_id,
        user_id=branch.user_id,
        role="manager",
        location_id=world.a.location_id,
    )
    other_location, _ = seed_other_branch(owner_conn, world.a)
    with owner_tenant_transaction(owner_conn, world.a.tenant_id):
        owner_conn.execute(
            "update gba.resources set location_id = %s where id = %s",
            (other_location, world.artist_a1),
        )
    at_branch = Reservations(client, world.a.tenant_id, branch, idp)
    refused = await at_branch.cancel(moved)
    assert (refused.status_code, refused.json()["error"]["code"]) == (409, "CONFLICT")
    assert len(await _active(app_pool, world.a.tenant_id, world.artist_a1)) == 1
    assert (await staff.cancel(moved)).status_code == 200
    assert await _active(app_pool, world.a.tenant_id, world.artist_a1) == []


async def test_resources_cannot_be_added_later_and_the_guard_checks_the_commit_trigger(
    staff: Reservations,
    world: BookingWorld,
    app_pool: RuntimePool,
    owner_conn: psycopg.Connection,
    client: httpx.AsyncClient,
) -> None:
    subject = uuid7()
    assert (
        await staff.put(subject, staff.body(world.a.location_id, [world.artist_a1], at(9), at(10)))
    ).status_code == 200
    with pytest.raises(psycopg.errors.CheckViolation, match="active reservation"):
        async with tenant_transaction(app_pool, world.a.tenant_id) as conn:
            await conn.execute(
                "insert into gba.resource_allocations (tenant_id, resource_id, source_kind, "
                "source_id, during, state) values (%s, %s, 'reservation', %s, "
                "tstzrange(%s, %s, '[)'), 'confirmed')",
                (world.a.tenant_id, world.artist_a2, subject, at(9), at(10)),
            )
    trigger = "resource_reservations_allocated"
    try:
        owner_conn.execute(f"alter table gba.resource_reservations disable trigger {trigger}")
        assert (await client.get("/health/ready")).status_code == 503
    finally:
        owner_conn.execute(f"alter table gba.resource_reservations enable trigger {trigger}")
    assert (await client.get("/health/ready")).status_code == 200
