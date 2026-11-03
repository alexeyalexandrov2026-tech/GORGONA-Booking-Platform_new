-- R3b (package R, RENT-01): rental unit blocks, moves between branches and availability.
-- docs/plan/PACKAGE_R3B_DESIGN_2026-11-03.md. A block takes a unit out of service for a period through a
-- confirmed hold on the shared occupancy, so it never overlaps an assignment; availability counts blocked
-- units; a unit with a current or future hold keeps its branch. Blocks and releases are insert-only.
alter table gba.resource_allocations drop constraint resource_allocations_source_kind;
alter table gba.resource_allocations add constraint resource_allocations_source_kind
    check (source_kind in ('booking', 'reservation', 'shift', 'trip_assignment', 'rental_assignment',
                           'rental_block'));

create table gba.rental_unit_blocks (
    tenant_id uuid not null references gba.tenants(id),
    id uuid not null,
    unit_id uuid not null,
    kind text not null constraint rental_unit_blocks_kind_check
        check (kind in ('maintenance', 'repair', 'other')),
    reason text not null constraint rental_unit_blocks_reason_check
        check (length(btrim(reason)) between 1 and 500),
    starts_at timestamptz not null,
    ends_at timestamptz not null,
    created_by uuid not null references gba.users(id),
    created_at timestamptz not null default now(),
    creation_xid xid8 not null default pg_current_xact_id(),
    primary key (tenant_id, id),
    foreign key (tenant_id, unit_id) references gba.rental_units (tenant_id, id),
    constraint rental_unit_blocks_period_check
        check (ends_at > starts_at and ends_at - starts_at <= interval '366 days')
);
create table gba.rental_unit_block_releases (
    tenant_id uuid not null references gba.tenants(id),
    block_id uuid not null,
    reason text not null constraint rental_unit_block_releases_reason_check
        check (length(btrim(reason)) between 1 and 500),
    released_by uuid not null references gba.users(id),
    released_at timestamptz not null default now(),
    creation_xid xid8 not null default pg_current_xact_id(),
    primary key (tenant_id, block_id),
    foreign key (tenant_id, block_id) references gba.rental_unit_blocks (tenant_id, id)
);

-- The peak at one instant of bookings of a class at a pickup branch plus the blocked units of that class
-- there, cancelled bookings and released blocks left out. 0097 counted bookings only.
create or replace function gba.rental_booking_peak(
    p_tenant uuid, p_class uuid, p_location uuid, p_starts timestamptz, p_ends timestamptz
) returns integer language sql stable as $$
    select coalesce(max((
        select count(*) from gba.rental_bookings b
        where b.tenant_id = p_tenant and b.class_id = p_class and b.pickup_location_id = p_location
          and b.starts_at <= point.at and b.ends_at > point.at
          and not exists (
              select 1 from gba.rental_booking_cancellations c
              where c.tenant_id = b.tenant_id and c.booking_id = b.id)
    ) + (
        select count(*) from gba.rental_unit_blocks k
          join gba.rental_units u on u.tenant_id = k.tenant_id and u.id = k.unit_id
        where k.tenant_id = p_tenant and u.class_id = p_class and u.location_id = p_location
          and k.starts_at <= point.at and k.ends_at > point.at
          and not exists (
              select 1 from gba.rental_unit_block_releases l
              where l.tenant_id = k.tenant_id and l.block_id = k.id)
    )), 0)::integer
    from (
        select p_starts as at
        union
        select b.starts_at from gba.rental_bookings b
        where b.tenant_id = p_tenant and b.class_id = p_class and b.pickup_location_id = p_location
          and b.starts_at > p_starts and b.starts_at < p_ends
        union
        select k.starts_at from gba.rental_unit_blocks k
          join gba.rental_units u on u.tenant_id = k.tenant_id and u.id = k.unit_id
        where k.tenant_id = p_tenant and u.class_id = p_class and u.location_id = p_location
          and k.starts_at > p_starts and k.starts_at < p_ends
    ) point;
$$;

