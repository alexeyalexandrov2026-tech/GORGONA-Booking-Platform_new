"""HTTP routes for MARKET-01 Slice 1 (0141): business storefronts, listings with strict
public field projection, and client-operated marketplaces.
"""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from uuid import UUID

from fastapi import APIRouter, Request

from gorgona_booking.api.businesses import CurrentPrincipal, MutationKey
from gorgona_booking.api.deps import runtime_pool
from gorgona_booking.api.request_id import get_request_id
from gorgona_booking.auth.permissions import Permission
from gorgona_booking.business import market_storefronts as ms
from gorgona_booking.db.schema_guard import assert_location_scope_ready
from gorgona_booking.tenancy.authorization import TenantAccess, authorized_tenant

router = APIRouter(prefix="/v1/businesses/{business_id}/market", tags=["market"])


@asynccontextmanager
async def _access(
    request: Request,
    principal: CurrentPrincipal,
    business_id: UUID,
    permission: Permission = Permission.MARKET_READ,
) -> AsyncIterator[TenantAccess]:
    async with authorized_tenant(
        runtime_pool(request),
        principal,
        business_id,
        permission,
        request_id=get_request_id(request),
        allow_location_scope=True,
    ) as access:
        await assert_location_scope_ready(access.conn)
        yield access


@router.get("/storefronts", response_model=ms.StorefrontList)
async def get_storefronts(
    business_id: UUID,
    request: Request,
    principal: CurrentPrincipal,
    location_id: UUID | None = None,
) -> ms.StorefrontList:
    async with _access(request, principal, business_id) as access:
        return await ms.list_storefronts(access.conn, business_id, location_id=location_id)


@router.get("/storefronts/{storefront_id}", response_model=ms.StorefrontView)
async def get_storefront(
    business_id: UUID,
    storefront_id: UUID,
    request: Request,
    principal: CurrentPrincipal,
) -> ms.StorefrontView:
    async with _access(request, principal, business_id) as access:
        return await ms.get_storefront(access.conn, business_id, storefront_id)


@router.put("/storefronts/{storefront_id}", response_model=ms.StorefrontView)
async def put_storefront(
    business_id: UUID,
    storefront_id: UUID,
    body: ms.StorefrontInput,
    request: Request,
    principal: CurrentPrincipal,
    key: MutationKey,
) -> ms.StorefrontView:
    async with _access(request, principal, business_id, Permission.MARKET_MANAGE) as access:
        return await ms.save_storefront(
            access.conn,
            business_id,
            storefront_id,
            user_id=principal.user_id,
            actor=principal.actor,
            key=key,
            body=body,
        )


@router.get(
    "/storefronts/{storefront_id}/public-catalog", response_model=ms.PublicStorefrontCatalog
)
async def get_public_catalog(
    business_id: UUID,
    storefront_id: UUID,
    request: Request,
    principal: CurrentPrincipal,
    category: str | None = None,
) -> ms.PublicStorefrontCatalog:
    async with _access(request, principal, business_id) as access:
        return await ms.get_public_storefront_catalog(
            access.conn, business_id, storefront_id, category=category
        )


@router.get("/listings", response_model=ms.ListingList)
async def get_listings(
    business_id: UUID,
    request: Request,
    principal: CurrentPrincipal,
    storefront_id: UUID | None = None,
) -> ms.ListingList:
    async with _access(request, principal, business_id) as access:
        return await ms.list_listings(access.conn, business_id, storefront_id=storefront_id)


@router.get("/listings/{listing_id}", response_model=ms.ListingView)
async def get_listing(
    business_id: UUID,
    listing_id: UUID,
    request: Request,
    principal: CurrentPrincipal,
) -> ms.ListingView:
    async with _access(request, principal, business_id) as access:
        return await ms.get_listing(access.conn, business_id, listing_id)


@router.put("/listings/{listing_id}", response_model=ms.ListingView)
async def put_listing(
    business_id: UUID,
    listing_id: UUID,
    body: ms.ListingInput,
    request: Request,
    principal: CurrentPrincipal,
    key: MutationKey,
) -> ms.ListingView:
    async with _access(request, principal, business_id, Permission.MARKET_MANAGE) as access:
        return await ms.save_listing(
            access.conn,
            business_id,
            listing_id,
            user_id=principal.user_id,
            actor=principal.actor,
            key=key,
            body=body,
        )


@router.get("/marketplaces", response_model=ms.MarketplaceList)
async def get_marketplaces(
    business_id: UUID,
    request: Request,
    principal: CurrentPrincipal,
    location_id: UUID | None = None,
) -> ms.MarketplaceList:
    async with _access(request, principal, business_id) as access:
        return await ms.list_marketplaces(access.conn, business_id, location_id=location_id)


@router.put("/marketplaces/{marketplace_id}", response_model=ms.MarketplaceView)
async def put_marketplace(
    business_id: UUID,
    marketplace_id: UUID,
    body: ms.MarketplaceInput,
    request: Request,
    principal: CurrentPrincipal,
    key: MutationKey,
) -> ms.MarketplaceView:
    async with _access(request, principal, business_id, Permission.MARKET_MANAGE) as access:
        return await ms.save_marketplace(
            access.conn,
            business_id,
            marketplace_id,
            user_id=principal.user_id,
            actor=principal.actor,
            key=key,
            body=body,
        )


@router.get(
    "/marketplaces/{marketplace_id}/sellers",
    response_model=ms.SellerConnectionList,
)
async def get_seller_connections(
    business_id: UUID,
    marketplace_id: UUID,
    request: Request,
    principal: CurrentPrincipal,
) -> ms.SellerConnectionList:
    async with _access(request, principal, business_id) as access:
        return await ms.list_seller_connections(access.conn, business_id, marketplace_id)


@router.put(
    "/marketplaces/{marketplace_id}/sellers/{connection_id}",
    response_model=ms.SellerConnectionView,
)
async def put_seller_connection(
    business_id: UUID,
    marketplace_id: UUID,
    connection_id: UUID,
    body: ms.SellerConnectionInput,
    request: Request,
    principal: CurrentPrincipal,
    key: MutationKey,
) -> ms.SellerConnectionView:
    async with _access(request, principal, business_id, Permission.MARKET_MANAGE) as access:
        return await ms.save_seller_connection(
            access.conn,
            business_id,
            marketplace_id,
            connection_id,
            user_id=principal.user_id,
            actor=principal.actor,
            key=key,
            body=body,
        )
