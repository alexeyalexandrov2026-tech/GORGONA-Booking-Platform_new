"""Company groups (ADR-0018): consent-based relationships that grant no data access.

An organizer business creates a group and invites independent businesses; each member
decides for itself. Commands run in the acting company's context with an expected
revision, an audit event in that company and an idempotent receipt.
"""

import hashlib
import json
from typing import Any, Literal
from uuid import UUID

from psycopg.errors import ForeignKeyViolation, UniqueViolation
from psycopg.types.json import Jsonb

from gorgona_booking.booking import idempotency
from gorgona_booking.booking.idempotency import IdempotencyScope
from gorgona_booking.booking.models import IdempotencyKeyReusedError
from gorgona_booking.business.group_contracts import (
    BusinessGroupList,
    BusinessGroupView,
    GroupCreate,
    GroupDecision,
    GroupInvite,
    GroupMembershipView,
)
from gorgona_booking.db.pool import RuntimeConnection
from gorgona_booking.errors import ConflictError, DomainError, InvalidReferenceError, NotFoundError

MemberAction = Literal["accept", "decline", "leave", "remove"]
_NEXT_STATUS: dict[MemberAction, str] = {
    "accept": "active",
    "decline": "declined",
    "leave": "left",
    "remove": "removed",
}
_FROM_STATUS: dict[MemberAction, tuple[str, ...]] = {
    "accept": ("invited",),
    "decline": ("invited",),
    "leave": ("active",),
    "remove": ("invited", "active"),
}


class GroupStateError(DomainError):
    code = "GROUP_STATE_INVALID"


def _hash(command: dict[str, Any]) -> str:
    return hashlib.sha256(json.dumps(command, sort_keys=True).encode()).hexdigest()


async def _claim(
    conn: RuntimeConnection, scope: IdempotencyScope, fingerprint: str
) -> BusinessGroupView | None:
    previous = await idempotency.claim(conn, scope, fingerprint)
    if previous is None:
        return None
    if previous.request_hash != fingerprint:
        raise IdempotencyKeyReusedError("This key was already used with another command")
    return BusinessGroupView.model_validate(previous.body)


async def _audit(
    conn: RuntimeConnection,
    business_id: UUID,
    actor: str,
    action: str,
    group_id: UUID,
    **details: object,
) -> None:
    await conn.execute(
        "insert into gba.audit_events "
        "(tenant_id, actor, action, target_type, target_id, details, request_id) "
        "values (%s, %s, %s, 'business_group', %s, %s, "
        "nullif(pg_catalog.current_setting('gba.request_id', true), ''))",
        (business_id, actor, f"business_group.{action}", str(group_id), Jsonb(details)),
    )


async def _views(
    conn: RuntimeConnection, business_id: UUID, groups: list[tuple[Any, ...]]
) -> list[BusinessGroupView]:
    if not groups:
        return []
    rows = await (
        await conn.execute(
            "select group_id, id, member_tenant_id, member_display_name, status, revision, "
            "invited_at, decided_at, ended_at from gba.business_group_members "
            "where group_id = any(%s) and (organizer_tenant_id = %s or member_tenant_id = %s) "
            "order by invited_at, id",
            ([row[0] for row in groups], business_id, business_id),
        )
    ).fetchall()
    views = []
    for group in groups:
        role = "organizer" if group[1] == business_id else "member"
        memberships = tuple(
            GroupMembershipView(
                membership_id=row[1],
                member_business_id=row[2],
                member_name=row[3],
                status=row[4],
                revision=row[5],
                invited_at=row[6],
                decided_at=row[7],
                ended_at=row[8],
            )
            for row in rows
            if row[0] == group[0] and (role == "organizer" or row[2] == business_id)
        )
        views.append(
            BusinessGroupView(
                group_id=group[0],
                organizer_business_id=group[1],
                organizer_name=group[2],
                code=group[3],
                name=group[4],
                role=role,
                memberships=memberships,
                created_at=group[5],
            )
        )
    return views


_GROUP = (
    "select g.id, g.organizer_tenant_id, g.organizer_display_name, g.code, g.name, g.created_at "
    "from gba.business_groups g where (g.organizer_tenant_id = %s or exists ("
    "select 1 from gba.business_group_members m where m.organizer_tenant_id = "
    "g.organizer_tenant_id and m.group_id = g.id and m.member_tenant_id = %s)) "
)


async def load_group(
    conn: RuntimeConnection, business_id: UUID, group_id: UUID
) -> BusinessGroupView | None:
    row = await (
        await conn.execute(_GROUP + "and g.id = %s", (business_id, business_id, group_id))
    ).fetchone()
    views = await _views(conn, business_id, [row] if row else [])
    return views[0] if views else None


async def list_groups(
    conn: RuntimeConnection, business_id: UUID, *, after: UUID | None, limit: int
) -> BusinessGroupList:
    rows = await (
        await conn.execute(
            _GROUP + "and (%s::uuid is null or g.id > %s) order by g.id limit %s",
            (business_id, business_id, after, after, limit + 1),
        )
    ).fetchall()
    items = tuple(await _views(conn, business_id, rows[:limit]))
    return BusinessGroupList(
        business_id=business_id,
        items=items,
        next_cursor=items[-1].group_id if len(rows) > limit else None,
    )


