-- REST-01 Slice 2 (ADR-0037): versioned menu items, modifiers and recipe ingredient BOMs.
-- Invoker rights only.

create table gba.restaurant_menu_items (
    tenant_id uuid not null,
    id uuid not null,
    location_id uuid not null,
    code text not null check (code ~ '^[A-Z0-9][A-Z0-9_-]{0,31}$'),
    name text not null check (char_length(btrim(name)) between 1 and 120),
    category text not null check (char_length(btrim(category)) between 1 and 64),
    kitchen_station text not null check (kitchen_station in ('hot', 'cold', 'bar', 'pastry')),
    price_minor bigint not null check (price_minor between 0 and 999999999999),
    currency text not null check (currency ~ '^[A-Z]{3}$'),
    description text check (description is null or char_length(btrim(description)) between 1 and 1000),
    revision integer not null check (revision >= 1),
    is_active boolean not null default true,
    recorded_by uuid not null references gba.users (id),
    recorded_at timestamptz not null default clock_timestamp(),
    primary key (tenant_id, id),
    unique (tenant_id, id, location_id),
    unique (tenant_id, location_id, code),
    foreign key (tenant_id, location_id) references gba.locations (tenant_id, id)
);
create index restaurant_menu_items_location_idx
    on gba.restaurant_menu_items (tenant_id, location_id, category, id);

create table gba.restaurant_menu_item_revisions (
    tenant_id uuid not null,
    menu_item_id uuid not null,
    revision integer not null check (revision >= 1),
    location_id uuid not null,
    code text not null check (code ~ '^[A-Z0-9][A-Z0-9_-]{0,31}$'),
    name text not null check (char_length(btrim(name)) between 1 and 120),
    category text not null check (char_length(btrim(category)) between 1 and 64),
    kitchen_station text not null check (kitchen_station in ('hot', 'cold', 'bar', 'pastry')),
    price_minor bigint not null check (price_minor between 0 and 999999999999),
    currency text not null check (currency ~ '^[A-Z]{3}$'),
    description text check (description is null or char_length(btrim(description)) between 1 and 1000),
    is_active boolean not null,
    recorded_by uuid not null references gba.users (id),
    recorded_at timestamptz not null default clock_timestamp(),
    primary key (tenant_id, menu_item_id, revision),
    unique (tenant_id, menu_item_id, revision, location_id),
    foreign key (tenant_id, menu_item_id, location_id)
        references gba.restaurant_menu_items (tenant_id, id, location_id)
);

create table gba.restaurant_modifier_groups (
    tenant_id uuid not null,
    id uuid not null,
    location_id uuid not null,
    code text not null check (code ~ '^[A-Z0-9][A-Z0-9_-]{0,31}$'),
    name text not null check (char_length(btrim(name)) between 1 and 120),
    min_select integer not null check (min_select between 0 and 50),
    max_select integer not null check (max_select between 1 and 50 and max_select >= min_select),
    currency text not null check (currency ~ '^[A-Z]{3}$'),
    revision integer not null check (revision >= 1),
    is_active boolean not null default true,
    recorded_by uuid not null references gba.users (id),
    recorded_at timestamptz not null default clock_timestamp(),
    primary key (tenant_id, id),
    unique (tenant_id, id, location_id),
    unique (tenant_id, location_id, code),
    foreign key (tenant_id, location_id) references gba.locations (tenant_id, id)
);
create index restaurant_modifier_groups_location_idx
    on gba.restaurant_modifier_groups (tenant_id, location_id, id);

