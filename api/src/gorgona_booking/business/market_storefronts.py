"""MARKET-01 Slice 1 (ADR-0040): Business storefronts, explicit published_fields allow-list,
strict public catalog projection (never leaking internal costs/notes/unselected fields),
moderation lifecycle, and client-operated marketplaces with zero GORGONA commission.
"""

from typing import Any, Literal
from uuid import UUID

from psycopg import errors
from pydantic import AwareDatetime, Field, field_validator

from gorgona_booking.booking.idempotency import IdempotencyScope
from gorgona_booking.business import commands, modules
from gorgona_booking.business.contracts import Strict, Versioned
from gorgona_booking.business.ledger_contracts import CURRENCY_PATTERN
from gorgona_booking.business.module_gate import module_writes, require_module
from gorgona_booking.business.readiness_registry import at_least
from gorgona_booking.db.pool import RuntimeConnection
from gorgona_booking.errors import ConflictError, InvalidReferenceError, NotFoundError

STOREFRONTS_MODULE = "storefronts"

PublicField = Literal[
    "title",
    "description",
    "price",
    "currency",
    "category",
    "availability",
    "location_city",
    "brand",
    "sku",
]
ALL_PUBLIC_FIELDS: frozenset[str] = frozenset(
    {
        "title",
        "description",
        "price",
        "currency",
        "category",
        "availability",
        "location_city",
        "brand",
        "sku",
    }
)
ModerationStatus = Literal["draft", "pending_review", "published", "suspended", "archived"]
OperatorScope = Literal["publish", "orders_read", "reports_read"]
ConnectionStatus = Literal["pending", "active", "suspended", "revoked"]


class MarketNotReadyError(ConflictError):
    code = "MODULE_NOT_READY"


class MarketRevisionConflictError(ConflictError):
    code = "MARKET_REVISION_CONFLICT"


class MarketStateError(ConflictError):
    code = "MARKET_STATE_INVALID"


def _check_ready() -> None:
    mod = modules.MODULES_BY_ID[STOREFRONTS_MODULE]
    if not mod.enableable or not at_least(mod.readiness, modules.MINIMUM_READINESS):
        raise MarketNotReadyError(
            "Storefronts module is not enabled for production writes",
            module_id=STOREFRONTS_MODULE,
        )


def _clean_slug(value: str) -> str:
    clean = value.strip().lower()
    if len(clean) < 2 or len(clean) > 64:
        raise ValueError("Slug must be 2..64 characters")
    if not clean[0].isalnum() or not all(c.isalnum() or c == "-" for c in clean):
        raise ValueError("Slug must use lowercase alphanumeric characters and hyphens")
    return clean


def _clean_sku(value: str) -> str:
    clean = value.strip().upper()
    if not clean or len(clean) > 64:
        raise ValueError("SKU must be 1..64 characters")
    if not clean[0].isalnum() or not all(c.isalnum() or c in "._:-" for c in clean):
        raise ValueError("SKU must use uppercase alphanumeric characters and . _ : -")
    return clean


def _clean_line(value: str, max_len: int) -> str:
    clean = value.strip()
    if not clean or len(clean) > max_len or "\n" in clean or "\r" in clean:
        raise ValueError(f"Expected non-empty single-line text up to {max_len} chars")
    return clean


class StorefrontInput(Versioned):
    expected_revision: int = Field(ge=0, le=1_000_000)
    location_id: UUID
    legal_entity_id: UUID
    slug: str
    display_name: str
    description: str | None = None
    location_city: str | None = None
    currency: str = Field(pattern=CURRENCY_PATTERN)
    published_fields: list[PublicField] = Field(min_length=1, max_length=9)
    is_published: bool = False

    @field_validator("slug")
    @classmethod
    def valid_slug(cls, value: str) -> str:
        return _clean_slug(value)

    @field_validator("display_name")
    @classmethod
    def valid_name(cls, value: str) -> str:
        return _clean_line(value, 200)

    @field_validator("description")
    @classmethod
    def valid_desc(cls, value: str | None) -> str | None:
        return None if value is None else _clean_line(value, 1000)

    @field_validator("location_city")
    @classmethod
    def valid_city(cls, value: str | None) -> str | None:
        return None if value is None else _clean_line(value, 120)

    @field_validator("published_fields")
    @classmethod
    def unique_fields(cls, value: list[PublicField]) -> list[PublicField]:
        deduped = list(dict.fromkeys(value))
        if not deduped:
            raise ValueError("At least one public field must be selected")
        return deduped


