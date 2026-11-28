"""AMARKAL v2.17.0: 1-Click B2C Storefront Builder, Promo Engine & 0%-Commission Checkout.

Invariants:
- Server NEVER trusts client-supplied item prices: every checkout recalculates totals strictly
  from live PG18 `gba.b2c_storefront_items` + `gba.b2c_promo_codes` in integer USD cents.
- Public storefront lookup resolves via invoker-only RLS setting `gba.b2c_store_slug` on
  `gba.b2c_storefronts` (zero elevated roles), then scopes all item/promo/order queries inside
  `tenant_transaction(pool, tenant_id)`.
- Accent colors enforce WCAG 2.1 AA contrast (>= 4.5:1 against white).
"""

from __future__ import annotations

import re
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Literal
from uuid import UUID

from psycopg import errors as pg_errors
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from gorgona_booking.business.workspace_studio import validate_wcag_accent_hex
from gorgona_booking.db.pool import RuntimeConnection
from gorgona_booking.notifications.service import EMAIL_RE

B2CItemKind = Literal["product", "service", "package", "digital"]
PromoDiscountKind = Literal["percent", "fixed_cents"]
B2COrderStatus = Literal["checkout_open", "paid", "fulfilled", "cancelled", "refunded"]

_SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9-]{2,62}$")
_SKU_RE = re.compile(r"^[A-Za-z0-9_-]{2,48}$")
_PROMO_RE = re.compile(r"^[A-Z0-9_-]{3,32}$")


@dataclass(frozen=True)
class B2CStorefrontConfigView:
    tenant_id: UUID
    public_slug: str
    store_name: str
    tagline: str
    hero_image_url: str | None
    accent_hex: str
    support_email: str | None
    is_published: bool
    show_services: bool
    allow_promo_codes: bool
    updated_at: datetime | None


@dataclass(frozen=True)
class B2CStorefrontItemView:
    id: UUID
    sku: str
    title: str
    category: str
    item_kind: B2CItemKind
    description: str
    price_cents: int
    compare_at_cents: int | None
    currency: Literal["USD"]
    image_url: str | None
    stock_qty: int | None
    is_active: bool
    display_order: int


@dataclass(frozen=True)
class B2CPromoCodeView:
    id: UUID
    code: str
    discount_kind: PromoDiscountKind
    discount_value: int
    min_subtotal_cents: int
    max_redemptions: int | None
    redemptions_count: int
    expires_at: datetime | None
    is_active: bool
    created_at: datetime


@dataclass(frozen=True)
class B2CCartLineResolved:
    item_id: UUID
    sku: str
    title: str
    unit_price_cents: int
    quantity: int
    line_total_cents: int


@dataclass(frozen=True)
class B2CCartQuoteResult:
    lines: list[B2CCartLineResolved]
    subtotal_cents: int
    discount_cents: int
    total_cents: int
    applied_promo_code: str | None
    promo_message: str | None


@dataclass(frozen=True)
class B2COrderView:
    id: UUID
    order_number: str
    customer_name: str
    customer_email: str
    items: list[dict[str, Any]]
    subtotal_cents: int
    discount_cents: int
    total_cents: int
    promo_code: str | None
    currency: Literal["USD"]
    status: B2COrderStatus
    stripe_session_id: str | None
    checkout_url: str | None
    created_at: datetime


def calculate_promo_discount_cents(
    *,
    subtotal_cents: int,
    promo: B2CPromoCodeView | None,
    now_utc: datetime | None = None,
) -> tuple[int, str | None, str | None]:
    """Deterministic integer-cent promo discount evaluator (respects $0.50 minimum charge)."""
    if promo is None:
        return 0, None, None
    now = now_utc or datetime.now(UTC)
    if not promo.is_active:
        raise ValueError(f"Promo code '{promo.code}' is inactive.")
    if promo.expires_at is not None and promo.expires_at <= now:
        raise ValueError(f"Promo code '{promo.code}' has expired.")
    if promo.max_redemptions is not None and promo.redemptions_count >= promo.max_redemptions:
        raise ValueError(f"Promo code '{promo.code}' has reached its redemption limit.")
    if subtotal_cents < promo.min_subtotal_cents:
        min_usd = promo.min_subtotal_cents / 100
        raise ValueError(
            f"Promo code '{promo.code}' requires a minimum order of ${min_usd:,.2f} USD."
        )

    if promo.discount_kind == "percent":
        raw_disc = (subtotal_cents * promo.discount_value) // 100
        label = f"{promo.discount_value}% off applied ({promo.code})"
    else:
        raw_disc = promo.discount_value
        label = f"${promo.discount_value / 100:,.2f} off applied ({promo.code})"

    max_allowed = max(0, subtotal_cents - 50)
    discount = min(raw_disc, max_allowed)
    return discount, promo.code, label


