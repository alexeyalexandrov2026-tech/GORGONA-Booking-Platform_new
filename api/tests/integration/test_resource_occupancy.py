"""Shared resource occupancy (ADR-0022, CORE-04) against real PostgreSQL 18."""

import secrets
from datetime import timedelta
from uuid import UUID, uuid7

import httpx
import psycopg
import pytest
from psycopg import sql
from psycopg.conninfo import conninfo_to_dict, make_conninfo

from gorgona_booking.booking.models import SlotConflictError
from gorgona_booking.booking.service import BookingService
from gorgona_booking.db.bootstrap import BootstrapSpec, bootstrap
from gorgona_booking.db.migrate import apply_migrations, load_migrations
from gorgona_booking.db.pool import RuntimePool, tenant_transaction
from gorgona_booking.db.provisioning import owner_tenant_transaction
from gorgona_booking.occupancy.backfill import (
    BackfillResult,
    UnknownCompanyError,
    backfill_for_owner,
)
from tests.integration import test_management_api as shared
from tests.integration.booking_support import BookingWorld, at
from tests.integration.conftest import TEST_APP_ROLE, TEST_OWNER_ROLE, ProvisionedDatabase
from tests.integration.seed import (
    force_hold_expired,
    seed_fake_catalog,
    seed_other_branch,
    seed_resource,
    seed_salon,
)

pytestmark = pytest.mark.anyio
client = shared.client
idp = shared.idp
ACTOR = "test:occupancy"


async def occupancy(pool: RuntimePool, tenant: UUID) -> list[tuple[object, ...]]:
    async with tenant_transaction(pool, tenant) as conn:
        return await (
            await conn.execute(
                "select source_kind, source_id, resource_id, lower(during), upper(during), state "
                "from gba.resource_allocations order by created_at, id"
            )
        ).fetchall()


async def mismatches(pool: RuntimePool, tenant: UUID) -> int:
    async with tenant_transaction(pool, tenant) as conn:
        row = await (await conn.execute("select gba.booking_occupancy_mismatches()")).fetchone()
    assert row is not None
    return int(row[0])


async def test_every_booking_status_is_mirrored_in_shared_occupancy(
    world: BookingWorld, app_pool: RuntimePool, owner_conn: psycopg.Connection
) -> None:
    service = BookingService(app_pool)
    tenant = world.a.tenant_id
    hold = await service.create_hold(
        tenant, world.request(at(10)), actor=ACTOR, idempotency_key=None
    )
    assert await occupancy(app_pool, tenant) == [
        ("booking", hold.booking_id, world.artist_a1, hold.starts_at, hold.ends_at, "held")
    ]
    await service.confirm(tenant, hold.booking_id, actor=ACTOR)
    assert [row[5] for row in await occupancy(app_pool, tenant)] == ["confirmed"]
    await service.cancel(tenant, hold.booking_id, actor=ACTOR)
    assert [row[5] for row in await occupancy(app_pool, tenant)] == ["released"]
    # The released interval can be taken again; an expired hold is released too.
    again = await service.create_hold(
        tenant, world.request(at(10)), actor=ACTOR, idempotency_key=None
    )
    force_hold_expired(owner_conn, world.a, again.booking_id)
    assert await service.expire_due_holds(tenant) == 1
    assert [(row[1], row[5]) for row in await occupancy(app_pool, tenant)] == [
        (hold.booking_id, "released"),
        (again.booking_id, "released"),
    ]
    assert await mismatches(app_pool, tenant) == 0
    # Another company never sees these rows.
    assert await occupancy(app_pool, world.b.tenant_id) == []


