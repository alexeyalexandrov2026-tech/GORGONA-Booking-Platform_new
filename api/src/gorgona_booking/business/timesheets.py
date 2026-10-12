"""Actual-time commands reuse staff identity, SQL guards, receipts and audit."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Any
from uuid import UUID

import psycopg

from gorgona_booking.booking.idempotency import IdempotencyScope
from gorgona_booking.business import commands, workforce
from gorgona_booking.business.module_gate import module_writes
from gorgona_booking.business.timesheet_contracts import (
    BreakPeriod,
    ClockCommand,
    ClockInInput,
    CorrectionCommand,
    DecisionCommand,
    EffectiveTime,
    TimeCommand,
    TimeHistory,
    TimeList,
    TimeView,
    microseconds,
)
from gorgona_booking.business.workforce_contracts import WorkforceReceipt
from gorgona_booking.db.pool import RuntimeConnection
from gorgona_booking.errors import InvalidReferenceError, NotFoundError
from gorgona_booking.tenancy.authorization import PermissionDeniedError

_SELECT = (
    "select e.id,e.profile_id,e.user_id,e.location_id,e.shift_id,e.shift_revision,"
    "v.revision,v.action,v.status,v.starts_at,v.ends_at,v.break_starts,v.break_ends,"
    "v.break_started_at,v.reason,v.created_by,v.created_at,v.self_approved,"
    "(e.shift_id is null or v.starts_at<e.shift_starts_at or v.starts_at>=e.shift_ends_at),"
    "a.revision,a.starts_at,a.ends_at,a.break_starts,a.break_ends,"
    "a.created_by,a.created_at,a.self_approved,"
    "(e.shift_id is null or a.starts_at<e.shift_starts_at or a.starts_at>=e.shift_ends_at) "
    "from gba.time_entries e "
    "join lateral (select * from gba.time_entry_revisions where tenant_id=e.tenant_id "
    "and entry_id=e.id and (%s::integer is null or revision=%s) "
    "order by revision desc limit 1) v on true "
    "left join lateral (select * from gba.time_entry_revisions where tenant_id=e.tenant_id "
    "and entry_id=e.id and action='approve' and revision<=v.revision "
    "order by revision desc limit 1) a on true where e.tenant_id=%s "
)


def _breaks(starts: list[datetime], ends: list[datetime]) -> tuple[BreakPeriod, ...]:
    return tuple(
        BreakPeriod(starts_at=start, ends_at=end) for start, end in zip(starts, ends, strict=True)
    )


def _worked(start: datetime, end: datetime, periods: tuple[BreakPeriod, ...]) -> int:
    return microseconds(start, end) - sum(microseconds(p.starts_at, p.ends_at) for p in periods)


def _view(business: UUID, row: tuple[Any, ...]) -> TimeView:
    periods = _breaks(row[11], row[12])
    effective = None
    if row[19] is not None:
        approved_breaks = _breaks(row[22], row[23])
        effective = EffectiveTime(
            revision=row[19],
            starts_at=row[20],
            ends_at=row[21],
            breaks=approved_breaks,
            worked_microseconds=_worked(row[20], row[21], approved_breaks),
            approved_by=row[24],
            approved_at=row[25],
            self_approved=row[26],
            out_of_schedule=row[27],
        )
    return TimeView(
        business_id=business,
        entry_id=row[0],
        staff_profile_id=row[1],
        user_id=row[2],
        location_id=row[3],
        shift_id=row[4],
        expected_shift_revision=row[5],
        revision=row[6],
        action=row[7],
        status=row[8],
        starts_at=row[9],
        ends_at=row[10],
        breaks=periods,
        break_started_at=row[13],
        reason=row[14],
        created_by=row[15],
        created_at=row[16],
        self_approved=row[17],
        out_of_schedule=row[18],
        worked_microseconds=_worked(row[9], row[10], periods) if row[10] is not None else None,
        effective=effective,
    )


@asynccontextmanager
async def _writes(
    conn: RuntimeConnection, business: UUID, closing: bool = False
) -> AsyncIterator[None]:
    if not closing:
        await workforce.require_workforce(conn, business)
    try:
        async with conn.transaction(), module_writes("workforce"):
            yield
            await conn.execute("set constraints all immediate")
            await conn.execute("set constraints all deferred")
    except psycopg.errors.InsufficientPrivilege as exc:
        raise PermissionDeniedError("This timesheet action is outside your permissions") from exc
    except (
        psycopg.errors.ExclusionViolation,
        psycopg.errors.UniqueViolation,
        psycopg.errors.SerializationFailure,
    ) as exc:
        raise workforce.WorkforceConflictError(
            "The employee time entry conflicts or has changed"
        ) from exc
    except psycopg.errors.ForeignKeyViolation as exc:
        raise InvalidReferenceError("A time entry reference is unavailable") from exc
    except psycopg.DatabaseError as exc:
        if exc.sqlstate == "GBW01":
            raise workforce.WorkforceConflictError(
                "The time entry revision or clock state has changed"
            ) from exc
        if exc.sqlstate == "23514":
            raise InvalidReferenceError("The time interval or derived state is invalid") from exc
        raise


async def load(
    conn: RuntimeConnection,
    business: UUID,
    entry: UUID,
    revision: int | None = None,
    participant: UUID | None = None,
) -> TimeView:
    row = await (
        await conn.execute(
            _SELECT + "and e.id=%s and (%s::uuid is null or e.user_id=%s)",
            (revision, revision, business, entry, participant, participant),
        )
    ).fetchone()
    if row is None:
        raise NotFoundError("Time entry not found")
    return _view(business, row)


async def clock_in(
    conn: RuntimeConnection,
    business: UUID,
    entry: UUID,
    user: UUID,
    actor: str,
    key: str,
    body: ClockInInput,
) -> TimeView:
    async with _writes(conn, business):
        scope = IdempotencyScope(business, actor, "workforce.time.clock_in", key)
        receipt = await commands.claim(
            conn,
            scope,
            commands.fingerprint({"id": str(entry), **body.model_dump(mode="json")}),
            WorkforceReceipt,
        )
        if receipt is not None:
            return await load(conn, business, receipt.subject_id, receipt.revision, user)
        await conn.execute(
            "insert into gba.time_entries "
            "(tenant_id,id,profile_id,shift_id,shift_revision,starts_at,created_by) "
            "values (%s,%s,%s,%s,%s,%s,%s)",
            (
                business,
                entry,
                body.staff_profile_id,
                body.shift_id,
                body.expected_shift_revision,
                body.starts_at,
                user,
            ),
        )
        await workforce._finish(
            conn,
            business,
            actor,
            "time.clock_in",
            scope,
            WorkforceReceipt(subject_id=entry, revision=1),
        )
        return await load(conn, business, entry, 1, user)


async def event(
    conn: RuntimeConnection,
    business: UUID,
    entry: UUID,
    user: UUID,
    actor: str,
    key: str,
    body: TimeCommand,
    participant: UUID | None,
) -> TimeView:
    async with _writes(conn, business, closing=body.action == "clock_out"):
        await load(conn, business, entry, participant=participant)
        scope = IdempotencyScope(business, actor, "workforce.time.event", key)
        receipt = await commands.claim(
            conn,
            scope,
            commands.fingerprint({"id": str(entry), **body.model_dump(mode="json")}),
            WorkforceReceipt,
        )
        if receipt is not None:
            return await load(conn, business, receipt.subject_id, receipt.revision, participant)
        revision = body.expected_revision + 1
        correction = body if isinstance(body, CorrectionCommand) else None
        decision = body if isinstance(body, DecisionCommand) else None
        await conn.execute(
            "insert into gba.time_entry_revisions "
            "(tenant_id,entry_id,revision,action,occurred_at,starts_at,ends_at,"
            "break_starts,break_ends,reason,created_by) "
            "values (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
            (
                business,
                entry,
                revision,
                body.action,
                body.at if isinstance(body, ClockCommand) else None,
                correction.starts_at if correction else None,
                correction.ends_at if correction else None,
                [p.starts_at for p in correction.breaks] if correction else None,
                [p.ends_at for p in correction.breaks] if correction else None,
                correction.reason if correction else decision.reason if decision else None,
                user,
            ),
        )
        await workforce._finish(
            conn,
            business,
            actor,
            "time." + body.action,
            scope,
            WorkforceReceipt(subject_id=entry, revision=revision),
        )
        return await load(conn, business, entry, revision, participant)


async def list_entries(
    conn: RuntimeConnection,
    business: UUID,
    participant: UUID | None,
    after: UUID | None,
    limit: int,
    open_only: bool,
) -> TimeList:
    rows = await (
        await conn.execute(
            _SELECT + "and (%s::uuid is null or e.user_id=%s) "
            "and (%s::uuid is null or e.id>%s) and (not %s or v.status='open') "
            "order by e.id limit %s",
            (None, None, business, participant, participant, after, after, open_only, limit + 1),
        )
    ).fetchall()
    items = tuple(_view(business, row) for row in rows[:limit])
    return TimeList(items=items, next_cursor=items[-1].entry_id if len(rows) > limit else None)


async def history(
    conn: RuntimeConnection,
    business: UUID,
    entry: UUID,
    participant: UUID | None,
    after: int,
    limit: int,
) -> TimeHistory:
    await load(conn, business, entry, participant=participant)
    # Reuse the as-of projection in one bulk query rather than load every event separately.
    query = _SELECT.replace(
        "and entry_id=e.id and (%s::integer is null or revision=%s) order by revision desc limit 1",
        "and entry_id=e.id and revision>%s order by revision limit %s",
    )
    rows = await (
        await conn.execute(
            query + "and e.id=%s order by v.revision", (after, limit + 1, business, entry)
        )
    ).fetchall()
    items = tuple(_view(business, row) for row in rows[:limit])
    return TimeHistory(items=items, next_revision=items[-1].revision if len(rows) > limit else None)
