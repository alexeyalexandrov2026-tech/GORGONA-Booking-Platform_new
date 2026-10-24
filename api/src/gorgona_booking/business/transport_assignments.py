"""M2 (package M, TMS-01): drivers, vehicles and assignment periods (ADR-0029).

A driver, truck or trailer has its own resource; an assignment holds it for its period of a trip in
the shared occupancy (gba.resource_allocations). Replacing ends one period and starts the next in
one transaction, so a busy resource changes nothing. Periods and their ends are insert-only; the
database checks at commit that every assignment holds exactly its period.
"""

import unicodedata
from datetime import datetime
from typing import Any, Literal, Self
from uuid import UUID

from psycopg.errors import ExclusionViolation, ForeignKeyViolation, UniqueViolation
from pydantic import AwareDatetime, BaseModel, Field, model_validator

from gorgona_booking.booking import idempotency
from gorgona_booking.booking.idempotency import IdempotencyScope
from gorgona_booking.booking.models import IdempotencyKeyReusedError
from gorgona_booking.booking.repository import lock_resource_schedule
from gorgona_booking.business.module_gate import TRANSPORT_MODULE, module_writes
from gorgona_booking.business.transport import (
    TransportReferenceTakenError,
    TripView,
    _fingerprint,
    _Strict,
    load_trip,
    require_transport,
    trip_span,
)
from gorgona_booking.db.pool import RuntimeConnection
from gorgona_booking.errors import ConflictError, DomainError, InvalidReferenceError, NotFoundError


class TransportResourceBusyError(ConflictError):
    code = "TRANSPORT_RESOURCE_BUSY"


class TransportAssignmentConflictError(ConflictError):
    code = "TRANSPORT_ASSIGNMENT_CONFLICT"


class TransportAssignmentInvalidError(DomainError):
    code = "TRANSPORT_ASSIGNMENT_INVALID"


def _visible(value: str) -> None:
    if not value.strip() or any(unicodedata.category(ch) == "Cc" for ch in value):
        raise ValueError("a name has visible text and no control characters")


class DriverInput(_Strict):
    schema_version: Literal[1]
    location_id: UUID
    display_name: str = Field(min_length=1, max_length=200)

    @model_validator(mode="after")
    def _text(self) -> Self:
        _visible(self.display_name)
        return self


class VehicleInput(_Strict):
    schema_version: Literal[1]
    location_id: UUID
    kind: Literal["truck", "trailer"]
    unit_number: str = Field(min_length=1, max_length=32)

    @model_validator(mode="after")
    def _text(self) -> Self:
        _visible(self.unit_number)
        return self


class AssignmentInput(_Strict):
    schema_version: Literal[1]
    role: Literal["driver", "truck", "trailer"]
    resource_id: UUID
    starts_at: AwareDatetime | None = None
    replaces: UUID | None = None


class EndInput(_Strict):
    schema_version: Literal[1]
    ends_at: AwareDatetime


class DriverView(BaseModel):
    driver_id: UUID
    location_id: UUID
    display_name: str
    resource_id: UUID


class DriverList(BaseModel):
    items: list[DriverView]


class VehicleView(BaseModel):
    vehicle_id: UUID
    location_id: UUID
    kind: str
    unit_number: str
    resource_id: UUID


class VehicleList(BaseModel):
    items: list[VehicleView]


_DRIVER = "select id, location_id, display_name, resource_id from gba.transport_drivers "
_VEHICLE = "select id, location_id, kind, unit_number, resource_id from gba.transport_vehicles "


def _driver(row: tuple[Any, ...]) -> DriverView:
    return DriverView(driver_id=row[0], location_id=row[1], display_name=row[2], resource_id=row[3])


def _vehicle(row: tuple[Any, ...]) -> VehicleView:
    return VehicleView(
        vehicle_id=row[0],
        location_id=row[1],
        kind=row[2],
        unit_number=row[3],
        resource_id=row[4],
    )


async def load_driver(conn: RuntimeConnection, driver_id: UUID) -> DriverView | None:
    row = await (await conn.execute(_DRIVER + "where id = %s", (driver_id,))).fetchone()
    return None if row is None else _driver(row)


async def list_drivers(conn: RuntimeConnection) -> DriverList:
    rows = await (await conn.execute(_DRIVER + "order by display_name, id limit 100")).fetchall()
    return DriverList(items=[_driver(row) for row in rows])