async def test_direct_sql_cannot_forge_or_rewrite_occupancy(
    world: BookingWorld, app_pool: RuntimePool, owner_conn: psycopg.Connection
) -> None:
    service = BookingService(app_pool)
    tenant = world.a.tenant_id
    booked = await service.create_hold(
        tenant, world.request(at(12)), actor=ACTOR, idempotency_key=None
    )
    await service.confirm(tenant, booked.booking_id, actor=ACTOR)
    # The runtime role cannot invent or release booking occupancy by itself.
    for statement, params in (
        (
            "insert into gba.resource_allocations (tenant_id, resource_id, source_kind, "
            "source_id, during, state) values (%s, %s, 'booking', %s, "
            "tstzrange(%s, %s, '[)'), 'confirmed')",
            (tenant, world.artist_a2, uuid7(), at(14), at(15)),
        ),
        (
            "update gba.resource_allocations set state = 'released' where source_id = %s",
            (booked.booking_id,),
        ),
    ):
        with pytest.raises(psycopg.errors.CheckViolation):
            async with tenant_transaction(app_pool, tenant) as conn:
                await conn.execute(statement, params)
    # Even the owner cannot delete rows, move intervals or revive a release.
    await service.cancel(tenant, booked.booking_id, actor=ACTOR)
    with owner_tenant_transaction(owner_conn, tenant):
        for statement in (
            "delete from gba.resource_allocations",
            "update gba.resource_allocations set during = tstzrange(lower(during), "
            "upper(during) + interval '1 hour', '[)')",
            "update gba.resource_allocations set state = 'confirmed'",
        ):
            with pytest.raises(psycopg.errors.CheckViolation), owner_conn.transaction():
                owner_conn.execute(statement)
    assert await mismatches(app_pool, tenant) == 0


async def test_readiness_refuses_drift_and_a_disabled_mirror(
    world: BookingWorld,
    app_pool: RuntimePool,
    owner_conn: psycopg.Connection,
    client: httpx.AsyncClient,
) -> None:
    service = BookingService(app_pool)
    tenant = world.a.tenant_id
    booked = await service.create_hold(
        tenant, world.request(at(16)), actor=ACTOR, idempotency_key=None
    )
    try:
        owner_conn.execute(
            "alter table gba.resource_allocations disable trigger resource_allocations_guard"
        )
        with owner_tenant_transaction(owner_conn, tenant):
            owner_conn.execute(
                "update gba.resource_allocations set state = 'released' where source_id = %s",
                (booked.booking_id,),
            )
        assert await mismatches(app_pool, tenant) == 1
        assert (await client.get("/health/ready")).status_code == 503
    finally:
        owner_conn.execute(
            "alter table gba.resource_allocations enable trigger resource_allocations_guard"
        )
    assert (await client.get("/health/ready")).status_code == 200
    trigger = "booking_allocations_mirror_occupancy"
    try:
        owner_conn.execute(f"alter table gba.booking_allocations disable trigger {trigger}")
        assert (await client.get("/health/ready")).status_code == 503
    finally:
        owner_conn.execute(f"alter table gba.booking_allocations enable trigger {trigger}")
    assert (await client.get("/health/ready")).status_code == 200


_PHANTOM = (
    "insert into gba.resource_allocations (tenant_id, resource_id, source_kind, source_id, "
    "during, state) values (%s, %s, 'booking', %s, tstzrange(%s, %s, '[)'), %s)"
)


def _without_guard(
    owner_conn: psycopg.Connection, tenant: UUID, statement: str, params: tuple[object, ...]
) -> None:
    """Simulate drift: write a row the guard would refuse (owner only, then restore)."""
    owner_conn.execute(
        "alter table gba.resource_allocations disable trigger resource_allocations_guard"
    )
    try:
        with owner_tenant_transaction(owner_conn, tenant):
            owner_conn.execute(statement, params)
    finally:
        owner_conn.execute(
            "alter table gba.resource_allocations enable trigger resource_allocations_guard"
        )


async def test_the_shared_constraint_decides_and_a_conflict_stays_a_slot_conflict(
    world: BookingWorld, app_pool: RuntimePool, owner_conn: psycopg.Connection
) -> None:
    service = BookingService(app_pool)
    tenant, resource = world.a.tenant_id, world.artist_a1
    # An active row the booking table does not know (drift or another module)
    # blocks the slot with the same typed conflict; a released row never does.
    _without_guard(
        owner_conn, tenant, _PHANTOM, (tenant, resource, uuid7(), at(18), at(19), "confirmed")
    )
    _without_guard(
        owner_conn, tenant, _PHANTOM, (tenant, resource, uuid7(), at(20), at(21), "released")
    )
    with pytest.raises(SlotConflictError):
        await service.create_hold(tenant, world.request(at(18)), actor=ACTOR, idempotency_key=None)
    admitted = await service.create_hold(
        tenant, world.request(at(20)), actor=ACTOR, idempotency_key=None
    )
    async with tenant_transaction(app_pool, tenant) as conn:
        active = await (
            await conn.execute(
                "select count(*) from gba.resource_allocations where resource_id = %s "
                "and state in ('held', 'confirmed')",
                (resource,),
            )
        ).fetchone()
    assert active == (2,)
    assert admitted.starts_at == at(20)


