"""Staff reservations of resources: the second consumer of shared occupancy (ADR-0022).

A reservation takes the same per-resource advisory locks as booking (resource-id
order), releases stale overlapping holds the way a new booking does, and inserts
the reservation with one confirmed allocation per resource in one savepoint: all
resources or none. The shared exclusion constraint decides, so a conflict with a
booking or another reservation is the same typed slot conflict. Receipts hold the
reservation id only; the audit never records the free-text purpose.
"""

from datetime import datetime
from typing import Any
from uuid import UUID

import psycopg
from psycopg import errors

from gorgona_booking.booking import repository as repo
from gorgona_booking.booking.idempotency import IdempotencyScope
from gorgona_booking.booking.models import ResourceUnavailableError, SlotConflictError
from gorgona_booking.business import commands
from gorgona_booking.business.modules import ModuleDisabledError
from gorgona_booking.db.pool import RuntimeConnection
from gorgona_booking.errors import ConflictError, InvalidReferenceError, NotFoundError
from gorgona_booking.occupancy.reservation_contracts import (
    CancelInput,
    ReservationInput,
    ReservationList,
    ReservationReceipt,
    ReservationView,
)

_CREATE = "business.reservation.create"
_CANCEL = "business.reservation.cancel"
_SELECT = (
    "select v.id, v.location_id, v.starts_at, v.ends_at, v.purpose, v.status, v.created_at, "
    "v.cancelled_at, coalesce((select array_agg(r.resource_id order by r.resource_id) "
    "from gba.resource_allocations r where r.tenant_id = v.tenant_id "
    "and r.source_kind = 'reservation' and r.source_id = v.id), '{}') "
    "from gba.resource_reservations v"
)


def _view(business_id: UUID, row: tuple[Any, ...]) -> ReservationView:
    return ReservationView(
        business_id=business_id,
        reservation_id=row[0],
        location_id=row[1],
        starts_at=row[2],
        ends_at=row[3],
        purpose=row[4],
        status=row[5],
        created_at=row[6],
        cancelled_at=row[7],
        resource_ids=tuple(row[8]),
    )


async def load_reservation(
    conn: RuntimeConnection, business_id: UUID, reservation_id: UUID
) -> ReservationView | None:
    row = await (
        await conn.execute(
            f"{_SELECT} where v.tenant_id = %s and v.id = %s",
            (business_id, reservation_id),
        )
    ).fetchone()
    return None if row is None else _view(business_id, tuple(row))


async def list_reservations(
    conn: RuntimeConnection,
    business_id: UUID,
    *,
    starts: datetime,
    ends: datetime,
    location_id: UUID | None,
) -> ReservationList:
    rows = await (
        await conn.execute(
            f"{_SELECT} where v.tenant_id = %s "
            "and v.starts_at < %s and v.ends_at > %s "
            "and (%s::uuid is null or v.location_id = %s) "
            "order by v.starts_at, v.id limit 200",
            (business_id, ends, starts, location_id, location_id),
        )
    ).fetchall()
    return ReservationList(
        business_id=business_id, items=tuple(_view(business_id, tuple(r)) for r in rows)
    )


async def _require(
    conn: RuntimeConnection, business_id: UUID, reservation_id: UUID
) -> ReservationView:
    current = await load_reservation(conn, business_id, reservation_id)
    if current is None:
        raise NotFoundError("Reservation not found")
    return current


async def _check_resources(
    conn: RuntimeConnection, body: ReservationInput, resources: list[UUID]
) -> None:
    rows = await (
        await conn.execute(
            "select id, location_id, is_active from gba.resources where id = any(%s)",
            (resources,),
        )
    ).fetchall()
    if len(rows) != len(resources) or any(row[1] != body.location_id for row in rows):
        raise InvalidReferenceError(
            "Every resource must belong to the reservation's branch", field="resource_ids"
        )
    if not all(row[2] for row in rows):
        raise ResourceUnavailableError("An inactive resource cannot be reserved")


