"""Company-wide H4 declarations; no approval or gateway-action endpoints."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Path, Query, Request

from gorgona_booking.api.businesses import CurrentPrincipal, MutationKey
from gorgona_booking.api.deps import runtime_pool
from gorgona_booking.api.request_id import get_request_id
from gorgona_booking.auth.permissions import Permission
from gorgona_booking.business import provider_admission as service
from gorgona_booking.business.provider_admission_contracts import (
    AdmissionActionInput,
    AdmissionCommandReference,
    AdmissionCommandStatus,
    AdmissionDraftInput,
    AdmissionList,
    AdmissionView,
)
from gorgona_booking.db.provider_admission_guard import assert_admission_ready
from gorgona_booking.db.schema_guard import assert_location_scope_ready
from gorgona_booking.errors import NotFoundError
from gorgona_booking.tenancy.authorization import TenantAccess, authorized_tenant

router = APIRouter(
    prefix="/v1/businesses/{business_id}/provider-admission", tags=["provider-admission"]
)
_COLLECTION = "/books/{book_id}/requests"
_ITEM = _COLLECTION + "/{request_id}"
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
        await assert_admission_ready(access.conn)
        yield access


@router.get(_COLLECTION)
async def requests(
    business_id: UUID,
    book_id: UUID,
    request: Request,
    principal: CurrentPrincipal,
    after: UUID | None = None,
    limit: Limit = 50,
) -> AdmissionList:
    async with _access(request, principal, business_id) as access:
        return await service.list_requests(
            access.conn, business_id, book_id, after=after, limit=limit
        )


@router.get(_ITEM)
async def admission(
    business_id: UUID,
    book_id: UUID,
    request_id: UUID,
    request: Request,
    principal: CurrentPrincipal,
    revision: Revision = None,
) -> AdmissionView:
    async with _access(request, principal, business_id) as access:
        result = await service.load_request(
            access.conn, business_id, book_id, request_id, revision=revision
        )
        if result is None:
            raise NotFoundError("Admission request version not found")
        return result


@router.put(_ITEM)
async def draft(
    business_id: UUID,
    book_id: UUID,
    request_id: UUID,
    body: AdmissionDraftInput,
    request: Request,
    principal: CurrentPrincipal,
    idempotency_key: MutationKey,
) -> AdmissionView:
    async with _access(request, principal, business_id, Permission.FINANCE_MANAGE) as access:
        return await service.save_draft(
            access.conn,
            business_id=business_id,
            book_id=book_id,
            request_id=request_id,
            user_id=principal.user_id,
            actor=principal.actor,
            key=idempotency_key,
            body=body,
        )


def _transition_route(action: Literal["submit", "withdraw"]) -> None:
    @router.post(_ITEM + "/" + action, name="admission_" + action)
    async def transition(
        business_id: UUID,
        book_id: UUID,
        request_id: UUID,
        body: AdmissionActionInput,
        request: Request,
        principal: CurrentPrincipal,
        idempotency_key: MutationKey,
    ) -> AdmissionView:
        async with _access(request, principal, business_id, Permission.FINANCE_MANAGE) as access:
            return await service.transition(
                access.conn,
                business_id=business_id,
                book_id=book_id,
                request_id=request_id,
                user_id=principal.user_id,
                actor=principal.actor,
                key=idempotency_key,
                body=body,
                action=action,
            )


_transition_route("submit")
_transition_route("withdraw")


@router.post("/commands/{key}/resolve")
async def resolve(
    business_id: UUID,
    key: CommandKey,
    body: AdmissionCommandReference,
    request: Request,
    principal: CurrentPrincipal,
) -> AdmissionCommandStatus:
    async with _access(request, principal, business_id, lock=True) as access:
        return await service.resolve_command(
            access.conn, business_id=business_id, actor=principal.actor, key=key, body=body
        )


@router.post("/commands/{key}/cancel")
async def cancel(
    business_id: UUID,
    key: CommandKey,
    body: AdmissionCommandReference,
    request: Request,
    principal: CurrentPrincipal,
) -> AdmissionCommandStatus:
    async with _access(request, principal, business_id, Permission.FINANCE_MANAGE) as access:
        return await service.cancel_command(
            access.conn,
            business_id=business_id,
            user_id=principal.user_id,
            actor=principal.actor,
            key=key,
            body=body,
        )
