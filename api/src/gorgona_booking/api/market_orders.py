"""HTTP routes for MARKET-01 Slice 2 (0142): multi-seller basket split into single-seller
orders, FIN-03 seller invoices, customer refund credit notes, and operator commercial fees.
"""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from uuid import UUID

from fastapi import APIRouter, Request

from gorgona_booking.api.businesses import CurrentPrincipal, MutationKey
from gorgona_booking.api.deps import runtime_pool
from gorgona_booking.api.request_id import get_request_id
from gorgona_booking.auth.permissions import ROLE_PERMISSIONS, Permission
from gorgona_booking.business import market_orders as mo
from gorgona_booking.db.schema_guard import assert_location_scope_ready
from gorgona_booking.tenancy.authorization import (
    PermissionDeniedError,
    TenantAccess,
    authorized_tenant,
)

router = APIRouter(prefix="/v1/businesses/{business_id}/market", tags=["market"])


@asynccontextmanager
async def _access(
    request: Request,
    principal: CurrentPrincipal,
    business_id: UUID,
    permission: Permission = Permission.MARKET_READ,
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
            if access.via != "platform" and Permission.FINANCE_MANAGE not in allowed:
                raise PermissionDeniedError(
                    "Insufficient permissions for marketplace financial settlement"
                )
        await assert_location_scope_ready(access.conn)
        yield access


@router.post("/baskets/checkout", response_model=mo.BasketCheckoutView)
async def post_basket_checkout(
    business_id: UUID,
    body: mo.BasketCheckoutInput,
    request: Request,
    principal: CurrentPrincipal,
    key: MutationKey,
) -> mo.BasketCheckoutView:
    async with _access(
        request,
        principal,
        business_id,
        Permission.MARKET_MANAGE,
        company_wide_finance=True,
    ) as access:
        return await mo.checkout_basket(
            access.conn,
            business_id,
            user_id=principal.user_id,
            actor=principal.actor,
            key=key,
            body=body,
        )


@router.get("/orders", response_model=mo.MarketOrderList)
async def get_market_orders(
    business_id: UUID,
    request: Request,
    principal: CurrentPrincipal,
    storefront_id: UUID | None = None,
    basket_id: UUID | None = None,
) -> mo.MarketOrderList:
    async with _access(request, principal, business_id) as access:
        return await mo.list_market_orders(
            access.conn,
            business_id,
            storefront_id=storefront_id,
            basket_id=basket_id,
        )


@router.get("/orders/{order_id}", response_model=mo.MarketOrderView)
async def get_market_order(
    business_id: UUID,
    order_id: UUID,
    request: Request,
    principal: CurrentPrincipal,
) -> mo.MarketOrderView:
    async with _access(request, principal, business_id) as access:
        return await mo.get_market_order(access.conn, business_id, order_id)


@router.post("/orders/{order_id}/refund", response_model=mo.MarketOrderView)
async def post_market_order_refund(
    business_id: UUID,
    order_id: UUID,
    body: mo.MarketOrderRefundInput,
    request: Request,
    principal: CurrentPrincipal,
    key: MutationKey,
) -> mo.MarketOrderView:
    async with _access(
        request,
        principal,
        business_id,
        Permission.MARKET_MANAGE,
        company_wide_finance=True,
    ) as access:
        return await mo.refund_market_order(
            access.conn,
            business_id,
            order_id,
            user_id=principal.user_id,
            actor=principal.actor,
            key=key,
            body=body,
        )


@router.get("/operator-fees", response_model=mo.OperatorFeeList)
async def get_operator_fees(
    business_id: UUID,
    request: Request,
    principal: CurrentPrincipal,
    marketplace_id: UUID | None = None,
) -> mo.OperatorFeeList:
    async with _access(request, principal, business_id) as access:
        return await mo.list_operator_fees(access.conn, business_id, marketplace_id=marketplace_id)