async def load_vehicle(conn: RuntimeConnection, vehicle_id: UUID) -> VehicleView | None:
    row = await (await conn.execute(_VEHICLE + "where id = %s", (vehicle_id,))).fetchone()
    return None if row is None else _vehicle(row)


async def list_vehicles(conn: RuntimeConnection) -> VehicleList:
    rows = await (await conn.execute(_VEHICLE + "order by unit_number, id limit 100")).fetchall()
    return VehicleList(items=[_vehicle(row) for row in rows])


async def _resource(
    conn: RuntimeConnection, business: UUID, location: UUID, kind: str, name: str
) -> UUID:
    """The lane of a new driver or vehicle: its own resource in its branch (decision 1)."""
    row = await (
        await conn.execute(
            "insert into gba.resources (tenant_id, location_id, kind, display_name) "
            "values (%s, %s, %s, %s) returning id",
            (business, location, kind, name),
        )
    ).fetchone()
    assert row is not None  # noqa: S101 - insert returning
    return UUID(str(row[0]))


async def save_driver(
    conn: RuntimeConnection,
    business: UUID,
    driver_id: UUID,
    *,
    user_id: UUID,
    actor: str,
    key: str,
    body: DriverInput,
) -> DriverView:
    """Register a driver once; the same id with the same details answers the same (decision 1)."""
    await require_transport(conn, business)
    scope = IdempotencyScope(business, actor, "transport.driver", key)
    fingerprint = _fingerprint(driver_id, body)
    stored = await idempotency.claim(conn, scope, fingerprint)
    if stored is not None and stored.request_hash != fingerprint:
        raise IdempotencyKeyReusedError("Key was used for another request")
    view = await load_driver(conn, driver_id)
    if view is None and stored is None:
        try:
            async with module_writes(TRANSPORT_MODULE), conn.transaction():
                resource = await _resource(
                    conn, business, body.location_id, "driver", body.display_name
                )
                await conn.execute(
                    "insert into gba.transport_drivers (tenant_id, id, location_id, resource_id, "
                    "display_name, created_by) values (%s, %s, %s, %s, %s, %s)",
                    (business, driver_id, body.location_id, resource, body.display_name, user_id),
                )
        except ForeignKeyViolation as exc:
            raise InvalidReferenceError("Unknown branch", field="location_id") from exc
        except UniqueViolation as exc:
            raise TransportReferenceTakenError("This driver is already registered") from exc
        view = await load_driver(conn, driver_id)
    if view is None:
        raise NotFoundError("Driver not found", driver_id=str(driver_id))
    if (view.location_id, view.display_name) != (body.location_id, body.display_name):
        raise TransportReferenceTakenError("This driver id is registered with other details")
    if stored is None:
        await idempotency.complete(conn, scope, 200, {"driver_id": str(driver_id)})
    return view


async def save_vehicle(
    conn: RuntimeConnection,
    business: UUID,
    vehicle_id: UUID,
    *,
    user_id: UUID,
    actor: str,
    key: str,
    body: VehicleInput,
) -> VehicleView:
    """Register a truck or trailer once; its unit number is unique in the business."""
    await require_transport(conn, business)
    scope = IdempotencyScope(business, actor, "transport.vehicle", key)
    fingerprint = _fingerprint(vehicle_id, body)
    stored = await idempotency.claim(conn, scope, fingerprint)
    if stored is not None and stored.request_hash != fingerprint:
        raise IdempotencyKeyReusedError("Key was used for another request")
    view = await load_vehicle(conn, vehicle_id)
    if view is None and stored is None:
        try:
            async with module_writes(TRANSPORT_MODULE), conn.transaction():
                resource = await _resource(
                    conn, business, body.location_id, body.kind, body.unit_number
                )
                await conn.execute(
                    "insert into gba.transport_vehicles (tenant_id, id, location_id, resource_id, "
                    "kind, unit_number, created_by) values (%s, %s, %s, %s, %s, %s, %s)",
                    (
                        business,
                        vehicle_id,
                        body.location_id,
                        resource,
                        body.kind,
                        body.unit_number,
                        user_id,
                    ),
                )
        except ForeignKeyViolation as exc:
            raise InvalidReferenceError("Unknown branch", field="location_id") from exc
        except UniqueViolation as exc:
            raise TransportReferenceTakenError("Another vehicle has this unit number") from exc
        view = await load_vehicle(conn, vehicle_id)
    if view is None:
        raise NotFoundError("Vehicle not found", vehicle_id=str(vehicle_id))
    if (view.location_id, view.kind, view.unit_number) != (
        body.location_id,
        body.kind,
        body.unit_number,
    ):
        raise TransportReferenceTakenError("This vehicle id is registered with other details")
    if stored is None:
        await idempotency.complete(conn, scope, 200, {"vehicle_id": str(vehicle_id)})
    return view


