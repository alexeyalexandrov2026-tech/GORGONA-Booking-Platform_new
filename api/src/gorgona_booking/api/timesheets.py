"""Own time commands, scoped managerial decisions, immutable history."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Query, Request

from gorgona_booking.api.businesses import CurrentPrincipal, MutationKey
from gorgona_booking.api.workforce import Limit, Revision, _access
from gorgona_booking.auth.permissions import Permission
from gorgona_booking.business import timesheets as service
from gorgona_booking.business.timesheet_contracts import (
    ClockInInput,
    TimeCommand,
    TimeHistory,
    TimeList,
    TimeView,
)

router = APIRouter(prefix="/v1/businesses/{business_id}/workforce", tags=["workforce"])


@router.put("/time-entries/{entry_id}")
async def put_time(
    business_id: UUID,
    entry_id: UUID,
    body: ClockInInput,
    request: Request,
    principal: CurrentPrincipal,
    idempotency_key: MutationKey,
) -> TimeView:
    async with _access(request, principal, business_id, Permission.WORKFORCE_SELF) as access:
        await access.conn.execute("select set_config('gba.location_id','',true)")
        return await service.clock_in(
            access.conn,
            business_id,
            entry_id,
            principal.user_id,
            principal.actor,
            idempotency_key,
            body,
        )


@router.post("/time-entries/{entry_id}/events")
async def post_event(
    business_id: UUID,
    entry_id: UUID,
    body: TimeCommand,
    request: Request,
    principal: CurrentPrincipal,
    idempotency_key: MutationKey,
) -> TimeView:
    managerial = body.action in ("approve", "decline")
    permission = Permission.WORKFORCE_MANAGE if managerial else Permission.WORKFORCE_SELF
    async with _access(request, principal, business_id, permission) as access:
        participant = None
        if not managerial:
            participant = principal.user_id
            await access.conn.execute("select set_config('gba.location_id','',true)")
        return await service.event(
            access.conn,
            business_id,
            entry_id,
            principal.user_id,
            principal.actor,
            idempotency_key,
            body,
            participant,
        )


@router.get("/time-entries")
async def get_times(
    business_id: UUID,
    request: Request,
    principal: CurrentPrincipal,
    after: UUID | None = None,
    limit: Limit = 100,
    open_only: bool = False,
) -> TimeList:
    async with _access(request, principal, business_id) as access:
        return await service.list_entries(access.conn, business_id, None, after, limit, open_only)


@router.get("/my-time-entries")
async def get_my_times(
    business_id: UUID,
    request: Request,
    principal: CurrentPrincipal,
    after: UUID | None = None,
    limit: Limit = 100,
    open_only: bool = False,
) -> TimeList:
    async with _access(request, principal, business_id, Permission.WORKFORCE_SELF) as access:
        await access.conn.execute("select set_config('gba.location_id','',true)")
        return await service.list_entries(
            access.conn, business_id, principal.user_id, after, limit, open_only
        )


@router.get("/time-entries/{entry_id}")
async def get_time(
    business_id: UUID,
    entry_id: UUID,
    request: Request,
    principal: CurrentPrincipal,
    revision: Revision = None,
) -> TimeView:
    async with _access(request, principal, business_id) as access:
        return await service.load(access.conn, business_id, entry_id, revision)


@router.get("/my-time-entries/{entry_id}")
async def get_my_time(
    business_id: UUID,
    entry_id: UUID,
    request: Request,
    principal: CurrentPrincipal,
    revision: Revision = None,
) -> TimeView:
    async with _access(request, principal, business_id, Permission.WORKFORCE_SELF) as access:
        await access.conn.execute("select set_config('gba.location_id','',true)")
        return await service.load(access.conn, business_id, entry_id, revision, principal.user_id)


@router.get("/time-entries/{entry_id}/history")
async def get_history(
    business_id: UUID,
    entry_id: UUID,
    request: Request,
    principal: CurrentPrincipal,
    after_revision: Annotated[int, Query(ge=0)] = 0,
    limit: Limit = 100,
) -> TimeHistory:
    async with _access(request, principal, business_id) as access:
        return await service.history(
            access.conn, business_id, entry_id, None, after_revision, limit
        )


@router.get("/my-time-entries/{entry_id}/history")
async def get_my_history(
    business_id: UUID,
    entry_id: UUID,
    request: Request,
    principal: CurrentPrincipal,
    after_revision: Annotated[int, Query(ge=0)] = 0,
    limit: Limit = 100,
) -> TimeHistory:
    async with _access(request, principal, business_id, Permission.WORKFORCE_SELF) as access:
        await access.conn.execute("select set_config('gba.location_id','',true)")
        return await service.history(
            access.conn, business_id, entry_id, principal.user_id, after_revision, limit
        )
