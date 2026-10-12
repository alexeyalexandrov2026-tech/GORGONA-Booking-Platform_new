"""I4 screen support: scoped reads, a branch setting and command outcomes by key.

A screen that lost a response asks for the outcome by the original key. The answer
names no reason, name or time. Cancelling an unresolved key claims it in the shared
receipt table, so the lost command cannot commit after the person starts again for
as long as that receipt lives (24 hours); after that the key is an unused key again.
"""

import hashlib
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Any
from uuid import UUID

import psycopg

from gorgona_booking.booking import idempotency
from gorgona_booking.booking.idempotency import IdempotencyScope
from gorgona_booking.business import commands, shift_changes, workforce
from gorgona_booking.business.modules import ModuleDisabledError
from gorgona_booking.business.workforce_contracts import ShiftList, WorkforceReceipt
from gorgona_booking.business.workforce_desk_contracts import (
    CancelledCommand,
    CommandReference,
    CommandState,
    CommandStatus,
    DeskView,
    DirectoryEntry,
    DirectoryList,
    LocationSettingInput,
    LocationSettingView,
    WriteState,
)
from gorgona_booking.db.pool import RuntimeConnection
from gorgona_booking.errors import DomainError, InvalidReferenceError, NotFoundError
from gorgona_booking.tenancy.authorization import PermissionDeniedError

_CANCELLED_STATUS = 410
# Discarded commands one person may leave in one business within 24 hours.
DISCARD_LIMIT = 20
_AUDIT_TARGET_LIMIT = 200


class TooManyDiscardsError(DomainError):
    code = "TOO_MANY_DISCARDED_COMMANDS"


@asynccontextmanager
async def _writes(conn: RuntimeConnection, business: UUID) -> AsyncIterator[None]:
    try:
        async with workforce._writes(conn, business):
            yield
    except psycopg.errors.InsufficientPrivilege as exc:
        raise PermissionDeniedError(
            "Only the owner or a manager of this branch changes its settings"
        ) from exc


async def load_location_setting(
    conn: RuntimeConnection, business: UUID, location: UUID, revision: int | None = None
) -> LocationSettingView:
    known = await (
        await conn.execute(
            "select 1 from gba.locations where tenant_id=%s and id=%s", (business, location)
        )
    ).fetchone()
    if known is None:
        raise NotFoundError("Location not found")
    row = await (
        await conn.execute(
            "select revision,colleague_shifts_visible,created_by,created_at "
            "from gba.work_location_setting_versions where tenant_id=%s and location_id=%s "
            "and (%s::integer is null or revision=%s) order by revision desc limit 1",
            (business, location, revision, revision),
        )
    ).fetchone()
    if row is None and revision is not None:
        raise NotFoundError("Setting version not found")
    return LocationSettingView(
        business_id=business,
        location_id=location,
        revision=0 if row is None else row[0],
        colleague_shifts_visible=True if row is None else row[1],
        changed_by=None if row is None else row[2],
        changed_at=None if row is None else row[3],
    )


async def save_location_setting(
    conn: RuntimeConnection,
    business: UUID,
    location: UUID,
    user: UUID,
    actor: str,
    key: str,
    body: LocationSettingInput,
) -> LocationSettingView:
    async with _writes(conn, business):
        scope = IdempotencyScope(business, actor, "workforce.location_setting", key)
        receipt = await commands.claim(
            conn,
            scope,
            commands.fingerprint({"id": str(location), **body.model_dump(mode="json")}),
            WorkforceReceipt,
        )
        if receipt is not None:
            return await load_location_setting(conn, business, location, receipt.revision)
        await load_location_setting(conn, business, location)
        revision = body.expected_revision + 1
        await conn.execute(
            "insert into gba.work_location_setting_versions "
            "(tenant_id,location_id,revision,colleague_shifts_visible,created_by) "
            "values (%s,%s,%s,%s,%s)",
            (business, location, revision, body.colleague_shifts_visible, user),
        )
        # The audit event carries the chosen value, not only the version number.
        await commands.audit(
            conn,
            business,
            actor,
            "workforce.location_setting",
            "location_setting",
            str(location),
            {"revision": revision, "colleague_shifts_visible": body.colleague_shifts_visible},
        )
        await commands.complete(
            conn, scope, WorkforceReceipt(subject_id=location, revision=revision)
        )
        return await load_location_setting(conn, business, location, revision)


