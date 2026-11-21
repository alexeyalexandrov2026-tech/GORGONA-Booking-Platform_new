-- REST-01 Slice 1 (ADR-0037): branch dining areas, tables and independent table reservations.
-- Invoker rights only.

alter table gba.resources drop constraint resources_kind_valid;
alter table gba.resources add constraint resources_kind_valid
    check (kind in ('artist','chair','room','staff','equipment','driver','truck','trailer',
                    'rental_unit','property_object','restaurant_table'));

alter table gba.resource_allocations drop constraint resource_allocations_source_kind;
alter table gba.resource_allocations add constraint resource_allocations_source_kind
    check (source_kind in ('booking','reservation','shift','trip_assignment','rental_assignment',
                           'rental_block','property_showing','restaurant_reservation'));

create table gba.restaurant_areas (
    tenant_id uuid not null,
    id uuid not null,
    location_id uuid not null,
    name text not null check (char_length(btrim(name)) between 1 and 120),
    service_style text not null check (service_style in ('dining', 'bar', 'patio', 'private')),
    revision integer not null check (revision >= 1),
    is_active boolean not null default true,
    recorded_by uuid not null references gba.users (id),
    recorded_at timestamptz not null default clock_timestamp(),
    primary key (tenant_id, id),
    unique (tenant_id, id, location_id),
    foreign key (tenant_id, location_id) references gba.locations (tenant_id, id)
);
create index restaurant_areas_location_id_idx on gba.restaurant_areas (tenant_id, location_id, id);

create table gba.restaurant_area_revisions (
    tenant_id uuid not null,
    area_id uuid not null,
    revision integer not null check (revision >= 1),
    location_id uuid not null,
    name text not null check (char_length(btrim(name)) between 1 and 120),
    service_style text not null check (service_style in ('dining', 'bar', 'patio', 'private')),
    is_active boolean not null,
    recorded_by uuid not null references gba.users (id),
    recorded_at timestamptz not null default clock_timestamp(),
    primary key (tenant_id, area_id, revision),
    foreign key (tenant_id, area_id, location_id)
        references gba.restaurant_areas (tenant_id, id, location_id)
);

create table gba.restaurant_tables (
    tenant_id uuid not null,
    id uuid not null,
    location_id uuid not null,
    area_id uuid not null,
    resource_id uuid not null,
    code text not null check (char_length(btrim(code)) between 1 and 32),
    min_covers integer not null check (min_covers between 1 and 100),
    max_covers integer not null check (max_covers between min_covers and 100),
    revision integer not null check (revision >= 1),
    is_active boolean not null default true,
    recorded_by uuid not null references gba.users (id),
    recorded_at timestamptz not null default clock_timestamp(),
    primary key (tenant_id, id),
    unique (tenant_id, resource_id),
    unique (tenant_id, location_id, code),
    unique (tenant_id, id, location_id, resource_id),
    foreign key (tenant_id, location_id) references gba.locations (tenant_id, id),
    foreign key (tenant_id, area_id, location_id)
        references gba.restaurant_areas (tenant_id, id, location_id),
    foreign key (tenant_id, resource_id) references gba.resources (tenant_id, id)
);
create index restaurant_tables_location_area_idx
    on gba.restaurant_tables (tenant_id, location_id, area_id, id);

create table gba.restaurant_table_reservations (
    tenant_id uuid not null,
    id uuid not null,
    location_id uuid not null,
    table_id uuid not null,
    table_resource_id uuid not null,
    guest_counterparty_id uuid,
    guest_name text not null check (char_length(btrim(guest_name)) between 1 and 120),
    party_size integer not null check (party_size between 1 and 100),
    starts_at timestamptz not null,
    ends_at timestamptz not null,
    note text check (note is null or char_length(btrim(note)) between 1 and 1000),
    status text not null check (status in ('booked', 'seated', 'completed', 'cancelled', 'no_show')),
    revision integer not null check (revision >= 1),
    recorded_by uuid not null references gba.users (id),
    recorded_at timestamptz not null default clock_timestamp(),
    creation_xid xid8 not null default pg_current_xact_id(),
    primary key (tenant_id, id),
    unique (tenant_id, id, location_id),
    foreign key (tenant_id, table_id, location_id, table_resource_id)
        references gba.restaurant_tables (tenant_id, id, location_id, resource_id),
    constraint restaurant_table_reservations_guest_fk foreign key (tenant_id, guest_counterparty_id)
        references gba.counterparties (tenant_id, id),
    check (isfinite(starts_at) and isfinite(ends_at)
           and ends_at > starts_at and ends_at - starts_at <= interval '24 hours')
);
create index restaurant_table_reservations_loc_idx
    on gba.restaurant_table_reservations (tenant_id, location_id, starts_at, id);
