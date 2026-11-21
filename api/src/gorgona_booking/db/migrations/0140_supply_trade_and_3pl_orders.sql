-- 0140_supply_trade_and_3pl_orders.sql
-- ADR-0039 / SUPPLY-01 Slice 3: channel & contract price lists, retail/wholesale & 3PL
-- fulfillment orders, owner-isolated lot/serial shipments (posting STOCK-01 COGS write_off
-- + FIN-03 receivable invoice), and customer returns (posting STOCK-01 return + FIN-03
-- credit note draft while restoring exact lot/serial balance and cost).
-- Invoker rights only. Leaves STOCK-01 core tables and inventory_guard.py 100% untouched.

create table gba.supply_price_lists (
    id uuid not null,
    tenant_id uuid not null,
    location_id uuid not null,
    code text not null,
    title text not null,
    channel text not null,
    currency text not null references gba.currencies(code),
    counterparty_id uuid null,
    is_active boolean not null default true,
    revision integer not null default 1,
    recorded_by uuid not null references gba.users(id),
    recorded_at timestamptz not null default clock_timestamp(),
    primary key (tenant_id, id),
    constraint supply_price_lists_location_fk
        foreign key (tenant_id, location_id)
        references gba.locations(tenant_id, id) on delete restrict,
    constraint supply_price_lists_counterparty_fk
        foreign key (tenant_id, counterparty_id)
        references gba.counterparties(tenant_id, id) on delete restrict,
    constraint supply_price_lists_loc_id_unique
        unique (tenant_id, location_id, id),
    constraint supply_price_lists_loc_code_unique
        unique (tenant_id, location_id, code),
    constraint supply_price_lists_code_check
        check (
            btrim(code) = code
            and char_length(code) between 1 and 64
            and code ~ '^[A-Z0-9][A-Z0-9._:-]*$'
        ),
    constraint supply_price_lists_title_check
        check (btrim(title) = title and char_length(title) between 1 and 200),
    constraint supply_price_lists_channel_check
        check (channel in ('retail', 'wholesale', 'contract_b2b')),
    constraint supply_price_lists_revision_check
        check (revision >= 1)
);

create index supply_price_lists_tenant_loc_idx
    on gba.supply_price_lists (tenant_id, location_id, channel, code);

create table gba.supply_price_list_items (
    id uuid not null,
    tenant_id uuid not null,
    location_id uuid not null,
    price_list_id uuid not null,
    item_id uuid not null,
    min_quantity bigint not null default 1,
    unit_price_minor bigint not null,
    primary key (tenant_id, id),
    constraint supply_price_list_items_list_fk
        foreign key (tenant_id, location_id, price_list_id)
        references gba.supply_price_lists(tenant_id, location_id, id) on delete cascade,
    constraint supply_price_list_items_item_fk
        foreign key (tenant_id, item_id)
        references gba.stock_items(tenant_id, id) on delete restrict,
    constraint supply_price_list_items_tier_unique
        unique (tenant_id, price_list_id, item_id, min_quantity),
    constraint supply_price_list_items_bounds_check
        check (
            min_quantity between 1 and 999999999999
            and unit_price_minor between 0 and 999999999999999
        )
);

create index supply_price_list_items_lookup_idx
    on gba.supply_price_list_items (tenant_id, price_list_id, item_id, min_quantity desc);

