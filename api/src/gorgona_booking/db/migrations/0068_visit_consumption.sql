-- L3 (package L, BEAUTY-01): recipes, visit completion and material consumption.
-- Design docs/plan/PACKAGE_L3_DESIGN_2026-10-22.md. A recipe lists the materials one variant or
-- one add-on uses, in the material's smallest unit like stock. A completion is a permanent fact
-- of a started confirmed booking (the booking stays CONFIRMED); its material uses keep the planned
-- and the actual quantity; the consumption is posted once as a STOCK-01 write-off.

create table gba.variant_materials (
    tenant_id uuid not null references gba.tenants(id),
    variant_id uuid not null,
    position smallint not null constraint variant_materials_position_check
        check (position between 1 and 20),
    item_id uuid not null,
    quantity bigint not null constraint variant_materials_quantity_check
        check (quantity between 1 and 999999999999),
    primary key (tenant_id, variant_id, position),
    unique (tenant_id, variant_id, item_id),
    foreign key (tenant_id, variant_id) references gba.service_variants (tenant_id, id),
    foreign key (tenant_id, item_id) references gba.stock_items (tenant_id, id)
);
create table gba.add_on_materials (
    tenant_id uuid not null references gba.tenants(id),
    add_on_id uuid not null,
    position smallint not null constraint add_on_materials_position_check
        check (position between 1 and 20),
    item_id uuid not null,
    quantity bigint not null constraint add_on_materials_quantity_check
        check (quantity between 1 and 999999999999),
    primary key (tenant_id, add_on_id, position),
    unique (tenant_id, add_on_id, item_id),
    foreign key (tenant_id, add_on_id) references gba.add_ons (tenant_id, id),
    foreign key (tenant_id, item_id) references gba.stock_items (tenant_id, id)
);

create table gba.visit_completions (
    tenant_id uuid not null references gba.tenants(id),
    booking_id uuid not null,
    location_id uuid not null,
    completed_at timestamptz not null default now(),
    completed_by uuid not null references gba.users(id),
    -- Set once by posting the consumption; a visit with nothing to write off keeps it empty.
    stock_document_id uuid,
    consumption_posted_at timestamptz,
    primary key (tenant_id, booking_id),
    foreign key (tenant_id, booking_id) references gba.bookings (tenant_id, id),
    foreign key (tenant_id, location_id) references gba.locations (tenant_id, id),
    foreign key (tenant_id, stock_document_id) references gba.stock_documents (tenant_id, id),
    constraint visit_completions_document_posted_check
        check (stock_document_id is null or consumption_posted_at is not null)
);
create table gba.visit_material_uses (
    tenant_id uuid not null references gba.tenants(id),
    booking_id uuid not null,
    item_id uuid not null,
    planned bigint not null constraint visit_material_uses_planned_check
        check (planned between 0 and 999999999999),
    actual bigint not null constraint visit_material_uses_actual_check
        check (actual between 0 and 999999999999),
    primary key (tenant_id, booking_id, item_id),
    foreign key (tenant_id, booking_id) references gba.visit_completions (tenant_id, booking_id),
    foreign key (tenant_id, item_id) references gba.stock_items (tenant_id, id)
);

-- A completion follows a started confirmed booking of its own branch; it never changes except
-- that its consumption is posted once.
create function gba.guard_visit_completion() returns trigger language plpgsql as $$
begin
    if tg_op = 'INSERT' then
        if not exists (
            select 1 from gba.bookings b
            where b.tenant_id = new.tenant_id and b.id = new.booking_id
              and b.status = 'CONFIRMED' and b.starts_at <= pg_catalog.now()
              and b.location_id = new.location_id
        ) or new.completed_at <> pg_catalog.now()
          or new.stock_document_id is not null or new.consumption_posted_at is not null then
            raise exception using errcode = 'check_violation',
                constraint = 'visit_completions_started_check',
                message = 'only a started confirmed booking is completed';
        end if;
        return new;
    end if;
    if old.consumption_posted_at is not null
       or (new.tenant_id, new.booking_id, new.location_id, new.completed_at, new.completed_by)
          is distinct from
          (old.tenant_id, old.booking_id, old.location_id, old.completed_at, old.completed_by)
       or new.consumption_posted_at is distinct from pg_catalog.now() then
        raise exception using errcode = 'check_violation',
            constraint = 'visit_completions_posted_once_check',
            message = 'a completion posts its consumption once';
    end if;
    return new;
end;
$$;
revoke all on function gba.guard_visit_completion() from public;
create trigger visit_completions_guard
    before insert or update on gba.visit_completions
    for each row execute function gba.guard_visit_completion();

-- Material uses are written with their completion, in the same transaction, and never change.
create function gba.guard_visit_material_use() returns trigger language plpgsql as $$
begin
    if not exists (
        select 1 from gba.visit_completions c
        where c.tenant_id = new.tenant_id and c.booking_id = new.booking_id
          and c.completed_at = pg_catalog.now() and c.consumption_posted_at is null
    ) then
        raise exception using errcode = 'check_violation',
            constraint = 'visit_material_uses_with_completion_check',
            message = 'material uses are recorded with their completion';
    end if;
    return new;
end;
$$;
revoke all on function gba.guard_visit_material_use() from public;
create trigger visit_material_uses_guard
    before insert on gba.visit_material_uses
    for each row execute function gba.guard_visit_material_use();

alter table gba.variant_materials enable row level security;
alter table gba.variant_materials force row level security;
alter table gba.add_on_materials enable row level security;
alter table gba.add_on_materials force row level security;
alter table gba.visit_completions enable row level security;
alter table gba.visit_completions force row level security;
alter table gba.visit_material_uses enable row level security;
alter table gba.visit_material_uses force row level security;
do $$
declare table_name text;
begin
    foreach table_name in array array['variant_materials', 'add_on_materials',
                                       'visit_completions', 'visit_material_uses'] loop
        execute format(
            'create policy %I on gba.%I using (tenant_id = gba.current_tenant_id()) '
            'with check (tenant_id = gba.current_tenant_id())',
            table_name || '_tenant_isolation', table_name);
    end loop;
end;
$$;
grant select, insert, delete on gba.variant_materials, gba.add_on_materials to gba_runtime;
grant select, insert on gba.visit_completions, gba.visit_material_uses to gba_runtime;
grant update (stock_document_id, consumption_posted_at) on gba.visit_completions to gba_runtime;

-- Visit branch scope:
create policy visit_completions_location_scope on gba.visit_completions
    as restrictive to gba_runtime
    using (gba.current_location_id() is null or location_id = gba.current_location_id())
    with check (gba.current_location_id() is null or location_id = gba.current_location_id());
create policy visit_material_uses_location_scope on gba.visit_material_uses
    as restrictive to gba_runtime
    using (gba.current_location_id() is null or exists (
        select 1 from gba.visit_completions c
        where c.tenant_id = visit_material_uses.tenant_id
          and c.booking_id = visit_material_uses.booking_id))
    with check (gba.current_location_id() is null or exists (
        select 1 from gba.visit_completions c
        where c.tenant_id = visit_material_uses.tenant_id
          and c.booking_id = visit_material_uses.booking_id));
