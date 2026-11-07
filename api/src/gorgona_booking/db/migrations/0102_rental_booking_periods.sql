-- R4c (package R, RENT-01): extensions and shortened periods on the shared occupancy.
-- docs/plan/PACKAGE_R4C_DESIGN_2026-11-06.md. A period change is an insert-only row numbered 2, 3 per booking; a
-- booking's current period is its latest change, or the booked period. Availability, assignments and agreement versions
-- use the current period; the booking row never changes. The shared occupancy guard is not replaced: an assignment's
-- hold already follows the assignment's own period.
create table gba.rental_booking_periods (
    tenant_id uuid not null references gba.tenants(id),
    booking_id uuid not null,
    sequence integer not null constraint rental_booking_periods_sequence_check check (sequence > 1),
    starts_at timestamptz not null,
    ends_at timestamptz not null,
    recorded_by uuid not null references gba.users(id),
    created_at timestamptz not null default now(),
    creation_xid xid8 not null default pg_current_xact_id(),
    primary key (tenant_id, booking_id, sequence),
    foreign key (tenant_id, booking_id) references gba.rental_bookings (tenant_id, id),
    constraint rental_booking_periods_period_check
        check (ends_at > starts_at and ends_at - starts_at <= interval '366 days')
);

-- Every booking of a company with its current period.
create function gba.rental_current_bookings(p_tenant uuid)
returns table (
    tenant_id uuid, id uuid, class_id uuid, pickup_location_id uuid,
    starts_at timestamptz, ends_at timestamptz, booked_at timestamptz
) language sql stable as $$
    select b.tenant_id, b.id, b.class_id, b.pickup_location_id,
           coalesce(p.starts_at, b.starts_at), coalesce(p.ends_at, b.ends_at), b.booked_at
    from gba.rental_bookings b
    left join lateral (
        select q.starts_at, q.ends_at from gba.rental_booking_periods q
        where q.tenant_id = b.tenant_id and q.booking_id = b.id
        order by q.sequence desc limit 1
    ) p on true
    where b.tenant_id = p_tenant;
$$;
revoke all on function gba.rental_current_bookings(uuid) from public;
grant execute on function gba.rental_current_bookings(uuid) to gba_runtime;

-- A period change follows the booking's changes under the class row lock, for a booking with an agreement that is not
-- cancelled.
create function gba.guard_rental_booking_period() returns trigger language plpgsql as $$
declare
    booking record;
    latest integer;
begin
    select b.class_id into booking from gba.rental_bookings b
    where b.tenant_id = new.tenant_id and b.id = new.booking_id;
    perform 1 from gba.rental_classes c
    where c.tenant_id = new.tenant_id and c.id = booking.class_id for update;
    if exists (
        select 1 from gba.rental_booking_cancellations c
        where c.tenant_id = new.tenant_id and c.booking_id = new.booking_id
    ) or not exists (
        select 1 from gba.rental_agreements a
        where a.tenant_id = new.tenant_id and a.booking_id = new.booking_id
    ) then
        raise exception using errcode = 'check_violation',
            constraint = 'rental_booking_periods_booking_check',
            message = 'a period changes only for a booking with an agreement that is not cancelled';
    end if;
    select max(q.sequence) into latest from gba.rental_booking_periods q
    where q.tenant_id = new.tenant_id and q.booking_id = new.booking_id;
    if new.sequence <> coalesce(latest, 1) + 1 then
        raise exception using errcode = 'check_violation',
            constraint = 'rental_booking_periods_sequence_next_check',
            message = 'a period change takes the next number of its booking';
    end if;
    return new;
end;
$$;
revoke all on function gba.guard_rental_booking_period() from public;
create trigger rental_booking_periods_guard
    before insert on gba.rental_booking_periods
    for each row execute function gba.guard_rental_booking_period();