class StorefrontView(Strict):
    schema_version: Literal[1] = 1
    storefront_id: UUID
    location_id: UUID
    legal_entity_id: UUID
    slug: str
    display_name: str
    description: str | None
    location_city: str | None
    currency: str
    published_fields: list[PublicField]
    is_published: bool
    revision: int
    recorded_by: UUID
    recorded_at: AwareDatetime


class StorefrontList(Strict):
    schema_version: Literal[1] = 1
    items: list[StorefrontView]


class ListingInput(Versioned):
    expected_revision: int = Field(ge=0, le=1_000_000)
    location_id: UUID
    storefront_id: UUID
    sku: str
    title: str
    description: str | None = None
    category: str
    brand: str | None = None
    currency: str = Field(pattern=CURRENCY_PATTERN)
    price_minor: int = Field(ge=0, le=999_999_999_999_999)
    available_quantity: int = Field(default=0, ge=0, le=999_999_999_999)
    internal_cost_minor: int = Field(default=0, ge=0, le=999_999_999_999_999)
    internal_notes: str | None = None
    published_fields: list[PublicField] = Field(min_length=1, max_length=9)
    moderation_status: ModerationStatus = "draft"

    @field_validator("sku")
    @classmethod
    def valid_sku(cls, value: str) -> str:
        return _clean_sku(value)

    @field_validator("title")
    @classmethod
    def valid_title(cls, value: str) -> str:
        return _clean_line(value, 200)

    @field_validator("category")
    @classmethod
    def valid_cat(cls, value: str) -> str:
        return _clean_line(value, 80)

    @field_validator("description", "internal_notes")
    @classmethod
    def valid_opt_long(cls, value: str | None) -> str | None:
        return None if value is None else _clean_line(value, 1000)

    @field_validator("brand")
    @classmethod
    def valid_brand(cls, value: str | None) -> str | None:
        return None if value is None else _clean_line(value, 120)

    @field_validator("published_fields")
    @classmethod
    def unique_fields(cls, value: list[PublicField]) -> list[PublicField]:
        deduped = list(dict.fromkeys(value))
        if not deduped:
            raise ValueError("At least one public field must be selected")
        return deduped


class ListingView(Strict):
    schema_version: Literal[1] = 1
    listing_id: UUID
    location_id: UUID
    storefront_id: UUID
    legal_entity_id: UUID
    sku: str
    title: str
    description: str | None
    category: str
    brand: str | None
    currency: str
    price_minor: int
    available_quantity: int
    internal_cost_minor: int
    internal_notes: str | None
    published_fields: list[PublicField]
    moderation_status: ModerationStatus
    revision: int
    recorded_by: UUID
    recorded_at: AwareDatetime


class ListingList(Strict):
    schema_version: Literal[1] = 1
    items: list[ListingView]


class PublicListingProjection(Strict):
    """Strict public storefront projection: emits ONLY the intersection of storefront and
    listing `published_fields`. Internal cost, internal notes, and unselected fields are
    explicitly excluded and never populated.
    """

    schema_version: Literal[1] = 1
    listing_id: UUID
    storefront_slug: str
    seller_display_name: str
    published_fields: list[PublicField]
    fields: dict[str, str | int | bool | None]


class PublicStorefrontCatalog(Strict):
    schema_version: Literal[1] = 1
    storefront_slug: str
    display_name: str
    published_fields: list[PublicField]
    items: list[PublicListingProjection]


