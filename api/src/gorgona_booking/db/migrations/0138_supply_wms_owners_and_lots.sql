-- SUPPLY-01 Slice 1 (ADR-0039): Multi-warehouse WMS bins, goods-owner isolation
-- (company legal entity vs 3PL customer bailor), lot/batch & serial tracking,
-- and WMS movements extending STOCK-01 without a second valuation ledger.
-- Invoker rights only.

create table gba.supply_goods_owners (
    tenant_id uuid not null references gba.tenants(id),
    id uuid not null,
    location_id uuid not null,
    code text not null check (code ~ '^[A-Z0-9][A-Z0-9_-]{0,63}$'),
    display_name text not null check (char_length(btrim(display_name)) between 1 and 200),
    owner_kind text not null check (owner_kind in ('company_entity', 'counterparty_3pl')),
    legal_entity_id uuid,
    counterparty_id uuid,
    is_active boolean not null default true,
    revision integer not null default 1 check (revision >= 1),
    recorded_by uuid not null references gba.users(id),
    recorded_at timestamptz not null default clock_timestamp(),
    primary key (tenant_id, id),
    unique (tenant_id, id, location_id),
    unique (tenant_id, id, owner_kind),
    unique (tenant_id, location_id, code),
    foreign key (tenant_id, location_id) references gba.locations(tenant_id, id),
    foreign key (tenant_id, legal_entity_id) references gba.legal_entities(tenant_id, id),
    foreign key (tenant_id, counterparty_id) references gba.counterparties(tenant_id, id),
    check (
        (owner_kind = 'company_entity' and legal_entity_id is not null and counterparty_id is null)
        or (owner_kind = 'counterparty_3pl' and counterparty_id is not null and legal_entity_id is null)
    )
);
create unique index supply_goods_owners_entity_uidx
    on gba.supply_goods_owners (tenant_id, location_id, legal_entity_id)
    where legal_entity_id is not null;
create unique index supply_goods_owners_counterparty_uidx
    on gba.supply_goods_owners (tenant_id, location_id, counterparty_id)
    where counterparty_id is not null;

create table gba.supply_warehouse_bins (
    tenant_id uuid not null references gba.tenants(id),
    id uuid not null,
    location_id uuid not null,
    place_id uuid not null,
    zone_code text not null check (zone_code ~ '^[A-Z0-9][A-Z0-9_-]{0,31}$'),
    bin_code text not null check (bin_code ~ '^[A-Z0-9][A-Z0-9_-]{0,63}$'),
    bin_kind text not null check (bin_kind in ('receiving', 'storage', 'picking', 'production', 'quarantine', 'shipping')),
    dedicated_owner_id uuid,
    is_active boolean not null default true,
    revision integer not null default 1 check (revision >= 1),
    recorded_by uuid not null references gba.users(id),
    recorded_at timestamptz not null default clock_timestamp(),
    primary key (tenant_id, id),
    unique (tenant_id, id, place_id, location_id),
    unique (tenant_id, place_id, bin_code),
    foreign key (tenant_id, place_id, location_id) references gba.stock_places(tenant_id, id, location_id),
    foreign key (tenant_id, dedicated_owner_id, location_id) references gba.supply_goods_owners(tenant_id, id, location_id)
);
create index supply_warehouse_bins_loc_idx
    on gba.supply_warehouse_bins (tenant_id, location_id, place_id, bin_code);

create table gba.supply_lots (
    tenant_id uuid not null references gba.tenants(id),
    id uuid not null,
    location_id uuid not null,
    goods_owner_id uuid not null,
    item_id uuid not null,
    lot_code text not null check (lot_code ~ '^[A-Z0-9][A-Z0-9._-]{0,63}$'),
    manufactured_on date,
    expires_on date,
    status text not null default 'active' check (status in ('active', 'quarantine', 'expired')),
    unit_cost_minor bigint not null default 0 check (unit_cost_minor >= 0),
    notes text check (notes is null or char_length(btrim(notes)) between 1 and 500),
    revision integer not null default 1 check (revision >= 1),
    recorded_by uuid not null references gba.users(id),
    recorded_at timestamptz not null default clock_timestamp(),
    primary key (tenant_id, id),
    unique (tenant_id, id, location_id),
    unique (tenant_id, id, goods_owner_id, item_id, location_id),
    unique (tenant_id, location_id, goods_owner_id, item_id, lot_code),
    foreign key (tenant_id, goods_owner_id, location_id) references gba.supply_goods_owners(tenant_id, id, location_id),
    foreign key (tenant_id, item_id) references gba.stock_items(tenant_id, id),
    check (expires_on is null or manufactured_on is null or expires_on >= manufactured_on)
);
create index supply_lots_owner_item_idx
    on gba.supply_lots (tenant_id, location_id, goods_owner_id, item_id, lot_code);

