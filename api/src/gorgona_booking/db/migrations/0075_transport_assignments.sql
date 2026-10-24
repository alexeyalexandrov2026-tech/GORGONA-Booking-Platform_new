-- M2 (package M, TMS-01): driver, truck and trailer assignments with periods in the shared
-- occupancy. ADR-0029. Each driver and vehicle has its own resource (kinds driver, truck,
-- trailer); a trip assignment holds it for its period through gba.resource_allocations, and a
-- replacement ends one period and starts the next in one transaction. Periods and their ends are
-- insert-only; at commit every assignment holds exactly its period of the trip.
alter table gba.resources drop constraint resources_kind_valid;
alter table gba.resources add constraint resources_kind_valid
    check (kind in ('artist', 'chair', 'room', 'staff', 'equipment', 'driver', 'truck', 'trailer'));
alter table gba.resource_allocations drop constraint resource_allocations_source_kind;
alter table gba.resource_allocations add constraint resource_allocations_source_kind
    check (source_kind in ('booking', 'reservation', 'shift', 'trip_assignment'));

create table gba.transport_drivers (
    tenant_id uuid not null references gba.tenants(id),
    id uuid not null,
    location_id uuid not null,
    resource_id uuid not null,
    display_name text not null constraint transport_drivers_display_name_check
        check (length(btrim(display_name)) between 1 and 200 and display_name !~ '[[:cntrl:]]'),
    created_by uuid not null references gba.users(id),
    created_at timestamptz not null default now(),
    primary key (tenant_id, id),
    unique (tenant_id, resource_id),
    foreign key (tenant_id, location_id) references gba.locations (tenant_id, id),
    foreign key (tenant_id, resource_id) references gba.resources (tenant_id, id)
);
create table gba.transport_vehicles (
    tenant_id uuid not null references gba.tenants(id),
    id uuid not null,
    location_id uuid not null,
    resource_id uuid not null,
    kind text not null constraint transport_vehicles_kind_check check (kind in ('truck', 'trailer')),
    unit_number text not null constraint transport_vehicles_unit_number_check
        check (length(btrim(unit_number)) between 1 and 32 and unit_number !~ '[[:cntrl:]]'),
    created_by uuid not null references gba.users(id),
    created_at timestamptz not null default now(),
    primary key (tenant_id, id),
    unique (tenant_id, resource_id),
    unique (tenant_id, unit_number),
    foreign key (tenant_id, location_id) references gba.locations (tenant_id, id),
    foreign key (tenant_id, resource_id) references gba.resources (tenant_id, id)
);
create table gba.transport_assignments (
    tenant_id uuid not null references gba.tenants(id),
    id uuid not null,
    trip_id uuid not null,
    role text not null constraint transport_assignments_role_check
        check (role in ('driver', 'truck', 'trailer')),
    resource_id uuid not null,
    starts_at timestamptz not null,
    replaces uuid,
    created_by uuid not null references gba.users(id),
    created_at timestamptz not null default now(),
    creation_xid xid8 not null default pg_current_xact_id(),
    primary key (tenant_id, id),
    unique (tenant_id, replaces),
    foreign key (tenant_id, trip_id) references gba.transport_trips (tenant_id, id),
    foreign key (tenant_id, resource_id) references gba.resources (tenant_id, id),
    foreign key (tenant_id, replaces) references gba.transport_assignments (tenant_id, id)
);
create table gba.transport_assignment_ends (
    tenant_id uuid not null references gba.tenants(id),
    assignment_id uuid not null,
    ends_at timestamptz not null,
    created_by uuid not null references gba.users(id),
    created_at timestamptz not null default now(),
    creation_xid xid8 not null default pg_current_xact_id(),
    primary key (tenant_id, assignment_id),
    foreign key (tenant_id, assignment_id) references gba.transport_assignments (tenant_id, id)
);

-- The span of a trip: from its earliest window start to its latest window end.
create function gba.transport_trip_span(uuid, uuid) returns tstzrange
    language sql stable as $$
    select tstzrange(min(s.window_start), max(s.window_end), '[)')
    from gba.transport_stops s where s.tenant_id = $1 and s.trip_id = $2
$$;
revoke all on function gba.transport_trip_span(uuid, uuid) from public;
grant execute on function gba.transport_trip_span(uuid, uuid) to gba_runtime;

