"""Company-owned group identities and append-only draft revisions."""

import hashlib
import json
from uuid import UUID

from psycopg.errors import CheckViolation, ForeignKeyViolation, UniqueViolation
from psycopg.types.json import Jsonb

from gorgona_booking.booking import idempotency
from gorgona_booking.booking.idempotency import IdempotencyScope
from gorgona_booking.booking.models import IdempotencyKeyReusedError
from gorgona_booking.business.group_contracts import (
    GroupInput,
    GroupList,
    GroupView,
)
from gorgona_booking.db.pool import RuntimeConnection
from gorgona_booking.errors import ConflictError, DatabaseUnavailableError, InvalidReferenceError


def request_hash(group_id: UUID, body: GroupInput) -> str:
    command = {"group_id": str(group_id), **body.model_dump(mode="json")}
    return hashlib.sha256(json.dumps(command, sort_keys=True).encode()).hexdigest()


async def load_group(
    conn: RuntimeConnection, business_id: UUID, group_id: UUID, *, revision: int | None = None
) -> GroupView | None:
    row = await (
        await conn.execute(
            "select e.code, v.name, v.revision, v.created_at "
            "from gba.company_groups e join gba.company_group_versions v "
            "on v.tenant_id = e.tenant_id and v.group_id = e.id "
            "where e.tenant_id = %s and e.id = %s "
            "and (%s::integer is null or v.revision = %s) "
            "order by v.revision desc limit 1",
            (business_id, group_id, revision, revision),
        )
    ).fetchone()
    if row is None:
        return None
    return GroupView(
        business_id=business_id,
        group_id=group_id,
        code=row[0],
        name=row[1],
        revision=row[2],
        created_at=row[3],
    )


async def list_company_groups(
    conn: RuntimeConnection, business_id: UUID, *, after: str | None, limit: int
) -> GroupList:
    rows = await (
        await conn.execute(
            "select e.id, e.code, v.name, v.revision, v.created_at "
            "from gba.company_groups e join lateral "
            "(select name, revision, created_at "
            "from gba.company_group_versions "
            "where tenant_id = e.tenant_id and group_id = e.id "
            "order by revision desc limit 1) v on true "
            "where e.tenant_id = %s and (%s::text is null or e.code > %s) "
            "order by e.code limit %s",
            (business_id, after, after, limit + 1),
        )
    ).fetchall()
    items = tuple(
        GroupView(
            business_id=business_id,
            group_id=row[0],
            code=row[1],
            name=row[2],
            revision=row[3],
            created_at=row[4],
        )
        for row in rows[:limit]
    )
    return GroupList(
        business_id=business_id,
        items=items,
        next_cursor=items[-1].code if len(rows) > limit else None,
    )


async def save_group(
    conn: RuntimeConnection,
    *,
    business_id: UUID,
    group_id: UUID,
    user_id: UUID,
    actor: str,
    key: str,
    body: GroupInput,
) -> GroupView:
    """Caller holds the company structure lock before the membership share lock.

    Identity, revision, audit and receipt commit or roll back together. A caller's
    internal reference distinguishes records; equal names never merge groups.
    """
    scope = IdempotencyScope(business_id, actor, "business.group.save", key)
    fingerprint = request_hash(group_id, body)
    previous = await idempotency.claim(conn, scope, fingerprint)
    if previous is not None:
        if previous.request_hash != fingerprint:
            raise IdempotencyKeyReusedError("This key was already used with another entity command")
        return GroupView.model_validate(previous.body)

    current = await load_group(conn, business_id, group_id)
    revision = current.revision if current else 0
    if body.expected_revision != revision:
        raise ConflictError("This group changed. Reload it before saving.", revision=revision)
    if current is not None and current.code != body.code:
        raise InvalidReferenceError("The internal reference of an existing entity cannot change")
    if current is None:
        try:
            async with conn.transaction():
                await conn.execute(
                    "insert into gba.company_groups (tenant_id, id, code, created_by) "
                    "values (%s, %s, %s, %s)",
                    (business_id, group_id, body.code, user_id),
                )
        except UniqueViolation as exc:
            if exc.diag.constraint_name != "company_groups_code_unique":
                raise
            raise ConflictError("A group with this internal reference already exists") from exc
    revision += 1
    try:
        async with conn.transaction():
            await conn.execute(
                "insert into gba.company_group_versions "
                "(tenant_id, group_id, revision, name, created_by) values (%s, %s, %s, %s, %s)",
                (
                    business_id,
                    group_id,
                    revision,
                    body.name,
                    user_id,
                ),
            )
    except ForeignKeyViolation as exc:
        raise InvalidReferenceError("Choose an existing group in this company") from exc
    except CheckViolation as exc:
        if exc.diag.constraint_name != "company_group_isolation":
            raise
        raise DatabaseUnavailableError("Group writes require READ COMMITTED") from exc
    result = await load_group(conn, business_id, group_id)
    if result is None:
        raise RuntimeError("Group insert did not produce a version")
    await conn.execute(
        "insert into gba.audit_events "
        "(tenant_id, actor, action, target_type, target_id, details, request_id) "
        "values (%s, %s, 'group.saved', 'group', %s, %s, "
        "nullif(pg_catalog.current_setting('gba.request_id', true), ''))",
        (business_id, actor, str(group_id), Jsonb({"revision": revision, "code": body.code})),
    )
    await idempotency.complete(conn, scope, 200, result.model_dump(mode="json"))
    return result
