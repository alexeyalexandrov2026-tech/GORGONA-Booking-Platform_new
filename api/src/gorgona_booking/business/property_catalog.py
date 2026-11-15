"""Versioned property catalog and the company-only ownership and management history."""

from datetime import datetime
from typing import Annotated, Literal, Self
from uuid import UUID

from psycopg.errors import ForeignKeyViolation
from psycopg.rows import class_row
from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

from gorgona_booking.booking.idempotency import IdempotencyScope
from gorgona_booking.business import commands, modules
from gorgona_booking.business.module_gate import (
    COUNTERPARTIES_MODULE,
    module_writes,
    require_module,
)
from gorgona_booking.db.pool import RuntimeConnection
from gorgona_booking.errors import ConflictError, InvalidReferenceError, NotFoundError

PROPERTY_MODULE = "property"
PAGE = 50
type PropertyKind = Literal["parcel", "building", "unit"]

_CATALOG_COLUMNS = "object_id, location_id, kind, name, parent_id, revision, recorded_at"
_HISTORY_COLUMNS = (
    "v.object_id, v.location_id, v.kind, v.name, v.parent_id, v.revision, v.recorded_at, "
    "p.recorded_by, p.owner_id, p.manager_id"
)
_REFERENCES = {
    "property_objects_location_fk": "location_id",
    "property_revisions_parent_fk": "parent_id",
    "property_parties_owner_fk": "owner_id",
    "property_parties_manager_fk": "manager_id",
}


class PropertyNotReadyError(ConflictError):
    code = "MODULE_NOT_READY"


class PropertyRevisionConflictError(ConflictError):
    code = "PROPERTY_REVISION_CONFLICT"


class PropertyIdentityFixedError(ConflictError):
    code = "PROPERTY_IDENTITY_FIXED"