async def get_storefront_config(
    conn: RuntimeConnection, *, tenant_id: UUID
) -> B2CStorefrontConfigView | None:
    async with conn.cursor(row_factory=dict_row) as cur:
        await cur.execute(
            """
            SELECT tenant_id, public_slug, store_name, tagline, hero_image_url,
                   accent_hex, support_email, is_published, show_services,
                   allow_promo_codes, updated_at
            FROM gba.b2c_storefronts
            WHERE tenant_id = %s
            """,
            (tenant_id,),
        )
        r = await cur.fetchone()
    if r is None:
        return None
    return _row_to_storefront(dict(r))


def _row_to_storefront(r: dict[str, Any]) -> B2CStorefrontConfigView:
    return B2CStorefrontConfigView(
        tenant_id=UUID(str(r["tenant_id"])),
        public_slug=str(r["public_slug"]),
        store_name=str(r["store_name"]),
        tagline=str(r["tagline"] or ""),
        hero_image_url=str(r["hero_image_url"]) if r["hero_image_url"] else None,
        accent_hex=str(r["accent_hex"]).upper(),
        support_email=str(r["support_email"]) if r["support_email"] else None,
        is_published=bool(r["is_published"]),
        show_services=bool(r["show_services"]),
        allow_promo_codes=bool(r["allow_promo_codes"]),
        updated_at=r["updated_at"],
    )


async def upsert_storefront_config(
    conn: RuntimeConnection,
    *,
    tenant_id: UUID,
    public_slug: str,
    store_name: str,
    tagline: str,
    hero_image_url: str | None,
    accent_hex: str,
    support_email: str | None,
    is_published: bool,
    show_services: bool,
    allow_promo_codes: bool,
    user_id: UUID | None,
) -> B2CStorefrontConfigView:
    clean_slug = public_slug.strip().lower()
    if not _SLUG_RE.match(clean_slug):
        raise ValueError(
            "Storefront slug must be 3-63 lowercase chars (a-z, 0-9, -) starting with a-z/0-9."
        )
    clean_name = store_name.strip()[:120]
    if len(clean_name) < 2:
        raise ValueError("Store name must be at least 2 characters.")
    clean_accent, _ = validate_wcag_accent_hex(accent_hex)
    clean_hero: str | None = None
    if hero_image_url and hero_image_url.strip():
        h = hero_image_url.strip()
        if not h.startswith("https://") or len(h) > 500:
            raise ValueError("Hero image URL must start with https:// (up to 500 chars).")
        clean_hero = h
    clean_email: str | None = None
    if support_email and support_email.strip():
        em = support_email.strip().lower()
        if not EMAIL_RE.match(em) or len(em) > 160:
            raise ValueError("Support email must be a valid email address.")
        clean_email = em

    try:
        async with conn.cursor(row_factory=dict_row) as cur:
            await cur.execute(
                """
                INSERT INTO gba.b2c_storefronts
                    (tenant_id, public_slug, store_name, tagline, hero_image_url, accent_hex,
                     support_email, is_published, show_services, allow_promo_codes,
                     updated_by_user_id)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (tenant_id) DO UPDATE SET
                    public_slug = EXCLUDED.public_slug,
                    store_name = EXCLUDED.store_name,
                    tagline = EXCLUDED.tagline,
                    hero_image_url = EXCLUDED.hero_image_url,
                    accent_hex = EXCLUDED.accent_hex,
                    support_email = EXCLUDED.support_email,
                    is_published = EXCLUDED.is_published,
                    show_services = EXCLUDED.show_services,
                    allow_promo_codes = EXCLUDED.allow_promo_codes,
                    updated_by_user_id = EXCLUDED.updated_by_user_id,
                    updated_at = now()
                RETURNING tenant_id, public_slug, store_name, tagline, hero_image_url,
                          accent_hex, support_email, is_published, show_services,
                          allow_promo_codes, updated_at
                """,
                (
                    tenant_id,
                    clean_slug,
                    clean_name,
                    tagline.strip()[:240],
                    clean_hero,
                    clean_accent,
                    clean_email,
                    is_published,
                    show_services,
                    allow_promo_codes,
                    user_id,
                ),
            )
            row = await cur.fetchone()
    except pg_errors.UniqueViolation as exc:
        raise ValueError(f"Storefront URL slug '{clean_slug}' is already taken.") from exc
    if row is None:
        raise RuntimeError("Failed to save B2C storefront config.")
    return _row_to_storefront(dict(row))


