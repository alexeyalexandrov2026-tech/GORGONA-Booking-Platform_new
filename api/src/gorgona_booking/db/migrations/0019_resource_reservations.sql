-- Staff reservations of resources: the second real consumer of shared occupancy
-- (ADR-0022, CORE-04). A company employee reserves one or more resources of one
-- branch for an interval (no customer, no payment). Each reserved resource is a
-- confirmed row in gba.resource_allocations, so the shared exclusion constraint
-- decides between reservations and bookings, all resources of a reservation or
-- none. A cancellation releases them. Reservations belong to the "Booking and
-- resources" module and stop with it.

alter table gba.resource_allocations drop constraint resource_allocations_source_kind;
alter table gba.resource_allocations add constraint resource_allocations_source_kind
    check (source_kind in ('booking', 'reservation'));

create table gba.resource_reservations (
    tenant_id uuid not null references gba.tenants (id),
    id uuid not null,
    location_id uuid not null,
    starts_at timestamptz not null,
    ends_at timestamptz not null,
    purpose text check (
        purpose is null or (length(btrim(purpose, E' \t\r\n')) between 1 and 200
                            and purpose !~ '[[:cntrl:]]')
    ),
    status text not null default 'active' check (status in ('active', 'cancelled')),
    -- How many resources the reservation holds; checked before commit and on release.
    resource_count smallint not null check (resource_count between 1 and 10),
    created_by uuid not null references gba.users (id),
    created_at timestamptz not null default now(),
    cancelled_by uuid references gba.users (id),
    cancelled_at timestamptz,
    primary key (tenant_id, id),
    constraint resource_reservations_location_fk
        foreign key (tenant_id, location_id) references gba.locations (tenant_id, id),
    constraint resource_reservations_interval check (ends_at > starts_at),
    constraint resource_reservations_cancellation check (
        (status = 'cancelled') = (cancelled_by is not null and cancelled_at is not null)
    )
);
create index resource_reservations_schedule
    on gba.resource_reservations (tenant_id, location_id, starts_at);

alter table gba.resource_reservations enable row level security;
alter table gba.resource_reservations force row level security;
create policy resource_reservations_tenant_isolation on gba.resource_reservations
    using (tenant_id = gba.current_tenant_id())
    with check (tenant_id = gba.current_tenant_id());
grant select on gba.resource_reservations to gba_runtime;
grant insert (tenant_id, id, location_id, starts_at, ends_at, purpose, resource_count,
                created_by)
    on gba.resource_reservations to gba_runtime;
grant update (status, cancelled_by, cancelled_at) on gba.resource_reservations to gba_runtime;

-- A reservation is created active and can only be cancelled once; nothing else
-- changes and nothing is deleted. A cancellation releases its allocations.
create function gba.guard_resource_reservation() returns trigger
    language plpgsql as $$
begin
    if tg_op = 'DELETE' then
        raise exception using errcode = 'check_violation',
            message = 'resource reservations are kept';
    end if;
    if tg_op = 'INSERT' then
        if new.status <> 'active' then
            raise exception using errcode = 'check_violation',
                message = 'a reservation is created active';
        end if;
        return new;
    end if;
    if (new.tenant_id, new.id, new.location_id, new.starts_at, new.ends_at, new.purpose,
        new.resource_count, new.created_by, new.created_at)
       is distinct from (old.tenant_id, old.id, old.location_id, old.starts_at, old.ends_at,
                         old.purpose, old.resource_count, old.created_by, old.created_at)
       or not (old.status = 'active' and new.status = 'cancelled') then
        raise exception using errcode = 'check_violation',
            message = 'an active reservation can only be cancelled';
    end if;
    new.cancelled_at := pg_catalog.now();
    return new;
end;
$$;
revoke all on function gba.guard_resource_reservation() from public;
create trigger resource_reservations_guard
    before insert or update or delete on gba.resource_reservations
    for each row execute function gba.guard_resource_reservation();

create function gba.release_reservation_allocations() returns trigger
    language plpgsql as $$
declare
    released integer;
begin
    if new.status = 'cancelled' then
        update gba.resource_allocations r set state = 'released'
         where r.tenant_id = new.tenant_id and r.source_kind = 'reservation'
           and r.source_id = new.id and r.state <> 'released';
        get diagnostics released = row_count;
        -- Row security hides a resource moved to another branch: never leave it
        -- reserved silently; a company-wide session can cancel.
        if released <> new.resource_count then
            raise exception using errcode = 'check_violation',
                message = 'a reserved resource is outside the current branch';
        end if;
    end if;
    return null;
end;
$$;
revoke all on function gba.release_reservation_allocations() from public;
create trigger resource_reservations_release
    after update of status on gba.resource_reservations
    for each row execute function gba.release_reservation_allocations();

-- A reservation holds at least one resource, inserted in its own transaction.
create function gba.check_reservation_allocated() returns trigger
    language plpgsql as $$
begin
    if (
        select count(*) from gba.resource_allocations r
        where r.tenant_id = new.tenant_id and r.source_kind = 'reservation'
          and r.source_id = new.id
    ) <> new.resource_count then
        raise exception using errcode = 'check_violation',
            message = 'a reservation requires its resources before commit';
    end if;
    return null;
end;
$$;
revoke all on function gba.check_reservation_allocated() from public;
create constraint trigger resource_reservations_allocated
    after insert on gba.resource_reservations deferrable initially deferred
    for each row execute function gba.check_reservation_allocated();

-- New reservations stop with the booking module, exactly as new bookings do.
create trigger resource_reservations_require_booking_module
    before insert on gba.resource_reservations
    for each row execute function gba.enforce_booking_module();

-- The occupancy row guard now also covers reservations: an active reservation's
-- interval, an active resource of the reservation's branch, confirmed in the
-- reservation's own transaction and released only by the cancellation; and no
-- active booking allocation that was not copied yet (a company not reconciled by
-- backfill-occupancy) may overlap.
create or replace function gba.guard_resource_allocation() returns trigger
    language plpgsql as $$
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
    return new;
end;
$$;

-- Reservation branch scope: reusable separately when restoring a damaged boundary in tests.
create policy resource_reservations_location_scope on gba.resource_reservations
    as restrictive to gba_runtime
    using (gba.current_location_id() is null or location_id = gba.current_location_id())
    with check (gba.current_location_id() is null or location_id = gba.current_location_id());