create index restaurant_table_reservations_table_idx
    on gba.restaurant_table_reservations (tenant_id, table_id, starts_at, id);

create table gba.restaurant_table_reservation_events (
    tenant_id uuid not null,
    reservation_id uuid not null,
    revision integer not null check (revision >= 2),
    location_id uuid not null,
    action text not null check (action in ('seat', 'complete', 'cancel', 'no_show')),
    note text check (note is null or char_length(btrim(note)) between 1 and 1000),
    recorded_by uuid not null references gba.users (id),
    recorded_at timestamptz not null default clock_timestamp(),
    creation_xid xid8 not null default pg_current_xact_id(),
    primary key (tenant_id, reservation_id, revision),
    foreign key (tenant_id, reservation_id, location_id)
        references gba.restaurant_table_reservations (tenant_id, id, location_id)
);

create function gba.guard_restaurant_table() returns trigger language plpgsql as $$
begin
    if tg_op = 'DELETE' then
        raise exception using errcode = '23514', message = 'restaurant tables are kept';
    end if;
    if tg_op = 'UPDATE' then
        if (old.tenant_id, old.id, old.location_id, old.resource_id)
           is distinct from (new.tenant_id, new.id, new.location_id, new.resource_id) then
            raise exception using errcode = '23514',
                message = 'a restaurant table keeps its branch and resource';
        end if;
        if new.revision <> old.revision + 1 then
            raise exception using errcode = '23514',
                message = 'restaurant table revision increments by one';
        end if;
    end if;
    if not exists (
        select 1 from gba.resources r
        where r.tenant_id = new.tenant_id and r.id = new.resource_id
          and r.location_id = new.location_id and r.kind = 'restaurant_table' and r.is_active
    ) then
        raise exception using errcode = '23514',
            message = 'a restaurant table requires an active table resource in its branch';
    end if;
    return new;
end;
$$;
revoke all on function gba.guard_restaurant_table() from public;
create trigger restaurant_tables_guard before insert or update or delete on gba.restaurant_tables
    for each row execute function gba.guard_restaurant_table();

create function gba.keep_restaurant_table_resource_identity() returns trigger language plpgsql as $$
begin
    if (old.kind = 'restaurant_table' or new.kind = 'restaurant_table') and
       (old.tenant_id, old.id, old.location_id, old.kind, old.is_active) is distinct from
       (new.tenant_id, new.id, new.location_id, new.kind, new.is_active) then
        raise exception using errcode = '23514',
            message = 'a restaurant table resource keeps its identity';
    end if;
    return new;
end;
$$;
revoke all on function gba.keep_restaurant_table_resource_identity() from public;
create trigger resources_keep_restaurant_table_identity before update on gba.resources
    for each row execute function gba.keep_restaurant_table_resource_identity();

create function gba.guard_restaurant_reservation() returns trigger language plpgsql as $$
declare
    tbl record;