async def test_overlapping_stale_holds_are_released_in_shared_occupancy(
    world: BookingWorld, app_pool: RuntimePool, owner_conn: psycopg.Connection
) -> None:
    service = BookingService(app_pool)
    tenant = world.a.tenant_id
    stale = await service.create_hold(
        tenant, world.request(at(11)), actor=ACTOR, idempotency_key=None
    )
    force_hold_expired(owner_conn, world.a, stale.booking_id)
    fresh = await service.create_hold(
        tenant, world.request(at(11)), actor=ACTOR, idempotency_key=None
    )
    assert [(row[1], row[5]) for row in await occupancy(app_pool, tenant)] == [
        (stale.booking_id, "released"),
        (fresh.booking_id, "held"),
    ]


async def test_a_moved_resource_keeps_the_mirror_exact_in_a_branch_session(
    world: BookingWorld, app_pool: RuntimePool, owner_conn: psycopg.Connection
) -> None:
    service = BookingService(app_pool)
    tenant = world.a.tenant_id
    booked = await service.create_hold(
        tenant, world.request(at(13)), actor=ACTOR, idempotency_key=None
    )
    other_location, _ = seed_other_branch(owner_conn, world.a)
    # The resource moves to another branch (no API does this yet). The booking's
    # branch can still cancel it: the status cascade and its mirror run in the
    # foreign-key context, so the hidden shared row still follows (no drift).
    with owner_tenant_transaction(owner_conn, tenant):
        owner_conn.execute(
            "update gba.resources set location_id = %s where id = %s",
            (other_location, world.artist_a1),
        )

    async def cancel_in_branch() -> None:
        async with tenant_transaction(app_pool, tenant) as conn:
            await conn.execute(
                "select pg_catalog.set_config('gba.location_id', %s, true)",
                (str(world.a.location_id),),
            )
            await conn.execute(
                "update gba.bookings set status = 'CANCELLED' where id = %s",
                (booked.booking_id,),
            )

    await cancel_in_branch()
    assert [row[5] for row in await occupancy(app_pool, tenant)] == ["released"]
    assert await mismatches(app_pool, tenant) == 0


async def test_backfill_copies_heals_stays_per_company_and_refuses_unknown_companies(
    world: BookingWorld, app_pool: RuntimePool, owner_conn: psycopg.Connection
) -> None:
    service = BookingService(app_pool)
    a, b = world.a.tenant_id, world.b.tenant_id
    other = await service.create_hold(
        b,
        world.request(at(10), resource=world.artist_b1, variant=world.catalog_b.base_variant_id),
        actor=ACTOR,
        idempotency_key=None,
    )
    # A booking from "before 0018": its allocation was never mirrored.
    trigger = "booking_allocations_mirror_occupancy"
    owner_conn.execute(f"alter table gba.booking_allocations disable trigger {trigger}")
    try:
        legacy = await service.create_hold(
            a, world.request(at(10)), actor=ACTOR, idempotency_key=None
        )
    finally:
        owner_conn.execute(f"alter table gba.booking_allocations enable trigger {trigger}")
    # Its later status change needs no copy yet; the backfill copies the result.
    await service.cancel(a, legacy.booking_id, actor=ACTOR)
    # A stale copy that fell behind its booking.
    behind = await service.create_hold(a, world.request(at(12)), actor=ACTOR, idempotency_key=None)
    await service.confirm(a, behind.booking_id, actor=ACTOR)
    _without_guard(
        owner_conn,
        a,
        "update gba.resource_allocations set state = 'held' where source_id = %s",
        (behind.booking_id,),
    )
    assert await mismatches(app_pool, a) == 2
    assert backfill_for_owner(owner_conn, a) == BackfillResult(2, 0)
    assert backfill_for_owner(owner_conn, a) == BackfillResult(0, 0)
    assert {(row[1], row[5]) for row in await occupancy(app_pool, a)} == {
        (legacy.booking_id, "released"),
        (behind.booking_id, "confirmed"),
    }
    assert await occupancy(app_pool, b) == [
        ("booking", other.booking_id, world.artist_b1, other.starts_at, other.ends_at, "held")
    ]
    with pytest.raises(UnknownCompanyError):
        backfill_for_owner(owner_conn, uuid7())


