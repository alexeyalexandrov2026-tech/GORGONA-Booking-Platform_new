-- 0142_market_orders_and_settlement.sql
-- ADR-0040 / MARKET-01 Slice 2: multi-seller basket split into strictly single-seller orders
-- & payments (one seller storefront + one legal_entity_id + one FIN-03 invoice/checkout per
-- order), customer refund credit notes, and separate seller-billed operator fees with zero
-- GORGONA transaction commission. Invoker rights only.

create table gba.market_baskets (
    id uuid not null,
    tenant_id uuid not null,
    location_id uuid not null,
    customer_counterparty_id uuid not null,
    marketplace_id uuid null,
    currency text not null references gba.currencies(code),
    split_order_count integer not null,
    recorded_by uuid not null references gba.users(id),
    recorded_at timestamptz not null default now(),
    primary key (tenant_id, id),
    constraint market_baskets_location_fk
        foreign key (tenant_id, location_id)
        references gba.locations(tenant_id, id) on delete restrict,
    constraint market_baskets_customer_fk
        foreign key (tenant_id, customer_counterparty_id)
        references gba.counterparties(tenant_id, id) on delete restrict,
    constraint market_baskets_mp_fk
        foreign key (tenant_id, location_id, marketplace_id)
        references gba.marketplaces(tenant_id, location_id, id) on delete restrict,
    constraint market_baskets_loc_id_unique
        unique (tenant_id, location_id, id),
    constraint market_baskets_split_check
        check (split_order_count between 1 and 50)
);

create table gba.market_orders (
    id uuid not null,
    tenant_id uuid not null,
    location_id uuid not null,
    basket_id uuid not null,
    storefront_id uuid not null,
    legal_entity_id uuid not null,
    customer_counterparty_id uuid not null,
    marketplace_id uuid null,
    order_number text not null,
    currency text not null references gba.currencies(code),
    total_minor bigint not null,
    refunded_minor bigint not null default 0,
    status text not null default 'confirmed',
    book_id uuid not null,
    control_account_id uuid not null,
    revenue_account_id uuid not null,
    invoice_document_id uuid not null,
    invoice_line_id uuid not null,
    obligation_id uuid not null,
    credit_note_document_id uuid null,
    revision integer not null default 1,
    recorded_by uuid not null references gba.users(id),
    recorded_at timestamptz not null default now(),
    primary key (tenant_id, id),
    constraint market_orders_basket_fk
        foreign key (tenant_id, location_id, basket_id)
        references gba.market_baskets(tenant_id, location_id, id) on delete restrict,
    constraint market_orders_storefront_fk
        foreign key (tenant_id, location_id, storefront_id, legal_entity_id)
        references gba.market_storefronts(
            tenant_id, location_id, id, legal_entity_id
        ) on delete restrict,
    constraint market_orders_customer_fk
        foreign key (tenant_id, customer_counterparty_id)
        references gba.counterparties(tenant_id, id) on delete restrict,
    constraint market_orders_invoice_fk
        foreign key (tenant_id, book_id, invoice_document_id)
        references gba.financial_documents(tenant_id, book_id, id) on delete restrict,
    constraint market_orders_credit_fk
        foreign key (tenant_id, book_id, credit_note_document_id)
        references gba.financial_documents(tenant_id, book_id, id) on delete restrict,
    constraint market_orders_seller_anchor_unique
        unique (tenant_id, location_id, id, storefront_id, legal_entity_id),
    constraint market_orders_basket_seller_unique
        unique (tenant_id, basket_id, storefront_id),
    constraint market_orders_number_unique
        unique (tenant_id, location_id, order_number),
    constraint market_orders_bounds_check
        check (
            btrim(order_number) = order_number
            and char_length(order_number) between 1 and 64
            and total_minor between 1 and 999999999999999
            and refunded_minor between 0 and total_minor
            and status in ('confirmed', 'fulfilled', 'partially_refunded', 'refunded')
            and revision >= 1
        )
);

create index market_orders_basket_idx
    on gba.market_orders (tenant_id, basket_id, storefront_id);

create table gba.market_order_lines (
    id uuid not null,
    tenant_id uuid not null,
    location_id uuid not null,
    order_id uuid not null,
    storefront_id uuid not null,
    legal_entity_id uuid not null,
    line_no smallint not null,
    listing_id uuid not null,
    quantity bigint not null,
    unit_price_minor bigint not null,
    line_total_minor bigint not null,
    primary key (tenant_id, id),
    -- Guarantees every line of an order belongs to that order's EXACT single seller & legal entity!
    constraint market_order_lines_order_seller_fk
        foreign key (tenant_id, location_id, order_id, storefront_id, legal_entity_id)
        references gba.market_orders(
            tenant_id, location_id, id, storefront_id, legal_entity_id
        ) on delete cascade,
    constraint market_order_lines_listing_seller_fk
        foreign key (tenant_id, location_id, listing_id, storefront_id, legal_entity_id)
        references gba.market_listings(
            tenant_id, location_id, id, storefront_id, legal_entity_id
        ) on delete restrict,
    constraint market_order_lines_no_unique
        unique (tenant_id, order_id, line_no),
    constraint market_order_lines_bounds_check
        check (
            line_no between 1 and 200
            and quantity between 1 and 999999999999
            and unit_price_minor between 1 and 999999999999999
            and line_total_minor = quantity * unit_price_minor
        )
);