async def resolve_published_storefront_by_slug(
    conn: RuntimeConnection, *, slug: str
) -> B2CStorefrontConfigView | None:
    clean_slug = slug.strip().lower()
    if not _SLUG_RE.match(clean_slug):
        return None
    await conn.execute(
        "SELECT pg_catalog.set_config('gba.b2c_store_slug', %s, true)",
        (clean_slug,),
    )
    async with conn.cursor(row_factory=dict_row) as cur:
        await cur.execute(
            """
            SELECT tenant_id, public_slug, store_name, tagline, hero_image_url,
                   accent_hex, support_email, is_published, show_services,
                   allow_promo_codes, updated_at
            FROM gba.b2c_storefronts
            WHERE public_slug = %s AND is_published = true
            """,
            (clean_slug,),
        )
        row = await cur.fetchone()
    return _row_to_storefront(dict(row)) if row else None


def _row_to_item(r: dict[str, Any]) -> B2CStorefrontItemView:
    return B2CStorefrontItemView(
        id=UUID(str(r["id"])),
        sku=str(r["sku"]),
        title=str(r["title"]),
        category=str(r["category"]),
        item_kind=r["item_kind"],
        description=str(r["description"] or ""),
        price_cents=int(r["price_cents"]),
        compare_at_cents=int(r["compare_at_cents"]) if r["compare_at_cents"] is not None else None,
        currency="USD",
        image_url=str(r["image_url"]) if r["image_url"] else None,
        stock_qty=int(r["stock_qty"]) if r["stock_qty"] is not None else None,
        is_active=bool(r["is_active"]),
        display_order=int(r["display_order"]),
    )


async def list_storefront_items(
    conn: RuntimeConnection, *, tenant_id: UUID, active_only: bool = False
) -> list[B2CStorefrontItemView]:
    sql = """
        SELECT id, sku, title, category, item_kind, description, price_cents,
               compare_at_cents, currency, image_url, stock_qty, is_active, display_order
        FROM gba.b2c_storefront_items
        WHERE tenant_id = %s
    """
    if active_only:
        sql += " AND is_active = true"
    sql += " ORDER BY display_order ASC, created_at ASC"
    async with conn.cursor(row_factory=dict_row) as cur:
        await cur.execute(sql, (tenant_id,))
        rows = await cur.fetchall()
    return [_row_to_item(dict(r)) for r in rows]


async def create_storefront_item(
    conn: RuntimeConnection,
    *,
    tenant_id: UUID,
    sku: str,
    title: str,
    category: str,
    item_kind: B2CItemKind,
    description: str,
    price_cents: int,
    compare_at_cents: int | None,
    image_url: str | None,
    stock_qty: int | None,
    display_order: int,
) -> B2CStorefrontItemView:
    clean_sku = sku.strip().upper()
    if not _SKU_RE.match(clean_sku):
        raise ValueError("SKU must be 2-48 chars using letters, numbers, _ or -.")
    clean_title = title.strip()[:160]
    if len(clean_title) < 2:
        raise ValueError("Item title must be at least 2 characters.")
    if not (50 <= price_cents <= 99_999_999):
        raise ValueError("Item price must be between $0.50 and $999,999.99 USD.")
    if compare_at_cents is not None and compare_at_cents <= price_cents:
        raise ValueError("Compare-at price must be greater than sale price.")
    clean_img: str | None = None
    if image_url and image_url.strip():
        u = image_url.strip()
        if not u.startswith("https://") or len(u) > 500:
            raise ValueError("Image URL must start with https://.")
        clean_img = u

    try:
        async with conn.cursor(row_factory=dict_row) as cur:
            await cur.execute(
                """
                INSERT INTO gba.b2c_storefront_items
                    (tenant_id, sku, title, category, item_kind, description, price_cents,
                     compare_at_cents, currency, image_url, stock_qty, is_active, display_order)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, 'USD', %s, %s, true, %s)
                RETURNING id, sku, title, category, item_kind, description, price_cents,
                          compare_at_cents, currency, image_url, stock_qty, is_active,
                          display_order
                """,
                (
                    tenant_id,
                    clean_sku,
                    clean_title,
                    (category.strip() or "Featured")[:64],
                    item_kind,
                    description.strip()[:1000],
                    price_cents,
                    compare_at_cents,
                    clean_img,
                    stock_qty,
                    max(0, min(display_order, 1000)),
                ),
            )
            row = await cur.fetchone()
    except pg_errors.UniqueViolation as exc:
        raise ValueError(f"Item SKU '{clean_sku}' already exists in your storefront.") from exc
    if row is None:
        raise RuntimeError("Failed to create B2C storefront item.")
    return _row_to_item(dict(row))


