"""HTTP routes for tenant brand media uploads backed by Cloudflare R2."""

from __future__ import annotations

import base64
from datetime import datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel, ConfigDict, Field

from gorgona_booking.api.businesses import CurrentPrincipal
from gorgona_booking.api.deps import runtime_pool
from gorgona_booking.api.holds import get_tenant_id
from gorgona_booking.api.request_id import get_request_id
from gorgona_booking.auth.permissions import Permission
from gorgona_booking.db.pool import tenant_transaction
from gorgona_booking.media.service import (
    MediaKind,
    delete_media_asset,
    list_media_assets,
    read_media_asset_bytes,
    upload_media_asset,
)
from gorgona_booking.tenancy.authorization import authorized_tenant

router = APIRouter(tags=["media"])
type HostTenant = Annotated[UUID, Depends(get_tenant_id)]


class MediaUploadRequest(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    kind: MediaKind = "logo"
    filename: str = Field(min_length=1, max_length=180)
    data_base64: str = Field(min_length=16, max_length=7_500_000)


class MediaAssetResponse(BaseModel):
    model_config = ConfigDict(frozen=True)
    id: UUID
    kind: str
    filename: str
    content_type: str
    size_bytes: int
    sha256: str
    storage_backend: str
    public_url: str
    created_at: datetime


def _to_response(row: dict[str, object]) -> MediaAssetResponse:
    aid = UUID(str(row["id"]))
    return MediaAssetResponse(
        id=aid,
        kind=str(row["kind"]),
        filename=str(row["filename"]),
        content_type=str(row["content_type"]),
        size_bytes=int(str(row["size_bytes"])),
        sha256=str(row["sha256"]),
        storage_backend=str(row["storage_backend"]),
        public_url=f"/v1/customer/media/{aid}",
        created_at=row["created_at"],
    )


@router.get("/v1/businesses/{business_id}/media", response_model=list[MediaAssetResponse])
@router.get("/v1/salons/{business_id}/media", response_model=list[MediaAssetResponse])
async def get_business_media(
    business_id: UUID,
    request: Request,
    principal: CurrentPrincipal,
    kind: str | None = None,
) -> list[MediaAssetResponse]:
    async with authorized_tenant(
        runtime_pool(request),
        principal,
        business_id,
        Permission.BUSINESS_READ,
        request_id=get_request_id(request),
    ) as session:
        rows = await list_media_assets(session.conn, tenant_id=business_id, kind=kind)
    return [_to_response(r) for r in rows]


@router.post(
    "/v1/businesses/{business_id}/media",
    response_model=MediaAssetResponse,
    status_code=status.HTTP_201_CREATED,
)
@router.post(
    "/v1/salons/{business_id}/media",
    response_model=MediaAssetResponse,
    status_code=status.HTTP_201_CREATED,
)
async def post_business_media(
    business_id: UUID,
    body: MediaUploadRequest,
    request: Request,
    principal: CurrentPrincipal,
) -> MediaAssetResponse:
    raw_b64 = body.data_base64.strip()
    if "," in raw_b64 and raw_b64.startswith("data:"):
        raw_b64 = raw_b64.split(",", 1)[1]
    try:
        data = base64.b64decode(raw_b64, validate=True)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Invalid base64 image payload",
        ) from exc
    try:
        async with authorized_tenant(
            runtime_pool(request),
            principal,
            business_id,
            Permission.BUSINESS_MANAGE,
            request_id=get_request_id(request),
        ) as session:
            row = await upload_media_asset(
                session.conn,
                tenant_id=business_id,
                kind=body.kind,
                filename=body.filename,
                data=data,
                user_id=principal.user_id,
            )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc
    return _to_response(row)


@router.delete(
    "/v1/businesses/{business_id}/media/{asset_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
@router.delete(
    "/v1/salons/{business_id}/media/{asset_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def remove_business_media(
    business_id: UUID,
    asset_id: UUID,
    request: Request,
    principal: CurrentPrincipal,
) -> Response:
    async with authorized_tenant(
        runtime_pool(request),
        principal,
        business_id,
        Permission.BUSINESS_MANAGE,
        request_id=get_request_id(request),
    ) as session:
        await delete_media_asset(session.conn, tenant_id=business_id, asset_id=asset_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/v1/customer/media", response_model=list[MediaAssetResponse])
async def get_customer_brand_media(
    request: Request,
    tenant_id: HostTenant,
) -> list[MediaAssetResponse]:
    async with tenant_transaction(runtime_pool(request), tenant_id) as conn:
        rows = await list_media_assets(conn, tenant_id=tenant_id)
    return [_to_response(r) for r in rows]


@router.get("/v1/customer/media/{asset_id}")
async def get_customer_media_binary(
    asset_id: UUID,
    request: Request,
    tenant_id: HostTenant,
) -> Response:
    async with tenant_transaction(runtime_pool(request), tenant_id) as conn:
        found = await read_media_asset_bytes(conn, tenant_id=tenant_id, asset_id=asset_id)
    if found is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Media asset not found")
    ctype, payload = found
    return Response(
        content=payload,
        media_type=ctype,
        headers={
            "Cache-Control": "public, max-age=300",
            "X-Content-Type-Options": "nosniff",
        },
    )
