"""R3b (package R, RENT-01): rental unit blocks on the shared occupancy.

docs/plan/PACKAGE_R3B_DESIGN_2026-11-03.md. A block takes a unit out of service for a period
through a confirmed hold, so it never overlaps an assignment; it counts in availability and is
checked under the class lock like bookings. A block is released once, with its hold.
"""

from datetime import UTC, datetime, timedelta
from typing import Annotated, Any, Literal, Self
from uuid import UUID, uuid7

from psycopg.errors import CheckViolation, ExclusionViolation, UniqueViolation
from pydantic import AfterValidator, AwareDatetime, BaseModel, Field, model_validator

from gorgona_booking.booking import idempotency
from gorgona_booking.booking.idempotency import IdempotencyScope
from gorgona_booking.booking.models import IdempotencyKeyReusedError
from gorgona_booking.business.module_gate import RENTAL_MODULE, module_writes
from gorgona_booking.business.rental import (
    RentalUnitRetiredError,
    Strict,
    fingerprint,
    require_rental,
)
from gorgona_booking.business.rental_assignments import RentalUnitBusyError
from gorgona_booking.business.rental_bookings import RentalUnavailableError
from gorgona_booking.db.pool import RuntimeConnection
from gorgona_booking.errors import ConflictError, NotFoundError

LONGEST = timedelta(days=366)


class RentalBlockReleasedError(ConflictError):
    code = "RENTAL_BLOCK_RELEASED"


def _text(value: str) -> str:
    if not value.strip():
        raise ValueError("text that is not only blanks")
    return value


Reason = Annotated[str, AfterValidator(_text), Field(min_length=1, max_length=500)]


class BlockInput(Strict):
    schema_version: Literal[1]
    kind: Literal["maintenance", "repair", "other"]
    reason: Reason
    starts_at: AwareDatetime
    ends_at: AwareDatetime

    @model_validator(mode="after")
    def _period(self) -> Self:
        if self.ends_at <= self.starts_at or self.ends_at - self.starts_at > LONGEST:
            raise ValueError("a period ends after it starts and lasts at most 366 days")
        return self


class BlockReleaseInput(Strict):
    schema_version: Literal[1]
    reason: Reason


class BlockReleaseView(BaseModel):
    reason: str
    released_at: datetime


class BlockView(BaseModel):
    block_id: UUID
    unit_id: UUID
    kind: str
    reason: str
    starts_at: datetime
    ends_at: datetime
    created_at: datetime
    release: BlockReleaseView | None


class BlockList(BaseModel):
    items: list[BlockView]


_SELECT = (
    "select b.id, b.unit_id, b.kind, b.reason, b.starts_at, b.ends_at, b.created_at, l.reason, "
    "l.released_at from gba.rental_unit_blocks b left join gba.rental_unit_block_releases l "
    "on l.tenant_id = b.tenant_id and l.block_id = b.id "
)


def _view(row: Any) -> BlockView:
    return BlockView(
        block_id=row[0],
        unit_id=row[1],
        kind=row[2],
        reason=row[3],
        starts_at=row[4].astimezone(UTC),
        ends_at=row[5].astimezone(UTC),
        created_at=row[6].astimezone(UTC),
        release=None
        if row[7] is None
        else BlockReleaseView(reason=row[7], released_at=row[8].astimezone(UTC)),
    )


async def _load(conn: RuntimeConnection, block_id: UUID) -> BlockView | None:
    row = await (await conn.execute(_SELECT + "where b.id = %s", (block_id,))).fetchone()
    return None if row is None else _view(row)


async def _unit(conn: RuntimeConnection, unit_id: UUID) -> Any:
    unit = await (
        await conn.execute(
            "select class_id, location_id, state, resource_id from gba.rental_units where id = %s",
            (unit_id,),
        )
    ).fetchone()
    if unit is None:
        raise NotFoundError("Unit not found", unit_id=str(unit_id))
    return unit


async def list_blocks(conn: RuntimeConnection, unit_id: UUID) -> BlockList:
    await _unit(conn, unit_id)
    rows = await (
        await conn.execute(_SELECT + "where b.unit_id = %s order by b.created_at", (unit_id,))
    ).fetchall()
    return BlockList(items=[_view(row) for row in rows])


