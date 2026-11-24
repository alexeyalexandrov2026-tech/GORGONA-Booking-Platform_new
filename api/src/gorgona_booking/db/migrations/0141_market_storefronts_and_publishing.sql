-- 0141_market_storefronts_and_publishing.sql
-- ADR-0040 / MARKET-01 Slice 1: business storefronts with explicit published_fields allow-list,
-- seller listings with strict private/public field separation, moderation lifecycle, and
-- client-operated marketplaces with independent seller connections and zero GORGONA commission.
-- Invoker rights only.

create table gba.market_storefronts (
    id uuid not null,
    tenant_id uuid not null,
    location_id uuid not null,
    legal_entity_id uuid not null,
    slug text not null,
    display_name text not null,
    description text null,
    location_city text null,
    currency text not null references gba.currencies(code),
    published_fields text[] not null default array['title', 'price', 'currency', 'availability'],
    is_published boolean not null default false,
    revision integer not null default 1,
    recorded_by uuid not null references gba.users(id),
    recorded_at timestamptz not null default now(),
    primary key (tenant_id, id),
    constraint market_storefronts_location_fk
        foreign key (tenant_id, location_id)
        references gba.locations(tenant_id, id) on delete restrict,
    constraint market_storefronts_le_fk
        foreign key (tenant_id, legal_entity_id)
        references gba.legal_entities(tenant_id, id) on delete restrict,
    constraint market_storefronts_loc_id_unique
        unique (tenant_id, location_id, id),
    constraint market_storefronts_anchor_unique
        unique (tenant_id, location_id, id, legal_entity_id),
    constraint market_storefronts_slug_unique
        unique (tenant_id, slug),
    constraint market_storefronts_slug_check
        check (
            btrim(slug) = slug
            and char_length(slug) between 2 and 64
            and slug ~ '^[a-z0-9][a-z0-9-]*$'
        ),
    constraint market_storefronts_name_check
        check (btrim(display_name) = display_name and char_length(display_name) between 1 and 200),
    constraint market_storefronts_fields_check
        check (
            cardinality(published_fields) >= 1
            and published_fields <@ array[
                'title',
                'description',
                'price',
                'currency',
                'category',
                'availability',
                'location_city',
                'brand',
                'sku'
            ]::text[]
        ),
    constraint market_storefronts_revision_check
        check (revision >= 1)
);

create index market_storefronts_tenant_loc_idx
    on gba.market_storefronts (tenant_id, location_id, is_published, slug);

create table gba.market_listings (
    id uuid not null,
    tenant_id uuid not null,
    location_id uuid not null,
    storefront_id uuid not null,
    legal_entity_id uuid not null,
    sku text not null,
    title text not null,
    description text null,
    category text not null,
    brand text null,
    currency text not null references gba.currencies(code),
    price_minor bigint not null,
    available_quantity bigint not null default 0,
    internal_cost_minor bigint not null default 0,
    internal_notes text null,
    published_fields text[] not null default array['title', 'price', 'currency', 'availability'],
    moderation_status text not null default 'draft',
    revision integer not null default 1,
    recorded_by uuid not null references gba.users(id),
    recorded_at timestamptz not null default now(),
    primary key (tenant_id, id),
    constraint market_listings_storefront_fk
        foreign key (tenant_id, location_id, storefront_id, legal_entity_id)
        references gba.market_storefronts(
            tenant_id, location_id, id, legal_entity_id
        ) on delete restrict,
    constraint market_listings_loc_sku_unique
        unique (tenant_id, storefront_id, sku),
    constraint market_listings_anchor_unique
        unique (tenant_id, location_id, id, storefront_id, legal_entity_id),
    constraint market_listings_sku_check
        check (
            btrim(sku) = sku
            and char_length(sku) between 1 and 64
            and sku ~ '^[A-Z0-9][A-Z0-9._:-]*$'
        ),
    constraint market_listings_title_check
        check (btrim(title) = title and char_length(title) between 1 and 200),
    constraint market_listings_category_check
        check (btrim(category) = category and char_length(category) between 1 and 80),
    constraint market_listings_amounts_check
        check (
            price_minor between 0 and 999999999999999
            and available_quantity between 0 and 999999999999
            and internal_cost_minor between 0 and 999999999999999
        ),
    constraint market_listings_fields_check
        check (
            cardinality(published_fields) >= 1
            and published_fields <@ array[
                'title',
                'description',
                'price',
                'currency',
                'category',
                'availability',
                'location_city',
                'brand',
                'sku'
            ]::text[]
        ),
    constraint market_listings_status_check
        check (
            moderation_status in (
                'draft',
                'pending_review',
                'published',
                'suspended',
                'archived'
            )
        ),
    constraint market_listings_revision_check
        check (revision >= 1)
);

create index market_listings_storefront_status_idx
    on gba.market_listings (tenant_id, storefront_id, moderation_status, category);

