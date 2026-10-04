"""Company-wide group drafts, under the existing business authorization boundary."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Query, Request
from pydantic import AwareDatetime

from gorgona_booking.api.businesses import CurrentPrincipal, MutationKey
from gorgona_booking.api.deps import runtime_pool
from gorgona_booking.api.request_id import get_request_id
from gorgona_booking.auth.permissions import Permission
from gorgona_booking.business.company_groups import (
    list_company_groups,
    load_group,
    save_group,
)
from gorgona_booking.business.group_contracts import (
    ConsentInput,
    GroupBookingReport,
    GroupInput,
    GroupList,
    GroupView,
    InvitationInput,
    InvitationList,
    InvitationView,
)
from gorgona_booking.business.group_membership import (
    consent,
    invite,
    list_invitations,
    withdraw_invitation,
)
from gorgona_booking.business.group_reports import booking_report
from gorgona_booking.db.schema_guard import assert_access_boundaries_ready
from gorgona_booking.errors import NotFoundError
from gorgona_booking.tenancy.authorization import authorized_tenant

router = APIRouter(prefix="/v1/businesses", tags=["groups"])


@router.get("/{business_id}/groups")
async def get_groups(
    business_id: UUID,
    request: Request,
    principal: CurrentPrincipal,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    after: Annotated[
        str | None, Query(min_length=1, max_length=64, pattern=r"^[A-Z0-9_-]+$")
    ] = None,
) -> GroupList:
    async with authorized_tenant(
        runtime_pool(request),
        principal,
        business_id,
        Permission.GROUP_MANAGE,
        request_id=get_request_id(request),
    ) as access:
        await assert_access_boundaries_ready(access.conn)
        return await list_company_groups(access.conn, business_id, after=after, limit=limit)


@router.get("/{business_id}/groups/{group_id}")
async def get_group(
    business_id: UUID,
    group_id: UUID,
    request: Request,
    principal: CurrentPrincipal,
    revision: Annotated[int | None, Query(ge=1, le=2_147_483_647)] = None,
) -> GroupView:
    async with authorized_tenant(
        runtime_pool(request),
        principal,
        business_id,
        Permission.GROUP_MANAGE,
        request_id=get_request_id(request),
    ) as access:
        await assert_access_boundaries_ready(access.conn)
        result = await load_group(access.conn, business_id, group_id, revision=revision)
        if result is None:
            raise NotFoundError("Group version not found")
        return result


@router.put("/{business_id}/groups/{group_id}")
async def put_group(
    business_id: UUID,
    group_id: UUID,
    body: GroupInput,
    request: Request,
    principal: CurrentPrincipal,
    idempotency_key: MutationKey,
) -> GroupView:
    async with authorized_tenant(
        runtime_pool(request),
        principal,
        business_id,
        Permission.GROUP_MANAGE,
        request_id=get_request_id(request),
        exclusive="company-groups",
    ) as access:
        await assert_access_boundaries_ready(access.conn)
        return await save_group(
            access.conn,
            business_id=business_id,
            group_id=group_id,
            user_id=principal.user_id,
            actor=access.actor,
            key=idempotency_key,
            body=body,
        )


@router.get("/{business_id}/groups/{group_id}/invitations")
async def get_group_invitations(
    business_id: UUID,
    group_id: UUID,
    request: Request,
    principal: CurrentPrincipal,
    after: UUID | None = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
) -> InvitationList:
    async with authorized_tenant(
        runtime_pool(request),
        principal,
        business_id,
        Permission.GROUP_MANAGE,
        request_id=get_request_id(request),
    ) as access:
        await assert_access_boundaries_ready(access.conn)
        if await load_group(access.conn, business_id, group_id) is None:
            raise NotFoundError("Group not found")
        return await list_invitations(
            access.conn, business_id, group_id=group_id, incoming=False, after=after, limit=limit
        )


@router.put("/{business_id}/groups/{group_id}/invitations/{invitation_id}")
async def put_group_invitation(
    business_id: UUID,
    group_id: UUID,
    invitation_id: UUID,
    body: InvitationInput,
    request: Request,
    principal: CurrentPrincipal,
    idempotency_key: MutationKey,
) -> InvitationView:
    async with authorized_tenant(
        runtime_pool(request),
        principal,
        business_id,
        Permission.GROUP_MANAGE,
        exclusive="company-groups",
        request_id=get_request_id(request),
    ) as access:
        await assert_access_boundaries_ready(access.conn)
        return await invite(
            access.conn,
            business_id=business_id,
            group_id=group_id,
            invitation_id=invitation_id,
            user_id=principal.user_id,
            actor=access.actor,
            key=idempotency_key,
            body=body,
        )


@router.post("/{business_id}/groups/{group_id}/invitations/{invitation_id}/withdraw")
async def post_group_invitation_withdrawal(
    business_id: UUID,
    group_id: UUID,
    invitation_id: UUID,
    body: ConsentInput,
    request: Request,
    principal: CurrentPrincipal,
    idempotency_key: MutationKey,
) -> InvitationView:
    async with authorized_tenant(
        runtime_pool(request),
        principal,
        business_id,
        Permission.GROUP_MANAGE,
        exclusive="company-groups",
        request_id=get_request_id(request),
    ) as access:
        await assert_access_boundaries_ready(access.conn)
        return await withdraw_invitation(
            access.conn,
            business_id=business_id,
            group_id=group_id,
            invitation_id=invitation_id,
            actor=access.actor,
            key=idempotency_key,
            body=body,
        )


@router.get("/{business_id}/group-invitations")
async def get_incoming_group_invitations(
    business_id: UUID,
    request: Request,
    principal: CurrentPrincipal,
    after: UUID | None = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
) -> InvitationList:
    async with authorized_tenant(
        runtime_pool(request),
        principal,
        business_id,
        Permission.GROUP_MANAGE,
        request_id=get_request_id(request),
    ) as access:
        await assert_access_boundaries_ready(access.conn)
        return await list_invitations(
            access.conn, business_id, group_id=None, incoming=True, after=after, limit=limit
        )


@router.put("/{business_id}/group-invitations/{invitation_id}/consent")
async def put_group_consent(
    business_id: UUID,
    invitation_id: UUID,
    body: ConsentInput,
    request: Request,
    principal: CurrentPrincipal,
    idempotency_key: MutationKey,
) -> InvitationView:
    async with authorized_tenant(
        runtime_pool(request),
        principal,
        business_id,
        Permission.GROUP_MANAGE,
        exclusive="company-groups",
        request_id=get_request_id(request),
    ) as access:
        await assert_access_boundaries_ready(access.conn)
        return await consent(
            access.conn,
            business_id=business_id,
            invitation_id=invitation_id,
            user_id=principal.user_id,
            actor=access.actor,
            key=idempotency_key,
            body=body,
        )


@router.get("/{business_id}/groups/{group_id}/booking-report")
async def get_group_booking_report(
    business_id: UUID,
    group_id: UUID,
    from_at: AwareDatetime,
    until_at: AwareDatetime,
    request: Request,
    principal: CurrentPrincipal,
    after: UUID | None = None,
    limit: Annotated[int, Query(ge=1, le=25)] = 25,
) -> GroupBookingReport:
    async with authorized_tenant(
        runtime_pool(request),
        principal,
        business_id,
        Permission.GROUP_MANAGE,
        exclusive="company-groups",
        request_id=get_request_id(request),
    ) as access:
        await assert_access_boundaries_ready(access.conn)
        return await booking_report(
            access.conn,
            principal,
            business_id,
            group_id,
            from_at=from_at,
            until_at=until_at,
            after=after,
            limit=limit,
        )
