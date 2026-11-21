-- SUPPLY-01 Slice 2 (ADR-0039): Manufacturing BOMs, production work orders,
-- component lot issues (STOCK-01 write_off), unused material returns (STOCK-01 return),
-- quality control, and finished-goods lot output (STOCK-01 receipt) with cost conservation.
-- Invoker rights only.

create table gba.supply_boms (
    tenant_id uuid not null references gba.tenants(id),
    id uuid not null,
    location_id uuid not null,
    code text not null check (code ~ '^[A-Z0-9][A-Z0-9_-]{0,63}$'),
    title text not null check (char_length(btrim(title)) between 1 and 200),
    output_item_id uuid not null,
    batch_output_quantity bigint not null check (batch_output_quantity between 1 and 999999999999),
    standard_labor_minor bigint not null default 0 check (standard_labor_minor >= 0),
    standard_overhead_minor bigint not null default 0 check (standard_overhead_minor >= 0),
    is_active boolean not null default true,
    revision integer not null default 1 check (revision >= 1),
    recorded_by uuid not null references gba.users(id),
    recorded_at timestamptz not null default clock_timestamp(),
    primary key (tenant_id, id),
    unique (tenant_id, id, location_id),
    unique (tenant_id, id, output_item_id, location_id),
    unique (tenant_id, location_id, code),
    foreign key (tenant_id, location_id) references gba.locations(tenant_id, id),
    foreign key (tenant_id, output_item_id) references gba.stock_items(tenant_id, id)
);

create table gba.supply_bom_components (
    tenant_id uuid not null references gba.tenants(id),
    id uuid not null,
    location_id uuid not null,
    bom_id uuid not null,
    line_no smallint not null check (line_no between 1 and 100),
    component_item_id uuid not null,
    quantity_per_batch bigint not null check (quantity_per_batch between 1 and 999999999999),
    scrap_bps integer not null default 0 check (scrap_bps between 0 and 10000),
    recorded_at timestamptz not null default clock_timestamp(),
    primary key (tenant_id, id),
    unique (tenant_id, bom_id, line_no),
    unique (tenant_id, bom_id, component_item_id),
    foreign key (tenant_id, bom_id, location_id) references gba.supply_boms(tenant_id, id, location_id),
    foreign key (tenant_id, component_item_id) references gba.stock_items(tenant_id, id)
);

create table gba.supply_work_orders (
    tenant_id uuid not null references gba.tenants(id),
    id uuid not null,
    location_id uuid not null,
    code text not null check (code ~ '^[A-Z0-9][A-Z0-9_-]{0,63}$'),
    goods_owner_id uuid not null,
    bom_id uuid not null,
    output_item_id uuid not null,
    place_id uuid not null,
    planned_quantity bigint not null check (planned_quantity between 1 and 999999999999),
    issued_material_cost_minor bigint not null default 0 check (issued_material_cost_minor >= 0),
    returned_material_cost_minor bigint not null default 0 check (returned_material_cost_minor >= 0),
    labor_cost_minor bigint not null default 0 check (labor_cost_minor >= 0),
    overhead_cost_minor bigint not null default 0 check (overhead_cost_minor >= 0),
    completed_quantity bigint not null default 0 check (completed_quantity >= 0),
    scrap_quantity bigint not null default 0 check (scrap_quantity >= 0),
    output_total_cost_minor bigint not null default 0 check (output_total_cost_minor >= 0),
    status text not null check (status in ('draft', 'released', 'in_progress', 'qc_passed', 'completed', 'cancelled')),
    revision integer not null default 1 check (revision >= 1),
    recorded_by uuid not null references gba.users(id),
    recorded_at timestamptz not null default clock_timestamp(),
    primary key (tenant_id, id),
    unique (tenant_id, id, location_id),
    unique (tenant_id, id, goods_owner_id, location_id),
    unique (tenant_id, location_id, code),
    foreign key (tenant_id, goods_owner_id, location_id) references gba.supply_goods_owners(tenant_id, id, location_id),
    foreign key (tenant_id, bom_id, output_item_id, location_id)
        references gba.supply_boms(tenant_id, id, output_item_id, location_id),
    foreign key (tenant_id, place_id, location_id) references gba.stock_places(tenant_id, id, location_id),
    check (returned_material_cost_minor <= issued_material_cost_minor)
);
create index supply_work_orders_loc_idx
    on gba.supply_work_orders (tenant_id, location_id, status, id);

