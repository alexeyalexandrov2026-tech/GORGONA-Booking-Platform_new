-- REST-01 Slice 3 (ADR-0037): independent guest checks, station-routed kitchen tickets
-- and coordinated STOCK-01 ingredient write-offs. Invoker rights only.

alter table gba.restaurant_tables
    add constraint restaurant_tables_branch_key unique (tenant_id, id, location_id);

create table gba.restaurant_checks (
    tenant_id uuid not null,
    id uuid not null,
    location_id uuid not null,
    service_mode text not null check (service_mode in ('dine_in', 'takeout', 'bar', 'delivery')),
    table_id uuid,
    reservation_id uuid,
    guest_counterparty_id uuid,
    guest_name text check (guest_name is null or char_length(btrim(guest_name)) between 1 and 120),
    currency text not null check (currency ~ '^[A-Z]{3}$'),
    status text not null check (status in ('open', 'closed', 'voided')),
    subtotal_minor bigint not null default 0 check (subtotal_minor between 0 and 999999999999),
    note text check (note is null or char_length(btrim(note)) between 1 and 1000),
    revision integer not null check (revision >= 1),
    opened_by uuid not null references gba.users (id),
    opened_at timestamptz not null default clock_timestamp(),
    closed_by uuid references gba.users (id),
    closed_at timestamptz,
    recorded_by uuid not null references gba.users (id),
    recorded_at timestamptz not null default clock_timestamp(),
    primary key (tenant_id, id),
    unique (tenant_id, id, location_id),
    foreign key (tenant_id, location_id) references gba.locations (tenant_id, id),
    foreign key (tenant_id, table_id, location_id)
        references gba.restaurant_tables (tenant_id, id, location_id),
    foreign key (tenant_id, reservation_id, location_id)
        references gba.restaurant_table_reservations (tenant_id, id, location_id),
    constraint restaurant_checks_guest_fk foreign key (tenant_id, guest_counterparty_id)
        references gba.counterparties (tenant_id, id),
    check (
        (status = 'open' and closed_by is null and closed_at is null)
        or (status in ('closed', 'voided') and closed_by is not null and closed_at is not null)
    )
);
create index restaurant_checks_location_idx
    on gba.restaurant_checks (tenant_id, location_id, status, id);
create index restaurant_checks_table_idx
    on gba.restaurant_checks (tenant_id, table_id, id) where table_id is not null;

create table gba.restaurant_kitchen_tickets (
    tenant_id uuid not null,
    id uuid not null,
    check_id uuid not null,
    location_id uuid not null,
    ticket_no integer not null check (ticket_no >= 1),
    kitchen_station text not null check (kitchen_station in ('hot', 'cold', 'bar', 'pastry')),
    status text not null check (status in ('queued', 'preparing', 'ready', 'served', 'voided')),
    revision integer not null check (revision >= 1),
    fired_by uuid not null references gba.users (id),
    fired_at timestamptz not null default clock_timestamp(),
    recorded_by uuid not null references gba.users (id),
    recorded_at timestamptz not null default clock_timestamp(),
    primary key (tenant_id, id),
    unique (tenant_id, id, location_id),
    unique (tenant_id, id, check_id, location_id),
    unique (tenant_id, check_id, ticket_no),
    foreign key (tenant_id, check_id, location_id)
        references gba.restaurant_checks (tenant_id, id, location_id)
);
create index restaurant_kitchen_tickets_board_idx
    on gba.restaurant_kitchen_tickets (tenant_id, location_id, kitchen_station, status, id);

create table gba.restaurant_kitchen_ticket_events (
    tenant_id uuid not null,
    ticket_id uuid not null,
    revision integer not null check (revision >= 2),
    location_id uuid not null,
    action text not null check (action in ('start', 'mark_ready', 'serve', 'void')),
    note text check (note is null or char_length(btrim(note)) between 1 and 1000),
    recorded_by uuid not null references gba.users (id),
    recorded_at timestamptz not null default clock_timestamp(),
    primary key (tenant_id, ticket_id, revision),
    foreign key (tenant_id, ticket_id, location_id)
        references gba.restaurant_kitchen_tickets (tenant_id, id, location_id)
);