create table gba.supply_lot_balances (
    tenant_id uuid not null references gba.tenants(id),
    id uuid not null,
    location_id uuid not null,
    place_id uuid not null,
    bin_id uuid not null,
    goods_owner_id uuid not null,
    item_id uuid not null,
    lot_id uuid not null,
    quantity bigint not null check (quantity between 0 and 999999999999999),
    updated_at timestamptz not null default clock_timestamp(),
    primary key (tenant_id, id),
    unique (tenant_id, bin_id, goods_owner_id, item_id, lot_id),
    foreign key (tenant_id, bin_id, place_id, location_id) references gba.supply_warehouse_bins(tenant_id, id, place_id, location_id),
    foreign key (tenant_id, lot_id, goods_owner_id, item_id, location_id)
        references gba.supply_lots(tenant_id, id, goods_owner_id, item_id, location_id)
);
create index supply_lot_balances_owner_idx
    on gba.supply_lot_balances (tenant_id, location_id, goods_owner_id, item_id, lot_id);

create table gba.supply_serial_units (
    tenant_id uuid not null references gba.tenants(id),
    id uuid not null,
    location_id uuid not null,
    place_id uuid not null,
    bin_id uuid not null,
    goods_owner_id uuid not null,
    item_id uuid not null,
    lot_id uuid not null,
    serial_code text not null check (serial_code ~ '^[A-Z0-9][A-Z0-9._-]{0,63}$'),
    state text not null check (state in ('in_stock', 'reserved', 'shipped', 'consumed', 'returned')),
    recorded_by uuid not null references gba.users(id),
    recorded_at timestamptz not null default clock_timestamp(),
    primary key (tenant_id, id),
    unique (tenant_id, item_id, serial_code),
    unique (tenant_id, id, goods_owner_id, item_id, lot_id, location_id),
    foreign key (tenant_id, bin_id, place_id, location_id) references gba.supply_warehouse_bins(tenant_id, id, place_id, location_id),
    foreign key (tenant_id, lot_id, goods_owner_id, item_id, location_id)
        references gba.supply_lots(tenant_id, id, goods_owner_id, item_id, location_id)
);
create index supply_serial_units_lot_idx
    on gba.supply_serial_units (tenant_id, location_id, goods_owner_id, lot_id, state);

create table gba.supply_wms_movements (
    tenant_id uuid not null references gba.tenants(id),
    id uuid not null,
    location_id uuid not null,
    place_id uuid not null,
    bin_id uuid not null,
    to_place_id uuid,
    to_bin_id uuid,
    goods_owner_id uuid not null,
    item_id uuid not null,
    lot_id uuid not null,
    movement_kind text not null check (
        movement_kind in (
            'inbound_putaway',
            'bin_relocation',
            'outbound_pick',
            'return_putaway',
            'production_issue',
            'production_output',
            'production_return'
        )
    ),
    direction text not null check (direction in ('in', 'out', 'relocate')),
    quantity bigint not null check (quantity between 1 and 999999999999),
    stock_document_id uuid,
    stock_line_no smallint,
    reference_code text check (reference_code is null or char_length(btrim(reference_code)) between 1 and 120),
    recorded_by uuid not null references gba.users(id),
    recorded_at timestamptz not null default clock_timestamp(),
    primary key (tenant_id, id),
    foreign key (tenant_id, bin_id, place_id, location_id) references gba.supply_warehouse_bins(tenant_id, id, place_id, location_id),
    foreign key (tenant_id, to_bin_id, to_place_id, location_id) references gba.supply_warehouse_bins(tenant_id, id, place_id, location_id),
    foreign key (tenant_id, lot_id, goods_owner_id, item_id, location_id)
        references gba.supply_lots(tenant_id, id, goods_owner_id, item_id, location_id),
    foreign key (tenant_id, stock_document_id, stock_line_no)
        references gba.stock_document_lines(tenant_id, document_id, line_no),
    check ((stock_document_id is null) = (stock_line_no is null)),
    check (
        (movement_kind = 'bin_relocation' and direction = 'relocate' and to_bin_id is not null and to_place_id is not null and to_bin_id <> bin_id)
        or (movement_kind <> 'bin_relocation' and direction in ('in', 'out') and to_bin_id is null and to_place_id is null)
    )
);
create index supply_wms_movements_lot_idx
    on gba.supply_wms_movements (tenant_id, location_id, goods_owner_id, lot_id, recorded_at desc, id);