begin
    if tg_op = 'DELETE' then
        raise exception using errcode = '23514', message = 'table reservations are kept';
    end if;
    if tg_op = 'INSERT' then
        if new.status <> 'booked' or new.revision <> 1 then
            raise exception using errcode = '23514',
                message = 'a new table reservation starts booked at revision 1';
        end if;
        select is_active, min_covers, max_covers into strict tbl
        from gba.restaurant_tables
        where tenant_id = new.tenant_id and id = new.table_id;
        if not tbl.is_active then
            raise exception using errcode = '23514', message = 'table is inactive';
        end if;
        if new.party_size < tbl.min_covers or new.party_size > tbl.max_covers then
            raise exception using errcode = '23514', message = 'party size outside table covers';
        end if;
        return new;
    end if;
    if (old.tenant_id, old.id, old.location_id, old.table_id, old.table_resource_id,
        old.guest_counterparty_id, old.guest_name, old.party_size, old.starts_at, old.ends_at,
        old.note, old.creation_xid)
       is distinct from (new.tenant_id, new.id, new.location_id, new.table_id,
                         new.table_resource_id, new.guest_counterparty_id, new.guest_name,
                         new.party_size, new.starts_at, new.ends_at, new.note,
                         new.creation_xid) then
        raise exception using errcode = '23514',
            message = 'reservation details are immutable; record a lifecycle event';
    end if;
    if new.revision <> old.revision + 1 then
        raise exception using errcode = '23514',
            message = 'reservation revision increments by one';
    end if;
    if not (
        (old.status = 'booked' and new.status in ('seated', 'cancelled', 'no_show'))
        or (old.status = 'seated' and new.status in ('completed', 'cancelled'))
    ) then
        raise exception using errcode = '23514',
            message = 'invalid table reservation status transition';
    end if;
    return new;
end;
$$;
revoke all on function gba.guard_restaurant_reservation() from public;
create trigger restaurant_table_reservations_guard
    before insert or update or delete on gba.restaurant_table_reservations
    for each row execute function gba.guard_restaurant_reservation();

create function gba.check_restaurant_reservation_allocated() returns trigger language plpgsql as $$
begin
    if (
        select count(*) from gba.resource_allocations a
        where a.tenant_id = new.tenant_id and a.source_kind = 'restaurant_reservation'
          and a.source_id = new.id
    ) <> 1 then
        raise exception using errcode = '23514',
            message = 'a table reservation requires its table allocation';
    end if;
    return null;
end;
$$;
revoke all on function gba.check_restaurant_reservation_allocated() from public;
create constraint trigger restaurant_table_reservations_allocated
    after insert on gba.restaurant_table_reservations
    deferrable initially deferred for each row
    execute function gba.check_restaurant_reservation_allocated();

create function gba.release_restaurant_reservation() returns trigger language plpgsql as $$
declare
    released integer;
begin
    if new.action in ('complete', 'cancel', 'no_show') then
        update gba.resource_allocations set state = 'released'
        where tenant_id = new.tenant_id and source_kind = 'restaurant_reservation'
          and source_id = new.reservation_id and state = 'confirmed';
        get diagnostics released = row_count;
        if released <> 1 then
            raise exception using errcode = '23514',
                message = 'closing event must release the table allocation';
        end if;
    end if;
    return null;
end;
$$;
revoke all on function gba.release_restaurant_reservation() from public;
create trigger restaurant_reservation_events_release
    after insert on gba.restaurant_table_reservation_events
    for each row execute function gba.release_restaurant_reservation();

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
    if exists (
        select 1 from gba.resources r where r.tenant_id = new.tenant_id
          and r.id = new.resource_id and r.kind = 'restaurant_table'
          and new.source_kind <> 'restaurant_reservation'
    ) then
        raise exception using errcode = '23514',
            message = 'a restaurant table resource is reserved only for table reservations';
    end if;
    if new.source_kind = 'restaurant_reservation' then
        if tg_op = 'INSERT' and not exists (
            select 1 from gba.restaurant_table_reservations s
              join gba.resources r on r.tenant_id = s.tenant_id
             where s.tenant_id = new.tenant_id and s.id = new.source_id
               and r.id = new.resource_id and r.location_id = s.location_id
               and r.kind = 'restaurant_table' and r.is_active
               and s.table_resource_id = r.id
               and s.creation_xid = pg_current_xact_id()
               and new.during = tstzrange(s.starts_at, s.ends_at, '[)')
               and new.state = 'confirmed'
        ) then
            raise exception using errcode = '23514',
                message = 'a table reservation allocation follows its reservation';
        end if;
        if tg_op = 'UPDATE' and new.state = 'released' and not exists (
            select 1 from gba.restaurant_table_reservation_events e
             where e.tenant_id = new.tenant_id and e.reservation_id = new.source_id
               and e.action in ('complete', 'cancel', 'no_show')
               and e.creation_xid = pg_current_xact_id()
        ) then
            raise exception using errcode = '23514',
                message = 'a table reservation release requires a closing event';
        end if;
    end if;
    return new;
