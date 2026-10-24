-- M1 (package M, TMS-01): the transport planning model. ADR-0028. Shipment order, load, trip, stop
-- and leg are separate: one trip carries several loads; a load is split across trips by quantity;
-- the planned total of a load never exceeds its quantity (checked at commit). Loads are never
-- deleted (a removed load is marked); a planned trip's stops and legs are replaced whole.
create table gba.transport_orders (
    tenant_id uuid not null references gba.tenants(id),
    id uuid not null,
    customer_id uuid not null,
    reference text not null constraint transport_orders_reference_check
        check (length(btrim(reference)) between 1 and 64),
    revision integer not null constraint transport_orders_revision_check check (revision > 0),
    created_by uuid not null references gba.users(id),
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    primary key (tenant_id, id),
    unique (tenant_id, reference),
    foreign key (tenant_id, customer_id) references gba.counterparties (tenant_id, id)
);
create table gba.transport_loads (
    tenant_id uuid not null references gba.tenants(id),
    id uuid not null,
    order_id uuid not null,
    position smallint not null constraint transport_loads_position_check
        check (position between 1 and 50),
    description text not null constraint transport_loads_description_check
        check (length(btrim(description)) between 1 and 500),
    quantity integer not null constraint transport_loads_quantity_check
        check (quantity between 1 and 1000000),
    unit text not null constraint transport_loads_unit_check
        check (length(btrim(unit)) between 1 and 32),
    weight_grams bigint constraint transport_loads_weight_check
        check (weight_grams between 0 and 999999999999),
    shipper_id uuid,
    consignee_id uuid,
    removed boolean not null default false,
    primary key (tenant_id, id),
    foreign key (tenant_id, order_id) references gba.transport_orders (tenant_id, id),
    foreign key (tenant_id, shipper_id) references gba.counterparties (tenant_id, id),
    foreign key (tenant_id, consignee_id) references gba.counterparties (tenant_id, id)
);
create table gba.transport_trips (
    tenant_id uuid not null references gba.tenants(id),
    id uuid not null,
    location_id uuid not null,
    reference text not null constraint transport_trips_reference_check
        check (length(btrim(reference)) between 1 and 64),
    status text not null default 'planned' constraint transport_trips_status_check
        check (status in ('planned')),
    revision integer not null constraint transport_trips_revision_check check (revision > 0),
    created_by uuid not null references gba.users(id),
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    primary key (tenant_id, id),
    unique (tenant_id, reference),
    foreign key (tenant_id, location_id) references gba.locations (tenant_id, id)
);
create table gba.transport_stops (
    tenant_id uuid not null references gba.tenants(id),
    trip_id uuid not null,
    position smallint not null constraint transport_stops_position_check
        check (position between 1 and 50),
    kind text not null constraint transport_stops_kind_check
        check (kind in ('pickup', 'delivery')),
    place text not null constraint transport_stops_place_check
        check (length(btrim(place)) between 1 and 300),
    time_zone text not null,
    window_start timestamptz not null,
    window_end timestamptz not null,
    primary key (tenant_id, trip_id, position),
    foreign key (tenant_id, trip_id) references gba.transport_trips (tenant_id, id),
    constraint transport_stops_window_check check (window_start <= window_end)
);
create table gba.transport_legs (
    tenant_id uuid not null references gba.tenants(id),
    trip_id uuid not null,
    position smallint not null constraint transport_legs_position_check
        check (position between 1 and 100),
    load_id uuid not null,
    quantity integer not null constraint transport_legs_quantity_check
        check (quantity between 1 and 1000000),
    pickup_stop smallint not null,
    delivery_stop smallint not null,
    primary key (tenant_id, trip_id, position),
    foreign key (tenant_id, trip_id) references gba.transport_trips (tenant_id, id),
    foreign key (tenant_id, load_id) references gba.transport_loads (tenant_id, id),
    foreign key (tenant_id, trip_id, pickup_stop)
        references gba.transport_stops (tenant_id, trip_id, position),
    foreign key (tenant_id, trip_id, delivery_stop)
        references gba.transport_stops (tenant_id, trip_id, position),
    constraint transport_legs_order_check check (pickup_stop < delivery_stop)
);

-- A stop names a time zone PostgreSQL knows.
create function gba.guard_transport_stop() returns trigger language plpgsql as $$
begin
    if not exists (select 1 from pg_catalog.pg_timezone_names z where z.name = new.time_zone) then
        raise exception using errcode = 'check_violation',
            constraint = 'transport_stops_time_zone_check',
            message = 'a stop names a known time zone';
    end if;
    return new;
end;
$$;
revoke all on function gba.guard_transport_stop() from public;
create trigger transport_stops_guard
    before insert on gba.transport_stops
    for each row execute function gba.guard_transport_stop();

