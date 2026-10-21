"""Company-wide H invoice and manual-accrual API; G finance alone does not enable it."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Path, Query, Request

from gorgona_booking.api.businesses import CurrentPrincipal, MutationKey
from gorgona_booking.api.deps import runtime_pool
from gorgona_booking.api.request_id import get_request_id
from gorgona_booking.auth.permissions import Permission
from gorgona_booking.business import (
    credit_notes,
    financial_commands,
    provider_payments,
    provider_review,
    settlements,
)
from gorgona_booking.business import financial_documents as service
from gorgona_booking.business.financial_contracts import (
    CreditDraftInput,
    CreditIssueInput,
    CreditList,
    CreditNoteView,
    CreditVoidInput,
    DocumentKind,
    FinancialCommandReference,
    FinancialCommandStatus,
    FinancialWorkflowStatus,
    InvoiceDocumentView,
    InvoiceDraftInput,
    InvoiceIssueInput,
    InvoiceList,
)
from gorgona_booking.business.modules import ModuleDisabledError
from gorgona_booking.business.settlement_contracts import (
    ObligationList,
    ObligationView,
    PaymentConfirmInput,
    PaymentCorrectInput,
    PaymentView,
    PaymentVoidInput,
    ProviderAcknowledgeInput,
    ProviderAcknowledgementResult,
    ProviderAttentionList,
    ProviderClearingAccountInput,
    ProviderClearingAccountView,
    ProviderConnectionList,
    ProviderLinkInput,
    ProviderLinkResult,
    ProviderOperationDetail,
    ProviderOperationList,
    ProviderOperationState,
    ProviderPaymentConfirmInput,
    ProviderReleaseInput,
    ProviderReleaseResult,
    SettlementAction,
    SettlementActionInput,
    SettlementCancelInput,
    SettlementList,
    SettlementPrepareInput,
    SettlementReleaseInput,
    SettlementView,
)
from gorgona_booking.db.schema_guard import assert_location_scope_ready
from gorgona_booking.errors import DomainError, NotFoundError
from gorgona_booking.observability import record_provider_application
from gorgona_booking.tenancy.authorization import TenantAccess, authorized_tenant

router = APIRouter(
    prefix="/v1/businesses/{business_id}/financial-documents", tags=["finance-documents"]
)
CommandKey = Annotated[str, Path(min_length=8, max_length=255, pattern=r"^[A-Za-z0-9._:-]+$")]
Limit = Annotated[int, Query(ge=1, le=100)]
Revision = Annotated[int | None, Query(ge=1, le=2147483647)]


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


@router.get("/overview")
async def overview(
    business_id: UUID, request: Request, principal: CurrentPrincipal
) -> FinancialWorkflowStatus:
    async with _access(request, principal, business_id) as access:
        blocked: Literal["not_ready", "module_disabled"] | None = None
        try:
            await service.require_workflow(access.conn, business_id)
        except service.FinancialWorkflowNotReadyError:
            blocked = "not_ready"
        except ModuleDisabledError:
            blocked = "module_disabled"
        return FinancialWorkflowStatus(
            business_id=business_id,
            write_enabled=blocked is None,
            blocked_reason=blocked,
            timezone=await service.business_timezone(access.conn, business_id),
        )


def _document_routes(segment: str, kind: DocumentKind) -> None:
    """List, read, draft and issue routes of one document kind; kinds never mix."""
    collection = f"/books/{{book_id}}/{segment}"
    item = collection + "/{document_id}"

    @router.get(collection, name=f"list_{segment}")
    async def documents(
        business_id: UUID,
        book_id: UUID,
        request: Request,
        principal: CurrentPrincipal,
        after: UUID | None = None,
        limit: Limit = 50,
    ) -> InvoiceList:
        async with _access(request, principal, business_id) as access:
            return await service.list_invoices(
                access.conn, business_id, book_id, after=after, limit=limit, kind=kind
            )

    @router.get(item, name=f"read_{segment}")
    async def document(
        business_id: UUID,
        book_id: UUID,
        document_id: UUID,
        request: Request,
        principal: CurrentPrincipal,
        revision: Revision = None,
    ) -> InvoiceDocumentView:
        async with _access(request, principal, business_id) as access:
            result = await service.load_invoice(
                access.conn, business_id, book_id, document_id, revision=revision, kind=kind
            )
            if result is None:
                raise NotFoundError("Financial document version not found")
            return result

    @router.put(item, name=f"draft_{segment}")
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
                kind=kind,
            )

    @router.post(item + "/issue", name=f"issue_{segment}")
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
            return await service.issue_document(
                access.conn,
                business_id=business_id,
                book_id=book_id,
                document_id=document_id,
                user_id=principal.user_id,
                actor=principal.actor,
                key=idempotency_key,
                body=body,
                kind=kind,
            )


_document_routes("invoices", "invoice")
_document_routes("accruals", "manual_accrual")

_CREDITS = "/books/{book_id}/credits"


@router.get(_CREDITS)
async def credit_list(
    business_id: UUID,
    book_id: UUID,
    request: Request,
    principal: CurrentPrincipal,
    after: UUID | None = None,
    limit: Limit = 50,
) -> CreditList:
    async with _access(request, principal, business_id) as access:
        return await credit_notes.list_credits(
            access.conn, business_id, book_id, after=after, limit=limit
        )


@router.get(_CREDITS + "/{document_id}")
async def credit(
    business_id: UUID,
    book_id: UUID,
    document_id: UUID,
    request: Request,
    principal: CurrentPrincipal,
    revision: Revision = None,
) -> CreditNoteView:
    async with _access(request, principal, business_id) as access:
        result = await credit_notes.load_credit(
            access.conn, business_id, book_id, document_id, revision=revision
        )
        if result is None:
            raise NotFoundError("Credit note version not found")
        return result


@router.put(_CREDITS + "/{document_id}")
async def credit_draft(
    business_id: UUID,
    book_id: UUID,
    document_id: UUID,
    body: CreditDraftInput,
    request: Request,
    principal: CurrentPrincipal,
    idempotency_key: MutationKey,
) -> CreditNoteView:
    async with _access(request, principal, business_id, Permission.FINANCE_MANAGE) as access:
        return await credit_notes.save_draft(
            access.conn,
            business_id=business_id,
            book_id=book_id,
            document_id=document_id,
            user_id=principal.user_id,
            actor=principal.actor,
            key=idempotency_key,
            body=body,
        )


@router.post(_CREDITS + "/{document_id}/issue")
async def credit_issue(
    business_id: UUID,
    book_id: UUID,
    document_id: UUID,
    body: CreditIssueInput,
    request: Request,
    principal: CurrentPrincipal,
    idempotency_key: MutationKey,
) -> CreditNoteView:
    """The unpaid part becomes credit; the paid part a separate refund obligation."""
    async with _access(request, principal, business_id, Permission.FINANCE_MANAGE) as access:
        return await credit_notes.issue_credit(
            access.conn,
            business_id=business_id,
            book_id=book_id,
            document_id=document_id,
            user_id=principal.user_id,
            actor=principal.actor,
            key=idempotency_key,
            body=body,
        )


@router.post("/books/{book_id}/credits/{document_id}/void")
async def credit_void(
    business_id: UUID,
    book_id: UUID,
    document_id: UUID,
    body: CreditVoidInput,
    request: Request,
    principal: CurrentPrincipal,
    idempotency_key: MutationKey,
) -> CreditNoteView:
    """A credit issued in error is mirrored; its untouched refund obligation is cancelled."""
    async with _access(request, principal, business_id, Permission.FINANCE_MANAGE) as access:
        return await credit_notes.void_credit(
            access.conn,
            business_id=business_id,
            book_id=book_id,
            document_id=document_id,
            user_id=principal.user_id,
            actor=principal.actor,
            key=idempotency_key,
            body=body,
        )


_SETTLEMENT = "/books/{book_id}/settlements/{settlement_id}"


@router.get("/books/{book_id}/obligations")
async def obligations(
    business_id: UUID,
    book_id: UUID,
    request: Request,
    principal: CurrentPrincipal,
    after: UUID | None = None,
    limit: Limit = 50,
) -> ObligationList:
    async with _access(request, principal, business_id) as access:
        return await settlements.list_obligations(
            access.conn, business_id, book_id, after=after, limit=limit
        )


@router.get("/books/{book_id}/obligations/{obligation_id}")
async def obligation(
    business_id: UUID,
    book_id: UUID,
    obligation_id: UUID,
    request: Request,
    principal: CurrentPrincipal,
) -> ObligationView:
    async with _access(request, principal, business_id) as access:
        result = await settlements.load_obligation(access.conn, business_id, book_id, obligation_id)
        if result is None:
            raise NotFoundError("Obligation not found")
        return result


@router.get("/books/{book_id}/settlements")
async def settlement_list(
    business_id: UUID,
    book_id: UUID,
    request: Request,
    principal: CurrentPrincipal,
    after: UUID | None = None,
    limit: Limit = 50,
) -> SettlementList:
    async with _access(request, principal, business_id) as access:
        return await settlements.list_settlements(
            access.conn, business_id, book_id, after=after, limit=limit
        )


@router.get(_SETTLEMENT)
async def settlement(
    business_id: UUID,
    book_id: UUID,
    settlement_id: UUID,
    request: Request,
    principal: CurrentPrincipal,
) -> SettlementView:
    async with _access(request, principal, business_id) as access:
        result = await settlements.load_settlement(access.conn, business_id, book_id, settlement_id)
        if result is None:
            raise NotFoundError("Settlement not found")
        return result


@router.put(_SETTLEMENT)
async def settlement_prepare(
    business_id: UUID,
    book_id: UUID,
    settlement_id: UUID,
    body: SettlementPrepareInput,
    request: Request,
    principal: CurrentPrincipal,
    idempotency_key: MutationKey,
) -> SettlementView:
    async with _access(request, principal, business_id, Permission.FINANCE_MANAGE) as access:
        return await settlements.prepare(
            access.conn,
            business_id=business_id,
            book_id=book_id,
            settlement_id=settlement_id,
            user_id=principal.user_id,
            actor=principal.actor,
            key=idempotency_key,
            body=body,
        )


async def _settlement_act(
    request: Request,
    principal: CurrentPrincipal,
    business_id: UUID,
    book_id: UUID,
    settlement_id: UUID,
    key: str,
    action: SettlementAction,
    body: SettlementActionInput,
) -> SettlementView:
    async with _access(request, principal, business_id, Permission.FINANCE_MANAGE) as access:
        return await settlements.act(
            access.conn,
            business_id=business_id,
            book_id=book_id,
            settlement_id=settlement_id,
            user_id=principal.user_id,
            actor=principal.actor,
            key=key,
            action=action,
            body=body,
        )


def _settlement_fact(action: SettlementAction) -> None:
    """Approve, reserve and sent carry only the expected sequence."""

    @router.post(f"{_SETTLEMENT}/{action}", name=f"settlement_{action}")
    async def record(
        business_id: UUID,
        book_id: UUID,
        settlement_id: UUID,
        body: SettlementActionInput,
        request: Request,
        principal: CurrentPrincipal,
        idempotency_key: MutationKey,
    ) -> SettlementView:
        return await _settlement_act(
            request, principal, business_id, book_id, settlement_id, idempotency_key, action, body
        )


_settlement_fact("approve")
_settlement_fact("reserve")
_settlement_fact("sent")


@router.post(f"{_SETTLEMENT}/release")
async def settlement_release(
    business_id: UUID,
    book_id: UUID,
    settlement_id: UUID,
    body: SettlementReleaseInput,
    request: Request,
    principal: CurrentPrincipal,
    idempotency_key: MutationKey,
) -> SettlementView:
    return await _settlement_act(
        request, principal, business_id, book_id, settlement_id, idempotency_key, "release", body
    )


@router.post(f"{_SETTLEMENT}/cancel")
async def settlement_cancel(
    business_id: UUID,
    book_id: UUID,
    settlement_id: UUID,
    body: SettlementCancelInput,
    request: Request,
    principal: CurrentPrincipal,
    idempotency_key: MutationKey,
) -> SettlementView:
    return await _settlement_act(
        request, principal, business_id, book_id, settlement_id, idempotency_key, "cancel", body
    )


@router.post(f"{_SETTLEMENT}/confirmations/{{payment_id}}")
async def settlement_confirm(
    business_id: UUID,
    book_id: UUID,
    settlement_id: UUID,
    payment_id: UUID,
    body: PaymentConfirmInput,
    request: Request,
    principal: CurrentPrincipal,
    idempotency_key: MutationKey,
) -> SettlementView:
    """A human attests an external payment; this program sends no money."""
    async with _access(request, principal, business_id, Permission.FINANCE_MANAGE) as access:
        return await settlements.confirm(
            access.conn,
            business_id=business_id,
            book_id=book_id,
            settlement_id=settlement_id,
            payment_id=payment_id,
            user_id=principal.user_id,
            actor=principal.actor,
            key=idempotency_key,
            body=body,
        )


@router.post(f"{_SETTLEMENT}/confirmations/{{payment_id}}/void")
async def settlement_payment_void(
    business_id: UUID,
    book_id: UUID,
    settlement_id: UUID,
    payment_id: UUID,
    body: PaymentVoidInput,
    request: Request,
    principal: CurrentPrincipal,
    idempotency_key: MutationKey,
) -> SettlementView:
    """A human attests that the confirmation was wrong; its identity stays bound."""
    async with _access(request, principal, business_id, Permission.FINANCE_MANAGE) as access:
        return await settlements.void_payment(
            access.conn,
            business_id=business_id,
            book_id=book_id,
            settlement_id=settlement_id,
            payment_id=payment_id,
            user_id=principal.user_id,
            actor=principal.actor,
            key=idempotency_key,
            body=body,
        )


@router.post(f"{_SETTLEMENT}/confirmations/{{payment_id}}/correct")
async def settlement_payment_correct(
    business_id: UUID,
    book_id: UUID,
    settlement_id: UUID,
    payment_id: UUID,
    body: PaymentCorrectInput,
    request: Request,
    principal: CurrentPrincipal,
    idempotency_key: MutationKey,
) -> SettlementView:
    """Replace the details of an erroneous attestation of the same external fact."""
    async with _access(request, principal, business_id, Permission.FINANCE_MANAGE) as access:
        return await settlements.correct_payment(
            access.conn,
            business_id=business_id,
            book_id=book_id,
            settlement_id=settlement_id,
            payment_id=payment_id,
            user_id=principal.user_id,
            actor=principal.actor,
            key=idempotency_key,
            body=body,
        )


@router.get("/books/{book_id}/payments/{payment_id}")
async def payment(
    business_id: UUID,
    book_id: UUID,
    payment_id: UUID,
    request: Request,
    principal: CurrentPrincipal,
) -> PaymentView:
    async with _access(request, principal, business_id) as access:
        result = await settlements.load_payment(access.conn, business_id, book_id, payment_id)
        if result is None:
            raise NotFoundError("Payment not found")
        return result


@router.get("/books/{book_id}/provider-operations")
async def provider_operations(
    business_id: UUID,
    book_id: UUID,
    request: Request,
    principal: CurrentPrincipal,
    after: UUID | None = None,
    limit: Limit = 50,
    state: ProviderOperationState | None = None,
) -> ProviderOperationList:
    """Observed provider operations of the book and whether they can move money (K3a, K4a)."""
    async with _access(request, principal, business_id) as access:
        return await provider_payments.list_operations(
            access.conn, business_id, book_id, after=after, limit=limit, state=state
        )


@router.get("/books/{book_id}/provider-operations/{operation_id}")
async def provider_operation(
    business_id: UUID,
    book_id: UUID,
    operation_id: UUID,
    request: Request,
    principal: CurrentPrincipal,
) -> ProviderOperationDetail:
    """Every event, decision and delivery of one operation, with the facts that differ (K4b)."""
    async with _access(request, principal, business_id) as access:
        return await provider_review.operation_detail(
            access.conn, business_id, book_id, operation_id
        )


@router.put("/books/{book_id}/provider-operations/{operation_id}/link")
async def provider_link(
    business_id: UUID,
    book_id: UUID,
    operation_id: UUID,
    body: ProviderLinkInput,
    request: Request,
    principal: CurrentPrincipal,
) -> ProviderLinkResult:
    """K3b: link an observed operation to the manual payment that already recorded it."""
    async with _access(request, principal, business_id, Permission.FINANCE_MANAGE) as access:
        return await provider_review.link(
            access.conn,
            business_id=business_id,
            book_id=book_id,
            operation_id=operation_id,
            user_id=principal.user_id,
            body=body,
        )


@router.get("/books/{book_id}/provider-attention")
async def provider_attention(
    business_id: UUID,
    book_id: UUID,
    request: Request,
    principal: CurrentPrincipal,
    after: UUID | None = None,
    limit: Limit = 50,
) -> ProviderAttentionList:
    """Events still waiting for a decision and decisions without an operation (K4b)."""
    async with _access(request, principal, business_id) as access:
        return await provider_review.list_attention(
            access.conn, business_id, book_id, after=after, limit=limit
        )


@router.put("/books/{book_id}/provider-attention/{event_id}/acknowledgement")
async def provider_acknowledgement(
    business_id: UUID,
    book_id: UUID,
    event_id: UUID,
    body: ProviderAcknowledgeInput,
    request: Request,
    principal: CurrentPrincipal,
) -> ProviderAcknowledgementResult:
    """A finance user marks a decision without an operation as handled, with a note."""
    async with _access(request, principal, business_id, Permission.FINANCE_MANAGE) as access:
        return await provider_review.acknowledge(
            access.conn,
            business_id=business_id,
            book_id=book_id,
            event_id=event_id,
            user_id=principal.user_id,
            body=body,
        )


@router.put("/books/{book_id}/provider-attention/{event_id}/release")
async def provider_release(
    business_id: UUID,
    book_id: UUID,
    event_id: UUID,
    body: ProviderReleaseInput,
    request: Request,
    principal: CurrentPrincipal,
) -> ProviderReleaseResult:
    """K6a: a finance user lets the worker try a parked event again, with a note."""
    async with _access(request, principal, business_id, Permission.FINANCE_MANAGE) as access:
        return await provider_review.release(
            access.conn,
            business_id=business_id,
            book_id=book_id,
            event_id=event_id,
            user_id=principal.user_id,
            body=body,
        )


@router.get("/books/{book_id}/provider-connections")
async def provider_connections(
    business_id: UUID,
    book_id: UUID,
    request: Request,
    principal: CurrentPrincipal,
    after: UUID | None = None,
    limit: Limit = 50,
) -> ProviderConnectionList:
    """The book's provider connections and their clearing accounts (K4a)."""
    async with _access(request, principal, business_id) as access:
        return await provider_payments.list_connections(
            access.conn, business_id, book_id, after=after, limit=limit
        )