create table gba.restaurant_check_lines (
    tenant_id uuid not null,
    id uuid not null,
    check_id uuid not null,
    location_id uuid not null,
    line_no integer not null check (line_no between 1 and 500),
    menu_item_id uuid not null,
    menu_item_revision integer not null check (menu_item_revision >= 1),
    recipe_revision integer check (recipe_revision is null or recipe_revision >= 1),
    item_code text not null check (item_code ~ '^[A-Z0-9][A-Z0-9_-]{0,31}$'),
    item_name text not null check (char_length(btrim(item_name)) between 1 and 120),
    kitchen_station text not null check (kitchen_station in ('hot', 'cold', 'bar', 'pastry')),
    quantity integer not null check (quantity between 1 and 100),
    base_price_minor bigint not null check (base_price_minor between 0 and 999999999999),
    modifiers_delta_minor bigint not null
        check (modifiers_delta_minor between -999999999999 and 999999999999),
    unit_price_minor bigint not null
        check (unit_price_minor between 0 and 999999999999
               and unit_price_minor = base_price_minor + modifiers_delta_minor),
    line_total_minor bigint not null
        check (line_total_minor between 0 and 999999999999
               and line_total_minor = unit_price_minor * quantity),
    status text not null check (status in ('draft', 'fired', 'served', 'voided')),
    kitchen_ticket_id uuid,
    note text check (note is null or char_length(btrim(note)) between 1 and 500),
    void_reason text check (void_reason is null or char_length(btrim(void_reason)) between 1 and 500),
    recorded_by uuid not null references gba.users (id),
    recorded_at timestamptz not null default clock_timestamp(),
    creation_xid xid8 not null default pg_current_xact_id(),
    primary key (tenant_id, id),
    unique (tenant_id, id, location_id),
    unique (tenant_id, check_id, line_no),
    foreign key (tenant_id, check_id, location_id)
        references gba.restaurant_checks (tenant_id, id, location_id),
    foreign key (tenant_id, menu_item_id, menu_item_revision, location_id)
        references gba.restaurant_menu_item_revisions (tenant_id, menu_item_id, revision, location_id),
    foreign key (tenant_id, menu_item_id, recipe_revision, location_id)
        references gba.restaurant_recipes (tenant_id, menu_item_id, revision, location_id),
    foreign key (tenant_id, kitchen_ticket_id, check_id, location_id)
        references gba.restaurant_kitchen_tickets (tenant_id, id, check_id, location_id),
    check (
        (status = 'draft' and kitchen_ticket_id is null and void_reason is null)
        or (status in ('fired', 'served') and kitchen_ticket_id is not null and void_reason is null)
        or (status = 'voided' and void_reason is not null)
    )
);
create index restaurant_check_lines_check_idx
    on gba.restaurant_check_lines (tenant_id, check_id, line_no);
create index restaurant_check_lines_ticket_idx
    on gba.restaurant_check_lines (tenant_id, kitchen_ticket_id, line_no)
    where kitchen_ticket_id is not null;

create table gba.restaurant_check_line_modifiers (
    tenant_id uuid not null,
    check_line_id uuid not null,
    modifier_no smallint not null check (modifier_no between 1 and 100),
    location_id uuid not null,
    group_id uuid not null,
    option_id uuid not null,
    group_name text not null check (char_length(btrim(group_name)) between 1 and 120),
    option_code text not null check (option_code ~ '^[A-Z0-9][A-Z0-9_-]{0,31}$'),
    option_name text not null check (char_length(btrim(option_name)) between 1 and 120),
    price_delta_minor bigint not null
        check (price_delta_minor between -999999999999 and 999999999999),
    stock_item_id uuid,
    stock_quantity bigint,
    primary key (tenant_id, check_line_id, modifier_no),
    foreign key (tenant_id, check_line_id, location_id)
        references gba.restaurant_check_lines (tenant_id, id, location_id),
    foreign key (tenant_id, option_id, location_id, group_id)
        references gba.restaurant_modifier_options (tenant_id, id, location_id, group_id),
    foreign key (tenant_id, stock_item_id) references gba.stock_items (tenant_id, id),
    check ((stock_item_id is null and stock_quantity is null)
        or (stock_item_id is not null and stock_quantity between 1 and 999999999999))
);

