"""I4 screen support: scoped reads and a reference-only outcome of a sent command.

A screen that lost a response asks for the outcome by the original key. The answer
names no reason, name or time. Cancelling an unresolved key claims it in the shared
receipt table, so the lost command can never commit after the person starts again.
"""

from datetime import datetime
from typing import Any
from uuid import UUID

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
    WriteState,
)
from gorgona_booking.db.pool import RuntimeConnection
from gorgona_booking.errors import InvalidReferenceError, NotFoundError

_CANCELLED_STATUS = 410


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
    return DeskView(business_id=business, writes=writes, profile=profile)


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
            "from gba.memberships m left join gba.users u on u.id=m.user_id "
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
    """Published shifts a home-branch colleague holds: the other side of a swap."""
    location = await shift_changes.home(conn, business, user)
    row = None
    if location is not None:
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
    if location is None or row is None:
        raise NotFoundError("Colleague not found")
    await conn.execute("select set_config('gba.location_id',%s,true)", (str(location),))
    listed = await workforce.list_shifts(conn, business, starts, ends, after, limit, row[0])
    items = tuple(
        item
        for item in listed.items
        if item.status == "published" and item.staff_profile_id == profile
    )
    return ShiftList(items=items, next_cursor=listed.next_cursor)


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
        key,
        {"operation": body.operation, "revision": body.revision},
    )
    return current.model_copy(update={"state": "cancelled"})