class MarketplaceInput(Versioned):
    expected_revision: int = Field(ge=0, le=1_000_000)
    location_id: UUID
    slug: str
    title: str
    description: str | None = None
    operator_fee_bps: int = Field(default=0, ge=0, le=5000)
    is_active: bool = True

    @field_validator("slug")
    @classmethod
    def valid_slug(cls, value: str) -> str:
        return _clean_slug(value)

    @field_validator("title")
    @classmethod
    def valid_title(cls, value: str) -> str:
        return _clean_line(value, 200)

    @field_validator("description")
    @classmethod
    def valid_desc(cls, value: str | None) -> str | None:
        return None if value is None else _clean_line(value, 1000)


class MarketplaceView(Strict):
    schema_version: Literal[1] = 1
    marketplace_id: UUID
    location_id: UUID
    slug: str
    title: str
    description: str | None
    gorgona_commission_bps: Literal[0] = 0
    operator_fee_bps: int
    is_active: bool
    revision: int
    recorded_by: UUID
    recorded_at: AwareDatetime


class MarketplaceList(Strict):
    schema_version: Literal[1] = 1
    items: list[MarketplaceView]


class SellerConnectionInput(Versioned):
    expected_revision: int = Field(ge=0, le=1_000_000)
    location_id: UUID
    seller_counterparty_id: UUID
    seller_storefront_slug: str
    granted_scopes: list[OperatorScope] = Field(min_length=1, max_length=3)
    status: ConnectionStatus = "active"

    @field_validator("seller_storefront_slug")
    @classmethod
    def valid_slug(cls, value: str) -> str:
        return _clean_slug(value)

    @field_validator("granted_scopes")
    @classmethod
    def unique_scopes(cls, value: list[OperatorScope]) -> list[OperatorScope]:
        return list(dict.fromkeys(value))


class SellerConnectionView(Strict):
    schema_version: Literal[1] = 1
    connection_id: UUID
    location_id: UUID
    marketplace_id: UUID
    seller_counterparty_id: UUID
    seller_storefront_slug: str
    granted_scopes: list[OperatorScope]
    status: ConnectionStatus
    revoked_at: AwareDatetime | None
    revision: int
    recorded_by: UUID
    recorded_at: AwareDatetime


class SellerConnectionList(Strict):
    schema_version: Literal[1] = 1
    items: list[SellerConnectionView]


# ---------------------------------------------------------------------------
# Row helpers & Storefronts
# ---------------------------------------------------------------------------


def _storefront_view(r: tuple[Any, ...]) -> StorefrontView:
    return StorefrontView(
        storefront_id=r[0],
        location_id=r[1],
        legal_entity_id=r[2],
        slug=str(r[3]),
        display_name=str(r[4]),
        description=r[5],
        location_city=r[6],
        currency=str(r[7]),
        published_fields=list(r[8]),
        is_published=bool(r[9]),
        revision=int(r[10]),
        recorded_by=r[11],
        recorded_at=r[12],
    )


def _listing_view(r: tuple[Any, ...]) -> ListingView:
    return ListingView(
        listing_id=r[0],
        location_id=r[1],
        storefront_id=r[2],
        legal_entity_id=r[3],
        sku=str(r[4]),
        title=str(r[5]),
        description=r[6],
        category=str(r[7]),
        brand=r[8],
        currency=str(r[9]),
        price_minor=int(r[10]),
        available_quantity=int(r[11]),
        internal_cost_minor=int(r[12]),
        internal_notes=r[13],
        published_fields=list(r[14]),
        moderation_status=r[15],
        revision=int(r[16]),
        recorded_by=r[17],
        recorded_at=r[18],
    )


def _marketplace_view(r: tuple[Any, ...]) -> MarketplaceView:
    return MarketplaceView(
        marketplace_id=r[0],
        location_id=r[1],
        slug=str(r[2]),
        title=str(r[3]),
        description=r[4],
        gorgona_commission_bps=0,
        operator_fee_bps=int(r[6]),
        is_active=bool(r[7]),
        revision=int(r[8]),
        recorded_by=r[9],
        recorded_at=r[10],
    )


