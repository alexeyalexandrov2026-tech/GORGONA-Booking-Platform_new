"""Company groups: organizer invites, each member decides; no data access is granted."""

from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Query, Request

from gorgona_booking.api.businesses import CurrentPrincipal, MutationKey
from gorgona_booking.api.deps import runtime_pool
from gorgona_booking.api.request_id import get_request_id
from gorgona_booking.auth.permissions import Permission
from gorgona_booking.business.group_contracts import (
    BusinessGroupList,
    BusinessGroupView,
    GroupCreate,
    GroupDecision,
    GroupInvite,
)
from gorgona_booking.business.groups import (
    change_membership,
    create_group,
    invite_member,
    list_groups,
    load_group,
)
from gorgona_booking.errors import NotFoundError
from gorgona_booking.tenancy.authorization import authorized_tenant

router = APIRouter(prefix="/v1/businesses", tags=["groups"])


@router.get("/{business_id}/groups")
async def get_groups(
    business_id: UUID,
    request: Request,
    principal: CurrentPrincipal,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    after: UUID | None = None,
) -> BusinessGroupList:
    async with authorized_tenant(
        runtime_pool(request),
        principal,
        business_id,
        Permission.BUSINESS_READ,
        request_id=get_request_id(request),
    ) as access:
        return await list_groups(access.conn, business_id, after=after, limit=limit)


@router.get("/{business_id}/groups/{group_id}")
async def get_group(
    business_id: UUID, group_id: UUID, request: Request, principal: CurrentPrincipal
) -> BusinessGroupView:
    async with authorized_tenant(
        runtime_pool(request),
        principal,
        business_id,
        Permission.BUSINESS_READ,
        request_id=get_request_id(request),
    ) as access:
        result = await load_group(access.conn, business_id, group_id)
        if result is None:
            raise NotFoundError("Group not found")
        return result


@router.put("/{business_id}/groups/{group_id}")
async def put_group(
    business_id: UUID,
    group_id: UUID,
    body: GroupCreate,
    request: Request,
    principal: CurrentPrincipal,
    idempotency_key: MutationKey,
) -> BusinessGroupView:
    async with authorized_tenant(
        runtime_pool(request),
        principal,
        business_id,
        Permission.BUSINESS_MANAGE,
        request_id=get_request_id(request),
        exclusive="business-groups",
    ) as access:
        return await create_group(
            access.conn,
            business_id=business_id,
            group_id=group_id,
            user_id=principal.user_id,
            actor=principal.actor,
            key=idempotency_key,
            body=body,
        )


@router.put("/{business_id}/groups/{group_id}/members/{member_business_id}")
async def put_group_member(
    business_id: UUID,
    group_id: UUID,
    member_business_id: UUID,
    body: GroupInvite,
    request: Request,
    principal: CurrentPrincipal,
    idempotency_key: MutationKey,
) -> BusinessGroupView:
    async with authorized_tenant(
        runtime_pool(request),
        principal,
        business_id,
        Permission.BUSINESS_MANAGE,
        request_id=get_request_id(request),
        exclusive="business-groups",
    ) as access:
        return await invite_member(
            access.conn,
            business_id=business_id,
            group_id=group_id,
            member_business_id=member_business_id,
            user_id=principal.user_id,
            actor=principal.actor,
            key=idempotency_key,
            body=body,
        )


async def _change(
    business_id: UUID,
    group_id: UUID,
    member_business_id: UUID,
    action: Literal["accept", "decline", "leave", "remove"],
    body: GroupDecision,
    request: Request,
    principal: CurrentPrincipal,
    key: str,
) -> BusinessGroupView:
    async with authorized_tenant(
        runtime_pool(request),
        principal,
        business_id,
        Permission.BUSINESS_MANAGE,
        request_id=get_request_id(request),
        exclusive="business-groups",
    ) as access:
        return await change_membership(
            access.conn,
            business_id=business_id,
            group_id=group_id,
            member_business_id=member_business_id,
            action=action,
            user_id=principal.user_id,
            actor=principal.actor,
            key=key,
            body=body,
        )


@router.post("/{business_id}/groups/{group_id}/members/{member_business_id}/remove")
async def remove_group_member(
    business_id: UUID,
    group_id: UUID,
    member_business_id: UUID,
    body: GroupDecision,
    request: Request,
    principal: CurrentPrincipal,
    idempotency_key: MutationKey,
) -> BusinessGroupView:
    return await _change(
        business_id,
        group_id,
        member_business_id,
        "remove",
        body,
        request,
        principal,
        idempotency_key,
    )


@router.post("/{business_id}/groups/{group_id}/{action}")
async def decide_group_membership(
    business_id: UUID,
    group_id: UUID,
    action: Literal["accept", "decline", "leave"],
    body: GroupDecision,
    request: Request,
    principal: CurrentPrincipal,
    idempotency_key: MutationKey,
) -> BusinessGroupView:
    """The member business decides for itself; the path business is the member."""
    return await _change(
        business_id, group_id, business_id, action, body, request, principal, idempotency_key
    )
