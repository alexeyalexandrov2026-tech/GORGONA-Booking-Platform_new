"""PRO-01 Slice 1: legal matters, projects, conflict checks, and ethical-wall ACL."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Query, Request

from gorgona_booking.api.businesses import CurrentPrincipal, MutationKey
from gorgona_booking.api.deps import runtime_pool
from gorgona_booking.api.request_id import get_request_id
from gorgona_booking.auth.permissions import Permission
from gorgona_booking.business import projects_matters as pm
from gorgona_booking.db.schema_guard import assert_location_scope_ready
from gorgona_booking.tenancy.authorization import TenantAccess, authorized_tenant

router = APIRouter(prefix="/v1/businesses/{business_id}/projects", tags=["projects"])


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


@router.get("/matters")
async def list_matters(
    business_id: UUID,
    request: Request,
    principal: CurrentPrincipal,
    location_id: UUID | None = None,
    kind: pm.MatterKind | None = None,
    status: pm.MatterStatus | None = None,
    after: UUID | None = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
) -> pm.MatterList:
    async with _access(business_id, request, principal, Permission.PROJECTS_READ) as access:
        return await pm.list_matters(
            access.conn,
            business_id,
            location_id=location_id,
            kind=kind,
            status=status,
            after=after,
            limit=limit,
        )


@router.get("/matters/{matter_id}")
async def get_matter(
    business_id: UUID, matter_id: UUID, request: Request, principal: CurrentPrincipal
) -> pm.MatterView:
    async with _access(business_id, request, principal, Permission.PROJECTS_READ) as access:
        return await pm.get_matter(access.conn, business_id, matter_id)


@router.put("/matters/{matter_id}")
async def put_matter(
    business_id: UUID,
    matter_id: UUID,
    body: pm.MatterInput,
    request: Request,
    principal: CurrentPrincipal,
    idempotency_key: MutationKey,
) -> pm.MatterView:
    async with _access(business_id, request, principal, Permission.PROJECTS_MANAGE) as access:
        return await pm.save_matter(
            access.conn,
            business_id,
            matter_id,
            location_scope=access.location_id,
            user_id=principal.user_id,
            actor=principal.actor,
            key=idempotency_key,
            body=body,
        )


@router.get("/matters/{matter_id}/revisions")
async def list_matter_revisions(
    business_id: UUID, matter_id: UUID, request: Request, principal: CurrentPrincipal
) -> pm.MatterRevisionList:
    async with _access(business_id, request, principal, Permission.PROJECTS_READ) as access:
        return await pm.list_matter_revisions(access.conn, business_id, matter_id)


@router.get("/matters/{matter_id}/conflict-checks")
async def list_conflict_checks(
    business_id: UUID, matter_id: UUID, request: Request, principal: CurrentPrincipal
) -> pm.ConflictCheckList:
    async with _access(business_id, request, principal, Permission.PROJECTS_READ) as access:
        return await pm.list_conflict_checks(access.conn, business_id, matter_id)


@router.post("/matters/{matter_id}/conflict-checks")
async def post_conflict_check(
    business_id: UUID,
    matter_id: UUID,
    body: pm.ConflictCheckInput,
    request: Request,
    principal: CurrentPrincipal,
    idempotency_key: MutationKey,
) -> pm.ConflictCheckView:
    async with _access(business_id, request, principal, Permission.PROJECTS_MANAGE) as access:
        return await pm.record_conflict_check(
            access.conn,
            business_id,
            matter_id,
            user_id=principal.user_id,
            actor=principal.actor,
            key=idempotency_key,
            body=body,
        )


@router.get("/matters/{matter_id}/members")
async def list_matter_members(
    business_id: UUID, matter_id: UUID, request: Request, principal: CurrentPrincipal
) -> pm.MatterMemberList:
    async with _access(business_id, request, principal, Permission.PROJECTS_READ) as access:
        return await pm.list_matter_members(access.conn, business_id, matter_id)


@router.post("/matters/{matter_id}/members")
async def post_matter_member(
    business_id: UUID,
    matter_id: UUID,
    body: pm.MatterMemberInput,
    request: Request,
    principal: CurrentPrincipal,
    idempotency_key: MutationKey,
) -> pm.MatterMemberView:
    async with _access(business_id, request, principal, Permission.PROJECTS_MANAGE) as access:
        return await pm.grant_matter_member(
            access.conn,
            business_id,
            matter_id,
            user_id=principal.user_id,
            actor=principal.actor,
            key=idempotency_key,
            body=body,
        )


@router.post("/matters/{matter_id}/members/{member_id}/revoke")
async def post_revoke_matter_member(
    business_id: UUID,
    matter_id: UUID,
    member_id: UUID,
    request: Request,
    principal: CurrentPrincipal,
    idempotency_key: MutationKey,
) -> pm.MatterMemberView:
    async with _access(business_id, request, principal, Permission.PROJECTS_MANAGE) as access:
        return await pm.revoke_matter_member(
            access.conn,
            business_id,
            matter_id,
            member_id,
            user_id=principal.user_id,
            actor=principal.actor,
            key=idempotency_key,
        )
