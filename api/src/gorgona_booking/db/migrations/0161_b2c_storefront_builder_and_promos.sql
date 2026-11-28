-- 0161_b2c_storefront_builder_and_promos.sql
-- AMARKAL v2.17.0: 1-Click B2C Storefront Builder, Public Retail/Services Catalog,
-- Promo Codes / Discounts, and 0%-Commission B2C Checkout Orders.
-- Invoker-rights only, ENABLE + FORCE ROW LEVEL SECURITY on every table.

CREATE TABLE gba.b2c_storefronts (
    tenant_id uuid PRIMARY KEY REFERENCES gba.tenants(id) ON DELETE RESTRICT,
    public_slug text NOT NULL UNIQUE CHECK (public_slug ~ '^[a-z0-9][a-z0-9-]{2,62}$'),
    store_name text NOT NULL CHECK (char_length(store_name) BETWEEN 2 AND 120),
    tagline text NOT NULL DEFAULT '' CHECK (char_length(tagline) <= 240),
    hero_image_url text CHECK (
        hero_image_url IS NULL
        OR (char_length(hero_image_url) <= 500 AND hero_image_url LIKE 'https://%')
    ),
    accent_hex text NOT NULL DEFAULT '#111111' CHECK (accent_hex ~ '^#[0-9A-Fa-f]{6}$'),
    support_email text CHECK (
        support_email IS NULL OR char_length(support_email) <= 160
    ),
    is_published boolean NOT NULL DEFAULT false,
    show_services boolean NOT NULL DEFAULT true,
    allow_promo_codes boolean NOT NULL DEFAULT true,
    updated_by_user_id uuid REFERENCES gba.users(id) ON DELETE SET NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE gba.b2c_storefront_items (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id uuid NOT NULL REFERENCES gba.tenants(id) ON DELETE RESTRICT,
    sku text NOT NULL CHECK (sku ~ '^[A-Za-z0-9_-]{2,48}$'),
    title text NOT NULL CHECK (char_length(title) BETWEEN 2 AND 160),
    category text NOT NULL DEFAULT 'Featured' CHECK (char_length(category) BETWEEN 2 AND 64),
    item_kind text NOT NULL DEFAULT 'product' CHECK (
        item_kind IN ('product', 'service', 'package', 'digital')
    ),
    description text NOT NULL DEFAULT '' CHECK (char_length(description) <= 1000),
    price_cents bigint NOT NULL CHECK (price_cents BETWEEN 50 AND 99999999),
    compare_at_cents bigint CHECK (
        compare_at_cents IS NULL OR compare_at_cents BETWEEN 50 AND 99999999
    ),
    currency text NOT NULL DEFAULT 'USD' CHECK (currency = 'USD'),
    image_url text CHECK (
        image_url IS NULL
        OR (char_length(image_url) <= 500 AND image_url LIKE 'https://%')
    ),
    stock_qty integer CHECK (stock_qty IS NULL OR stock_qty >= 0),
    is_active boolean NOT NULL DEFAULT true,
    display_order integer NOT NULL DEFAULT 0 CHECK (display_order BETWEEN 0 AND 1000),
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (tenant_id, sku)
);

CREATE INDEX b2c_storefront_items_tenant_active_idx
    ON gba.b2c_storefront_items (tenant_id, is_active, display_order ASC);

CREATE TABLE gba.b2c_promo_codes (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id uuid NOT NULL REFERENCES gba.tenants(id) ON DELETE RESTRICT,
    code text NOT NULL CHECK (code ~ '^[A-Z0-9_-]{3,32}$'),
    discount_kind text NOT NULL CHECK (discount_kind IN ('percent', 'fixed_cents')),
    discount_value integer NOT NULL CHECK (discount_value > 0),
    min_subtotal_cents bigint NOT NULL DEFAULT 0 CHECK (min_subtotal_cents >= 0),
    max_redemptions integer CHECK (max_redemptions IS NULL OR max_redemptions > 0),
    redemptions_count integer NOT NULL DEFAULT 0 CHECK (redemptions_count >= 0),
    expires_at timestamptz,
    is_active boolean NOT NULL DEFAULT true,
    created_by_user_id uuid REFERENCES gba.users(id) ON DELETE SET NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (tenant_id, code)
);

CREATE INDEX b2c_promo_codes_tenant_active_idx
    ON gba.b2c_promo_codes (tenant_id, is_active, code);

CREATE TABLE gba.b2c_orders (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id uuid NOT NULL REFERENCES gba.tenants(id) ON DELETE RESTRICT,
    order_number text NOT NULL CHECK (char_length(order_number) BETWEEN 4 AND 48),
    customer_name text NOT NULL CHECK (char_length(customer_name) BETWEEN 2 AND 160),
    customer_email text NOT NULL CHECK (char_length(customer_email) BETWEEN 5 AND 160),
    items jsonb NOT NULL,
    subtotal_cents bigint NOT NULL CHECK (subtotal_cents >= 50),
    discount_cents bigint NOT NULL DEFAULT 0 CHECK (discount_cents >= 0),
    total_cents bigint NOT NULL CHECK (total_cents >= 50),
    promo_code text,
    currency text NOT NULL DEFAULT 'USD' CHECK (currency = 'USD'),
    status text NOT NULL DEFAULT 'checkout_open' CHECK (
        status IN ('checkout_open', 'paid', 'fulfilled', 'cancelled', 'refunded')
    ),
    stripe_session_id text,
    checkout_url text,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (tenant_id, order_number)
);

CREATE INDEX b2c_orders_tenant_created_idx
    ON gba.b2c_orders (tenant_id, created_at DESC);

ALTER TABLE gba.b2c_storefronts ENABLE ROW LEVEL SECURITY;
ALTER TABLE gba.b2c_storefronts FORCE ROW LEVEL SECURITY;
ALTER TABLE gba.b2c_storefront_items ENABLE ROW LEVEL SECURITY;
ALTER TABLE gba.b2c_storefront_items FORCE ROW LEVEL SECURITY;
ALTER TABLE gba.b2c_promo_codes ENABLE ROW LEVEL SECURITY;
ALTER TABLE gba.b2c_promo_codes FORCE ROW LEVEL SECURITY;
ALTER TABLE gba.b2c_orders ENABLE ROW LEVEL SECURITY;
ALTER TABLE gba.b2c_orders FORCE ROW LEVEL SECURITY;

-- b2c_storefronts allows tenant-scoped management OR exact published slug lookup for /v1/public/shop
DROP POLICY IF EXISTS b2c_storefronts_tenant_isolation ON gba.b2c_storefronts;
CREATE POLICY b2c_storefronts_tenant_isolation ON gba.b2c_storefronts
    FOR ALL
    TO gba_runtime
    USING (
        tenant_id = gba.current_tenant_id()
        OR (
            is_published = true
            AND public_slug = nullif(pg_catalog.current_setting('gba.b2c_store_slug', true), '')
        )
    )
    WITH CHECK (tenant_id = gba.current_tenant_id());

DROP POLICY IF EXISTS b2c_storefront_items_tenant_isolation ON gba.b2c_storefront_items;
CREATE POLICY b2c_storefront_items_tenant_isolation ON gba.b2c_storefront_items
    FOR ALL
    TO gba_runtime
    USING (tenant_id = gba.current_tenant_id())
    WITH CHECK (tenant_id = gba.current_tenant_id());

DROP POLICY IF EXISTS b2c_promo_codes_tenant_isolation ON gba.b2c_promo_codes;
CREATE POLICY b2c_promo_codes_tenant_isolation ON gba.b2c_promo_codes
    FOR ALL
    TO gba_runtime
    USING (tenant_id = gba.current_tenant_id())
    WITH CHECK (tenant_id = gba.current_tenant_id());

DROP POLICY IF EXISTS b2c_orders_tenant_isolation ON gba.b2c_orders;
CREATE POLICY b2c_orders_tenant_isolation ON gba.b2c_orders
    FOR ALL
    TO gba_runtime
    USING (tenant_id = gba.current_tenant_id())
    WITH CHECK (tenant_id = gba.current_tenant_id());

GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE gba.b2c_storefronts TO gba_runtime;
GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE gba.b2c_storefront_items TO gba_runtime;
GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE gba.b2c_promo_codes TO gba_runtime;
GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE gba.b2c_orders TO gba_runtime;
