"""HTTP routes for AMARKAL v2.17.0 1-Click B2C Storefront Builder & Public Shop (/shop/)."""

from __future__ import annotations

from collections import deque
from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from fastapi import APIRouter, HTTPException, Request, Response, status
from pydantic import BaseModel, ConfigDict, Field

from gorgona_booking.api.businesses import CurrentPrincipal
from gorgona_booking.api.deps import runtime_pool
from gorgona_booking.api.request_id import get_request_id
from gorgona_booking.api.self_service import (
    enforce_sliding_window_rate_limit,
    extract_client_ip,
)
from gorgona_booking.auth.permissions import Permission
from gorgona_booking.business.b2c_storefront import (
    B2CCartQuoteResult,
    B2CItemKind,
    B2COrderStatus,
    B2COrderView,
    B2CPromoCodeView,
    B2CStorefrontConfigView,
    B2CStorefrontItemView,
    PromoDiscountKind,
    create_promo_code,
    create_storefront_item,
    delete_promo_code,
    delete_storefront_item,
    get_storefront_config,
    list_b2c_orders,
    list_promo_codes,
    list_storefront_items,
    quote_b2c_cart,
    record_b2c_order,
    resolve_published_storefront_by_slug,
    sync_services_to_storefront,
    upsert_storefront_config,
)
from gorgona_booking.db.pool import tenant_transaction
from gorgona_booking.payments.stripe_service import (
    StripePaymentError,
    StripeRuntimeConfig,
    create_stripe_checkout_session,
)
from gorgona_booking.tenancy.authorization import authorized_tenant

router = APIRouter(tags=["b2c-storefront"])

_PUBLIC_CHECKOUT_HITS: dict[str, deque[float]] = {}


def _base_url(request: Request) -> str:
    host = request.headers.get("host") or request.url.netloc
    hostname = host.split(":", 1)[0].lower()
    raw_scheme = request.headers.get("x-forwarded-proto") or request.url.scheme or "https"
    scheme = raw_scheme if hostname in ("127.0.0.1", "localhost") else "https"
    return f"{scheme}://{host}"


class StorefrontConfigResponse(BaseModel):
    model_config = ConfigDict(frozen=True)
    configured: bool
    public_slug: str | None = None
    store_name: str | None = None
    tagline: str = ""
    hero_image_url: str | None = None
    accent_hex: str = "#111111"
    support_email: str | None = None
    is_published: bool = False
    show_services: bool = True
    allow_promo_codes: bool = True
    updated_at: datetime | None = None


