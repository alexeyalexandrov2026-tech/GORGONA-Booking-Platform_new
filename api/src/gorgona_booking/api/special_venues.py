"""HTTP routes for SPECIAL-01 (0145): Education/Fitness, Hospitality & Events."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from uuid import UUID

from fastapi import APIRouter, Request

from gorgona_booking.api.businesses import CurrentPrincipal, MutationKey
from gorgona_booking.api.deps import runtime_pool
from gorgona_booking.api.request_id import get_request_id
from gorgona_booking.auth.permissions import Permission
from gorgona_booking.business import special_venues as sv
from gorgona_booking.db.schema_guard import assert_location_scope_ready
from gorgona_booking.tenancy.authorization import TenantAccess, authorized_tenant

router = APIRouter(prefix="/v1/businesses/{business_id}/special-venues", tags=["special_venues"])


@asynccontextmanager
async def _access(
    request: Request,
    principal: CurrentPrincipal,
    business_id: UUID,
    permission: Permission = Permission.SPECIAL_READ,
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


@router.put("/programs/{program_id}", response_model=sv.ProgramView)
async def put_program(
    business_id: UUID,
    program_id: UUID,
    body: sv.ProgramInput,
    request: Request,
    principal: CurrentPrincipal,
    key: MutationKey,
) -> sv.ProgramView:
    async with _access(request, principal, business_id, Permission.SPECIAL_MANAGE) as access:
        return await sv.save_program(
            access.conn,
            business_id,
            program_id,
            user_id=principal.user_id,
            actor=principal.actor,
            key=key,
            body=body,
        )


@router.put("/enrollments/{enrollment_id}", response_model=sv.EnrollmentView)
async def put_enrollment(
    business_id: UUID,
    enrollment_id: UUID,
    body: sv.EnrollmentInput,
    request: Request,
    principal: CurrentPrincipal,
    key: MutationKey,
) -> sv.EnrollmentView:
    async with _access(request, principal, business_id, Permission.SPECIAL_WORK) as access:
        return await sv.create_enrollment(
            access.conn,
            business_id,
            enrollment_id,
            user_id=principal.user_id,
            actor=principal.actor,
            key=key,
            body=body,
        )


@router.post("/enrollments/{enrollment_id}/use-sessions", response_model=sv.EnrollmentView)
async def post_use_sessions(
    business_id: UUID,
    enrollment_id: UUID,
    body: sv.EnrollmentSessionUseInput,
    request: Request,
    principal: CurrentPrincipal,
    key: MutationKey,
) -> sv.EnrollmentView:
    async with _access(request, principal, business_id, Permission.SPECIAL_WORK) as access:
        return await sv.use_enrollment_sessions(
            access.conn,
            business_id,
            enrollment_id,
            user_id=principal.user_id,
            actor=principal.actor,
            key=key,
            body=body,
        )


@router.put("/rooms/{room_id}", response_model=sv.RoomView)
async def put_room(
    business_id: UUID,
    room_id: UUID,
    body: sv.RoomInput,
    request: Request,
    principal: CurrentPrincipal,
    key: MutationKey,
) -> sv.RoomView:
    async with _access(request, principal, business_id, Permission.SPECIAL_MANAGE) as access:
        return await sv.save_room(
            access.conn,
            business_id,
            room_id,
            user_id=principal.user_id,
            actor=principal.actor,
            key=key,
            body=body,
        )


@router.put("/stays/{stay_id}", response_model=sv.StayView)
async def put_stay(
    business_id: UUID,
    stay_id: UUID,
    body: sv.StayInput,
    request: Request,
    principal: CurrentPrincipal,
    key: MutationKey,
) -> sv.StayView:
    async with _access(request, principal, business_id, Permission.SPECIAL_WORK) as access:
        return await sv.create_stay(
            access.conn,
            business_id,
            stay_id,
            user_id=principal.user_id,
            actor=principal.actor,
            key=key,
            body=body,
        )


@router.post("/stays/{stay_id}/transition", response_model=sv.StayView)
async def post_stay_transition(
    business_id: UUID,
    stay_id: UUID,
    body: sv.StayTransitionInput,
    request: Request,
    principal: CurrentPrincipal,
    key: MutationKey,
) -> sv.StayView:
    async with _access(request, principal, business_id, Permission.SPECIAL_WORK) as access:
        return await sv.transition_stay(
            access.conn,
            business_id,
            stay_id,
            user_id=principal.user_id,
            actor=principal.actor,
            key=key,
            body=body,
        )


@router.put("/events/{event_id}", response_model=sv.EventView)
async def put_event(
    business_id: UUID,
    event_id: UUID,
    body: sv.EventInput,
    request: Request,
    principal: CurrentPrincipal,
    key: MutationKey,
) -> sv.EventView:
    async with _access(request, principal, business_id, Permission.SPECIAL_MANAGE) as access:
        return await sv.save_event(
            access.conn,
            business_id,
            event_id,
            user_id=principal.user_id,
            actor=principal.actor,
            key=key,
            body=body,
        )


@router.put("/tickets/{ticket_id}", response_model=sv.TicketView)
async def put_ticket(
    business_id: UUID,
    ticket_id: UUID,
    body: sv.TicketInput,
    request: Request,
    principal: CurrentPrincipal,
    key: MutationKey,
) -> sv.TicketView:
    async with _access(request, principal, business_id, Permission.SPECIAL_WORK) as access:
        return await sv.issue_ticket(
            access.conn,
            business_id,
            ticket_id,
            user_id=principal.user_id,
            actor=principal.actor,
            key=key,
            body=body,
        )


@router.post("/tickets/{ticket_id}/transition", response_model=sv.TicketView)
async def post_ticket_transition(
    business_id: UUID,
    ticket_id: UUID,
    body: sv.TicketTransitionInput,
    request: Request,
    principal: CurrentPrincipal,
    key: MutationKey,
) -> sv.TicketView:
    async with _access(request, principal, business_id, Permission.SPECIAL_WORK) as access:
        return await sv.transition_ticket(
            access.conn,
            business_id,
            ticket_id,
            user_id=principal.user_id,
            actor=principal.actor,
            key=key,
            body=body,
        )