-- A driver or vehicle has its own active resource of its kind in its branch.
create function gba.guard_transport_driver() returns trigger language plpgsql as $$
begin
    if not exists (
        select 1 from gba.resources r
        where r.tenant_id = new.tenant_id and r.id = new.resource_id and r.kind = 'driver'
          and r.location_id = new.location_id and r.is_active
    ) then
        raise exception using errcode = 'check_violation',
            constraint = 'transport_drivers_resource_check',
            message = 'a driver has its own resource in its branch';
    end if;
    return new;
end;
$$;
revoke all on function gba.guard_transport_driver() from public;
create trigger transport_drivers_guard before insert on gba.transport_drivers
    for each row execute function gba.guard_transport_driver();
create function gba.guard_transport_vehicle() returns trigger language plpgsql as $$
begin
    if not exists (
        select 1 from gba.resources r
        where r.tenant_id = new.tenant_id and r.id = new.resource_id and r.kind = new.kind
          and r.location_id = new.location_id and r.is_active
    ) then
        raise exception using errcode = 'check_violation',
            constraint = 'transport_vehicles_resource_check',
            message = 'a vehicle has its own resource of its kind in its branch';
    end if;
    return new;
end;
$$;
revoke all on function gba.guard_transport_vehicle() from public;
create trigger transport_vehicles_guard before insert on gba.transport_vehicles
    for each row execute function gba.guard_transport_vehicle();

-- A transport resource belongs to its driver or vehicle and never changes.
create function gba.check_transport_resource() returns trigger language plpgsql as $$
begin
    if new.kind in ('driver', 'truck', 'trailer') and not exists (
        select 1 from gba.transport_drivers d
        where d.tenant_id = new.tenant_id and d.resource_id = new.id and new.kind = 'driver'
    ) and not exists (
        select 1 from gba.transport_vehicles v
        where v.tenant_id = new.tenant_id and v.resource_id = new.id and v.kind = new.kind
    ) then
        raise exception using errcode = 'check_violation',
            message = 'a transport resource requires its driver or vehicle';
    end if;
    return null;
end;
$$;
revoke all on function gba.check_transport_resource() from public;
create constraint trigger resources_transport_lane after insert on gba.resources
    deferrable initially deferred for each row execute function gba.check_transport_resource();
create function gba.protect_transport_resource() returns trigger language plpgsql as $$
begin
    if old.kind in ('driver', 'truck', 'trailer') or new.kind in ('driver', 'truck', 'trailer') then
        raise exception using errcode = 'check_violation',
            message = 'transport resources are owned by transport';
    end if;
    if tg_op = 'DELETE' then
        return old;
    end if;
    return new;
end;
$$;
revoke all on function gba.protect_transport_resource() from public;
create trigger resources_transport_protected before update or delete on gba.resources
    for each row execute function gba.protect_transport_resource();

-- An assignment starts inside the span of its planned trip, names an active resource of its role
-- in the trip's branch, and never overlaps another period of its role on that trip. The trip row
-- is locked first, so every period change of one trip is serialized, by the service or by SQL.
create function gba.guard_transport_assignment() returns trigger language plpgsql as $$
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
    if trip_status is distinct from 'planned' or span is null or isempty(span)
       or lower_inf(span) or upper_inf(span)
       or new.starts_at < lower(span) or new.starts_at >= upper(span) then
        raise exception using errcode = 'check_violation',
            constraint = 'transport_assignments_period_check',
            message = 'an assignment starts inside the span of a planned trip';
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
revoke all on function gba.guard_transport_assignment() from public;
create trigger transport_assignments_guard before insert on gba.transport_assignments
    for each row execute function gba.guard_transport_assignment();

-- An assignment ends once, inside its period and the trip's span.
create function gba.guard_transport_assignment_end() returns trigger language plpgsql as $$
declare
    started timestamptz;
    span tstzrange;
begin
    select a.starts_at, gba.transport_trip_span(a.tenant_id, a.trip_id) into started, span
      from gba.transport_assignments a
      join gba.transport_trips t on t.tenant_id = a.tenant_id and t.id = a.trip_id
     where a.tenant_id = new.tenant_id and a.id = new.assignment_id
       for update of t;
    if started is null or span is null or upper_inf(span)
       or new.ends_at < started or new.ends_at > upper(span) then
        raise exception using errcode = 'check_violation',
            constraint = 'transport_assignment_ends_period_check',
            message = 'an assignment ends inside its period';
    end if;
    return new;
end;
$$;
revoke all on function gba.guard_transport_assignment_end() from public;
create trigger transport_assignment_ends_guard before insert on gba.transport_assignment_ends
    for each row execute function gba.guard_transport_assignment_end();

