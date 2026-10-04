"""Configuration publication, module registry and readiness records (ADR-0019).

Reads need `business.read`; commands need `business.manage`, company-wide access and
an Idempotency-Key, and are never delegable. Commands share the per-business
`business-configuration` lock with the database booking trigger.
"""

from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Path, Query, Request

from gorgona_booking.api.businesses import CurrentPrincipal, MutationKey
from gorgona_booking.api.deps import runtime_pool
from gorgona_booking.api.request_id import get_request_id
from gorgona_booking.auth.permissions import Permission
from gorgona_booking.business.configuration_contracts import (
    ConfigurationCommand,
    ConfigurationDraftInput,
    ConfigurationPreview,
    ConfigurationVersionList,
    ConfigurationVersionView,
    ConfigurationView,
)
from gorgona_booking.business.configurations import (
    list_versions,
    load_configuration,
    load_version,
    preview_version,
    publish_version,
    save_draft,
    validate_version,
)
from gorgona_booking.business.modules import MODULE_CATALOG, ModuleCatalog
from gorgona_booking.business.readiness_registry import READINESS_REGISTRY, ReadinessRegistry
from gorgona_booking.errors import NotFoundError
from gorgona_booking.tenancy.authorization import authorized_tenant

router = APIRouter(prefix="/v1/businesses", tags=["configuration"])
_LOCK = "business-configuration"
VersionNumber = Annotated[int, Path(ge=1, le=2_147_483_647)]


@router.get("/{business_id}/module-catalog")
async def module_catalog(
    business_id: UUID, request: Request, principal: CurrentPrincipal
) -> ModuleCatalog:
    async with authorized_tenant(
        runtime_pool(request),
        principal,
        business_id,
        Permission.BUSINESS_READ,
        request_id=get_request_id(request),
    ):
        return MODULE_CATALOG


@router.get("/{business_id}/readiness-registry")
async def readiness_registry(
    business_id: UUID, request: Request, principal: CurrentPrincipal
) -> ReadinessRegistry:
    async with authorized_tenant(
        runtime_pool(request),
        principal,
        business_id,
        Permission.BUSINESS_READ,
        request_id=get_request_id(request),
    ):
        return READINESS_REGISTRY


@router.get("/{business_id}/configuration")
async def get_configuration(
    business_id: UUID, request: Request, principal: CurrentPrincipal
) -> ConfigurationView:
    async with authorized_tenant(
        runtime_pool(request),
        principal,
        business_id,
        Permission.BUSINESS_READ,
        request_id=get_request_id(request),
    ) as access:
        return await load_configuration(access.conn, business_id)


@router.get("/{business_id}/configuration/versions")
async def get_configuration_versions(
    business_id: UUID,
    request: Request,
    principal: CurrentPrincipal,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    before: Annotated[int | None, Query(ge=2, le=2_147_483_647)] = None,
) -> ConfigurationVersionList:
    async with authorized_tenant(
        runtime_pool(request),
        principal,
        business_id,
        Permission.BUSINESS_READ,
        request_id=get_request_id(request),
    ) as access:
        return await list_versions(access.conn, business_id, before=before, limit=limit)


@router.get("/{business_id}/configuration/versions/{version}")
async def get_configuration_version(
    business_id: UUID, version: VersionNumber, request: Request, principal: CurrentPrincipal
) -> ConfigurationVersionView:
    async with authorized_tenant(
        runtime_pool(request),
        principal,
        business_id,
        Permission.BUSINESS_READ,
        request_id=get_request_id(request),
    ) as access:
        result = await load_version(access.conn, business_id, version)
        if result is None:
            raise NotFoundError("Configuration version not found")
        return result


@router.get("/{business_id}/configuration/versions/{version}/preview")
async def get_configuration_preview(
    business_id: UUID, version: VersionNumber, request: Request, principal: CurrentPrincipal
) -> ConfigurationPreview:
    async with authorized_tenant(
        runtime_pool(request),
        principal,
        business_id,
        Permission.BUSINESS_READ,
        request_id=get_request_id(request),
    ) as access:
        return await preview_version(access.conn, business_id, version)


@router.put("/{business_id}/configuration/draft")
async def put_configuration_draft(
    business_id: UUID,
    body: ConfigurationDraftInput,
    request: Request,
    principal: CurrentPrincipal,
    idempotency_key: MutationKey,
) -> ConfigurationVersionView:
    async with authorized_tenant(
        runtime_pool(request),
        principal,
        business_id,
        Permission.BUSINESS_MANAGE,
        request_id=get_request_id(request),
        exclusive=_LOCK,
    ) as access:
        return await save_draft(
            access.conn,
            business_id=business_id,
            user_id=principal.user_id,
            actor=principal.actor,
            key=idempotency_key,
            body=body,
        )


@router.post("/{business_id}/configuration/versions/{version}/{step}")
async def decide_configuration(
    business_id: UUID,
    version: VersionNumber,
    step: Literal["validate", "publish"],
    body: ConfigurationCommand,
    request: Request,
    principal: CurrentPrincipal,
    idempotency_key: MutationKey,
) -> ConfigurationVersionView:
    async with authorized_tenant(
        runtime_pool(request),
        principal,
        business_id,
        Permission.BUSINESS_MANAGE,
        request_id=get_request_id(request),
        exclusive=_LOCK,
    ) as access:
        command = validate_version if step == "validate" else publish_version
        return await command(
            access.conn,
            business_id=business_id,
            version=version,
            user_id=principal.user_id,
            actor=principal.actor,
            key=idempotency_key,
            body=body,
        )
