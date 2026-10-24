-- M3 (package M, TMS-01 and TMS-03): trip stop events as idempotent facts; partial delivery.
-- ADR-0030. An event is an insert-only fact with its source and the source's event id (unique
-- in the business); loading and delivery events name quantities per leg; a leg never loads more
-- than planned nor resolves more than loaded (checked at commit). The first event starts the trip:
-- its plan is frozen from then on, while assignments can still be replaced.
alter table gba.transport_trips drop constraint transport_trips_status_check;
alter table gba.transport_trips add constraint transport_trips_status_check
    check (status in ('planned', 'in_transit'));

create table gba.transport_stop_events (
    tenant_id uuid not null references gba.tenants(id),
    id uuid not null,
    trip_id uuid not null,
    stop_position smallint not null,
    kind text not null constraint transport_stop_events_kind_check
        check (kind in ('arrived', 'departed', 'loaded', 'delivered', 'refused', 'damaged',
                        'exception')),
    occurred_at timestamptz not null,
    source text not null constraint transport_stop_events_source_check
        check (source ~ '^[a-z][a-z0-9_.-]{0,31}$'),
    source_event_id text not null constraint transport_stop_events_source_event_id_check
        check (length(btrim(source_event_id)) between 1 and 200
               and source_event_id !~ '[[:cntrl:]]'),
    note text constraint transport_stop_events_note_check
        check (note is null or (length(note) <= 500 and note !~ '[[:cntrl:]]')),
    recorded_by uuid not null references gba.users(id),
    recorded_at timestamptz not null default now(),
    primary key (tenant_id, id),
    unique (tenant_id, source, source_event_id),
    foreign key (tenant_id, trip_id) references gba.transport_trips (tenant_id, id),
    foreign key (tenant_id, trip_id, stop_position)
        references gba.transport_stops (tenant_id, trip_id, position)
);
create table gba.transport_event_quantities (
    tenant_id uuid not null references gba.tenants(id),
    event_id uuid not null,
    trip_id uuid not null,
    leg_position smallint not null,
    quantity integer not null constraint transport_event_quantities_quantity_check
        check (quantity between 1 and 1000000),
    primary key (tenant_id, event_id, leg_position),
    foreign key (tenant_id, event_id) references gba.transport_stop_events (tenant_id, id),
    foreign key (tenant_id, trip_id, leg_position)
        references gba.transport_legs (tenant_id, trip_id, position)
);

-- A quantity names a leg of its event's trip: loaded at the leg's pickup, the others at its
-- delivery; only loading and delivery events carry quantities.
create function gba.guard_transport_event_quantity() returns trigger language plpgsql as $$
declare
    event_trip uuid;
    event_stop smallint;
    event_kind text;
begin
    select e.trip_id, e.stop_position, e.kind into event_trip, event_stop, event_kind
      from gba.transport_stop_events e
     where e.tenant_id = new.tenant_id and e.id = new.event_id;
    if event_trip is distinct from new.trip_id
       or coalesce(event_kind, '') not in ('loaded', 'delivered', 'refused', 'damaged')
       or not exists (
           select 1 from gba.transport_legs g
            where g.tenant_id = new.tenant_id and g.trip_id = new.trip_id
              and g.position = new.leg_position
              and case when event_kind = 'loaded' then g.pickup_stop else g.delivery_stop end
                  = event_stop
       ) then
        raise exception using errcode = 'check_violation',
            constraint = 'transport_event_quantities_leg_check',
            message = 'a quantity names a leg of its event''s trip at its stop';
    end if;
    return new;
end;
$$;
revoke all on function gba.guard_transport_event_quantity() from public;
create trigger transport_event_quantities_guard before insert on gba.transport_event_quantities
    for each row execute function gba.guard_transport_event_quantity();