async def desk(conn: RuntimeConnection, business: UUID, user: UUID) -> DeskView:
    writes: WriteState = "open"
    try:
        await workforce.require_workforce(conn, business)
    except workforce.WorkforceNotReadyError:
        writes = "not_accepted"
    except ModuleDisabledError:
        writes = "module_disabled"
    row = await (
        await conn.execute(
            "select p.id from gba.staff_profiles p join gba.memberships m "
            "on m.tenant_id=p.tenant_id and m.id=p.membership_id "
            "where p.tenant_id=%s and p.user_id=%s and m.status='active' order by p.id limit 1",
            (business, user),
        )
    ).fetchone()
    profile = None if row is None else await workforce.load_profile(conn, business, row[0])
    visible = profile is None or await shift_changes.shifts_visible(
        conn, business, profile.location_id
    )
    return DeskView(
        business_id=business,
        writes=writes,
        profile=profile,
        colleague_shifts="visible" if visible else "hidden",
    )


async def directory(
    conn: RuntimeConnection,
    business: UUID,
    location: UUID | None,
    after: UUID | None,
    limit: int,
) -> DirectoryList:
    """Active members with their staff profile; a branch manager sees one branch."""
    rows = await (
        await conn.execute(
            "select m.id,m.user_id,u.display_name,m.role,m.location_id,p.id,p.location_id "
            "from gba.memberships m join gba.users u on u.id=m.user_id and u.status='active' "
            "left join gba.staff_profiles p on p.tenant_id=m.tenant_id and p.membership_id=m.id "
            "where m.tenant_id=%s and m.status='active' "
            "and (%s::uuid is null or p.location_id=%s or (p.id is null and m.location_id=%s)) "
            "and (%s::uuid is null or m.id>%s) order by m.id limit %s",
            (business, location, location, location, after, after, limit + 1),
        )
    ).fetchall()
    items = tuple(
        DirectoryEntry(
            membership_id=r[0],
            user_id=r[1],
            display_name=r[2],
            role=r[3],
            location_id=r[4],
            profile_id=r[5],
            home_location_id=r[6],
        )
        for r in rows[:limit]
    )
    return DirectoryList(
        items=items, next_cursor=items[-1].membership_id if len(rows) > limit else None
    )


async def colleague_shifts(
    conn: RuntimeConnection,
    business: UUID,
    user: UUID,
    profile: UUID,
    starts: datetime,
    ends: datetime,
    after: UUID | None,
    limit: int,
) -> ShiftList:
    """Published shifts a home-branch colleague holds: the other side of a swap.

    The home branch may hide them; then nothing about a colleague is read here.
    """
    location = await shift_changes.home(conn, business, user)
    row = None
    if location is not None:
        # The colleague is looked up in the caller's own scope, as before the setting.
        row = await (
            await conn.execute(
                "select m.user_id from gba.staff_profiles p join gba.memberships m "
                "on m.tenant_id=p.tenant_id and m.id=p.membership_id "
                "join gba.users u on u.id=p.user_id "
                "where p.tenant_id=%s and p.id=%s and p.location_id=%s "
                "and m.status='active' and u.status='active'",
                (business, profile, location),
            )
        ).fetchone()
        await conn.execute("select set_config('gba.location_id',%s,true)", (str(location),))
        # A hidden branch answers the same for a known and an unknown colleague.
        if not await shift_changes.shifts_visible(conn, business, location):
            raise shift_changes.ColleagueShiftsHiddenError(
                "Your branch does not show colleagues' shifts"
            )
    if location is None or row is None:
        raise NotFoundError("Colleague not found")
    listed = await workforce.list_shifts(conn, business, starts, ends, after, limit, row[0])
    items = tuple(
        item
        for item in listed.items
        if item.status == "published" and item.staff_profile_id == profile
    )
    return ShiftList(items=items, next_cursor=listed.next_cursor)