async def create_group(
    conn: RuntimeConnection,
    *,
    business_id: UUID,
    group_id: UUID,
    user_id: UUID,
    actor: str,
    key: str,
    body: GroupCreate,
) -> BusinessGroupView:
    scope = IdempotencyScope(business_id, actor, "business.group.create", key)
    fingerprint = _hash({"group_id": str(group_id), **body.model_dump(mode="json")})
    if (previous := await _claim(conn, scope, fingerprint)) is not None:
        return previous
    organizer = await (
        await conn.execute("select display_name from gba.tenants where id = %s", (business_id,))
    ).fetchone()
    if organizer is None:
        raise RuntimeError("Authorized business is not visible")
    try:
        async with conn.transaction():
            await conn.execute(
                "insert into gba.business_groups (organizer_tenant_id, id, code, name, "
                "organizer_display_name, created_by) values (%s, %s, %s, %s, %s, %s)",
                (business_id, group_id, body.code, body.name, organizer[0], user_id),
            )
    except UniqueViolation as exc:
        if exc.diag.constraint_name == "business_groups_code_unique":
            raise ConflictError("A group with this internal reference already exists") from exc
        raise ConflictError("This group already exists") from exc
    result = await load_group(conn, business_id, group_id)
    if result is None:
        raise RuntimeError("Group insert did not produce a group")
    await _audit(conn, business_id, actor, "created", group_id, code=body.code)
    await idempotency.complete(conn, scope, 200, result.model_dump(mode="json"))
    return result


async def invite_member(
    conn: RuntimeConnection,
    *,
    business_id: UUID,
    group_id: UUID,
    member_business_id: UUID,
    user_id: UUID,
    actor: str,
    key: str,
    body: GroupInvite,
) -> BusinessGroupView:
    scope = IdempotencyScope(business_id, actor, "business.group.invite", key)
    fingerprint = _hash(
        {"group_id": str(group_id), "member": str(member_business_id), **body.model_dump()}
    )
    if (previous := await _claim(conn, scope, fingerprint)) is not None:
        return previous
    group = await (
        await conn.execute(
            "select 1 from gba.business_groups where organizer_tenant_id = %s and id = %s",
            (business_id, group_id),
        )
    ).fetchone()
    if group is None:
        raise NotFoundError("Group not found")
    if member_business_id == business_id:
        raise GroupStateError("The organizer is not invited to its own group")
    try:
        async with conn.transaction():
            await conn.execute(
                "insert into gba.business_group_members "
                "(organizer_tenant_id, group_id, member_tenant_id, invited_by) "
                "values (%s, %s, %s, %s)",
                (business_id, group_id, member_business_id, user_id),
            )
    except UniqueViolation as exc:
        raise ConflictError("This business is already invited to or in the group") from exc
    except ForeignKeyViolation as exc:
        raise InvalidReferenceError("Unknown business", field="member_business_id") from exc
    result = await load_group(conn, business_id, group_id)
    if result is None:
        raise RuntimeError("Group disappeared during an invitation")
    await _audit(
        conn, business_id, actor, "invited", group_id, member_business_id=str(member_business_id)
    )
    await idempotency.complete(conn, scope, 200, result.model_dump(mode="json"))
    return result


async def change_membership(
    conn: RuntimeConnection,
    *,
    business_id: UUID,
    group_id: UUID,
    member_business_id: UUID,
    action: MemberAction,
    user_id: UUID,
    actor: str,
    key: str,
    body: GroupDecision,
) -> BusinessGroupView:
    """Members accept, decline or leave for themselves; only the organizer removes."""
    scope = IdempotencyScope(business_id, actor, f"business.group.{action}", key)
    fingerprint = _hash(
        {
            "group_id": str(group_id),
            "member": str(member_business_id),
            "action": action,
            **body.model_dump(),
        }
    )
    if (previous := await _claim(conn, scope, fingerprint)) is not None:
        return previous
    organizer_side = action == "remove"
    row = await (
        await conn.execute(
            "select organizer_tenant_id, id, status, revision from gba.business_group_members "
            "where group_id = %s and member_tenant_id = %s "
            "and status in ('invited', 'active') "
            "and (case when %s then organizer_tenant_id = %s else member_tenant_id = %s end) "
            "for update",
            (group_id, member_business_id, organizer_side, business_id, business_id),
        )
    ).fetchone()
    if row is None or (not organizer_side and member_business_id != business_id):
        raise NotFoundError("Group membership not found")
    organizer_id, membership_id, status, revision = row
    if body.expected_revision != revision:
        raise ConflictError(
            "This membership changed. Reload it before deciding.", revision=revision
        )
    if status not in _FROM_STATUS[action]:
        raise GroupStateError("This membership cannot change this way in its current state")
    if action in ("accept", "decline"):
        name = await (
            await conn.execute("select display_name from gba.tenants where id = %s", (business_id,))
        ).fetchone()
        await conn.execute(
            "update gba.business_group_members set status = %s, revision = revision + 1, "
            "member_display_name = %s, decided_by = %s, decided_at = now() "
            "where organizer_tenant_id = %s and id = %s",
            (
                _NEXT_STATUS[action],
                name[0] if name and action == "accept" else None,
                user_id,
                organizer_id,
                membership_id,
            ),
        )
    else:
        await conn.execute(
            "update gba.business_group_members set status = %s, revision = revision + 1, "
            "ended_by = %s, ended_at = now() where organizer_tenant_id = %s and id = %s",
            (_NEXT_STATUS[action], user_id, organizer_id, membership_id),
        )
    result = await load_group(conn, business_id, group_id)
    if result is None:
        raise RuntimeError("Group disappeared during a decision")
    await _audit(
        conn,
        business_id,
        actor,
        {"accept": "joined", "decline": "declined", "leave": "left", "remove": "removed"}[action],
        group_id,
        member_business_id=str(member_business_id),
        revision=revision + 1,
    )
    await idempotency.complete(conn, scope, 200, result.model_dump(mode="json"))
    return result
