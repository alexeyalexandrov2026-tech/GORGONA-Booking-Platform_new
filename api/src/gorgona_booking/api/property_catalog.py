"""Internal, tenant-scoped property catalog."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Query, Request

from gorgona_booking.api.businesses import CurrentPrincipal, MutationKey
from gorgona_booking.api.deps import runtime_pool
from gorgona_booking.api.request_id import get_request_id
from gorgona_booking.auth.permissions import Permission
from gorgona_booking.business import property_catalog as catalog
from gorgona_booking.db.schema_guard import assert_location_scope_ready
from gorgona_booking.tenancy.authorization import TenantAccess, authorized_tenant

router = APIRouter(prefix="/v1/businesses/{business_id}/property/objects", tags=["property"])


@asynccontextmanager
async def _access(
    business_id: UUID, request: Request, principal: CurrentPrincipal, permission: Permission
) -> AsyncIterator[TenantAccess]:
    async with authorized_tenant(
        runtime_pool(request),
        principal,
        business_id,
        permission,
        allow_location_scope=permission == Permission.PROPERTY_READ,
        request_id=get_request_id(request),
    ) as access:
        if access.location_id is None:
            await assert_location_scope_ready(access.conn)
        yield access


@router.get("")
async def list_objects(
    business_id: UUID, request: Request, principal: CurrentPrincipal, after: UUID | None = None
) -> catalog.PropertyList:
    async with _access(business_id, request, principal, Permission.PROPERTY_READ) as access:
        return await catalog.list_properties(access.conn, after)


@router.get("/{object_id}")
async def get_object(
    business_id: UUID, object_id: UUID, request: Request, principal: CurrentPrincipal
) -> catalog.PropertyView:
    async with _access(business_id, request, principal, Permission.PROPERTY_READ) as access:
        return await catalog.get_property(access.conn, object_id)


@router.get("/{object_id}/history")
async def object_history(
    business_id: UUID,
    object_id: UUID,
    request: Request,
    principal: CurrentPrincipal,
    after: Annotated[int, Query(ge=0, le=2_147_483_647)] = 0,
) -> catalog.PropertyHistory:
    async with _access(business_id, request, principal, Permission.PROPERTY_MANAGE) as access:
        return await catalog.get_history(access.conn, object_id, after)


@router.put("/{object_id}")
async def put_object(
    business_id: UUID,
    object_id: UUID,
    body: catalog.PropertyInput,
    request: Request,
    principal: CurrentPrincipal,
    idempotency_key: MutationKey,
) -> catalog.PropertyRevision:
    async with _access(business_id, request, principal, Permission.PROPERTY_MANAGE) as access:
        return await catalog.save_property(
            access.conn,
            business_id,
            object_id,
            user_id=principal.user_id,
            actor=principal.actor,
            key=idempotency_key,
            body=body,
        )
