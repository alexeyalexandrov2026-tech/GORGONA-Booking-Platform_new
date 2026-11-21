"""SUPPLY-01 Slice 2 API routes: Manufacturing BOMs, work orders, issues, returns, QC, and
output."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from uuid import UUID

from fastapi import APIRouter, Request

from gorgona_booking.api.businesses import CurrentPrincipal, MutationKey
from gorgona_booking.api.deps import runtime_pool
from gorgona_booking.api.request_id import get_request_id
from gorgona_booking.auth.permissions import ROLE_PERMISSIONS, Permission
from gorgona_booking.business import supply_manufacturing as sm
from gorgona_booking.db.schema_guard import assert_location_scope_ready
from gorgona_booking.tenancy.authorization import (
    PermissionDeniedError,
    TenantAccess,
    authorized_tenant,
)

router = APIRouter(prefix="/v1/businesses/{business_id}/supply", tags=["supply"])


@asynccontextmanager
async def _access(
    request: Request,
    principal: CurrentPrincipal,
    business_id: UUID,
    permission: Permission = Permission.SUPPLY_READ,
    *,
    company_wide_finance: bool = False,
) -> AsyncIterator[TenantAccess]:
    async with authorized_tenant(
        runtime_pool(request),
        principal,
        business_id,
        permission,
        request_id=get_request_id(request),
        allow_location_scope=not company_wide_finance,
    ) as access:
        if company_wide_finance:
            allowed = ROLE_PERMISSIONS.get(access.role or "", frozenset())
            if access.via != "platform" and (
                Permission.FINANCE_MANAGE not in allowed
                or Permission.INVENTORY_MANAGE not in allowed
            ):
                raise PermissionDeniedError("Insufficient permissions for supply financial posting")
        await assert_location_scope_ready(access.conn)
        yield access


@router.get("/boms")
async def get_boms(
    business_id: UUID,
    request: Request,
    principal: CurrentPrincipal,
    location_id: UUID | None = None,
) -> sm.BomList:
    async with _access(request, principal, business_id) as access:
        return await sm.list_boms(access.conn, business_id, location_id=location_id)


@router.put("/boms/{bom_id}")
async def put_bom(
    business_id: UUID,
    bom_id: UUID,
    body: sm.BomInput,
    request: Request,
    principal: CurrentPrincipal,
    idempotency_key: MutationKey,
) -> sm.BomView:
    async with _access(request, principal, business_id, Permission.SUPPLY_MANAGE) as access:
        return await sm.save_bom(
            access.conn,
            business_id,
            bom_id,
            user_id=principal.user_id,
            actor=principal.actor,
            key=idempotency_key,
            body=body,
        )


@router.get("/work-orders")
async def get_work_orders(
    business_id: UUID,
    request: Request,
    principal: CurrentPrincipal,
    location_id: UUID | None = None,
) -> sm.WorkOrderList:
    async with _access(request, principal, business_id) as access:
        return await sm.list_work_orders(access.conn, business_id, location_id=location_id)


@router.put("/work-orders/{work_order_id}")
async def put_work_order(
    business_id: UUID,
    work_order_id: UUID,
    body: sm.WorkOrderInput,
    request: Request,
    principal: CurrentPrincipal,
    idempotency_key: MutationKey,
) -> sm.WorkOrderView:
    async with _access(request, principal, business_id, Permission.SUPPLY_WORK) as access:
        return await sm.save_work_order(
            access.conn,
            business_id,
            work_order_id,
            user_id=principal.user_id,
            actor=principal.actor,
            key=idempotency_key,
            body=body,
        )


@router.get("/work-orders/{work_order_id}/issues")
async def get_wo_issues(
    business_id: UUID,
    work_order_id: UUID,
    request: Request,
    principal: CurrentPrincipal,
) -> sm.WorkOrderIssueList:
    async with _access(request, principal, business_id) as access:
        return await sm.list_work_order_issues(access.conn, business_id, work_order_id)


@router.post("/work-orders/{work_order_id}/issues")
async def post_wo_issue(
    business_id: UUID,
    work_order_id: UUID,
    body: sm.WorkOrderIssueInput,
    request: Request,
    principal: CurrentPrincipal,
    idempotency_key: MutationKey,
) -> sm.WorkOrderIssueView:
    async with _access(
        request,
        principal,
        business_id,
        Permission.SUPPLY_MANAGE,
        company_wide_finance=True,
    ) as access:
        return await sm.issue_work_order_material(
            access.conn,
            business_id,
            work_order_id,
            user_id=principal.user_id,
            actor=principal.actor,
            key=idempotency_key,
            body=body,
        )


@router.get("/work-orders/{work_order_id}/returns")
async def get_wo_returns(
    business_id: UUID,
    work_order_id: UUID,
    request: Request,
    principal: CurrentPrincipal,
) -> sm.WorkOrderReturnList:
    async with _access(request, principal, business_id) as access:
        return await sm.list_work_order_returns(access.conn, business_id, work_order_id)


@router.post("/work-orders/{work_order_id}/returns")
async def post_wo_return(
    business_id: UUID,
    work_order_id: UUID,
    body: sm.WorkOrderReturnInput,
    request: Request,
    principal: CurrentPrincipal,
    idempotency_key: MutationKey,
) -> sm.WorkOrderReturnView:
    async with _access(
        request,
        principal,
        business_id,
        Permission.SUPPLY_MANAGE,
        company_wide_finance=True,
    ) as access:
        return await sm.return_work_order_material(
            access.conn,
            business_id,
            work_order_id,
            user_id=principal.user_id,
            actor=principal.actor,
            key=idempotency_key,
            body=body,
        )


@router.post("/work-orders/{work_order_id}/qc")
async def post_wo_qc(
    business_id: UUID,
    work_order_id: UUID,
    body: sm.WorkOrderQcInput,
    request: Request,
    principal: CurrentPrincipal,
    idempotency_key: MutationKey,
) -> sm.WorkOrderQcView:
    async with _access(request, principal, business_id, Permission.SUPPLY_WORK) as access:
        return await sm.record_work_order_qc(
            access.conn,
            business_id,
            work_order_id,
            user_id=principal.user_id,
            actor=principal.actor,
            key=idempotency_key,
            body=body,
        )


@router.get("/work-orders/{work_order_id}/output")
async def get_wo_output(
    business_id: UUID,
    work_order_id: UUID,
    request: Request,
    principal: CurrentPrincipal,
) -> sm.WorkOrderOutputView:
    async with _access(request, principal, business_id) as access:
        return await sm.get_work_order_output(access.conn, business_id, work_order_id)


@router.post("/work-orders/{work_order_id}/output")
async def post_wo_output(
    business_id: UUID,
    work_order_id: UUID,
    body: sm.WorkOrderOutputInput,
    request: Request,
    principal: CurrentPrincipal,
    idempotency_key: MutationKey,
) -> sm.WorkOrderOutputView:
    async with _access(
        request,
        principal,
        business_id,
        Permission.SUPPLY_MANAGE,
        company_wide_finance=True,
    ) as access:
        return await sm.complete_work_order_output(
            access.conn,
            business_id,
            work_order_id,
            user_id=principal.user_id,
            actor=principal.actor,
            key=idempotency_key,
            body=body,
        )