def test_migration_copies_and_reconciles_existing_booking_allocations(
    test_database: ProvisionedDatabase,
) -> None:
    owner, app = conninfo_to_dict(test_database.owner_dsn), conninfo_to_dict(test_database.app_dsn)
    name = f"gba_test_{secrets.token_hex(6)}"
    bootstrap(
        test_database.admin_dsn,
        BootstrapSpec(
            database=name,
            owner_role=TEST_OWNER_ROLE,
            owner_password=str(owner["password"]),
            app_role=TEST_APP_ROLE,
            app_password=str(app["password"]),
        ),
    )
    dsn = make_conninfo(test_database.owner_dsn, dbname=name)
    try:
        apply_migrations(dsn, [m for m in load_migrations() if m.version < 18])
        with psycopg.connect(dsn, autocommit=True) as conn:
            salon = seed_salon(conn, "occupancy")
            catalog = seed_fake_catalog(conn, salon)
            resource = seed_resource(conn, salon)
            day = at(9) + timedelta(days=30)
            booked: list[UUID] = []
            with owner_tenant_transaction(conn, salon.tenant_id):
                for hour, status in ((0, "HOLD"), (1, "CONFIRMED"), (2, "CONFIRMED")):
                    start, end = day + timedelta(hours=hour), day + timedelta(hours=hour + 1)
                    row = conn.execute(
                        "insert into gba.bookings (tenant_id, location_id, variant_id, status, "
                        "starts_at, ends_at, hold_expires_at, total_cents, currency, quote, "
                        "created_by) values (%s, %s, %s, %s, %s, %s, "
                        "case when %s = 'HOLD' then now() + interval '10 minutes' end, "
                        "5000, 'USD', '{}'::jsonb, 'test:migration') returning id",
                        (
                            salon.tenant_id,
                            salon.location_id,
                            catalog.base_variant_id,
                            status,
                            start,
                            end,
                            status,
                        ),
                    ).fetchone()
                    assert row is not None
                    conn.execute(
                        "insert into gba.booking_allocations (tenant_id, booking_id, "
                        "booking_status, resource_id, during) "
                        "values (%s, %s, %s, %s, tstzrange(%s, %s, '[)'))",
                        (salon.tenant_id, row[0], status, resource, start, end),
                    )
                    booked.append(UUID(str(row[0])))
                # One booking ends cancelled before the migration.
                conn.execute(
                    "update gba.bookings set status = 'CANCELLED' where id = %s", (booked[2],)
                )
        assert [m.version for m in apply_migrations(dsn)] == [18]
        with psycopg.connect(dsn, autocommit=True) as conn:
            # Migrations never bypass row security: the copy is a per-company step.
            with owner_tenant_transaction(conn, salon.tenant_id):
                drift = conn.execute("select gba.booking_occupancy_mismatches()").fetchone()
            assert drift == (3,)
            assert backfill_for_owner(conn, salon.tenant_id) == BackfillResult(3, 0)
            assert backfill_for_owner(conn, salon.tenant_id) == BackfillResult(0, 0)
            with owner_tenant_transaction(conn, salon.tenant_id):
                rows = conn.execute(
                    "select source_kind, source_id, resource_id, state "
                    "from gba.resource_allocations order by lower(during)"
                ).fetchall()
        assert rows == [
            ("booking", booked[0], resource, "held"),
            ("booking", booked[1], resource, "confirmed"),
            ("booking", booked[2], resource, "released"),
        ]
    finally:
        with psycopg.connect(test_database.admin_dsn, autocommit=True) as conn:
            conn.execute(
                sql.SQL("drop database if exists {} with (force)").format(sql.Identifier(name))
            )
