"""Inventory API of J1 and J5; its permissions never delegate or grant support access."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Path, Query, Request

from gorgona_booking.api.businesses import CurrentPrincipal, MutationKey
from gorgona_booking.api.deps import runtime_pool
from gorgona_booking.api.request_id import get_request_id
from gorgona_booking.auth.permissions import Permission
from gorgona_booking.business import inventory as service
from gorgona_booking.business import inventory_commands
from gorgona_booking.business.inventory_contracts import (
    CommandReference,
    CommandStatus,
    ItemInput,
    ItemList,
    ItemView,
    PlaceInput,
    PlaceList,
    PlaceView,
)
from gorgona_booking.db.inventory_guard import assert_inventory_ready
from gorgona_booking.db.schema_guard import assert_location_scope_ready
from gorgona_booking.tenancy.authorization import (
    PermissionDeniedError,
    TenantAccess,
    authorized_tenant,
)

router = APIRouter(prefix="/v1/businesses/{business_id}/inventory", tags=["inventory"])
Revision = Annotated[int | None, Query(ge=1, le=2147483647)]
Limit = Annotated[int, Query(ge=1, le=100)]


@asynccontextmanager
async def _access(
    request: Request,
    principal: CurrentPrincipal,
    business_id: UUID,
    permission: Permission = Permission.INVENTORY_READ,
) -> AsyncIterator[TenantAccess]:
    async with authorized_tenant(
        runtime_pool(request),
        principal,
        business_id,
        permission,
        allow_location_scope=True,
        request_id=get_request_id(request),
    ) as access:
        await assert_location_scope_ready(access.conn)
        await assert_inventory_ready(access.conn)
        yield access


@router.get("/items")
async def get_items(
    business_id: UUID,
    request: Request,
    principal: CurrentPrincipal,
    after: UUID | None = None,
    limit: Limit = 100,
) -> ItemList:
    async with _access(request, principal, business_id) as access:
        return await service.list_items(access.conn, business_id, after, limit)


@router.get("/items/{item_id}")
async def get_item(
    business_id: UUID,
    item_id: UUID,
    request: Request,
    principal: CurrentPrincipal,
    revision: Revision = None,
) -> ItemView:
    async with _access(request, principal, business_id) as access:
        return await service.load_item(access.conn, business_id, item_id, revision)


@router.put("/items/{item_id}")
async def put_item(
    business_id: UUID,
    item_id: UUID,
    body: ItemInput,
    request: Request,
    principal: CurrentPrincipal,
    idempotency_key: MutationKey,
) -> ItemView:
    async with _access(request, principal, business_id, Permission.INVENTORY_MANAGE) as access:
        if access.location_id is not None:
            raise PermissionDeniedError("The material list requires company-wide access")
        return await service.save_item(
            access.conn,
            business_id,
            item_id,
            principal.user_id,
            principal.actor,
            idempotency_key,
            body,
        )


@router.get("/places")
async def get_places(
    business_id: UUID,
    request: Request,
    principal: CurrentPrincipal,
    after: UUID | None = None,
    limit: Limit = 100,
) -> PlaceList:
    async with _access(request, principal, business_id) as access:
        return await service.list_places(access.conn, business_id, after, limit)


@router.get("/places/{place_id}")
async def get_place(
    business_id: UUID,
    place_id: UUID,
    request: Request,
    principal: CurrentPrincipal,
    revision: Revision = None,
) -> PlaceView:
    async with _access(request, principal, business_id) as access:
        return await service.load_place(access.conn, business_id, place_id, revision)


@router.put("/places/{place_id}")
async def put_place(
    business_id: UUID,
    place_id: UUID,
    body: PlaceInput,
    request: Request,
    principal: CurrentPrincipal,
    idempotency_key: MutationKey,
) -> PlaceView:
    async with _access(request, principal, business_id, Permission.INVENTORY_MANAGE) as access:
        access.require_location(body.location_id)
        return await service.save_place(
            access.conn,
            business_id,
            place_id,
            principal.user_id,
            principal.actor,
            idempotency_key,
            body,
        )


# J5: a command whose answer was lost is settled by its key. Only the caller's own keys are
# read; cancelling an unresolved command makes its late copy a refused, reused key.
CommandKey = Annotated[str, Path(min_length=8, max_length=255, pattern=r"^[A-Za-z0-9._:-]+$")]


@router.post("/commands/{key}/resolve")
async def resolve_command(
    business_id: UUID,
    key: CommandKey,
    body: CommandReference,
    request: Request,
    principal: CurrentPrincipal,
) -> CommandStatus:
    async with _access(request, principal, business_id) as access:
        return await inventory_commands.resolve_command(
            access.conn, business_id, principal.actor, key, body
        )


@router.post("/commands/{key}/cancel")
async def cancel_command(
    business_id: UUID,
    key: CommandKey,
    body: CommandReference,
    request: Request,
    principal: CurrentPrincipal,
) -> CommandStatus:
    async with _access(request, principal, business_id) as access:
        return await inventory_commands.cancel_command(
            access.conn, business_id, principal.actor, key, body
        )