create table gba.restaurant_modifier_options (
    tenant_id uuid not null,
    id uuid not null,
    location_id uuid not null,
    group_id uuid not null,
    code text not null check (code ~ '^[A-Z0-9][A-Z0-9_-]{0,31}$'),
    name text not null check (char_length(btrim(name)) between 1 and 120),
    price_delta_minor bigint not null check (price_delta_minor between -999999999999 and 999999999999),
    sort_order integer not null default 0 check (sort_order between 0 and 10000),
    stock_item_id uuid,
    stock_quantity bigint,
    revision integer not null check (revision >= 1),
    is_active boolean not null default true,
    recorded_by uuid not null references gba.users (id),
    recorded_at timestamptz not null default clock_timestamp(),
    primary key (tenant_id, id),
    unique (tenant_id, id, location_id, group_id),
    unique (tenant_id, group_id, code),
    foreign key (tenant_id, group_id, location_id)
        references gba.restaurant_modifier_groups (tenant_id, id, location_id),
    constraint restaurant_modifier_options_stock_fk
        foreign key (tenant_id, stock_item_id) references gba.stock_items (tenant_id, id),
    check ((stock_item_id is null and stock_quantity is null)
        or (stock_item_id is not null and stock_quantity between 1 and 999999999999))
);
create index restaurant_modifier_options_group_idx
    on gba.restaurant_modifier_options (tenant_id, group_id, sort_order, id);

create table gba.restaurant_menu_item_modifier_groups (
    tenant_id uuid not null,
    menu_item_id uuid not null,
    group_id uuid not null,
    location_id uuid not null,
    sort_order integer not null default 0 check (sort_order between 0 and 10000),
    recorded_by uuid not null references gba.users (id),
    recorded_at timestamptz not null default clock_timestamp(),
    primary key (tenant_id, menu_item_id, group_id),
    foreign key (tenant_id, menu_item_id, location_id)
        references gba.restaurant_menu_items (tenant_id, id, location_id),
    foreign key (tenant_id, group_id, location_id)
        references gba.restaurant_modifier_groups (tenant_id, id, location_id)
);
create index restaurant_menu_item_mod_groups_group_idx
    on gba.restaurant_menu_item_modifier_groups (tenant_id, group_id, menu_item_id);

create table gba.restaurant_recipes (
    tenant_id uuid not null,
    menu_item_id uuid not null,
    revision integer not null check (revision >= 1),
    location_id uuid not null,
    note text check (note is null or char_length(btrim(note)) between 1 and 1000),
    line_count smallint not null check (line_count between 1 and 100),
    recorded_by uuid not null references gba.users (id),
    recorded_at timestamptz not null default clock_timestamp(),
    creation_xid xid8 not null default pg_current_xact_id(),
    primary key (tenant_id, menu_item_id, revision),
    unique (tenant_id, menu_item_id, revision, location_id),
    foreign key (tenant_id, menu_item_id, location_id)
        references gba.restaurant_menu_items (tenant_id, id, location_id)
);

create table gba.restaurant_recipe_lines (
    tenant_id uuid not null,
    menu_item_id uuid not null,
    revision integer not null check (revision >= 1),
    line_no smallint not null check (line_no between 1 and 100),
    location_id uuid not null,
    stock_item_id uuid not null,
    quantity bigint not null check (quantity between 1 and 999999999999),
    note text check (note is null or char_length(btrim(note)) between 1 and 200),
    primary key (tenant_id, menu_item_id, revision, line_no),
    unique (tenant_id, menu_item_id, revision, stock_item_id),
    foreign key (tenant_id, menu_item_id, revision, location_id)
        references gba.restaurant_recipes (tenant_id, menu_item_id, revision, location_id),
    constraint restaurant_recipe_lines_stock_fk
        foreign key (tenant_id, stock_item_id) references gba.stock_items (tenant_id, id)
);
create index restaurant_recipe_lines_stock_idx
    on gba.restaurant_recipe_lines (tenant_id, stock_item_id, menu_item_id);