create table gba.supply_trade_orders (
    id uuid not null,
    tenant_id uuid not null,
    location_id uuid not null,
    code text not null,
    order_kind text not null,
    goods_owner_id uuid not null,
    customer_counterparty_id uuid not null,
    price_list_id uuid null,
    currency text not null references gba.currencies(code),
    book_id uuid null,
    control_account_id uuid null,
    revenue_account_id uuid null,
    status text not null default 'confirmed',
    total_ordered_minor bigint not null default 0,
    total_shipped_minor bigint not null default 0,
    total_returned_minor bigint not null default 0,
    revision integer not null default 1,
    recorded_by uuid not null references gba.users(id),
    recorded_at timestamptz not null default clock_timestamp(),
    primary key (tenant_id, id),
    constraint supply_trade_orders_location_fk
        foreign key (tenant_id, location_id)
        references gba.locations(tenant_id, id) on delete restrict,
    constraint supply_trade_orders_owner_fk
        foreign key (tenant_id, goods_owner_id, location_id)
        references gba.supply_goods_owners(tenant_id, id, location_id) on delete restrict,
    constraint supply_trade_orders_customer_fk
        foreign key (tenant_id, customer_counterparty_id)
        references gba.counterparties(tenant_id, id) on delete restrict,
    constraint supply_trade_orders_price_list_fk
        foreign key (tenant_id, location_id, price_list_id)
        references gba.supply_price_lists(tenant_id, location_id, id) on delete restrict,
    constraint supply_trade_orders_book_fk
        foreign key (tenant_id, book_id)
        references gba.ledger_books(tenant_id, id) on delete restrict,
    constraint supply_trade_orders_loc_id_unique
        unique (tenant_id, location_id, id),
    constraint supply_trade_orders_loc_code_unique
        unique (tenant_id, location_id, code),
    constraint supply_trade_orders_owner_anchor_unique
        unique (tenant_id, location_id, id, goods_owner_id),
    constraint supply_trade_orders_code_check
        check (
            btrim(code) = code
            and char_length(code) between 1 and 64
            and code ~ '^[A-Z0-9][A-Z0-9._:-]*$'
        ),
    constraint supply_trade_orders_kind_check
        check (order_kind in ('retail_sale', 'wholesale_sale', '3pl_fulfillment')),
    constraint supply_trade_orders_status_check
        check (
            status in (
                'draft',
                'confirmed',
                'partially_shipped',
                'shipped',
                'returned',
                'cancelled'
            )
        ),
    constraint supply_trade_orders_totals_check
        check (
            total_ordered_minor >= 0
            and total_shipped_minor >= 0
            and total_returned_minor >= 0
            and total_shipped_minor <= total_ordered_minor
            and total_returned_minor <= total_shipped_minor
        ),
    constraint supply_trade_orders_revision_check
        check (revision >= 1)
);

create index supply_trade_orders_tenant_loc_idx
    on gba.supply_trade_orders (tenant_id, location_id, status, code);

create table gba.supply_trade_order_lines (
    id uuid not null,
    tenant_id uuid not null,
    location_id uuid not null,
    order_id uuid not null,
    line_no smallint not null,
    item_id uuid not null,
    ordered_quantity bigint not null,
    shipped_quantity bigint not null default 0,
    returned_quantity bigint not null default 0,
    unit_price_minor bigint not null,
    line_total_minor bigint not null,
    primary key (tenant_id, id),
    constraint supply_trade_order_lines_order_fk
        foreign key (tenant_id, location_id, order_id)
        references gba.supply_trade_orders(tenant_id, location_id, id) on delete cascade,
    constraint supply_trade_order_lines_item_fk
        foreign key (tenant_id, item_id)
        references gba.stock_items(tenant_id, id) on delete restrict,
    constraint supply_trade_order_lines_anchor_unique
        unique (tenant_id, location_id, id, order_id, item_id),
    constraint supply_trade_order_lines_no_unique
        unique (tenant_id, order_id, line_no),
    constraint supply_trade_order_lines_item_unique
        unique (tenant_id, order_id, item_id),
    constraint supply_trade_order_lines_bounds_check
        check (
            line_no between 1 and 200
            and ordered_quantity between 1 and 999999999999
            and shipped_quantity between 0 and ordered_quantity
            and returned_quantity between 0 and shipped_quantity
            and unit_price_minor between 0 and 999999999999999
            and line_total_minor = ordered_quantity * unit_price_minor
        )
);