def _seller_connection_view(r: tuple[Any, ...]) -> SellerConnectionView:
    return SellerConnectionView(
        connection_id=r[0],
        location_id=r[1],
        marketplace_id=r[2],
        seller_counterparty_id=r[3],
        seller_storefront_slug=str(r[4]),
        granted_scopes=list(r[5]),
        status=r[6],
        revoked_at=r[7],
        revision=int(r[8]),
        recorded_by=r[9],
        recorded_at=r[10],
    )


async def list_storefronts(
    conn: RuntimeConnection,
    business: UUID,
    *,
    location_id: UUID | None = None,
) -> StorefrontList:
    await require_module(conn, business, STOREFRONTS_MODULE)
    rows = await (
        await conn.execute(
            "select id, location_id, legal_entity_id, slug, display_name, "
            "description, location_city, currency, published_fields, is_published, revision, "
            "recorded_by, recorded_at from gba.market_storefronts "
            "where tenant_id = %s and (%s::uuid is null or location_id = %s) order by slug, id",
            (business, location_id, location_id),
        )
    ).fetchall()
    return StorefrontList(items=[_storefront_view(r) for r in rows])


async def get_storefront(
    conn: RuntimeConnection,
    business: UUID,
    storefront_id: UUID,
) -> StorefrontView:
    await require_module(conn, business, STOREFRONTS_MODULE)
    row = await (
        await conn.execute(
            "select id, location_id, legal_entity_id, slug, display_name, "
            "description, location_city, currency, published_fields, is_published, revision, "
            "recorded_by, recorded_at from gba.market_storefronts "
            "where tenant_id = %s and id = %s",
            (business, storefront_id),
        )
    ).fetchone()
    if row is None:
        raise NotFoundError("Storefront not found")
    return _storefront_view(row)


async def save_storefront(
    conn: RuntimeConnection,
    business: UUID,
    storefront_id: UUID,
    *,
    user_id: UUID,
    actor: str,
    key: str,
    body: StorefrontInput,
) -> StorefrontView:
    _check_ready()
    await require_module(conn, business, STOREFRONTS_MODULE)
    scope = IdempotencyScope(business, actor, "market.storefront.save", key)
    replay = await commands.claim(
        conn,
        scope,
        commands.fingerprint({"storefront_id": str(storefront_id), **body.model_dump(mode="json")}),
        StorefrontView,
    )
    if replay is not None:
        return replay

    async with module_writes(STOREFRONTS_MODULE):
        existing = await (
            await conn.execute(
                "select revision, location_id, legal_entity_id from gba.market_storefronts "
                "where tenant_id = %s and id = %s for update",
                (business, storefront_id),
            )
        ).fetchone()
        try:
            if existing is None:
                if body.expected_revision != 0:
                    raise MarketRevisionConflictError(
                        "Storefront does not exist yet; expected_revision must be 0"
                    )
                await conn.execute(
                    "insert into gba.market_storefronts ("
                    "id, tenant_id, location_id, legal_entity_id, slug, display_name, "
                    "description, location_city, currency, published_fields, is_published, "
                    "revision, recorded_by"
                    ") values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 1, %s)",
                    (
                        storefront_id,
                        business,
                        body.location_id,
                        body.legal_entity_id,
                        body.slug,
                        body.display_name,
                        body.description,
                        body.location_city,
                        body.currency,
                        list(body.published_fields),
                        body.is_published,
                        user_id,
                    ),
                )
            else:
                curr_rev, curr_loc, curr_le = int(existing[0]), existing[1], existing[2]
                if body.expected_revision != curr_rev:
                    raise MarketRevisionConflictError("Storefront revision mismatch")
                if body.location_id != curr_loc or body.legal_entity_id != curr_le:
                    raise InvalidReferenceError(
                        "Storefront location_id and legal_entity_id cannot be changed"
                    )
                await conn.execute(
                    "update gba.market_storefronts set slug = %s, display_name = %s, "
                    "description = %s, location_city = %s, currency = %s, "
                    "published_fields = %s, is_published = %s, revision = revision + 1, "
                    "recorded_by = %s, recorded_at = now() where tenant_id = %s and id = %s",
                    (
                        body.slug,
                        body.display_name,
                        body.description,
                        body.location_city,
                        body.currency,
                        list(body.published_fields),
                        body.is_published,
                        user_id,
                        business,
                        storefront_id,
                    ),
                )
        except errors.UniqueViolation as exc:
            raise MarketRevisionConflictError("Storefront slug already exists") from exc
        except errors.ForeignKeyViolation as exc:
            raise InvalidReferenceError(
                "Referenced location, legal entity, or currency not found"
            ) from exc

        view = await get_storefront(conn, business, storefront_id)
        await commands.complete(conn, scope, view)
        return view


