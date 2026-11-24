"""PRO-01 Slice 4 API: FIN-03 matter invoicing and ACL-enforced audited exports."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from uuid import UUID

from fastapi import APIRouter, Request

from gorgona_booking.api.businesses import CurrentPrincipal, MutationKey
from gorgona_booking.api.deps import runtime_pool
from gorgona_booking.api.request_id import get_request_id
from gorgona_booking.auth.permissions import ROLE_PERMISSIONS, Permission
from gorgona_booking.business import projects_billing as pb
from gorgona_booking.db.schema_guard import assert_location_scope_ready
from gorgona_booking.tenancy.authorization import (
    PermissionDeniedError,
    TenantAccess,
    authorized_tenant,
)

router = APIRouter(prefix="/v1/businesses/{business_id}/projects", tags=["projects"])


@asynccontextmanager
async def _access(
    business_id: UUID,
    request: Request,
    principal: CurrentPrincipal,
    permission: Permission,
    *,
    allow_location_scope: bool = True,
) -> AsyncIterator[TenantAccess]:
    async with authorized_tenant(
        runtime_pool(request),
        principal,
        business_id,
        permission,
        allow_location_scope=allow_location_scope,
        allow_delegation=False,
        request_id=get_request_id(request),
    ) as access:
        await assert_location_scope_ready(access.conn)
        yield access


@router.get("/matters/{matter_id}/invoices")
async def list_matter_invoices(
    business_id: UUID, matter_id: UUID, request: Request, principal: CurrentPrincipal
) -> pb.MatterInvoiceList:
    async with _access(business_id, request, principal, Permission.PROJECTS_READ) as access:
        return await pb.list_matter_invoices(access.conn, business_id, matter_id)


@router.post("/matters/{matter_id}/invoices")
async def post_matter_invoice(
    business_id: UUID,
    matter_id: UUID,
    body: pb.MatterInvoiceInput,
    request: Request,
    principal: CurrentPrincipal,
    idempotency_key: MutationKey,
) -> pb.MatterInvoiceView:
    # Issuing FIN-03 drafts requires company-wide scope + FINANCE_MANAGE + PROJECTS_MANAGE.
    async with _access(
        business_id,
        request,
        principal,
        Permission.PROJECTS_MANAGE,
        allow_location_scope=False,
    ) as access:
        if Permission.FINANCE_MANAGE not in ROLE_PERMISSIONS.get(access.role or "", frozenset()):
            raise PermissionDeniedError("Finance management permission is required to bill matters")
        return await pb.create_matter_invoice(
            access.conn,
            business_id,
            matter_id,
            user_id=principal.user_id,
            actor=principal.actor,
            key=idempotency_key,
            body=body,
        )


@router.get("/exports")
async def list_exports(
    business_id: UUID, request: Request, principal: CurrentPrincipal
) -> pb.ProjectExportList:
    async with _access(business_id, request, principal, Permission.PROJECTS_READ) as access:
        return await pb.list_exports(access.conn, business_id)


@router.post("/matters/{matter_id}/exports")
async def post_export_matter(
    business_id: UUID,
    matter_id: UUID,
    request: Request,
    principal: CurrentPrincipal,
    idempotency_key: MutationKey,
) -> pb.MatterExportPayload:
    async with _access(business_id, request, principal, Permission.PROJECTS_READ) as access:
        return await pb.export_matter(
            access.conn,
            business_id,
            matter_id,
            user_id=principal.user_id,
            actor=principal.actor,
            key=idempotency_key,
        )


@router.post("/exports")
async def post_export_portfolio(
    business_id: UUID,
    body: pb.PortfolioExportInput,
    request: Request,
    principal: CurrentPrincipal,
    idempotency_key: MutationKey,
) -> pb.PortfolioExportPayload:
    async with _access(business_id, request, principal, Permission.PROJECTS_READ) as access:
        return await pb.export_portfolio(
            access.conn,
            business_id,
            location_scope=access.location_id,
            user_id=principal.user_id,
            actor=principal.actor,
            key=idempotency_key,
            body=body,
        )
