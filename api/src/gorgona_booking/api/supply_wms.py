"""SUPPLY-01 Slice 1 API routes: Goods owners, warehouse bins, lots, serial units, and WMS
movements."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from uuid import UUID

from fastapi import APIRouter, Request

from gorgona_booking.api.businesses import CurrentPrincipal, MutationKey
from gorgona_booking.api.deps import runtime_pool
from gorgona_booking.api.request_id import get_request_id
from gorgona_booking.auth.permissions import Permission
from gorgona_booking.business import supply_wms as sw
from gorgona_booking.db.schema_guard import assert_location_scope_ready
from gorgona_booking.tenancy.authorization import TenantAccess, authorized_tenant

router = APIRouter(prefix="/v1/businesses/{business_id}/supply", tags=["supply"])


@asynccontextmanager
async def _access(
    request: Request,
    principal: CurrentPrincipal,
    business_id: UUID,
    permission: Permission = Permission.SUPPLY_READ,
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


@router.get("/owners")
async def get_owners(
    business_id: UUID,
    request: Request,
    principal: CurrentPrincipal,
    location_id: UUID | None = None,
) -> sw.GoodsOwnerList:
    async with _access(request, principal, business_id) as access:
        return await sw.list_goods_owners(access.conn, business_id, location_id=location_id)


@router.put("/owners/{owner_id}")
async def put_owner(
    business_id: UUID,
    owner_id: UUID,
    body: sw.GoodsOwnerInput,
    request: Request,
    principal: CurrentPrincipal,
    idempotency_key: MutationKey,
) -> sw.GoodsOwnerView:
    async with _access(request, principal, business_id, Permission.SUPPLY_MANAGE) as access:
        return await sw.save_goods_owner(
            access.conn,
            business_id,
            owner_id,
            user_id=principal.user_id,
            actor=principal.actor,
            key=idempotency_key,
            body=body,
        )


@router.get("/bins")
async def get_bins(
    business_id: UUID,
    request: Request,
    principal: CurrentPrincipal,
    location_id: UUID | None = None,
    place_id: UUID | None = None,
) -> sw.WarehouseBinList:
    async with _access(request, principal, business_id) as access:
        return await sw.list_warehouse_bins(
            access.conn, business_id, location_id=location_id, place_id=place_id
        )


@router.put("/bins/{bin_id}")
async def put_bin(
    business_id: UUID,
    bin_id: UUID,
    body: sw.WarehouseBinInput,
    request: Request,
    principal: CurrentPrincipal,
    idempotency_key: MutationKey,
) -> sw.WarehouseBinView:
    async with _access(request, principal, business_id, Permission.SUPPLY_MANAGE) as access:
        return await sw.save_warehouse_bin(
            access.conn,
            business_id,
            bin_id,
            user_id=principal.user_id,
            actor=principal.actor,
            key=idempotency_key,
            body=body,
        )


@router.get("/lots")
async def get_lots(
    business_id: UUID,
    request: Request,
    principal: CurrentPrincipal,
    location_id: UUID | None = None,
    goods_owner_id: UUID | None = None,
    item_id: UUID | None = None,
) -> sw.LotList:
    async with _access(request, principal, business_id) as access:
        return await sw.list_lots(
            access.conn,
            business_id,
            location_id=location_id,
            goods_owner_id=goods_owner_id,
            item_id=item_id,
        )


@router.put("/lots/{lot_id}")
async def put_lot(
    business_id: UUID,
    lot_id: UUID,
    body: sw.LotInput,
    request: Request,
    principal: CurrentPrincipal,
    idempotency_key: MutationKey,
) -> sw.LotView:
    async with _access(request, principal, business_id, Permission.SUPPLY_WORK) as access:
        return await sw.save_lot(
            access.conn,
            business_id,
            lot_id,
            user_id=principal.user_id,
            actor=principal.actor,
            key=idempotency_key,
            body=body,
        )


@router.get("/lot-balances")
async def get_lot_balances(
    business_id: UUID,
    request: Request,
    principal: CurrentPrincipal,
    location_id: UUID | None = None,
    goods_owner_id: UUID | None = None,
    item_id: UUID | None = None,
    bin_id: UUID | None = None,
    lot_id: UUID | None = None,
) -> sw.LotBalanceList:
    async with _access(request, principal, business_id) as access:
        return await sw.list_lot_balances(
            access.conn,
            business_id,
            location_id=location_id,
            goods_owner_id=goods_owner_id,
            item_id=item_id,
            bin_id=bin_id,
            lot_id=lot_id,
        )


@router.get("/serials")
async def get_serials(
    business_id: UUID,
    request: Request,
    principal: CurrentPrincipal,
    location_id: UUID | None = None,
    goods_owner_id: UUID | None = None,
    lot_id: UUID | None = None,
    item_id: UUID | None = None,
    state: sw.SerialState | None = None,
) -> sw.SerialUnitList:
    async with _access(request, principal, business_id) as access:
        return await sw.list_serial_units(
            access.conn,
            business_id,
            location_id=location_id,
            goods_owner_id=goods_owner_id,
            lot_id=lot_id,
            item_id=item_id,
            state=state,
        )


@router.get("/movements")
async def get_movements(
    business_id: UUID,
    request: Request,
    principal: CurrentPrincipal,
    location_id: UUID | None = None,
    goods_owner_id: UUID | None = None,
    lot_id: UUID | None = None,
) -> sw.WmsMovementList:
    async with _access(request, principal, business_id) as access:
        return await sw.list_wms_movements(
            access.conn,
            business_id,
            location_id=location_id,
            goods_owner_id=goods_owner_id,
            lot_id=lot_id,
        )


@router.post("/movements/inbound")
async def post_inbound_movement(
    business_id: UUID,
    body: sw.InboundPutawayInput,
    request: Request,
    principal: CurrentPrincipal,
    idempotency_key: MutationKey,
) -> sw.WmsMovementView:
    async with _access(request, principal, business_id, Permission.SUPPLY_WORK) as access:
        return await sw.record_inbound_putaway(
            access.conn,
            business_id,
            user_id=principal.user_id,
            actor=principal.actor,
            key=idempotency_key,
            body=body,
        )


@router.post("/movements/relocate")
async def post_relocate_movement(
    business_id: UUID,
    body: sw.BinRelocationInput,
    request: Request,
    principal: CurrentPrincipal,
    idempotency_key: MutationKey,
) -> sw.WmsMovementView:
    async with _access(request, principal, business_id, Permission.SUPPLY_WORK) as access:
        return await sw.record_bin_relocation(
            access.conn,
            business_id,
            user_id=principal.user_id,
            actor=principal.actor,
            key=idempotency_key,
            body=body,
        )


@router.post("/movements/outbound")
async def post_outbound_movement(
    business_id: UUID,
    body: sw.OutboundPickInput,
    request: Request,
    principal: CurrentPrincipal,
    idempotency_key: MutationKey,
) -> sw.WmsMovementView:
    async with _access(request, principal, business_id, Permission.SUPPLY_WORK) as access:
        return await sw.record_outbound_pick(
            access.conn,
            business_id,
            user_id=principal.user_id,
            actor=principal.actor,
            key=idempotency_key,
            body=body,
        )
