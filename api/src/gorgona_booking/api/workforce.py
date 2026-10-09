"""Branch-scoped workforce API; permissions never delegate or grant support access."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import timedelta
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Query, Request
from pydantic import AwareDatetime

from gorgona_booking.api.businesses import CurrentPrincipal, MutationKey
from gorgona_booking.api.deps import runtime_pool
from gorgona_booking.api.request_id import get_request_id
from gorgona_booking.auth.permissions import Permission
from gorgona_booking.business import workforce as service
from gorgona_booking.business.workforce_contracts import (
    AssignmentInput,
    ProfileInput,
    ProfileList,
    ProfileView,
    ShiftInput,
    ShiftList,
    ShiftView,
    SkillHistory,
    SkillInput,
    SkillList,
    SkillView,
    StaffSkillInput,
    StaffSkillView,
)
from gorgona_booking.db.schema_guard import assert_location_scope_ready
from gorgona_booking.db.workforce_guard import assert_workforce_ready
from gorgona_booking.errors import DomainError
from gorgona_booking.tenancy.authorization import (
    PermissionDeniedError,
    TenantAccess,
    authorized_tenant,
)

router = APIRouter(prefix="/v1/businesses/{business_id}/workforce", tags=["workforce"])
Revision = Annotated[int | None, Query(ge=1, le=2147483647)]
Limit = Annotated[int, Query(ge=1, le=100)]


@asynccontextmanager
async def _access(
    request: Request,
    principal: CurrentPrincipal,
    business_id: UUID,
    permission: Permission = Permission.WORKFORCE_READ,
) -> AsyncIterator[TenantAccess]:
    async with authorized_tenant(
        runtime_pool(request),
        principal,
        business_id,
        permission,
        allow_location_scope=True,
        request_id=get_request_id(request),
    ) as access:
        await assert_location_scope_ready(access.conn)
        await assert_workforce_ready(access.conn)
        yield access


@router.put("/staff/{profile_id}")
async def put_profile(
    business_id: UUID,
    profile_id: UUID,
    body: ProfileInput,
    request: Request,
    principal: CurrentPrincipal,
    idempotency_key: MutationKey,
) -> ProfileView:
    async with _access(request, principal, business_id, Permission.WORKFORCE_MANAGE) as access:
        access.require_location(body.location_id)
        return await service.save_profile(
            access.conn,
            business_id,
            profile_id,
            principal.user_id,
            principal.actor,
            idempotency_key,
            body,
        )


@router.get("/staff")
async def get_profiles(
    business_id: UUID,
    request: Request,
    principal: CurrentPrincipal,
    after: UUID | None = None,
    limit: Limit = 100,
) -> ProfileList:
    async with _access(request, principal, business_id) as access:
        return await service.list_profiles(access.conn, business_id, after, limit)


@router.get("/skills")
async def get_skills(
    business_id: UUID,
    request: Request,
    principal: CurrentPrincipal,
    after: UUID | None = None,
    limit: Limit = 100,
) -> SkillList:
    async with _access(request, principal, business_id) as access:
        return await service.list_skills(access.conn, business_id, after, limit)


@router.get("/skills/{skill_id}")
async def get_skill(
    business_id: UUID,
    skill_id: UUID,
    request: Request,
    principal: CurrentPrincipal,
    revision: Revision = None,
) -> SkillView:
    async with _access(request, principal, business_id) as access:
        return await service.load_skill(access.conn, business_id, skill_id, revision)


@router.put("/skills/{skill_id}")
async def put_skill(
    business_id: UUID,
    skill_id: UUID,
    body: SkillInput,
    request: Request,
    principal: CurrentPrincipal,
    idempotency_key: MutationKey,
) -> SkillView:
    async with _access(request, principal, business_id, Permission.WORKFORCE_MANAGE) as access:
        if access.location_id is not None:
            raise PermissionDeniedError("Company skills require company-wide access")
        return await service.save_skill(
            access.conn,
            business_id,
            skill_id,
            principal.user_id,
            principal.actor,
            idempotency_key,
            body,
        )


@router.put("/staff/{profile_id}/skills/{skill_id}")
async def put_staff_skill(
    business_id: UUID,
    profile_id: UUID,
    skill_id: UUID,
    body: StaffSkillInput,
    request: Request,
    principal: CurrentPrincipal,
    idempotency_key: MutationKey,
) -> StaffSkillView:
    async with _access(request, principal, business_id, Permission.WORKFORCE_MANAGE) as access:
        return await service.save_staff_skill(
            access.conn,
            business_id,
            profile_id,
            skill_id,
            principal.user_id,
            principal.actor,
            idempotency_key,
            body,
        )


@router.get("/staff/{profile_id}/skills/{skill_id}/history")
async def get_skill_history(
    business_id: UUID,
    profile_id: UUID,
    skill_id: UUID,
    request: Request,
    principal: CurrentPrincipal,
    after_revision: Annotated[int, Query(ge=0)] = 0,
    limit: Limit = 100,
) -> SkillHistory:
    async with _access(request, principal, business_id) as access:
        return await service.skill_history(
            access.conn, business_id, profile_id, skill_id, after_revision, limit
        )


@router.get("/shifts/{shift_id}")
async def get_shift(
    business_id: UUID,
    shift_id: UUID,
    request: Request,
    principal: CurrentPrincipal,
    revision: Revision = None,
) -> ShiftView:
    async with _access(request, principal, business_id) as access:
        return await service.load_shift(access.conn, business_id, shift_id, revision)


@router.put("/shifts/{shift_id}")
async def put_shift(
    business_id: UUID,
    shift_id: UUID,
    body: ShiftInput,
    request: Request,
    principal: CurrentPrincipal,
    idempotency_key: MutationKey,
) -> ShiftView:
    async with _access(request, principal, business_id, Permission.WORKFORCE_MANAGE) as access:
        access.require_location(body.location_id)
        return await service.save_shift(
            access.conn,
            business_id,
            shift_id,
            principal.user_id,
            principal.actor,
            idempotency_key,
            body,
        )


@router.post("/shifts/{shift_id}/assign")
async def post_assign(
    business_id: UUID,
    shift_id: UUID,
    body: AssignmentInput,
    request: Request,
    principal: CurrentPrincipal,
    idempotency_key: MutationKey,
) -> ShiftView:
    async with _access(request, principal, business_id, Permission.WORKFORCE_MANAGE) as access:
        return await service.assign(
            access.conn,
            business_id,
            shift_id,
            principal.user_id,
            principal.actor,
            idempotency_key,
            body,
        )


async def _schedule(
    request: Request,
    principal: CurrentPrincipal,
    business_id: UUID,
    starts: AwareDatetime,
    ends: AwareDatetime,
    after: UUID | None,
    limit: int,
    own: bool,
) -> ShiftList:
    if not timedelta(0) < ends - starts <= timedelta(days=62):
        raise DomainError("Request a schedule window of at most 62 days")
    permission = Permission.WORKFORCE_SELF if own else Permission.WORKFORCE_READ
    async with _access(request, principal, business_id, permission) as access:
        if own:
            # A membership may receive a shift in another branch. Only this read
            # widens branch scope; the SQL always filters the trusted user id.
            await access.conn.execute("select set_config('gba.location_id','',true)")
        return await service.list_shifts(
            access.conn, business_id, starts, ends, after, limit, principal.user_id if own else None
        )


@router.get("/shifts")
async def get_shifts(
    business_id: UUID,
    request: Request,
    principal: CurrentPrincipal,
    starts: AwareDatetime,
    ends: AwareDatetime,
    after: UUID | None = None,
    limit: Limit = 100,
) -> ShiftList:
    return await _schedule(request, principal, business_id, starts, ends, after, limit, False)


@router.get("/my-shifts")
async def get_my_shifts(
    business_id: UUID,
    request: Request,
    principal: CurrentPrincipal,
    starts: AwareDatetime,
    ends: AwareDatetime,
    after: UUID | None = None,
    limit: Limit = 100,
) -> ShiftList:
    return await _schedule(request, principal, business_id, starts, ends, after, limit, True)
