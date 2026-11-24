-- R3a (package R, RENT-01): rental units on the shared occupancy (ADR-0022) and their assignment to bookings.
-- docs/plan/PACKAGE_R3A_DESIGN_2026-11-03.md. Every unit has its own resource of kind rental_unit in its branch;
-- an assignment holds that resource for the booking period through one confirmed allocation, so the
-- exclusion constraint of 0018 makes a double issue impossible. Assignments and releases are insert-only.
alter table gba.resources drop constraint resources_kind_valid;
alter table gba.resources add constraint resources_kind_valid
    check (kind in ('artist', 'chair', 'room', 'staff', 'equipment', 'driver', 'truck', 'trailer',
                    'rental_unit'));
alter table gba.resource_allocations drop constraint resource_allocations_source_kind;
alter table gba.resource_allocations add constraint resource_allocations_source_kind
    check (source_kind in ('booking', 'reservation', 'shift', 'trip_assignment', 'rental_assignment'));

-- No unit can exist yet: rental has never been enableable, and migrations never lift row security
-- to fill other companies' rows. Setting the column not null refuses the upgrade loudly if a unit did
-- exist. From here on a unit is never without its own resource.
alter table gba.rental_units add column resource_id uuid;
alter table gba.rental_units alter column resource_id set not null;
alter table gba.rental_units add constraint rental_units_resource_unique unique (tenant_id, resource_id);
alter table gba.rental_units add constraint rental_units_resource_fk
    foreign key (tenant_id, resource_id) references gba.resources (tenant_id, id);

-- At commit, a unit's resource is a rental resource in the unit's branch, active while the unit is.
create function gba.check_rental_unit_resource() returns trigger language plpgsql as $$
begin
    if not exists (
        select 1 from gba.resources r
        where r.tenant_id = new.tenant_id and r.id = new.resource_id and r.kind = 'rental_unit'
          and r.location_id = new.location_id and r.is_active = (new.state = 'active')
    ) then
        raise exception using errcode = 'check_violation',
            constraint = 'rental_units_resource_check',
            message = 'a unit has its own rental resource in its branch, active while the unit is';
    end if;
    return null;
end;
$$;
revoke all on function gba.check_rental_unit_resource() from public;
create constraint trigger rental_units_resource
    after insert or update on gba.rental_units
    deferrable initially deferred
    for each row execute function gba.check_rental_unit_resource();

create table gba.rental_assignments (
    tenant_id uuid not null references gba.tenants(id),
    id uuid not null,
    booking_id uuid not null,
    unit_id uuid not null,
    starts_at timestamptz not null,
    ends_at timestamptz not null,
    assigned_by uuid not null references gba.users(id),
    assigned_at timestamptz not null default now(),
    creation_xid xid8 not null default pg_current_xact_id(),
    primary key (tenant_id, id),
    foreign key (tenant_id, booking_id) references gba.rental_bookings (tenant_id, id),
    foreign key (tenant_id, unit_id) references gba.rental_units (tenant_id, id),
    constraint rental_assignments_period_check check (ends_at > starts_at)
);
create table gba.rental_assignment_releases (
    tenant_id uuid not null references gba.tenants(id),
    assignment_id uuid not null,
    reason text not null constraint rental_assignment_releases_reason_check
        check (reason in ('replaced', 'cancelled')),
    released_by uuid not null references gba.users(id),
    released_at timestamptz not null default now(),
    creation_xid xid8 not null default pg_current_xact_id(),
    primary key (tenant_id, assignment_id),
    foreign key (tenant_id, assignment_id) references gba.rental_assignments (tenant_id, id)
);

-- An assignment names an active unit of the booked class at the pickup branch for the whole period of a
-- booking that is not cancelled, and only once the booking's earlier assignment is released.
create function gba.guard_rental_assignment() returns trigger language plpgsql as $$
begin
    if not exists (
        select 1 from gba.rental_bookings b
          join gba.rental_units u on u.tenant_id = b.tenant_id and u.id = new.unit_id
         where b.tenant_id = new.tenant_id and b.id = new.booking_id
           and u.class_id = b.class_id and u.location_id = b.pickup_location_id
           and u.state = 'active' and new.starts_at = b.starts_at and new.ends_at = b.ends_at
           and not exists (
               select 1 from gba.rental_booking_cancellations c
               where c.tenant_id = b.tenant_id and c.booking_id = b.id)
    ) then
        raise exception using errcode = 'check_violation',
            constraint = 'rental_assignments_booking_check',
            message = 'an assignment names a suitable unit for a booking that is not cancelled';
    end if;
    if exists (
        select 1 from gba.rental_assignments a
        where a.tenant_id = new.tenant_id and a.booking_id = new.booking_id
          and not exists (
              select 1 from gba.rental_assignment_releases l
              where l.tenant_id = a.tenant_id and l.assignment_id = a.id)
    ) then
        raise exception using errcode = 'check_violation',
            constraint = 'rental_assignments_current_check',
            message = 'a booking has one current assignment';
    end if;
    return new;
end;
$$;
revoke all on function gba.guard_rental_assignment() from public;
create trigger rental_assignments_guard
    before insert on gba.rental_assignments
    for each row execute function gba.guard_rental_assignment();

-- At commit, an assignment holds its unit through its allocation.
create function gba.check_rental_assignment_hold() returns trigger language plpgsql as $$
begin
    if not exists (
        select 1 from gba.resource_allocations x
        where x.tenant_id = new.tenant_id and x.source_kind = 'rental_assignment'
          and x.source_id = new.id
    ) then
        raise exception using errcode = 'check_violation',
            constraint = 'rental_assignments_hold_check',
            message = 'an assignment holds its unit';
    end if;
    return null;
