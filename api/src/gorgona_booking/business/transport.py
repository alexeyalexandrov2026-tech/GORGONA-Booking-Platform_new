"""M1 (package M, TMS-01): shipment orders, loads, trips, stops and legs (ADR-0028).

One trip carries several loads; a load is split across trips by quantity; the planned total of a
load never exceeds its quantity. Orders and trips are replaced whole with their expected revision;
the database rechecks the plan at commit and gates writes on the transport module.
"""

import hashlib
import json
from datetime import UTC, datetime
from typing import Literal, Self
from uuid import UUID

from psycopg.errors import ForeignKeyViolation, UniqueViolation
from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator

from gorgona_booking.booking import idempotency
from gorgona_booking.booking.idempotency import IdempotencyScope
from gorgona_booking.booking.models import IdempotencyKeyReusedError
from gorgona_booking.business import modules
from gorgona_booking.business.module_gate import TRANSPORT_MODULE, module_writes, require_module
from gorgona_booking.business.readiness_registry import at_least
from gorgona_booking.db.pool import RuntimeConnection
from gorgona_booking.errors import ConflictError, DomainError, InvalidReferenceError, NotFoundError


class TransportNotReadyError(ConflictError):
    code = "MODULE_NOT_READY"


class TransportRevisionConflictError(ConflictError):
    code = "TRANSPORT_REVISION_CONFLICT"


class TransportReferenceTakenError(ConflictError):
    code = "TRANSPORT_REFERENCE_TAKEN"


class TransportLegInvalidError(DomainError):
    code = "TRANSPORT_LEG_INVALID"


class TransportTimeZoneError(DomainError):
    code = "TRANSPORT_TIME_ZONE_UNKNOWN"


class TransportLoadOverplannedError(ConflictError):
    code = "TRANSPORT_LOAD_OVERPLANNED"


class TransportLoadPlannedError(ConflictError):
    code = "TRANSPORT_LOAD_PLANNED"


class TransportTripAssignedError(ConflictError):
    code = "TRANSPORT_TRIP_ASSIGNED"


class TransportTripStartedError(ConflictError):
    code = "TRANSPORT_TRIP_STARTED"


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class LoadInput(_Strict):
    load_id: UUID
    description: str = Field(min_length=1, max_length=500)
    quantity: int = Field(ge=1, le=1_000_000)
    unit: str = Field(min_length=1, max_length=32)
    weight_grams: int | None = Field(default=None, ge=0, le=999_999_999_999)
    shipper_id: UUID | None = None
    consignee_id: UUID | None = None


class OrderInput(_Strict):
    schema_version: Literal[1]
    expected_revision: int = Field(ge=0, le=2_147_483_647)
    customer_id: UUID
    reference: str = Field(min_length=1, max_length=64)
    loads: list[LoadInput] = Field(min_length=1, max_length=50)

    @model_validator(mode="after")
    def _distinct(self) -> Self:
        if len({load.load_id for load in self.loads}) != len(self.loads):
            raise ValueError("each load is listed once")
        return self


class StopInput(_Strict):
    kind: Literal["pickup", "delivery"]
    place: str = Field(min_length=1, max_length=300)
    time_zone: str = Field(min_length=1, max_length=64)
    window_start: AwareDatetime
    window_end: AwareDatetime

    @model_validator(mode="after")
    def _window(self) -> Self:
        if self.window_start > self.window_end:
            raise ValueError("a window starts before it ends")
        return self


class LegInput(_Strict):
    load_id: UUID
    quantity: int = Field(ge=1, le=1_000_000)
    pickup_stop: int = Field(ge=1, le=50)
    delivery_stop: int = Field(ge=1, le=50)


class TripInput(_Strict):
    schema_version: Literal[1]
    expected_revision: int = Field(ge=0, le=2_147_483_647)
    location_id: UUID
    reference: str = Field(min_length=1, max_length=64)
    stops: list[StopInput] = Field(min_length=2, max_length=50)
    legs: list[LegInput] = Field(min_length=1, max_length=100)