async def create_reservation(
    conn: RuntimeConnection,
    *,
    business_id: UUID,
    reservation_id: UUID,
    user_id: UUID,
    actor: str,
    key: str,
    body: ReservationInput,
    request_id: str | None,
) -> ReservationView:
    scope = IdempotencyScope(business_id, actor, _CREATE, key)
    request_hash = commands.fingerprint(
        {"reservation_id": str(reservation_id), **body.model_dump(mode="json")}
    )
    receipt = await commands.claim(conn, scope, request_hash, ReservationReceipt)
    if receipt is not None:
        return await _require(conn, business_id, receipt.reservation_id)

    resources = sorted(set(body.resource_ids))
    # The same locks and order as booking: contention queues instead of deadlocking.
    for resource_id in resources:
        await repo.lock_resource_schedule(conn, business_id, resource_id)
    await _check_resources(conn, body, resources)
    if await load_reservation(conn, business_id, reservation_id) is not None:
        raise ConflictError("This reservation already exists")
    await repo.set_audit_context(
        conn, actor="system:hold-expiry", reason="expired_on_contention", request_id=request_id
    )
    for resource_id in resources:
        await repo.expire_stale_holds_overlapping(conn, resource_id, body.starts_at, body.ends_at)
    try:
        async with conn.transaction():
            await conn.execute(
                "insert into gba.resource_reservations (tenant_id, id, location_id, starts_at, "
                "ends_at, purpose, resource_count, created_by) "
                "values (%s, %s, %s, %s, %s, %s, %s, %s)",
                (
                    business_id,
                    reservation_id,
                    body.location_id,
                    body.starts_at,
                    body.ends_at,
                    body.purpose,
                    len(resources),
                    user_id,
                ),
            )
            for resource_id in resources:
                await conn.execute(
                    "insert into gba.resource_allocations (tenant_id, resource_id, source_kind, "
                    "source_id, during, state) values (%s, %s, 'reservation', %s, "
                    "tstzrange(%s, %s, '[)'), 'confirmed')",
                    (business_id, resource_id, reservation_id, body.starts_at, body.ends_at),
                )
    except errors.ExclusionViolation as exc:
        if repo.is_slot_conflict(exc):
            raise SlotConflictError("A resource is already taken in this interval") from exc
        raise
    except errors.UniqueViolation as exc:
        # The same id in another branch (hidden by row security) or a racing request.
        raise ConflictError("This reservation already exists") from exc
    except psycopg.DatabaseError as exc:
        if exc.sqlstate == repo.BOOKING_MODULE_DISABLED:
            raise ModuleDisabledError(
                "Booking and resources are turned off in this business's configuration"
            ) from exc
        raise
    await commands.audit(
        conn,
        business_id,
        actor,
        "resource_reservation.created",
        "resource_reservation",
        str(reservation_id),
        {
            "location_id": str(body.location_id),
            "resource_count": len(resources),
            "starts_at": body.starts_at.isoformat(),
            "ends_at": body.ends_at.isoformat(),
        },
    )
    await commands.complete(conn, scope, ReservationReceipt(reservation_id=reservation_id))
    return await _require(conn, business_id, reservation_id)


async def cancel_reservation(
    conn: RuntimeConnection,
    *,
    business_id: UUID,
    reservation_id: UUID,
    user_id: UUID,
    actor: str,
    key: str,
    body: CancelInput,
) -> ReservationView:
    scope = IdempotencyScope(business_id, actor, _CANCEL, key)
    request_hash = commands.fingerprint(
        {"reservation_id": str(reservation_id), **body.model_dump(mode="json")}
    )
    receipt = await commands.claim(conn, scope, request_hash, ReservationReceipt)
    if receipt is not None:
        return await _require(conn, business_id, receipt.reservation_id)
    current = await _require(conn, business_id, reservation_id)
    try:
        # Only an active reservation changes; a concurrent cancel leaves nothing to do.
        cancelled = await (
            await conn.execute(
                "update gba.resource_reservations set status = 'cancelled', cancelled_by = %s, "
                "cancelled_at = now() where tenant_id = %s and id = %s and status = 'active' "
                "returning id",
                (user_id, business_id, reservation_id),
            )
        ).fetchone()
    except errors.CheckViolation as exc:
        raise ConflictError(
            "A reserved resource now belongs to another branch; cancel this reservation "
            "with company-wide access"
        ) from exc
    if cancelled is not None:
        await commands.audit(
            conn,
            business_id,
            actor,
            "resource_reservation.cancelled",
            "resource_reservation",
            str(reservation_id),
            {"location_id": str(current.location_id), "resource_count": len(current.resource_ids)},
        )
    await commands.complete(conn, scope, ReservationReceipt(reservation_id=reservation_id))
    return await _require(conn, business_id, reservation_id)
