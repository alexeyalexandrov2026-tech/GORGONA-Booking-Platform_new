"""Staff reservations of resources (ADR-0022): branch-scoped staff management routes."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import timedelta
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Path, Query, Request
from pydantic import AwareDatetime

from gorgona_booking.api.businesses import CurrentPrincipal, MutationKey
from gorgona_booking.api.deps import runtime_pool
from gorgona_booking.api.request_id import get_request_id
from gorgona_booking.auth.permissions import Permission
from gorgona_booking.db.schema_guard import assert_location_scope_ready
from gorgona_booking.errors import DomainError, NotFoundError
from gorgona_booking.occupancy import reservations as service
from gorgona_booking.occupancy.reservation_contracts import (
    CancelInput,
    ReservationInput,
    ReservationList,
    ReservationView,
)
from gorgona_booking.tenancy.authorization import TenantAccess, authorized_tenant

router = APIRouter(prefix="/v1/businesses", tags=["resource-reservations"])
ReservationId = Annotated[UUID, Path()]
_MAX_WINDOW = timedelta(days=62)


class ReservationWindowError(DomainError):
    code = "RESERVATION_WINDOW_INVALID"


@asynccontextmanager
async def _access(
    request: Request,
    principal: CurrentPrincipal,
    business_id: UUID,
    *,
    write: bool = False,
) -> AsyncIterator[TenantAccess]:
    # Resources are staff of a branch: branch managers act within their branch only.
    async with authorized_tenant(
        runtime_pool(request),
        principal,
        business_id,
        Permission.STAFF_MANAGE if write else Permission.STAFF_READ,
        request_id=get_request_id(request),
        allow_location_scope=True,
    ) as access:
        await assert_location_scope_ready(access.conn)
        yield access


@router.get("/{business_id}/resource-reservations")
async def get_reservations(
    business_id: UUID,
    request: Request,
    principal: CurrentPrincipal,
    starts: Annotated[AwareDatetime, Query()],
    ends: Annotated[AwareDatetime, Query()],
    location_id: UUID | None = None,
) -> ReservationList:
    if not starts < ends <= starts + _MAX_WINDOW:
        raise ReservationWindowError("Ask for at most 62 days, ending after the start")
    async with _access(request, principal, business_id) as access:
        if location_id is not None:
            access.require_location(location_id)
        return await service.list_reservations(
            access.conn, business_id, starts=starts, ends=ends, location_id=location_id
        )


@router.get("/{business_id}/resource-reservations/{reservation_id}")
async def get_reservation(
    business_id: UUID,
    reservation_id: ReservationId,
    request: Request,
    principal: CurrentPrincipal,
) -> ReservationView:
    async with _access(request, principal, business_id) as access:
        result = await service.load_reservation(access.conn, business_id, reservation_id)
        if result is None:
            raise NotFoundError("Reservation not found")
        return result


@router.put("/{business_id}/resource-reservations/{reservation_id}")
async def put_reservation(
    business_id: UUID,
    reservation_id: ReservationId,
    body: ReservationInput,
    request: Request,
    principal: CurrentPrincipal,
    idempotency_key: MutationKey,
) -> ReservationView:
    async with _access(request, principal, business_id, write=True) as access:
        access.require_location(body.location_id)
        return await service.create_reservation(
            access.conn,
            business_id=business_id,
            reservation_id=reservation_id,
            user_id=principal.user_id,
            actor=principal.actor,
            key=idempotency_key,
            body=body,
            request_id=get_request_id(request),
        )


@router.post("/{business_id}/resource-reservations/{reservation_id}/cancel")
async def post_cancel(
    business_id: UUID,
    reservation_id: ReservationId,
    body: CancelInput,
    request: Request,
    principal: CurrentPrincipal,
    idempotency_key: MutationKey,
) -> ReservationView:
    async with _access(request, principal, business_id, write=True) as access:
        return await service.cancel_reservation(
            access.conn,
            business_id=business_id,
            reservation_id=reservation_id,
            user_id=principal.user_id,
            actor=principal.actor,
            key=idempotency_key,
            body=body,
        )