-- At commit every assignment of a changed trip holds exactly its period: an open one from its
-- start to the span end (and starts inside the span), an ended one from its start to its end
-- (nothing when the period is empty).
create function gba.check_transport_trip_holds() returns trigger language plpgsql as $$
declare
    checked_tenant uuid;
    checked_trip uuid;
    span tstzrange;
begin
    if tg_table_name = 'transport_assignment_ends' then
        select a.tenant_id, a.trip_id into checked_tenant, checked_trip
          from gba.transport_assignments a
         where a.tenant_id = new.tenant_id and a.id = new.assignment_id;
    elsif tg_op = 'DELETE' then
        checked_tenant := old.tenant_id;
        checked_trip := old.trip_id;
    else
        checked_tenant := new.tenant_id;
        checked_trip := new.trip_id;
    end if;
    span := gba.transport_trip_span(checked_tenant, checked_trip);
    if exists (
        select 1
          from gba.transport_assignments a
          left join gba.transport_assignment_ends e
            on e.tenant_id = a.tenant_id and e.assignment_id = a.id
         cross join lateral (
             select case
                 when e.assignment_id is null and span is not null and not upper_inf(span)
                      and a.starts_at < upper(span)
                     then tstzrange(a.starts_at, upper(span), '[)')
                 when e.assignment_id is not null and e.ends_at > a.starts_at
                     then tstzrange(a.starts_at, e.ends_at, '[)')
             end as period
         ) p
         where a.tenant_id = checked_tenant and a.trip_id = checked_trip
           and (
               (e.assignment_id is null
                and (p.period is null or lower_inf(span) or a.starts_at < lower(span)))
               or array(
                   select r.during from gba.resource_allocations r
                    where r.tenant_id = a.tenant_id and r.source_kind = 'trip_assignment'
                      and r.source_id = a.id and r.state = 'confirmed'
                    order by r.during
               ) is distinct from (
                   case when p.period is null then array[]::tstzrange[] else array[p.period] end
               )
           )
    ) then
        raise exception using errcode = 'check_violation',
            constraint = 'transport_assignment_holds_check',
            message = 'every assignment holds exactly its period of the trip';
    end if;
    return null;
end;
$$;
revoke all on function gba.check_transport_trip_holds() from public;
create constraint trigger transport_assignments_holds after insert on gba.transport_assignments
    deferrable initially deferred for each row execute function gba.check_transport_trip_holds();
create constraint trigger transport_assignment_ends_holds
    after insert on gba.transport_assignment_ends
    deferrable initially deferred for each row execute function gba.check_transport_trip_holds();
create constraint trigger transport_stops_holds after insert or delete on gba.transport_stops
    deferrable initially deferred for each row execute function gba.check_transport_trip_holds();

