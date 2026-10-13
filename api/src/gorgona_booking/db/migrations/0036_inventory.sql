-- J1 / ADR-0026: the material list and the storage places of the inventory module.
-- Forward only. No stock, amounts, ledger change or readiness promotion.
-- The unit and the quantity scale live in the immutable head row: they never change.
create table gba.stock_items (
    tenant_id uuid not null references gba.tenants(id),
    id uuid not null,
    code text not null constraint stock_items_code_check check (code ~ '^[A-Z0-9][A-Z0-9_-]{0,63}$'),
    unit text not null constraint stock_items_unit_check
        check (length(unit) between 1 and 16 and unit = btrim(unit) and unit !~ '[[:cntrl:]]'),
    quantity_scale integer not null constraint stock_items_scale_check
        check (quantity_scale between 0 and 3),
    created_at timestamptz not null default now(),
    primary key (tenant_id, id),
    unique (tenant_id, code)
);
create table gba.stock_item_versions (
    tenant_id uuid not null references gba.tenants(id),
    item_id uuid not null,
    revision integer not null constraint stock_item_versions_revision_check check (revision > 0),
    name text not null constraint stock_item_versions_name_check
        check (length(btrim(name)) between 1 and 200 and name !~ '[[:cntrl:]]'),
    archived boolean not null,
    created_by uuid not null references gba.users(id),
    created_at timestamptz not null default now(),
    primary key (tenant_id, item_id, revision),
    foreign key (tenant_id, item_id) references gba.stock_items(tenant_id, id)
);
-- A storage place belongs to one branch for good; its code is unique inside that branch.
create table gba.stock_places (
    tenant_id uuid not null references gba.tenants(id),
    id uuid not null,
    location_id uuid not null,
    code text not null constraint stock_places_code_check check (code ~ '^[A-Z0-9][A-Z0-9_-]{0,63}$'),
    created_at timestamptz not null default now(),
    primary key (tenant_id, id),
    unique (tenant_id, location_id, code),
    foreign key (tenant_id, location_id) references gba.locations(tenant_id, id)
);
create table gba.stock_place_versions (
    tenant_id uuid not null references gba.tenants(id),
    place_id uuid not null,
    revision integer not null constraint stock_place_versions_revision_check check (revision > 0),
    name text not null constraint stock_place_versions_name_check
        check (length(btrim(name)) between 1 and 200 and name !~ '[[:cntrl:]]'),
    archived boolean not null,
    created_by uuid not null references gba.users(id),
    created_at timestamptz not null default now(),
    primary key (tenant_id, place_id, revision),
    foreign key (tenant_id, place_id) references gba.stock_places(tenant_id, id)
);

-- The author of a material version is the authenticated owner or manager of the whole
-- company. Versions of one material are ordered by its row lock; the next is latest plus one.
create function gba.guard_stock_item_version() returns trigger language plpgsql as $$
declare latest integer;
begin
    perform 1 from gba.memberships m join gba.users u on u.id=m.user_id
     where m.tenant_id=new.tenant_id and m.user_id=new.created_by and m.status='active' and u.status='active'
       and m.role in ('owner','manager') and m.location_id is null
     for share of m;
    if not found or new.created_by is distinct from gba.current_user_id() then
        raise exception using errcode='42501', message='a material needs its authenticated company-wide owner or manager';
    end if;
    perform 1 from gba.stock_items where tenant_id=new.tenant_id and id=new.item_id for update;
    select coalesce(max(revision),0) into latest from gba.stock_item_versions
     where tenant_id=new.tenant_id and item_id=new.item_id;
    if new.revision <> latest+1 then
        raise exception using errcode='GBS01', message='stale material revision';
    end if;
    return new;
end;
$$;
-- The author of a storage place version is the authenticated owner or manager whose
-- membership covers the branch of the place.
create function gba.guard_stock_place_version() returns trigger language plpgsql as $$
declare latest integer; branch uuid;
begin
    select location_id into branch from gba.stock_places
     where tenant_id=new.tenant_id and id=new.place_id for update;
    perform 1 from gba.memberships m join gba.users u on u.id=m.user_id
     where m.tenant_id=new.tenant_id and m.user_id=new.created_by and m.status='active' and u.status='active'
       and m.role in ('owner','manager') and (m.location_id is null or m.location_id=branch)
     for share of m;
    if not found or new.created_by is distinct from gba.current_user_id() then
        raise exception using errcode='42501', message='a storage place needs its authenticated owner or manager';
    end if;
    select coalesce(max(revision),0) into latest from gba.stock_place_versions
     where tenant_id=new.tenant_id and place_id=new.place_id;
    if new.revision <> latest+1 then
        raise exception using errcode='GBS01', message='stale storage place revision';
    end if;
    return new;
end;
$$;
create function gba.check_stock_head() returns trigger language plpgsql as $$
begin
    if (tg_table_name='stock_items' and not exists (
        select 1 from gba.stock_item_versions where tenant_id=new.tenant_id and item_id=new.id
    )) or (tg_table_name='stock_places' and not exists (
        select 1 from gba.stock_place_versions where tenant_id=new.tenant_id and place_id=new.id
    )) then
        raise exception using errcode='23514', message='a stock head requires its first version';
    end if;
    return null;
