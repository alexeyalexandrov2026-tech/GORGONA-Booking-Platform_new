"""M3 (package M, TMS-01 and TMS-03): trip stop events and partial delivery (ADR-0030).

An event is an insert-only fact with its source and the source's own event id; repeating it with the
same content changes nothing, with other content it is refused. Loading and delivery events name
quantities per leg; a leg never loads more than planned nor resolves more than it loaded.
"""

import unicodedata
from datetime import datetime
from typing import Any, Literal, Self
from uuid import UUID, uuid7

from psycopg.errors import UniqueViolation
from pydantic import AwareDatetime, Field, model_validator

from gorgona_booking.booking import idempotency
from gorgona_booking.booking.idempotency import IdempotencyScope
from gorgona_booking.booking.models import IdempotencyKeyReusedError
from gorgona_booking.business import transport_carrier_companies as carriers
from gorgona_booking.business.module_gate import TRANSPORT_MODULE, module_writes
from gorgona_booking.business.transport import (
    TripView,
    _fingerprint,
    _Strict,
    load_trip,
    require_transport,
)
from gorgona_booking.db.pool import RuntimeConnection
from gorgona_booking.errors import ConflictError, DomainError, NotFoundError
from gorgona_booking.tenancy.authorization import PermissionDeniedError

QUANTITY_KINDS = frozenset({"loaded", "delivered", "refused", "damaged"})


class TransportEventInvalidError(DomainError):
    code = "TRANSPORT_EVENT_INVALID"


class TransportEventConflictError(ConflictError):
    code = "TRANSPORT_EVENT_CONFLICT"


class TransportQuantityExceededError(ConflictError):
    code = "TRANSPORT_QUANTITY_EXCEEDED"


def _plain(value: str) -> bool:
    return not any(unicodedata.category(ch) == "Cc" for ch in value)


class QuantityInput(_Strict):
    leg_position: int = Field(ge=1, le=100)
    quantity: int = Field(ge=1, le=1_000_000)


class EventInput(_Strict):
    schema_version: Literal[1]
    source: str = Field(pattern=r"^[a-z][a-z0-9_.-]{0,31}$")
    source_event_id: str = Field(min_length=1, max_length=200)
    stop_position: int = Field(ge=1, le=50)
    kind: Literal["arrived", "departed", "loaded", "delivered", "refused", "damaged", "exception"]
    occurred_at: AwareDatetime
    note: str | None = Field(default=None, max_length=500)
    quantities: list[QuantityInput] = Field(default_factory=list, max_length=100)

    @model_validator(mode="after")
    def _shape(self) -> Self:
        if not self.source_event_id.strip() or not _plain(self.source_event_id):
            raise ValueError("a source event id has visible text and no control characters")
        if self.note is not None and not _plain(self.note):
            raise ValueError("a note has no control characters")
        if len({q.leg_position for q in self.quantities}) != len(self.quantities):
            raise ValueError("each leg is listed once")
        return self


def _same(row: tuple[Any, ...], lines: dict[int, int], trip_id: UUID, body: EventInput) -> bool:
    """Does the recorded fact say exactly what the repeat says (decision 2)?"""
    occurred: datetime = row[4]
    return (row[1], row[2], row[3], occurred, row[5]) == (
        trip_id,
        body.stop_position,
        body.kind,
        body.occurred_at,
        body.note,
    ) and lines == {q.leg_position: q.quantity for q in body.quantities}


async def _tendered_only(
    conn: RuntimeConnection, trip_id: UUID, party: UUID, body: EventInput
) -> None:
    """Refuse a stop or a quantity outside the legs tendered to this carrier and accepted."""
    legs = await carriers.tendered_legs(conn, trip_id, party)
    stops = await (
        await conn.execute(
            "select pickup_stop, delivery_stop from gba.transport_legs "
            "where trip_id = %s and position = any(%s)",
            (trip_id, sorted(legs)),
        )
    ).fetchall()
    at_stop = any(body.stop_position in (row[0], row[1]) for row in stops)
    if not at_stop or any(q.leg_position not in legs for q in body.quantities):
        raise PermissionDeniedError("Your company records events only on its tendered legs")


async def _view(conn: RuntimeConnection, trip_id: UUID) -> TripView:
    view = await load_trip(conn, trip_id)
    if view is None:
        raise NotFoundError("Trip not found", trip_id=str(trip_id))
    return view