class LoadView(BaseModel):
    load_id: UUID
    position: int
    description: str
    quantity: int
    unit: str
    weight_grams: int | None
    shipper_id: UUID | None
    consignee_id: UUID | None
    planned: int


class OrderView(BaseModel):
    order_id: UUID
    revision: int
    customer_id: UUID
    reference: str
    loads: list[LoadView]


class OrderList(BaseModel):
    items: list[OrderView]


class StopView(BaseModel):
    position: int
    kind: str
    place: str
    time_zone: str
    window_start: datetime
    window_end: datetime


class LegView(BaseModel):
    position: int
    load_id: UUID
    quantity: int
    pickup_stop: int
    delivery_stop: int
    # ADR-0030: what the leg's events recorded; loaded and not yet resolved stays open.
    loaded: int = 0
    delivered: int = 0
    refused: int = 0
    damaged: int = 0


class AssignmentView(BaseModel):
    """A period of a driver, truck or trailer on the trip; `ends_at` is null while it is open."""

    assignment_id: UUID
    role: str
    resource_id: UUID
    starts_at: datetime
    ends_at: datetime | None
    replaces: UUID | None


class QuantityView(BaseModel):
    leg_position: int
    quantity: int


class EventView(BaseModel):
    """A stop event: an insert-only fact with its source and the source's event id."""

    event_id: UUID
    stop_position: int
    kind: str
    occurred_at: datetime
    source: str
    source_event_id: str
    note: str | None
    quantities: list[QuantityView]


class TripView(BaseModel):
    trip_id: UUID
    location_id: UUID
    reference: str
    status: str
    revision: int
    stops: list[StopView]
    legs: list[LegView]
    assignments: list[AssignmentView]
    events: list[EventView]


class TripList(BaseModel):
    items: list[TripView]


async def require_transport(conn: RuntimeConnection, business: UUID) -> None:
    """Writes need an accepted module that this business enabled (ADR-0019, ADR-0028)."""
    current = modules.MODULES_BY_ID[TRANSPORT_MODULE]
    if not current.enableable or not at_least(current.readiness, modules.MINIMUM_READINESS):
        raise TransportNotReadyError("Transport has not been accepted", module_id=TRANSPORT_MODULE)
    await require_module(conn, business, TRANSPORT_MODULE)
    for dependency in current.depends_on:
        if modules.MODULES_BY_ID[dependency].kind == modules.ModuleKind.OPTIONAL:
            await require_module(conn, business, dependency)