# ---------------------------------------------------------------------------
# Listings & Strict Public Field Projection
# ---------------------------------------------------------------------------


async def list_listings(
    conn: RuntimeConnection,
    business: UUID,
    *,
    storefront_id: UUID | None = None,
) -> ListingList:
    await require_module(conn, business, STOREFRONTS_MODULE)
    rows = await (
        await conn.execute(
            "select id, location_id, storefront_id, legal_entity_id, sku, title, "
            "description, category, brand, currency, price_minor, available_quantity, "
            "internal_cost_minor, internal_notes, published_fields, moderation_status, "
            "revision, recorded_by, recorded_at from gba.market_listings "
            "where tenant_id = %s and (%s::uuid is null or storefront_id = %s) order by sku, id",
            (business, storefront_id, storefront_id),
        )
    ).fetchall()
    return ListingList(items=[_listing_view(r) for r in rows])


async def get_listing(
    conn: RuntimeConnection,
    business: UUID,
    listing_id: UUID,
) -> ListingView:
    await require_module(conn, business, STOREFRONTS_MODULE)
    row = await (
        await conn.execute(
            "select id, location_id, storefront_id, legal_entity_id, sku, title, "
            "description, category, brand, currency, price_minor, available_quantity, "
            "internal_cost_minor, internal_notes, published_fields, moderation_status, "
            "revision, recorded_by, recorded_at from gba.market_listings "
            "where tenant_id = %s and id = %s",
            (business, listing_id),
        )
    ).fetchone()
    if row is None:
        raise NotFoundError("Listing not found")
    return _listing_view(row)


async def save_listing(
    conn: RuntimeConnection,
    business: UUID,
    listing_id: UUID,
    *,
    user_id: UUID,
    actor: str,
    key: str,
    body: ListingInput,
) -> ListingView:
    _check_ready()
    await require_module(conn, business, STOREFRONTS_MODULE)
    scope = IdempotencyScope(business, actor, "market.listing.save", key)
    replay = await commands.claim(
        conn,
        scope,
        commands.fingerprint({"listing_id": str(listing_id), **body.model_dump(mode="json")}),
        ListingView,
    )
    if replay is not None:
        return replay

    sf_row = await (
        await conn.execute(
            "select legal_entity_id from gba.market_storefronts "
            "where tenant_id = %s and location_id = %s and id = %s",
            (business, body.location_id, body.storefront_id),
        )
    ).fetchone()
    if sf_row is None:
        raise InvalidReferenceError("Storefront not found in this branch")
    legal_entity_id = sf_row[0]

    async with module_writes(STOREFRONTS_MODULE):
        existing = await (
            await conn.execute(
                "select revision, location_id, storefront_id from gba.market_listings "
                "where tenant_id = %s and id = %s for update",
                (business, listing_id),
            )
        ).fetchone()
        try:
            if existing is None:
                if body.expected_revision != 0:
                    raise MarketRevisionConflictError(
                        "Listing does not exist yet; expected_revision must be 0"
                    )
                await conn.execute(
                    "insert into gba.market_listings ("
                    "id, tenant_id, location_id, storefront_id, legal_entity_id, sku, title, "
                    "description, category, brand, currency, price_minor, available_quantity, "
                    "internal_cost_minor, internal_notes, published_fields, moderation_status, "
                    "revision, recorded_by"
                    ") values ("
                    "%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 1, %s"
                    ")",
                    (
                        listing_id,
                        business,
                        body.location_id,
                        body.storefront_id,
                        legal_entity_id,
                        body.sku,
                        body.title,
                        body.description,
                        body.category,
                        body.brand,
                        body.currency,
                        body.price_minor,
                        body.available_quantity,
                        body.internal_cost_minor,
                        body.internal_notes,
                        list(body.published_fields),
                        body.moderation_status,
                        user_id,
                    ),
                )
            else:
                curr_rev, curr_loc, curr_sf = int(existing[0]), existing[1], existing[2]
                if body.expected_revision != curr_rev:
                    raise MarketRevisionConflictError("Listing revision mismatch")
                if body.location_id != curr_loc or body.storefront_id != curr_sf:
                    raise InvalidReferenceError(
                        "Listing location_id and storefront_id cannot be changed"
                    )
                await conn.execute(
                    "update gba.market_listings set sku = %s, title = %s, description = %s, "
                    "category = %s, brand = %s, currency = %s, price_minor = %s, "
                    "available_quantity = %s, internal_cost_minor = %s, internal_notes = %s, "
                    "published_fields = %s, moderation_status = %s, revision = revision + 1, "
                    "recorded_by = %s, recorded_at = now() where tenant_id = %s and id = %s",
                    (
                        body.sku,
                        body.title,
                        body.description,
                        body.category,
                        body.brand,
                        body.currency,
                        body.price_minor,
                        body.available_quantity,
                        body.internal_cost_minor,
                        body.internal_notes,
                        list(body.published_fields),
                        body.moderation_status,
                        user_id,
                        business,
                        listing_id,
                    ),
                )
        except errors.UniqueViolation as exc:
            raise MarketRevisionConflictError(
                "Listing SKU already exists in this storefront"
            ) from exc
        except errors.ForeignKeyViolation as exc:
            raise InvalidReferenceError("Referenced storefront or currency not found") from exc

        view = await get_listing(conn, business, listing_id)
        await commands.complete(conn, scope, view)
        return view