create function gba.guard_restaurant_menu_item() returns trigger language plpgsql as $$
begin
    if tg_op = 'DELETE' then
        raise exception using errcode = '23514', message = 'restaurant menu items are kept';
    end if;
    if tg_op = 'INSERT' then
        if new.revision <> 1 then
            raise exception using errcode = '23514',
                message = 'a new menu item starts at revision 1';
        end if;
        return new;
    end if;
    if (old.tenant_id, old.id, old.location_id, old.code)
       is distinct from (new.tenant_id, new.id, new.location_id, new.code) then
        raise exception using errcode = '23514',
            message = 'a restaurant menu item keeps its branch and code';
    end if;
    if new.revision <> old.revision + 1 then
        raise exception using errcode = '23514',
            message = 'restaurant menu item revision increments by one';
    end if;
    if new.currency <> old.currency and exists (
        select 1
        from gba.restaurant_menu_item_modifier_groups l
        join gba.restaurant_modifier_groups g
          on g.tenant_id = l.tenant_id and g.id = l.group_id
        where l.tenant_id = new.tenant_id and l.menu_item_id = new.id
          and g.currency <> new.currency
    ) then
        raise exception using errcode = '23514',
            message = 'menu item currency must match attached modifier groups';
    end if;
    return new;
end;
$$;
revoke all on function gba.guard_restaurant_menu_item() from public;
create trigger restaurant_menu_items_guard
    before insert or update or delete on gba.restaurant_menu_items
    for each row execute function gba.guard_restaurant_menu_item();

create function gba.record_restaurant_menu_item_revision() returns trigger language plpgsql as $$
begin
    insert into gba.restaurant_menu_item_revisions (
        tenant_id, menu_item_id, revision, location_id, code, name, category,
        kitchen_station, price_minor, currency, description, is_active,
        recorded_by, recorded_at
    ) values (
        new.tenant_id, new.id, new.revision, new.location_id, new.code, new.name, new.category,
        new.kitchen_station, new.price_minor, new.currency, new.description, new.is_active,
        new.recorded_by, new.recorded_at
    );
    return null;
end;
$$;
revoke all on function gba.record_restaurant_menu_item_revision() from public;
create trigger restaurant_menu_items_record_revision
    after insert or update on gba.restaurant_menu_items
    for each row execute function gba.record_restaurant_menu_item_revision();

create function gba.guard_restaurant_menu_item_revision() returns trigger language plpgsql as $$
begin
    raise exception using errcode = '23514',
        message = 'restaurant menu item revisions are immutable';
end;
$$;
revoke all on function gba.guard_restaurant_menu_item_revision() from public;
create trigger restaurant_menu_item_revisions_immutable
    before update or delete on gba.restaurant_menu_item_revisions
    for each row execute function gba.guard_restaurant_menu_item_revision();

create function gba.guard_restaurant_modifier_group() returns trigger language plpgsql as $$
begin
    if tg_op = 'DELETE' then
        raise exception using errcode = '23514', message = 'restaurant modifier groups are kept';
    end if;
    if tg_op = 'INSERT' then
        if new.revision <> 1 then
            raise exception using errcode = '23514',
                message = 'a new modifier group starts at revision 1';
        end if;
        return new;
    end if;
    if (old.tenant_id, old.id, old.location_id, old.code)
       is distinct from (new.tenant_id, new.id, new.location_id, new.code) then
        raise exception using errcode = '23514',
            message = 'a restaurant modifier group keeps its branch and code';
    end if;
    if new.revision <> old.revision + 1 then
        raise exception using errcode = '23514',
            message = 'restaurant modifier group revision increments by one';
    end if;
    if new.currency <> old.currency and exists (
        select 1
        from gba.restaurant_menu_item_modifier_groups l
        join gba.restaurant_menu_items m
          on m.tenant_id = l.tenant_id and m.id = l.menu_item_id
        where l.tenant_id = new.tenant_id and l.group_id = new.id
          and m.currency <> new.currency
    ) then
        raise exception using errcode = '23514',
            message = 'modifier group currency must match attached menu items';
    end if;
    return new;
end;
$$;
revoke all on function gba.guard_restaurant_modifier_group() from public;
create trigger restaurant_modifier_groups_guard
    before insert or update or delete on gba.restaurant_modifier_groups
    for each row execute function gba.guard_restaurant_modifier_group();

