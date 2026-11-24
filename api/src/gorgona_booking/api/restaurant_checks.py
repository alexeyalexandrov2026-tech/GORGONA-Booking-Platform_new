"""REST-01 Slice 3: independent guest checks, kitchen tickets and STOCK-01 write-offs."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Query, Request

from gorgona_booking.api.businesses import CurrentPrincipal, MutationKey
from gorgona_booking.api.deps import runtime_pool
from gorgona_booking.api.request_id import get_request_id
from gorgona_booking.auth.permissions import Permission
from gorgona_booking.business import restaurant_checks as checks
from gorgona_booking.business.restaurant_menu import KitchenStation
from gorgona_booking.db.inventory_guard import assert_inventory_ready
from gorgona_booking.db.schema_guard import assert_location_scope_ready
from gorgona_booking.tenancy.authorization import TenantAccess, authorized_tenant

router = APIRouter(prefix="/v1/businesses/{business_id}/restaurant", tags=["restaurant"])


@asynccontextmanager
async def _access(
    business_id: UUID,
    request: Request,
    principal: CurrentPrincipal,
    permission: Permission,
) -> AsyncIterator[TenantAccess]:
    async with authorized_tenant(
        runtime_pool(request),
        principal,
        business_id,
        permission,
        allow_location_scope=True,
        allow_delegation=False,
        request_id=get_request_id(request),
    ) as access:
        await assert_location_scope_ready(access.conn)
        yield access


@router.get("/checks")
async def list_checks(
    business_id: UUID,
    request: Request,
    principal: CurrentPrincipal,
    location_id: UUID | None = None,
    status: checks.CheckStatus | None = None,
    table_id: UUID | None = None,
    after: UUID | None = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
) -> checks.CheckList:
    async with _access(business_id, request, principal, Permission.RESTAURANT_READ) as access:
        return await checks.list_checks(
            access.conn,
            business_id,
            location_id=location_id,
            status=status,
            table_id=table_id,
            after=after,
            limit=limit,
        )


@router.get("/checks/{check_id}")
async def get_check(
    business_id: UUID,
    check_id: UUID,
    request: Request,
    principal: CurrentPrincipal,
) -> checks.CheckView:
    async with _access(business_id, request, principal, Permission.RESTAURANT_READ) as access:
        return await checks.get_check(access.conn, business_id, check_id)


@router.post("/checks")
async def open_check(
    business_id: UUID,
    body: checks.OpenCheckInput,
    request: Request,
    principal: CurrentPrincipal,
    idempotency_key: MutationKey,
) -> checks.CheckView:
    async with _access(business_id, request, principal, Permission.RESTAURANT_SERVICE) as access:
        return await checks.open_check(
            access.conn,
            business_id,
            location_scope=access.location_id,
            user_id=principal.user_id,
            actor=principal.actor,
            key=idempotency_key,
            body=body,
        )


@router.post("/checks/{check_id}/lines")
async def add_check_line(
    business_id: UUID,
    check_id: UUID,
    body: checks.AddCheckLineInput,
    request: Request,
    principal: CurrentPrincipal,
    idempotency_key: MutationKey,
) -> checks.CheckView:
    async with _access(business_id, request, principal, Permission.RESTAURANT_SERVICE) as access:
        return await checks.add_check_line(
            access.conn,
            business_id,
            check_id,
            location_scope=access.location_id,
            user_id=principal.user_id,
            actor=principal.actor,
            key=idempotency_key,
            body=body,
        )


@router.post("/checks/{check_id}/lines/{line_id}/void")
async def void_check_line(
    business_id: UUID,
    check_id: UUID,
    line_id: UUID,
    body: checks.VoidCheckLineInput,
    request: Request,
    principal: CurrentPrincipal,
    idempotency_key: MutationKey,
) -> checks.CheckView:
    async with _access(business_id, request, principal, Permission.RESTAURANT_SERVICE) as access:
        return await checks.void_check_line(
            access.conn,
            business_id,
            check_id,
            line_id,
            location_scope=access.location_id,
            can_manage=access.role in ("owner", "manager"),
            user_id=principal.user_id,
            actor=principal.actor,
            key=idempotency_key,
            body=body,
        )


@router.post("/checks/{check_id}/fire")
async def fire_check(
    business_id: UUID,
    check_id: UUID,
    body: checks.FireCheckInput,
    request: Request,
    principal: CurrentPrincipal,
    idempotency_key: MutationKey,
) -> checks.FireResultView:
    async with _access(business_id, request, principal, Permission.RESTAURANT_SERVICE) as access:
        return await checks.fire_check_lines(
            access.conn,
            business_id,
            check_id,
            location_scope=access.location_id,
            user_id=principal.user_id,
            actor=principal.actor,
            key=idempotency_key,
            body=body,
        )


@router.post("/checks/{check_id}/close")
async def close_check(
    business_id: UUID,
    check_id: UUID,
    body: checks.CloseCheckInput,
    request: Request,
    principal: CurrentPrincipal,
    idempotency_key: MutationKey,
) -> checks.CheckView:
    async with _access(business_id, request, principal, Permission.RESTAURANT_SERVICE) as access:
        return await checks.close_check(
            access.conn,
            business_id,
            check_id,
            location_scope=access.location_id,
            can_manage=access.role in ("owner", "manager"),
            user_id=principal.user_id,
            actor=principal.actor,
            key=idempotency_key,
            body=body,
        )


@router.get("/kitchen/tickets")
async def list_kitchen_tickets(
    business_id: UUID,
    request: Request,
    principal: CurrentPrincipal,
    location_id: UUID | None = None,
    kitchen_station: KitchenStation | None = None,
    status: checks.KitchenTicketStatus | None = None,
    check_id: UUID | None = None,
    after: UUID | None = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
) -> checks.KitchenTicketList:
    async with _access(business_id, request, principal, Permission.RESTAURANT_READ) as access:
        return await checks.list_kitchen_tickets(
            access.conn,
            business_id,
            location_id=location_id,
            kitchen_station=kitchen_station,
            status=status,
            check_id=check_id,
            after=after,
            limit=limit,
        )


@router.get("/kitchen/tickets/{ticket_id}")
async def get_kitchen_ticket(
    business_id: UUID,
    ticket_id: UUID,
    request: Request,
    principal: CurrentPrincipal,
) -> checks.KitchenTicketView:
    async with _access(business_id, request, principal, Permission.RESTAURANT_READ) as access:
        return await checks.get_kitchen_ticket(access.conn, business_id, ticket_id)


@router.post("/kitchen/tickets/{ticket_id}/events")
async def post_kitchen_ticket_event(
    business_id: UUID,
    ticket_id: UUID,
    body: checks.KitchenTicketEventInput,
    request: Request,
    principal: CurrentPrincipal,
    idempotency_key: MutationKey,
) -> checks.KitchenTicketView:
    async with _access(business_id, request, principal, Permission.RESTAURANT_KITCHEN) as access:
        return await checks.record_kitchen_ticket_event(
            access.conn,
            business_id,
            ticket_id,
            location_scope=access.location_id,
            can_manage=access.role in ("owner", "manager"),
            user_id=principal.user_id,
            actor=principal.actor,
            key=idempotency_key,
            body=body,
        )


@router.get("/checks/{check_id}/consumption")
async def get_check_consumption(
    business_id: UUID,
    check_id: UUID,
    request: Request,
    principal: CurrentPrincipal,
) -> checks.CheckConsumptionView:
    async with _access(business_id, request, principal, Permission.RESTAURANT_READ) as access:
        return await checks.get_check_consumption(access.conn, business_id, check_id)


@router.post("/checks/{check_id}/post-consumption")
async def post_check_consumption(
    business_id: UUID,
    check_id: UUID,
    body: checks.PostConsumptionInput,
    request: Request,
    principal: CurrentPrincipal,
    idempotency_key: MutationKey,
) -> checks.CheckConsumptionView:
    async with _access(business_id, request, principal, Permission.RESTAURANT_MANAGE) as access:
        await assert_inventory_ready(access.conn)
        return await checks.post_check_consumption(
            access.conn,
            business_id,
            check_id,
            location_scope=access.location_id,
            user_id=principal.user_id,
            actor=principal.actor,
            key=idempotency_key,
            body=body,
        )