-- A leg goes from a pickup to a later delivery of its trip, for a load that is not removed.
create function gba.guard_transport_leg() returns trigger language plpgsql as $$
begin
    if not exists (
        select 1 from gba.transport_stops s
        where s.tenant_id = new.tenant_id and s.trip_id = new.trip_id
          and s.position = new.pickup_stop and s.kind = 'pickup'
    ) or not exists (
        select 1 from gba.transport_stops s
        where s.tenant_id = new.tenant_id and s.trip_id = new.trip_id
          and s.position = new.delivery_stop and s.kind = 'delivery'
    ) or exists (
        select 1 from gba.transport_loads l
        where l.tenant_id = new.tenant_id and l.id = new.load_id and l.removed
    ) then
        raise exception using errcode = 'check_violation',
            constraint = 'transport_legs_stops_check',
            message = 'a leg goes from a pickup to a later delivery of a current load';
    end if;
    return new;
end;
$$;
revoke all on function gba.guard_transport_leg() from public;
create trigger transport_legs_guard
    before insert on gba.transport_legs
    for each row execute function gba.guard_transport_leg();

-- At commit, no load is planned beyond its quantity and no planned load is removed.
create function gba.check_transport_load_plan() returns trigger language plpgsql as $$
declare
    checked uuid;
begin
    if tg_table_name = 'transport_loads' then
        checked := new.id;
    else
        checked := new.load_id;
    end if;
    if exists (
        select 1 from gba.transport_loads l
        where l.tenant_id = new.tenant_id and l.id = checked
          and coalesce((
              select sum(g.quantity) from gba.transport_legs g
              where g.tenant_id = l.tenant_id and g.load_id = l.id), 0)
              > case when l.removed then 0 else l.quantity end
    ) then
        raise exception using errcode = 'check_violation',
            constraint = 'transport_loads_plan_check',
            message = 'a load is never planned beyond its quantity';
    end if;
    return null;
end;
$$;
revoke all on function gba.check_transport_load_plan() from public;
create constraint trigger transport_legs_plan_check
    after insert on gba.transport_legs
    deferrable initially deferred
    for each row execute function gba.check_transport_load_plan();
create constraint trigger transport_loads_plan_check
    after update on gba.transport_loads
    deferrable initially deferred
    for each row execute function gba.check_transport_load_plan();

-- Writes need the transport module (ADR-0019 gate).
create trigger transport_orders_module_gate
    before insert on gba.transport_orders
    for each row execute function gba.require_enabled_module('transport');
create trigger transport_trips_module_gate
    before insert on gba.transport_trips
    for each row execute function gba.require_enabled_module('transport');

alter table gba.transport_orders enable row level security;
alter table gba.transport_orders force row level security;
alter table gba.transport_loads enable row level security;
alter table gba.transport_loads force row level security;
alter table gba.transport_trips enable row level security;
alter table gba.transport_trips force row level security;
alter table gba.transport_stops enable row level security;
alter table gba.transport_stops force row level security;
alter table gba.transport_legs enable row level security;
alter table gba.transport_legs force row level security;
create policy transport_orders_tenant_isolation on gba.transport_orders
    using (tenant_id = gba.current_tenant_id())
    with check (tenant_id = gba.current_tenant_id());
create policy transport_loads_tenant_isolation on gba.transport_loads
    using (tenant_id = gba.current_tenant_id())
    with check (tenant_id = gba.current_tenant_id());
create policy transport_trips_tenant_isolation on gba.transport_trips
    using (tenant_id = gba.current_tenant_id())
    with check (tenant_id = gba.current_tenant_id());
create policy transport_stops_tenant_isolation on gba.transport_stops
    using (tenant_id = gba.current_tenant_id())
    with check (tenant_id = gba.current_tenant_id());
create policy transport_legs_tenant_isolation on gba.transport_legs
    using (tenant_id = gba.current_tenant_id())
    with check (tenant_id = gba.current_tenant_id());
grant select, insert on gba.transport_orders, gba.transport_loads, gba.transport_trips
    to gba_runtime;
grant update (customer_id, reference, revision, updated_at) on gba.transport_orders to gba_runtime;
grant update (position, description, quantity, unit, weight_grams, shipper_id, consignee_id, removed)
    on gba.transport_loads to gba_runtime;
grant update (reference, revision, updated_at) on gba.transport_trips to gba_runtime;
grant select, insert, delete on gba.transport_stops, gba.transport_legs to gba_runtime;

-- Transport branch scope:
create policy transport_trips_location_scope on gba.transport_trips
    as restrictive to gba_runtime
    using (gba.current_location_id() is null or location_id = gba.current_location_id())
    with check (gba.current_location_id() is null or location_id = gba.current_location_id());
create policy transport_stops_location_scope on gba.transport_stops
    as restrictive to gba_runtime
    using (gba.current_location_id() is null or exists (
        select 1 from gba.transport_trips t
        where t.tenant_id = transport_stops.tenant_id and t.id = transport_stops.trip_id))
    with check (gba.current_location_id() is null or exists (
        select 1 from gba.transport_trips t
        where t.tenant_id = transport_stops.tenant_id and t.id = transport_stops.trip_id));
create policy transport_legs_location_scope on gba.transport_legs
    as restrictive to gba_runtime
    using (gba.current_location_id() is null or exists (
        select 1 from gba.transport_trips t
        where t.tenant_id = transport_legs.tenant_id and t.id = transport_legs.trip_id))
    with check (gba.current_location_id() is null or exists (
        select 1 from gba.transport_trips t
        where t.tenant_id = transport_legs.tenant_id and t.id = transport_legs.trip_id));
