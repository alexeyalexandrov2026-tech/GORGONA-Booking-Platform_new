"""M1 transport planning API (ADR-0028); never delegated in M1."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from uuid import UUID

from fastapi import APIRouter, Request

from gorgona_booking.api.businesses import CurrentPrincipal, MutationKey
from gorgona_booking.api.deps import runtime_pool
from gorgona_booking.api.request_id import get_request_id
from gorgona_booking.auth.permissions import Permission
from gorgona_booking.business import transport as service
from gorgona_booking.business.transport import (
    OrderInput,
    OrderList,
    OrderView,
    TripInput,
    TripList,
    TripView,
)
from gorgona_booking.db.schema_guard import assert_location_scope_ready
from gorgona_booking.errors import NotFoundError
from gorgona_booking.tenancy.authorization import TenantAccess, authorized_tenant

router = APIRouter(prefix="/v1/businesses/{business_id}/transport", tags=["transport"])


@asynccontextmanager
async def _access(
    request: Request,
    principal: CurrentPrincipal,
    business_id: UUID,
    permission: Permission = Permission.TRANSPORT_READ,
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
        yield access


@router.get("/orders")
async def get_orders(business_id: UUID, request: Request, principal: CurrentPrincipal) -> OrderList:
    async with _access(request, principal, business_id) as access:
        return await service.list_orders(access.conn)


@router.get("/orders/{order_id}")
async def get_order(
    business_id: UUID, order_id: UUID, request: Request, principal: CurrentPrincipal
) -> OrderView:
    async with _access(request, principal, business_id) as access:
        view = await service.load_order(access.conn, order_id)
        if view is None:
            raise NotFoundError("Order not found", order_id=str(order_id))
        return view


@router.put("/orders/{order_id}")
async def put_order(
    business_id: UUID,
    order_id: UUID,
    body: OrderInput,
    request: Request,
    principal: CurrentPrincipal,
    idempotency_key: MutationKey,
) -> OrderView:
    """ADR-0028 decision 3: the whole order and its loads, with the expected revision."""
    async with _access(request, principal, business_id, Permission.TRANSPORT_MANAGE) as access:
        return await service.save_order(
            access.conn,
            business_id,
            order_id,
            user_id=principal.user_id,
            actor=principal.actor,
            key=idempotency_key,
            body=body,
        )


@router.get("/trips")
async def get_trips(business_id: UUID, request: Request, principal: CurrentPrincipal) -> TripList:
    async with _access(request, principal, business_id) as access:
        return await service.list_trips(access.conn)


@router.get("/trips/{trip_id}")
async def get_trip(
    business_id: UUID, trip_id: UUID, request: Request, principal: CurrentPrincipal
) -> TripView:
    async with _access(request, principal, business_id) as access:
        view = await service.load_trip(access.conn, trip_id)
        if view is None:
            raise NotFoundError("Trip not found", trip_id=str(trip_id))
        return view


@router.put("/trips/{trip_id}")
async def put_trip(
    business_id: UUID,
    trip_id: UUID,
    body: TripInput,
    request: Request,
    principal: CurrentPrincipal,
    idempotency_key: MutationKey,
) -> TripView:
    """ADR-0028 decision 4: the whole planned trip, its stops and legs, with its revision."""
    async with _access(request, principal, business_id, Permission.TRANSPORT_MANAGE) as access:
        return await service.save_trip(
            access.conn,
            business_id,
            trip_id,
            user_id=principal.user_id,
            actor=principal.actor,
            key=idempotency_key,
            body=body,
        )