create table gba.restaurant_check_consumptions (
    tenant_id uuid not null,
    check_id uuid not null,
    location_id uuid not null,
    legal_entity_id uuid not null,
    place_id uuid not null,
    document_date date not null,
    stock_document_id uuid,
    line_count smallint not null check (line_count between 0 and 100),
    posted_by uuid not null references gba.users (id),
    posted_at timestamptz not null default clock_timestamp(),
    creation_xid xid8 not null default pg_current_xact_id(),
    primary key (tenant_id, check_id),
    unique (tenant_id, check_id, location_id),
    foreign key (tenant_id, check_id, location_id)
        references gba.restaurant_checks (tenant_id, id, location_id),
    foreign key (tenant_id, legal_entity_id) references gba.legal_entities (tenant_id, id),
    foreign key (tenant_id, place_id, location_id)
        references gba.stock_places (tenant_id, id, location_id),
    foreign key (tenant_id, stock_document_id) references gba.stock_documents (tenant_id, id),
    check ((line_count = 0 and stock_document_id is null)
        or (line_count > 0 and stock_document_id is not null))
);
create unique index restaurant_check_consumptions_doc_uidx
    on gba.restaurant_check_consumptions (tenant_id, stock_document_id)
    where stock_document_id is not null;

create table gba.restaurant_check_consumption_lines (
    tenant_id uuid not null,
    check_id uuid not null,
    line_no smallint not null check (line_no between 1 and 100),
    location_id uuid not null,
    stock_item_id uuid not null,
    quantity bigint not null check (quantity between 1 and 999999999999),
    primary key (tenant_id, check_id, line_no),
    unique (tenant_id, check_id, stock_item_id),
    foreign key (tenant_id, check_id, location_id)
        references gba.restaurant_check_consumptions (tenant_id, check_id, location_id),
    foreign key (tenant_id, stock_item_id) references gba.stock_items (tenant_id, id)
);

create function gba.guard_restaurant_check() returns trigger language plpgsql as $$
declare
    res_table uuid;
begin
    if tg_op = 'DELETE' then
        raise exception using errcode = '23514', message = 'restaurant checks are kept';
    end if;
    if tg_op = 'INSERT' then
        if new.status <> 'open' or new.revision <> 1 or new.subtotal_minor <> 0 then
            raise exception using errcode = '23514',
                message = 'a new check starts open at revision 1 with zero subtotal';
        end if;
        if new.table_id is not null and new.reservation_id is not null then
            select table_id into strict res_table
            from gba.restaurant_table_reservations
            where tenant_id = new.tenant_id and id = new.reservation_id;
            if res_table <> new.table_id then
                raise exception using errcode = '23514',
                    message = 'reservation does not belong to the specified table';
            end if;
        end if;
        return new;
    end if;
    if (old.tenant_id, old.id, old.location_id, old.service_mode, old.table_id,
        old.reservation_id, old.guest_counterparty_id, old.currency,
        old.opened_by, old.opened_at)
       is distinct from (new.tenant_id, new.id, new.location_id, new.service_mode, new.table_id,
                         new.reservation_id, new.guest_counterparty_id, new.currency,
                         new.opened_by, new.opened_at) then
        raise exception using errcode = '23514',
            message = 'check identity fields are immutable';
    end if;
    if new.revision <> old.revision + 1 then
        raise exception using errcode = '23514',
            message = 'check revision increments by one';
    end if;
    if old.status <> 'open' then
        raise exception using errcode = '23514',
            message = 'closed or voided checks cannot be modified';
    end if;
    if new.status in ('closed', 'voided') then
        if exists (
            select 1 from gba.restaurant_check_lines l
            where l.tenant_id = new.tenant_id and l.check_id = new.id and l.status = 'draft'
        ) then
            raise exception using errcode = '23514',
                message = 'cannot close or void a check with unfired draft lines';
        end if;
        if exists (
            select 1 from gba.restaurant_kitchen_tickets t
            where t.tenant_id = new.tenant_id and t.check_id = new.id
              and t.status in ('queued', 'preparing', 'ready')
        ) then
            raise exception using errcode = '23514',
                message = 'cannot close or void a check with open kitchen tickets';
        end if;
    end if;
    if new.status = 'voided' and exists (
        select 1 from gba.restaurant_check_lines l
        where l.tenant_id = new.tenant_id and l.check_id = new.id and l.status <> 'voided'
    ) then
        raise exception using errcode = '23514',
            message = 'cannot void a check that still has active lines';
    end if;
    return new;
