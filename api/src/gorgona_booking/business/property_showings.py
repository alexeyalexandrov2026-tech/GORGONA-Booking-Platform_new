"""Property showings backed by the shared resource allocations."""

from datetime import timedelta
from typing import Literal, Self
from uuid import UUID, uuid7

from psycopg import errors
from psycopg.rows import class_row
from pydantic import AwareDatetime, model_validator

from gorgona_booking.booking import repository as repo
from gorgona_booking.booking.idempotency import IdempotencyScope
from gorgona_booking.booking.models import SlotConflictError
from gorgona_booking.business import commands, modules
from gorgona_booking.business.contracts import Strict, Versioned
from gorgona_booking.business.module_gate import (
    COUNTERPARTIES_MODULE,
    module_writes,
    require_module,
)
from gorgona_booking.business.property_catalog import PROPERTY_MODULE, PropertyNotReadyError
from gorgona_booking.db.pool import RuntimeConnection
from gorgona_booking.errors import ConflictError, InvalidReferenceError, NotFoundError

PAGE = 50
_SELECT = (
    "select s.id as showing_id, s.object_id, s.location_id, s.host_resource_id, "
    "s.starts_at, s.ends_at, s.recorded_at, c.cancelled_at, "
    "case when c.showing_id is null then 'active' else 'cancelled' end as status "
    "from gba.property_showings s left join gba.property_showing_cancellations c "
    "on c.tenant_id = s.tenant_id and c.showing_id = s.id "
)


class ShowingInput(Versioned):
    object_id: UUID
    prospect_id: UUID
    host_resource_id: UUID | None = None
    starts_at: AwareDatetime
    ends_at: AwareDatetime

    @model_validator(mode="after")
    def validate_interval(self) -> Self:
        if not timedelta(0) < self.ends_at - self.starts_at <= timedelta(days=31):
            raise ValueError("A showing lasts between zero and 31 days")
        return self


class CancelInput(Versioned):
    pass


class ShowingView(Strict):
    schema_version: Literal[1] = 1
    showing_id: UUID
    object_id: UUID
    location_id: UUID
    host_resource_id: UUID | None
    starts_at: AwareDatetime
    ends_at: AwareDatetime
    recorded_at: AwareDatetime
    cancelled_at: AwareDatetime | None
    status: Literal["active", "cancelled"]


class ShowingList(Strict):
    schema_version: Literal[1] = 1
    items: list[ShowingView]
    next_cursor: UUID | None


class ShowingReceipt(Strict):
    showing_id: UUID


async def list_showings(conn: RuntimeConnection, business: UUID, after: UUID | None) -> ShowingList:
    async with conn.cursor(row_factory=class_row(ShowingView)) as cur:
        await cur.execute(
            f"{_SELECT} where s.tenant_id = %s and (%s::uuid is null or s.id > %s)"
            " order by s.id limit %s",
            (business, after, after, PAGE + 1),
        )
        rows = await cur.fetchall()
    items = rows[:PAGE]
    return ShowingList(items=items, next_cursor=items[-1].showing_id if len(rows) > PAGE else None)


async def get_showing(conn: RuntimeConnection, business: UUID, showing_id: UUID) -> ShowingView:
    async with conn.cursor(row_factory=class_row(ShowingView)) as cur:
        await cur.execute(f"{_SELECT} where s.tenant_id = %s and s.id = %s", (business, showing_id))
        view = await cur.fetchone()
    if view is None:
        raise NotFoundError("Showing not found")
    return view


async def _object_resource(
    conn: RuntimeConnection, business: UUID, object_id: UUID
) -> tuple[UUID, UUID]:
    await conn.execute("select gba.lock_property_object(%s, %s)", (business, object_id))
    row = await (
        await conn.execute(
            "select o.location_id, o.kind, m.resource_id from gba.property_objects o "
            "left join gba.property_showing_resources m "
            "on m.tenant_id = o.tenant_id and m.object_id = o.id "
            "where o.tenant_id = %s and o.id = %s",
            (business, object_id),
        )
    ).fetchone()
    if row is None:
        raise NotFoundError("Property object not found")
    location_id, kind, resource = row
    if resource is None:
        resource = uuid7()
        await conn.execute(
            "insert into gba.resources (tenant_id, id, location_id, kind, display_name) "
            "values (%s, %s, %s, 'property_object', 'Property showing')",
            (business, resource, location_id),
        )
        await conn.execute(
            "insert into gba.property_showing_resources "
            "(tenant_id, object_id, location_id, object_kind, resource_id) values (%s,%s,%s,%s,%s)",
            (business, object_id, location_id, kind, resource),
        )
    return location_id, resource