async def request_shifts(
    conn: RuntimeConnection, business: UUID, user: UUID, request: UUID
) -> ShiftList:
    """The shift versions a request names, for a person who takes part in it.

    A request shares exactly its own shifts, also where the branch hides the rest.
    """
    change = await shift_changes.load(conn, business, request, participant=user)
    items = [
        await workforce.load_shift(conn, business, change.shift_id, change.expected_shift_revision)
    ]
    if change.other_shift_id is not None:
        items.append(
            await workforce.load_shift(
                conn, business, change.other_shift_id, change.expected_other_shift_revision
            )
        )
    return ShiftList(items=tuple(items))


def _scope(business: UUID, actor: str, body: CommandReference, key: str) -> IdempotencyScope:
    return IdempotencyScope(business, actor, "workforce." + body.operation, key)


def _state(status: int, stored: dict[str, Any], body: CommandReference) -> CommandState:
    expected = (body.subject_id, body.revision, body.skill_id)
    if status == _CANCELLED_STATUS:
        cancelled = CancelledCommand.model_validate(stored)
        found = (cancelled.subject_id, cancelled.revision, cancelled.skill_id)
    else:
        receipt = WorkforceReceipt.model_validate(stored)
        found = (receipt.subject_id, receipt.revision, receipt.skill_id)
    if found != expected:
        raise InvalidReferenceError("This outcome belongs to another workforce reference")
    return "cancelled" if status == _CANCELLED_STATUS else "committed"


async def resolve_command(
    conn: RuntimeConnection, business: UUID, actor: str, key: str, body: CommandReference
) -> CommandStatus:
    scope = _scope(business, actor, body, key)
    # An expired receipt still records what happened; only a later claim may reuse it.
    row = await (
        await conn.execute(
            "select response_status,response_body from gba.idempotency_keys "
            "where tenant_id=%s and actor_key=%s and operation=%s and idempotency_key=%s",
            (business, actor, scope.operation, key),
        )
    ).fetchone()
    state: CommandState = "unresolved"
    if row is not None and row[0] is not None:
        state = _state(row[0], row[1], body)
    return CommandStatus(business_id=business, key=key, operation=body.operation, state=state)


async def cancel_command(
    conn: RuntimeConnection, business: UUID, actor: str, key: str, body: CommandReference
) -> CommandStatus:
    current = await resolve_command(conn, business, actor, key, body)
    if current.state != "unresolved":
        return current
    scope = _scope(business, actor, body, key)
    discarded = await (
        await conn.execute(
            "select count(*) from gba.idempotency_keys where tenant_id=%s and actor_key=%s "
            "and operation like 'workforce.%%' and response_status=%s "
            "and created_at>now()-interval '24 hours'",
            (business, actor, _CANCELLED_STATUS),
        )
    ).fetchone()
    if discarded is not None and discarded[0] >= DISCARD_LIMIT:
        raise TooManyDiscardsError(
            "Too many actions were discarded today; check the result instead or try later"
        )
    marker = CancelledCommand(**body.model_dump())
    # The claim waits for a command still running under this key, then reports it.
    previous = await idempotency.claim(
        conn, scope, commands.fingerprint(marker.model_dump(mode="json"))
    )
    if previous is not None:
        return current.model_copy(
            update={"state": _state(previous.status_code, previous.body, body)}
        )
    await idempotency.complete(conn, scope, _CANCELLED_STATUS, marker.model_dump(mode="json"))
    await commands.audit(
        conn,
        business,
        actor,
        "workforce.command_cancelled",
        "workforce_command",
        # A key may be longer than an audit target; then its digest names it.
        key
        if len(key) <= _AUDIT_TARGET_LIMIT
        else "sha256:" + hashlib.sha256(key.encode()).hexdigest(),
        {"operation": body.operation, "revision": body.revision},
    )
    return current.model_copy(update={"state": "cancelled"})