end;
$$;
revoke all on function gba.guard_stock_item_version() from public;
revoke all on function gba.guard_stock_place_version() from public;
revoke all on function gba.check_stock_head() from public;
create trigger stock_item_versions_guard before insert on gba.stock_item_versions
    for each row execute function gba.guard_stock_item_version();
create trigger stock_place_versions_guard before insert on gba.stock_place_versions
    for each row execute function gba.guard_stock_place_version();
create constraint trigger stock_items_version_required after insert on gba.stock_items
    deferrable initially deferred for each row execute function gba.check_stock_head();
create constraint trigger stock_places_version_required after insert on gba.stock_places
    deferrable initially deferred for each row execute function gba.check_stock_head();

-- Grants, tenant/location policies and immutable/module guards are declared below.
-- PostgreSQL row-lock commands need column UPDATE rights. Immutability triggers
-- still reject every actual mutation, including an UPDATE that keeps the same id.
grant update (id) on gba.stock_items, gba.stock_places to gba_runtime;

alter table gba.stock_items enable row level security;
alter table gba.stock_items force row level security;
create policy stock_items_tenant_isolation on gba.stock_items
    using (tenant_id=gba.current_tenant_id()) with check (tenant_id=gba.current_tenant_id());
create policy stock_items_location_scope on gba.stock_items as restrictive to gba_runtime
    using (true) with check (gba.current_location_id() is null);
grant select on gba.stock_items to gba_runtime;
grant insert (tenant_id,id,code,unit,quantity_scale) on gba.stock_items to gba_runtime;
create trigger stock_items_immutable before update or delete on gba.stock_items
    for each row execute function gba.reject_counterparty_mutation();
create trigger stock_items_require_inventory before insert on gba.stock_items
    for each row execute function gba.require_enabled_module('inventory');

alter table gba.stock_item_versions enable row level security;
alter table gba.stock_item_versions force row level security;
create policy stock_item_versions_tenant_isolation on gba.stock_item_versions
    using (tenant_id=gba.current_tenant_id()) with check (tenant_id=gba.current_tenant_id());
create policy stock_item_versions_location_scope on gba.stock_item_versions as restrictive to gba_runtime
    using (true) with check (gba.current_location_id() is null);
grant select on gba.stock_item_versions to gba_runtime;
grant insert (tenant_id,item_id,revision,name,archived,created_by) on gba.stock_item_versions to gba_runtime;
create trigger stock_item_versions_immutable before update or delete on gba.stock_item_versions
    for each row execute function gba.reject_counterparty_mutation();
create trigger stock_item_versions_require_inventory before insert on gba.stock_item_versions
    for each row execute function gba.require_enabled_module('inventory');

alter table gba.stock_places enable row level security;
alter table gba.stock_places force row level security;
create policy stock_places_tenant_isolation on gba.stock_places
    using (tenant_id=gba.current_tenant_id()) with check (tenant_id=gba.current_tenant_id());
create policy stock_places_location_scope on gba.stock_places as restrictive to gba_runtime
    using (gba.current_location_id() is null or location_id=gba.current_location_id())
    with check (gba.current_location_id() is null or location_id=gba.current_location_id());
grant select on gba.stock_places to gba_runtime;
grant insert (tenant_id,id,location_id,code) on gba.stock_places to gba_runtime;
create trigger stock_places_immutable before update or delete on gba.stock_places
    for each row execute function gba.reject_counterparty_mutation();
create trigger stock_places_require_inventory before insert on gba.stock_places
    for each row execute function gba.require_enabled_module('inventory');

alter table gba.stock_place_versions enable row level security;
alter table gba.stock_place_versions force row level security;
create policy stock_place_versions_tenant_isolation on gba.stock_place_versions
    using (tenant_id=gba.current_tenant_id()) with check (tenant_id=gba.current_tenant_id());
create policy stock_place_versions_location_scope on gba.stock_place_versions as restrictive to gba_runtime
    using ((gba.current_location_id() is null or exists (select 1 from gba.stock_places p where p.tenant_id=stock_place_versions.tenant_id and p.id=stock_place_versions.place_id and p.location_id=gba.current_location_id())))
    with check ((gba.current_location_id() is null or exists (select 1 from gba.stock_places p where p.tenant_id=stock_place_versions.tenant_id and p.id=stock_place_versions.place_id and p.location_id=gba.current_location_id())));
grant select on gba.stock_place_versions to gba_runtime;
grant insert (tenant_id,place_id,revision,name,archived,created_by) on gba.stock_place_versions to gba_runtime;
create trigger stock_place_versions_immutable before update or delete on gba.stock_place_versions
    for each row execute function gba.reject_counterparty_mutation();
create trigger stock_place_versions_require_inventory before insert on gba.stock_place_versions
    for each row execute function gba.require_enabled_module('inventory');