end;
$$;
revoke all on function gba.check_rental_assignment_hold() from public;
create constraint trigger rental_assignments_hold
    after insert on gba.rental_assignments
    deferrable initially deferred
    for each row execute function gba.check_rental_assignment_hold();

-- A cancellation release needs the booking's cancellation; at commit, the hold of a released assignment
-- is released.
create function gba.guard_rental_assignment_release() returns trigger language plpgsql as $$
begin
    if new.reason = 'cancelled' and not exists (
        select 1 from gba.rental_assignments a
          join gba.rental_booking_cancellations c
            on c.tenant_id = a.tenant_id and c.booking_id = a.booking_id
         where a.tenant_id = new.tenant_id and a.id = new.assignment_id
    ) then
        raise exception using errcode = 'check_violation',
            constraint = 'rental_assignment_releases_reason_check',
            message = 'a cancellation release follows the cancellation of the booking';
    end if;
    return new;
end;
$$;
revoke all on function gba.guard_rental_assignment_release() from public;
create trigger rental_assignment_releases_guard
    before insert on gba.rental_assignment_releases
    for each row execute function gba.guard_rental_assignment_release();
create function gba.check_rental_assignment_released() returns trigger language plpgsql as $$
begin
    if exists (
        select 1 from gba.resource_allocations x
        where x.tenant_id = new.tenant_id and x.source_kind = 'rental_assignment'
          and x.source_id = new.assignment_id and x.state <> 'released'
    ) then
        raise exception using errcode = 'check_violation',
            constraint = 'rental_assignment_releases_hold_check',
            message = 'a released assignment releases its hold';
    end if;
    return null;
end;
$$;
revoke all on function gba.check_rental_assignment_released() from public;
create constraint trigger rental_assignment_releases_hold
    after insert on gba.rental_assignment_releases
    deferrable initially deferred
    for each row execute function gba.check_rental_assignment_released();

-- The shared occupancy guard (0075) learns rental assignments: rental resources take only rental
-- assignment holds, a rental hold follows its exact assignment created in this transaction, and it is
-- released only by the transaction that released its assignment. The 0075 body is kept whole.
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
    if exists (select 1 from gba.resources r where r.tenant_id = new.tenant_id
        and r.id = new.resource_id
        and (r.kind = 'rental_unit') <> (new.source_kind = 'rental_assignment')) then
        raise exception using errcode = '23514',
            message = 'rental occupancy is only for rental assignments';
    end if;
    if new.source_kind = 'rental_assignment' then
        if tg_op = 'INSERT' and not exists (
            select 1 from gba.rental_assignments a
              join gba.rental_units u on u.tenant_id = a.tenant_id and u.id = a.unit_id
             where a.tenant_id = new.tenant_id and a.id = new.source_id
               and u.resource_id = new.resource_id and new.state = 'confirmed'
               and a.creation_xid = pg_current_xact_id()
               and new.during = tstzrange(a.starts_at, a.ends_at, '[)')
        ) then
            raise exception using errcode = '23514',
                message = 'a rental allocation follows its exact assignment';
        end if;
        if tg_op = 'UPDATE' and new.state = 'released' and not exists (
            select 1 from gba.rental_assignment_releases l
             where l.tenant_id = new.tenant_id and l.assignment_id = new.source_id
               and l.creation_xid = pg_current_xact_id()
        ) then
            raise exception using errcode = '23514',
                message = 'a rental allocation is released by its release';
        end if;
    end if;
    return new;
end;
$$;

-- Writes need the rental module (ADR-0019 gate).
create trigger rental_assignments_module_gate
    before insert on gba.rental_assignments
    for each row execute function gba.require_enabled_module('rental');
create trigger rental_assignment_releases_module_gate
    before insert on gba.rental_assignment_releases
    for each row execute function gba.require_enabled_module('rental');

alter table gba.rental_assignments enable row level security;
alter table gba.rental_assignments force row level security;
alter table gba.rental_assignment_releases enable row level security;
alter table gba.rental_assignment_releases force row level security;
create policy rental_assignments_tenant_isolation on gba.rental_assignments
    using (tenant_id = gba.current_tenant_id())
    with check (tenant_id = gba.current_tenant_id());
create policy rental_assignment_releases_tenant_isolation on gba.rental_assignment_releases
    using (tenant_id = gba.current_tenant_id())
    with check (tenant_id = gba.current_tenant_id());
grant select, insert on gba.rental_assignments, gba.rental_assignment_releases to gba_runtime;

-- Rental branch scope:
create policy rental_assignments_location_scope on gba.rental_assignments
    as restrictive to gba_runtime
    using (gba.current_location_id() is null or exists (
        select 1 from gba.rental_bookings b
        where b.tenant_id = rental_assignments.tenant_id and b.id = rental_assignments.booking_id))
    with check (gba.current_location_id() is null or exists (
        select 1 from gba.rental_bookings b
        where b.tenant_id = rental_assignments.tenant_id and b.id = rental_assignments.booking_id));
create policy rental_assignment_releases_location_scope on gba.rental_assignment_releases
    as restrictive to gba_runtime
    using (gba.current_location_id() is null or exists (
        select 1 from gba.rental_assignments a
        where a.tenant_id = rental_assignment_releases.tenant_id
          and a.id = rental_assignment_releases.assignment_id))
    with check (gba.current_location_id() is null or exists (
        select 1 from gba.rental_assignments a
        where a.tenant_id = rental_assignment_releases.tenant_id
          and a.id = rental_assignment_releases.assignment_id));