end;
$$;
revoke all on function gba.guard_restaurant_check() from public;
create trigger restaurant_checks_guard
    before insert or update or delete on gba.restaurant_checks
    for each row execute function gba.guard_restaurant_check();

create function gba.guard_restaurant_kitchen_ticket() returns trigger language plpgsql as $$
declare
    chk_status text;
begin
    if tg_op = 'DELETE' then
        raise exception using errcode = '23514', message = 'kitchen tickets are kept';
    end if;
    if tg_op = 'INSERT' then
        if new.status <> 'queued' or new.revision <> 1 then
            raise exception using errcode = '23514',
                message = 'a new kitchen ticket starts queued at revision 1';
        end if;
        select status into strict chk_status
        from gba.restaurant_checks
        where tenant_id = new.tenant_id and id = new.check_id;
        if chk_status <> 'open' then
            raise exception using errcode = '23514',
                message = 'kitchen tickets can only be fired on an open check';
        end if;
        return new;
    end if;
    if (old.tenant_id, old.id, old.check_id, old.location_id, old.ticket_no,
        old.kitchen_station, old.fired_by, old.fired_at)
       is distinct from (new.tenant_id, new.id, new.check_id, new.location_id, new.ticket_no,
                         new.kitchen_station, new.fired_by, new.fired_at) then
        raise exception using errcode = '23514',
            message = 'kitchen ticket identity is immutable';
    end if;
    if new.revision <> old.revision + 1 then
        raise exception using errcode = '23514',
            message = 'kitchen ticket revision increments by one';
    end if;
    if not (
        (old.status = 'queued' and new.status in ('preparing', 'voided'))
        or (old.status = 'preparing' and new.status in ('ready', 'voided'))
        or (old.status = 'ready' and new.status in ('served', 'voided'))
    ) then
        raise exception using errcode = '23514',
            message = 'invalid kitchen ticket status transition';
    end if;
    return new;
end;
$$;
revoke all on function gba.guard_restaurant_kitchen_ticket() from public;
create trigger restaurant_kitchen_tickets_guard
    before insert or update or delete on gba.restaurant_kitchen_tickets
    for each row execute function gba.guard_restaurant_kitchen_ticket();

create function gba.guard_restaurant_kitchen_ticket_event() returns trigger language plpgsql as $$
begin
    raise exception using errcode = '23514',
        message = 'kitchen ticket events are immutable';
end;
$$;
revoke all on function gba.guard_restaurant_kitchen_ticket_event() from public;
create trigger restaurant_kitchen_ticket_events_immutable
    before update or delete on gba.restaurant_kitchen_ticket_events
    for each row execute function gba.guard_restaurant_kitchen_ticket_event();

create function gba.guard_restaurant_check_line() returns trigger language plpgsql as $$
declare
    chk record;
    rev_currency text;