create table gba.supply_order_shipments (
    id uuid not null,
    tenant_id uuid not null,
    location_id uuid not null,
    order_id uuid not null,
    order_line_id uuid not null,
    goods_owner_id uuid not null,
    place_id uuid not null,
    bin_id uuid not null,
    item_id uuid not null,
    lot_id uuid not null,
    quantity bigint not null,
    returned_quantity bigint not null default 0,
    unit_price_minor bigint not null,
    revenue_minor bigint not null,
    cogs_minor bigint not null default 0,
    returned_cogs_minor bigint not null default 0,
    wms_movement_id uuid not null,
    stock_document_id uuid null,
    stock_line_no smallint null,
    book_id uuid null,
    invoice_document_id uuid null,
    invoice_line_id uuid null,
    obligation_id uuid null,
    recorded_by uuid not null references gba.users(id),
    recorded_at timestamptz not null default clock_timestamp(),
    primary key (tenant_id, id),
    constraint supply_order_shipments_order_owner_fk
        foreign key (tenant_id, location_id, order_id, goods_owner_id)
        references gba.supply_trade_orders(
            tenant_id, location_id, id, goods_owner_id
        ) on delete restrict,
    constraint supply_order_shipments_line_fk
        foreign key (tenant_id, location_id, order_line_id, order_id, item_id)
        references gba.supply_trade_order_lines(
            tenant_id, location_id, id, order_id, item_id
        ) on delete restrict,
    constraint supply_order_shipments_lot_owner_fk
        foreign key (tenant_id, lot_id, goods_owner_id, item_id, location_id)
        references gba.supply_lots(
            tenant_id, id, goods_owner_id, item_id, location_id
        ) on delete restrict,
    constraint supply_order_shipments_bin_fk
        foreign key (tenant_id, bin_id, place_id, location_id)
        references gba.supply_warehouse_bins(
            tenant_id, id, place_id, location_id
        ) on delete restrict,
    constraint supply_order_shipments_movement_fk
        foreign key (tenant_id, wms_movement_id)
        references gba.supply_wms_movements(tenant_id, id) on delete restrict,
    constraint supply_order_shipments_stock_line_fk
        foreign key (tenant_id, stock_document_id, stock_line_no)
        references gba.stock_document_lines(
            tenant_id, document_id, line_no
        ) on delete restrict,
    constraint supply_order_shipments_invoice_fk
        foreign key (tenant_id, book_id, invoice_document_id)
        references gba.financial_documents(tenant_id, book_id, id) on delete restrict,
    constraint supply_order_shipments_return_anchor_unique
        unique (
            tenant_id,
            location_id,
            id,
            order_id,
            order_line_id,
            goods_owner_id,
            place_id,
            item_id,
            lot_id
        ),
    constraint supply_order_shipments_bounds_check
        check (
            quantity between 1 and 999999999999
            and returned_quantity between 0 and quantity
            and unit_price_minor >= 0
            and revenue_minor = quantity * unit_price_minor
            and cogs_minor >= 0
            and returned_cogs_minor between 0 and cogs_minor
            and ((stock_document_id is null) = (stock_line_no is null))
            and ((book_id is null) = (invoice_document_id is null))
            and ((invoice_document_id is null) = (invoice_line_id is null))
            and ((invoice_document_id is null) = (obligation_id is null))
        )
);

create index supply_order_shipments_order_idx
    on gba.supply_order_shipments (tenant_id, order_id, recorded_at, id);

create table gba.supply_order_returns (
    id uuid not null,
    tenant_id uuid not null,
    location_id uuid not null,
    order_id uuid not null,
    order_line_id uuid not null,
    shipment_id uuid not null,
    goods_owner_id uuid not null,
    place_id uuid not null,
    bin_id uuid not null,
    item_id uuid not null,
    lot_id uuid not null,
    quantity bigint not null,
    refund_minor bigint not null,
    cogs_restored_minor bigint not null default 0,
    wms_movement_id uuid not null,
    stock_return_document_id uuid null,
    stock_return_line_no smallint null,
    book_id uuid null,
    credit_note_document_id uuid null,
    reason text not null,
    recorded_by uuid not null references gba.users(id),
    recorded_at timestamptz not null default clock_timestamp(),
    primary key (tenant_id, id),
    constraint supply_order_returns_shipment_fk
        foreign key (
            tenant_id,
            location_id,
            shipment_id,
            order_id,
            order_line_id,
            goods_owner_id,
            place_id,
            item_id,
            lot_id
        )
        references gba.supply_order_shipments(
            tenant_id,
            location_id,
            id,
            order_id,
            order_line_id,
            goods_owner_id,
            place_id,
            item_id,
            lot_id
        ) on delete restrict,
    constraint supply_order_returns_bin_fk
        foreign key (tenant_id, bin_id, place_id, location_id)
        references gba.supply_warehouse_bins(
            tenant_id, id, place_id, location_id
        ) on delete restrict,
    constraint supply_order_returns_movement_fk
        foreign key (tenant_id, wms_movement_id)
        references gba.supply_wms_movements(tenant_id, id) on delete restrict,
    constraint supply_order_returns_stock_line_fk
        foreign key (tenant_id, stock_return_document_id, stock_return_line_no)
        references gba.stock_document_lines(
            tenant_id, document_id, line_no
        ) on delete restrict,
    constraint supply_order_returns_credit_fk
        foreign key (tenant_id, book_id, credit_note_document_id)
        references gba.financial_documents(tenant_id, book_id, id) on delete restrict,
    constraint supply_order_returns_bounds_check
        check (
            quantity between 1 and 999999999999
            and refund_minor >= 0
            and cogs_restored_minor >= 0
            and btrim(reason) = reason
            and char_length(reason) between 1 and 300
            and ((stock_return_document_id is null) = (stock_return_line_no is null))
            and ((book_id is null) = (credit_note_document_id is null))
        )
);

create index supply_order_returns_order_idx
    on gba.supply_order_returns (tenant_id, order_id, recorded_at, id);