def project_public_listing(
    *,
    storefront: StorefrontView,
    listing: ListingView,
) -> PublicListingProjection:
    """Strictly project ONLY the intersection of storefront and listing `published_fields`."""
    allowed: list[PublicField] = [
        f for f in listing.published_fields if f in storefront.published_fields
    ]
    raw_map: dict[PublicField, str | int | bool | None] = {
        "title": listing.title,
        "description": listing.description,
        "price": listing.price_minor,
        "currency": listing.currency,
        "category": listing.category,
        "availability": listing.available_quantity > 0,
        "location_city": storefront.location_city,
        "brand": listing.brand,
        "sku": listing.sku,
    }
    projected: dict[str, str | int | bool | None] = {f: raw_map[f] for f in allowed}
    return PublicListingProjection(
        listing_id=listing.listing_id,
        storefront_slug=storefront.slug,
        seller_display_name=storefront.display_name,
        published_fields=allowed,
        fields=projected,
    )


async def get_public_storefront_catalog(
    conn: RuntimeConnection,
    business: UUID,
    storefront_id: UUID,
    *,
    category: str | None = None,
) -> PublicStorefrontCatalog:
    """Return ONLY published listings projected via storefront & listing `published_fields`."""
    await require_module(conn, business, STOREFRONTS_MODULE)
    sf = await get_storefront(conn, business, storefront_id)
    if not sf.is_published:
        raise NotFoundError("Storefront is not published")
    rows = await (
        await conn.execute(
            "select id, location_id, storefront_id, legal_entity_id, sku, title, "
            "description, category, brand, currency, price_minor, available_quantity, "
            "internal_cost_minor, internal_notes, published_fields, moderation_status, "
            "revision, recorded_by, recorded_at from gba.market_listings "
            "where tenant_id = %s and storefront_id = %s and moderation_status = 'published' "
            "and (%s::text is null or category = %s) order by sku, id",
            (business, storefront_id, category, category),
        )
    ).fetchall()
    return PublicStorefrontCatalog(
        storefront_slug=sf.slug,
        display_name=sf.display_name,
        published_fields=sf.published_fields,
        items=[project_public_listing(storefront=sf, listing=_listing_view(row)) for row in rows],
    )


# ---------------------------------------------------------------------------
# Client-Operated Marketplaces & Seller Connections
# ---------------------------------------------------------------------------


