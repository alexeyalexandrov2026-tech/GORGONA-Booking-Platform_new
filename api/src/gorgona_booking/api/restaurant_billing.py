"""REST-01 Slice 4: check splitting, FIN-03 per-share invoicing and coordinated refunds."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Path, Request

from gorgona_booking.api.businesses import CurrentPrincipal, MutationKey
from gorgona_booking.api.deps import runtime_pool
from gorgona_booking.api.request_id import get_request_id
from gorgona_booking.auth.permissions import Permission
from gorgona_booking.business import restaurant_billing as billing
from gorgona_booking.db.schema_guard import assert_location_scope_ready
from gorgona_booking.tenancy.authorization import TenantAccess, authorized_tenant

router = APIRouter(prefix="/v1/businesses/{business_id}/restaurant", tags=["restaurant"])


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


@router.get("/checks/{check_id}/split")
async def get_check_split(
    business_id: UUID,
    check_id: UUID,
    request: Request,
    principal: CurrentPrincipal,
) -> billing.CheckSplitView:
    async with _access(business_id, request, principal, Permission.RESTAURANT_READ) as access:
        return await billing.get_check_split(access.conn, business_id, check_id)


@router.post("/checks/{check_id}/split")
async def split_check(
    business_id: UUID,
    check_id: UUID,
    body: billing.SplitCheckInput,
    request: Request,
    principal: CurrentPrincipal,
    idempotency_key: MutationKey,
) -> billing.CheckSplitView:
    async with _access(business_id, request, principal, Permission.RESTAURANT_SERVICE) as access:
        return await billing.split_check(
            access.conn,
            business_id,
            check_id,
            location_scope=access.location_id,
            user_id=principal.user_id,
            actor=principal.actor,
            key=idempotency_key,
            body=body,
        )


@router.post("/checks/{check_id}/shares/{share_no}/bill")
async def bill_check_share(
    business_id: UUID,
    check_id: UUID,
    share_no: Annotated[int, Path(ge=1, le=20)],
    body: billing.BillShareInput,
    request: Request,
    principal: CurrentPrincipal,
    idempotency_key: MutationKey,
) -> billing.CheckBillView:
    async with _access(business_id, request, principal, Permission.RESTAURANT_MANAGE) as access:
        return await billing.bill_check_share(
            access.conn,
            business_id,
            check_id,
            share_no,
            location_scope=access.location_id,
            user_id=principal.user_id,
            actor=principal.actor,
            key=idempotency_key,
            body=body,
        )


@router.post("/checks/{check_id}/refunds")
async def record_check_refund(
    business_id: UUID,
    check_id: UUID,
    body: billing.RefundCheckInput,
    request: Request,
    principal: CurrentPrincipal,
    idempotency_key: MutationKey,
) -> billing.CheckRefundView:
    async with _access(business_id, request, principal, Permission.RESTAURANT_MANAGE) as access:
        return await billing.record_check_refund(
            access.conn,
            business_id,
            check_id,
            location_scope=access.location_id,
            user_id=principal.user_id,
            actor=principal.actor,
            key=idempotency_key,
            body=body,
        )


@router.get("/checks/{check_id}/reconciliation")
async def get_check_reconciliation(
    business_id: UUID,
    check_id: UUID,
    request: Request,
    principal: CurrentPrincipal,
) -> billing.CheckReconciliationView:
    async with _access(business_id, request, principal, Permission.RESTAURANT_READ) as access:
        return await billing.get_check_reconciliation(
            access.conn,
            business_id,
            check_id,
            location_scope=access.location_id,
        )