create table gba.market_operator_fees (
    id uuid not null,
    tenant_id uuid not null,
    location_id uuid not null,
    marketplace_id uuid not null,
    order_id uuid not null,
    seller_counterparty_id uuid not null,
    currency text not null references gba.currencies(code),
    gorgona_commission_minor bigint not null default 0,
    operator_fee_minor bigint not null,
    status text not null default 'accrued',
    recorded_by uuid not null references gba.users(id),
    recorded_at timestamptz not null default now(),
    primary key (tenant_id, id),
    constraint market_operator_fees_mp_fk
        foreign key (tenant_id, location_id, marketplace_id)
        references gba.marketplaces(tenant_id, location_id, id) on delete restrict,
    constraint market_operator_fees_order_fk
        foreign key (tenant_id, order_id)
        references gba.market_orders(tenant_id, id) on delete restrict,
    constraint market_operator_fees_seller_cp_fk
        foreign key (tenant_id, seller_counterparty_id)
        references gba.counterparties(tenant_id, id) on delete restrict,
    constraint market_operator_fees_order_unique
        unique (tenant_id, order_id),
    constraint market_operator_fees_bounds_check
        check (
            gorgona_commission_minor = 0
            and operator_fee_minor >= 0
            and status in ('accrued', 'invoiced', 'waived')
        )
);

-- RLS, grants and module write gates
alter table gba.market_baskets enable row level security;
alter table gba.market_baskets force row level security;
create policy market_baskets_tenant_isolation on gba.market_baskets
    using (tenant_id = gba.current_tenant_id())
    with check (tenant_id = gba.current_tenant_id());
grant select, insert, update, delete on gba.market_baskets to gba_runtime;
create trigger market_baskets_require_module
    before insert on gba.market_baskets
    for each row execute function gba.require_enabled_module('storefronts');

alter table gba.market_orders enable row level security;
alter table gba.market_orders force row level security;
create policy market_orders_tenant_isolation on gba.market_orders
    using (tenant_id = gba.current_tenant_id())
    with check (tenant_id = gba.current_tenant_id());
grant select, insert, update, delete on gba.market_orders to gba_runtime;
create trigger market_orders_require_module
    before insert on gba.market_orders
    for each row execute function gba.require_enabled_module('storefronts');

alter table gba.market_order_lines enable row level security;
alter table gba.market_order_lines force row level security;
create policy market_order_lines_tenant_isolation on gba.market_order_lines
    using (tenant_id = gba.current_tenant_id())
    with check (tenant_id = gba.current_tenant_id());
grant select, insert, update, delete on gba.market_order_lines to gba_runtime;
create trigger market_order_lines_require_module
    before insert on gba.market_order_lines
    for each row execute function gba.require_enabled_module('storefronts');

alter table gba.market_operator_fees enable row level security;
alter table gba.market_operator_fees force row level security;
create policy market_operator_fees_tenant_isolation on gba.market_operator_fees
    using (tenant_id = gba.current_tenant_id())
    with check (tenant_id = gba.current_tenant_id());
grant select, insert, update, delete on gba.market_operator_fees to gba_runtime;
create trigger market_operator_fees_require_module
    before insert on gba.market_operator_fees
    for each row execute function gba.require_enabled_module('storefronts');

-- Market orders branch scope:
create policy market_baskets_location_scope on gba.market_baskets
    as restrictive to gba_runtime
    using (gba.current_location_id() is null or location_id = gba.current_location_id())
    with check (gba.current_location_id() is null or location_id = gba.current_location_id());

create policy market_orders_location_scope on gba.market_orders
    as restrictive to gba_runtime
    using (gba.current_location_id() is null or location_id = gba.current_location_id())
    with check (gba.current_location_id() is null or location_id = gba.current_location_id());

create policy market_order_lines_location_scope on gba.market_order_lines
    as restrictive to gba_runtime
    using (gba.current_location_id() is null or location_id = gba.current_location_id())
    with check (gba.current_location_id() is null or location_id = gba.current_location_id());

create policy market_operator_fees_location_scope on gba.market_operator_fees
    as restrictive to gba_runtime
    using (gba.current_location_id() is null or location_id = gba.current_location_id())
    with check (gba.current_location_id() is null or location_id = gba.current_location_id());
