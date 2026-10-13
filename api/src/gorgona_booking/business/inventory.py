"""J1 commands for materials and storage places: shared receipts and audit, no money."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from uuid import UUID

import psycopg

from gorgona_booking.booking.idempotency import IdempotencyScope
from gorgona_booking.business import commands, modules
from gorgona_booking.business.inventory_contracts import (
    InventoryReceipt,
    ItemInput,
    ItemList,
    ItemView,
    PlaceInput,
    PlaceList,
    PlaceView,
)
from gorgona_booking.business.module_gate import INVENTORY_MODULE, module_writes, require_module
from gorgona_booking.business.readiness_registry import at_least
from gorgona_booking.db.pool import RuntimeConnection
from gorgona_booking.errors import ConflictError, InvalidReferenceError, NotFoundError
from gorgona_booking.tenancy.authorization import PermissionDeniedError


class InventoryNotReadyError(ConflictError):
    code = "MODULE_NOT_READY"


class InventoryConflictError(ConflictError):
    code = "INVENTORY_CONFLICT"


async def require_inventory(conn: RuntimeConnection, business: UUID) -> None:
    current = modules.MODULES_BY_ID[INVENTORY_MODULE]
    if not current.enableable or not at_least(current.readiness, modules.MINIMUM_READINESS):
        raise InventoryNotReadyError("Inventory has not been accepted", module_id=INVENTORY_MODULE)
    await require_module(conn, business, INVENTORY_MODULE)
    for dependency in current.depends_on:
        if modules.MODULES_BY_ID[dependency].kind == modules.ModuleKind.OPTIONAL:
            await require_module(conn, business, dependency)


@asynccontextmanager
async def _writes(conn: RuntimeConnection, business: UUID) -> AsyncIterator[None]:
    await require_inventory(conn, business)
    try:
        async with conn.transaction(), module_writes(INVENTORY_MODULE):
            yield
            # Surface deferred integrity failures before returning the API result.
            await conn.execute("set constraints all immediate")
            await conn.execute("set constraints all deferred")
    except psycopg.errors.UniqueViolation as exc:
        raise InventoryConflictError("This inventory record already exists") from exc
    except psycopg.errors.ForeignKeyViolation as exc:
        raise InvalidReferenceError("An inventory reference is unavailable") from exc
    except psycopg.errors.InsufficientPrivilege as exc:
        raise PermissionDeniedError("This inventory change is outside your access") from exc
    except psycopg.DatabaseError as exc:
        if exc.sqlstate == "GBS01":
            raise InventoryConflictError("The inventory revision has changed") from exc
        if exc.sqlstate == "23514":
            raise InvalidReferenceError("This inventory state or reference is invalid") from exc
        raise


async def _finish(
    conn: RuntimeConnection,
    business: UUID,
    actor: str,
    kind: str,
    scope: IdempotencyScope,
    receipt: InventoryReceipt,
) -> None:
    await commands.audit(
        conn,
        business,
        actor,
        f"inventory.{kind}",
        kind,
        str(receipt.subject_id),
        {"revision": receipt.revision},
    )
    await commands.complete(conn, scope, receipt)


def _item(business: UUID, row: tuple[object, ...]) -> ItemView:
    return ItemView.model_validate(
        {
            "business_id": business,
            "item_id": row[0],
            "code": row[1],
            "unit": row[2],
            "quantity_scale": row[3],
            "revision": row[4],
            "name": row[5],
            "archived": row[6],
        }
    )


def _place(business: UUID, row: tuple[object, ...]) -> PlaceView:
    return PlaceView.model_validate(
        {
            "business_id": business,
            "place_id": row[0],
            "location_id": row[1],
            "code": row[2],
            "revision": row[3],
            "name": row[4],
            "archived": row[5],
        }
    )


async def load_item(
    conn: RuntimeConnection, business: UUID, item: UUID, revision: int | None = None
) -> ItemView:
    row = await (
        await conn.execute(
            "select s.id,s.code,s.unit,s.quantity_scale,v.revision,v.name,v.archived "
            "from gba.stock_items s join gba.stock_item_versions v "
            "on v.tenant_id=s.tenant_id and v.item_id=s.id "
            "where s.tenant_id=%s and s.id=%s and (%s::integer is null or v.revision=%s) "
            "order by v.revision desc limit 1",
            (business, item, revision, revision),
        )
    ).fetchone()
    if row is None:
        raise NotFoundError("Material not found")
    return _item(business, row)


async def save_item(
    conn: RuntimeConnection,
    business: UUID,
    item: UUID,
    user: UUID,
    actor: str,
    key: str,
    body: ItemInput,
) -> ItemView:
    async with _writes(conn, business):
        scope = IdempotencyScope(business, actor, "inventory.item", key)
        receipt = await commands.claim(
            conn,
            scope,
            commands.fingerprint({"id": str(item), **body.model_dump(mode="json")}),
            InventoryReceipt,
        )
        if receipt is not None:
            return await load_item(conn, business, item, receipt.revision)
        if body.expected_revision == 0:
            await conn.execute(
                "insert into gba.stock_items (tenant_id,id,code,unit,quantity_scale) "
                "values (%s,%s,%s,%s,%s)",
                (business, item, body.code, body.unit, body.quantity_scale),
            )
        else:
            current = await load_item(conn, business, item)
            if (current.code, current.unit, current.quantity_scale) != (
                body.code,
                body.unit,
                body.quantity_scale,
            ):
                raise InvalidReferenceError("A material keeps its code, unit and quantity scale")
        revision = body.expected_revision + 1
        await conn.execute(
            "insert into gba.stock_item_versions "
            "(tenant_id,item_id,revision,name,archived,created_by) values (%s,%s,%s,%s,%s,%s)",
            (business, item, revision, body.name, body.archived, user),
        )
        await _finish(
            conn,
            business,
            actor,
            "item",
            scope,
            InventoryReceipt(subject_id=item, revision=revision),
        )
        return await load_item(conn, business, item, revision)


async def list_items(
    conn: RuntimeConnection, business: UUID, after: UUID | None, limit: int
) -> ItemList:
    rows = await (
        await conn.execute(
            "select s.id,s.code,s.unit,s.quantity_scale,v.revision,v.name,v.archived "
            "from gba.stock_items s join lateral (select revision,name,archived "
            "from gba.stock_item_versions where tenant_id=s.tenant_id and item_id=s.id "
            "order by revision desc limit 1) v on true "
            "where s.tenant_id=%s and (%s::uuid is null or s.id>%s) order by s.id limit %s",
            (business, after, after, limit + 1),
        )
    ).fetchall()
    items = tuple(_item(business, row) for row in rows[:limit])
    return ItemList(items=items, next_cursor=items[-1].item_id if len(rows) > limit else None)


async def load_place(
    conn: RuntimeConnection, business: UUID, place: UUID, revision: int | None = None
) -> PlaceView:
    row = await (
        await conn.execute(
            "select s.id,s.location_id,s.code,v.revision,v.name,v.archived "
            "from gba.stock_places s join gba.stock_place_versions v "
            "on v.tenant_id=s.tenant_id and v.place_id=s.id "
            "where s.tenant_id=%s and s.id=%s and (%s::integer is null or v.revision=%s) "
            "order by v.revision desc limit 1",
            (business, place, revision, revision),
        )
    ).fetchone()
    if row is None:
        raise NotFoundError("Storage place not found")
    return _place(business, row)


async def save_place(
    conn: RuntimeConnection,
    business: UUID,
    place: UUID,
    user: UUID,
    actor: str,
    key: str,
    body: PlaceInput,
) -> PlaceView:
    async with _writes(conn, business):
        scope = IdempotencyScope(business, actor, "inventory.place", key)
        receipt = await commands.claim(
            conn,
            scope,
            commands.fingerprint({"id": str(place), **body.model_dump(mode="json")}),
            InventoryReceipt,
        )
        if receipt is not None:
            return await load_place(conn, business, place, receipt.revision)
        if body.expected_revision == 0:
            await conn.execute(
                "insert into gba.stock_places (tenant_id,id,location_id,code) values (%s,%s,%s,%s)",
                (business, place, body.location_id, body.code),
            )
        else:
            current = await load_place(conn, business, place)
            if (current.location_id, current.code) != (body.location_id, body.code):
                raise InvalidReferenceError("A storage place keeps its branch and code")
        revision = body.expected_revision + 1
        await conn.execute(
            "insert into gba.stock_place_versions "
            "(tenant_id,place_id,revision,name,archived,created_by) values (%s,%s,%s,%s,%s,%s)",
            (business, place, revision, body.name, body.archived, user),
        )
        await _finish(
            conn,
            business,
            actor,
            "place",
            scope,
            InventoryReceipt(subject_id=place, revision=revision),
        )
        return await load_place(conn, business, place, revision)


async def list_places(
    conn: RuntimeConnection, business: UUID, after: UUID | None, limit: int
) -> PlaceList:
    rows = await (
        await conn.execute(
            "select s.id,s.location_id,s.code,v.revision,v.name,v.archived "
            "from gba.stock_places s join lateral (select revision,name,archived "
            "from gba.stock_place_versions where tenant_id=s.tenant_id and place_id=s.id "
            "order by revision desc limit 1) v on true "
            "where s.tenant_id=%s and (%s::uuid is null or s.id>%s) order by s.id limit %s",
            (business, after, after, limit + 1),
        )
    ).fetchall()
    items = tuple(_place(business, row) for row in rows[:limit])
    return PlaceList(items=items, next_cursor=items[-1].place_id if len(rows) > limit else None)
