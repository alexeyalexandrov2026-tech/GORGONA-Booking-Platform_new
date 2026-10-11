"""I4 screen support routes; the same access rules as the other workforce routes."""

from datetime import timedelta
from uuid import UUID

from fastapi import APIRouter, Request
from pydantic import AwareDatetime

from gorgona_booking.api.businesses import CurrentPrincipal
from gorgona_booking.api.workforce import Limit, _access
from gorgona_booking.auth.permissions import Permission
from gorgona_booking.business import workforce_desk as service
from gorgona_booking.business.workforce_contracts import ShiftList
from gorgona_booking.business.workforce_desk_contracts import (
    CommandReference,
    CommandStatus,
    DeskView,
    DirectoryList,
)
from gorgona_booking.errors import DomainError

router = APIRouter(prefix="/v1/businesses/{business_id}/workforce", tags=["workforce"])


@router.get("/desk")
async def get_desk(business_id: UUID, request: Request, principal: CurrentPrincipal) -> DeskView:
    async with _access(request, principal, business_id, Permission.WORKFORCE_SELF) as access:
        # Only the caller's own profile is read; the SQL filters the trusted user id.
        await access.conn.execute("select set_config('gba.location_id','',true)")
        return await service.desk(access.conn, business_id, principal.user_id)


@router.get("/directory")
async def get_directory(
    business_id: UUID,
    request: Request,
    principal: CurrentPrincipal,
    after: UUID | None = None,
    limit: Limit = 100,
) -> DirectoryList:
    async with _access(request, principal, business_id) as access:
        return await service.directory(access.conn, business_id, access.location_id, after, limit)


@router.get("/colleagues/{profile_id}/shifts")
async def get_colleague_shifts(
    business_id: UUID,
    profile_id: UUID,
    request: Request,
    principal: CurrentPrincipal,
    starts: AwareDatetime,
    ends: AwareDatetime,
    after: UUID | None = None,
    limit: Limit = 100,
) -> ShiftList:
    if not timedelta(0) < ends - starts <= timedelta(days=62):
        raise DomainError("Request a schedule window of at most 62 days")
    async with _access(request, principal, business_id, Permission.WORKFORCE_SELF) as access:
        return await service.colleague_shifts(
            access.conn, business_id, principal.user_id, profile_id, starts, ends, after, limit
        )


@router.post("/commands/{key}/resolve")
async def resolve(
    business_id: UUID,
    key: str,
    body: CommandReference,
    request: Request,
    principal: CurrentPrincipal,
) -> CommandStatus:
    async with _access(request, principal, business_id, Permission.WORKFORCE_SELF) as access:
        return await service.resolve_command(access.conn, business_id, principal.actor, key, body)


@router.post("/commands/{key}/cancel")
async def cancel(
    business_id: UUID,
    key: str,
    body: CommandReference,
    request: Request,
    principal: CurrentPrincipal,
) -> CommandStatus:
    async with _access(request, principal, business_id, Permission.WORKFORCE_SELF) as access:
        return await service.cancel_command(access.conn, business_id, principal.actor, key, body)