begin
    if tg_op = 'DELETE' then
        raise exception using errcode = '23514', message = 'check lines are kept';
    end if;
    if exists (
        select 1 from gba.restaurant_check_consumptions c
        where c.tenant_id = new.tenant_id and c.check_id = new.check_id
    ) then
        raise exception using errcode = '23514',
            message = 'check lines cannot change after ingredient write-off is posted';
    end if;
    if tg_op = 'INSERT' then
        if new.status <> 'draft' then
            raise exception using errcode = '23514',
                message = 'a new check line starts in draft state';
        end if;
        select status, currency into strict chk
        from gba.restaurant_checks
        where tenant_id = new.tenant_id and id = new.check_id;
        if chk.status <> 'open' then
            raise exception using errcode = '23514',
                message = 'lines can only be added to an open check';
        end if;
        select currency into strict rev_currency
        from gba.restaurant_menu_item_revisions
        where tenant_id = new.tenant_id
          and menu_item_id = new.menu_item_id
          and revision = new.menu_item_revision;
        if rev_currency <> chk.currency then
            raise exception using errcode = '23514',
                message = 'menu item currency must match check currency';
        end if;
        return new;
    end if;
    if (old.tenant_id, old.id, old.check_id, old.location_id, old.line_no,
        old.menu_item_id, old.menu_item_revision, old.recipe_revision,
        old.item_code, old.item_name, old.kitchen_station, old.quantity,
        old.base_price_minor, old.modifiers_delta_minor, old.unit_price_minor,
        old.line_total_minor, old.note, old.creation_xid)
       is distinct from (new.tenant_id, new.id, new.check_id, new.location_id, new.line_no,
                         new.menu_item_id, new.menu_item_revision, new.recipe_revision,
                         new.item_code, new.item_name, new.kitchen_station, new.quantity,
                         new.base_price_minor, new.modifiers_delta_minor, new.unit_price_minor,
                         new.line_total_minor, new.note, new.creation_xid) then
        raise exception using errcode = '23514',
            message = 'check line commercial snapshot is immutable';
    end if;
    if not (
        (old.status = 'draft' and new.status in ('fired', 'voided'))
        or (old.status = 'fired' and new.status in ('served', 'voided'))
        or (old.status = 'served' and new.status = 'voided')
    ) then
        raise exception using errcode = '23514',
            message = 'invalid check line status transition';
    end if;
    if old.kitchen_ticket_id is not null and new.kitchen_ticket_id is distinct from old.kitchen_ticket_id then
        raise exception using errcode = '23514',
            message = 'check line kitchen ticket cannot change once fired';
    end if;
    return new;
end;
$$;
revoke all on function gba.guard_restaurant_check_line() from public;
create trigger restaurant_check_lines_guard
    before insert or update or delete on gba.restaurant_check_lines
    for each row execute function gba.guard_restaurant_check_line();

create function gba.guard_restaurant_check_line_modifier() returns trigger language plpgsql as $$
begin
    if tg_op <> 'INSERT' then
        raise exception using errcode = '23514',
            message = 'check line modifier snapshots are immutable';
    end if;
    perform 1 from gba.restaurant_check_lines l
    where l.tenant_id = new.tenant_id and l.id = new.check_line_id
      and l.location_id = new.location_id
      and l.creation_xid = pg_current_xact_id();
    if not found then
        raise exception using errcode = '23514',
            message = 'modifier snapshots are written with their check line';
    end if;
    return new;
end;
$$;
revoke all on function gba.guard_restaurant_check_line_modifier() from public;
create trigger restaurant_check_line_modifiers_guard
    before insert or update or delete on gba.restaurant_check_line_modifiers
    for each row execute function gba.guard_restaurant_check_line_modifier();

create function gba.guard_restaurant_check_consumption() returns trigger language plpgsql as $$
declare
    chk_status text;
