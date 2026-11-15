"""Company-wide property lease routes."""

from uuid import UUID

from fastapi import APIRouter, Request

from gorgona_booking.api.businesses import CurrentPrincipal, MutationKey
from gorgona_booking.api.property_catalog import _access
from gorgona_booking.auth.permissions import Permission
from gorgona_booking.business import property_leases as leases

router = APIRouter(prefix="/v1/businesses/{business_id}/property/leases", tags=["property"])


@router.get("")
async def list_leases(
    business_id: UUID, request: Request, principal: CurrentPrincipal, after: UUID | None = None
) -> leases.LeaseList:
    async with _access(business_id, request, principal, Permission.PROPERTY_MANAGE) as access:
        return await leases.list_leases(access.conn, business_id, after)


@router.get("/{lease_id}")
async def get_lease(
    business_id: UUID, lease_id: UUID, request: Request, principal: CurrentPrincipal
) -> leases.LeaseView:
    async with _access(business_id, request, principal, Permission.PROPERTY_MANAGE) as access:
        return await leases.get_lease(access.conn, business_id, lease_id)


@router.put("/{lease_id}")
async def put_lease(
    business_id: UUID,
    lease_id: UUID,
    body: leases.LeaseInput,
    request: Request,
    principal: CurrentPrincipal,
    idempotency_key: MutationKey,
) -> leases.LeaseView:
    async with _access(business_id, request, principal, Permission.PROPERTY_MANAGE) as access:
        return await leases.register_lease(
            access.conn,
            business_id,
            lease_id,
            user_id=principal.user_id,
            actor=principal.actor,
            key=idempotency_key,
            body=body,
        )