-- At commit: loading and delivery events name quantities and the others none; for every leg of
-- the trip, loaded never exceeds the plan and delivered, refused and damaged never exceed loaded.
create function gba.check_transport_trip_events() returns trigger language plpgsql as $$
begin
    if exists (
        select 1 from gba.transport_stop_events e
         where e.tenant_id = new.tenant_id and e.trip_id = new.trip_id
           and (e.kind in ('loaded', 'delivered', 'refused', 'damaged')) <> exists (
               select 1 from gba.transport_event_quantities q
                where q.tenant_id = e.tenant_id and q.event_id = e.id)
    ) then
        raise exception using errcode = 'check_violation',
            constraint = 'transport_stop_events_quantities_check',
            message = 'loading and delivery events name their quantities, others none';
    end if;
    if exists (
        select 1
          from gba.transport_legs g
         cross join lateral (
             select coalesce(sum(q.quantity) filter (where e.kind = 'loaded'), 0) as loaded,
                    coalesce(sum(q.quantity) filter (where e.kind <> 'loaded'), 0) as resolved
               from gba.transport_event_quantities q
               join gba.transport_stop_events e on e.tenant_id = q.tenant_id and e.id = q.event_id
              where q.tenant_id = g.tenant_id and q.trip_id = g.trip_id
                and q.leg_position = g.position
         ) t
         where g.tenant_id = new.tenant_id and g.trip_id = new.trip_id
           and (t.loaded > g.quantity or t.resolved > t.loaded)
    ) then
        raise exception using errcode = 'check_violation',
            constraint = 'transport_event_quantities_total_check',
            message = 'a leg never loads more than planned nor resolves more than loaded';
    end if;
    return null;
end;
$$;
revoke all on function gba.check_transport_trip_events() from public;
create constraint trigger transport_stop_events_totals after insert on gba.transport_stop_events
    deferrable initially deferred for each row execute function gba.check_transport_trip_events();
create constraint trigger transport_event_quantities_totals
    after insert on gba.transport_event_quantities
    deferrable initially deferred for each row execute function gba.check_transport_trip_events();

-- The first event starts its trip.
create function gba.start_transport_trip() returns trigger language plpgsql as $$
begin
    update gba.transport_trips t set status = 'in_transit'
     where t.tenant_id = new.tenant_id and t.id = new.trip_id and t.status = 'planned';
    return null;
end;
$$;
revoke all on function gba.start_transport_trip() from public;
create trigger transport_stop_events_start after insert on gba.transport_stop_events
    for each row execute function gba.start_transport_trip();

-- A trip moves only from planned to in transit, only with an event, and a started trip keeps
-- its plan: its reference and revision, stops and legs never change.
create function gba.guard_transport_trip_status() returns trigger language plpgsql as $$
begin
    if new.status is distinct from old.status and not (
        old.status = 'planned' and new.status = 'in_transit'
        and exists (
            select 1 from gba.transport_stop_events e
             where e.tenant_id = new.tenant_id and e.trip_id = new.id)
    ) then
        raise exception using errcode = 'check_violation',
            constraint = 'transport_trips_status_move_check',
            message = 'a trip starts with its first event and never goes back';
    end if;
    if old.status <> 'planned'
       and (new.reference, new.revision) is distinct from (old.reference, old.revision) then
        raise exception using errcode = 'check_violation',
            constraint = 'transport_trips_started_check',
            message = 'a started trip keeps its plan';
    end if;
    return new;
end;
$$;
revoke all on function gba.guard_transport_trip_status() from public;
create trigger transport_trips_status_guard before update on gba.transport_trips
    for each row execute function gba.guard_transport_trip_status();
create function gba.guard_transport_plan_change() returns trigger language plpgsql as $$
declare
    checked_tenant uuid;
    checked_trip uuid;
begin
    if tg_op = 'DELETE' then
        checked_tenant := old.tenant_id;
        checked_trip := old.trip_id;
    else
        checked_tenant := new.tenant_id;
        checked_trip := new.trip_id;
    end if;
    if exists (
        select 1 from gba.transport_trips t
         where t.tenant_id = checked_tenant and t.id = checked_trip and t.status <> 'planned'
    ) then
        raise exception using errcode = 'check_violation',
            constraint = 'transport_trips_started_check',
            message = 'a started trip keeps its plan';
    end if;
    if tg_op = 'DELETE' then
        return old;
    end if;
    return new;
end;
$$;
revoke all on function gba.guard_transport_plan_change() from public;
create trigger transport_stops_plan_guard before insert or delete on gba.transport_stops
    for each row execute function gba.guard_transport_plan_change();
create trigger transport_legs_plan_guard before insert or delete on gba.transport_legs
    for each row execute function gba.guard_transport_plan_change();

-- Assignments (0075) continue while the trip is in transit: a truck can be replaced on the road.
create or replace function gba.guard_transport_assignment() returns trigger language plpgsql as $$
declare
    trip_location uuid;
    trip_status text;
    span tstzrange;