create function gba.guard_restaurant_modifier_option() returns trigger language plpgsql as $$
declare
    is_archived boolean;
begin
    if tg_op = 'DELETE' then
        raise exception using errcode = '23514', message = 'restaurant modifier options are kept';
    end if;
    if tg_op = 'INSERT' then
        if new.revision <> 1 then
            raise exception using errcode = '23514',
                message = 'a new modifier option starts at revision 1';
        end if;
    else
        if (old.tenant_id, old.id, old.location_id, old.group_id, old.code)
           is distinct from (new.tenant_id, new.id, new.location_id, new.group_id, new.code) then
            raise exception using errcode = '23514',
                message = 'a modifier option keeps its branch, group and code';
        end if;
        if new.revision <> old.revision + 1 then
            raise exception using errcode = '23514',
                message = 'restaurant modifier option revision increments by one';
        end if;
    end if;
    if new.stock_item_id is not null and (
        tg_op = 'INSERT'
        or new.stock_item_id is distinct from old.stock_item_id
        or (new.is_active and not old.is_active)
    ) then
        if exists (
            select 1 from gba.stock_items s
            where s.tenant_id = new.tenant_id and s.id = new.stock_item_id
        ) then
            select v.archived into is_archived
            from gba.stock_item_versions v
            where v.tenant_id = new.tenant_id and v.item_id = new.stock_item_id
            order by v.revision desc
            limit 1;
            if is_archived is null or is_archived then
                raise exception using errcode = '23514',
                    message = 'modifier option ingredient must be an active inventory material';
            end if;
        end if;
    end if;
    return new;
end;
$$;
revoke all on function gba.guard_restaurant_modifier_option() from public;
create trigger restaurant_modifier_options_guard
    before insert or update or delete on gba.restaurant_modifier_options
    for each row execute function gba.guard_restaurant_modifier_option();

create function gba.guard_restaurant_menu_item_modifier_group() returns trigger language plpgsql as $$
declare
    item_currency text;
    grp record;
begin
    select currency into strict item_currency
    from gba.restaurant_menu_items
    where tenant_id = new.tenant_id and id = new.menu_item_id and location_id = new.location_id
    for share;

    select currency, is_active into strict grp
    from gba.restaurant_modifier_groups
    where tenant_id = new.tenant_id and id = new.group_id and location_id = new.location_id
    for share;

    if tg_op = 'INSERT' and not grp.is_active then
        raise exception using errcode = '23514',
            message = 'cannot attach an inactive modifier group';
    end if;
    if item_currency <> grp.currency then
        raise exception using errcode = '23514',
            message = 'modifier group currency must match menu item currency';
    end if;
    return new;
end;
$$;
revoke all on function gba.guard_restaurant_menu_item_modifier_group() from public;
create trigger restaurant_menu_item_modifier_groups_guard
    before insert or update on gba.restaurant_menu_item_modifier_groups
    for each row execute function gba.guard_restaurant_menu_item_modifier_group();

create function gba.guard_restaurant_recipe() returns trigger language plpgsql as $$
declare
    latest integer;
begin
    if tg_op <> 'INSERT' then
        raise exception using errcode = '23514', message = 'restaurant recipes are immutable';
    end if;
    perform 1 from gba.restaurant_menu_items m
    where m.tenant_id = new.tenant_id and m.id = new.menu_item_id
      and m.location_id = new.location_id
    for update;
    select coalesce(max(r.revision), 0) into latest
    from gba.restaurant_recipes r
    where r.tenant_id = new.tenant_id and r.menu_item_id = new.menu_item_id;
    if new.revision <> latest + 1 then
        raise exception using errcode = 'GBS01', message = 'stale recipe revision';
    end if;
    return new;
end;
$$;
revoke all on function gba.guard_restaurant_recipe() from public;
create trigger restaurant_recipes_guard
    before insert or update or delete on gba.restaurant_recipes
    for each row execute function gba.guard_restaurant_recipe();