async def create_block(
    conn: RuntimeConnection,
    business: UUID,
    unit_id: UUID,
    *,
    user_id: UUID,
    actor: str,
    key: str,
    body: BlockInput,
) -> BlockView:
    """Take a unit out of service for a period, if every booking keeps a unit (decisions 1-2)."""
    await require_rental(conn, business)
    scope = IdempotencyScope(business, actor, "rental.block", key)
    request = fingerprint(str(unit_id), body)
    stored = await idempotency.claim(conn, scope, request)
    if stored is not None:
        if stored.request_hash != request:
            raise IdempotencyKeyReusedError("Key was used for another request")
        view = await _load(conn, UUID(str(stored.body["block_id"])))
        if view is None:
            raise NotFoundError("Block not found")
        return view
    unit = await _unit(conn, unit_id)
    await conn.execute("select 1 from gba.rental_classes where id = %s for update", (unit[0],))
    await conn.execute("select 1 from gba.rental_units where id = %s for update", (unit_id,))
    if unit[2] != "active":
        raise RentalUnitRetiredError("A retired unit is not blocked")
    count = await (
        await conn.execute(
            "select count(*) from gba.rental_units where class_id = %s and location_id = %s "
            "and state = 'active'",
            (unit[0], unit[1]),
        )
    ).fetchone()
    peak = await (
        await conn.execute(
            "select gba.rental_booking_peak(%s, %s, %s, %s, %s)",
            (business, unit[0], unit[1], body.starts_at, body.ends_at),
        )
    ).fetchone()
    units = int(count[0]) if count else 0
    if (int(peak[0]) if peak else 0) + 1 > units:
        raise RentalUnavailableError(
            "The block would leave a booking of the class without a unit", units=units
        )
    block_id = uuid7()
    try:
        async with module_writes(RENTAL_MODULE), conn.transaction():
            await conn.execute(
                "insert into gba.rental_unit_blocks (tenant_id, id, unit_id, kind, reason, "
                "starts_at, ends_at, created_by) values (%s, %s, %s, %s, %s, %s, %s, %s)",
                (
                    business,
                    block_id,
                    unit_id,
                    body.kind,
                    body.reason,
                    body.starts_at,
                    body.ends_at,
                    user_id,
                ),
            )
            await conn.execute(
                "insert into gba.resource_allocations (tenant_id, resource_id, source_kind, "
                "source_id, during, state) values (%s, %s, 'rental_block', %s, "
                "tstzrange(%s, %s, '[)'), 'confirmed')",
                (business, unit[3], block_id, body.starts_at, body.ends_at),
            )
            await conn.execute("set constraints gba.rental_unit_blocks_hold immediate")
    except ExclusionViolation as exc:
        raise RentalUnitBusyError(
            "The unit is held for an overlapping assignment or block", unit_id=str(unit_id)
        ) from exc
    except CheckViolation as exc:
        if exc.diag.constraint_name == "rental_unit_blocks_availability_check":
            raise RentalUnavailableError("The block would leave a booking without a unit") from exc
        raise
    view = await _load(conn, block_id)
    assert view is not None  # noqa: S101 - saved above
    await idempotency.complete(conn, scope, 200, {"block_id": str(block_id)})
    return view


async def release_block(
    conn: RuntimeConnection,
    business: UUID,
    unit_id: UUID,
    block_id: UUID,
    *,
    user_id: UUID,
    actor: str,
    key: str,
    body: BlockReleaseInput,
) -> BlockView:
    """Release a block once, with its hold (decision 1)."""
    await require_rental(conn, business)
    scope = IdempotencyScope(business, actor, "rental.block_release", key)
    request = fingerprint(str(block_id), body)
    stored = await idempotency.claim(conn, scope, request)
    if stored is not None:
        if stored.request_hash != request:
            raise IdempotencyKeyReusedError("Key was used for another request")
        view = await _load(conn, block_id)
        if view is None:
            raise NotFoundError("Block not found", block_id=str(block_id))
        return view
    await _unit(conn, unit_id)
    await conn.execute("select 1 from gba.rental_units where id = %s for update", (unit_id,))
    current = await _load(conn, block_id)
    if current is None or current.unit_id != unit_id:
        raise NotFoundError("Block not found", block_id=str(block_id))
    if current.release is not None:
        raise RentalBlockReleasedError("The block is already released")
    try:
        async with module_writes(RENTAL_MODULE), conn.transaction():
            await conn.execute(
                "insert into gba.rental_unit_block_releases (tenant_id, block_id, reason, "
                "released_by) values (%s, %s, %s, %s)",
                (business, block_id, body.reason, user_id),
            )
            await conn.execute(
                "update gba.resource_allocations set state = 'released' "
                "where source_kind = 'rental_block' and source_id = %s",
                (block_id,),
            )
    except UniqueViolation as exc:
        raise RentalBlockReleasedError("The block is already released") from exc
    view = await _load(conn, block_id)
    assert view is not None  # noqa: S101 - saved above
    await idempotency.complete(conn, scope, 200, {"block_id": str(block_id)})
    return view