async def delete_storefront_item(
    conn: RuntimeConnection, *, tenant_id: UUID, item_id: UUID
) -> bool:
    cur = await conn.execute(
        "DELETE FROM gba.b2c_storefront_items WHERE tenant_id = %s AND id = %s",
        (tenant_id, item_id),
    )
    return cur.rowcount > 0


async def sync_services_to_storefront(conn: RuntimeConnection, *, tenant_id: UUID) -> int:
    """1-click import of published AMARKAL services into B2C storefront catalog."""
    async with conn.cursor(row_factory=dict_row) as cur:
        await cur.execute(
            """
            SELECT v.id, s.name AS service_name, v.name AS variant_name,
                   v.price_cents, v.currency
            FROM gba.service_variants v
            JOIN gba.services s ON s.tenant_id = v.tenant_id AND s.id = v.service_id
            WHERE v.tenant_id = %s
              AND v.status = 'published'
              AND v.price_cents >= 50
              AND upper(v.currency) = 'USD'
            ORDER BY s.name ASC, v.name ASC
            LIMIT 40
            """,
            (tenant_id,),
        )
        rows = await cur.fetchall()
    imported = 0
    for idx, r in enumerate(rows):
        sku = f"SVC-{str(r['id']).replace('-', '')[:10].upper()}"
        title = f"{r['service_name']} — {r['variant_name']}"[:160]
        async with conn.cursor() as cur:
            res = await cur.execute(
                """
                INSERT INTO gba.b2c_storefront_items
                    (tenant_id, sku, title, category, item_kind, description, price_cents,
                     currency, is_active, display_order)
                VALUES (
                    %s, %s, %s, 'Services', 'service',
                    'Published directly from AMARKAL catalog.',
                    %s, 'USD', true, %s
                )
                ON CONFLICT (tenant_id, sku) DO UPDATE SET
                    title = EXCLUDED.title,
                    price_cents = EXCLUDED.price_cents,
                    is_active = true,
                    updated_at = now()
                """,
                (tenant_id, sku, title, int(r["price_cents"]), idx),
            )
            if res.rowcount > 0:
                imported += 1
    return imported


def _row_to_promo(r: dict[str, Any]) -> B2CPromoCodeView:
    return B2CPromoCodeView(
        id=UUID(str(r["id"])),
        code=str(r["code"]),
        discount_kind=r["discount_kind"],
        discount_value=int(r["discount_value"]),
        min_subtotal_cents=int(r["min_subtotal_cents"]),
        max_redemptions=int(r["max_redemptions"]) if r["max_redemptions"] is not None else None,
        redemptions_count=int(r["redemptions_count"]),
        expires_at=r["expires_at"],
        is_active=bool(r["is_active"]),
        created_at=r["created_at"],
    )


async def list_promo_codes(conn: RuntimeConnection, *, tenant_id: UUID) -> list[B2CPromoCodeView]:
    async with conn.cursor(row_factory=dict_row) as cur:
        await cur.execute(
            """
            SELECT id, code, discount_kind, discount_value, min_subtotal_cents,
                   max_redemptions, redemptions_count, expires_at, is_active, created_at
            FROM gba.b2c_promo_codes
            WHERE tenant_id = %s
            ORDER BY created_at DESC
            """,
            (tenant_id,),
        )
        rows = await cur.fetchall()
    return [_row_to_promo(dict(r)) for r in rows]


