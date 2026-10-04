"""Tenant-owned departments: append-only draft revisions in one acyclic company structure."""

import hashlib
import json
from typing import Any
from uuid import UUID

from psycopg.errors import ForeignKeyViolation, UniqueViolation
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
from gorgona_booking.errors import ConflictError, DomainError, InvalidReferenceError

# Levels including the saved department. The bounded parent walk also stops on
# any cycle written outside this service instead of recursing without limit.
MAX_DEPTH = 32

_LINK_FIELDS = {
    "department_versions_parent_fk": "parent_department_id",
    "department_versions_legal_entity_fk": "legal_entity_id",
    "department_versions_location_fk": "location_id",
}


class DepartmentStructureError(DomainError):
    code = "DEPARTMENT_STRUCTURE_INVALID"


def request_hash(department_id: UUID, body: DepartmentInput) -> str:
    command = {"department_id": str(department_id), **body.model_dump(mode="json")}
    return hashlib.sha256(json.dumps(command, sort_keys=True).encode()).hexdigest()


def _view(business_id: UUID, department_id: UUID, row: tuple[Any, ...]) -> DepartmentView:
    return DepartmentView(
        business_id=business_id,
        department_id=department_id,
        code=row[0],
        name=row[1],
        parent_department_id=row[2],
        legal_entity_id=row[3],
        location_id=row[4],
        archived=row[5],
        revision=row[6],
        created_at=row[7],
    )


async def load_department(
    conn: RuntimeConnection, business_id: UUID, department_id: UUID, *, revision: int | None = None
) -> DepartmentView | None:
    row = await (
        await conn.execute(
            "select d.code, v.name, v.parent_department_id, v.legal_entity_id, v.location_id, "
            "v.archived, v.revision, v.created_at "
            "from gba.departments d join gba.department_versions v "
            "on v.tenant_id = d.tenant_id and v.department_id = d.id "
            "where d.tenant_id = %s and d.id = %s "
            "and (%s::integer is null or v.revision = %s) "
            "order by v.revision desc limit 1",
            (business_id, department_id, revision, revision),
        )
    ).fetchone()
    return None if row is None else _view(business_id, department_id, row)


async def list_departments(
    conn: RuntimeConnection, business_id: UUID, *, after: str | None, limit: int
) -> DepartmentList:
    rows = await (
        await conn.execute(
            "select d.id, d.code, v.name, v.parent_department_id, v.legal_entity_id, "
            "v.location_id, v.archived, v.revision, v.created_at "
            "from gba.departments d join lateral "
            "(select name, parent_department_id, legal_entity_id, location_id, archived, "
            "revision, created_at from gba.department_versions "
            "where tenant_id = d.tenant_id and department_id = d.id "
            "order by revision desc limit 1) v on true "
            "where d.tenant_id = %s and (%s::text is null or d.code > %s) "
            "order by d.code limit %s",
            (business_id, after, after, limit + 1),
        )
    ).fetchall()
    items = tuple(_view(business_id, row[0], row[1:]) for row in rows[:limit])
    return DepartmentList(
        business_id=business_id,
        items=items,
        next_cursor=items[-1].code if len(rows) > limit else None,
    )


