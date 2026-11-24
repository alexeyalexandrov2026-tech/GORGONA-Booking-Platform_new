"""Authenticated property showing routes."""

from uuid import UUID

from fastapi import APIRouter, Request

from gorgona_booking.api.businesses import CurrentPrincipal, MutationKey
from gorgona_booking.api.property_catalog import _access
from gorgona_booking.api.request_id import get_request_id
from gorgona_booking.auth.permissions import Permission
from gorgona_booking.business import property_showings as showings

router = APIRouter(prefix="/v1/businesses/{business_id}/property/showings", tags=["property"])


@router.get("")
async def list_showings(
    business_id: UUID, request: Request, principal: CurrentPrincipal, after: UUID | None = None
) -> showings.ShowingList:
    async with _access(business_id, request, principal, Permission.PROPERTY_READ) as access:
        return await showings.list_showings(access.conn, business_id, after)


@router.get("/{showing_id}")
async def get_showing(
    business_id: UUID, showing_id: UUID, request: Request, principal: CurrentPrincipal
) -> showings.ShowingView:
    async with _access(business_id, request, principal, Permission.PROPERTY_READ) as access:
        return await showings.get_showing(access.conn, business_id, showing_id)


@router.put("/{showing_id}")
async def put_showing(
    business_id: UUID,
    showing_id: UUID,
    body: showings.ShowingInput,
    request: Request,
    principal: CurrentPrincipal,
    idempotency_key: MutationKey,
) -> showings.ShowingView:
    async with _access(business_id, request, principal, Permission.PROPERTY_MANAGE) as access:
        return await showings.create_showing(
            access.conn,
            business_id,
            showing_id,
            user_id=principal.user_id,
            actor=principal.actor,
            key=idempotency_key,
            body=body,
            request_id=get_request_id(request),
        )


@router.post("/{showing_id}/cancel")
async def cancel_showing(
    business_id: UUID,
    showing_id: UUID,
    body: showings.CancelInput,
    request: Request,
    principal: CurrentPrincipal,
    idempotency_key: MutationKey,
) -> showings.ShowingView:
    async with _access(business_id, request, principal, Permission.PROPERTY_MANAGE) as access:
        return await showings.cancel_showing(
            access.conn,
            business_id,
            showing_id,
            user_id=principal.user_id,
            actor=principal.actor,
            key=idempotency_key,
        )
