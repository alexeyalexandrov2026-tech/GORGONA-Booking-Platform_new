"""HTTP routes for SPECIAL-03 (0147): Assets, inspections, work orders and safety incidents."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from uuid import UUID

from fastapi import APIRouter, Request

from gorgona_booking.api.businesses import CurrentPrincipal, MutationKey
from gorgona_booking.api.deps import runtime_pool
from gorgona_booking.api.request_id import get_request_id
from gorgona_booking.auth.permissions import Permission
from gorgona_booking.business import special_assets as sa
from gorgona_booking.db.schema_guard import assert_location_scope_ready
from gorgona_booking.tenancy.authorization import TenantAccess, authorized_tenant

router = APIRouter(prefix="/v1/businesses/{business_id}/assets", tags=["assets"])


@asynccontextmanager
async def _access(
    request: Request,
    principal: CurrentPrincipal,
    business_id: UUID,
    permission: Permission = Permission.ASSETS_READ,
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


@router.get("/items", response_model=sa.ManagedAssetList)
async def get_assets(
    business_id: UUID,
    request: Request,
    principal: CurrentPrincipal,
    location_id: UUID | None = None,
) -> sa.ManagedAssetList:
    async with _access(request, principal, business_id) as access:
        return await sa.list_assets(access.conn, business_id, location_id=location_id)


@router.put("/items/{asset_id}", response_model=sa.ManagedAssetView)
async def put_asset(
    business_id: UUID,
    asset_id: UUID,
    body: sa.ManagedAssetInput,
    request: Request,
    principal: CurrentPrincipal,
    key: MutationKey,
) -> sa.ManagedAssetView:
    async with _access(request, principal, business_id, Permission.ASSETS_MANAGE) as access:
        return await sa.save_asset(
            access.conn,
            business_id,
            asset_id,
            user_id=principal.user_id,
            actor=principal.actor,
            key=key,
            body=body,
        )


@router.get("/inspections", response_model=sa.AssetInspectionList)
async def get_inspections(
    business_id: UUID,
    request: Request,
    principal: CurrentPrincipal,
    asset_id: UUID | None = None,
) -> sa.AssetInspectionList:
    async with _access(request, principal, business_id) as access:
        return await sa.list_inspections(access.conn, business_id, asset_id=asset_id)


@router.put("/inspections/{inspection_id}", response_model=sa.AssetInspectionView)
async def put_inspection(
    business_id: UUID,
    inspection_id: UUID,
    body: sa.AssetInspectionInput,
    request: Request,
    principal: CurrentPrincipal,
    key: MutationKey,
) -> sa.AssetInspectionView:
    async with _access(request, principal, business_id, Permission.ASSETS_WORK) as access:
        return await sa.record_inspection(
            access.conn,
            business_id,
            inspection_id,
            user_id=principal.user_id,
            actor=principal.actor,
            key=key,
            body=body,
        )


@router.get("/work-orders", response_model=sa.AssetWorkOrderList)
async def get_work_orders(
    business_id: UUID,
    request: Request,
    principal: CurrentPrincipal,
    asset_id: UUID | None = None,
) -> sa.AssetWorkOrderList:
    async with _access(request, principal, business_id) as access:
        return await sa.list_work_orders(access.conn, business_id, asset_id=asset_id)


@router.put("/work-orders/{work_order_id}", response_model=sa.AssetWorkOrderView)
async def put_work_order(
    business_id: UUID,
    work_order_id: UUID,
    body: sa.AssetWorkOrderInput,
    request: Request,
    principal: CurrentPrincipal,
    key: MutationKey,
) -> sa.AssetWorkOrderView:
    async with _access(request, principal, business_id, Permission.ASSETS_WORK) as access:
        return await sa.save_work_order(
            access.conn,
            business_id,
            work_order_id,
            user_id=principal.user_id,
            actor=principal.actor,
            key=key,
            body=body,
        )


@router.get("/incidents", response_model=sa.AssetIncidentList)
async def get_incidents(
    business_id: UUID,
    request: Request,
    principal: CurrentPrincipal,
    asset_id: UUID | None = None,
) -> sa.AssetIncidentList:
    async with _access(request, principal, business_id) as access:
        return await sa.list_incidents(access.conn, business_id, asset_id=asset_id)


@router.put("/incidents/{incident_id}", response_model=sa.AssetIncidentView)
async def put_incident(
    business_id: UUID,
    incident_id: UUID,
    body: sa.AssetIncidentInput,
    request: Request,
    principal: CurrentPrincipal,
    key: MutationKey,
) -> sa.AssetIncidentView:
    async with _access(request, principal, business_id, Permission.ASSETS_WORK) as access:
        return await sa.save_incident(
            access.conn,
            business_id,
            incident_id,
            user_id=principal.user_id,
            actor=principal.actor,
            key=key,
            body=body,
        )