async def list_marketplaces(
    conn: RuntimeConnection,
    business: UUID,
    *,
    location_id: UUID | None = None,
) -> MarketplaceList:
    await require_module(conn, business, STOREFRONTS_MODULE)
    rows = await (
        await conn.execute(
            "select id, location_id, slug, title, description, "
            "gorgona_commission_bps, operator_fee_bps, is_active, revision, "
            "recorded_by, recorded_at from gba.marketplaces "
            "where tenant_id = %s and (%s::uuid is null or location_id = %s) order by slug, id",
            (business, location_id, location_id),
        )
    ).fetchall()
    return MarketplaceList(items=[_marketplace_view(r) for r in rows])


async def save_marketplace(
    conn: RuntimeConnection,
    business: UUID,
    marketplace_id: UUID,
    *,
    user_id: UUID,
    actor: str,
    key: str,
    body: MarketplaceInput,
) -> MarketplaceView:
    _check_ready()
    await require_module(conn, business, STOREFRONTS_MODULE)
    scope = IdempotencyScope(business, actor, "market.marketplace.save", key)
    replay = await commands.claim(
        conn,
        scope,
        commands.fingerprint(
            {"marketplace_id": str(marketplace_id), **body.model_dump(mode="json")}
        ),
        MarketplaceView,
    )
    if replay is not None:
        return replay

    async with module_writes(STOREFRONTS_MODULE):
        existing = await (
            await conn.execute(
                "select revision, location_id from gba.marketplaces "
                "where tenant_id = %s and id = %s for update",
                (business, marketplace_id),
            )
        ).fetchone()
        try:
            if existing is None:
                if body.expected_revision != 0:
                    raise MarketRevisionConflictError(
                        "Marketplace does not exist yet; expected_revision must be 0"
                    )
                await conn.execute(
                    "insert into gba.marketplaces ("
                    "id, tenant_id, location_id, slug, title, description, "
                    "gorgona_commission_bps, operator_fee_bps, is_active, revision, recorded_by"
                    ") values (%s, %s, %s, %s, %s, %s, 0, %s, %s, 1, %s)",
                    (
                        marketplace_id,
                        business,
                        body.location_id,
                        body.slug,
                        body.title,
                        body.description,
                        body.operator_fee_bps,
                        body.is_active,
                        user_id,
                    ),
                )
            else:
                curr_rev, curr_loc = int(existing[0]), existing[1]
                if body.expected_revision != curr_rev:
                    raise MarketRevisionConflictError("Marketplace revision mismatch")
                if body.location_id != curr_loc:
                    raise InvalidReferenceError("Marketplace location_id cannot be changed")
                await conn.execute(
                    "update gba.marketplaces set slug = %s, title = %s, description = %s, "
                    "operator_fee_bps = %s, is_active = %s, revision = revision + 1, "
                    "recorded_by = %s, recorded_at = now() where tenant_id = %s and id = %s",
                    (
                        body.slug,
                        body.title,
                        body.description,
                        body.operator_fee_bps,
                        body.is_active,
                        user_id,
                        business,
                        marketplace_id,
                    ),
                )
        except errors.UniqueViolation as exc:
            raise MarketRevisionConflictError("Marketplace slug already exists") from exc
        except errors.ForeignKeyViolation as exc:
            raise InvalidReferenceError("Referenced location not found") from exc

        row = await (
            await conn.execute(
                "select id, location_id, slug, title, description, "
                "gorgona_commission_bps, operator_fee_bps, is_active, revision, "
                "recorded_by, recorded_at from gba.marketplaces "
                "where tenant_id = %s and id = %s",
                (business, marketplace_id),
            )
        ).fetchone()
        if row is None:
            raise NotFoundError("Saved marketplace not found")
        view = _marketplace_view(row)
        await commands.complete(conn, scope, view)
        return view


