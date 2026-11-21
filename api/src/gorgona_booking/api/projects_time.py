"""PRO-01 Slice 3 API: billable time tracking and recurring service schedules/runs."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Query, Request

from gorgona_booking.api.businesses import CurrentPrincipal, MutationKey
from gorgona_booking.api.deps import runtime_pool
from gorgona_booking.api.request_id import get_request_id
from gorgona_booking.auth.permissions import Permission
from gorgona_booking.business import projects_time as pt
from gorgona_booking.db.schema_guard import assert_location_scope_ready
from gorgona_booking.tenancy.authorization import TenantAccess, authorized_tenant

router = APIRouter(prefix="/v1/businesses/{business_id}/projects", tags=["projects"])


@asynccontextmanager
async def _access(
    business_id: UUID,
    request: Request,
    principal: CurrentPrincipal,
    permission: Permission,
) -> AsyncIterator[TenantAccess]:
    async with authorized_tenant(
        runtime_pool(request),
        principal,
        business_id,
        permission,
        allow_location_scope=True,
        allow_delegation=False,
        request_id=get_request_id(request),
    ) as access:
        await assert_location_scope_ready(access.conn)
        yield access


@router.get("/matters/{matter_id}/time-entries")
async def list_time_entries(
    business_id: UUID,
    matter_id: UUID,
    request: Request,
    principal: CurrentPrincipal,
    status: pt.TimeEntryStatus | None = None,
    after: UUID | None = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
) -> pt.TimeEntryList:
    async with _access(business_id, request, principal, Permission.PROJECTS_READ) as access:
        return await pt.list_time_entries(
            access.conn, business_id, matter_id, status=status, after=after, limit=limit
        )


@router.put("/matters/{matter_id}/time-entries/{time_entry_id}")
async def put_time_entry(
    business_id: UUID,
    matter_id: UUID,
    time_entry_id: UUID,
    body: pt.TimeEntryInput,
    request: Request,
    principal: CurrentPrincipal,
    idempotency_key: MutationKey,
) -> pt.TimeEntryView:
    async with _access(business_id, request, principal, Permission.PROJECTS_WORK) as access:
        return await pt.save_time_entry(
            access.conn,
            business_id,
            matter_id,
            time_entry_id,
            user_id=principal.user_id,
            actor=principal.actor,
            key=idempotency_key,
            body=body,
        )


@router.get("/matters/{matter_id}/time-entries/{time_entry_id}/revisions")
async def list_time_entry_revisions(
    business_id: UUID,
    matter_id: UUID,
    time_entry_id: UUID,
    request: Request,
    principal: CurrentPrincipal,
) -> pt.TimeEntryRevisionList:
    async with _access(business_id, request, principal, Permission.PROJECTS_READ) as access:
        return await pt.list_time_entry_revisions(
            access.conn, business_id, matter_id, time_entry_id
        )


@router.post("/matters/{matter_id}/time-entries/{time_entry_id}/decision")
async def post_decide_time_entry(
    business_id: UUID,
    matter_id: UUID,
    time_entry_id: UUID,
    body: pt.TimeEntryDecisionInput,
    request: Request,
    principal: CurrentPrincipal,
    idempotency_key: MutationKey,
) -> pt.TimeEntryView:
    async with _access(business_id, request, principal, Permission.PROJECTS_MANAGE) as access:
        return await pt.decide_time_entry(
            access.conn,
            business_id,
            matter_id,
            time_entry_id,
            user_id=principal.user_id,
            actor=principal.actor,
            key=idempotency_key,
            body=body,
        )


@router.get("/matters/{matter_id}/recurring-schedules")
async def list_recurring_schedules(
    business_id: UUID, matter_id: UUID, request: Request, principal: CurrentPrincipal
) -> pt.RecurringScheduleList:
    async with _access(business_id, request, principal, Permission.PROJECTS_READ) as access:
        return await pt.list_recurring_schedules(access.conn, business_id, matter_id)


@router.put("/matters/{matter_id}/recurring-schedules/{schedule_id}")
async def put_recurring_schedule(
    business_id: UUID,
    matter_id: UUID,
    schedule_id: UUID,
    body: pt.RecurringScheduleInput,
    request: Request,
    principal: CurrentPrincipal,
    idempotency_key: MutationKey,
) -> pt.RecurringScheduleView:
    async with _access(business_id, request, principal, Permission.PROJECTS_MANAGE) as access:
        return await pt.save_recurring_schedule(
            access.conn,
            business_id,
            matter_id,
            schedule_id,
            user_id=principal.user_id,
            actor=principal.actor,
            key=idempotency_key,
            body=body,
        )


@router.get("/matters/{matter_id}/recurring-runs")
async def list_recurring_runs(
    business_id: UUID,
    matter_id: UUID,
    request: Request,
    principal: CurrentPrincipal,
    schedule_id: UUID | None = None,
) -> pt.RecurringRunList:
    async with _access(business_id, request, principal, Permission.PROJECTS_READ) as access:
        return await pt.list_recurring_runs(
            access.conn, business_id, matter_id, schedule_id=schedule_id
        )


@router.post("/matters/{matter_id}/recurring-schedules/{schedule_id}/run")
async def post_materialize_recurring_run(
    business_id: UUID,
    matter_id: UUID,
    schedule_id: UUID,
    body: pt.RecurringRunTriggerInput,
    request: Request,
    principal: CurrentPrincipal,
    idempotency_key: MutationKey,
) -> pt.RecurringRunView:
    async with _access(business_id, request, principal, Permission.PROJECTS_MANAGE) as access:
        return await pt.materialize_recurring_run(
            access.conn,
            business_id,
            matter_id,
            schedule_id,
            user_id=principal.user_id,
            actor=principal.actor,
            key=idempotency_key,
            body=body,
        )
