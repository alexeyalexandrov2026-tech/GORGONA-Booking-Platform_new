"""HTTP routes for ENTERPRISE-01 Slice 1 (0143): corporate SSO providers, employee directory
links, and atomic employee lifecycle deprovisioning.
"""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from uuid import UUID

from fastapi import APIRouter, Request

from gorgona_booking.api.businesses import CurrentPrincipal, MutationKey
from gorgona_booking.api.deps import runtime_pool
from gorgona_booking.api.request_id import get_request_id
from gorgona_booking.auth.permissions import Permission
from gorgona_booking.business import enterprise_sso as es
from gorgona_booking.db.schema_guard import assert_location_scope_ready
from gorgona_booking.tenancy.authorization import TenantAccess, authorized_tenant

router = APIRouter(prefix="/v1/businesses/{business_id}/enterprise", tags=["enterprise"])


@asynccontextmanager
async def _access(
    request: Request,
    principal: CurrentPrincipal,
    business_id: UUID,
    permission: Permission = Permission.ENTERPRISE_READ,
    *,
    exclusive: str | None = None,
) -> AsyncIterator[TenantAccess]:
    async with authorized_tenant(
        runtime_pool(request),
        principal,
        business_id,
        permission,
        request_id=get_request_id(request),
        exclusive=exclusive,
        allow_location_scope=False,
    ) as access:
        await assert_location_scope_ready(access.conn)
        yield access


@router.get("/sso-providers", response_model=es.SsoProviderList)
async def get_sso_providers(
    business_id: UUID,
    request: Request,
    principal: CurrentPrincipal,
) -> es.SsoProviderList:
    async with _access(request, principal, business_id) as access:
        return await es.list_sso_providers(access.conn, business_id)


@router.put("/sso-providers/{provider_id}", response_model=es.SsoProviderView)
async def put_sso_provider(
    business_id: UUID,
    provider_id: UUID,
    body: es.SsoProviderInput,
    request: Request,
    principal: CurrentPrincipal,
    key: MutationKey,
) -> es.SsoProviderView:
    async with _access(request, principal, business_id, Permission.ENTERPRISE_MANAGE) as access:
        return await es.save_sso_provider(
            access.conn,
            business_id,
            provider_id,
            user_id=principal.user_id,
            actor=principal.actor,
            key=key,
            body=body,
        )


@router.get("/directory-links", response_model=es.DirectoryLinkList)
async def get_directory_links(
    business_id: UUID,
    request: Request,
    principal: CurrentPrincipal,
) -> es.DirectoryLinkList:
    async with _access(request, principal, business_id) as access:
        return await es.list_directory_links(access.conn, business_id)


@router.put("/directory-links/{link_id}", response_model=es.DirectoryLinkView)
async def put_directory_link(
    business_id: UUID,
    link_id: UUID,
    body: es.DirectoryLinkInput,
    request: Request,
    principal: CurrentPrincipal,
    key: MutationKey,
) -> es.DirectoryLinkView:
    async with _access(request, principal, business_id, Permission.ENTERPRISE_MANAGE) as access:
        return await es.save_directory_link(
            access.conn,
            business_id,
            link_id,
            user_id=principal.user_id,
            actor=principal.actor,
            key=key,
            body=body,
        )


@router.post(
    "/directory-links/{link_id}/deprovision",
    response_model=es.DeprovisionResultView,
)
async def post_deprovision_link(
    business_id: UUID,
    link_id: UUID,
    body: es.DeprovisionInput,
    request: Request,
    principal: CurrentPrincipal,
    key: MutationKey,
) -> es.DeprovisionResultView:
    async with _access(
        request,
        principal,
        business_id,
        Permission.ENTERPRISE_MANAGE,
        exclusive="members",
    ) as access:
        return await es.deprovision_directory_link(
            access.conn,
            business_id,
            link_id,
            user_id=principal.user_id,
            actor=principal.actor,
            key=key,
            body=body,
        )


@router.get("/lifecycle-events", response_model=es.LifecycleEventList)
async def get_lifecycle_events(
    business_id: UUID,
    request: Request,
    principal: CurrentPrincipal,
) -> es.LifecycleEventList:
    async with _access(request, principal, business_id) as access:
        return await es.list_lifecycle_events(access.conn, business_id)
