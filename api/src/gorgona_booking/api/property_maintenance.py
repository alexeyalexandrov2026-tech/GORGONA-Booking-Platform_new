"""Property maintenance requests, lifecycle events and separate FIN-03 obligations."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Query, Request

from gorgona_booking.api.businesses import CurrentPrincipal, MutationKey
from gorgona_booking.api.deps import runtime_pool
from gorgona_booking.api.property_catalog import _access
from gorgona_booking.api.request_id import get_request_id
from gorgona_booking.auth.permissions import Permission
from gorgona_booking.business import property_maintenance as maintenance
from gorgona_booking.db.schema_guard import assert_location_scope_ready
from gorgona_booking.tenancy.authorization import (
    DelegationScope,
    PermissionDeniedError,
    TenantAccess,
    authorized_tenant,
)

router = APIRouter(prefix="/v1/businesses/{business_id}/property/maintenance", tags=["property"])


@asynccontextmanager
async def _contractor_grant(
    request: Request, principal: CurrentPrincipal, business_id: UUID, grant_id: UUID
) -> AsyncIterator[tuple[TenantAccess, DelegationScope]]:
    async with authorized_tenant(
        runtime_pool(request),
        principal,
        business_id,
        Permission.PROPERTY_CONTRACTOR_WORK,
        allow_location_scope=True,
        allow_delegation=True,
        delegation_id=grant_id,
        request_id=get_request_id(request),
    ) as access:
        if access.delegation is None:
            raise PermissionDeniedError(
                "Only the contractor's delegate can access this maintenance request"
            )
        await assert_location_scope_ready(access.conn)
        yield access, access.delegation


@router.get("")
async def list_maintenance(
    business_id: UUID,
    request: Request,
    principal: CurrentPrincipal,
    after: UUID | None = None,
    object_id: UUID | None = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
) -> maintenance.MaintenanceRequestList:
    async with _access(business_id, request, principal, Permission.PROPERTY_READ) as access:
        return await maintenance.list_requests(
            access.conn, business_id, after=after, object_id=object_id, limit=limit
        )


@router.get("/{request_id}")
async def get_maintenance(
    business_id: UUID, request_id: UUID, request: Request, principal: CurrentPrincipal
) -> maintenance.MaintenanceRequestView:
    async with _access(business_id, request, principal, Permission.PROPERTY_READ) as access:
        return await maintenance.get_request(access.conn, business_id, request_id)


@router.put("/{request_id}")
async def put_maintenance(
    business_id: UUID,
    request_id: UUID,
    body: maintenance.MaintenanceRequestInput,
    request: Request,
    principal: CurrentPrincipal,
    idempotency_key: MutationKey,
) -> maintenance.MaintenanceRequestView:
    async with _access(business_id, request, principal, Permission.PROPERTY_MANAGE) as access:
        return await maintenance.create_request(
            access.conn,
            business_id,
            request_id,
            user_id=principal.user_id,
            actor=principal.actor,
            key=idempotency_key,
            body=body,
        )


@router.get("/{request_id}/events")
async def get_maintenance_events(
    business_id: UUID,
    request_id: UUID,
    request: Request,
    principal: CurrentPrincipal,
    before: Annotated[int | None, Query(ge=1, le=2_147_483_647)] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
) -> maintenance.MaintenanceEventHistory:
    async with _access(business_id, request, principal, Permission.PROPERTY_MANAGE) as access:
        return await maintenance.list_events(
            access.conn, business_id, request_id, before=before, limit=limit
        )


@router.post("/{request_id}/events")
async def post_maintenance_event(
    business_id: UUID,
    request_id: UUID,
    body: maintenance.MaintenanceEventInput,
    request: Request,
    principal: CurrentPrincipal,
    idempotency_key: MutationKey,
) -> maintenance.MaintenanceRequestView:
    async with _access(business_id, request, principal, Permission.PROPERTY_MANAGE) as access:
        return await maintenance.record_event(
            access.conn,
            business_id,
            request_id,
            user_id=principal.user_id,
            actor=principal.actor,
            key=idempotency_key,
            body=body,
        )


@router.get("/{request_id}/obligations")
async def get_maintenance_obligations(
    business_id: UUID, request_id: UUID, request: Request, principal: CurrentPrincipal
) -> maintenance.MaintenanceObligationList:
    async with _access(business_id, request, principal, Permission.PROPERTY_MANAGE) as access:
        return await maintenance.list_obligations(access.conn, business_id, request_id)


@router.post("/{request_id}/obligations")
async def post_maintenance_obligation(
    business_id: UUID,
    request_id: UUID,
    body: maintenance.MaintenanceObligationInput,
    request: Request,
    principal: CurrentPrincipal,
    idempotency_key: MutationKey,
) -> maintenance.MaintenanceObligationView:
    async with _access(business_id, request, principal, Permission.PROPERTY_MANAGE) as access:
        return await maintenance.record_obligation(
            access.conn,
            business_id,
            request_id,
            user_id=principal.user_id,
            actor=principal.actor,
            key=idempotency_key,
            body=body,
        )


@router.get("/{request_id}/contractor-company")
async def get_contractor_company(
    business_id: UUID, request_id: UUID, request: Request, principal: CurrentPrincipal
) -> maintenance.ContractorCompanyView:
    async with _access(business_id, request, principal, Permission.PROPERTY_MANAGE) as access:
        return await maintenance.get_contractor_company(access.conn, business_id, request_id)


@router.put("/{request_id}/contractor-company")
async def put_contractor_company(
    business_id: UUID,
    request_id: UUID,
    body: maintenance.ContractorCompanyInput,
    request: Request,
    principal: CurrentPrincipal,
    idempotency_key: MutationKey,
) -> maintenance.ContractorCompanyView:
    async with _access(business_id, request, principal, Permission.PROPERTY_MANAGE) as access:
        return await maintenance.set_contractor_company(
            access.conn,
            business_id,
            request_id,
            user_id=principal.user_id,
            actor=principal.actor,
            key=idempotency_key,
            body=body,
        )


@router.get("/{request_id}/contractor-updates")
async def get_contractor_updates(
    business_id: UUID, request_id: UUID, request: Request, principal: CurrentPrincipal
) -> maintenance.ContractorUpdateList:
    async with _access(business_id, request, principal, Permission.PROPERTY_MANAGE) as access:
        return await maintenance.list_contractor_updates(access.conn, business_id, request_id)


@router.get("/{request_id}/contractor-work/{grant_id}")
async def get_contractor_work(
    business_id: UUID,
    request_id: UUID,
    grant_id: UUID,
    request: Request,
    principal: CurrentPrincipal,
) -> maintenance.ContractorWorkOrderView:
    async with _contractor_grant(request, principal, business_id, grant_id) as (access, grant):
        return await maintenance.get_contractor_work(
            access.conn, business_id, request_id, grant, location_id=access.location_id
        )


@router.post("/{request_id}/contractor-work/{grant_id}/updates")
async def post_contractor_update(
    business_id: UUID,
    request_id: UUID,
    grant_id: UUID,
    body: maintenance.ContractorUpdateInput,
    request: Request,
    principal: CurrentPrincipal,
    idempotency_key: MutationKey,
) -> maintenance.ContractorUpdateView:
    async with _contractor_grant(request, principal, business_id, grant_id) as (access, grant):
        return await maintenance.record_contractor_update(
            access.conn,
            business_id,
            request_id,
            grant,
            location_id=access.location_id,
            user_id=principal.user_id,
            actor=principal.actor,
            key=idempotency_key,
            body=body,
        )
