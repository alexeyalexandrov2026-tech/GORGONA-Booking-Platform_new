"""HTTP routes for SPECIAL-04 (0148): Staffing, advisory, organizations and public admin."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from uuid import UUID

from fastapi import APIRouter, Request

from gorgona_booking.api.businesses import CurrentPrincipal, MutationKey
from gorgona_booking.api.deps import runtime_pool
from gorgona_booking.api.request_id import get_request_id
from gorgona_booking.auth.permissions import Permission
from gorgona_booking.business import special_civic as cv
from gorgona_booking.db.schema_guard import assert_location_scope_ready
from gorgona_booking.tenancy.authorization import TenantAccess, authorized_tenant

router = APIRouter(prefix="/v1/businesses/{business_id}/civic", tags=["public_civic"])


@asynccontextmanager
async def _access(
    request: Request,
    principal: CurrentPrincipal,
    business_id: UUID,
    permission: Permission = Permission.CIVIC_READ,
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


@router.get("/programs", response_model=cv.CivicProgramList)
async def get_programs(
    business_id: UUID,
    request: Request,
    principal: CurrentPrincipal,
) -> cv.CivicProgramList:
    async with _access(request, principal, business_id) as access:
        return await cv.list_programs(access.conn, business_id)


@router.put("/programs/{program_id}", response_model=cv.CivicProgramView)
async def put_program(
    business_id: UUID,
    program_id: UUID,
    body: cv.CivicProgramInput,
    request: Request,
    principal: CurrentPrincipal,
    key: MutationKey,
) -> cv.CivicProgramView:
    async with _access(request, principal, business_id, Permission.CIVIC_MANAGE) as access:
        return await cv.save_program(
            access.conn,
            business_id,
            program_id,
            user_id=principal.user_id,
            actor=principal.actor,
            key=key,
            body=body,
        )


@router.get("/cases", response_model=cv.CivicCaseList)
async def get_cases(
    business_id: UUID,
    request: Request,
    principal: CurrentPrincipal,
    program_id: UUID | None = None,
) -> cv.CivicCaseList:
    async with _access(request, principal, business_id) as access:
        return await cv.list_cases(access.conn, business_id, program_id=program_id)


@router.put("/cases/{case_id}", response_model=cv.CivicCaseView)
async def put_case(
    business_id: UUID,
    case_id: UUID,
    body: cv.CivicCaseInput,
    request: Request,
    principal: CurrentPrincipal,
    key: MutationKey,
) -> cv.CivicCaseView:
    async with _access(request, principal, business_id, Permission.CIVIC_WORK) as access:
        return await cv.save_case(
            access.conn,
            business_id,
            case_id,
            user_id=principal.user_id,
            actor=principal.actor,
            key=key,
            body=body,
        )


@router.get("/allocations", response_model=cv.CivicAllocationList)
async def get_allocations(
    business_id: UUID,
    request: Request,
    principal: CurrentPrincipal,
    case_id: UUID | None = None,
) -> cv.CivicAllocationList:
    async with _access(request, principal, business_id) as access:
        return await cv.list_allocations(access.conn, business_id, case_id=case_id)


@router.put("/allocations/{allocation_id}", response_model=cv.CivicAllocationView)
async def put_allocation(
    business_id: UUID,
    allocation_id: UUID,
    body: cv.CivicAllocationInput,
    request: Request,
    principal: CurrentPrincipal,
    key: MutationKey,
) -> cv.CivicAllocationView:
    async with _access(request, principal, business_id, Permission.CIVIC_MANAGE) as access:
        return await cv.save_allocation(
            access.conn,
            business_id,
            allocation_id,
            user_id=principal.user_id,
            actor=principal.actor,
            key=key,
            body=body,
        )


@router.get("/audit-events", response_model=cv.CivicAuditEventList)
async def get_audit_events(
    business_id: UUID,
    request: Request,
    principal: CurrentPrincipal,
    case_id: UUID | None = None,
) -> cv.CivicAuditEventList:
    async with _access(request, principal, business_id) as access:
        return await cv.list_audit_events(access.conn, business_id, case_id=case_id)


@router.put("/audit-events/{event_id}", response_model=cv.CivicAuditEventView)
async def put_audit_event(
    business_id: UUID,
    event_id: UUID,
    body: cv.CivicAuditEventInput,
    request: Request,
    principal: CurrentPrincipal,
    key: MutationKey,
) -> cv.CivicAuditEventView:
    async with _access(request, principal, business_id, Permission.CIVIC_WORK) as access:
        return await cv.record_audit_event(
            access.conn,
            business_id,
            event_id,
            user_id=principal.user_id,
            actor=principal.actor,
            key=key,
            body=body,
        )