async def _check_structure(
    conn: RuntimeConnection,
    business_id: UUID,
    department_id: UUID,
    current: DepartmentView | None,
    body: DepartmentInput,
) -> None:
    """Validate links against the latest saved structure, under the structure lock."""
    parent_id = body.parent_department_id
    if parent_id == department_id:
        raise DepartmentStructureError("A department cannot be its own parent")
    if parent_id is not None:
        parent = await load_department(conn, business_id, parent_id)
        if parent is None:
            raise InvalidReferenceError("Unknown parent department", field="parent_department_id")
        if parent.archived and not body.archived:
            raise DepartmentStructureError("Choose an active parent department")
        row = await (
            await conn.execute(
                "with recursive latest as ("
                "select distinct on (department_id) department_id, parent_department_id "
                "from gba.department_versions where tenant_id = %s "
                "order by department_id, revision desc"
                "), chain (id, depth) as ("
                "select %s::uuid, 1 union all "
                "select l.parent_department_id, c.depth + 1 "
                "from chain c join latest l on l.department_id = c.id "
                "where l.parent_department_id is not null and c.depth < %s"
                ") select coalesce(bool_or(id = %s), false), max(depth) from chain",
                (business_id, parent_id, MAX_DEPTH, department_id),
            )
        ).fetchone()
        if row is None or row[0]:
            raise DepartmentStructureError(
                "A department cannot be placed under its own subdepartment"
            )
        if row[1] >= MAX_DEPTH:
            raise DepartmentStructureError(
                f"Department structure can have at most {MAX_DEPTH} levels"
            )
    if body.archived and current is not None and not current.archived:
        active_child = await (
            await conn.execute(
                "select 1 from gba.departments d join lateral "
                "(select parent_department_id, archived from gba.department_versions "
                "where tenant_id = d.tenant_id and department_id = d.id "
                "order by revision desc limit 1) v on true "
                "where d.tenant_id = %s and v.parent_department_id = %s and not v.archived "
                "limit 1",
                (business_id, department_id),
            )
        ).fetchone()
        if active_child is not None:
            raise DepartmentStructureError("Archive or move its active subdepartments first")
    for table, value, field, label in (
        ("legal_entities", body.legal_entity_id, "legal_entity_id", "legal entity"),
        ("locations", body.location_id, "location_id", "location"),
    ):
        if value is None:
            continue
        # Fixed table names from the tuple above, never request data.
        found = await (
            await conn.execute(
                f"select 1 from gba.{table} where tenant_id = %s and id = %s",  # noqa: S608
                (business_id, value),
            )
        ).fetchone()
        if found is None:
            raise InvalidReferenceError(f"Unknown {label}", field=field)


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

    Identity, revision, audit and receipt commit or roll back together. The internal
    reference distinguishes records; equal names never merge departments.
    """
    scope = IdempotencyScope(business_id, actor, "business.department.save", key)
    fingerprint = request_hash(department_id, body)
    previous = await idempotency.claim(conn, scope, fingerprint)
    if previous is not None:
        if previous.request_hash != fingerprint:
            raise IdempotencyKeyReusedError(
                "This key was already used with another department command"
            )
        return DepartmentView.model_validate(previous.body)

    current = await load_department(conn, business_id, department_id)
    revision = current.revision if current else 0
    if body.expected_revision != revision:
        raise ConflictError("This department changed. Reload it before saving.", revision=revision)
    if current is not None and current.code != body.code:
        raise InvalidReferenceError(
            "The internal reference of an existing department cannot change"
        )
    await _check_structure(conn, business_id, department_id, current, body)
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
                "insert into gba.department_versions (tenant_id, department_id, revision, name, "
                "parent_department_id, legal_entity_id, location_id, archived, created_by) "
                "values (%s, %s, %s, %s, %s, %s, %s, %s, %s)",
                (
                    business_id,
                    department_id,
                    revision,
                    body.name,
                    body.parent_department_id,
                    body.legal_entity_id,
                    body.location_id,
                    body.archived,
                    user_id,
                ),
            )
    except ForeignKeyViolation as exc:
        field = _LINK_FIELDS.get(exc.diag.constraint_name or "")
        if field is None:
            raise
        raise InvalidReferenceError("Unknown linked record", field=field) from exc
    result = await load_department(conn, business_id, department_id)
    if result is None:
        raise RuntimeError("Department insert did not produce a version")
    links = body.model_dump(
        mode="json", include={"parent_department_id", "legal_entity_id", "location_id", "archived"}
    )
    await conn.execute(
        "insert into gba.audit_events "
        "(tenant_id, actor, action, target_type, target_id, details, request_id) "
        "values (%s, %s, 'department.saved', 'department', %s, %s, "
        "nullif(pg_catalog.current_setting('gba.request_id', true), ''))",
        (
            business_id,
            actor,
            str(department_id),
            Jsonb({"revision": revision, "code": body.code, **links}),
        ),
    )
    await idempotency.complete(conn, scope, 200, result.model_dump(mode="json"))
    return result
