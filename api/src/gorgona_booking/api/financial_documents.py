"""Company-wide H1 invoice API; published G finance does not enable this feature."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Path, Query, Request

from gorgona_booking.api.businesses import CurrentPrincipal, MutationKey
from gorgona_booking.api.deps import runtime_pool
from gorgona_booking.api.request_id import get_request_id
from gorgona_booking.auth.permissions import Permission
from gorgona_booking.business import financial_documents as service
from gorgona_booking.business.financial_contracts import (
    FinancialCommandReference,
    FinancialCommandStatus,
    InvoiceDocumentView,
    InvoiceDraftInput,
    InvoiceIssueInput,
    InvoiceList,
)
from gorgona_booking.db.schema_guard import assert_location_scope_ready
from gorgona_booking.errors import NotFoundError
from gorgona_booking.tenancy.authorization import TenantAccess, authorized_tenant

router = APIRouter(
    prefix="/v1/businesses/{business_id}/financial-documents", tags=["finance-documents"]
)
CommandKey = Annotated[str, Path(min_length=8, max_length=255, pattern=r"^[A-Za-z0-9._:-]+$")]
Limit = Annotated[int, Query(ge=1, le=100)]


@asynccontextmanager
async def _access(
    request: Request,
    principal: CurrentPrincipal,
    business_id: UUID,
    permission: Permission = Permission.FINANCE_READ,
    *,
    lock: bool = False,
) -> AsyncIterator[TenantAccess]:
    async with authorized_tenant(
        runtime_pool(request),
        principal,
        business_id,
        permission,
        request_id=get_request_id(request),
        exclusive="ledger" if lock or permission != Permission.FINANCE_READ else None,
    ) as access:
        await assert_location_scope_ready(access.conn)
        yield access


@router.get("/books/{book_id}/invoices")
async def invoices(
    business_id: UUID,
    book_id: UUID,
    request: Request,
    principal: CurrentPrincipal,
    after: UUID | None = None,
    limit: Limit = 50,
) -> InvoiceList:
    async with _access(request, principal, business_id) as access:
        return await service.list_invoices(
            access.conn, business_id, book_id, after=after, limit=limit
        )


@router.get("/books/{book_id}/invoices/{document_id}")
async def invoice(
    business_id: UUID,
    book_id: UUID,
    document_id: UUID,
    request: Request,
    principal: CurrentPrincipal,
    revision: Annotated[int | None, Query(ge=1, le=2147483647)] = None,
) -> InvoiceDocumentView:
    async with _access(request, principal, business_id) as access:
        result = await service.load_invoice(
            access.conn, business_id, book_id, document_id, revision=revision
        )
        if result is None:
            raise NotFoundError("Invoice version not found")
        return result


@router.put("/books/{book_id}/invoices/{document_id}")
async def draft(
    business_id: UUID,
    book_id: UUID,
    document_id: UUID,
    body: InvoiceDraftInput,
    request: Request,
    principal: CurrentPrincipal,
    idempotency_key: MutationKey,
) -> InvoiceDocumentView:
    async with _access(request, principal, business_id, Permission.FINANCE_MANAGE) as access:
        return await service.save_draft(
            access.conn,
            business_id=business_id,
            book_id=book_id,
            document_id=document_id,
            user_id=principal.user_id,
            actor=principal.actor,
            key=idempotency_key,
            body=body,
        )


@router.post("/books/{book_id}/invoices/{document_id}/issue")
async def issue(
    business_id: UUID,
    book_id: UUID,
    document_id: UUID,
    body: InvoiceIssueInput,
    request: Request,
    principal: CurrentPrincipal,
    idempotency_key: MutationKey,
) -> InvoiceDocumentView:
    async with _access(request, principal, business_id, Permission.FINANCE_MANAGE) as access:
        return await service.issue_invoice(
            access.conn,
            business_id=business_id,
            book_id=book_id,
            document_id=document_id,
            user_id=principal.user_id,
            actor=principal.actor,
            key=idempotency_key,
            body=body,
        )


@router.post("/commands/{key}/resolve")
async def resolve(
    business_id: UUID,
    key: CommandKey,
    body: FinancialCommandReference,
    request: Request,
    principal: CurrentPrincipal,
) -> FinancialCommandStatus:
    async with _access(request, principal, business_id, lock=True) as access:
        return await service.resolve_command(
            access.conn, business_id=business_id, actor=principal.actor, key=key, body=body
        )


@router.post("/commands/{key}/cancel")
async def cancel(
    business_id: UUID,
    key: CommandKey,
    body: FinancialCommandReference,
    request: Request,
    principal: CurrentPrincipal,
) -> FinancialCommandStatus:
    async with _access(request, principal, business_id, Permission.FINANCE_MANAGE) as access:
        return await service.cancel_command(
            access.conn,
            business_id=business_id,
            user_id=principal.user_id,
            actor=principal.actor,
            key=key,
            body=body,
        )
