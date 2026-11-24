"""Versioned listings of property catalog objects (PROPERTY-01 step 2a)."""

from datetime import date, datetime
from typing import Annotated, Literal
from uuid import UUID

from psycopg.rows import class_row
from pydantic import BaseModel, ConfigDict, Field, StringConstraints

from gorgona_booking.booking.idempotency import IdempotencyScope
from gorgona_booking.business import commands, modules
from gorgona_booking.business.module_gate import module_writes, require_module
from gorgona_booking.business.property_catalog import (
    PAGE,
    PROPERTY_MODULE,
    PropertyKind,
    PropertyNotReadyError,
    PropertyRevisionConflictError,
    get_property,
)
from gorgona_booking.db.pool import RuntimeConnection
from gorgona_booking.errors import NotFoundError

type ListingState = Literal["draft", "published", "withdrawn"]

_COLUMNS = (
    "v.object_id, v.location_id, l.kind, v.revision, v.state, v.headline, v.description, "
    "v.monthly_rent, v.currency, v.available_from, v.recorded_at"
)
_LATEST = (
    "from gba.property_listings l join gba.property_listing_revisions v "
    "using (tenant_id, object_id, location_id) "
    "where v.revision = (select max(r.revision) from gba.property_listing_revisions r "
    "where r.tenant_id = v.tenant_id and r.object_id = v.object_id)"
)


class ListingInput(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    schema_version: Literal[1]
    expected_revision: int = Field(ge=0, le=2_147_483_646, strict=True)
    state: ListingState
    headline: Annotated[
        str,
        StringConstraints(strip_whitespace=True, min_length=1, max_length=120),
        Field(pattern=r"^[^\x00-\x1f\x7f]+$"),
    ]
    description: (
        Annotated[str, Field(max_length=4000, pattern=r"^[^\x00-\x08\x0b-\x1f\x7f]*$")] | None
    ) = None
    monthly_rent: int = Field(ge=1, le=1_000_000_000_000, strict=True)
    currency: Annotated[str, Field(pattern=r"^[A-Z]{3}$")]
    available_from: date


class ListingView(BaseModel):
    schema_version: Literal[1] = 1
    object_id: UUID
    location_id: UUID
    kind: PropertyKind
    revision: int
    state: ListingState
    headline: str
    description: str | None
    monthly_rent: int
    currency: str
    available_from: date
    recorded_at: datetime


class ListingRevision(ListingView):
    recorded_by: UUID


class ListingList(BaseModel):
    schema_version: Literal[1] = 1
    items: list[ListingView]
    next_cursor: UUID | None


class ListingHistory(BaseModel):
    schema_version: Literal[1] = 1
    items: list[ListingRevision]
    next_cursor: int | None


class ListingReceipt(BaseModel):
    revision: int


async def list_listings(conn: RuntimeConnection, after: UUID | None) -> ListingList:
    async with conn.cursor(row_factory=class_row(ListingView)) as cur:
        await cur.execute(
            f"select {_COLUMNS} {_LATEST} "
            "and (%s::uuid is null or v.object_id > %s) order by v.object_id limit %s",
            (after, after, PAGE + 1),
        )
        rows = await cur.fetchall()
    items = rows[:PAGE]
    return ListingList(items=items, next_cursor=items[-1].object_id if len(rows) > PAGE else None)


async def get_listing(conn: RuntimeConnection, object_id: UUID) -> ListingView:
    async with conn.cursor(row_factory=class_row(ListingView)) as cur:
        await cur.execute(
            f"select {_COLUMNS} {_LATEST} and v.object_id = %s",
            (object_id,),
        )
        view = await cur.fetchone()
    if view is None:
        raise NotFoundError("Property listing not found", object_id=str(object_id))
    return view


async def _revision(conn: RuntimeConnection, object_id: UUID, revision: int) -> ListingRevision:
    async with conn.cursor(row_factory=class_row(ListingRevision)) as cur:
        await cur.execute(
            f"select {_COLUMNS}, v.recorded_by "  # noqa: S608 - fixed columns
            "from gba.property_listings l join gba.property_listing_revisions v "
            "using (tenant_id, object_id, location_id) "
            "where v.object_id = %s and v.revision = %s",
            (object_id, revision),
        )
        row = await cur.fetchone()
    if row is None:
        raise NotFoundError(
            "Property listing revision not found", object_id=str(object_id), revision=revision
        )
    return row


async def get_history(conn: RuntimeConnection, object_id: UUID, after: int) -> ListingHistory:
    await get_listing(conn, object_id)
    async with conn.cursor(row_factory=class_row(ListingRevision)) as cur:
        await cur.execute(
            f"select {_COLUMNS}, v.recorded_by "  # noqa: S608 - fixed columns
            "from gba.property_listings l join gba.property_listing_revisions v "
            "using (tenant_id, object_id, location_id) "
            "where v.object_id = %s and v.revision > %s order by v.revision limit %s",
            (object_id, after, PAGE + 1),
        )
        rows = await cur.fetchall()
    items = rows[:PAGE]
    return ListingHistory(items=items, next_cursor=items[-1].revision if len(rows) > PAGE else None)


async def save_listing(
    conn: RuntimeConnection,
    business: UUID,
    object_id: UUID,
    *,
    user_id: UUID,
    actor: str,
    key: str,
    body: ListingInput,
) -> ListingRevision:
    scope = IdempotencyScope(business, actor, "property.listing.save", key)
    request_hash = commands.fingerprint(
        {"object_id": str(object_id), "body": body.model_dump(mode="json", exclude_unset=True)}
    )
    receipt = await commands.claim(conn, scope, request_hash, ListingReceipt)
    if receipt is not None:
        return await _revision(conn, object_id, receipt.revision)

    if not modules.MODULES_BY_ID[PROPERTY_MODULE].enableable:
        raise PropertyNotReadyError("The property module is not ready", module_id=PROPERTY_MODULE)
    await require_module(conn, business, PROPERTY_MODULE)

    await conn.execute("select gba.lock_property_object(%s, %s)", (business, object_id))
    item = await get_property(conn, object_id)
    current = await (
        await conn.execute(
            "select max(revision) from gba.property_listing_revisions where object_id = %s",
            (object_id,),
        )
    ).fetchone()
    revision = int(current[0]) if current is not None and current[0] is not None else 0
    if body.expected_revision != revision:
        raise PropertyRevisionConflictError(
            "The listing changed since it was read", revision=revision
        )

    next_revision = revision + 1
    async with module_writes(PROPERTY_MODULE):
        if revision == 0:
            await conn.execute(
                "insert into gba.property_listings (tenant_id, object_id, location_id, kind) "
                "values (%s, %s, %s, %s)",
                (business, object_id, item.location_id, item.kind),
            )
        await conn.execute(
            "insert into gba.property_listing_revisions (tenant_id, object_id, revision, "
            "location_id, state, headline, description, monthly_rent, currency, available_from, "
            "recorded_by) values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
            (
                business,
                object_id,
                next_revision,
                item.location_id,
                body.state,
                body.headline,
                body.description,
                body.monthly_rent,
                body.currency,
                body.available_from,
                user_id,
            ),
        )

    await commands.audit(
        conn,
        business,
        actor,
        "property.listing_saved",
        "property_listing",
        str(object_id),
        {"location_id": str(item.location_id), "revision": next_revision, "state": body.state},
    )
    await commands.complete(conn, scope, ListingReceipt(revision=next_revision))
    return await _revision(conn, object_id, next_revision)
