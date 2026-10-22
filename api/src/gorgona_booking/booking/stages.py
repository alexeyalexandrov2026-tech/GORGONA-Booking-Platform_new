"""L2a: stage-by-stage occupancy (package L, design docs/plan/PACKAGE_L2_DESIGN_2026-10-22.md).

Each stage of a staged variant occupies the resources of its kinds for its minutes; consecutive
stages on one resource join into one interval and a gap starts another, so the specialist is free
while a colour develops and the chair stays held. A variant without stages never comes here.
"""

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta
from uuid import UUID

from gorgona_booking.booking import repository as repo
from gorgona_booking.booking.models import SlotConflictError, StageResourceError
from gorgona_booking.catalog.models import StageSpec
from gorgona_booking.db.pool import RuntimeConnection

# The resource kind that serves each stage kind; the specialist is always the request's resource.
RESOURCE_KIND = {"specialist": "artist", "chair": "chair", "room": "room", "equipment": "equipment"}

type Span = tuple[int, int]  # minutes from the start of the visit, half-open


def stage_spans(stages: Sequence[StageSpec]) -> dict[str, list[Span]]:
    """Minutes each stage kind is occupied, consecutive stages joined (pure)."""
    spans: dict[str, list[Span]] = {}
    offset = 0
    for stage in stages:
        end = offset + stage.minutes
        for kind in stage.resources:
            own = spans.setdefault(kind, [])
            if own and own[-1][1] == offset:
                own[-1] = (own[-1][0], end)
            else:
                own.append((offset, end))
        offset = end
    return spans


@dataclass(frozen=True, slots=True)
class Allocation:
    resource_id: UUID
    starts_at: datetime
    ends_at: datetime


def _at(start: datetime, span: Span) -> tuple[datetime, datetime]:
    return start + timedelta(minutes=span[0]), start + timedelta(minutes=span[1])


async def _resource(conn: RuntimeConnection, resource_id: UUID) -> tuple[str, UUID, bool] | None:
    row = await (
        await conn.execute(
            "select kind, location_id, is_active from gba.resources where id = %s", (resource_id,)
        )
    ).fetchone()
    return None if row is None else (str(row[0]), row[1], bool(row[2]))


async def _require(
    conn: RuntimeConnection, resource_id: UUID, kind: str, location_id: UUID | None
) -> UUID:
    found = await _resource(conn, resource_id)
    expected = RESOURCE_KIND[kind]
    if found is None or found[0] != expected or not found[2]:
        raise StageResourceError(f"The {kind} must be an active {expected} resource", kind=kind)
    if location_id is not None and found[1] != location_id:
        raise StageResourceError(f"The {kind} belongs to another branch", kind=kind)
    return UUID(str(found[1]))


async def candidates(conn: RuntimeConnection, location_id: UUID, kind: str) -> list[UUID]:
    rows = await (
        await conn.execute(
            "select id from gba.resources where location_id = %s and kind = %s and is_active "
            "order by id",
            (location_id, RESOURCE_KIND[kind]),
        )
    ).fetchall()
    return [UUID(str(r[0])) for r in rows]


async def _free(
    conn: RuntimeConnection, resource_id: UUID, intervals: Iterable[tuple[datetime, datetime]]
) -> bool:
    for starts_at, ends_at in intervals:
        row = await (
            await conn.execute(
                "select exists (select 1 from gba.resource_allocations where resource_id = %s "
                "and state in ('held', 'confirmed') and during && tstzrange(%s, %s, '[)')) "
                "or exists (select 1 from gba.resource_blocks where resource_id = %s "
                "and starts_at < %s and ends_at > %s)",
                (resource_id, starts_at, ends_at, resource_id, ends_at, starts_at),
            )
        ).fetchone()
        if row is None or row[0]:
            return False
    return True


async def plan(
    conn: RuntimeConnection,
    tenant_id: UUID,
    *,
    specialist_id: UUID,
    stages: Sequence[StageSpec],
    starts_at: datetime,
    named: Sequence[tuple[str, UUID]],
    preferred: Sequence[UUID] = (),
) -> tuple[UUID, list[Allocation]]:
    """Validate, lock and choose the resources of a staged visit; returns (branch, allocations).

    Every resource that may be used is locked in id order before any choice, so two visits never
    wait on each other in opposite order; the exclusion constraint stays the final arbiter. The
    caller sets the hold-expiry audit context first: stale holds on these intervals expire here.
    """
    spans = stage_spans(stages)
    location_id = await _require(conn, specialist_id, "specialist", None)
    chosen: dict[str, UUID] = {"specialist": specialist_id}
    for kind, resource_id in named:
        if kind not in RESOURCE_KIND or kind == "specialist" or kind not in spans:
            raise StageResourceError(f"This service has no {kind} stage", kind=kind)
        if kind in chosen:
            raise StageResourceError(f"The {kind} is named twice", kind=kind)
        await _require(conn, resource_id, kind, location_id)
        chosen[kind] = resource_id
    pools = {
        kind: await candidates(conn, location_id, kind) for kind in spans if kind not in chosen
    }
    for resource_id in sorted({*chosen.values(), *(r for pool in pools.values() for r in pool)}):
        await repo.lock_resource_schedule(conn, tenant_id, resource_id)
    for kind, pool in pools.items():
        intervals = [_at(starts_at, span) for span in spans[kind]]
        ordered = [r for r in preferred if r in pool] + [r for r in pool if r not in preferred]
        for resource_id in ordered:
            for interval in intervals:
                await repo.expire_stale_holds_overlapping(conn, resource_id, *interval)
            if await _free(conn, resource_id, intervals):
                chosen[kind] = resource_id
                break
        else:
            raise SlotConflictError(f"No {kind} is free for this visit", kind=kind)
    for kind in ("specialist", *(k for k, _ in named)):
        for interval in (_at(starts_at, span) for span in spans[kind]):
            await repo.expire_stale_holds_overlapping(conn, chosen[kind], *interval)
    allocations = [
        Allocation(chosen[kind], *_at(starts_at, span))
        for kind in sorted(spans)
        for span in spans[kind]
    ]
    return location_id, allocations
