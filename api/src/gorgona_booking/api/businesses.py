"""Universal business boundary; business_id and legacy salon_id identify the same tenant."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Header, Request

from gorgona_booking.api.deps import get_principal, runtime_pool
from gorgona_booking.api.request_id import get_request_id
from gorgona_booking.auth.permissions import Permission
from gorgona_booking.auth.principal import Principal
from gorgona_booking.business.catalog import CATALOG, IndustryCatalog
from gorgona_booking.business.contracts import (
    BusinessLocation,
    BusinessProfile,
    BusinessView,
    ProfileInput,
)
from gorgona_booking.business.service import load_profile, save_profile
from gorgona_booking.errors import NotFoundError
from gorgona_booking.tenancy.authorization import authorized_tenant

router = APIRouter(prefix="/v1/businesses", tags=["businesses"])
CurrentPrincipal = Annotated[Principal, Depends(get_principal)]
MutationKey = Annotated[
    str,
    Header(alias="Idempotency-Key", min_length=8, max_length=255, pattern=r"^[A-Za-z0-9._:-]+$"),
]


@router.get("/{business_id}/industry-catalog")
async def industry_catalog(
    business_id: UUID, request: Request, principal: CurrentPrincipal
) -> IndustryCatalog:
    async with authorized_tenant(
        runtime_pool(request),
        principal,
        business_id,
        Permission.BUSINESS_READ,
        request_id=get_request_id(request),
    ):
        return CATALOG


@router.get("/{business_id}")
async def get_business(
    business_id: UUID, request: Request, principal: CurrentPrincipal
) -> BusinessView:
    async with authorized_tenant(
        runtime_pool(request),
        principal,
        business_id,
        Permission.BUSINESS_READ,
        request_id=get_request_id(request),
    ) as access:
        row = await (
            await access.conn.execute(
                "select display_name from gba.tenants where id = %s", (business_id,)
            )
        ).fetchone()
        if row is None:
            raise NotFoundError("Business not found")
        locations = await (
            await access.conn.execute(
                "select id, name, timezone from gba.locations "
                "where tenant_id = %s order by name, id",
                (business_id,),
            )
        ).fetchall()
        return BusinessView(
            business_id=business_id,
            display_name=row[0],
            locations=tuple(BusinessLocation(id=r[0], name=r[1], timezone=r[2]) for r in locations),
            profile=await load_profile(access.conn, business_id),
        )


@router.put("/{business_id}/profile")
async def update_profile(
    business_id: UUID,
    body: ProfileInput,
    request: Request,
    principal: CurrentPrincipal,
    idempotency_key: MutationKey,
) -> BusinessProfile:
    async with authorized_tenant(
        runtime_pool(request),
        principal,
        business_id,
        Permission.BUSINESS_MANAGE,
        request_id=get_request_id(request),
        exclusive="business-profile",
    ) as access:
        return await save_profile(
            access.conn,
            business_id=business_id,
            user_id=principal.user_id,
            actor=principal.actor,
            key=idempotency_key,
            body=body,
        )
