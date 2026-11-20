"""Property maintenance requests, lifecycle events and separate FIN-03 obligations."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Query, Request

from gorgona_booking.api.businesses import CurrentPrincipal, MutationKey
from gorgona_booking.api.property_catalog import _access
from gorgona_booking.auth.permissions import Permission
from gorgona_booking.business import property_maintenance as maintenance

router = APIRouter(prefix="/v1/businesses/{business_id}/property/maintenance", tags=["property"])


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