-- Enforce dedicated bin owner isolation and STOCK-01 document owner/item/place/quantity consistency
create function gba.check_supply_bin_and_movement_integrity() returns trigger language plpgsql as $$
declare
    v_dedicated_owner uuid;
    v_to_dedicated_owner uuid;
    v_owner_kind text;
    v_owner_entity uuid;
    v_doc_entity uuid;
    v_doc_place uuid;
    v_line_item uuid;
    v_line_qty bigint;
begin
    select dedicated_owner_id into v_dedicated_owner
      from gba.supply_warehouse_bins
     where tenant_id = new.tenant_id and id = new.bin_id;
    if v_dedicated_owner is not null and v_dedicated_owner <> new.goods_owner_id then
        raise exception using errcode = '23514',
            message = 'warehouse bin is dedicated to another goods owner';
    end if;

    if tg_table_name = 'supply_wms_movements' then
        if new.to_bin_id is not null then
            select dedicated_owner_id into v_to_dedicated_owner
              from gba.supply_warehouse_bins
             where tenant_id = new.tenant_id and id = new.to_bin_id;
            if v_to_dedicated_owner is not null and v_to_dedicated_owner <> new.goods_owner_id then
                raise exception using errcode = '23514',
                    message = 'destination warehouse bin is dedicated to another goods owner';
            end if;
        end if;

        select owner_kind, legal_entity_id into v_owner_kind, v_owner_entity
          from gba.supply_goods_owners
         where tenant_id = new.tenant_id and id = new.goods_owner_id;

        if v_owner_kind = 'company_entity' and new.movement_kind <> 'bin_relocation' then
            if new.stock_document_id is null then
                raise exception using errcode = '23514',
                    message = 'company-owned WMS movement requires a linked STOCK-01 document line';
            end if;
            select d.legal_entity_id, d.place_id, l.item_id, l.quantity
              into v_doc_entity, v_doc_place, v_line_item, v_line_qty
              from gba.stock_documents d
              join gba.stock_document_lines l
                on l.tenant_id = d.tenant_id and l.document_id = d.id
             where d.tenant_id = new.tenant_id
               and d.id = new.stock_document_id
               and l.line_no = new.stock_line_no;
            if v_doc_entity <> v_owner_entity then
                raise exception using errcode = '23514',
                    message = 'STOCK-01 document legal entity does not match goods owner';
            end if;
            if v_doc_place <> new.place_id or v_line_item <> new.item_id or new.quantity > v_line_qty then
                raise exception using errcode = '23514',
                    message = 'WMS movement place, item or quantity does not match STOCK-01 document line';
            end if;
        elsif v_owner_kind = 'counterparty_3pl' and new.stock_document_id is not null then
            raise exception using errcode = '23514',
                message = '3PL customer-owned goods cannot attach to a company-owned STOCK-01 valuation document';
        end if;
    end if;

    return new;
end;
$$;
revoke all on function gba.check_supply_bin_and_movement_integrity() from public;
grant execute on function gba.check_supply_bin_and_movement_integrity() to gba_runtime;

create trigger supply_lot_balances_owner_bin_guard
    before insert or update on gba.supply_lot_balances
    for each row execute function gba.check_supply_bin_and_movement_integrity();

create trigger supply_serial_units_owner_bin_guard
    before insert or update on gba.supply_serial_units
    for each row execute function gba.check_supply_bin_and_movement_integrity();

create trigger supply_wms_movements_owner_bin_guard
    before insert on gba.supply_wms_movements
    for each row execute function gba.check_supply_bin_and_movement_integrity();

create function gba.guard_supply_append_only() returns trigger language plpgsql as $$
begin
    raise exception using errcode = '23514',
        message = tg_table_name || ' is append-only';
end;
$$;
revoke all on function gba.guard_supply_append_only() from public;
grant execute on function gba.guard_supply_append_only() to gba_runtime;

create trigger supply_wms_movements_append_only
    before update or delete on gba.supply_wms_movements
    for each row execute function gba.guard_supply_append_only();