create table gba.supply_work_order_issues (
    tenant_id uuid not null references gba.tenants(id),
    id uuid not null,
    location_id uuid not null,
    work_order_id uuid not null,
    goods_owner_id uuid not null,
    place_id uuid not null,
    bin_id uuid not null,
    component_item_id uuid not null,
    lot_id uuid not null,
    quantity bigint not null check (quantity between 1 and 999999999999),
    returned_quantity bigint not null default 0 check (returned_quantity >= 0 and returned_quantity <= quantity),
    stock_document_id uuid not null,
    stock_line_no smallint not null,
    cost_minor bigint not null check (cost_minor >= 0),
    returned_cost_minor bigint not null default 0 check (returned_cost_minor >= 0 and returned_cost_minor <= cost_minor),
    recorded_by uuid not null references gba.users(id),
    recorded_at timestamptz not null default clock_timestamp(),
    primary key (tenant_id, id),
    unique (tenant_id, id, work_order_id, goods_owner_id, component_item_id, lot_id, location_id),
    foreign key (tenant_id, work_order_id, goods_owner_id, location_id)
        references gba.supply_work_orders(tenant_id, id, goods_owner_id, location_id),
    foreign key (tenant_id, bin_id, place_id, location_id)
        references gba.supply_warehouse_bins(tenant_id, id, place_id, location_id),
    foreign key (tenant_id, lot_id, goods_owner_id, component_item_id, location_id)
        references gba.supply_lots(tenant_id, id, goods_owner_id, item_id, location_id),
    foreign key (tenant_id, stock_document_id, stock_line_no)
        references gba.stock_document_lines(tenant_id, document_id, line_no)
);
create index supply_work_order_issues_wo_idx
    on gba.supply_work_order_issues (tenant_id, work_order_id, recorded_at, id);

create table gba.supply_work_order_returns (
    tenant_id uuid not null references gba.tenants(id),
    id uuid not null,
    location_id uuid not null,
    work_order_id uuid not null,
    issue_id uuid not null,
    goods_owner_id uuid not null,
    place_id uuid not null,
    bin_id uuid not null,
    component_item_id uuid not null,
    lot_id uuid not null,
    quantity bigint not null check (quantity between 1 and 999999999999),
    stock_return_document_id uuid not null,
    stock_return_line_no smallint not null,
    cost_returned_minor bigint not null check (cost_returned_minor >= 0),
    recorded_by uuid not null references gba.users(id),
    recorded_at timestamptz not null default clock_timestamp(),
    primary key (tenant_id, id),
    foreign key (tenant_id, issue_id, work_order_id, goods_owner_id, component_item_id, lot_id, location_id)
        references gba.supply_work_order_issues(tenant_id, id, work_order_id, goods_owner_id, component_item_id, lot_id, location_id),
    foreign key (tenant_id, bin_id, place_id, location_id)
        references gba.supply_warehouse_bins(tenant_id, id, place_id, location_id),
    foreign key (tenant_id, stock_return_document_id, stock_return_line_no)
        references gba.stock_document_lines(tenant_id, document_id, line_no)
);
create index supply_work_order_returns_wo_idx
    on gba.supply_work_order_returns (tenant_id, work_order_id, recorded_at, id);

create table gba.supply_work_order_qc (
    tenant_id uuid not null references gba.tenants(id),
    id uuid not null,
    location_id uuid not null,
    work_order_id uuid not null,
    passed_quantity bigint not null check (passed_quantity between 1 and 999999999999),
    scrap_quantity bigint not null default 0 check (scrap_quantity >= 0),
    notes text check (notes is null or char_length(btrim(notes)) between 1 and 500),
    inspected_by uuid not null references gba.users(id),
    inspected_at timestamptz not null default clock_timestamp(),
    primary key (tenant_id, id),
    foreign key (tenant_id, work_order_id, location_id)
        references gba.supply_work_orders(tenant_id, id, location_id)
);