begin
    select t.location_id, t.status into trip_location, trip_status
      from gba.transport_trips t
     where t.tenant_id = new.tenant_id and t.id = new.trip_id
       for update;
    span := gba.transport_trip_span(new.tenant_id, new.trip_id);
    if coalesce(trip_status, '') not in ('planned', 'in_transit') or span is null or isempty(span)
       or lower_inf(span) or upper_inf(span)
       or new.starts_at < lower(span) or new.starts_at >= upper(span) then
        raise exception using errcode = 'check_violation',
            constraint = 'transport_assignments_period_check',
            message = 'an assignment starts inside the span of a planned or running trip';
    end if;
    if not exists (
        select 1 from gba.resources r
        where r.tenant_id = new.tenant_id and r.id = new.resource_id and r.kind = new.role
          and r.location_id = trip_location and r.is_active
    ) then
        raise exception using errcode = 'check_violation',
            constraint = 'transport_assignments_resource_check',
            message = 'an assignment names an active resource of its role in the trip''s branch';
    end if;
    if exists (
        select 1 from gba.transport_assignments a
          left join gba.transport_assignment_ends e
            on e.tenant_id = a.tenant_id and e.assignment_id = a.id
         where a.tenant_id = new.tenant_id and a.trip_id = new.trip_id and a.role = new.role
           and (e.assignment_id is null or e.ends_at > new.starts_at)
    ) then
        raise exception using errcode = 'check_violation',
            constraint = 'transport_assignments_overlap_check',
            message = 'periods of one role on one trip never overlap';
    end if;
    if new.replaces is not null and not exists (
        select 1 from gba.transport_assignments a
          join gba.transport_assignment_ends e
            on e.tenant_id = a.tenant_id and e.assignment_id = a.id
         where a.tenant_id = new.tenant_id and a.id = new.replaces and a.trip_id = new.trip_id
           and a.role = new.role and e.ends_at = new.starts_at
    ) then
        raise exception using errcode = 'check_violation',
            constraint = 'transport_assignments_replaces_check',
            message = 'a replacement starts where the replaced period ends';
    end if;
    return new;
end;
$$;

-- Writes need the transport module (ADR-0019 gate).
create trigger transport_stop_events_module_gate before insert on gba.transport_stop_events
    for each row execute function gba.require_enabled_module('transport');
create trigger transport_event_quantities_module_gate
    before insert on gba.transport_event_quantities
    for each row execute function gba.require_enabled_module('transport');

alter table gba.transport_stop_events enable row level security;
alter table gba.transport_stop_events force row level security;
alter table gba.transport_event_quantities enable row level security;
alter table gba.transport_event_quantities force row level security;
create policy transport_stop_events_tenant_isolation on gba.transport_stop_events
    using (tenant_id = gba.current_tenant_id())
    with check (tenant_id = gba.current_tenant_id());
create policy transport_event_quantities_tenant_isolation on gba.transport_event_quantities
    using (tenant_id = gba.current_tenant_id())
    with check (tenant_id = gba.current_tenant_id());
grant select on gba.transport_stop_events, gba.transport_event_quantities to gba_runtime;
grant insert (tenant_id, id, trip_id, stop_position, kind, occurred_at, source, source_event_id,
              note, recorded_by)
    on gba.transport_stop_events to gba_runtime;
grant insert (tenant_id, event_id, trip_id, leg_position, quantity)
    on gba.transport_event_quantities to gba_runtime;
grant update (status) on gba.transport_trips to gba_runtime;

-- Transport event branch scope:
create policy transport_stop_events_location_scope on gba.transport_stop_events
    as restrictive to gba_runtime
    using (gba.current_location_id() is null or exists (
        select 1 from gba.transport_trips t
        where t.tenant_id = transport_stop_events.tenant_id
          and t.id = transport_stop_events.trip_id))
    with check (gba.current_location_id() is null or exists (
        select 1 from gba.transport_trips t
        where t.tenant_id = transport_stop_events.tenant_id
          and t.id = transport_stop_events.trip_id));
create policy transport_event_quantities_location_scope on gba.transport_event_quantities
    as restrictive to gba_runtime
    using (gba.current_location_id() is null or exists (
        select 1 from gba.transport_trips t
        where t.tenant_id = transport_event_quantities.tenant_id
          and t.id = transport_event_quantities.trip_id))
    with check (gba.current_location_id() is null or exists (
        select 1 from gba.transport_trips t
        where t.tenant_id = transport_event_quantities.tenant_id
          and t.id = transport_event_quantities.trip_id));