@router.put("/books/{book_id}/provider-connections/{connection_id}/clearing-account")
async def provider_clearing_account(
    business_id: UUID,
    book_id: UUID,
    connection_id: UUID,
    body: ProviderClearingAccountInput,
    request: Request,
    principal: CurrentPrincipal,
) -> ProviderClearingAccountView:
    """Register, once, the asset account a connection's observed money goes to."""
    async with _access(request, principal, business_id, Permission.FINANCE_MANAGE) as access:
        return await provider_payments.register_clearing_account(
            access.conn,
            business_id=business_id,
            book_id=book_id,
            connection_id=connection_id,
            user_id=principal.user_id,
            body=body,
        )


@router.post(f"{_SETTLEMENT}/provider-confirmations/{{payment_id}}")
async def settlement_provider_confirm(
    business_id: UUID,
    book_id: UUID,
    settlement_id: UUID,
    payment_id: UUID,
    body: ProviderPaymentConfirmInput,
    request: Request,
    principal: CurrentPrincipal,
    idempotency_key: MutationKey,
) -> SettlementView:
    """A finance user applies one observed provider operation; its facts set the money.

    Only an authorized request of a real company is counted (K5a-fix finding 3), so a refused
    caller cannot grow the metric with company IDs of its own choosing.
    """
    async with _access(request, principal, business_id, Permission.FINANCE_MANAGE) as access:
        try:
            result = await settlements.confirm_provider(
                access.conn,
                business_id=business_id,
                book_id=book_id,
                settlement_id=settlement_id,
                payment_id=payment_id,
                user_id=principal.user_id,
                actor=principal.actor,
                key=idempotency_key,
                body=body,
            )
        except DomainError as error:
            record_provider_application(error.code, business_id)
            raise
    record_provider_application("applied", business_id)
    return result


@router.post("/commands/{key}/resolve")
async def resolve(
    business_id: UUID,
    key: CommandKey,
    body: FinancialCommandReference,
    request: Request,
    principal: CurrentPrincipal,
) -> FinancialCommandStatus:
    async with _access(request, principal, business_id, lock=True) as access:
        return await financial_commands.resolve_command(
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
        return await financial_commands.cancel_command(
            access.conn,
            business_id=business_id,
            user_id=principal.user_id,
            actor=principal.actor,
            key=key,
            body=body,
        )