create table gba.supply_work_order_outputs (
    tenant_id uuid not null references gba.tenants(id),
    id uuid not null,
    location_id uuid not null,
    work_order_id uuid not null,
    goods_owner_id uuid not null,
    place_id uuid not null,
    bin_id uuid not null,
    output_item_id uuid not null,
    output_lot_id uuid not null,
    quantity bigint not null check (quantity between 1 and 999999999999),
    material_cost_minor bigint not null check (material_cost_minor >= 0),
    labor_cost_minor bigint not null check (labor_cost_minor >= 0),
    overhead_cost_minor bigint not null check (overhead_cost_minor >= 0),
    total_cost_minor bigint not null check (total_cost_minor = material_cost_minor + labor_cost_minor + overhead_cost_minor),
    unit_cost_minor bigint not null check (unit_cost_minor >= 0),
    stock_receipt_document_id uuid not null,
    stock_receipt_line_no smallint not null,
    recorded_by uuid not null references gba.users(id),
    recorded_at timestamptz not null default clock_timestamp(),
    primary key (tenant_id, id),
    unique (tenant_id, work_order_id),
    foreign key (tenant_id, work_order_id, goods_owner_id, location_id)
        references gba.supply_work_orders(tenant_id, id, goods_owner_id, location_id),
    foreign key (tenant_id, bin_id, place_id, location_id)
        references gba.supply_warehouse_bins(tenant_id, id, place_id, location_id),
    foreign key (tenant_id, output_lot_id, goods_owner_id, output_item_id, location_id)
        references gba.supply_lots(tenant_id, id, goods_owner_id, item_id, location_id),
    foreign key (tenant_id, stock_receipt_document_id, stock_receipt_line_no)
        references gba.stock_document_lines(tenant_id, document_id, line_no)
);

-- Enforce that manufacturing work orders belong to a company_entity goods owner
create function gba.check_supply_work_order_company_owner() returns trigger language plpgsql as $$
declare
    v_kind text;
begin
    select owner_kind into v_kind
      from gba.supply_goods_owners
     where tenant_id = new.tenant_id and id = new.goods_owner_id;
    if v_kind <> 'company_entity' then
        raise exception using errcode = '23514',
            message = 'manufacturing work orders require a company_entity goods owner';
    end if;
    return new;
end;
$$;
revoke all on function gba.check_supply_work_order_company_owner() from public;
grant execute on function gba.check_supply_work_order_company_owner() to gba_runtime;

create trigger supply_work_orders_company_owner_guard
    before insert or update on gba.supply_work_orders
    for each row execute function gba.check_supply_work_order_company_owner();

create trigger supply_work_order_returns_append_only
    before update or delete on gba.supply_work_order_returns
    for each row execute function gba.guard_supply_append_only();

create trigger supply_work_order_qc_append_only
    before update or delete on gba.supply_work_order_qc
    for each row execute function gba.guard_supply_append_only();

create trigger supply_work_order_outputs_append_only
    before update or delete on gba.supply_work_order_outputs
    for each row execute function gba.guard_supply_append_only();

-- RLS, module write gates (before insert, tgtype=7) and minimal runtime privileges
alter table gba.supply_boms enable row level security;
alter table gba.supply_boms force row level security;
create policy supply_boms_tenant_isolation on gba.supply_boms
    using (tenant_id = gba.current_tenant_id()) with check (tenant_id = gba.current_tenant_id());
grant select, insert, update on gba.supply_boms to gba_runtime;
create trigger supply_boms_require_module before insert on gba.supply_boms
    for each row execute function gba.require_enabled_module('supply');

alter table gba.supply_bom_components enable row level security;
alter table gba.supply_bom_components force row level security;
create policy supply_bom_components_tenant_isolation on gba.supply_bom_components
    using (tenant_id = gba.current_tenant_id()) with check (tenant_id = gba.current_tenant_id());
grant select, insert, delete on gba.supply_bom_components to gba_runtime;
create trigger supply_bom_components_require_module before insert on gba.supply_bom_components
    for each row execute function gba.require_enabled_module('supply');

alter table gba.supply_work_orders enable row level security;
alter table gba.supply_work_orders force row level security;
create policy supply_work_orders_tenant_isolation on gba.supply_work_orders
    using (tenant_id = gba.current_tenant_id()) with check (tenant_id = gba.current_tenant_id());