async def record_event(
    conn: RuntimeConnection,
    business: UUID,
    trip_id: UUID,
    *,
    user_id: UUID,
    actor: str,
    key: str,
    body: EventInput,
    servicer: UUID | None = None,
) -> TripView:
    """Record one stop event; a repeat of its source event id changes nothing (ADR-0030).

    N4: a delegate of a linked carrier company records only on its accepted tendered legs.
    """
    await require_transport(conn, business)
    if servicer is not None and (party := await carriers.linked_carrier(conn, servicer)):
        await _tendered_only(conn, trip_id, party, body)
    scope = IdempotencyScope(business, actor, "transport.event", key)
    fingerprint = _fingerprint(trip_id, body)
    stored = await idempotency.claim(conn, scope, fingerprint)
    if stored is not None:
        if stored.request_hash != fingerprint:
            raise IdempotencyKeyReusedError("Key was used for another request")
        return await _view(conn, trip_id)
    # Every event of one trip waits here first, so totals are read after the previous event.
    trip = await (
        await conn.execute(
            "select status from gba.transport_trips where id = %s for update", (trip_id,)
        )
    ).fetchone()
    if trip is None:
        raise NotFoundError("Trip not found", trip_id=str(trip_id))
    recorded = await (
        await conn.execute(
            "select id, trip_id, stop_position, kind, occurred_at, note "
            "from gba.transport_stop_events where source = %s and source_event_id = %s",
            (body.source, body.source_event_id),
        )
    ).fetchone()
    if recorded is not None:
        lines = {
            row[0]: row[1]
            for row in await (
                await conn.execute(
                    "select leg_position, quantity from gba.transport_event_quantities "
                    "where event_id = %s",
                    (recorded[0],),
                )
            ).fetchall()
        }
        if not _same(recorded, lines, trip_id, body):
            raise TransportEventConflictError(
                "This source event id was recorded with other content",
                source=body.source,
                source_event_id=body.source_event_id,
            )
        await idempotency.complete(conn, scope, 200, {"trip_id": str(trip_id)})
        return await _view(conn, trip_id)
    stop = await (
        await conn.execute(
            "select 1 from gba.transport_stops where trip_id = %s and position = %s",
            (trip_id, body.stop_position),
        )
    ).fetchone()
    if stop is None:
        raise TransportEventInvalidError("The trip has no such stop", stop=body.stop_position)
    if (body.kind in QUANTITY_KINDS) != bool(body.quantities):
        raise TransportEventInvalidError(
            "Loading and delivery events name their quantities, other events none"
        )
    legs = {
        int(row[0]): (int(row[1]), int(row[2]), int(row[3]))
        for row in await (
            await conn.execute(
                "select position, quantity, pickup_stop, delivery_stop "
                "from gba.transport_legs where trip_id = %s",
                (trip_id,),
            )
        ).fetchall()
    }
    for line in body.quantities:
        leg = legs.get(line.leg_position)
        at = None if leg is None else (leg[1] if body.kind == "loaded" else leg[2])
        if at != body.stop_position:
            raise TransportEventInvalidError(
                "A quantity names a leg loaded or delivered at this stop", leg=line.leg_position
            )
    totals: dict[int, tuple[int, int]] = {
        int(row[0]): (int(row[1]), int(row[2]))
        for row in await (
            await conn.execute(
                "select q.leg_position, "
                "coalesce(sum(q.quantity) filter (where e.kind = 'loaded'), 0), "
                "coalesce(sum(q.quantity) filter (where e.kind <> 'loaded'), 0) "
                "from gba.transport_event_quantities q join gba.transport_stop_events e "
                "on e.tenant_id = q.tenant_id and e.id = q.event_id "
                "where q.trip_id = %s group by q.leg_position",
                (trip_id,),
            )
        ).fetchall()
    }
    for line in body.quantities:
        loaded, resolved = totals.get(line.leg_position, (0, 0))
        if body.kind == "loaded":
            exceeded = loaded + line.quantity > legs[line.leg_position][0]
        else:
            exceeded = resolved + line.quantity > loaded
        if exceeded:
            raise TransportQuantityExceededError(
                "A leg never loads more than planned nor resolves more than it loaded",
                leg=line.leg_position,
                planned=legs[line.leg_position][0],
                loaded=loaded,
                resolved=resolved,
            )
    event_id = uuid7()
    try:
        async with module_writes(TRANSPORT_MODULE), conn.transaction():
            await conn.execute(
                "insert into gba.transport_stop_events (tenant_id, id, trip_id, stop_position, "
                "kind, occurred_at, source, source_event_id, note, recorded_by) "
                "values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
                (
                    business,
                    event_id,
                    trip_id,
                    body.stop_position,
                    body.kind,
                    body.occurred_at,
                    body.source,
                    body.source_event_id,
                    body.note,
                    user_id,
                ),
            )
            for line in body.quantities:
                await conn.execute(
                    "insert into gba.transport_event_quantities (tenant_id, event_id, trip_id, "
                    "leg_position, quantity) values (%s, %s, %s, %s, %s)",
                    (business, event_id, trip_id, line.leg_position, line.quantity),
                )
    except UniqueViolation as exc:
        raise TransportEventConflictError(
            "This source event id was recorded for another trip",
            source=body.source,
            source_event_id=body.source_event_id,
        ) from exc
    view = await _view(conn, trip_id)
    await idempotency.complete(conn, scope, 200, {"trip_id": str(trip_id)})
    return view