def _fingerprint(subject: UUID | str, body: BaseModel) -> str:
    return hashlib.sha256(
        json.dumps(
            {"subject": str(subject), "body": body.model_dump(mode="json")},
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
    ).hexdigest()


async def _planned(conn: RuntimeConnection, load_ids: list[UUID]) -> dict[UUID, int]:
    rows = await (
        await conn.execute(
            "select load_id, sum(quantity) from gba.transport_legs where load_id = any(%s) "
            "group by load_id",
            (load_ids,),
        )
    ).fetchall()
    return {row[0]: int(row[1]) for row in rows}


async def load_order(conn: RuntimeConnection, order_id: UUID) -> OrderView | None:
    head = await (
        await conn.execute(
            "select revision, customer_id, reference from gba.transport_orders where id = %s",
            (order_id,),
        )
    ).fetchone()
    if head is None:
        return None
    rows = await (
        await conn.execute(
            "select id, position, description, quantity, unit, weight_grams, shipper_id, "
            "consignee_id from gba.transport_loads where order_id = %s and not removed "
            "order by position",
            (order_id,),
        )
    ).fetchall()
    planned = await _planned(conn, [row[0] for row in rows])
    return OrderView(
        order_id=order_id,
        revision=head[0],
        customer_id=head[1],
        reference=head[2],
        loads=[
            LoadView(
                load_id=row[0],
                position=row[1],
                description=row[2],
                quantity=row[3],
                unit=row[4],
                weight_grams=row[5],
                shipper_id=row[6],
                consignee_id=row[7],
                planned=planned.get(row[0], 0),
            )
            for row in rows
        ],
    )


async def list_orders(conn: RuntimeConnection) -> OrderList:
    rows = await (
        await conn.execute("select id from gba.transport_orders order by id limit 100")
    ).fetchall()
    items = [await load_order(conn, row[0]) for row in rows]
    return OrderList(items=[item for item in items if item is not None])


async def save_order(
    conn: RuntimeConnection,
    business: UUID,
    order_id: UUID,
    *,
    user_id: UUID,
    actor: str,
    key: str,
    body: OrderInput,
) -> OrderView:
    """Replace a shipment order and its loads whole, with the expected revision (decision 3)."""
    await require_transport(conn, business)
    scope = IdempotencyScope(business, actor, "transport.order", key)
    fingerprint = _fingerprint(order_id, body)
    stored = await idempotency.claim(conn, scope, fingerprint)
    if stored is not None:
        if stored.request_hash != fingerprint:
            raise IdempotencyKeyReusedError("Key was used for another request")
        view = await load_order(conn, order_id)
        if view is None:
            raise NotFoundError("Order not found", order_id=str(order_id))
        return view
    current = await (
        await conn.execute(
            "select revision from gba.transport_orders where id = %s for update", (order_id,)
        )
    ).fetchone()
    found = 0 if current is None else int(current[0])
    if found != body.expected_revision:
        raise TransportRevisionConflictError(
            "The order changed since it was read; reload it", revision=found
        )
    try:
        async with module_writes(TRANSPORT_MODULE), conn.transaction():
            if current is None:
                await conn.execute(
                    "insert into gba.transport_orders (tenant_id, id, customer_id, reference, "
                    "revision, created_by) values (%s, %s, %s, %s, 1, %s)",
                    (business, order_id, body.customer_id, body.reference, user_id),
                )
            else:
                await conn.execute(
                    "update gba.transport_orders set customer_id = %s, reference = %s, "
                    "revision = revision + 1, updated_at = clock_timestamp() where id = %s",
                    (body.customer_id, body.reference, order_id),
                )
            await _save_loads(conn, business, order_id, body)
    except UniqueViolation as exc:
        raise TransportReferenceTakenError("Another order has this reference") from exc
    except ForeignKeyViolation as exc:
        raise InvalidReferenceError("Unknown counterparty", field="customer_id") from exc
    view = await load_order(conn, order_id)
    assert view is not None  # noqa: S101 - saved above
    await idempotency.complete(conn, scope, 200, {"order_id": str(order_id)})
    return view


async def _save_loads(
    conn: RuntimeConnection, business: UUID, order_id: UUID, body: OrderInput
) -> None:
    existing = {
        row[0]: row[1]
        for row in await (
            await conn.execute(
                "select id, order_id from gba.transport_loads where order_id = %s "
                "or id = any(%s) order by id for update",
                (order_id, [load.load_id for load in body.loads]),
            )
        ).fetchall()
    }
    planned = await _planned(conn, list(existing))
    wanted = {load.load_id for load in body.loads}
    for load_id, owner in existing.items():
        if owner != order_id:
            raise InvalidReferenceError("A load belongs to another order", load_id=str(load_id))
        if load_id not in wanted:
            if planned.get(load_id, 0) > 0:
                raise TransportLoadPlannedError(
                    "A planned load cannot be removed", load_id=str(load_id)
                )
            await conn.execute(
                "update gba.transport_loads set removed = true where id = %s", (load_id,)
            )
    for position, load in enumerate(body.loads, start=1):
        values = (
            position,
            load.description,
            load.quantity,
            load.unit,
            load.weight_grams,
            load.shipper_id,
            load.consignee_id,
        )
        if load.load_id in existing:
            if load.quantity < planned.get(load.load_id, 0):
                raise TransportLoadPlannedError(
                    "A load cannot shrink below what is planned",
                    load_id=str(load.load_id),
                    planned=planned.get(load.load_id, 0),
                )
            await conn.execute(
                "update gba.transport_loads set position = %s, description = %s, "
                "quantity = %s, unit = %s, weight_grams = %s, shipper_id = %s, "
                "consignee_id = %s, removed = false where id = %s",
                (*values, load.load_id),
            )
        else:
            await conn.execute(
                "insert into gba.transport_loads (tenant_id, id, order_id, position, "
                "description, quantity, unit, weight_grams, shipper_id, consignee_id) "
                "values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
                (business, load.load_id, order_id, *values),
            )


def _utc(value: datetime) -> datetime:
    return value.astimezone(UTC)


async def trip_span(conn: RuntimeConnection, trip_id: UUID) -> tuple[datetime, datetime] | None:
    """[earliest window start, latest window end) of a trip's stops (ADR-0029 decision 4)."""
    row = await (
        await conn.execute(
            "select min(window_start), max(window_end) from gba.transport_stops where trip_id = %s",
            (trip_id,),
        )
    ).fetchone()
    if row is None or row[0] is None:
        return None
    return row[0], row[1]


async def has_open_assignment(conn: RuntimeConnection, trip_id: UUID) -> bool:
    row = await (
        await conn.execute(
            "select 1 from gba.transport_assignments a where a.trip_id = %s and not exists ("
            "select 1 from gba.transport_assignment_ends e "
            "where e.tenant_id = a.tenant_id and e.assignment_id = a.id) limit 1",
            (trip_id,),
        )
    ).fetchone()
    return row is not None


async def load_trip(conn: RuntimeConnection, trip_id: UUID) -> TripView | None:
    head = await (
        await conn.execute(
            "select location_id, reference, status, revision from gba.transport_trips "
            "where id = %s",
            (trip_id,),
        )
    ).fetchone()
    if head is None:
        return None
    stops = await (
        await conn.execute(
            "select position, kind, place, time_zone, window_start, window_end "
            "from gba.transport_stops where trip_id = %s order by position",
            (trip_id,),
        )
    ).fetchall()
    legs = await (
        await conn.execute(
            "select position, load_id, quantity, pickup_stop, delivery_stop "
            "from gba.transport_legs where trip_id = %s order by position",
            (trip_id,),
        )
    ).fetchall()
    periods = await (
        await conn.execute(
            "select a.id, a.role, a.resource_id, a.starts_at, e.ends_at, a.replaces "
            "from gba.transport_assignments a left join gba.transport_assignment_ends e "
            "on e.tenant_id = a.tenant_id and e.assignment_id = a.id "
            "where a.trip_id = %s order by a.starts_at, a.created_at, a.id",
            (trip_id,),
        )
    ).fetchall()
    done: dict[int, dict[str, int]] = {}
    for position, kind, total in await (
        await conn.execute(
            "select q.leg_position, e.kind, sum(q.quantity) from gba.transport_event_quantities q "
            "join gba.transport_stop_events e on e.tenant_id = q.tenant_id and e.id = q.event_id "
            "where q.trip_id = %s group by q.leg_position, e.kind",
            (trip_id,),
        )
    ).fetchall():
        done.setdefault(int(position), {})[kind] = int(total)
    quantities: dict[UUID, list[QuantityView]] = {}
    for event_id, position, quantity in await (
        await conn.execute(
            "select event_id, leg_position, quantity from gba.transport_event_quantities "
            "where trip_id = %s order by event_id, leg_position",
            (trip_id,),
        )
    ).fetchall():
        quantities.setdefault(event_id, []).append(
            QuantityView(leg_position=position, quantity=quantity)
        )
    events = await (
        await conn.execute(
            "select id, stop_position, kind, occurred_at, source, source_event_id, note "
            "from gba.transport_stop_events where trip_id = %s "
            "order by occurred_at, recorded_at, id",
            (trip_id,),
        )
    ).fetchall()
    return TripView(
        trip_id=trip_id,
        location_id=head[0],
        reference=head[1],
        status=head[2],
        revision=head[3],
        stops=[
            StopView(
                position=row[0],
                kind=row[1],
                place=row[2],
                time_zone=row[3],
                window_start=_utc(row[4]),
                window_end=_utc(row[5]),
            )
            for row in stops
        ],
        legs=[
            LegView(
                position=row[0],
                load_id=row[1],
                quantity=row[2],
                pickup_stop=row[3],
                delivery_stop=row[4],
                **{
                    kind: done.get(row[0], {}).get(kind, 0)
                    for kind in ("loaded", "delivered", "refused", "damaged")
                },
            )
            for row in legs
        ],
        assignments=[
            AssignmentView(
                assignment_id=row[0],
                role=row[1],
                resource_id=row[2],
                starts_at=_utc(row[3]),
                ends_at=None if row[4] is None else _utc(row[4]),
                replaces=row[5],
            )
            for row in periods
        ],
        events=[
            EventView(
                event_id=row[0],
                stop_position=row[1],
                kind=row[2],
                occurred_at=_utc(row[3]),
                source=row[4],
                source_event_id=row[5],
                note=row[6],
                quantities=quantities.get(row[0], []),
            )
            for row in events
        ],
    )


async def list_trips(conn: RuntimeConnection) -> TripList:
    rows = await (
        await conn.execute("select id from gba.transport_trips order by id limit 100")
    ).fetchall()
    items = [await load_trip(conn, row[0]) for row in rows]
    return TripList(items=[item for item in items if item is not None])


def _check_legs(body: TripInput) -> None:
    for leg in body.legs:
        count = len(body.stops)
        if not (1 <= leg.pickup_stop < leg.delivery_stop <= count):
            raise TransportLegInvalidError(
                "A leg goes from a pickup to a later delivery of this trip"
            )
        if (
            body.stops[leg.pickup_stop - 1].kind != "pickup"
            or body.stops[leg.delivery_stop - 1].kind != "delivery"
        ):
            raise TransportLegInvalidError(
                "A leg goes from a pickup to a later delivery of this trip"
            )


async def save_trip(
    conn: RuntimeConnection,
    business: UUID,
    trip_id: UUID,
    *,
    user_id: UUID,
    actor: str,
    key: str,
    body: TripInput,
) -> TripView:
    """Replace a planned trip's stops and legs whole, never over-planning a load (decision 4)."""
    await require_transport(conn, business)
    scope = IdempotencyScope(business, actor, "transport.trip", key)
    fingerprint = _fingerprint(trip_id, body)
    stored = await idempotency.claim(conn, scope, fingerprint)
    if stored is not None:
        if stored.request_hash != fingerprint:
            raise IdempotencyKeyReusedError("Key was used for another request")
        view = await load_trip(conn, trip_id)
        if view is None:
            raise NotFoundError("Trip not found", trip_id=str(trip_id))
        return view
    _check_legs(body)
    zones = sorted({stop.time_zone for stop in body.stops})
    known = {
        row[0]
        for row in await (
            await conn.execute(
                "select name from pg_catalog.pg_timezone_names where name = any(%s)", (zones,)
            )
        ).fetchall()
    }
    if set(zones) - known:
        raise TransportTimeZoneError("Unknown time zone", time_zones=sorted(set(zones) - known))
    # Two plans of one load wait here; the second sees what the first planned (decision 3).
    load_ids = sorted({leg.load_id for leg in body.legs})
    loads = {
        row[0]: (int(row[1]), bool(row[2]))
        for row in await (
            await conn.execute(
                "select id, quantity, removed from gba.transport_loads where id = any(%s) "
                "order by id for update",
                (load_ids,),
            )
        ).fetchall()
    }
    missing = [str(load) for load in load_ids if load not in loads or loads[load][1]]
    if missing:
        raise InvalidReferenceError("Unknown load", field="load_id", load_ids=missing)
    current = await (
        await conn.execute(
            "select revision, status from gba.transport_trips where id = %s for update",
            (trip_id,),
        )
    ).fetchone()
    found = 0 if current is None else int(current[0])
    if found != body.expected_revision:
        raise TransportRevisionConflictError(
            "The trip changed since it was read; reload it", revision=found
        )
    if current is not None and current[1] != "planned":
        raise TransportTripStartedError("A started trip keeps its plan")
    if current is not None and await has_open_assignment(conn, trip_id):
        span = (
            min(stop.window_start for stop in body.stops),
            max(stop.window_end for stop in body.stops),
        )
        if await trip_span(conn, trip_id) != span:
            raise TransportTripAssignedError(
                "An assigned trip keeps its span; end its assignments first"
            )
    elsewhere = {
        row[0]: int(row[1])
        for row in await (
            await conn.execute(
                "select load_id, sum(quantity) from gba.transport_legs where load_id = any(%s) "
                "and trip_id <> %s group by load_id",
                (load_ids, trip_id),
            )
        ).fetchall()
    }
    wanted: dict[UUID, int] = {}
    for leg in body.legs:
        wanted[leg.load_id] = wanted.get(leg.load_id, 0) + leg.quantity
    for load_id, quantity in wanted.items():
        if elsewhere.get(load_id, 0) + quantity > loads[load_id][0]:
            raise TransportLoadOverplannedError(
                "A load is never planned beyond its quantity",
                load_id=str(load_id),
                quantity=loads[load_id][0],
                planned_elsewhere=elsewhere.get(load_id, 0),
            )
    try:
        async with module_writes(TRANSPORT_MODULE), conn.transaction():
            if current is None:
                await conn.execute(
                    "insert into gba.transport_trips (tenant_id, id, location_id, reference, "
                    "revision, created_by) values (%s, %s, %s, %s, 1, %s)",
                    (business, trip_id, body.location_id, body.reference, user_id),
                )
            else:
                await conn.execute(
                    "update gba.transport_trips set reference = %s, revision = revision + 1, "
                    "updated_at = clock_timestamp() where id = %s",
                    (body.reference, trip_id),
                )
                await conn.execute("delete from gba.transport_legs where trip_id = %s", (trip_id,))
                await conn.execute("delete from gba.transport_stops where trip_id = %s", (trip_id,))
            for position, stop in enumerate(body.stops, start=1):
                await conn.execute(
                    "insert into gba.transport_stops (tenant_id, trip_id, position, kind, place, "
                    "time_zone, window_start, window_end) values (%s, %s, %s, %s, %s, %s, %s, %s)",
                    (
                        business,
                        trip_id,
                        position,
                        stop.kind,
                        stop.place,
                        stop.time_zone,
                        stop.window_start,
                        stop.window_end,
                    ),
                )
            for position, leg in enumerate(body.legs, start=1):
                await conn.execute(
                    "insert into gba.transport_legs (tenant_id, trip_id, position, load_id, "
                    "quantity, pickup_stop, delivery_stop) values (%s, %s, %s, %s, %s, %s, %s)",
                    (
                        business,
                        trip_id,
                        position,
                        leg.load_id,
                        leg.quantity,
                        leg.pickup_stop,
                        leg.delivery_stop,
                    ),
                )
    except UniqueViolation as exc:
        raise TransportReferenceTakenError("Another trip has this reference") from exc
    except ForeignKeyViolation as exc:
        raise InvalidReferenceError("Unknown branch", field="location_id") from exc
    view = await load_trip(conn, trip_id)
    assert view is not None  # noqa: S101 - saved above
    await idempotency.complete(conn, scope, 200, {"trip_id": str(trip_id)})
    return view
