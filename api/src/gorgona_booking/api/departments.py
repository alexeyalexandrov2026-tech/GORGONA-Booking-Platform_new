"""Company-wide department drafts, under the existing business authorization boundary."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Query, Request

from gorgona_booking.api.businesses import CurrentPrincipal, MutationKey
from gorgona_booking.api.deps import runtime_pool
from gorgona_booking.api.request_id import get_request_id
from gorgona_booking.auth.permissions import Permission
from gorgona_booking.business.department_contracts import (
    DepartmentInput,
    DepartmentList,
    DepartmentView,
)
from gorgona_booking.business.departments import (
    list_departments,
    load_department,
    save_department,
)
from gorgona_booking.errors import NotFoundError
from gorgona_booking.tenancy.authorization import authorized_tenant

router = APIRouter(prefix="/v1/businesses", tags=["departments"])


@router.get("/{business_id}/departments")
async def get_departments(
    business_id: UUID,
    request: Request,
    principal: CurrentPrincipal,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    after: Annotated[
        str | None, Query(min_length=1, max_length=64, pattern=r"^[A-Z0-9_-]+$")
    ] = None,
) -> DepartmentList:
    async with authorized_tenant(
        runtime_pool(request),
        principal,
        business_id,
        Permission.BUSINESS_READ,
        request_id=get_request_id(request),
    ) as access:
        return await list_departments(access.conn, business_id, after=after, limit=limit)


@router.get("/{business_id}/departments/{department_id}")
async def get_department(
    business_id: UUID,
    department_id: UUID,
    request: Request,
    principal: CurrentPrincipal,
    revision: Annotated[int | None, Query(ge=1, le=2_147_483_647)] = None,
) -> DepartmentView:
    async with authorized_tenant(
        runtime_pool(request),
        principal,
        business_id,
        Permission.BUSINESS_READ,
        request_id=get_request_id(request),
    ) as access:
        result = await load_department(access.conn, business_id, department_id, revision=revision)
        if result is None:
            raise NotFoundError("Department version not found")
        return result


@router.put("/{business_id}/departments/{department_id}")
async def put_department(
    business_id: UUID,
    department_id: UUID,
    body: DepartmentInput,
    request: Request,
    principal: CurrentPrincipal,
    idempotency_key: MutationKey,
) -> DepartmentView:
    async with authorized_tenant(
        runtime_pool(request),
        principal,
        business_id,
        Permission.BUSINESS_MANAGE,
        request_id=get_request_id(request),
        exclusive="business-structure",
    ) as access:
        return await save_department(
            access.conn,
            business_id=business_id,
            department_id=department_id,
            user_id=principal.user_id,
            actor=principal.actor,
            key=idempotency_key,
            body=body,
        )