create function gba.guard_restaurant_recipe_line() returns trigger language plpgsql as $$
declare
    is_archived boolean;
begin
    if tg_op <> 'INSERT' then
        raise exception using errcode = '23514', message = 'restaurant recipe lines are immutable';
    end if;
    perform 1 from gba.restaurant_recipes r
    where r.tenant_id = new.tenant_id and r.menu_item_id = new.menu_item_id
      and r.revision = new.revision and r.location_id = new.location_id
      and new.line_no <= r.line_count
      and r.creation_xid = pg_current_xact_id();
    if not found then
        raise exception using errcode = '23514',
            message = 'recipe lines are written with their recipe revision';
    end if;
    if exists (
        select 1 from gba.stock_items s
        where s.tenant_id = new.tenant_id and s.id = new.stock_item_id
    ) then
        select v.archived into is_archived
        from gba.stock_item_versions v
        where v.tenant_id = new.tenant_id and v.item_id = new.stock_item_id
        order by v.revision desc
        limit 1;
        if is_archived is null or is_archived then
            raise exception using errcode = '23514',
                message = 'recipe ingredient must be an active inventory material';
        end if;
    end if;
    return new;
end;
$$;
revoke all on function gba.guard_restaurant_recipe_line() from public;
create trigger restaurant_recipe_lines_guard
    before insert or update or delete on gba.restaurant_recipe_lines
    for each row execute function gba.guard_restaurant_recipe_line();

create function gba.check_restaurant_recipe_lines() returns trigger language plpgsql as $$
begin
    if (
        select count(*) <> new.line_count or min(l.line_no) <> 1 or max(l.line_no) <> new.line_count
        from gba.restaurant_recipe_lines l
        where l.tenant_id = new.tenant_id
          and l.menu_item_id = new.menu_item_id
          and l.revision = new.revision
    ) is not false then
        raise exception using errcode = '23514',
            message = 'a restaurant recipe keeps its numbered ingredient lines';
    end if;
    return null;
end;
$$;
revoke all on function gba.check_restaurant_recipe_lines() from public;
create constraint trigger restaurant_recipes_lines_complete
    after insert on gba.restaurant_recipes
    deferrable initially deferred for each row
    execute function gba.check_restaurant_recipe_lines();

-- RLS, module write gates and minimal runtime privileges
alter table gba.restaurant_menu_items enable row level security;
alter table gba.restaurant_menu_items force row level security;
create policy restaurant_menu_items_tenant_isolation on gba.restaurant_menu_items
    using (tenant_id = gba.current_tenant_id()) with check (tenant_id = gba.current_tenant_id());
grant select, insert, update on gba.restaurant_menu_items to gba_runtime;
create trigger restaurant_menu_items_require_module before insert on gba.restaurant_menu_items
    for each row execute function gba.require_enabled_module('restaurant');

alter table gba.restaurant_menu_item_revisions enable row level security;
alter table gba.restaurant_menu_item_revisions force row level security;
create policy restaurant_menu_item_revisions_tenant_isolation on gba.restaurant_menu_item_revisions
    using (tenant_id = gba.current_tenant_id()) with check (tenant_id = gba.current_tenant_id());
grant select, insert on gba.restaurant_menu_item_revisions to gba_runtime;

alter table gba.restaurant_modifier_groups enable row level security;
alter table gba.restaurant_modifier_groups force row level security;
create policy restaurant_modifier_groups_tenant_isolation on gba.restaurant_modifier_groups
    using (tenant_id = gba.current_tenant_id()) with check (tenant_id = gba.current_tenant_id());
grant select, insert, update on gba.restaurant_modifier_groups to gba_runtime;
create trigger restaurant_modifier_groups_require_module before insert on gba.restaurant_modifier_groups
    for each row execute function gba.require_enabled_module('restaurant');