-- RLS, grants and module write gates
alter table gba.supply_price_lists enable row level security;
alter table gba.supply_price_lists force row level security;
create policy supply_price_lists_tenant_isolation on gba.supply_price_lists
    using (tenant_id = gba.current_tenant_id()) with check (tenant_id = gba.current_tenant_id());
grant select, insert, update on gba.supply_price_lists to gba_runtime;
create trigger supply_price_lists_require_module before insert on gba.supply_price_lists
    for each row execute function gba.require_enabled_module('supply');

alter table gba.supply_price_list_items enable row level security;
alter table gba.supply_price_list_items force row level security;
create policy supply_price_list_items_tenant_isolation on gba.supply_price_list_items
    using (tenant_id = gba.current_tenant_id()) with check (tenant_id = gba.current_tenant_id());
grant select, insert, update, delete on gba.supply_price_list_items to gba_runtime;
create trigger supply_price_list_items_require_module before insert on gba.supply_price_list_items
    for each row execute function gba.require_enabled_module('supply');

alter table gba.supply_trade_orders enable row level security;
alter table gba.supply_trade_orders force row level security;
create policy supply_trade_orders_tenant_isolation on gba.supply_trade_orders
    using (tenant_id = gba.current_tenant_id()) with check (tenant_id = gba.current_tenant_id());
grant select, insert, update on gba.supply_trade_orders to gba_runtime;
create trigger supply_trade_orders_require_module before insert on gba.supply_trade_orders
    for each row execute function gba.require_enabled_module('supply');

alter table gba.supply_trade_order_lines enable row level security;
alter table gba.supply_trade_order_lines force row level security;
create policy supply_trade_order_lines_tenant_isolation on gba.supply_trade_order_lines
    using (tenant_id = gba.current_tenant_id()) with check (tenant_id = gba.current_tenant_id());
grant select, insert, update, delete on gba.supply_trade_order_lines to gba_runtime;
create trigger supply_trade_order_lines_require_module before insert on gba.supply_trade_order_lines
    for each row execute function gba.require_enabled_module('supply');

alter table gba.supply_order_shipments enable row level security;
alter table gba.supply_order_shipments force row level security;
create policy supply_order_shipments_tenant_isolation on gba.supply_order_shipments
    using (tenant_id = gba.current_tenant_id()) with check (tenant_id = gba.current_tenant_id());
grant select, insert, update on gba.supply_order_shipments to gba_runtime;
create trigger supply_order_shipments_require_module before insert on gba.supply_order_shipments
    for each row execute function gba.require_enabled_module('supply');

alter table gba.supply_order_returns enable row level security;
alter table gba.supply_order_returns force row level security;
create policy supply_order_returns_tenant_isolation on gba.supply_order_returns
    using (tenant_id = gba.current_tenant_id()) with check (tenant_id = gba.current_tenant_id());
grant select, insert on gba.supply_order_returns to gba_runtime;
create trigger supply_order_returns_require_module before insert on gba.supply_order_returns
    for each row execute function gba.require_enabled_module('supply');

-- Supply trade branch scope:
create policy supply_price_lists_location_scope on gba.supply_price_lists as restrictive to gba_runtime
    using (gba.current_location_id() is null or location_id = gba.current_location_id())
    with check (gba.current_location_id() is null or location_id = gba.current_location_id());

create policy supply_price_list_items_location_scope on gba.supply_price_list_items as restrictive to gba_runtime
    using (gba.current_location_id() is null or location_id = gba.current_location_id())
    with check (gba.current_location_id() is null or location_id = gba.current_location_id());

create policy supply_trade_orders_location_scope on gba.supply_trade_orders as restrictive to gba_runtime
    using (gba.current_location_id() is null or location_id = gba.current_location_id())
    with check (gba.current_location_id() is null or location_id = gba.current_location_id());

create policy supply_trade_order_lines_location_scope on gba.supply_trade_order_lines as restrictive to gba_runtime
    using (gba.current_location_id() is null or location_id = gba.current_location_id())
    with check (gba.current_location_id() is null or location_id = gba.current_location_id());

create policy supply_order_shipments_location_scope on gba.supply_order_shipments as restrictive to gba_runtime
    using (gba.current_location_id() is null or location_id = gba.current_location_id())
    with check (gba.current_location_id() is null or location_id = gba.current_location_id());

create policy supply_order_returns_location_scope on gba.supply_order_returns as restrictive to gba_runtime
    using (gba.current_location_id() is null or location_id = gba.current_location_id())
    with check (gba.current_location_id() is null or location_id = gba.current_location_id());
