"""I2 commands reuse workforce writes, receipts, audit and SQL application."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any
from uuid import UUID

import psycopg

from gorgona_booking.booking.idempotency import IdempotencyScope
from gorgona_booking.business import commands, workforce
from gorgona_booking.business.shift_change_contracts import (
    AppliedShift,
    ChangeEventInput,
    ChangeHistory,
    ChangeInput,
    ChangeList,
    ChangeView,
    ColleagueList,
    ColleagueView,
)
from gorgona_booking.business.workforce_contracts import WorkforceReceipt
from gorgona_booking.db.pool import RuntimeConnection
from gorgona_booking.errors import NotFoundError
from gorgona_booking.tenancy.authorization import PermissionDeniedError

_SELECT = (
    "select r.id,r.kind,r.location_id,r.other_location_id,r.shift_id,r.shift_revision,"
    "r.other_shift_id,r.other_shift_revision,r.from_profile_id,r.target_profile_id,"
    "r.proposed_by,r.recipient_user_id,e.revision,e.status,e.created_by,e.created_at "
    "from gba.shift_change_requests r "
    "join lateral (select revision,status,created_by,created_at from gba.shift_change_events "
    "where tenant_id=r.tenant_id and request_id=r.id "
    "and (%s::integer is null or revision=%s) order by revision desc limit 1) e on true "
    "where r.tenant_id=%s "
)


def _view(business: UUID, row: tuple[Any, ...]) -> ChangeView:
    applied: tuple[AppliedShift, ...] = ()
    if row[13] == "approved":
        values = [AppliedShift(shift_id=row[4], revision=row[5] + 1)]
        if row[6] is not None:
            values.append(AppliedShift(shift_id=row[6], revision=row[7] + 1))
        applied = tuple(sorted(values, key=lambda value: value.shift_id))
    return ChangeView(
        business_id=business,
        request_id=row[0],
        kind=row[1],
        location_id=row[2],
        other_location_id=row[3],
        shift_id=row[4],
        expected_shift_revision=row[5],
        other_shift_id=row[6],
        expected_other_shift_revision=row[7],
        from_profile_id=row[8],
        target_profile_id=row[9],
        proposed_by=row[10],
        recipient_user_id=row[11],
        revision=row[12],
        status=row[13],
        event_created_by=row[14],
        event_created_at=row[15],
        applied_shifts=applied,
    )


class ColleagueShiftsHiddenError(PermissionDeniedError):
    code = "COLLEAGUE_SHIFTS_HIDDEN"


async def shifts_visible(conn: RuntimeConnection, business: UUID, location: UUID) -> bool:
    """Whether staff of this branch may see colleagues' published shifts."""
    row = await (
        await conn.execute(
            "select colleague_shifts_visible from gba.work_location_setting_versions "
            "where tenant_id=%s and location_id=%s order by revision desc limit 1",
            (business, location),
        )
    ).fetchone()
    # No version means the default nobody has changed: visible.
    return True if row is None else bool(row[0])


@asynccontextmanager
async def _writes(conn: RuntimeConnection, business: UUID) -> AsyncIterator[None]:
    try:
        async with workforce._writes(conn, business):
            yield
    except psycopg.errors.InsufficientPrivilege as exc:
        raise PermissionDeniedError(
            "This change action is outside your workforce permissions"
        ) from exc


async def load(
    conn: RuntimeConnection,
    business: UUID,
    request: UUID,
    revision: int | None = None,
    participant: UUID | None = None,
) -> ChangeView:
    row = await (
        await conn.execute(
            _SELECT
            + "and r.id=%s and (%s::uuid is null or r.proposed_by=%s or r.recipient_user_id=%s)",
            (revision, revision, business, request, participant, participant, participant),
        )
    ).fetchone()
    if row is None:
        raise NotFoundError("Shift change not found")
    return _view(business, row)


async def propose(
    conn: RuntimeConnection,
    business: UUID,
    request: UUID,
    user: UUID,
    actor: str,
    key: str,
    body: ChangeInput,
) -> ChangeView:
    async with _writes(conn, business):
        scope = IdempotencyScope(business, actor, "workforce.change.propose", key)
        receipt = await commands.claim(
            conn,
            scope,
            commands.fingerprint({"id": str(request), **body.model_dump(mode="json")}),
            WorkforceReceipt,
        )
        if receipt is not None:
            return await load(conn, business, request, receipt.revision, user)
        if body.kind == "swap":
            # A swap names a colleague's shift. Where the branch hides those shifts the
            # swap is closed before anything is looked up, so every such request gets
            # one answer and a known shift id tells nothing about its holder.
            location = await home(conn, business, user)
            if location is None or not await shifts_visible(conn, business, location):
                raise ColleagueShiftsHiddenError("Your branch does not show colleagues' shifts")
        await conn.execute(
            "insert into gba.shift_change_requests (tenant_id,id,kind,shift_id,shift_revision,"
            "other_shift_id,other_shift_revision,target_profile_id,proposed_by) "
            "values (%s,%s,%s,%s,%s,%s,%s,%s,%s)",
            (
                business,
                request,
                body.kind,
                body.shift_id,
                body.expected_shift_revision,
                body.other_shift_id,
                body.expected_other_shift_revision,
                body.target_profile_id,
                user,
            ),
        )
        await workforce._finish(
            conn,
            business,
            actor,
            "change.propose",
            scope,
            WorkforceReceipt(subject_id=request, revision=1),
        )
        return await load(conn, business, request, 1, user)