class UpsertStorefrontConfigRequest(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    public_slug: str = Field(min_length=3, max_length=63)
    store_name: str = Field(min_length=2, max_length=120)
    tagline: str = Field(default="", max_length=240)
    hero_image_url: str | None = Field(default=None, max_length=500)
    accent_hex: str = Field(default="#111111", pattern=r"^#[0-9A-Fa-f]{6}$")
    support_email: str | None = Field(default=None, max_length=160)
    is_published: bool = True
    show_services: bool = True
    allow_promo_codes: bool = True


class StorefrontItemResponse(BaseModel):
    model_config = ConfigDict(frozen=True)
    id: UUID
    sku: str
    title: str
    category: str
    item_kind: B2CItemKind
    description: str
    price_cents: int
    compare_at_cents: int | None = None
    currency: Literal["USD"] = "USD"
    image_url: str | None = None
    stock_qty: int | None = None
    is_active: bool = True
    display_order: int = 0


class CreateStorefrontItemRequest(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    sku: str = Field(min_length=2, max_length=48)
    title: str = Field(min_length=2, max_length=160)
    category: str = Field(default="Featured", min_length=2, max_length=64)
    item_kind: B2CItemKind = "product"
    description: str = Field(default="", max_length=1000)
    price_cents: int = Field(ge=50, le=99_999_999)
    compare_at_cents: int | None = Field(default=None, ge=50, le=99_999_999)
    image_url: str | None = Field(default=None, max_length=500)
    stock_qty: int | None = Field(default=None, ge=0, le=1_000_000)
    display_order: int = Field(default=0, ge=0, le=1000)


class PromoCodeResponse(BaseModel):
    model_config = ConfigDict(frozen=True)
    id: UUID
    code: str
    discount_kind: PromoDiscountKind
    discount_value: int
    min_subtotal_cents: int
    max_redemptions: int | None = None
    redemptions_count: int
    expires_at: datetime | None = None
    is_active: bool
    created_at: datetime


class CreatePromoCodeRequest(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    code: str = Field(min_length=3, max_length=32)
    discount_kind: PromoDiscountKind = "percent"
    discount_value: int = Field(ge=1, le=99_999_999)
    min_subtotal_cents: int = Field(default=0, ge=0, le=99_999_999)
    max_redemptions: int | None = Field(default=None, ge=1, le=1_000_000)
    expires_at: datetime | None = None


class B2COrderResponse(BaseModel):
    model_config = ConfigDict(frozen=True)
    id: UUID
    order_number: str
    customer_name: str
    customer_email: str
    items: list[dict[str, Any]]
    subtotal_cents: int
    discount_cents: int
    total_cents: int
    promo_code: str | None = None
    currency: Literal["USD"] = "USD"
    status: B2COrderStatus
    stripe_session_id: str | None = None
    checkout_url: str | None = None
    created_at: datetime


class PublicShopCatalogResponse(BaseModel):
    model_config = ConfigDict(frozen=True)
    public_slug: str
    store_name: str
    tagline: str
    hero_image_url: str | None = None
    accent_hex: str
    support_email: str | None = None
    allow_promo_codes: bool
    items: list[StorefrontItemResponse]


class CartLineInput(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    item_id: UUID
    quantity: int = Field(ge=1, le=50)


class PublicQuoteCartRequest(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    items: list[CartLineInput] = Field(min_length=1, max_length=25)
    promo_code: str | None = Field(default=None, max_length=32)


class PublicCartLineResponse(BaseModel):
    model_config = ConfigDict(frozen=True)
    item_id: UUID
    sku: str
    title: str
    unit_price_cents: int
    quantity: int
    line_total_cents: int


class PublicQuoteCartResponse(BaseModel):
    model_config = ConfigDict(frozen=True)
    lines: list[PublicCartLineResponse]
    subtotal_cents: int
    discount_cents: int
    total_cents: int
    applied_promo_code: str | None = None
    promo_message: str | None = None


class PublicCheckoutRequest(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    customer_name: str = Field(min_length=2, max_length=160)
    customer_email: str = Field(min_length=5, max_length=160)
    items: list[CartLineInput] = Field(min_length=1, max_length=25)
    promo_code: str | None = Field(default=None, max_length=32)


def _cfg_resp(cfg: B2CStorefrontConfigView | None) -> StorefrontConfigResponse:
    if cfg is None:
        return StorefrontConfigResponse(configured=False)
    return StorefrontConfigResponse(
        configured=True,
        public_slug=cfg.public_slug,
        store_name=cfg.store_name,
        tagline=cfg.tagline,
        hero_image_url=cfg.hero_image_url,
        accent_hex=cfg.accent_hex,
        support_email=cfg.support_email,
        is_published=cfg.is_published,
        show_services=cfg.show_services,
        allow_promo_codes=cfg.allow_promo_codes,
        updated_at=cfg.updated_at,
    )


def _item_resp(it: B2CStorefrontItemView) -> StorefrontItemResponse:
    return StorefrontItemResponse(
        id=it.id,
        sku=it.sku,
        title=it.title,
        category=it.category,
        item_kind=it.item_kind,
        description=it.description,
        price_cents=it.price_cents,
        compare_at_cents=it.compare_at_cents,
        currency=it.currency,
        image_url=it.image_url,
        stock_qty=it.stock_qty,
        is_active=it.is_active,
        display_order=it.display_order,
    )


def _promo_resp(p: B2CPromoCodeView) -> PromoCodeResponse:
    return PromoCodeResponse(
        id=p.id,
        code=p.code,
        discount_kind=p.discount_kind,
        discount_value=p.discount_value,
        min_subtotal_cents=p.min_subtotal_cents,
        max_redemptions=p.max_redemptions,
        redemptions_count=p.redemptions_count,
        expires_at=p.expires_at,
        is_active=p.is_active,
        created_at=p.created_at,
    )


def _order_resp(o: B2COrderView) -> B2COrderResponse:
    return B2COrderResponse(
        id=o.id,
        order_number=o.order_number,
        customer_name=o.customer_name,
        customer_email=o.customer_email,
        items=o.items,
        subtotal_cents=o.subtotal_cents,
        discount_cents=o.discount_cents,
        total_cents=o.total_cents,
        promo_code=o.promo_code,
        currency=o.currency,
        status=o.status,
        stripe_session_id=o.stripe_session_id,
        checkout_url=o.checkout_url,
        created_at=o.created_at,
    )


def _quote_resp(q: B2CCartQuoteResult) -> PublicQuoteCartResponse:
    return PublicQuoteCartResponse(
        lines=[
            PublicCartLineResponse(
                item_id=ln.item_id,
                sku=ln.sku,
                title=ln.title,
                unit_price_cents=ln.unit_price_cents,
                quantity=ln.quantity,
                line_total_cents=ln.line_total_cents,
            )
            for ln in q.lines
        ],
        subtotal_cents=q.subtotal_cents,
        discount_cents=q.discount_cents,
        total_cents=q.total_cents,
        applied_promo_code=q.applied_promo_code,
        promo_message=q.promo_message,
    )


@router.get(
    "/v1/businesses/{business_id}/storefront-builder/config",
    response_model=StorefrontConfigResponse,
)
async def get_builder_config_route(
    business_id: UUID,
    request: Request,
    principal: CurrentPrincipal,
) -> StorefrontConfigResponse:
    async with authorized_tenant(
        runtime_pool(request),
        principal,
        business_id,
        Permission.BUSINESS_READ,
        request_id=get_request_id(request),
    ) as session:
        cfg = await get_storefront_config(session.conn, tenant_id=business_id)
    return _cfg_resp(cfg)


@router.put(
    "/v1/businesses/{business_id}/storefront-builder/config",
    response_model=StorefrontConfigResponse,
)
async def put_builder_config_route(
    business_id: UUID,
    body: UpsertStorefrontConfigRequest,
    request: Request,
    principal: CurrentPrincipal,
) -> StorefrontConfigResponse:
    try:
        async with authorized_tenant(
            runtime_pool(request),
            principal,
            business_id,
            Permission.BUSINESS_MANAGE,
            request_id=get_request_id(request),
        ) as session:
            cfg = await upsert_storefront_config(
                session.conn,
                tenant_id=business_id,
                public_slug=body.public_slug,
                store_name=body.store_name,
                tagline=body.tagline,
                hero_image_url=body.hero_image_url,
                accent_hex=body.accent_hex,
                support_email=body.support_email,
                is_published=body.is_published,
                show_services=body.show_services,
                allow_promo_codes=body.allow_promo_codes,
                user_id=principal.user_id,
            )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc
    return _cfg_resp(cfg)


@router.get(
    "/v1/businesses/{business_id}/storefront-builder/items",
    response_model=list[StorefrontItemResponse],
)
async def get_builder_items_route(
    business_id: UUID,
    request: Request,
    principal: CurrentPrincipal,
) -> list[StorefrontItemResponse]:
    async with authorized_tenant(
        runtime_pool(request),
        principal,
        business_id,
        Permission.BUSINESS_READ,
        request_id=get_request_id(request),
    ) as session:
        rows = await list_storefront_items(session.conn, tenant_id=business_id)
    return [_item_resp(r) for r in rows]


@router.post(
    "/v1/businesses/{business_id}/storefront-builder/items",
    response_model=StorefrontItemResponse,
    status_code=status.HTTP_201_CREATED,
)
async def post_builder_item_route(
    business_id: UUID,
    body: CreateStorefrontItemRequest,
    request: Request,
    principal: CurrentPrincipal,
) -> StorefrontItemResponse:
    try:
        async with authorized_tenant(
            runtime_pool(request),
            principal,
            business_id,
            Permission.BUSINESS_MANAGE,
            request_id=get_request_id(request),
        ) as session:
            item = await create_storefront_item(
                session.conn,
                tenant_id=business_id,
                sku=body.sku,
                title=body.title,
                category=body.category,
                item_kind=body.item_kind,
                description=body.description,
                price_cents=body.price_cents,
                compare_at_cents=body.compare_at_cents,
                image_url=body.image_url,
                stock_qty=body.stock_qty,
                display_order=body.display_order,
            )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc
    return _item_resp(item)


@router.delete(
    "/v1/businesses/{business_id}/storefront-builder/items/{item_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_builder_item_route(
    business_id: UUID,
    item_id: UUID,
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
        await delete_storefront_item(session.conn, tenant_id=business_id, item_id=item_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/v1/businesses/{business_id}/storefront-builder/sync-services")
async def post_sync_services_route(
    business_id: UUID,
    request: Request,
    principal: CurrentPrincipal,
) -> dict[str, int]:
    async with authorized_tenant(
        runtime_pool(request),
        principal,
        business_id,
        Permission.BUSINESS_MANAGE,
        request_id=get_request_id(request),
    ) as session:
        count = await sync_services_to_storefront(session.conn, tenant_id=business_id)
    return {"synced_count": count}


@router.get(
    "/v1/businesses/{business_id}/storefront-builder/promos",
    response_model=list[PromoCodeResponse],
)
async def get_builder_promos_route(
    business_id: UUID,
    request: Request,
    principal: CurrentPrincipal,
) -> list[PromoCodeResponse]:
    async with authorized_tenant(
        runtime_pool(request),
        principal,
        business_id,
        Permission.BUSINESS_READ,
        request_id=get_request_id(request),
    ) as session:
        rows = await list_promo_codes(session.conn, tenant_id=business_id)
    return [_promo_resp(r) for r in rows]


@router.post(
    "/v1/businesses/{business_id}/storefront-builder/promos",
    response_model=PromoCodeResponse,
    status_code=status.HTTP_201_CREATED,
)
async def post_builder_promo_route(
    business_id: UUID,
    body: CreatePromoCodeRequest,
    request: Request,
    principal: CurrentPrincipal,
) -> PromoCodeResponse:
    try:
        async with authorized_tenant(
            runtime_pool(request),
            principal,
            business_id,
            Permission.BUSINESS_MANAGE,
            request_id=get_request_id(request),
        ) as session:
            promo = await create_promo_code(
                session.conn,
                tenant_id=business_id,
                code=body.code,
                discount_kind=body.discount_kind,
                discount_value=body.discount_value,
                min_subtotal_cents=body.min_subtotal_cents,
                max_redemptions=body.max_redemptions,
                expires_at=body.expires_at,
                user_id=principal.user_id,
            )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc
    return _promo_resp(promo)


@router.delete(
    "/v1/businesses/{business_id}/storefront-builder/promos/{promo_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_builder_promo_route(
    business_id: UUID,
    promo_id: UUID,
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
        await delete_promo_code(session.conn, tenant_id=business_id, promo_id=promo_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get(
    "/v1/businesses/{business_id}/storefront-builder/orders",
    response_model=list[B2COrderResponse],
)
async def get_builder_orders_route(
    business_id: UUID,
    request: Request,
    principal: CurrentPrincipal,
) -> list[B2COrderResponse]:
    async with authorized_tenant(
        runtime_pool(request),
        principal,
        business_id,
        Permission.BUSINESS_READ,
        request_id=get_request_id(request),
    ) as session:
        rows = await list_b2c_orders(session.conn, tenant_id=business_id)
    return [_order_resp(r) for r in rows]


@router.get(
    "/v1/public/shop/{slug}",
    response_model=PublicShopCatalogResponse,
)
async def get_public_shop_route(
    slug: str,
    request: Request,
) -> PublicShopCatalogResponse:
    pool = runtime_pool(request)
    async with pool.connection() as conn, conn.transaction():
        cfg = await resolve_published_storefront_by_slug(conn, slug=slug)
    if cfg is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Published storefront not found.",
        )
    async with tenant_transaction(pool, cfg.tenant_id) as tconn:
        items = await list_storefront_items(tconn, tenant_id=cfg.tenant_id, active_only=True)
    return PublicShopCatalogResponse(
        public_slug=cfg.public_slug,
        store_name=cfg.store_name,
        tagline=cfg.tagline,
        hero_image_url=cfg.hero_image_url,
        accent_hex=cfg.accent_hex,
        support_email=cfg.support_email,
        allow_promo_codes=cfg.allow_promo_codes,
        items=[_item_resp(it) for it in items],
    )


@router.post(
    "/v1/public/shop/{slug}/quote-cart",
    response_model=PublicQuoteCartResponse,
)
async def post_public_shop_quote_route(
    slug: str,
    body: PublicQuoteCartRequest,
    request: Request,
) -> PublicQuoteCartResponse:
    pool = runtime_pool(request)
    async with pool.connection() as conn, conn.transaction():
        cfg = await resolve_published_storefront_by_slug(conn, slug=slug)
    if cfg is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Published storefront not found.",
        )
    promo = body.promo_code if cfg.allow_promo_codes else None
    try:
        async with tenant_transaction(pool, cfg.tenant_id) as tconn:
            quoted = await quote_b2c_cart(
                tconn,
                tenant_id=cfg.tenant_id,
                cart_items=[(ln.item_id, ln.quantity) for ln in body.items],
                promo_code=promo,
            )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc
    return _quote_resp(quoted)


@router.post(
    "/v1/public/shop/{slug}/checkout",
    response_model=B2COrderResponse,
    status_code=status.HTTP_201_CREATED,
)
async def post_public_shop_checkout_route(
    slug: str,
    body: PublicCheckoutRequest,
    request: Request,
) -> B2COrderResponse:
    settings = getattr(request.app.state, "settings", None)
    if settings is not None and settings.environment in ("staging", "production"):
        enforce_sliding_window_rate_limit(
            _PUBLIC_CHECKOUT_HITS,
            key=extract_client_ip(request),
            window_seconds=300.0,
            max_requests=20,
            detail="Too many checkout attempts. Please wait a few minutes and try again.",
        )
    pool = runtime_pool(request)
    async with pool.connection() as conn, conn.transaction():
        cfg = await resolve_published_storefront_by_slug(conn, slug=slug)
    if cfg is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Published storefront not found.",
        )

    promo = body.promo_code if cfg.allow_promo_codes else None
    try:
        async with tenant_transaction(pool, cfg.tenant_id) as tconn:
            quoted = await quote_b2c_cart(
                tconn,
                tenant_id=cfg.tenant_id,
                cart_items=[(ln.item_id, ln.quantity) for ln in body.items],
                promo_code=promo,
            )
            stripe_cfg = StripeRuntimeConfig.from_env()
            stripe_session_id: str | None = None
            checkout_url: str | None = None
            if stripe_cfg.configured:
                base = _base_url(request)
                summary_desc = ", ".join(f"{ln.quantity}x {ln.title}" for ln in quoted.lines)[:280]
                rec = await create_stripe_checkout_session(
                    tconn,
                    config=stripe_cfg,
                    tenant_id=cfg.tenant_id,
                    amount_cents=quoted.total_cents,
                    description=f"{cfg.store_name}: {summary_desc}"[:300],
                    reference_kind="order",
                    reference_id=cfg.public_slug,
                    customer_name=body.customer_name,
                    customer_email=body.customer_email,
                    success_url=f"{base}/shop/?store={cfg.public_slug}&checkout=success",
                    cancel_url=f"{base}/shop/?store={cfg.public_slug}&checkout=cancelled",
                    allow_ach=False,
                    connected_account_id=None,
                    created_by_user_id=None,
                )
                stripe_session_id = rec.provider_session_id
                checkout_url = rec.checkout_url
            order = await record_b2c_order(
                tconn,
                tenant_id=cfg.tenant_id,
                customer_name=body.customer_name,
                customer_email=body.customer_email,
                quote=quoted,
                stripe_session_id=stripe_session_id,
                checkout_url=checkout_url,
            )
    except StripePaymentError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc
    return _order_resp(order)
