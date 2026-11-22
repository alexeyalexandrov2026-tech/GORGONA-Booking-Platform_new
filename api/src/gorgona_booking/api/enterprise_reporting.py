"""HTTP routes for ENTERPRISE-01 Slice 2 (0144): consent-based group reporting grants,
member aggregate report snapshots, and organizer consolidated group reports.
"""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from uuid import UUID

from fastapi import APIRouter, Request

from gorgona_booking.api.businesses import CurrentPrincipal, MutationKey
from gorgona_booking.api.deps import runtime_pool
from gorgona_booking.api.request_id import get_request_id
from gorgona_booking.auth.permissions import Permission
from gorgona_booking.business import enterprise_reporting as er
from gorgona_booking.db.schema_guard import assert_location_scope_ready
from gorgona_booking.tenancy.authorization import TenantAccess, authorized_tenant

router = APIRouter(prefix="/v1/businesses/{business_id}/enterprise", tags=["enterprise"])


@asynccontextmanager
async def _access(
    request: Request,
    principal: CurrentPrincipal,
    business_id: UUID,
    permission: Permission = Permission.ENTERPRISE_READ,
) -> AsyncIterator[TenantAccess]:
    async with authorized_tenant(
        runtime_pool(request),
        principal,
        business_id,
        permission,
        request_id=get_request_id(request),
        allow_location_scope=False,
    ) as access:
        await assert_location_scope_ready(access.conn)
        yield access


@router.get("/group-report-grants", response_model=er.GroupReportGrantList)
async def get_group_report_grants(
    business_id: UUID,
    request: Request,
    principal: CurrentPrincipal,
    group_id: UUID | None = None,
) -> er.GroupReportGrantList:
    async with _access(request, principal, business_id) as access:
        return await er.list_report_grants(access.conn, business_id, group_id=group_id)


@router.put("/group-report-grants/{grant_id}", response_model=er.GroupReportGrantView)
async def put_group_report_grant(
    business_id: UUID,
    grant_id: UUID,
    body: er.GroupReportGrantInput,
    request: Request,
    principal: CurrentPrincipal,
    key: MutationKey,
) -> er.GroupReportGrantView:
    async with _access(request, principal, business_id, Permission.ENTERPRISE_MANAGE) as access:
        return await er.save_report_grant(
            access.conn,
            business_id,
            grant_id,
            user_id=principal.user_id,
            actor=principal.actor,
            key=key,
            body=body,
        )


@router.put("/group-report-snapshots/{snapshot_id}", response_model=er.GroupReportSnapshotView)
async def put_group_report_snapshot(
    business_id: UUID,
    snapshot_id: UUID,
    body: er.GroupReportSnapshotInput,
    request: Request,
    principal: CurrentPrincipal,
    key: MutationKey,
) -> er.GroupReportSnapshotView:
    async with _access(request, principal, business_id, Permission.ENTERPRISE_MANAGE) as access:
        return await er.publish_report_snapshot(
            access.conn,
            business_id,
            snapshot_id,
            user_id=principal.user_id,
            actor=principal.actor,
            key=key,
            body=body,
        )


@router.get(
    "/groups/{group_id}/consolidated-report",
    response_model=er.ConsolidatedGroupReportView,
)
async def get_group_consolidated_report(
    business_id: UUID,
    group_id: UUID,
    request: Request,
    principal: CurrentPrincipal,
    period_key: str | None = None,
) -> er.ConsolidatedGroupReportView:
    async with _access(request, principal, business_id) as access:
        return await er.get_consolidated_group_report(
            access.conn, business_id, group_id, period_key=period_key
        )
