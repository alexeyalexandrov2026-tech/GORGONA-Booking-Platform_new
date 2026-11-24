"""REST-01 Slice 1: dining areas, tables and independent table reservations."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Query, Request

from gorgona_booking.api.businesses import CurrentPrincipal, MutationKey
from gorgona_booking.api.deps import runtime_pool
from gorgona_booking.api.request_id import get_request_id
from gorgona_booking.auth.permissions import Permission
from gorgona_booking.business import restaurant_floor as floor
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


@router.get("/areas")
async def list_areas(
    business_id: UUID,
    request: Request,
    principal: CurrentPrincipal,
    location_id: UUID | None = None,
    after: UUID | None = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
) -> floor.AreaList:
    async with _access(business_id, request, principal, Permission.RESTAURANT_READ) as access:
        return await floor.list_areas(
            access.conn, business_id, location_id=location_id, after=after, limit=limit
        )


@router.get("/areas/{area_id}")
async def get_area(
    business_id: UUID, area_id: UUID, request: Request, principal: CurrentPrincipal
) -> floor.AreaView:
    async with _access(business_id, request, principal, Permission.RESTAURANT_READ) as access:
        return await floor.get_area(access.conn, business_id, area_id)


@router.put("/areas/{area_id}")
async def put_area(
    business_id: UUID,
    area_id: UUID,
    body: floor.AreaInput,
    request: Request,
    principal: CurrentPrincipal,
    idempotency_key: MutationKey,
) -> floor.AreaView:
    async with _access(business_id, request, principal, Permission.RESTAURANT_MANAGE) as access:
        return await floor.save_area(
            access.conn,
            business_id,
            area_id,
            location_scope=access.location_id,
            user_id=principal.user_id,
            actor=principal.actor,
            key=idempotency_key,
            body=body,
        )


@router.get("/tables")
async def list_tables(
    business_id: UUID,
    request: Request,
    principal: CurrentPrincipal,
    location_id: UUID | None = None,
    area_id: UUID | None = None,
    after: UUID | None = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
) -> floor.TableList:
    async with _access(business_id, request, principal, Permission.RESTAURANT_READ) as access:
        return await floor.list_tables(
            access.conn,
            business_id,
            location_id=location_id,
            area_id=area_id,
            after=after,
            limit=limit,
        )


@router.get("/tables/{table_id}")
async def get_table(
    business_id: UUID, table_id: UUID, request: Request, principal: CurrentPrincipal
) -> floor.TableView:
    async with _access(business_id, request, principal, Permission.RESTAURANT_READ) as access:
        return await floor.get_table(access.conn, business_id, table_id)


@router.put("/tables/{table_id}")
async def put_table(
    business_id: UUID,
    table_id: UUID,
    body: floor.TableInput,
    request: Request,
    principal: CurrentPrincipal,
    idempotency_key: MutationKey,
) -> floor.TableView:
    async with _access(business_id, request, principal, Permission.RESTAURANT_MANAGE) as access:
        return await floor.save_table(
            access.conn,
            business_id,
            table_id,
            location_scope=access.location_id,
            user_id=principal.user_id,
            actor=principal.actor,
            key=idempotency_key,
            body=body,
        )


@router.get("/reservations")
async def list_reservations(
    business_id: UUID,
    request: Request,
    principal: CurrentPrincipal,
    location_id: UUID | None = None,
    table_id: UUID | None = None,
    status: floor.ReservationStatus | None = None,
    after: UUID | None = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
) -> floor.ReservationList:
    async with _access(business_id, request, principal, Permission.RESTAURANT_READ) as access:
        return await floor.list_reservations(
            access.conn,
            business_id,
            location_id=location_id,
            table_id=table_id,
            status=status,
            after=after,
            limit=limit,
        )


@router.get("/reservations/{reservation_id}")
async def get_reservation(
    business_id: UUID, reservation_id: UUID, request: Request, principal: CurrentPrincipal
) -> floor.ReservationView:
    async with _access(business_id, request, principal, Permission.RESTAURANT_READ) as access:
        return await floor.get_reservation(access.conn, business_id, reservation_id)


@router.put("/reservations/{reservation_id}")
async def put_reservation(
    business_id: UUID,
    reservation_id: UUID,
    body: floor.ReservationInput,
    request: Request,
    principal: CurrentPrincipal,
    idempotency_key: MutationKey,
) -> floor.ReservationView:
    async with _access(business_id, request, principal, Permission.RESTAURANT_SERVICE) as access:
        return await floor.create_reservation(
            access.conn,
            business_id,
            reservation_id,
            user_id=principal.user_id,
            actor=principal.actor,
            key=idempotency_key,
            body=body,
        )


@router.get("/reservations/{reservation_id}/events")
async def list_reservation_events(
    business_id: UUID, reservation_id: UUID, request: Request, principal: CurrentPrincipal
) -> floor.ReservationEventList:
    async with _access(business_id, request, principal, Permission.RESTAURANT_READ) as access:
        return await floor.list_reservation_events(access.conn, business_id, reservation_id)


@router.post("/reservations/{reservation_id}/events")
async def post_reservation_event(
    business_id: UUID,
    reservation_id: UUID,
    body: floor.ReservationEventInput,
    request: Request,
    principal: CurrentPrincipal,
    idempotency_key: MutationKey,
) -> floor.ReservationView:
    async with _access(business_id, request, principal, Permission.RESTAURANT_SERVICE) as access:
        return await floor.record_reservation_event(
            access.conn,
            business_id,
            reservation_id,
            user_id=principal.user_id,
            actor=principal.actor,
            key=idempotency_key,
            body=body,
        )