async def _view(conn: RuntimeConnection, trip_id: UUID) -> TripView:
    view = await load_trip(conn, trip_id)
    if view is None:
        raise NotFoundError("Trip not found", trip_id=str(trip_id))
    return view


async def _lock_trip(conn: RuntimeConnection, trip_id: UUID) -> tuple[UUID, str]:
    """Every period change of one trip waits here first (decision 7)."""
    row = await (
        await conn.execute(
            "select location_id, status from gba.transport_trips where id = %s for update",
            (trip_id,),
        )
    ).fetchone()
    if row is None:
        raise NotFoundError("Trip not found", trip_id=str(trip_id))
    return row[0], row[1]


async def _span(conn: RuntimeConnection, trip_id: UUID) -> tuple[datetime, datetime]:
    span = await trip_span(conn, trip_id)
    if span is None or span[0] >= span[1]:
        raise TransportAssignmentInvalidError("The trip has no span to assign")
    return span


async def _hold(
    conn: RuntimeConnection,
    business: UUID,
    resource: UUID,
    assignment: UUID,
    start: datetime,
    end: datetime,
) -> None:
    await conn.execute(
        "insert into gba.resource_allocations (tenant_id, resource_id, source_kind, source_id, "
        "during, state) values (%s, %s, 'trip_assignment', %s, tstzrange(%s, %s, '[)'), "
        "'confirmed')",
        (business, resource, assignment, start, end),
    )


async def _end_period(
    conn: RuntimeConnection,
    business: UUID,
    *,
    assignment: UUID,
    resource: UUID,
    started: datetime,
    at: datetime,
    user_id: UUID,
) -> None:
    """End a period at `at`: release its open hold and keep `[start, at)` (decision 5)."""
    await conn.execute(
        "insert into gba.transport_assignment_ends (tenant_id, assignment_id, ends_at, "
        "created_by) values (%s, %s, %s, %s)",
        (business, assignment, at, user_id),
    )
    await conn.execute(
        "update gba.resource_allocations set state = 'released' "
        "where source_kind = 'trip_assignment' and source_id = %s and state = 'confirmed'",
        (assignment,),
    )
    if at > started:
        await _hold(conn, business, resource, assignment, started, at)


