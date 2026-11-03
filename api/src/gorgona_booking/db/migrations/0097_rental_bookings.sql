-- R2 (package R, RENT-01): rental class bookings and their cancellations. docs/plan/PACKAGE_R2_DESIGN_2026-11-03.md.
-- A booking holds a class, never a unit, for a period from a pickup branch; it is accepted only while the active
-- units of the class at that branch cover the peak of overlapping bookings. Bookings and cancellations are
-- insert-only; the database rechecks the sequence (per pickup branch, the scope a branch member sees), the
-- customer and the availability under the class lock.
create table gba.rental_bookings (
    tenant_id uuid not null references gba.tenants(id),
    id uuid not null,
    number integer not null constraint rental_bookings_number_check check (number > 0),
    class_id uuid not null,
    customer_id uuid not null,
    pickup_location_id uuid not null,
    return_location_id uuid not null,
    starts_at timestamptz not null,
    ends_at timestamptz not null,
    note text constraint rental_bookings_note_check
        check (note is null or (length(btrim(note)) between 1 and 1000)),
    booked_by uuid not null references gba.users(id),
    booked_at timestamptz not null default now(),
    primary key (tenant_id, id),
    unique (tenant_id, pickup_location_id, number),
    foreign key (tenant_id, class_id) references gba.rental_classes (tenant_id, id),
    foreign key (tenant_id, customer_id) references gba.counterparties (tenant_id, id),
    foreign key (tenant_id, pickup_location_id) references gba.locations (tenant_id, id),
    foreign key (tenant_id, return_location_id) references gba.locations (tenant_id, id),
    constraint rental_bookings_period_check
        check (ends_at > starts_at and ends_at - starts_at <= interval '366 days')
);
create table gba.rental_booking_cancellations (
    tenant_id uuid not null references gba.tenants(id),
    booking_id uuid not null,
    reason text not null constraint rental_booking_cancellations_reason_check
        check (length(btrim(reason)) between 1 and 500),
    cancelled_by uuid not null references gba.users(id),
    cancelled_at timestamptz not null default now(),
    primary key (tenant_id, booking_id),
    foreign key (tenant_id, booking_id) references gba.rental_bookings (tenant_id, id)
);

-- The peak of bookings of a class at a pickup branch that overlap at one instant of a period, cancelled ones
-- left out. The peak is reached at the start of the period or at the start of a booking inside it.
create function gba.rental_booking_peak(
    p_tenant uuid, p_class uuid, p_location uuid, p_starts timestamptz, p_ends timestamptz
) returns integer language sql stable as $$
    select coalesce(max((
        select count(*) from gba.rental_bookings b
        where b.tenant_id = p_tenant and b.class_id = p_class and b.pickup_location_id = p_location
          and b.starts_at <= point.at and b.ends_at > point.at
          and not exists (
              select 1 from gba.rental_booking_cancellations c
              where c.tenant_id = b.tenant_id and c.booking_id = b.id)
    )), 0)::integer
    from (
        select p_starts as at
        union
        select b.starts_at from gba.rental_bookings b
        where b.tenant_id = p_tenant and b.class_id = p_class and b.pickup_location_id = p_location
          and b.starts_at > p_starts and b.starts_at < p_ends
    ) point;
$$;
revoke all on function gba.rental_booking_peak(uuid, uuid, uuid, timestamptz, timestamptz) from public;
grant execute on function gba.rental_booking_peak(uuid, uuid, uuid, timestamptz, timestamptz)
    to gba_runtime;

-- Bookings follow each other per pickup branch, name an active customer and fit the units of the class there.
create function gba.guard_rental_booking() returns trigger language plpgsql as $$
declare
    units integer;
begin
    perform 1 from gba.rental_classes c
    where c.tenant_id = new.tenant_id and c.id = new.class_id for update;
    if new.number <> coalesce((
        select max(b.number) from gba.rental_bookings b
        where b.tenant_id = new.tenant_id and b.pickup_location_id = new.pickup_location_id), 0) + 1 then
        raise exception using errcode = 'check_violation',
            constraint = 'rental_bookings_sequence_check',
            message = 'a booking follows the latest one of its pickup branch';
    end if;
    if not exists (
        select 1 from gba.counterparty_versions v
        where v.tenant_id = new.tenant_id and v.counterparty_id = new.customer_id
          and v.state = 'active' and 'customer' = any(v.roles)
          and v.revision = (
              select max(x.revision) from gba.counterparty_versions x
              where x.tenant_id = v.tenant_id and x.counterparty_id = v.counterparty_id)
    ) then
        raise exception using errcode = 'check_violation',
            constraint = 'rental_bookings_customer_check',
            message = 'a booking names an active customer';
    end if;
    select count(*) into units from gba.rental_units u
    where u.tenant_id = new.tenant_id and u.class_id = new.class_id
      and u.location_id = new.pickup_location_id and u.state = 'active';
    if gba.rental_booking_peak(new.tenant_id, new.class_id, new.pickup_location_id,
                               new.starts_at, new.ends_at) + 1 > units then
        raise exception using errcode = 'check_violation',
            constraint = 'rental_bookings_availability_check',
            message = 'a booking fits the units of its class at the pickup branch';
    end if;
    return new;
end;
$$;
revoke all on function gba.guard_rental_booking() from public;
create trigger rental_bookings_guard
    before insert on gba.rental_bookings
    for each row execute function gba.guard_rental_booking();

-- Writes need the rental module (ADR-0019 gate).
create trigger rental_bookings_module_gate
    before insert on gba.rental_bookings
    for each row execute function gba.require_enabled_module('rental');
create trigger rental_booking_cancellations_module_gate
    before insert on gba.rental_booking_cancellations
    for each row execute function gba.require_enabled_module('rental');

alter table gba.rental_bookings enable row level security;
alter table gba.rental_bookings force row level security;
alter table gba.rental_booking_cancellations enable row level security;
alter table gba.rental_booking_cancellations force row level security;
create policy rental_bookings_tenant_isolation on gba.rental_bookings
    using (tenant_id = gba.current_tenant_id())
    with check (tenant_id = gba.current_tenant_id());
create policy rental_booking_cancellations_tenant_isolation on gba.rental_booking_cancellations
    using (tenant_id = gba.current_tenant_id())
    with check (tenant_id = gba.current_tenant_id());
grant select, insert on gba.rental_bookings, gba.rental_booking_cancellations to gba_runtime;

-- Rental branch scope:
create policy rental_bookings_location_scope on gba.rental_bookings
    as restrictive to gba_runtime
    using (gba.current_location_id() is null or pickup_location_id = gba.current_location_id())
    with check (gba.current_location_id() is null
        or pickup_location_id = gba.current_location_id());
create policy rental_booking_cancellations_location_scope on gba.rental_booking_cancellations
    as restrictive to gba_runtime
    using (gba.current_location_id() is null or exists (
        select 1 from gba.rental_bookings b
        where b.tenant_id = rental_booking_cancellations.tenant_id
          and b.id = rental_booking_cancellations.booking_id))
    with check (gba.current_location_id() is null or exists (
        select 1 from gba.rental_bookings b
        where b.tenant_id = rental_booking_cancellations.tenant_id
          and b.id = rental_booking_cancellations.booking_id));