async def event(
    conn: RuntimeConnection,
    business: UUID,
    request: UUID,
    user: UUID,
    actor: str,
    key: str,
    body: ChangeEventInput,
    participant: UUID | None,
) -> ChangeView:
    async with _writes(conn, business):
        # Filter a self route by the trusted user's identity before any contents or
        # mutation are returned. Manager calls retain their authorized branch GUC.
        await load(conn, business, request, participant=participant)
        scope = IdempotencyScope(business, actor, "workforce.change.event", key)
        receipt = await commands.claim(
            conn,
            scope,
            commands.fingerprint({"id": str(request), **body.model_dump(mode="json")}),
            WorkforceReceipt,
        )
        if receipt is not None:
            return await load(conn, business, request, receipt.revision, participant)
        revision = body.expected_revision + 1
        await conn.execute(
            "insert into gba.shift_change_events (tenant_id,request_id,revision,action,created_by) "
            "values (%s,%s,%s,%s,%s)",
            (business, request, revision, body.action, user),
        )
        await workforce._finish(
            conn,
            business,
            actor,
            "change." + body.action,
            scope,
            WorkforceReceipt(subject_id=request, revision=revision),
        )
        return await load(conn, business, request, revision, participant)


async def list_requests(
    conn: RuntimeConnection,
    business: UUID,
    participant: UUID | None,
    after: UUID | None,
    limit: int,
) -> ChangeList:
    rows = await (
        await conn.execute(
            _SELECT + "and (%s::uuid is null or r.proposed_by=%s or r.recipient_user_id=%s) "
            "and (%s::uuid is null or r.id>%s) order by r.id limit %s",
            (None, None, business, participant, participant, participant, after, after, limit + 1),
        )
    ).fetchall()
    items = tuple(_view(business, row) for row in rows[:limit])
    return ChangeList(items=items, next_cursor=items[-1].request_id if len(rows) > limit else None)


async def history(
    conn: RuntimeConnection,
    business: UUID,
    request: UUID,
    participant: UUID | None,
    after: int,
    limit: int,
) -> ChangeHistory:
    await load(conn, business, request, participant=participant)
    # One bulk query returns immutable event revisions with the static head.
    rows = await (
        await conn.execute(
            "select r.id,r.kind,r.location_id,r.other_location_id,r.shift_id,r.shift_revision,"
            "r.other_shift_id,r.other_shift_revision,r.from_profile_id,r.target_profile_id,"
            "r.proposed_by,r.recipient_user_id,e.revision,e.status,e.created_by,e.created_at "
            "from gba.shift_change_requests r join gba.shift_change_events e "
            "on e.tenant_id=r.tenant_id and e.request_id=r.id "
            "where r.tenant_id=%s and r.id=%s and e.revision>%s order by e.revision limit %s",
            (business, request, after, limit + 1),
        )
    ).fetchall()
    items = tuple(_view(business, row) for row in rows[:limit])
    return ChangeHistory(
        items=items, next_revision=items[-1].revision if len(rows) > limit else None
    )


async def home(conn: RuntimeConnection, business: UUID, user: UUID) -> UUID | None:
    """The immutable staff home, including a same-home reinvitation before profiling.

    A current membership must still cover that home; a new branch membership is
    not permission to browse the old branch. No safe home closes new swaps.
    """
    row = await (
        await conn.execute(
            "select o.location_id from gba.staff_resource_owners o join gba.memberships m "
            "on m.tenant_id=o.tenant_id and m.user_id=o.user_id "
            "where o.tenant_id=%s and o.user_id=%s and m.status='active' "
            "and (m.location_id is null or m.location_id=o.location_id)",
            (business, user),
        )
    ).fetchone()
    return row[0] if row is not None else None


async def colleagues(
    conn: RuntimeConnection,
    business: UUID,
    user: UUID,
    after: UUID | None,
    limit: int,
) -> ColleagueList:
    location = await home(conn, business, user)
    rows = await (
        await conn.execute(
            "select p.id,u.display_name from gba.staff_profiles p join gba.memberships m "
            "on m.tenant_id=p.tenant_id and m.id=p.membership_id "
            "join gba.users u on u.id=p.user_id "
            "where p.tenant_id=%s and p.location_id=%s and m.status='active' and u.status='active' "
            "and (%s::uuid is null or p.id>%s) order by p.id limit %s",
            (business, location, after, after, limit + 1),
        )
    ).fetchall()
    items = tuple(ColleagueView(profile_id=row[0], display_name=row[1]) for row in rows[:limit])
    return ColleagueList(
        items=items, next_cursor=items[-1].profile_id if len(rows) > limit else None
    )
