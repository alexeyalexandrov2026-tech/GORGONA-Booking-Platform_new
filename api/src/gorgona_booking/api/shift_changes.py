"""Self actions use trusted participant filters; management keeps branch scope."""

from datetime import timedelta
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Query, Request
from pydantic import AwareDatetime

from gorgona_booking.api.businesses import CurrentPrincipal, MutationKey
from gorgona_booking.api.workforce import Limit, Revision, _access
from gorgona_booking.auth.permissions import Permission
from gorgona_booking.business import shift_changes as service
from gorgona_booking.business import workforce
from gorgona_booking.business.shift_change_contracts import (
    ChangeEventInput,
    ChangeHistory,
    ChangeInput,
    ChangeList,
    ChangeView,
    ColleagueList,
)
from gorgona_booking.business.workforce_contracts import ShiftList
from gorgona_booking.errors import DomainError, NotFoundError

router = APIRouter(prefix="/v1/businesses/{business_id}/workforce", tags=["workforce"])


@router.put("/changes/{request_id}")
async def put_change(
    business_id: UUID,
    request_id: UUID,
    body: ChangeInput,
    request: Request,
    principal: CurrentPrincipal,
    idempotency_key: MutationKey,
) -> ChangeView:
    async with _access(request, principal, business_id, Permission.WORKFORCE_SELF) as access:
        # SQL requires this verified user to own the outgoing assignment, or be
        # the named pickup recipient. It cannot create a request for another user.
        await access.conn.execute("select set_config('gba.location_id','',true)")
        return await service.propose(
            access.conn,
            business_id,
            request_id,
            principal.user_id,
            principal.actor,
            idempotency_key,
            body,
        )


@router.post("/changes/{request_id}/events")
async def post_event(
    business_id: UUID,
    request_id: UUID,
    body: ChangeEventInput,
    request: Request,
    principal: CurrentPrincipal,
    idempotency_key: MutationKey,
) -> ChangeView:
    permission = (
        Permission.WORKFORCE_MANAGE if body.action == "approve" else Permission.WORKFORCE_SELF
    )
    async with _access(request, principal, business_id, permission) as access:
        participant = None
        if body.action in ("accept", "withdraw") or access.role not in ("owner", "manager"):
            participant = principal.user_id
            await access.conn.execute("select set_config('gba.location_id','',true)")
        elif body.action == "decline":
            # A branch manager can also be the recipient of their OWN cross-home
            # request. Probe only that user's immutable participant association;
            # otherwise restore management scope before reading any other request.
            await access.conn.execute("select set_config('gba.location_id','',true)")
            try:
                await service.load(
                    access.conn, business_id, request_id, participant=principal.user_id
                )
            except NotFoundError:
                await access.conn.execute(
                    "select set_config('gba.location_id',%s,true)",
                    (str(access.location_id) if access.location_id else "",),
                )
            else:
                participant = principal.user_id
        return await service.event(
            access.conn,
            business_id,
            request_id,
            principal.user_id,
            principal.actor,
            idempotency_key,
            body,
            participant,
        )


@router.get("/changes")
async def get_changes(
    business_id: UUID,
    request: Request,
    principal: CurrentPrincipal,
    after: UUID | None = None,
    limit: Limit = 100,
) -> ChangeList:
    async with _access(request, principal, business_id) as access:
        return await service.list_requests(access.conn, business_id, None, after, limit)


@router.get("/changes/{request_id}")
async def get_change(
    business_id: UUID,
    request_id: UUID,
    request: Request,
    principal: CurrentPrincipal,
    revision: Revision = None,
) -> ChangeView:
    async with _access(request, principal, business_id) as access:
        return await service.load(access.conn, business_id, request_id, revision)


@router.get("/changes/{request_id}/history")
async def get_history(
    business_id: UUID,
    request_id: UUID,
    request: Request,
    principal: CurrentPrincipal,
    after_revision: Annotated[int, Query(ge=0)] = 0,
    limit: Limit = 100,
) -> ChangeHistory:
    async with _access(request, principal, business_id) as access:
        return await service.history(
            access.conn, business_id, request_id, None, after_revision, limit
        )


@router.get("/my-changes")
async def get_my_changes(
    business_id: UUID,
    request: Request,
    principal: CurrentPrincipal,
    after: UUID | None = None,
    limit: Limit = 100,
) -> ChangeList:
    async with _access(request, principal, business_id, Permission.WORKFORCE_SELF) as access:
        await access.conn.execute("select set_config('gba.location_id','',true)")
        return await service.list_requests(
            access.conn, business_id, principal.user_id, after, limit
        )


@router.get("/my-changes/{request_id}")
async def get_my_change(
    business_id: UUID,
    request_id: UUID,
    request: Request,
    principal: CurrentPrincipal,
    revision: Revision = None,
) -> ChangeView:
    async with _access(request, principal, business_id, Permission.WORKFORCE_SELF) as access:
        await access.conn.execute("select set_config('gba.location_id','',true)")
        return await service.load(access.conn, business_id, request_id, revision, principal.user_id)


@router.get("/my-changes/{request_id}/history")
async def get_my_history(
    business_id: UUID,
    request_id: UUID,
    request: Request,
    principal: CurrentPrincipal,
    after_revision: Annotated[int, Query(ge=0)] = 0,
    limit: Limit = 100,
) -> ChangeHistory:
    async with _access(request, principal, business_id, Permission.WORKFORCE_SELF) as access:
        await access.conn.execute("select set_config('gba.location_id','',true)")
        return await service.history(
            access.conn, business_id, request_id, principal.user_id, after_revision, limit
        )


@router.get("/colleagues")
async def get_colleagues(
    business_id: UUID,
    request: Request,
    principal: CurrentPrincipal,
    after: UUID | None = None,
    limit: Limit = 100,
) -> ColleagueList:
    async with _access(request, principal, business_id, Permission.WORKFORCE_SELF) as access:
        return await service.colleagues(access.conn, business_id, principal.user_id, after, limit)


@router.get("/open-shifts")
async def get_open_shifts(
    business_id: UUID,
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
        location = await service.home(access.conn, business_id, principal.user_id)
        if location is None:
            return ShiftList(items=())
        await access.conn.execute("select set_config('gba.location_id',%s,true)", (str(location),))
        return await workforce.list_shifts(
            access.conn, business_id, starts, ends, after, limit, None, open_only=True
        )
