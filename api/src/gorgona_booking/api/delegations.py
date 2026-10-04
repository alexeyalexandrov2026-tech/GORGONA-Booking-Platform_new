"""Delegation between independent businesses (ADR-0016).

The owner business manages outgoing grants; the serving business designates its own
employees. Both sides require the owner-only `delegation.manage` permission.
"""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Query, Request

from gorgona_booking.api.businesses import CurrentPrincipal, MutationKey
from gorgona_booking.api.deps import runtime_pool
from gorgona_booking.api.request_id import get_request_id
from gorgona_booking.auth.permissions import Permission
from gorgona_booking.business.delegation_contracts import (
    DelegationGrantInput,
    DelegationGrantList,
    DelegationGrantView,
    DelegationRevokeInput,
    IncomingDelegationList,
    IncomingDelegationView,
)
from gorgona_booking.business.delegations import (
    designate,
    list_grants,
    list_incoming,
    load_grant,
    remove_designation,
    revoke_grant,
    save_grant,
)
from gorgona_booking.errors import NotFoundError
from gorgona_booking.tenancy.authorization import authorized_tenant

router = APIRouter(prefix="/v1/businesses", tags=["delegations"])

PageLimit = Annotated[int, Query(ge=1, le=100)]


@router.get("/{business_id}/delegations")
async def get_delegations(
    business_id: UUID,
    request: Request,
    principal: CurrentPrincipal,
    limit: PageLimit = 50,
    after: UUID | None = None,
) -> DelegationGrantList:
    async with authorized_tenant(
        runtime_pool(request),
        principal,
        business_id,
        Permission.DELEGATION_MANAGE,
        request_id=get_request_id(request),
    ) as access:
        return await list_grants(access.conn, business_id, after=after, limit=limit)


@router.get("/{business_id}/delegations/{grant_id}")
async def get_delegation(
    business_id: UUID,
    grant_id: UUID,
    request: Request,
    principal: CurrentPrincipal,
    revision: Annotated[int | None, Query(ge=1, le=2_147_483_647)] = None,
) -> DelegationGrantView:
    async with authorized_tenant(
        runtime_pool(request),
        principal,
        business_id,
        Permission.DELEGATION_MANAGE,
        request_id=get_request_id(request),
    ) as access:
        result = await load_grant(access.conn, business_id, grant_id, revision=revision)
        if result is None:
            raise NotFoundError("Delegation revision not found")
        return result


@router.put("/{business_id}/delegations/{grant_id}")
async def put_delegation(
    business_id: UUID,
    grant_id: UUID,
    body: DelegationGrantInput,
    request: Request,
    principal: CurrentPrincipal,
    idempotency_key: MutationKey,
) -> DelegationGrantView:
    async with authorized_tenant(
        runtime_pool(request),
        principal,
        business_id,
        Permission.DELEGATION_MANAGE,
        request_id=get_request_id(request),
        exclusive="delegations",
    ) as access:
        return await save_grant(
            access.conn,
            owner_id=business_id,
            grant_id=grant_id,
            user_id=principal.user_id,
            actor=principal.actor,
            key=idempotency_key,
            body=body,
        )


@router.post("/{business_id}/delegations/{grant_id}/revoke")
async def post_delegation_revoke(
    business_id: UUID,
    grant_id: UUID,
    body: DelegationRevokeInput,
    request: Request,
    principal: CurrentPrincipal,
    idempotency_key: MutationKey,
) -> DelegationGrantView:
    async with authorized_tenant(
        runtime_pool(request),
        principal,
        business_id,
        Permission.DELEGATION_MANAGE,
        request_id=get_request_id(request),
        exclusive="delegations",
    ) as access:
        return await revoke_grant(
            access.conn,
            owner_id=business_id,
            grant_id=grant_id,
            user_id=principal.user_id,
            actor=principal.actor,
            key=idempotency_key,
            body=body,
        )


@router.get("/{business_id}/incoming-delegations")
async def get_incoming_delegations(
    business_id: UUID,
    request: Request,
    principal: CurrentPrincipal,
    limit: PageLimit = 50,
    after: UUID | None = None,
) -> IncomingDelegationList:
    async with authorized_tenant(
        runtime_pool(request),
        principal,
        business_id,
        Permission.DELEGATION_MANAGE,
        request_id=get_request_id(request),
    ) as access:
        return await list_incoming(access.conn, business_id, after=after, limit=limit)


@router.put("/{business_id}/incoming-delegations/{grant_id}/delegates/{membership_id}")
async def put_delegate(
    business_id: UUID,
    grant_id: UUID,
    membership_id: UUID,
    request: Request,
    principal: CurrentPrincipal,
    idempotency_key: MutationKey,
) -> IncomingDelegationView:
    async with authorized_tenant(
        runtime_pool(request),
        principal,
        business_id,
        Permission.DELEGATION_MANAGE,
        request_id=get_request_id(request),
        exclusive="delegation-designations",
    ) as access:
        return await designate(
            access.conn,
            serving_id=business_id,
            grant_id=grant_id,
            membership_id=membership_id,
            user_id=principal.user_id,
            actor=principal.actor,
            key=idempotency_key,
        )


@router.delete("/{business_id}/incoming-delegations/{grant_id}/delegates/{membership_id}")
async def delete_delegate(
    business_id: UUID,
    grant_id: UUID,
    membership_id: UUID,
    request: Request,
    principal: CurrentPrincipal,
    idempotency_key: MutationKey,
) -> IncomingDelegationView:
    async with authorized_tenant(
        runtime_pool(request),
        principal,
        business_id,
        Permission.DELEGATION_MANAGE,
        request_id=get_request_id(request),
        exclusive="delegation-designations",
    ) as access:
        return await remove_designation(
            access.conn,
            serving_id=business_id,
            grant_id=grant_id,
            membership_id=membership_id,
            user_id=principal.user_id,
            actor=principal.actor,
            key=idempotency_key,
        )