async def create_showing(
    conn: RuntimeConnection,
    business: UUID,
    showing_id: UUID,
    *,
    user_id: UUID,
    actor: str,
    key: str,
    body: ShowingInput,
    request_id: str,
) -> ShowingView:
    scope = IdempotencyScope(business, actor, "property.showing.create", key)
    fingerprint = commands.fingerprint(
        {"showing_id": str(showing_id), "body": body.model_dump(mode="json")}
    )
    receipt = await commands.claim(conn, scope, fingerprint, ShowingReceipt)
    if receipt is not None:
        original = await get_showing(conn, business, receipt.showing_id)
        return original.model_copy(update={"status": "active", "cancelled_at": None})
    if not modules.MODULES_BY_ID[PROPERTY_MODULE].enableable:
        raise PropertyNotReadyError("The property module is not ready", module_id=PROPERTY_MODULE)
    await require_module(conn, business, PROPERTY_MODULE)
    await require_module(conn, business, COUNTERPARTIES_MODULE)
    try:
        async with module_writes(PROPERTY_MODULE):
            location, resource = await _object_resource(conn, business, body.object_id)
            host = body.host_resource_id
            resources = [resource] if host is None else sorted((resource, host))
            for resource_id in resources:
                await repo.lock_resource_schedule(conn, business, resource_id)
            if host is not None:
                active_host = await (
                    await conn.execute(
                        "select 1 from gba.resources where tenant_id = %s and id = %s "
                        "and location_id = %s and kind = 'artist' and is_active for share",
                        (business, host, location),
                    )
                ).fetchone()
                if active_host is None:
                    raise InvalidReferenceError(
                        "The host must be an active bookable employee in the object's branch",
                        field="host_resource_id",
                    )
                await repo.set_audit_context(
                    conn,
                    actor="system:hold-expiry",
                    reason="expired_on_contention",
                    request_id=request_id,
                )
                await repo.expire_stale_holds_overlapping(conn, host, body.starts_at, body.ends_at)
            await conn.execute(
                "insert into gba.property_showings (tenant_id, id, object_id, location_id, "
                "object_resource_id, host_resource_id, prospect_id, starts_at, ends_at, "
                "recorded_by)"
                " values (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                (
                    business,
                    showing_id,
                    body.object_id,
                    location,
                    resource,
                    host,
                    body.prospect_id,
                    body.starts_at,
                    body.ends_at,
                    user_id,
                ),
            )
            for resource_id in resources:
                await conn.execute(
                    "insert into gba.resource_allocations "
                    "(tenant_id, resource_id, source_kind, source_id, during, state) "
                    "values (%s,%s,'property_showing',%s,tstzrange(%s,%s,'[)'),'confirmed')",
                    (business, resource_id, showing_id, body.starts_at, body.ends_at),
                )
    except errors.ExclusionViolation as exc:
        if repo.is_slot_conflict(exc):
            raise SlotConflictError("An object or host is already taken in this interval") from exc
        raise
    except errors.UniqueViolation as exc:
        if exc.diag.constraint_name == "property_showings_pkey":
            raise ConflictError("This showing already exists") from exc
        raise
    except errors.ForeignKeyViolation as exc:
        if exc.diag.constraint_name == "property_showings_prospect_fk":
            raise InvalidReferenceError("Unknown prospect", field="prospect_id") from exc
        raise
    await commands.audit(
        conn,
        business,
        actor,
        "property.showing_created",
        "property_showing",
        str(showing_id),
        {"object_id": str(body.object_id), "location_id": str(location)},
    )
    await commands.complete(conn, scope, ShowingReceipt(showing_id=showing_id))
    return await get_showing(conn, business, showing_id)


async def cancel_showing(
    conn: RuntimeConnection,
    business: UUID,
    showing_id: UUID,
    *,
    user_id: UUID,
    actor: str,
    key: str,
) -> ShowingView:
    scope = IdempotencyScope(business, actor, "property.showing.cancel", key)
    fingerprint = commands.fingerprint({"showing_id": str(showing_id)})
    receipt = await commands.claim(conn, scope, fingerprint, ShowingReceipt)
    if receipt is not None:
        return await get_showing(conn, business, receipt.showing_id)
    await get_showing(conn, business, showing_id)
    cancelled = await (
        await conn.execute(
            "insert into gba.property_showing_cancellations (tenant_id, showing_id, cancelled_by) "
            "values (%s,%s,%s) on conflict (tenant_id, showing_id) do nothing returning showing_id",
            (business, showing_id, user_id),
        )
    ).fetchone()
    if cancelled is not None:
        await commands.audit(
            conn,
            business,
            actor,
            "property.showing_cancelled",
            "property_showing",
            str(showing_id),
            {},
        )
    await commands.complete(conn, scope, ShowingReceipt(showing_id=showing_id))
    return await get_showing(conn, business, showing_id)
