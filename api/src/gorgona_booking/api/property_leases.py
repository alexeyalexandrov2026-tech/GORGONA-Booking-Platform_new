"""Company-wide property lease routes."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Query, Request

from gorgona_booking.api.businesses import CurrentPrincipal, MutationKey
from gorgona_booking.api.property_catalog import _access
from gorgona_booking.auth.permissions import Permission
from gorgona_booking.business import property_lease_terms as terms
from gorgona_booking.business import property_leases as leases
from gorgona_booking.business import property_move_in as move_in

router = APIRouter(prefix="/v1/businesses/{business_id}/property/leases", tags=["property"])


@router.get("")
async def list_leases(
    business_id: UUID,
    request: Request,
    principal: CurrentPrincipal,
    after: UUID | None = None,
    object_id: UUID | None = None,
) -> leases.LeaseList:
    async with _access(business_id, request, principal, Permission.PROPERTY_MANAGE) as access:
        return await leases.list_leases(access.conn, business_id, after, object_id)


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


@router.get("/{lease_id}/terms")
async def get_terms(
    business_id: UUID,
    lease_id: UUID,
    request: Request,
    principal: CurrentPrincipal,
    before: Annotated[int | None, Query(ge=1, le=2_147_483_647)] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
) -> terms.LeaseTermHistory:
    async with _access(business_id, request, principal, Permission.PROPERTY_MANAGE) as access:
        return await terms.term_history(access.conn, business_id, lease_id, before, limit)


@router.post("/{lease_id}/terms")
async def post_term(
    business_id: UUID,
    lease_id: UUID,
    body: terms.LeaseTermInput,
    request: Request,
    principal: CurrentPrincipal,
    idempotency_key: MutationKey,
) -> terms.LeaseTermView:
    async with _access(business_id, request, principal, Permission.PROPERTY_MANAGE) as access:
        return await terms.record_term(
            access.conn,
            business_id,
            lease_id,
            user_id=principal.user_id,
            actor=principal.actor,
            key=idempotency_key,
            body=body,
        )


@router.get("/{lease_id}/move-in")
async def get_move_in(
    business_id: UUID, lease_id: UUID, request: Request, principal: CurrentPrincipal
) -> move_in.MoveInView:
    async with _access(business_id, request, principal, Permission.PROPERTY_MANAGE) as access:
        return await move_in.get_move_in(access.conn, business_id, lease_id)


@router.put("/{lease_id}/move-in")
async def put_move_in(
    business_id: UUID,
    lease_id: UUID,
    body: move_in.MoveInInput,
    request: Request,
    principal: CurrentPrincipal,
    idempotency_key: MutationKey,
) -> move_in.MoveInView:
    async with _access(business_id, request, principal, Permission.PROPERTY_MANAGE) as access:
        return await move_in.record_move_in(
            access.conn,
            business_id,
            lease_id,
            user_id=principal.user_id,
            actor=principal.actor,
            key=idempotency_key,
            body=body,
        )