begin
    if tg_op <> 'INSERT' then
        raise exception using errcode = '23514',
            message = 'check consumption records are immutable';
    end if;
    select status into strict chk_status
    from gba.restaurant_checks
    where tenant_id = new.tenant_id and id = new.check_id
    for update;
    if chk_status = 'voided' then
        raise exception using errcode = '23514',
            message = 'voided checks cannot post ingredient consumption';
    end if;
    if exists (
        select 1 from gba.restaurant_check_lines l
        where l.tenant_id = new.tenant_id and l.check_id = new.check_id and l.status = 'draft'
    ) then
        raise exception using errcode = '23514',
            message = 'fire or void all draft lines before posting ingredient consumption';
    end if;
    return new;
end;
$$;
revoke all on function gba.guard_restaurant_check_consumption() from public;
create trigger restaurant_check_consumptions_guard
    before insert or update or delete on gba.restaurant_check_consumptions
    for each row execute function gba.guard_restaurant_check_consumption();

create function gba.guard_restaurant_check_consumption_line() returns trigger language plpgsql as $$
begin
    if tg_op <> 'INSERT' then
        raise exception using errcode = '23514',
            message = 'check consumption lines are immutable';
    end if;
    perform 1 from gba.restaurant_check_consumptions c
    where c.tenant_id = new.tenant_id and c.check_id = new.check_id
      and c.location_id = new.location_id
      and new.line_no <= c.line_count
      and c.creation_xid = pg_current_xact_id();
    if not found then
        raise exception using errcode = '23514',
            message = 'consumption lines are written with their consumption record';
    end if;
    return new;
end;
$$;
revoke all on function gba.guard_restaurant_check_consumption_line() from public;
create trigger restaurant_check_consumption_lines_guard
    before insert or update or delete on gba.restaurant_check_consumption_lines
    for each row execute function gba.guard_restaurant_check_consumption_line();

create function gba.check_restaurant_consumption_lines() returns trigger language plpgsql as $$
declare
    cnt integer;
    min_no integer;
    max_no integer;
begin
    select count(*), min(l.line_no), max(l.line_no) into cnt, min_no, max_no
    from gba.restaurant_check_consumption_lines l
    where l.tenant_id = new.tenant_id and l.check_id = new.check_id;
    if new.line_count = 0 then
        if cnt <> 0 then
            raise exception using errcode = '23514',
                message = 'empty consumption must have zero lines';
        end if;
    else
        if cnt <> new.line_count or min_no <> 1 or max_no <> new.line_count then
            raise exception using errcode = '23514',
                message = 'consumption must keep its numbered ingredient lines';
        end if;
    end if;
    return null;
end;
$$;
revoke all on function gba.check_restaurant_consumption_lines() from public;
create constraint trigger restaurant_check_consumptions_complete
    after insert on gba.restaurant_check_consumptions
    deferrable initially deferred for each row
    execute function gba.check_restaurant_consumption_lines();

-- RLS, module write gates and minimal runtime privileges
alter table gba.restaurant_checks enable row level security;
alter table gba.restaurant_checks force row level security;
create policy restaurant_checks_tenant_isolation on gba.restaurant_checks
    using (tenant_id = gba.current_tenant_id()) with check (tenant_id = gba.current_tenant_id());
grant select, insert, update on gba.restaurant_checks to gba_runtime;
create trigger restaurant_checks_require_module before insert on gba.restaurant_checks
    for each row execute function gba.require_enabled_module('restaurant');

alter table gba.restaurant_kitchen_tickets enable row level security;
alter table gba.restaurant_kitchen_tickets force row level security;
create policy restaurant_kitchen_tickets_tenant_isolation on gba.restaurant_kitchen_tickets
    using (tenant_id = gba.current_tenant_id()) with check (tenant_id = gba.current_tenant_id());
grant select, insert, update on gba.restaurant_kitchen_tickets to gba_runtime;
create trigger restaurant_kitchen_tickets_require_module before insert on gba.restaurant_kitchen_tickets
    for each row execute function gba.require_enabled_module('restaurant');

