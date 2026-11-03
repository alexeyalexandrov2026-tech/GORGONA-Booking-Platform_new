"""Rental API (ADR-0036): item classes and units (package R, RENT-01)."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from uuid import UUID

from fastapi import APIRouter, Request

from gorgona_booking.api.businesses import CurrentPrincipal, MutationKey
from gorgona_booking.api.deps import runtime_pool
from gorgona_booking.api.request_id import get_request_id
from gorgona_booking.auth.permissions import Permission
from gorgona_booking.business import rental as service
from gorgona_booking.business.rental import (
    ClassInput,
    ClassList,
    ClassView,
    UnitInput,
    UnitList,
    UnitView,
)
from gorgona_booking.db.schema_guard import assert_location_scope_ready
from gorgona_booking.errors import NotFoundError
from gorgona_booking.tenancy.authorization import TenantAccess, authorized_tenant

router = APIRouter(prefix="/v1/businesses/{business_id}/rental", tags=["rental"])


@asynccontextmanager
async def _access(
    request: Request,
    principal: CurrentPrincipal,
    business_id: UUID,
    permission: Permission = Permission.RENTAL_READ,
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


@router.get("/classes")
async def get_classes(
    business_id: UUID, request: Request, principal: CurrentPrincipal, after: UUID | None = None
) -> ClassList:
    async with _access(request, principal, business_id) as access:
        return await service.list_classes(access.conn, after)


@router.get("/classes/{class_id}")
async def get_class(
    business_id: UUID, class_id: UUID, request: Request, principal: CurrentPrincipal
) -> ClassView:
    async with _access(request, principal, business_id) as access:
        view = await service.load_class(access.conn, class_id)
        if view is None:
            raise NotFoundError("Class not found", class_id=str(class_id))
        return view


@router.put("/classes/{class_id}")
async def put_class(
    business_id: UUID,
    class_id: UUID,
    body: ClassInput,
    request: Request,
    principal: CurrentPrincipal,
    idempotency_key: MutationKey,
) -> ClassView:
    """ADR-0036 decision 3: the whole class with its attribute set and the expected revision."""
    async with _access(request, principal, business_id, Permission.RENTAL_MANAGE) as access:
        return await service.save_class(
            access.conn,
            business_id,
            class_id,
            user_id=principal.user_id,
            actor=principal.actor,
            key=idempotency_key,
            body=body,
        )


@router.get("/units")
async def get_units(
    business_id: UUID,
    request: Request,
    principal: CurrentPrincipal,
    after: UUID | None = None,
    class_id: UUID | None = None,
) -> UnitList:
    async with _access(request, principal, business_id) as access:
        return await service.list_units(access.conn, after, class_id)


@router.get("/units/{unit_id}")
async def get_unit(
    business_id: UUID, unit_id: UUID, request: Request, principal: CurrentPrincipal
) -> UnitView:
    async with _access(request, principal, business_id) as access:
        view = await service.load_unit(access.conn, unit_id)
        if view is None:
            raise NotFoundError("Unit not found", unit_id=str(unit_id))
        return view


@router.put("/units/{unit_id}")
async def put_unit(
    business_id: UUID,
    unit_id: UUID,
    body: UnitInput,
    request: Request,
    principal: CurrentPrincipal,
    idempotency_key: MutationKey,
) -> UnitView:
    """ADR-0036 decision 4: the whole unit with its values and the expected revision."""
    async with _access(request, principal, business_id, Permission.RENTAL_MANAGE) as access:
        return await service.save_unit(
            access.conn,
            business_id,
            unit_id,
            user_id=principal.user_id,
            actor=principal.actor,
            key=idempotency_key,
            body=body,
        )