-- A block names an active unit and leaves every booking of its class at its branch a unit; the check runs
-- under the class lock, as bookings do.
create function gba.guard_rental_unit_block() returns trigger language plpgsql as $$
declare
    unit record;
    units integer;
begin
    select u.class_id, u.location_id, u.state into unit from gba.rental_units u
    where u.tenant_id = new.tenant_id and u.id = new.unit_id;
    perform 1 from gba.rental_classes c
    where c.tenant_id = new.tenant_id and c.id = unit.class_id for update;
    if unit.state is distinct from 'active' then
        raise exception using errcode = 'check_violation',
            constraint = 'rental_unit_blocks_unit_check',
            message = 'a block names an active unit';
    end if;
    select count(*) into units from gba.rental_units u
    where u.tenant_id = new.tenant_id and u.class_id = unit.class_id
      and u.location_id = unit.location_id and u.state = 'active';
    if gba.rental_booking_peak(new.tenant_id, unit.class_id, unit.location_id,
                               new.starts_at, new.ends_at) + 1 > units then
        raise exception using errcode = 'check_violation',
            constraint = 'rental_unit_blocks_availability_check',
            message = 'a block leaves every booking of its class a unit';
    end if;
    return new;
end;
$$;
revoke all on function gba.guard_rental_unit_block() from public;
create trigger rental_unit_blocks_guard
    before insert on gba.rental_unit_blocks
    for each row execute function gba.guard_rental_unit_block();

-- At commit, a block holds its unit, and a released block has released its hold.
create function gba.check_rental_unit_block_hold() returns trigger language plpgsql as $$
begin
    if not exists (
        select 1 from gba.resource_allocations x
        where x.tenant_id = new.tenant_id and x.source_kind = 'rental_block' and x.source_id = new.id
    ) then
        raise exception using errcode = 'check_violation',
            constraint = 'rental_unit_blocks_hold_check',
            message = 'a block holds its unit';
    end if;
    return null;
end;
$$;
revoke all on function gba.check_rental_unit_block_hold() from public;
create constraint trigger rental_unit_blocks_hold
    after insert on gba.rental_unit_blocks
    deferrable initially deferred
    for each row execute function gba.check_rental_unit_block_hold();
create function gba.check_rental_unit_block_released() returns trigger language plpgsql as $$
begin
    if exists (
        select 1 from gba.resource_allocations x
        where x.tenant_id = new.tenant_id and x.source_kind = 'rental_block'
          and x.source_id = new.block_id and x.state <> 'released'
    ) then
        raise exception using errcode = 'check_violation',
            constraint = 'rental_unit_block_releases_hold_check',
            message = 'a released block releases its hold';
    end if;
    return null;
end;
$$;
revoke all on function gba.check_rental_unit_block_released() from public;
create constraint trigger rental_unit_block_releases_hold
    after insert on gba.rental_unit_block_releases
    deferrable initially deferred
    for each row execute function gba.check_rental_unit_block_released();

-- The unit guard (0096) learns moves: a unit with a current or future hold keeps its branch. The 0096 body
-- is kept whole.
create or replace function gba.guard_rental_unit() returns trigger language plpgsql as $$
begin
    if tg_op = 'INSERT' then
        if new.revision <> 1 then
            raise exception using errcode = 'check_violation',
                constraint = 'rental_units_revision_sequence_check',
                message = 'a unit starts at revision 1';
        end if;
        return new;
    end if;
    if old.state = 'retired' then
        raise exception using errcode = 'check_violation',
            constraint = 'rental_units_retired_check',
            message = 'a retired unit takes no new revision';
    end if;
    if new.class_id <> old.class_id or new.identifier <> old.identifier
       or new.revision <> old.revision + 1 then
        raise exception using errcode = 'check_violation',
            constraint = 'rental_units_revision_sequence_check',
            message = 'a unit keeps its class and identifier and takes the next revision';
    end if;
    if new.location_id <> old.location_id and exists (
        select 1 from gba.resource_allocations x
        where x.tenant_id = new.tenant_id and x.resource_id = old.resource_id
          and x.state in ('held', 'confirmed') and upper(x.during) > now()
    ) then
        raise exception using errcode = 'check_violation',
            constraint = 'rental_units_held_check',
            message = 'a unit with a current or future hold keeps its branch';
    end if;
    return new;