create table gba.marketplaces (
    id uuid not null,
    tenant_id uuid not null,
    location_id uuid not null,
    slug text not null,
    title text not null,
    description text null,
    gorgona_commission_bps integer not null default 0,
    operator_fee_bps integer not null default 0,
    is_active boolean not null default true,
    revision integer not null default 1,
    recorded_by uuid not null references gba.users(id),
    recorded_at timestamptz not null default now(),
    primary key (tenant_id, id),
    constraint marketplaces_location_fk
        foreign key (tenant_id, location_id)
        references gba.locations(tenant_id, id) on delete restrict,
    constraint marketplaces_loc_id_unique
        unique (tenant_id, location_id, id),
    constraint marketplaces_slug_unique
        unique (tenant_id, slug),
    constraint marketplaces_slug_check
        check (
            btrim(slug) = slug
            and char_length(slug) between 2 and 64
            and slug ~ '^[a-z0-9][a-z0-9-]*$'
        ),
    constraint marketplaces_title_check
        check (btrim(title) = title and char_length(title) between 1 and 200),
    constraint marketplaces_zero_gorgona_commission_check
        check (gorgona_commission_bps = 0 and operator_fee_bps between 0 and 5000),
    constraint marketplaces_revision_check
        check (revision >= 1)
);

create table gba.marketplace_seller_connections (
    id uuid not null,
    tenant_id uuid not null,
    location_id uuid not null,
    marketplace_id uuid not null,
    seller_counterparty_id uuid not null,
    seller_storefront_slug text not null,
    granted_scopes text[] not null default array['publish', 'reports_read'],
    status text not null default 'active',
    revoked_at timestamptz null,
    revision integer not null default 1,
    recorded_by uuid not null references gba.users(id),
    recorded_at timestamptz not null default now(),
    primary key (tenant_id, id),
    constraint marketplace_seller_connections_mp_fk
        foreign key (tenant_id, location_id, marketplace_id)
        references gba.marketplaces(tenant_id, location_id, id) on delete restrict,
    constraint marketplace_seller_connections_cp_fk
        foreign key (tenant_id, seller_counterparty_id)
        references gba.counterparties(tenant_id, id) on delete restrict,
    constraint marketplace_seller_connections_unique
        unique (tenant_id, marketplace_id, seller_counterparty_id, seller_storefront_slug),
    constraint marketplace_seller_connections_scopes_check
        check (
            cardinality(granted_scopes) >= 1
            and granted_scopes <@ array['publish', 'orders_read', 'reports_read']::text[]
        ),
    constraint marketplace_seller_connections_status_check
        check (
            status in ('pending', 'active', 'suspended', 'revoked')
            and ((status = 'revoked') = (revoked_at is not null))
        ),
    constraint marketplace_seller_connections_revision_check
        check (revision >= 1)
);

create index marketplace_seller_connections_mp_idx
    on gba.marketplace_seller_connections (tenant_id, marketplace_id, status);

-- RLS, grants and module write gates
alter table gba.market_storefronts enable row level security;
alter table gba.market_storefronts force row level security;
create policy market_storefronts_tenant_isolation on gba.market_storefronts
    using (tenant_id = gba.current_tenant_id())
    with check (tenant_id = gba.current_tenant_id());
grant select, insert, update, delete on gba.market_storefronts to gba_runtime;
create trigger market_storefronts_require_module
    before insert on gba.market_storefronts
    for each row execute function gba.require_enabled_module('storefronts');

alter table gba.market_listings enable row level security;
alter table gba.market_listings force row level security;
create policy market_listings_tenant_isolation on gba.market_listings
    using (tenant_id = gba.current_tenant_id())
    with check (tenant_id = gba.current_tenant_id());
grant select, insert, update, delete on gba.market_listings to gba_runtime;
create trigger market_listings_require_module
    before insert on gba.market_listings
    for each row execute function gba.require_enabled_module('storefronts');

alter table gba.marketplaces enable row level security;
alter table gba.marketplaces force row level security;
create policy marketplaces_tenant_isolation on gba.marketplaces
    using (tenant_id = gba.current_tenant_id())
    with check (tenant_id = gba.current_tenant_id());
grant select, insert, update, delete on gba.marketplaces to gba_runtime;
create trigger marketplaces_require_module
    before insert on gba.marketplaces
    for each row execute function gba.require_enabled_module('storefronts');

alter table gba.marketplace_seller_connections enable row level security;
alter table gba.marketplace_seller_connections force row level security;
create policy marketplace_seller_connections_tenant_isolation on gba.marketplace_seller_connections
    using (tenant_id = gba.current_tenant_id())
    with check (tenant_id = gba.current_tenant_id());
grant select, insert, update, delete on gba.marketplace_seller_connections to gba_runtime;
create trigger marketplace_seller_connections_require_module
    before insert on gba.marketplace_seller_connections
    for each row execute function gba.require_enabled_module('storefronts');

-- Market storefronts branch scope:
create policy market_storefronts_location_scope on gba.market_storefronts
    as restrictive to gba_runtime
    using (gba.current_location_id() is null or location_id = gba.current_location_id())
    with check (gba.current_location_id() is null or location_id = gba.current_location_id());

create policy market_listings_location_scope on gba.market_listings
    as restrictive to gba_runtime
    using (gba.current_location_id() is null or location_id = gba.current_location_id())
    with check (gba.current_location_id() is null or location_id = gba.current_location_id());

create policy marketplaces_location_scope on gba.marketplaces
    as restrictive to gba_runtime
    using (gba.current_location_id() is null or location_id = gba.current_location_id())
    with check (gba.current_location_id() is null or location_id = gba.current_location_id());

create policy marketplace_seller_connections_location_scope on gba.marketplace_seller_connections
    as restrictive to gba_runtime
    using (gba.current_location_id() is null or location_id = gba.current_location_id())
    with check (gba.current_location_id() is null or location_id = gba.current_location_id());