-- The shared occupancy guard (0032) learns trip assignments: transport lanes take only trip
-- holds, a trip hold follows its exact assignment or end created in this transaction, and it is
-- released only by the transaction that ended its assignment.
create or replace function gba.guard_resource_allocation() returns trigger language plpgsql as $$
begin
    if tg_op = 'DELETE' then
        raise exception using errcode = 'check_violation',
            message = 'resource allocations are kept';
    end if;
    if tg_op = 'UPDATE' then
        if (new.tenant_id, new.id, new.resource_id, new.source_kind, new.source_id,
            new.during, new.created_at)
           is distinct from (old.tenant_id, old.id, old.resource_id, old.source_kind,
                             old.source_id, old.during, old.created_at) then
            raise exception using errcode = 'check_violation',
                message = 'an allocation keeps its resource, source and interval';
        end if;
        if new.state is distinct from old.state and not (
            (old.state = 'held' and new.state in ('confirmed', 'released'))
            or (old.state = 'confirmed' and new.state = 'released')
        ) then
            raise exception using errcode = 'check_violation',
                message = 'this allocation state change is not allowed';
        end if;
        new.updated_at := pg_catalog.now();
    end if;
    if new.source_kind = 'booking' and not exists (
        select 1 from gba.booking_allocations a
        where a.tenant_id = new.tenant_id and a.booking_id = new.source_id
          and a.resource_id = new.resource_id and a.during = new.during
          and gba.booking_occupancy_state(a.booking_status) = new.state
    ) then
        raise exception using errcode = 'check_violation',
            message = 'a booking allocation follows its booking';
    end if;
    if new.source_kind = 'reservation' then
        if tg_op = 'INSERT' and not exists (
            select 1 from gba.resource_reservations v
            join gba.resources r
              on r.tenant_id = v.tenant_id and r.location_id = v.location_id
            where v.tenant_id = new.tenant_id and v.id = new.source_id
              and v.status = 'active' and new.state = 'confirmed'
              -- Only in the transaction that created the reservation.
              and v.created_at = pg_catalog.now()
              and new.during = tstzrange(v.starts_at, v.ends_at, '[)')
              and r.id = new.resource_id and r.is_active
        ) then
            raise exception using errcode = 'check_violation',
                message = 'a reservation allocation follows its active reservation';
        end if;
        if tg_op = 'UPDATE' and new.state = 'released' and not exists (
            select 1 from gba.resource_reservations v
            where v.tenant_id = new.tenant_id and v.id = new.source_id
              and v.status = 'cancelled'
        ) then
            raise exception using errcode = 'check_violation',
                message = 'a reservation allocation is released by its cancellation';
        end if;
        -- Mirrored bookings are decided by the exclusion constraint; this only
        -- covers booking allocations a company has not copied yet.
        if tg_op = 'INSERT' and exists (
            select 1 from gba.booking_allocations a
            where a.tenant_id = new.tenant_id and a.resource_id = new.resource_id
              and a.booking_status in ('HOLD', 'CONFIRMED') and a.during && new.during
              and not exists (
                  select 1 from gba.resource_allocations c
                  where c.tenant_id = a.tenant_id and c.source_kind = 'booking'
                    and c.source_id = a.booking_id and c.resource_id = a.resource_id)
        ) then
            raise exception using errcode = 'exclusion_violation',
                constraint = 'resource_allocations_no_overlap',
                message = 'the resource is booked in this interval';
        end if;
    end if;

    if exists (select 1 from gba.resources r where r.tenant_id=new.tenant_id
        and r.id=new.resource_id and (r.kind='staff') <> (new.source_kind='shift')) then
        raise exception using errcode='23514', message='staff occupancy is only for shifts';
    end if;
    if new.source_kind='shift' then
        if tg_op='INSERT' and not exists (
            select 1 from gba.shift_assignments a join gba.work_shift_versions v
              on v.tenant_id=a.tenant_id and v.shift_id=a.shift_id and v.revision=a.shift_revision
              join gba.staff_profiles p on p.tenant_id=a.tenant_id and p.id=a.profile_id
             where a.tenant_id=new.tenant_id and a.id=new.source_id
               and p.resource_id=new.resource_id and v.profile_id=p.id and v.status='published'
               and a.creation_xid=pg_current_xact_id() and v.creation_xid=a.creation_xid
               and new.during=tstzrange(v.starts_at,v.ends_at,'[)') and new.state='confirmed'
        ) then
            raise exception using errcode='23514',
                message='a shift allocation follows its exact assignment';
        end if;
        if tg_op='UPDATE' and new.state='released' and not exists (
            select 1 from gba.shift_assignments a join gba.work_shift_versions v
              on v.tenant_id=a.tenant_id and v.shift_id=a.shift_id and v.revision>a.shift_revision
             where a.tenant_id=new.tenant_id and a.id=new.source_id
        ) then
            raise exception using errcode='23514',
                message='a shift allocation is released by a new version';
        end if;
    end if;
    if exists (select 1 from gba.resources r where r.tenant_id = new.tenant_id
        and r.id = new.resource_id
        and (r.kind in ('driver', 'truck', 'trailer'))
            <> (new.source_kind = 'trip_assignment')) then
        raise exception using errcode = '23514',
            message = 'transport occupancy is only for trip assignments';
    end if;
    if new.source_kind = 'trip_assignment' then
        if tg_op = 'INSERT' and not exists (
            select 1 from gba.transport_assignments a
             where a.tenant_id = new.tenant_id and a.id = new.source_id
               and a.resource_id = new.resource_id and new.state = 'confirmed'
               and (
                   (a.creation_xid = pg_current_xact_id()
                    and new.during = tstzrange(
                        a.starts_at, upper(gba.transport_trip_span(a.tenant_id, a.trip_id)), '[)'))
                   or exists (
                       select 1 from gba.transport_assignment_ends e
                        where e.tenant_id = a.tenant_id and e.assignment_id = a.id
                          and e.creation_xid = pg_current_xact_id()
                          and new.during = tstzrange(a.starts_at, e.ends_at, '[)'))
               )
        ) then
            raise exception using errcode = '23514',
                message = 'a trip allocation follows its exact assignment';
        end if;
        if tg_op = 'UPDATE' and new.state = 'released' and not exists (
            select 1 from gba.transport_assignment_ends e
             where e.tenant_id = new.tenant_id and e.assignment_id = new.source_id
               and e.creation_xid = pg_current_xact_id()
        ) then
            raise exception using errcode = '23514',
                message = 'a trip allocation is released by its end';
        end if;
    end if;
    return new;