end;
$$;

-- RLS, module write gates and minimal runtime privileges
alter table gba.restaurant_areas enable row level security;
alter table gba.restaurant_areas force row level security;
create policy restaurant_areas_tenant_isolation on gba.restaurant_areas
    using (tenant_id = gba.current_tenant_id()) with check (tenant_id = gba.current_tenant_id());
create policy restaurant_areas_location_scope on gba.restaurant_areas as restrictive to gba_runtime
    using (gba.current_location_id() is null or location_id = gba.current_location_id())
    with check (gba.current_location_id() is null or location_id = gba.current_location_id());
grant select, insert, update on gba.restaurant_areas to gba_runtime;
create trigger restaurant_areas_require_module before insert on gba.restaurant_areas
    for each row execute function gba.require_enabled_module('restaurant');

alter table gba.restaurant_area_revisions enable row level security;
alter table gba.restaurant_area_revisions force row level security;
create policy restaurant_area_revisions_tenant_isolation on gba.restaurant_area_revisions
    using (tenant_id = gba.current_tenant_id()) with check (tenant_id = gba.current_tenant_id());
create policy restaurant_area_revisions_location_scope on gba.restaurant_area_revisions as restrictive to gba_runtime
    using (gba.current_location_id() is null or location_id = gba.current_location_id())
    with check (gba.current_location_id() is null or location_id = gba.current_location_id());
grant select, insert on gba.restaurant_area_revisions to gba_runtime;

alter table gba.restaurant_tables enable row level security;
alter table gba.restaurant_tables force row level security;
create policy restaurant_tables_tenant_isolation on gba.restaurant_tables
    using (tenant_id = gba.current_tenant_id()) with check (tenant_id = gba.current_tenant_id());
create policy restaurant_tables_location_scope on gba.restaurant_tables as restrictive to gba_runtime
    using (gba.current_location_id() is null or location_id = gba.current_location_id())
    with check (gba.current_location_id() is null or location_id = gba.current_location_id());
grant select, insert, update on gba.restaurant_tables to gba_runtime;
create trigger restaurant_tables_require_module before insert on gba.restaurant_tables
    for each row execute function gba.require_enabled_module('restaurant');

alter table gba.restaurant_table_reservations enable row level security;
alter table gba.restaurant_table_reservations force row level security;
create policy restaurant_table_reservations_tenant_isolation on gba.restaurant_table_reservations
    using (tenant_id = gba.current_tenant_id()) with check (tenant_id = gba.current_tenant_id());
create policy restaurant_table_reservations_location_scope on gba.restaurant_table_reservations as restrictive to gba_runtime
    using (gba.current_location_id() is null or location_id = gba.current_location_id())
    with check (gba.current_location_id() is null or location_id = gba.current_location_id());
grant select, insert, update on gba.restaurant_table_reservations to gba_runtime;
create trigger restaurant_table_reservations_require_module before insert on gba.restaurant_table_reservations
    for each row execute function gba.require_enabled_module('restaurant');

alter table gba.restaurant_table_reservation_events enable row level security;
alter table gba.restaurant_table_reservation_events force row level security;
create policy restaurant_table_reservation_events_tenant_isolation on gba.restaurant_table_reservation_events
    using (tenant_id = gba.current_tenant_id()) with check (tenant_id = gba.current_tenant_id());
create policy restaurant_table_reservation_events_location_scope on gba.restaurant_table_reservation_events as restrictive to gba_runtime
    using (gba.current_location_id() is null or location_id = gba.current_location_id())
    with check (gba.current_location_id() is null or location_id = gba.current_location_id());
grant select, insert on gba.restaurant_table_reservation_events to gba_runtime;
