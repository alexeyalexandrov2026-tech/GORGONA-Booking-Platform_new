"""Rental API (ADR-0036): item classes and units (package R, RENT-01)."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from uuid import UUID

from fastapi import APIRouter, Request
from pydantic import AwareDatetime

from gorgona_booking.api.businesses import CurrentPrincipal, MutationKey
from gorgona_booking.api.deps import runtime_pool
from gorgona_booking.api.request_id import get_request_id
from gorgona_booking.auth.permissions import Permission
from gorgona_booking.business import rental as service
from gorgona_booking.business import rental_assignments as assignments
from gorgona_booking.business import rental_blocks as blocks
from gorgona_booking.business import rental_bookings as bookings
from gorgona_booking.business.rental import (
    ClassInput,
    ClassList,
    ClassView,
    UnitInput,
    UnitList,
    UnitView,
)
from gorgona_booking.business.rental_assignments import (
    AssignmentInput,
    AssignmentList,
    AssignmentView,
)
from gorgona_booking.business.rental_blocks import (
    BlockInput,
    BlockList,
    BlockReleaseInput,
    BlockView,
)
from gorgona_booking.business.rental_bookings import (
    AvailabilityView,
    BookingInput,
    BookingList,
    BookingView,
    CancellationInput,
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


@router.get("/bookings")
async def get_bookings(
    business_id: UUID,
    request: Request,
    principal: CurrentPrincipal,
    after: UUID | None = None,
    class_id: UUID | None = None,
) -> BookingList:
    async with _access(request, principal, business_id) as access:
        return await bookings.list_bookings(access.conn, after, class_id)


@router.get("/bookings/{booking_id}")
async def get_booking(
    business_id: UUID, booking_id: UUID, request: Request, principal: CurrentPrincipal
) -> BookingView:
    async with _access(request, principal, business_id) as access:
        view = await bookings.load_booking(access.conn, booking_id)
        if view is None:
            raise NotFoundError("Booking not found", booking_id=str(booking_id))
        return view


@router.post("/bookings")
async def post_booking(
    business_id: UUID,
    body: BookingInput,
    request: Request,
    principal: CurrentPrincipal,
    idempotency_key: MutationKey,
) -> BookingView:
    """R2 decisions 1-3: a class for a period, while its units at the pickup branch cover it."""
    async with _access(request, principal, business_id, Permission.RENTAL_MANAGE) as access:
        return await bookings.create_booking(
            access.conn,
            business_id,
            user_id=principal.user_id,
            actor=principal.actor,
            key=idempotency_key,
            body=body,
        )


@router.post("/bookings/{booking_id}/cancellation")
async def post_cancellation(
    business_id: UUID,
    booking_id: UUID,
    body: CancellationInput,
    request: Request,
    principal: CurrentPrincipal,
    idempotency_key: MutationKey,
) -> BookingView:
    """R2 decision 1: a booking is cancelled once, with its reason."""
    async with _access(request, principal, business_id, Permission.RENTAL_MANAGE) as access:
        return await bookings.cancel_booking(
            access.conn,
            business_id,
            booking_id,
            user_id=principal.user_id,
            actor=principal.actor,
            key=idempotency_key,
            body=body,
        )


@router.get("/availability")
async def get_availability(
    business_id: UUID,
    class_id: UUID,
    location_id: UUID,
    starts_at: AwareDatetime,
    ends_at: AwareDatetime,
    request: Request,
    principal: CurrentPrincipal,
) -> AvailabilityView:
    """R2 decision 2: units minus the peak of overlapping bookings over a period."""
    async with _access(request, principal, business_id) as access:
        return await bookings.availability(
            access.conn, business_id, class_id, location_id, starts_at, ends_at
        )


@router.get("/bookings/{booking_id}/assignments")
async def get_assignments(
    business_id: UUID, booking_id: UUID, request: Request, principal: CurrentPrincipal
) -> AssignmentList:
    async with _access(request, principal, business_id) as access:
        return await assignments.list_assignments(access.conn, booking_id)


@router.post("/bookings/{booking_id}/assignment")
async def post_assignment(
    business_id: UUID,
    booking_id: UUID,
    body: AssignmentInput,
    request: Request,
    principal: CurrentPrincipal,
    idempotency_key: MutationKey,
) -> AssignmentView:
    """R3a decisions 2-3: hold a suitable unit for the booking period, replacing the current one."""
    async with _access(request, principal, business_id, Permission.RENTAL_MANAGE) as access:
        return await assignments.assign_unit(
            access.conn,
            business_id,
            booking_id,
            user_id=principal.user_id,
            actor=principal.actor,
            key=idempotency_key,
            body=body,
        )


@router.get("/units/{unit_id}/blocks")
async def get_blocks(
    business_id: UUID, unit_id: UUID, request: Request, principal: CurrentPrincipal
) -> BlockList:
    async with _access(request, principal, business_id) as access:
        return await blocks.list_blocks(access.conn, unit_id)


@router.post("/units/{unit_id}/blocks")
async def post_block(
    business_id: UUID,
    unit_id: UUID,
    body: BlockInput,
    request: Request,
    principal: CurrentPrincipal,
    idempotency_key: MutationKey,
) -> BlockView:
    """R3b decisions 1-2: take a unit out of service for a period, if every booking keeps a unit."""
    async with _access(request, principal, business_id, Permission.RENTAL_MANAGE) as access:
        return await blocks.create_block(
            access.conn,
            business_id,
            unit_id,
            user_id=principal.user_id,
            actor=principal.actor,
            key=idempotency_key,
            body=body,
        )


@router.post("/units/{unit_id}/blocks/{block_id}/release")
async def post_block_release(
    business_id: UUID,
    unit_id: UUID,
    block_id: UUID,
    body: BlockReleaseInput,
    request: Request,
    principal: CurrentPrincipal,
    idempotency_key: MutationKey,
) -> BlockView:
    """R3b decision 1: a block is released once, with its hold."""
    async with _access(request, principal, business_id, Permission.RENTAL_MANAGE) as access:
        return await blocks.release_block(
            access.conn,
            business_id,
            unit_id,
            block_id,
            user_id=principal.user_id,
            actor=principal.actor,
            key=idempotency_key,
            body=body,
        )