-- RLS, module write gates and minimal runtime privileges
alter table gba.supply_goods_owners enable row level security;
alter table gba.supply_goods_owners force row level security;
create policy supply_goods_owners_tenant_isolation on gba.supply_goods_owners
    using (tenant_id = gba.current_tenant_id()) with check (tenant_id = gba.current_tenant_id());
grant select, insert, update on gba.supply_goods_owners to gba_runtime;
create trigger supply_goods_owners_require_module before insert on gba.supply_goods_owners
    for each row execute function gba.require_enabled_module('supply');

alter table gba.supply_warehouse_bins enable row level security;
alter table gba.supply_warehouse_bins force row level security;
create policy supply_warehouse_bins_tenant_isolation on gba.supply_warehouse_bins
    using (tenant_id = gba.current_tenant_id()) with check (tenant_id = gba.current_tenant_id());
grant select, insert, update on gba.supply_warehouse_bins to gba_runtime;
create trigger supply_warehouse_bins_require_module before insert on gba.supply_warehouse_bins
    for each row execute function gba.require_enabled_module('supply');

alter table gba.supply_lots enable row level security;
alter table gba.supply_lots force row level security;
create policy supply_lots_tenant_isolation on gba.supply_lots
    using (tenant_id = gba.current_tenant_id()) with check (tenant_id = gba.current_tenant_id());
grant select, insert, update on gba.supply_lots to gba_runtime;
create trigger supply_lots_require_module before insert on gba.supply_lots
    for each row execute function gba.require_enabled_module('supply');

alter table gba.supply_lot_balances enable row level security;
alter table gba.supply_lot_balances force row level security;
create policy supply_lot_balances_tenant_isolation on gba.supply_lot_balances
    using (tenant_id = gba.current_tenant_id()) with check (tenant_id = gba.current_tenant_id());
grant select, insert, update on gba.supply_lot_balances to gba_runtime;
create trigger supply_lot_balances_require_module before insert on gba.supply_lot_balances
    for each row execute function gba.require_enabled_module('supply');

alter table gba.supply_serial_units enable row level security;
alter table gba.supply_serial_units force row level security;
create policy supply_serial_units_tenant_isolation on gba.supply_serial_units
    using (tenant_id = gba.current_tenant_id()) with check (tenant_id = gba.current_tenant_id());
grant select, insert, update on gba.supply_serial_units to gba_runtime;
create trigger supply_serial_units_require_module before insert on gba.supply_serial_units
    for each row execute function gba.require_enabled_module('supply');

alter table gba.supply_wms_movements enable row level security;
alter table gba.supply_wms_movements force row level security;
create policy supply_wms_movements_tenant_isolation on gba.supply_wms_movements
    using (tenant_id = gba.current_tenant_id()) with check (tenant_id = gba.current_tenant_id());
grant select, insert on gba.supply_wms_movements to gba_runtime;
create trigger supply_wms_movements_require_module before insert on gba.supply_wms_movements
    for each row execute function gba.require_enabled_module('supply');

-- Supply WMS branch scope:
create policy supply_goods_owners_location_scope on gba.supply_goods_owners as restrictive to gba_runtime
    using (gba.current_location_id() is null or location_id = gba.current_location_id())
    with check (gba.current_location_id() is null or location_id = gba.current_location_id());

create policy supply_warehouse_bins_location_scope on gba.supply_warehouse_bins as restrictive to gba_runtime
    using (gba.current_location_id() is null or location_id = gba.current_location_id())
    with check (gba.current_location_id() is null or location_id = gba.current_location_id());

create policy supply_lots_location_scope on gba.supply_lots as restrictive to gba_runtime
    using (gba.current_location_id() is null or location_id = gba.current_location_id())
    with check (gba.current_location_id() is null or location_id = gba.current_location_id());

create policy supply_lot_balances_location_scope on gba.supply_lot_balances as restrictive to gba_runtime
    using (gba.current_location_id() is null or location_id = gba.current_location_id())
    with check (gba.current_location_id() is null or location_id = gba.current_location_id());

create policy supply_serial_units_location_scope on gba.supply_serial_units as restrictive to gba_runtime
    using (gba.current_location_id() is null or location_id = gba.current_location_id())
    with check (gba.current_location_id() is null or location_id = gba.current_location_id());

create policy supply_wms_movements_location_scope on gba.supply_wms_movements as restrictive to gba_runtime
    using (gba.current_location_id() is null or location_id = gba.current_location_id())
    with check (gba.current_location_id() is null or location_id = gba.current_location_id());