async def assign(
    conn: RuntimeConnection,
    business: UUID,
    trip_id: UUID,
    assignment_id: UUID,
    *,
    user_id: UUID,
    actor: str,
    key: str,
    body: AssignmentInput,
) -> TripView:
    """Assign a driver, truck or trailer, or replace the open one of that role (decisions 2-5)."""
    await require_transport(conn, business)
    scope = IdempotencyScope(business, actor, "transport.assignment", key)
    fingerprint = _fingerprint(f"{trip_id}/{assignment_id}", body)
    stored = await idempotency.claim(conn, scope, fingerprint)
    if stored is not None:
        if stored.request_hash != fingerprint:
            raise IdempotencyKeyReusedError("Key was used for another request")
        return await _view(conn, trip_id)
    location, status = await _lock_trip(conn, trip_id)
    if status not in ("planned", "in_transit"):
        raise TransportAssignmentInvalidError("Only a planned or running trip is assigned")
    used = await (
        await conn.execute(
            "select 1 from gba.transport_assignments where id = %s", (assignment_id,)
        )
    ).fetchone()
    if used is not None:
        raise TransportAssignmentConflictError("This assignment id is already used")
    start, end = await _span(conn, trip_id)
    periods = await (
        await conn.execute(
            "select a.id, a.resource_id, a.starts_at, e.ends_at "
            "from gba.transport_assignments a left join gba.transport_assignment_ends e "
            "on e.tenant_id = a.tenant_id and e.assignment_id = a.id "
            "where a.trip_id = %s and a.role = %s order by a.starts_at, a.created_at",
            (trip_id, body.role),
        )
    ).fetchall()
    current = next((p for p in periods if p[3] is None), None)
    if (None if current is None else current[0]) != body.replaces:
        raise TransportAssignmentConflictError(
            "The trip's assignments changed since they were read; reload the trip",
            open_assignment=None if current is None else str(current[0]),
        )
    resource = await (
        await conn.execute(
            "select kind, location_id, is_active from gba.resources where id = %s",
            (body.resource_id,),
        )
    ).fetchone()
    if resource is None or (resource[0], resource[1], resource[2]) != (body.role, location, True):
        raise TransportAssignmentInvalidError(
            "The resource is not an active lane of this role in the trip's branch",
            resource_id=str(body.resource_id),
        )
    starts = body.starts_at or start
    if not start <= starts < end:
        raise TransportAssignmentInvalidError(
            "An assignment starts inside the trip's span",
            span_start=start.isoformat(),
            span_end=end.isoformat(),
        )
    if current is not None:
        if body.resource_id == current[1]:
            raise TransportAssignmentInvalidError("A replacement names another resource")
        if starts < current[2]:
            raise TransportAssignmentInvalidError("A replacement starts within the period it ends")
    elif any(p[3] is not None and p[3] > starts for p in periods):
        raise TransportAssignmentInvalidError("Periods of one role on one trip never overlap")
    try:
        async with module_writes(TRANSPORT_MODULE), conn.transaction():
            if current is not None:
                await _end_period(
                    conn,
                    business,
                    assignment=current[0],
                    resource=current[1],
                    started=current[2],
                    at=starts,
                    user_id=user_id,
                )
            await lock_resource_schedule(conn, business, body.resource_id)
            await conn.execute(
                "insert into gba.transport_assignments (tenant_id, id, trip_id, role, "
                "resource_id, starts_at, replaces, created_by) "
                "values (%s, %s, %s, %s, %s, %s, %s, %s)",
                (
                    business,
                    assignment_id,
                    trip_id,
                    body.role,
                    body.resource_id,
                    starts,
                    body.replaces,
                    user_id,
                ),
            )
            await _hold(conn, business, body.resource_id, assignment_id, starts, end)
    except ExclusionViolation as exc:
        raise TransportResourceBusyError(
            "The resource is held by another trip in this period",
            resource_id=str(body.resource_id),
        ) from exc
    view = await _view(conn, trip_id)
    await idempotency.complete(conn, scope, 200, {"trip_id": str(trip_id)})
    return view


async def end_assignment(
    conn: RuntimeConnection,
    business: UUID,
    trip_id: UUID,
    assignment_id: UUID,
    *,
    user_id: UUID,
    actor: str,
    key: str,
    body: EndInput,
) -> TripView:
    """End an open period without a successor; the rest of its hold is released (decision 4)."""
    await require_transport(conn, business)
    scope = IdempotencyScope(business, actor, "transport.assignment_end", key)
    fingerprint = _fingerprint(f"{trip_id}/{assignment_id}", body)
    stored = await idempotency.claim(conn, scope, fingerprint)
    if stored is not None:
        if stored.request_hash != fingerprint:
            raise IdempotencyKeyReusedError("Key was used for another request")
        return await _view(conn, trip_id)
    await _lock_trip(conn, trip_id)
    row = await (
        await conn.execute(
            "select a.resource_id, a.starts_at, e.ends_at "
            "from gba.transport_assignments a left join gba.transport_assignment_ends e "
            "on e.tenant_id = a.tenant_id and e.assignment_id = a.id "
            "where a.id = %s and a.trip_id = %s",
            (assignment_id, trip_id),
        )
    ).fetchone()
    if row is None:
        raise NotFoundError("Assignment not found", assignment_id=str(assignment_id))
    if row[2] is not None:
        raise TransportAssignmentConflictError("The assignment has already ended")
    _, end = await _span(conn, trip_id)
    if not row[1] <= body.ends_at <= end:
        raise TransportAssignmentInvalidError("An assignment ends inside its period")
    async with module_writes(TRANSPORT_MODULE), conn.transaction():
        await _end_period(
            conn,
            business,
            assignment=assignment_id,
            resource=row[0],
            started=row[1],
            at=body.ends_at,
            user_id=user_id,
        )
    view = await _view(conn, trip_id)
    await idempotency.complete(conn, scope, 200, {"trip_id": str(trip_id)})
    return view