async def create_promo_code(
    conn: RuntimeConnection,
    *,
    tenant_id: UUID,
    code: str,
    discount_kind: PromoDiscountKind,
    discount_value: int,
    min_subtotal_cents: int,
    max_redemptions: int | None,
    expires_at: datetime | None,
    user_id: UUID | None,
) -> B2CPromoCodeView:
    clean_code = code.strip().upper()
    if not _PROMO_RE.match(clean_code):
        raise ValueError("Promo code must be 3-32 uppercase chars (A-Z, 0-9, _ or -).")
    if discount_kind == "percent" and not (1 <= discount_value <= 95):
        raise ValueError("Percentage discount must be between 1% and 95%.")
    if discount_kind == "fixed_cents" and not (50 <= discount_value <= 99_999_999):
        raise ValueError("Fixed discount must be between $0.50 and $999,999.99.")
    try:
        async with conn.cursor(row_factory=dict_row) as cur:
            await cur.execute(
                """
                INSERT INTO gba.b2c_promo_codes
                    (tenant_id, code, discount_kind, discount_value, min_subtotal_cents,
                     max_redemptions, expires_at, is_active, created_by_user_id)
                VALUES (%s, %s, %s, %s, %s, %s, %s, true, %s)
                RETURNING id, code, discount_kind, discount_value, min_subtotal_cents,
                          max_redemptions, redemptions_count, expires_at, is_active, created_at
                """,
                (
                    tenant_id,
                    clean_code,
                    discount_kind,
                    discount_value,
                    max(0, min_subtotal_cents),
                    max_redemptions,
                    expires_at,
                    user_id,
                ),
            )
            row = await cur.fetchone()
    except pg_errors.UniqueViolation as exc:
        raise ValueError(f"Promo code '{clean_code}' already exists.") from exc
    if row is None:
        raise RuntimeError("Failed to create promo code.")
    return _row_to_promo(dict(row))


async def delete_promo_code(conn: RuntimeConnection, *, tenant_id: UUID, promo_id: UUID) -> bool:
    cur = await conn.execute(
        "DELETE FROM gba.b2c_promo_codes WHERE tenant_id = %s AND id = %s",
        (tenant_id, promo_id),
    )
    return cur.rowcount > 0


async def quote_b2c_cart(
    conn: RuntimeConnection,
    *,
    tenant_id: UUID,
    cart_items: list[tuple[UUID, int]],
    promo_code: str | None,
) -> B2CCartQuoteResult:
    """Resolve authoritative prices from DB and compute exact USD totals with optional promo."""
    if not cart_items:
        raise ValueError("Shopping cart cannot be empty.")
    items = await list_storefront_items(conn, tenant_id=tenant_id, active_only=True)
    by_id = {it.id: it for it in items}
    resolved: list[B2CCartLineResolved] = []
    subtotal = 0
    for item_id, qty in cart_items:
        if not (1 <= qty <= 50):
            raise ValueError("Quantity per item must be between 1 and 50.")
        item = by_id.get(item_id)
        if item is None:
            raise ValueError("One or more items in your cart are no longer available.")
        if item.stock_qty is not None and qty > item.stock_qty:
            raise ValueError(f"Only {item.stock_qty} left in stock for '{item.title}'.")
        line_total = item.price_cents * qty
        subtotal += line_total
        resolved.append(
            B2CCartLineResolved(
                item_id=item.id,
                sku=item.sku,
                title=item.title,
                unit_price_cents=item.price_cents,
                quantity=qty,
                line_total_cents=line_total,
            )
        )

    promo_obj: B2CPromoCodeView | None = None
    if promo_code and promo_code.strip():
        clean_code = promo_code.strip().upper()
        async with conn.cursor(row_factory=dict_row) as cur:
            await cur.execute(
                """
                SELECT id, code, discount_kind, discount_value, min_subtotal_cents,
                       max_redemptions, redemptions_count, expires_at, is_active, created_at
                FROM gba.b2c_promo_codes
                WHERE tenant_id = %s AND code = %s
                """,
                (tenant_id, clean_code),
            )
            prow = await cur.fetchone()
        if prow is None:
            raise ValueError(f"Promo code '{clean_code}' was not found.")
        promo_obj = _row_to_promo(dict(prow))

    discount, applied_code, promo_msg = calculate_promo_discount_cents(
        subtotal_cents=subtotal, promo=promo_obj
    )
    return B2CCartQuoteResult(
        lines=resolved,
        subtotal_cents=subtotal,
        discount_cents=discount,
        total_cents=subtotal - discount,
        applied_promo_code=applied_code,
        promo_message=promo_msg,
    )