async def list_seller_connections(
    conn: RuntimeConnection,
    business: UUID,
    marketplace_id: UUID,
) -> SellerConnectionList:
    await require_module(conn, business, STOREFRONTS_MODULE)
    rows = await (
        await conn.execute(
            "select id, location_id, marketplace_id, seller_counterparty_id, "
            "seller_storefront_slug, granted_scopes, status, revoked_at, revision, "
            "recorded_by, recorded_at from gba.marketplace_seller_connections "
            "where tenant_id = %s and marketplace_id = %s order by seller_storefront_slug, id",
            (business, marketplace_id),
        )
    ).fetchall()
    return SellerConnectionList(items=[_seller_connection_view(r) for r in rows])


async def save_seller_connection(
    conn: RuntimeConnection,
    business: UUID,
    marketplace_id: UUID,
    connection_id: UUID,
    *,
    user_id: UUID,
    actor: str,
    key: str,
    body: SellerConnectionInput,
) -> SellerConnectionView:
    _check_ready()
    await require_module(conn, business, STOREFRONTS_MODULE)
    scope = IdempotencyScope(business, actor, "market.seller_conn.save", key)
    replay = await commands.claim(
        conn,
        scope,
        commands.fingerprint(
            {
                "marketplace_id": str(marketplace_id),
                "connection_id": str(connection_id),
                **body.model_dump(mode="json"),
            }
        ),
        SellerConnectionView,
    )
    if replay is not None:
        return replay

    async with module_writes(STOREFRONTS_MODULE):
        existing = await (
            await conn.execute(
                "select revision, status from gba.marketplace_seller_connections "
                "where tenant_id = %s and marketplace_id = %s and id = %s for update",
                (business, marketplace_id, connection_id),
            )
        ).fetchone()
        try:
            if existing is None:
                if body.expected_revision != 0:
                    raise MarketRevisionConflictError(
                        "Seller connection does not exist yet; expected_revision must be 0"
                    )
                await conn.execute(
                    "insert into gba.marketplace_seller_connections ("
                    "id, tenant_id, location_id, marketplace_id, seller_counterparty_id, "
                    "seller_storefront_slug, granted_scopes, status, revoked_at, "
                    "revision, recorded_by"
                    ") values ("
                    "%s, %s, %s, %s, %s, %s, %s, %s, "
                    "case when %s = 'revoked' then now() else null end, 1, %s"
                    ")",
                    (
                        connection_id,
                        business,
                        body.location_id,
                        marketplace_id,
                        body.seller_counterparty_id,
                        body.seller_storefront_slug,
                        list(body.granted_scopes),
                        body.status,
                        body.status,
                        user_id,
                    ),
                )
            else:
                curr_rev, curr_status = int(existing[0]), str(existing[1])
                if body.expected_revision != curr_rev:
                    raise MarketRevisionConflictError("Seller connection revision mismatch")
                if curr_status == "revoked":
                    raise MarketStateError("A revoked seller connection cannot be reactivated")
                await conn.execute(
                    "update gba.marketplace_seller_connections set "
                    "granted_scopes = %s, status = %s, "
                    "revoked_at = case when %s = 'revoked' then now() else null end, "
                    "revision = revision + 1, recorded_by = %s, recorded_at = now() "
                    "where tenant_id = %s and marketplace_id = %s and id = %s",
                    (
                        list(body.granted_scopes),
                        body.status,
                        body.status,
                        user_id,
                        business,
                        marketplace_id,
                        connection_id,
                    ),
                )
        except errors.UniqueViolation as exc:
            raise MarketRevisionConflictError(
                "Seller storefront is already connected to this marketplace"
            ) from exc
        except errors.ForeignKeyViolation as exc:
            raise InvalidReferenceError("Referenced marketplace or counterparty not found") from exc

        row = await (
            await conn.execute(
                "select id, location_id, marketplace_id, seller_counterparty_id, "
                "seller_storefront_slug, granted_scopes, status, revoked_at, revision, "
                "recorded_by, recorded_at from gba.marketplace_seller_connections "
                "where tenant_id = %s and id = %s",
                (business, connection_id),
            )
        ).fetchone()
        if row is None:
            raise NotFoundError("Saved seller connection not found")
        view = _seller_connection_view(row)
        await commands.complete(conn, scope, view)
        return view
