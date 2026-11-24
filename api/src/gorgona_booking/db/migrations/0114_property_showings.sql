-- PROPERTY-01 2b: authenticated showings use the shared resource allocations.
alter table gba.resources drop constraint resources_kind_valid;
alter table gba.resources add constraint resources_kind_valid
    check (kind in ('artist','chair','room','staff','equipment','driver','truck','trailer',
                    'rental_unit','property_object'));
alter table gba.resource_allocations drop constraint resource_allocations_source_kind;
alter table gba.resource_allocations add constraint resource_allocations_source_kind
    check (source_kind in ('booking','reservation','shift','trip_assignment','rental_assignment',
                           'rental_block','property_showing'));

create table gba.property_showing_resources (
    tenant_id uuid not null,
    object_id uuid not null,
    location_id uuid not null,
    object_kind text not null,
    resource_id uuid not null,
    primary key (tenant_id, object_id),
    unique (tenant_id, resource_id),
    unique (tenant_id, object_id, location_id, resource_id),
    foreign key (tenant_id, object_id, location_id, object_kind)
        references gba.property_objects (tenant_id, id, location_id, kind),
    foreign key (tenant_id, resource_id) references gba.resources (tenant_id, id)
);

create table gba.property_showings (
    tenant_id uuid not null,
    id uuid not null,
    object_id uuid not null,
    location_id uuid not null,
    object_resource_id uuid not null,
    host_resource_id uuid,
    prospect_id uuid not null,
    starts_at timestamptz not null,
    ends_at timestamptz not null,
    recorded_by uuid not null references gba.users (id),
    recorded_at timestamptz not null default clock_timestamp(),
    creation_xid xid8 not null default pg_current_xact_id(),
    primary key (tenant_id, id),
    foreign key (tenant_id, object_id, location_id, object_resource_id)
        references gba.property_showing_resources (tenant_id, object_id, location_id, resource_id),
    constraint property_showings_prospect_fk foreign key (tenant_id, prospect_id)
        references gba.counterparties (tenant_id, id),
    foreign key (tenant_id, host_resource_id) references gba.resources (tenant_id, id),
    check (isfinite(starts_at) and isfinite(ends_at)
           and ends_at > starts_at and ends_at - starts_at <= interval '744 hours'),
    check (host_resource_id is null or host_resource_id <> object_resource_id)
);
create index property_showings_location_id_index on gba.property_showings (tenant_id, location_id, id);

create table gba.property_showing_cancellations (
    tenant_id uuid not null,
    showing_id uuid not null,
    cancelled_by uuid not null references gba.users (id),
    cancelled_at timestamptz not null default clock_timestamp(),
    creation_xid xid8 not null default pg_current_xact_id(),
    primary key (tenant_id, showing_id),
    foreign key (tenant_id, showing_id) references gba.property_showings (tenant_id, id)
);

create function gba.guard_property_showing_resource() returns trigger language plpgsql as $$
begin
    if not exists (
        select 1 from gba.resources r
        where r.tenant_id = new.tenant_id and r.id = new.resource_id
          and r.location_id = new.location_id and r.kind = 'property_object' and r.is_active
    ) then
        raise exception using errcode = '23514',
            message = 'a showing object has its branch resource';
    end if;
    return new;
end;
$$;
revoke all on function gba.guard_property_showing_resource() from public;
create trigger property_showing_resources_guard before insert on gba.property_showing_resources
    for each row execute function gba.guard_property_showing_resource();

create function gba.keep_property_resource_identity() returns trigger language plpgsql as $$
begin
    if (old.kind = 'property_object' or new.kind = 'property_object') and
       (old.tenant_id, old.id, old.location_id, old.kind, old.is_active) is distinct from
       (new.tenant_id, new.id, new.location_id, new.kind, new.is_active) then
        raise exception using errcode = '23514', message = 'a property resource keeps its identity';
    end if;
    return new;
end;
$$;
revoke all on function gba.keep_property_resource_identity() from public;
create trigger resources_keep_property_identity before update on gba.resources
    for each row execute function gba.keep_property_resource_identity();

create function gba.check_property_showing_allocated() returns trigger language plpgsql as $$
begin
    if (
        select count(*) from gba.resource_allocations a
        where a.tenant_id = new.tenant_id and a.source_kind = 'property_showing'
          and a.source_id = new.id
    ) <> (case when new.host_resource_id is null then 1 else 2 end) then
        raise exception using errcode = '23514', message = 'a showing requires all its allocations';
    end if;
    return null;
end;
$$;
revoke all on function gba.check_property_showing_allocated() from public;
create constraint trigger property_showings_allocated after insert on gba.property_showings
    deferrable initially deferred for each row execute function gba.check_property_showing_allocated();

create function gba.release_property_showing() returns trigger language plpgsql as $$
declare
    released integer;
    expected integer;
begin
    select case when s.host_resource_id is null then 1 else 2 end into strict expected
    from gba.property_showings s where s.tenant_id = new.tenant_id and s.id = new.showing_id;
    update gba.resource_allocations set state = 'released'
    where tenant_id = new.tenant_id and source_kind = 'property_showing'
      and source_id = new.showing_id and state = 'confirmed';
    get diagnostics released = row_count;
    if released <> expected then
        raise exception using errcode = '23514', message = 'cancellation releases all allocations';
    end if;
    return null;