end;
$$;

-- Writes need the transport module (ADR-0019 gate).
create trigger transport_drivers_module_gate before insert on gba.transport_drivers
    for each row execute function gba.require_enabled_module('transport');
create trigger transport_vehicles_module_gate before insert on gba.transport_vehicles
    for each row execute function gba.require_enabled_module('transport');
create trigger transport_assignments_module_gate before insert on gba.transport_assignments
    for each row execute function gba.require_enabled_module('transport');
create trigger transport_assignment_ends_module_gate before insert on gba.transport_assignment_ends
    for each row execute function gba.require_enabled_module('transport');

alter table gba.transport_drivers enable row level security;
alter table gba.transport_drivers force row level security;
alter table gba.transport_vehicles enable row level security;
alter table gba.transport_vehicles force row level security;
alter table gba.transport_assignments enable row level security;
alter table gba.transport_assignments force row level security;
alter table gba.transport_assignment_ends enable row level security;
alter table gba.transport_assignment_ends force row level security;
create policy transport_drivers_tenant_isolation on gba.transport_drivers
    using (tenant_id = gba.current_tenant_id())
    with check (tenant_id = gba.current_tenant_id());
create policy transport_vehicles_tenant_isolation on gba.transport_vehicles
    using (tenant_id = gba.current_tenant_id())
    with check (tenant_id = gba.current_tenant_id());
create policy transport_assignments_tenant_isolation on gba.transport_assignments
    using (tenant_id = gba.current_tenant_id())
    with check (tenant_id = gba.current_tenant_id());
create policy transport_assignment_ends_tenant_isolation on gba.transport_assignment_ends
    using (tenant_id = gba.current_tenant_id())
    with check (tenant_id = gba.current_tenant_id());
grant select on gba.transport_drivers, gba.transport_vehicles, gba.transport_assignments,
    gba.transport_assignment_ends to gba_runtime;
grant insert (tenant_id, id, location_id, resource_id, display_name, created_by)
    on gba.transport_drivers to gba_runtime;
grant insert (tenant_id, id, location_id, resource_id, kind, unit_number, created_by)
    on gba.transport_vehicles to gba_runtime;
grant insert (tenant_id, id, trip_id, role, resource_id, starts_at, replaces, created_by)
    on gba.transport_assignments to gba_runtime;
grant insert (tenant_id, assignment_id, ends_at, created_by)
    on gba.transport_assignment_ends to gba_runtime;

-- Transport assignment branch scope:
create policy transport_drivers_location_scope on gba.transport_drivers
    as restrictive to gba_runtime
    using (gba.current_location_id() is null or location_id = gba.current_location_id())
    with check (gba.current_location_id() is null or location_id = gba.current_location_id());
create policy transport_vehicles_location_scope on gba.transport_vehicles
    as restrictive to gba_runtime
    using (gba.current_location_id() is null or location_id = gba.current_location_id())
    with check (gba.current_location_id() is null or location_id = gba.current_location_id());
create policy transport_assignments_location_scope on gba.transport_assignments
    as restrictive to gba_runtime
    using (gba.current_location_id() is null or exists (
        select 1 from gba.transport_trips t
        where t.tenant_id = transport_assignments.tenant_id
          and t.id = transport_assignments.trip_id))
    with check (gba.current_location_id() is null or exists (
        select 1 from gba.transport_trips t
        where t.tenant_id = transport_assignments.tenant_id
          and t.id = transport_assignments.trip_id));
create policy transport_assignment_ends_location_scope on gba.transport_assignment_ends
    as restrictive to gba_runtime
    using (gba.current_location_id() is null or exists (
        select 1 from gba.transport_assignments a
        where a.tenant_id = transport_assignment_ends.tenant_id
          and a.id = transport_assignment_ends.assignment_id))
    with check (gba.current_location_id() is null or exists (
        select 1 from gba.transport_assignments a
        where a.tenant_id = transport_assignment_ends.tenant_id
          and a.id = transport_assignment_ends.assignment_id));
