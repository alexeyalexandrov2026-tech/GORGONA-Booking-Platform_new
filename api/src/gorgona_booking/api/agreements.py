"""Company-wide contracts with counterparties (ADR-0020 E3)."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Path, Query, Request

from gorgona_booking.api.businesses import CurrentPrincipal, MutationKey
from gorgona_booking.api.deps import runtime_pool
from gorgona_booking.api.request_id import get_request_id
from gorgona_booking.auth.permissions import Permission
from gorgona_booking.business import agreements as service
from gorgona_booking.business.agreement_contracts import (
    AgreeInput,
    AgreementDraftInput,
    AgreementHistory,
    AgreementList,
    AgreementView,
    TerminateInput,
)
from gorgona_booking.db.schema_guard import assert_location_scope_ready
from gorgona_booking.errors import NotFoundError
from gorgona_booking.tenancy.authorization import TenantAccess, authorized_tenant

router = APIRouter(prefix="/v1/businesses", tags=["agreements"])
Limit = Annotated[int, Query(ge=1, le=100)]
Revision = Annotated[int | None, Query(ge=1, le=2_147_483_647)]
AgreementId = Annotated[UUID, Path()]


@asynccontextmanager
async def _access(
    request: Request,
    principal: CurrentPrincipal,
    business_id: UUID,
    *,
    write: bool = False,
) -> AsyncIterator[TenantAccess]:
    # Contracts use the counterparty permissions and lock; company-wide only.
    async with authorized_tenant(
        runtime_pool(request),
        principal,
        business_id,
        Permission.COUNTERPARTIES_MANAGE if write else Permission.COUNTERPARTIES_READ,
        request_id=get_request_id(request),
        exclusive="counterparties" if write else None,
    ) as access:
        await assert_location_scope_ready(access.conn)
        yield access


@router.get("/{business_id}/counterparties/{counterparty_id}/agreements")
async def get_agreements(
    business_id: UUID,
    counterparty_id: UUID,
    request: Request,
    principal: CurrentPrincipal,
    after: UUID | None = None,
    limit: Limit = 50,
) -> AgreementList:
    async with _access(request, principal, business_id) as access:
        return await service.list_agreements(
            access.conn, business_id, counterparty_id, after=after, limit=limit
        )


@router.get("/{business_id}/agreements/{agreement_id}")
async def get_agreement(
    business_id: UUID,
    agreement_id: AgreementId,
    request: Request,
    principal: CurrentPrincipal,
    revision: Revision = None,
) -> AgreementView:
    async with _access(request, principal, business_id) as access:
        result = await service.load_agreement(
            access.conn, business_id, agreement_id, revision=revision
        )
        if result is None:
            raise NotFoundError("Contract version not found")
        return result


@router.get("/{business_id}/agreements/{agreement_id}/versions")
async def get_agreement_history(
    business_id: UUID,
    agreement_id: AgreementId,
    request: Request,
    principal: CurrentPrincipal,
    before: Revision = None,
    limit: Limit = 50,
) -> AgreementHistory:
    async with _access(request, principal, business_id) as access:
        return await service.agreement_history(
            access.conn, business_id, agreement_id, before=before, limit=limit
        )


@router.put("/{business_id}/agreements/{agreement_id}")
async def put_agreement(
    business_id: UUID,
    agreement_id: AgreementId,
    body: AgreementDraftInput,
    request: Request,
    principal: CurrentPrincipal,
    idempotency_key: MutationKey,
) -> AgreementView:
    async with _access(request, principal, business_id, write=True) as access:
        return await service.save_draft(
            access.conn,
            business_id=business_id,
            agreement_id=agreement_id,
            user_id=principal.user_id,
            actor=principal.actor,
            key=idempotency_key,
            body=body,
        )


@router.post("/{business_id}/agreements/{agreement_id}/agree")
async def post_agree(
    business_id: UUID,
    agreement_id: AgreementId,
    body: AgreeInput,
    request: Request,
    principal: CurrentPrincipal,
    idempotency_key: MutationKey,
) -> AgreementView:
    async with _access(request, principal, business_id, write=True) as access:
        return await service.agree(
            access.conn,
            business_id=business_id,
            agreement_id=agreement_id,
            user_id=principal.user_id,
            actor=principal.actor,
            key=idempotency_key,
            body=body,
        )


@router.post("/{business_id}/agreements/{agreement_id}/terminate")
async def post_terminate(
    business_id: UUID,
    agreement_id: AgreementId,
    body: TerminateInput,
    request: Request,
    principal: CurrentPrincipal,
    idempotency_key: MutationKey,
) -> AgreementView:
    async with _access(request, principal, business_id, write=True) as access:
        return await service.terminate(
            access.conn,
            business_id=business_id,
            agreement_id=agreement_id,
            user_id=principal.user_id,
            actor=principal.actor,
            key=idempotency_key,
            body=body,
        )