grant select, insert, update on gba.supply_work_orders to gba_runtime;
create trigger supply_work_orders_require_module before insert on gba.supply_work_orders
    for each row execute function gba.require_enabled_module('supply');

alter table gba.supply_work_order_issues enable row level security;
alter table gba.supply_work_order_issues force row level security;
create policy supply_work_order_issues_tenant_isolation on gba.supply_work_order_issues
    using (tenant_id = gba.current_tenant_id()) with check (tenant_id = gba.current_tenant_id());
grant select, insert, update on gba.supply_work_order_issues to gba_runtime;
create trigger supply_work_order_issues_require_module before insert on gba.supply_work_order_issues
    for each row execute function gba.require_enabled_module('supply');

alter table gba.supply_work_order_returns enable row level security;
alter table gba.supply_work_order_returns force row level security;
create policy supply_work_order_returns_tenant_isolation on gba.supply_work_order_returns
    using (tenant_id = gba.current_tenant_id()) with check (tenant_id = gba.current_tenant_id());
grant select, insert on gba.supply_work_order_returns to gba_runtime;
create trigger supply_work_order_returns_require_module before insert on gba.supply_work_order_returns
    for each row execute function gba.require_enabled_module('supply');

alter table gba.supply_work_order_qc enable row level security;
alter table gba.supply_work_order_qc force row level security;
create policy supply_work_order_qc_tenant_isolation on gba.supply_work_order_qc
    using (tenant_id = gba.current_tenant_id()) with check (tenant_id = gba.current_tenant_id());
grant select, insert on gba.supply_work_order_qc to gba_runtime;
create trigger supply_work_order_qc_require_module before insert on gba.supply_work_order_qc
    for each row execute function gba.require_enabled_module('supply');

alter table gba.supply_work_order_outputs enable row level security;
alter table gba.supply_work_order_outputs force row level security;
create policy supply_work_order_outputs_tenant_isolation on gba.supply_work_order_outputs
    using (tenant_id = gba.current_tenant_id()) with check (tenant_id = gba.current_tenant_id());
grant select, insert on gba.supply_work_order_outputs to gba_runtime;
create trigger supply_work_order_outputs_require_module before insert on gba.supply_work_order_outputs
    for each row execute function gba.require_enabled_module('supply');

-- Supply manufacturing branch scope:
create policy supply_boms_location_scope on gba.supply_boms as restrictive to gba_runtime
    using (gba.current_location_id() is null or location_id = gba.current_location_id())
    with check (gba.current_location_id() is null or location_id = gba.current_location_id());

create policy supply_bom_components_location_scope on gba.supply_bom_components as restrictive to gba_runtime
    using (gba.current_location_id() is null or location_id = gba.current_location_id())
    with check (gba.current_location_id() is null or location_id = gba.current_location_id());

create policy supply_work_orders_location_scope on gba.supply_work_orders as restrictive to gba_runtime
    using (gba.current_location_id() is null or location_id = gba.current_location_id())
    with check (gba.current_location_id() is null or location_id = gba.current_location_id());

create policy supply_work_order_issues_location_scope on gba.supply_work_order_issues as restrictive to gba_runtime
    using (gba.current_location_id() is null or location_id = gba.current_location_id())
    with check (gba.current_location_id() is null or location_id = gba.current_location_id());

create policy supply_work_order_returns_location_scope on gba.supply_work_order_returns as restrictive to gba_runtime
    using (gba.current_location_id() is null or location_id = gba.current_location_id())
    with check (gba.current_location_id() is null or location_id = gba.current_location_id());

create policy supply_work_order_qc_location_scope on gba.supply_work_order_qc as restrictive to gba_runtime
    using (gba.current_location_id() is null or location_id = gba.current_location_id())
    with check (gba.current_location_id() is null or location_id = gba.current_location_id());

create policy supply_work_order_outputs_location_scope on gba.supply_work_order_outputs as restrictive to gba_runtime
    using (gba.current_location_id() is null or location_id = gba.current_location_id())
    with check (gba.current_location_id() is null or location_id = gba.current_location_id());
