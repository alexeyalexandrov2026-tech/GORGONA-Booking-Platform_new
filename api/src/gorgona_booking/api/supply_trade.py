"""HTTP routes for SUPPLY-01 Slice 3 (0140): channel & contract price lists,
retail/wholesale & 3PL fulfillment orders, owner-isolated lot/serial shipments
(STOCK-01 COGS write_off + FIN-03 receivable invoice), and customer returns
(STOCK-01 return + FIN-03 credit note draft).
"""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from uuid import UUID

from fastapi import APIRouter, Request

from gorgona_booking.api.businesses import CurrentPrincipal, MutationKey
from gorgona_booking.api.deps import runtime_pool
from gorgona_booking.api.request_id import get_request_id
from gorgona_booking.auth.permissions import ROLE_PERMISSIONS, Permission
from gorgona_booking.business import supply_trade as domain
from gorgona_booking.db.schema_guard import assert_location_scope_ready
from gorgona_booking.tenancy.authorization import (
    PermissionDeniedError,
    TenantAccess,
    authorized_tenant,
)

router = APIRouter(prefix="/v1/businesses/{business_id}/supply", tags=["supply"])


@asynccontextmanager
async def _access(
    request: Request,
    principal: CurrentPrincipal,
    business_id: UUID,
    permission: Permission = Permission.SUPPLY_READ,
    *,
    company_wide_finance: bool = False,
) -> AsyncIterator[TenantAccess]:
    async with authorized_tenant(
        runtime_pool(request),
        principal,
        business_id,
        permission,
        request_id=get_request_id(request),
        allow_location_scope=not company_wide_finance,
    ) as access:
        if company_wide_finance:
            allowed = ROLE_PERMISSIONS.get(access.role or "", frozenset())
            if access.via != "platform" and (
                Permission.FINANCE_MANAGE not in allowed
                or Permission.INVENTORY_MANAGE not in allowed
            ):
                raise PermissionDeniedError("Insufficient permissions for supply financial posting")
        await assert_location_scope_ready(access.conn)
        yield access


@router.get("/price-lists", response_model=domain.PriceListCollection)
async def list_price_lists(
    business_id: UUID,
    request: Request,
    principal: CurrentPrincipal,
    location_id: UUID | None = None,
) -> domain.PriceListCollection:
    async with _access(request, principal, business_id) as access:
        return await domain.list_price_lists(access.conn, business_id, location_id=location_id)


@router.get("/price-lists/{price_list_id}", response_model=domain.PriceListView)
async def get_price_list(
    business_id: UUID,
    price_list_id: UUID,
    request: Request,
    principal: CurrentPrincipal,
) -> domain.PriceListView:
    async with _access(request, principal, business_id) as access:
        return await domain.get_price_list(access.conn, business_id, price_list_id)


@router.put("/price-lists/{price_list_id}", response_model=domain.PriceListView)
async def save_price_list(
    business_id: UUID,
    price_list_id: UUID,
    body: domain.PriceListInput,
    request: Request,
    principal: CurrentPrincipal,
    key: MutationKey,
) -> domain.PriceListView:
    async with _access(request, principal, business_id, Permission.SUPPLY_MANAGE) as access:
        return await domain.save_price_list(
            access.conn,
            business_id,
            price_list_id,
            user_id=principal.user_id,
            actor=principal.actor,
            key=key,
            body=body,
        )


@router.get("/orders", response_model=domain.TradeOrderList)
async def list_trade_orders(
    business_id: UUID,
    request: Request,
    principal: CurrentPrincipal,
    location_id: UUID | None = None,
    goods_owner_id: UUID | None = None,
) -> domain.TradeOrderList:
    async with _access(request, principal, business_id) as access:
        return await domain.list_trade_orders(
            access.conn,
            business_id,
            location_id=location_id,
            goods_owner_id=goods_owner_id,
        )


@router.get("/orders/{order_id}", response_model=domain.TradeOrderView)
async def get_trade_order(
    business_id: UUID,
    order_id: UUID,
    request: Request,
    principal: CurrentPrincipal,
) -> domain.TradeOrderView:
    async with _access(request, principal, business_id) as access:
        return await domain.get_trade_order(access.conn, business_id, order_id)


@router.put("/orders/{order_id}", response_model=domain.TradeOrderView)
async def save_trade_order(
    business_id: UUID,
    order_id: UUID,
    body: domain.TradeOrderInput,
    request: Request,
    principal: CurrentPrincipal,
    key: MutationKey,
) -> domain.TradeOrderView:
    async with _access(request, principal, business_id, Permission.SUPPLY_WORK) as access:
        return await domain.save_trade_order(
            access.conn,
            business_id,
            order_id,
            user_id=principal.user_id,
            actor=principal.actor,
            key=key,
            body=body,
        )


@router.get("/orders/{order_id}/shipments", response_model=domain.OrderShipmentList)
async def list_order_shipments(
    business_id: UUID,
    order_id: UUID,
    request: Request,
    principal: CurrentPrincipal,
) -> domain.OrderShipmentList:
    async with _access(request, principal, business_id) as access:
        return await domain.list_order_shipments(access.conn, business_id, order_id)


@router.post("/orders/{order_id}/shipments", response_model=domain.OrderShipmentView)
async def post_order_shipment(
    business_id: UUID,
    order_id: UUID,
    body: domain.OrderShipmentInput,
    request: Request,
    principal: CurrentPrincipal,
    key: MutationKey,
) -> domain.OrderShipmentView:
    async with _access(
        request,
        principal,
        business_id,
        Permission.SUPPLY_WORK,
        company_wide_finance=True,
    ) as access:
        return await domain.post_order_shipment(
            access.conn,
            business_id,
            order_id,
            user_id=principal.user_id,
            actor=principal.actor,
            key=key,
            body=body,
        )


@router.get("/orders/{order_id}/returns", response_model=domain.OrderReturnList)
async def list_order_returns(
    business_id: UUID,
    order_id: UUID,
    request: Request,
    principal: CurrentPrincipal,
) -> domain.OrderReturnList:
    async with _access(request, principal, business_id) as access:
        return await domain.list_order_returns(access.conn, business_id, order_id)


@router.post("/orders/{order_id}/returns", response_model=domain.OrderReturnView)
async def post_order_return(
    business_id: UUID,
    order_id: UUID,
    body: domain.OrderReturnInput,
    request: Request,
    principal: CurrentPrincipal,
    key: MutationKey,
) -> domain.OrderReturnView:
    async with _access(
        request,
        principal,
        business_id,
        Permission.SUPPLY_WORK,
        company_wide_finance=True,
    ) as access:
        return await domain.post_order_return(
            access.conn,
            business_id,
            order_id,
            user_id=principal.user_id,
            actor=principal.actor,
            key=key,
            body=body,
        )