end;
$$;

-- The shared occupancy guard (0098) learns rental blocks: rental resources take rental assignment and block
-- holds only, a block hold follows its exact block created in this transaction, and it is released only by
-- the transaction that released its block. The 0098 body is kept whole.
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
        and (r.kind = 'rental_unit')
            <> (new.source_kind in ('rental_assignment', 'rental_block'))) then
        raise exception using errcode = '23514',
            message = 'rental occupancy is only for rental assignments and blocks';
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
    if new.source_kind = 'rental_block' then
        if tg_op = 'INSERT' and not exists (
            select 1 from gba.rental_unit_blocks b
              join gba.rental_units u on u.tenant_id = b.tenant_id and u.id = b.unit_id
             where b.tenant_id = new.tenant_id and b.id = new.source_id
               and u.resource_id = new.resource_id and new.state = 'confirmed'
               and b.creation_xid = pg_current_xact_id()
               and new.during = tstzrange(b.starts_at, b.ends_at, '[)')
        ) then
            raise exception using errcode = '23514',
                message = 'a rental block hold follows its exact block';
        end if;
        if tg_op = 'UPDATE' and new.state = 'released' and not exists (
            select 1 from gba.rental_unit_block_releases l
             where l.tenant_id = new.tenant_id and l.block_id = new.source_id
               and l.creation_xid = pg_current_xact_id()
        ) then
            raise exception using errcode = '23514',
                message = 'a rental block hold is released by its release';
        end if;
    end if;
    return new;
end;
$$;

-- Writes need the rental module (ADR-0019 gate).
create trigger rental_unit_blocks_module_gate
    before insert on gba.rental_unit_blocks
    for each row execute function gba.require_enabled_module('rental');
create trigger rental_unit_block_releases_module_gate
    before insert on gba.rental_unit_block_releases
    for each row execute function gba.require_enabled_module('rental');

alter table gba.rental_unit_blocks enable row level security;
alter table gba.rental_unit_blocks force row level security;
alter table gba.rental_unit_block_releases enable row level security;
alter table gba.rental_unit_block_releases force row level security;
create policy rental_unit_blocks_tenant_isolation on gba.rental_unit_blocks
    using (tenant_id = gba.current_tenant_id())
    with check (tenant_id = gba.current_tenant_id());
create policy rental_unit_block_releases_tenant_isolation on gba.rental_unit_block_releases
    using (tenant_id = gba.current_tenant_id())
    with check (tenant_id = gba.current_tenant_id());
grant select, insert on gba.rental_unit_blocks, gba.rental_unit_block_releases to gba_runtime;

-- Rental branch scope:
create policy rental_unit_blocks_location_scope on gba.rental_unit_blocks
    as restrictive to gba_runtime
    using (gba.current_location_id() is null or exists (
        select 1 from gba.rental_units u
        where u.tenant_id = rental_unit_blocks.tenant_id and u.id = rental_unit_blocks.unit_id))
    with check (gba.current_location_id() is null or exists (
        select 1 from gba.rental_units u
        where u.tenant_id = rental_unit_blocks.tenant_id and u.id = rental_unit_blocks.unit_id));
create policy rental_unit_block_releases_location_scope on gba.rental_unit_block_releases
    as restrictive to gba_runtime
    using (gba.current_location_id() is null or exists (
        select 1 from gba.rental_unit_blocks b
        where b.tenant_id = rental_unit_block_releases.tenant_id
          and b.id = rental_unit_block_releases.block_id))
    with check (gba.current_location_id() is null or exists (
        select 1 from gba.rental_unit_blocks b
        where b.tenant_id = rental_unit_block_releases.tenant_id
          and b.id = rental_unit_block_releases.block_id));
