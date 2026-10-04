"""Company-owned department identities and append-only draft revisions."""

import hashlib
import json
from uuid import UUID

from psycopg.errors import CheckViolation, ForeignKeyViolation, UniqueViolation
from psycopg.types.json import Jsonb

from gorgona_booking.booking import idempotency
from gorgona_booking.booking.idempotency import IdempotencyScope
from gorgona_booking.booking.models import IdempotencyKeyReusedError
from gorgona_booking.business.department_contracts import (
    DepartmentInput,
    DepartmentList,
    DepartmentView,
)
from gorgona_booking.db.pool import RuntimeConnection
from gorgona_booking.errors import ConflictError, DatabaseUnavailableError, InvalidReferenceError


def request_hash(department_id: UUID, body: DepartmentInput) -> str:
    command = {"department_id": str(department_id), **body.model_dump(mode="json")}
    return hashlib.sha256(json.dumps(command, sort_keys=True).encode()).hexdigest()


async def load_department(
    conn: RuntimeConnection, business_id: UUID, department_id: UUID, *, revision: int | None = None
) -> DepartmentView | None:
    row = await (
        await conn.execute(
            "select e.code, v.name, v.revision, v.created_at, "
            "v.parent_department_id, v.location_id, v.legal_entity_id "
            "from gba.departments e join gba.department_versions v "
            "on v.tenant_id = e.tenant_id and v.department_id = e.id "
            "where e.tenant_id = %s and e.id = %s "
            "and (%s::integer is null or v.revision = %s) "
            "order by v.revision desc limit 1",
            (business_id, department_id, revision, revision),
        )
    ).fetchone()
    if row is None:
        return None
    return DepartmentView(
        business_id=business_id,
        department_id=department_id,
        code=row[0],
        name=row[1],
        revision=row[2],
        created_at=row[3],
        parent_department_id=row[4],
        location_id=row[5],
        legal_entity_id=row[6],
    )


async def list_departments(
    conn: RuntimeConnection, business_id: UUID, *, after: str | None, limit: int
) -> DepartmentList:
    rows = await (
        await conn.execute(
            "select e.id, e.code, v.name, v.revision, v.created_at, "
            "v.parent_department_id, v.location_id, v.legal_entity_id "
            "from gba.departments e join lateral "
            "(select name, revision, created_at, parent_department_id, "
            "location_id, legal_entity_id "
            "from gba.department_versions "
            "where tenant_id = e.tenant_id and department_id = e.id "
            "order by revision desc limit 1) v on true "
            "where e.tenant_id = %s and (%s::text is null or e.code > %s) "
            "order by e.code limit %s",
            (business_id, after, after, limit + 1),
        )
    ).fetchall()
    items = tuple(
        DepartmentView(
            business_id=business_id,
            department_id=row[0],
            code=row[1],
            name=row[2],
            revision=row[3],
            created_at=row[4],
            parent_department_id=row[5],
            location_id=row[6],
            legal_entity_id=row[7],
        )
        for row in rows[:limit]
    )
    return DepartmentList(
        business_id=business_id,
        items=items,
        next_cursor=items[-1].code if len(rows) > limit else None,
    )


async def save_department(
    conn: RuntimeConnection,
    *,
    business_id: UUID,
    department_id: UUID,
    user_id: UUID,
    actor: str,
    key: str,
    body: DepartmentInput,
) -> DepartmentView:
    """Caller holds the company structure lock before the membership share lock.

    Identity, revision, audit and receipt commit or roll back together. A caller's
    internal reference distinguishes records; equal names never merge departments.
    """
    scope = IdempotencyScope(business_id, actor, "business.department.save", key)
    fingerprint = request_hash(department_id, body)
    previous = await idempotency.claim(conn, scope, fingerprint)
    if previous is not None:
        if previous.request_hash != fingerprint:
            raise IdempotencyKeyReusedError("This key was already used with another entity command")
        return DepartmentView.model_validate(previous.body)

    current = await load_department(conn, business_id, department_id)
    revision = current.revision if current else 0
    if body.expected_revision != revision:
        raise ConflictError("This department changed. Reload it before saving.", revision=revision)
    if current is not None and current.code != body.code:
        raise InvalidReferenceError("The internal reference of an existing entity cannot change")
    if current is None:
        try:
            async with conn.transaction():
                await conn.execute(
                    "insert into gba.departments (tenant_id, id, code, created_by) "
                    "values (%s, %s, %s, %s)",
                    (business_id, department_id, body.code, user_id),
                )
        except UniqueViolation as exc:
            if exc.diag.constraint_name != "departments_code_unique":
                raise
            raise ConflictError("A department with this internal reference already exists") from exc
    revision += 1
    try:
        async with conn.transaction():
            await conn.execute(
                "insert into gba.department_versions "
                "(tenant_id, department_id, revision, name, parent_department_id, "
                "location_id, legal_entity_id, created_by) values (%s, %s, %s, %s, %s, %s, %s, %s)",
                (
                    business_id,
                    department_id,
                    revision,
                    body.name,
                    body.parent_department_id,
                    body.location_id,
                    body.legal_entity_id,
                    user_id,
                ),
            )
    except ForeignKeyViolation as exc:
        raise InvalidReferenceError(
            "Choose existing department, branch and legal entity in this company"
        ) from exc
    except CheckViolation as exc:
        if exc.diag.constraint_name == "department_isolation":
            raise DatabaseUnavailableError("Department writes require READ COMMITTED") from exc
        if exc.diag.constraint_name != "department_hierarchy":
            raise
        raise InvalidReferenceError(
            "Choose a saved parent department without creating a cycle"
        ) from exc
    result = await load_department(conn, business_id, department_id)
    if result is None:
        raise RuntimeError("Department insert did not produce a version")
    await conn.execute(
        "insert into gba.audit_events "
        "(tenant_id, actor, action, target_type, target_id, details, request_id) "
        "values (%s, %s, 'department.saved', 'department', %s, %s, "
        "nullif(pg_catalog.current_setting('gba.request_id', true), ''))",
        (business_id, actor, str(department_id), Jsonb({"revision": revision, "code": body.code})),
    )
    await idempotency.complete(conn, scope, 200, result.model_dump(mode="json"))
    return result
