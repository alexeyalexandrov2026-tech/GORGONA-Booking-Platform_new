"""Cross-company delegation grants: the owner issues, the servicing business decides."""

from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Query, Request

from gorgona_booking.api.businesses import CurrentPrincipal, MutationKey
from gorgona_booking.api.deps import runtime_pool
from gorgona_booking.api.request_id import get_request_id
from gorgona_booking.auth.permissions import Permission
from gorgona_booking.business.delegation_contracts import (
    DelegateSelection,
    DelegationDecision,
    DelegationIssue,
    DelegationList,
    DelegationView,
)
from gorgona_booking.business.delegations import (
    change_delegation,
    issue_delegation,
    list_delegations,
    load_delegation,
)
from gorgona_booking.errors import NotFoundError
from gorgona_booking.tenancy.authorization import authorized_tenant

router = APIRouter(prefix="/v1/businesses", tags=["delegations"])


@router.get("/{business_id}/delegations")
async def get_delegations(
    business_id: UUID,
    request: Request,
    principal: CurrentPrincipal,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    after: UUID | None = None,
) -> DelegationList:
    async with authorized_tenant(
        runtime_pool(request),
        principal,
        business_id,
        Permission.MEMBERS_MANAGE,
        request_id=get_request_id(request),
    ) as access:
        return await list_delegations(access.conn, business_id, after=after, limit=limit)


@router.get("/{business_id}/delegations/{grant_id}")
async def get_delegation(
    business_id: UUID, grant_id: UUID, request: Request, principal: CurrentPrincipal
) -> DelegationView:
    async with authorized_tenant(
        runtime_pool(request),
        principal,
        business_id,
        Permission.MEMBERS_MANAGE,
        request_id=get_request_id(request),
    ) as access:
        result = await load_delegation(access.conn, business_id, grant_id)
        if result is None:
            raise NotFoundError("Delegation not found")
        return result


@router.put("/{business_id}/delegations/{grant_id}")
async def put_delegation(
    business_id: UUID,
    grant_id: UUID,
    body: DelegationIssue,
    request: Request,
    principal: CurrentPrincipal,
    idempotency_key: MutationKey,
) -> DelegationView:
    """Only an owner may offer another business access to this business's work."""
    async with authorized_tenant(
        runtime_pool(request),
        principal,
        business_id,
        Permission.MEMBERS_MANAGE_ADMINS,
        request_id=get_request_id(request),
        exclusive="delegations",
    ) as access:
        return await issue_delegation(
            access.conn,
            business_id=business_id,
            grant_id=grant_id,
            user_id=principal.user_id,
            actor=principal.actor,
            key=idempotency_key,
            body=body,
        )


async def _change(
    business_id: UUID,
    grant_id: UUID,
    action: Literal["accept", "decline", "revoke", "delegates"],
    body: DelegationDecision,
    request: Request,
    principal: CurrentPrincipal,
    key: str,
) -> DelegationView:
    async with authorized_tenant(
        runtime_pool(request),
        principal,
        business_id,
        Permission.MEMBERS_MANAGE,
        request_id=get_request_id(request),
        exclusive="delegations",
    ) as access:
        return await change_delegation(
            access.conn,
            business_id=business_id,
            grant_id=grant_id,
            action=action,
            user_id=principal.user_id,
            actor=principal.actor,
            key=key,
            body=body,
        )


@router.post("/{business_id}/delegations/{grant_id}/accept")
async def accept_delegation(
    business_id: UUID,
    grant_id: UUID,
    body: DelegateSelection,
    request: Request,
    principal: CurrentPrincipal,
    idempotency_key: MutationKey,
) -> DelegationView:
    return await _change(business_id, grant_id, "accept", body, request, principal, idempotency_key)


@router.post("/{business_id}/delegations/{grant_id}/decline")
async def decline_delegation(
    business_id: UUID,
    grant_id: UUID,
    body: DelegationDecision,
    request: Request,
    principal: CurrentPrincipal,
    idempotency_key: MutationKey,
) -> DelegationView:
    return await _change(
        business_id, grant_id, "decline", body, request, principal, idempotency_key
    )


@router.post("/{business_id}/delegations/{grant_id}/revoke")
async def revoke_delegation(
    business_id: UUID,
    grant_id: UUID,
    body: DelegationDecision,
    request: Request,
    principal: CurrentPrincipal,
    idempotency_key: MutationKey,
) -> DelegationView:
    return await _change(business_id, grant_id, "revoke", body, request, principal, idempotency_key)


@router.put("/{business_id}/delegations/{grant_id}/delegates")
async def put_delegates(
    business_id: UUID,
    grant_id: UUID,
    body: DelegateSelection,
    request: Request,
    principal: CurrentPrincipal,
    idempotency_key: MutationKey,
) -> DelegationView:
    return await _change(
        business_id, grant_id, "delegates", body, request, principal, idempotency_key
    )