async def record_b2c_order(
    conn: RuntimeConnection,
    *,
    tenant_id: UUID,
    customer_name: str,
    customer_email: str,
    quote: B2CCartQuoteResult,
    stripe_session_id: str | None,
    checkout_url: str | None,
) -> B2COrderView:
    clean_name = customer_name.strip()[:160]
    clean_email = customer_email.strip().lower()[:160]
    if len(clean_name) < 2 or not EMAIL_RE.match(clean_email):
        raise ValueError("Enter your name and a valid email address.")
    order_no = f"SHP-{datetime.now(UTC).strftime('%y%m%d')}-{secrets.token_hex(3).upper()}"
    lines_json = [
        {
            "item_id": str(ln.item_id),
            "sku": ln.sku,
            "title": ln.title,
            "unit_price_cents": ln.unit_price_cents,
            "quantity": ln.quantity,
            "line_total_cents": ln.line_total_cents,
        }
        for ln in quote.lines
    ]
    if quote.applied_promo_code:
        await conn.execute(
            """
            UPDATE gba.b2c_promo_codes
            SET redemptions_count = redemptions_count + 1, updated_at = now()
            WHERE tenant_id = %s AND code = %s
            """,
            (tenant_id, quote.applied_promo_code),
        )
    async with conn.cursor(row_factory=dict_row) as cur:
        await cur.execute(
            """
            INSERT INTO gba.b2c_orders
                (tenant_id, order_number, customer_name, customer_email, items,
                 subtotal_cents, discount_cents, total_cents, promo_code, currency,
                 status, stripe_session_id, checkout_url)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, 'USD', 'checkout_open', %s, %s)
            RETURNING id, order_number, customer_name, customer_email, items,
                      subtotal_cents, discount_cents, total_cents, promo_code, currency,
                      status, stripe_session_id, checkout_url, created_at
            """,
            (
                tenant_id,
                order_no,
                clean_name,
                clean_email,
                Jsonb(lines_json),
                quote.subtotal_cents,
                quote.discount_cents,
                quote.total_cents,
                quote.applied_promo_code,
                stripe_session_id,
                checkout_url,
            ),
        )
        row = await cur.fetchone()
    if row is None:
        raise RuntimeError("Failed to record B2C order.")
    return _row_to_order(dict(row))


def _row_to_order(r: dict[str, Any]) -> B2COrderView:
    return B2COrderView(
        id=UUID(str(r["id"])),
        order_number=str(r["order_number"]),
        customer_name=str(r["customer_name"]),
        customer_email=str(r["customer_email"]),
        items=list(r["items"] or []),
        subtotal_cents=int(r["subtotal_cents"]),
        discount_cents=int(r["discount_cents"]),
        total_cents=int(r["total_cents"]),
        promo_code=str(r["promo_code"]) if r["promo_code"] else None,
        currency="USD",
        status=r["status"],
        stripe_session_id=str(r["stripe_session_id"]) if r["stripe_session_id"] else None,
        checkout_url=str(r["checkout_url"]) if r["checkout_url"] else None,
        created_at=r["created_at"],
    )


async def list_b2c_orders(
    conn: RuntimeConnection, *, tenant_id: UUID, limit: int = 30
) -> list[B2COrderView]:
    async with conn.cursor(row_factory=dict_row) as cur:
        await cur.execute(
            """
            SELECT id, order_number, customer_name, customer_email, items,
                   subtotal_cents, discount_cents, total_cents, promo_code, currency,
                   status, stripe_session_id, checkout_url, created_at
            FROM gba.b2c_orders
            WHERE tenant_id = %s
            ORDER BY created_at DESC
            LIMIT %s
            """,
            (tenant_id, max(1, min(limit, 100))),
        )
        rows = await cur.fetchall()
    return [_row_to_order(dict(r)) for r in rows]