alter table gba.restaurant_modifier_options enable row level security;
alter table gba.restaurant_modifier_options force row level security;
create policy restaurant_modifier_options_tenant_isolation on gba.restaurant_modifier_options
    using (tenant_id = gba.current_tenant_id()) with check (tenant_id = gba.current_tenant_id());
grant select, insert, update on gba.restaurant_modifier_options to gba_runtime;
create trigger restaurant_modifier_options_require_module before insert on gba.restaurant_modifier_options
    for each row execute function gba.require_enabled_module('restaurant');

alter table gba.restaurant_menu_item_modifier_groups enable row level security;
alter table gba.restaurant_menu_item_modifier_groups force row level security;
create policy restaurant_menu_item_modifier_groups_tenant_isolation
    on gba.restaurant_menu_item_modifier_groups
    using (tenant_id = gba.current_tenant_id()) with check (tenant_id = gba.current_tenant_id());
grant select, insert, update, delete on gba.restaurant_menu_item_modifier_groups to gba_runtime;
create trigger restaurant_menu_item_modifier_groups_require_module
    before insert on gba.restaurant_menu_item_modifier_groups
    for each row execute function gba.require_enabled_module('restaurant');

alter table gba.restaurant_recipes enable row level security;
alter table gba.restaurant_recipes force row level security;
create policy restaurant_recipes_tenant_isolation on gba.restaurant_recipes
    using (tenant_id = gba.current_tenant_id()) with check (tenant_id = gba.current_tenant_id());
grant select, insert on gba.restaurant_recipes to gba_runtime;
create trigger restaurant_recipes_require_module before insert on gba.restaurant_recipes
    for each row execute function gba.require_enabled_module('restaurant');

alter table gba.restaurant_recipe_lines enable row level security;
alter table gba.restaurant_recipe_lines force row level security;
create policy restaurant_recipe_lines_tenant_isolation on gba.restaurant_recipe_lines
    using (tenant_id = gba.current_tenant_id()) with check (tenant_id = gba.current_tenant_id());
grant select, insert on gba.restaurant_recipe_lines to gba_runtime;

-- Restaurant menu branch scope:
create policy restaurant_menu_items_location_scope on gba.restaurant_menu_items as restrictive to gba_runtime
    using (gba.current_location_id() is null or location_id = gba.current_location_id())
    with check (gba.current_location_id() is null or location_id = gba.current_location_id());

create policy restaurant_menu_item_revisions_location_scope on gba.restaurant_menu_item_revisions as restrictive to gba_runtime
    using (gba.current_location_id() is null or location_id = gba.current_location_id())
    with check (gba.current_location_id() is null or location_id = gba.current_location_id());

create policy restaurant_modifier_groups_location_scope on gba.restaurant_modifier_groups as restrictive to gba_runtime
    using (gba.current_location_id() is null or location_id = gba.current_location_id())
    with check (gba.current_location_id() is null or location_id = gba.current_location_id());

create policy restaurant_modifier_options_location_scope on gba.restaurant_modifier_options as restrictive to gba_runtime
    using (gba.current_location_id() is null or location_id = gba.current_location_id())
    with check (gba.current_location_id() is null or location_id = gba.current_location_id());

create policy restaurant_menu_item_modifier_groups_location_scope on gba.restaurant_menu_item_modifier_groups as restrictive to gba_runtime
    using (gba.current_location_id() is null or location_id = gba.current_location_id())
    with check (gba.current_location_id() is null or location_id = gba.current_location_id());

create policy restaurant_recipes_location_scope on gba.restaurant_recipes as restrictive to gba_runtime
    using (gba.current_location_id() is null or location_id = gba.current_location_id())
    with check (gba.current_location_id() is null or location_id = gba.current_location_id());

create policy restaurant_recipe_lines_location_scope on gba.restaurant_recipe_lines as restrictive to gba_runtime
    using (gba.current_location_id() is null or location_id = gba.current_location_id())
    with check (gba.current_location_id() is null or location_id = gba.current_location_id());