class PropertyInput(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    schema_version: Literal[1]
    expected_revision: int = Field(ge=0, le=2_147_483_646, strict=True)
    location_id: UUID
    kind: PropertyKind
    name: Annotated[
        str,
        StringConstraints(strip_whitespace=True, min_length=1, max_length=200),
        Field(pattern=r"^[^\x00-\x1f\x7f]+$"),
    ]
    parent_id: UUID | None = None
    owner_id: UUID | None = None
    manager_id: UUID | None = None

    @model_validator(mode="after")
    def validate_parent(self) -> Self:
        if self.kind == "parcel" and self.parent_id is not None:
            raise ValueError("A parcel cannot have a parent")
        if self.kind == "unit" and self.parent_id is None:
            raise ValueError("A unit requires its building")
        return self


class PropertyView(BaseModel):
    schema_version: Literal[1] = 1
    object_id: UUID
    location_id: UUID
    kind: PropertyKind
    name: str
    parent_id: UUID | None
    revision: int
    recorded_at: datetime


class PropertyRevision(PropertyView):
    recorded_by: UUID
    owner_id: UUID | None
    manager_id: UUID | None


class PropertyList(BaseModel):
    schema_version: Literal[1] = 1
    items: list[PropertyView]
    next_cursor: UUID | None


class PropertyHistory(BaseModel):
    schema_version: Literal[1] = 1
    items: list[PropertyRevision]
    next_cursor: int | None


class RevisionReceipt(BaseModel):
    revision: int


async def list_properties(conn: RuntimeConnection, after: UUID | None) -> PropertyList:
    async with conn.cursor(row_factory=class_row(PropertyView)) as cur:
        await cur.execute(
            "select v.* from gba.property_objects o "
            "cross join lateral (select object_id, location_id, kind, name, parent_id, "
            "revision, recorded_at from gba.property_revisions rv "
            "where rv.tenant_id = o.tenant_id and rv.object_id = o.id "
            "order by revision desc limit 1) v "
            "where (%s::uuid is null or o.id > %s) order by o.id limit %s",
            (after, after, PAGE + 1),
        )
        rows = await cur.fetchall()
    items = rows[:PAGE]
    return PropertyList(items=items, next_cursor=items[-1].object_id if len(rows) > PAGE else None)


async def get_property(conn: RuntimeConnection, object_id: UUID) -> PropertyView:
    async with conn.cursor(row_factory=class_row(PropertyView)) as cur:
        await cur.execute(
            f"select {_CATALOG_COLUMNS} from gba.property_revisions "  # noqa: S608 - fixed columns
            "where object_id = %s order by revision desc limit 1",
            (object_id,),
        )
        view = await cur.fetchone()
    if view is None:
        raise NotFoundError("Property object not found", object_id=str(object_id))
    return view


async def get_history(conn: RuntimeConnection, object_id: UUID, after: int) -> PropertyHistory:
    await get_property(conn, object_id)
    async with conn.cursor(row_factory=class_row(PropertyRevision)) as cur:
        await cur.execute(
            f"select {_HISTORY_COLUMNS} from gba.property_revisions v "  # noqa: S608 - fixed columns
            "join gba.property_parties p using (tenant_id, object_id, revision) "
            "where v.object_id = %s and v.revision > %s order by v.revision limit %s",
            (object_id, after, PAGE + 1),
        )
        rows = await cur.fetchall()
    items = rows[:PAGE]
    return PropertyHistory(
        items=items, next_cursor=items[-1].revision if len(rows) > PAGE else None
    )


async def _get_revision(
    conn: RuntimeConnection, object_id: UUID, revision: int
) -> PropertyRevision:
    async with conn.cursor(row_factory=class_row(PropertyRevision)) as cur:
        await cur.execute(
            f"select {_HISTORY_COLUMNS} from gba.property_revisions v "  # noqa: S608 - fixed columns
            "join gba.property_parties p using (tenant_id, object_id, revision) "
            "where v.object_id = %s and v.revision = %s",
            (object_id, revision),
        )
        row = await cur.fetchone()
    if row is None:
        raise NotFoundError(
            "Property revision not found", object_id=str(object_id), revision=revision
        )
    return row


async def save_property(
    conn: RuntimeConnection,
    business: UUID,
    object_id: UUID,
    *,
    user_id: UUID,
    actor: str,
    key: str,
    body: PropertyInput,
) -> PropertyRevision:
    if not modules.MODULES_BY_ID[PROPERTY_MODULE].enableable:
        raise PropertyNotReadyError("The property module is not ready", module_id=PROPERTY_MODULE)
    await require_module(conn, business, PROPERTY_MODULE)
    await require_module(conn, business, COUNTERPARTIES_MODULE)

    scope = IdempotencyScope(business, actor, "property.object.save", key)
    request_hash = commands.fingerprint(
        {"object_id": str(object_id), "body": body.model_dump(mode="json")}
    )
    receipt = await commands.claim(conn, scope, request_hash, RevisionReceipt)
    if receipt is not None:
        return await _get_revision(conn, object_id, receipt.revision)

    await conn.execute("select gba.lock_property_object(%s, %s)", (business, object_id))
    current = await (
        await conn.execute(
            "select revision, location_id, kind from gba.property_revisions "
            "where object_id = %s order by revision desc limit 1",
            (object_id,),
        )
    ).fetchone()
    revision = int(current[0]) if current is not None else 0
    if body.expected_revision != revision:
        raise PropertyRevisionConflictError(
            "The property changed since it was read", revision=revision
        )
    if current is not None and (body.location_id, body.kind) != (current[1], current[2]):
        raise PropertyIdentityFixedError("The property type and branch are fixed")

    next_revision = revision + 1
    try:
        async with module_writes(PROPERTY_MODULE):
            if current is None:
                await conn.execute(
                    "insert into gba.property_objects (tenant_id, id, location_id, kind) "
                    "values (%s, %s, %s, %s)",
                    (business, object_id, body.location_id, body.kind),
                )
            await conn.execute(
                "insert into gba.property_revisions "
                "(tenant_id, object_id, revision, location_id, kind, name, parent_id) "
                "values (%s, %s, %s, %s, %s, %s, %s)",
                (
                    business,
                    object_id,
                    next_revision,
                    body.location_id,
                    body.kind,
                    body.name,
                    body.parent_id,
                ),
            )
            await conn.execute(
                "insert into gba.property_parties "
                "(tenant_id, object_id, revision, owner_id, manager_id, recorded_by) "
                "values (%s, %s, %s, %s, %s, %s)",
                (business, object_id, next_revision, body.owner_id, body.manager_id, user_id),
            )
    except ForeignKeyViolation as exc:
        field = _REFERENCES.get(exc.diag.constraint_name or "")
        if field is None:
            raise
        raise InvalidReferenceError(
            "Unknown or incompatible property reference", field=field
        ) from exc

    await commands.audit(
        conn,
        business,
        actor,
        "property.object_saved",
        "property_object",
        str(object_id),
        {"location_id": str(body.location_id), "revision": next_revision},
    )
    await commands.complete(conn, scope, RevisionReceipt(revision=next_revision))
    return await _get_revision(conn, object_id, next_revision)