end;
$$;
revoke all on function gba.release_property_showing() from public;
create trigger property_showing_cancellations_release
    after insert on gba.property_showing_cancellations
    for each row execute function gba.release_property_showing();
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
    if exists (
        select 1 from gba.resources r where r.tenant_id = new.tenant_id
          and r.id = new.resource_id and r.kind = 'property_object'
          and new.source_kind <> 'property_showing'
    ) then
        raise exception using errcode = '23514',
            message = 'a property object resource is reserved only for showings';
    end if;
    if new.source_kind = 'property_showing' then
        if tg_op = 'INSERT' and not exists (
            select 1 from gba.property_showings s join gba.resources r on r.tenant_id = s.tenant_id
             where s.tenant_id = new.tenant_id and s.id = new.source_id
               and r.id = new.resource_id and r.location_id = s.location_id and r.is_active
               and ((s.object_resource_id = r.id and r.kind = 'property_object')
                    or (s.host_resource_id = r.id and r.kind = 'artist'))
               and s.creation_xid = pg_current_xact_id()
               and new.during = tstzrange(s.starts_at, s.ends_at, '[)') and new.state = 'confirmed'
        ) then
            raise exception using errcode = '23514', message = 'an allocation follows its showing';
        end if;
        if tg_op = 'UPDATE' and new.state = 'released' and not exists (
            select 1 from gba.property_showing_cancellations c
             where c.tenant_id = new.tenant_id and c.showing_id = new.source_id
               and c.creation_xid = pg_current_xact_id()
        ) then
            raise exception using errcode = '23514',
                message = 'a showing release requires cancellation';
        end if;
        if tg_op = 'INSERT' and exists (
            select 1 from gba.booking_allocations a
             where a.tenant_id = new.tenant_id and a.resource_id = new.resource_id
               and a.booking_status in ('HOLD', 'CONFIRMED') and a.during && new.during
        ) then
            raise exception using errcode = 'exclusion_violation',
                constraint = 'resource_allocations_no_overlap',
                message = 'the resource is booked in this interval';
        end if;
    end if;
    return new;
end;
$$;


alter table gba.property_showing_resources enable row level security;
alter table gba.property_showing_resources force row level security;
create policy property_showing_resources_tenant_isolation on gba.property_showing_resources
    using (tenant_id = gba.current_tenant_id()) with check (tenant_id = gba.current_tenant_id());
grant select, insert on gba.property_showing_resources to gba_runtime;
create trigger property_showing_resources_require_module before insert on gba.property_showing_resources
    for each row execute function gba.require_enabled_module('property');

alter table gba.property_showings enable row level security;
alter table gba.property_showings force row level security;
create policy property_showings_tenant_isolation on gba.property_showings
    using (tenant_id = gba.current_tenant_id()) with check (tenant_id = gba.current_tenant_id());
grant select, insert on gba.property_showings to gba_runtime;
create trigger property_showings_require_module before insert on gba.property_showings
    for each row execute function gba.require_enabled_module('property');

alter table gba.property_showing_cancellations enable row level security;
alter table gba.property_showing_cancellations force row level security;
create policy property_showing_cancellations_tenant_isolation on gba.property_showing_cancellations
    using (tenant_id = gba.current_tenant_id()) with check (tenant_id = gba.current_tenant_id());
grant select, insert on gba.property_showing_cancellations to gba_runtime;

-- Property showing branch scope:
create policy property_showing_resources_location_scope on gba.property_showing_resources as restrictive to gba_runtime
    using (gba.current_location_id() is null or location_id = gba.current_location_id())
    with check (gba.current_location_id() is null or location_id = gba.current_location_id());
create policy property_showing_resources_unrestricted_insert on gba.property_showing_resources
    as restrictive for insert to gba_runtime with check (gba.current_location_id() is null);

create policy property_showings_location_scope on gba.property_showings as restrictive to gba_runtime
    using (gba.current_location_id() is null or location_id = gba.current_location_id())
    with check (gba.current_location_id() is null or location_id = gba.current_location_id());
create policy property_showings_unrestricted_insert on gba.property_showings
    as restrictive for insert to gba_runtime with check (gba.current_location_id() is null);

create policy property_showing_cancellations_location_scope on gba.property_showing_cancellations as restrictive to gba_runtime
    using (gba.current_location_id() is null or exists (
        select 1 from gba.property_showings s
        where s.tenant_id = property_showing_cancellations.tenant_id
          and s.id = property_showing_cancellations.showing_id))
    with check (gba.current_location_id() is null or exists (
        select 1 from gba.property_showings s
        where s.tenant_id = property_showing_cancellations.tenant_id
          and s.id = property_showing_cancellations.showing_id));
create policy property_showing_cancellations_unrestricted_insert on gba.property_showing_cancellations
    as restrictive for insert to gba_runtime with check (gba.current_location_id() is null);