alter table gba.restaurant_kitchen_ticket_events enable row level security;
alter table gba.restaurant_kitchen_ticket_events force row level security;
create policy restaurant_kitchen_ticket_events_tenant_isolation on gba.restaurant_kitchen_ticket_events
    using (tenant_id = gba.current_tenant_id()) with check (tenant_id = gba.current_tenant_id());
grant select, insert on gba.restaurant_kitchen_ticket_events to gba_runtime;

alter table gba.restaurant_check_lines enable row level security;
alter table gba.restaurant_check_lines force row level security;
create policy restaurant_check_lines_tenant_isolation on gba.restaurant_check_lines
    using (tenant_id = gba.current_tenant_id()) with check (tenant_id = gba.current_tenant_id());
grant select, insert, update on gba.restaurant_check_lines to gba_runtime;

alter table gba.restaurant_check_line_modifiers enable row level security;
alter table gba.restaurant_check_line_modifiers force row level security;
create policy restaurant_check_line_modifiers_tenant_isolation on gba.restaurant_check_line_modifiers
    using (tenant_id = gba.current_tenant_id()) with check (tenant_id = gba.current_tenant_id());
grant select, insert on gba.restaurant_check_line_modifiers to gba_runtime;

alter table gba.restaurant_check_consumptions enable row level security;
alter table gba.restaurant_check_consumptions force row level security;
create policy restaurant_check_consumptions_tenant_isolation on gba.restaurant_check_consumptions
    using (tenant_id = gba.current_tenant_id()) with check (tenant_id = gba.current_tenant_id());
grant select, insert on gba.restaurant_check_consumptions to gba_runtime;
create trigger restaurant_check_consumptions_require_module
    before insert on gba.restaurant_check_consumptions
    for each row execute function gba.require_enabled_module('restaurant');

alter table gba.restaurant_check_consumption_lines enable row level security;
alter table gba.restaurant_check_consumption_lines force row level security;
create policy restaurant_check_consumption_lines_tenant_isolation
    on gba.restaurant_check_consumption_lines
    using (tenant_id = gba.current_tenant_id()) with check (tenant_id = gba.current_tenant_id());
grant select, insert on gba.restaurant_check_consumption_lines to gba_runtime;

-- Restaurant checks branch scope:
create policy restaurant_checks_location_scope on gba.restaurant_checks as restrictive to gba_runtime
    using (gba.current_location_id() is null or location_id = gba.current_location_id())
    with check (gba.current_location_id() is null or location_id = gba.current_location_id());

create policy restaurant_kitchen_tickets_location_scope on gba.restaurant_kitchen_tickets as restrictive to gba_runtime
    using (gba.current_location_id() is null or location_id = gba.current_location_id())
    with check (gba.current_location_id() is null or location_id = gba.current_location_id());

create policy restaurant_kitchen_ticket_events_location_scope on gba.restaurant_kitchen_ticket_events as restrictive to gba_runtime
    using (gba.current_location_id() is null or location_id = gba.current_location_id())
    with check (gba.current_location_id() is null or location_id = gba.current_location_id());

create policy restaurant_check_lines_location_scope on gba.restaurant_check_lines as restrictive to gba_runtime
    using (gba.current_location_id() is null or location_id = gba.current_location_id())
    with check (gba.current_location_id() is null or location_id = gba.current_location_id());

create policy restaurant_check_line_modifiers_location_scope on gba.restaurant_check_line_modifiers as restrictive to gba_runtime
    using (gba.current_location_id() is null or location_id = gba.current_location_id())
    with check (gba.current_location_id() is null or location_id = gba.current_location_id());

create policy restaurant_check_consumptions_location_scope on gba.restaurant_check_consumptions as restrictive to gba_runtime
    using (gba.current_location_id() is null or location_id = gba.current_location_id())
    with check (gba.current_location_id() is null or location_id = gba.current_location_id());

create policy restaurant_check_consumption_lines_location_scope on gba.restaurant_check_consumption_lines as restrictive to gba_runtime
    using (gba.current_location_id() is null or location_id = gba.current_location_id())
    with check (gba.current_location_id() is null or location_id = gba.current_location_id());