-- Availability counts every booking by its current period (0099 body kept whole).
create or replace function gba.rental_booking_peak(
    p_tenant uuid, p_class uuid, p_location uuid, p_starts timestamptz, p_ends timestamptz
) returns integer language sql stable as $$
    select coalesce(max((
        select count(*) from gba.rental_current_bookings(p_tenant) b
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
        select b.starts_at from gba.rental_current_bookings(p_tenant) b
        where b.tenant_id = p_tenant and b.class_id = p_class and b.pickup_location_id = p_location
          and b.starts_at > p_starts and b.starts_at < p_ends
        union
        select k.starts_at from gba.rental_unit_blocks k
          join gba.rental_units u on u.tenant_id = k.tenant_id and u.id = k.unit_id
        where k.tenant_id = p_tenant and u.class_id = p_class and u.location_id = p_location
          and k.starts_at > p_starts and k.starts_at < p_ends
    ) point;
$$;

-- An assignment carries the booking's current period (0098 body kept whole).
create or replace function gba.guard_rental_assignment() returns trigger language plpgsql as $$
begin
    if not exists (
        select 1 from gba.rental_current_bookings(new.tenant_id) b
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

-- Version 1 freezes the current period; a change keeps the card and carries the current period (0101 body kept whole).
create or replace function gba.guard_rental_agreement_version() returns trigger language plpgsql as $$
declare
    booking record;
    card record;
    latest record;
    in_force uuid;
    hours bigint;
begin
    select b.id, b.class_id, b.pickup_location_id, b.starts_at, b.ends_at, b.booked_at into booking
    from gba.rental_agreements a
      join gba.rental_current_bookings(new.tenant_id) b on b.id = a.booking_id
    where a.tenant_id = new.tenant_id and a.id = new.agreement_id;
    perform 1 from gba.rental_classes c
    where c.tenant_id = new.tenant_id and c.id = booking.class_id for update;
    if exists (
        select 1 from gba.rental_booking_cancellations c
        where c.tenant_id = new.tenant_id and c.booking_id = booking.id
    ) then
        raise exception using errcode = 'check_violation',
            constraint = 'rental_agreement_versions_booking_check',
            message = 'a cancelled booking takes no agreement version';
    end if;
    select v.version, v.rate_card_id, v.starts_at, v.ends_at into latest
    from gba.rental_agreement_versions v
    where v.tenant_id = new.tenant_id and v.agreement_id = new.agreement_id
    order by v.version desc limit 1;
    if new.version <> coalesce(latest.version, 0) + 1 then
        raise exception using errcode = 'check_violation',
            constraint = 'rental_agreement_versions_sequence_check',
            message = 'an agreement takes its next version';
    end if;
    if new.version = 1 then
        select r.id into in_force from gba.rental_rate_cards r
        where r.tenant_id = new.tenant_id and r.class_id = booking.class_id
          and r.location_id = booking.pickup_location_id and r.effective_from <= booking.booked_at
        order by r.effective_from desc, r.version desc limit 1;
        if new.rate_card_id is distinct from in_force
           or new.starts_at <> booking.starts_at or new.ends_at <> booking.ends_at then
            raise exception using errcode = 'check_violation',
                constraint = 'rental_agreement_versions_frozen_check',
                message = 'version 1 freezes the card in force at the booking and its period';
        end if;
    elsif new.rate_card_id <> latest.rate_card_id
          or new.starts_at <> booking.starts_at or new.ends_at <> booking.ends_at then
        raise exception using errcode = 'check_violation',
            constraint = 'rental_agreement_versions_frozen_check',
            message = 'a change keeps the card and carries the current period';
    end if;
    select r.hour_rate, r.day_rate, r.week_rate, r.month_rate into card
    from gba.rental_rate_cards r where r.tenant_id = new.tenant_id and r.id = new.rate_card_id;
    hours := ceil(extract(epoch from (new.ends_at - new.starts_at)) / 3600);
    if new.rental_days <> ceil(extract(epoch from (new.ends_at - new.starts_at)) / 86400)
       or (card.month_rate is null and new.month_count > 0) or (card.week_rate is null and new.week_count > 0)
       or (card.day_rate is null and new.day_count > 0) or (card.hour_rate is null and new.hour_count > 0)
       or new.month_count * 720 + new.week_count * 168 + new.day_count * 24 + new.hour_count < hours
       or new.rental_amount <> new.month_count * coalesce(card.month_rate, 0)
            + new.week_count * coalesce(card.week_rate, 0) + new.day_count * coalesce(card.day_rate, 0)
            + new.hour_count * coalesce(card.hour_rate, 0) then
        raise exception using errcode = 'check_violation',
            constraint = 'rental_agreement_versions_rental_check',
            message = 'the rental amount prices whole units of the card that cover the period';
    end if;
    return new;
end;
$$;

-- With the change in place, every booking of the class at its pickup branch still has a unit.
create function gba.check_rental_booking_period_availability() returns trigger language plpgsql as $$
declare
    booking record;
    units integer;
begin
    select b.class_id, b.pickup_location_id into booking from gba.rental_bookings b
    where b.tenant_id = new.tenant_id and b.id = new.booking_id;
    select count(*) into units from gba.rental_units u
    where u.tenant_id = new.tenant_id and u.class_id = booking.class_id
      and u.location_id = booking.pickup_location_id and u.state = 'active';
    if gba.rental_booking_peak(new.tenant_id, booking.class_id, booking.pickup_location_id,
                               new.starts_at, new.ends_at) > units then
        raise exception using errcode = 'check_violation',
            constraint = 'rental_booking_periods_availability_check',
            message = 'a period change leaves every booking of its class a unit';
    end if;
    return null;
end;
$$;
revoke all on function gba.check_rental_booking_period_availability() from public;
create trigger rental_booking_periods_availability
    after insert on gba.rental_booking_periods
    for each row execute function gba.check_rental_booking_period_availability();

-- At commit, the latest agreement version and a current assignment carry the booking's current period.
create function gba.check_rental_booking_period_follows() returns trigger language plpgsql as $$
declare
    period_now record;
begin
    select b.starts_at, b.ends_at into period_now from gba.rental_current_bookings(new.tenant_id) b
    where b.id = new.booking_id;
    if not exists (
        select 1 from gba.rental_agreements a
          join gba.rental_agreement_versions v on v.tenant_id = a.tenant_id and v.agreement_id = a.id
        where a.tenant_id = new.tenant_id and a.booking_id = new.booking_id
          and v.starts_at = period_now.starts_at and v.ends_at = period_now.ends_at
          and v.version = (
              select max(w.version) from gba.rental_agreement_versions w
              where w.tenant_id = v.tenant_id and w.agreement_id = v.agreement_id)
    ) then
        raise exception using errcode = 'check_violation',
            constraint = 'rental_booking_periods_agreement_check',
            message = 'a period change comes with the agreement version that carries it';
    end if;
    if exists (
        select 1 from gba.rental_assignments s
        where s.tenant_id = new.tenant_id and s.booking_id = new.booking_id
          and (s.starts_at <> period_now.starts_at or s.ends_at <> period_now.ends_at)
          and not exists (
              select 1 from gba.rental_assignment_releases l
              where l.tenant_id = s.tenant_id and l.assignment_id = s.id)
    ) then
        raise exception using errcode = 'check_violation',
            constraint = 'rental_booking_periods_assignment_check',
            message = 'a current assignment carries the booking period';
    end if;
    return null;
end;
$$;
revoke all on function gba.check_rental_booking_period_follows() from public;
create constraint trigger rental_booking_periods_follow
    after insert on gba.rental_booking_periods
    deferrable initially deferred
    for each row execute function gba.check_rental_booking_period_follows();

-- Writes need the rental module (ADR-0019 gate).
create trigger rental_booking_periods_module_gate
    before insert on gba.rental_booking_periods
    for each row execute function gba.require_enabled_module('rental');

alter table gba.rental_booking_periods enable row level security;
alter table gba.rental_booking_periods force row level security;
create policy rental_booking_periods_tenant_isolation on gba.rental_booking_periods
    using (tenant_id = gba.current_tenant_id())
    with check (tenant_id = gba.current_tenant_id());
grant select, insert on gba.rental_booking_periods to gba_runtime;

-- Rental branch scope:
create policy rental_booking_periods_location_scope on gba.rental_booking_periods
    as restrictive to gba_runtime
    using (gba.current_location_id() is null or exists (
        select 1 from gba.rental_bookings b
        where b.tenant_id = rental_booking_periods.tenant_id and b.id = rental_booking_periods.booking_id))
    with check (gba.current_location_id() is null or exists (
        select 1 from gba.rental_bookings b
        where b.tenant_id = rental_booking_periods.tenant_id and b.id = rental_booking_periods.booking_id));
