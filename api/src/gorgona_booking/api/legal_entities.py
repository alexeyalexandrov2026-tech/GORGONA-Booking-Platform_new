"""Company-wide legal-entity drafts, under the existing business authorization boundary."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Query, Request

from gorgona_booking.api.businesses import CurrentPrincipal, MutationKey
from gorgona_booking.api.deps import runtime_pool
from gorgona_booking.api.request_id import get_request_id
from gorgona_booking.auth.permissions import Permission
from gorgona_booking.business.legal_entities import (
    list_legal_entities,
    load_legal_entity,
    save_legal_entity,
)
from gorgona_booking.business.legal_entity_contracts import (
    LegalEntityInput,
    LegalEntityList,
    LegalEntityView,
)
from gorgona_booking.errors import NotFoundError
from gorgona_booking.tenancy.authorization import authorized_tenant

router = APIRouter(prefix="/v1/businesses", tags=["legal-entities"])


@router.get("/{business_id}/legal-entities")
async def get_legal_entities(
    business_id: UUID,
    request: Request,
    principal: CurrentPrincipal,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    after: Annotated[
        str | None, Query(min_length=1, max_length=64, pattern=r"^[A-Z0-9_-]+$")
    ] = None,
) -> LegalEntityList:
    async with authorized_tenant(
        runtime_pool(request),
        principal,
        business_id,
        Permission.BUSINESS_READ,
        request_id=get_request_id(request),
    ) as access:
        return await list_legal_entities(access.conn, business_id, after=after, limit=limit)


@router.get("/{business_id}/legal-entities/{entity_id}")
async def get_legal_entity(
    business_id: UUID,
    entity_id: UUID,
    request: Request,
    principal: CurrentPrincipal,
    revision: Annotated[int | None, Query(ge=1, le=2_147_483_647)] = None,
) -> LegalEntityView:
    async with authorized_tenant(
        runtime_pool(request),
        principal,
        business_id,
        Permission.BUSINESS_READ,
        request_id=get_request_id(request),
    ) as access:
        result = await load_legal_entity(access.conn, business_id, entity_id, revision=revision)
        if result is None:
            raise NotFoundError("Legal entity version not found")
        return result


@router.put("/{business_id}/legal-entities/{entity_id}")
async def put_legal_entity(
    business_id: UUID,
    entity_id: UUID,
    body: LegalEntityInput,
    request: Request,
    principal: CurrentPrincipal,
    idempotency_key: MutationKey,
) -> LegalEntityView:
    async with authorized_tenant(
        runtime_pool(request),
        principal,
        business_id,
        Permission.BUSINESS_MANAGE,
        request_id=get_request_id(request),
        exclusive="business-structure",
    ) as access:
        return await save_legal_entity(
            access.conn,
            business_id=business_id,
            entity_id=entity_id,
            user_id=principal.user_id,
            actor=principal.actor,
            key=idempotency_key,
            body=body,
        )
