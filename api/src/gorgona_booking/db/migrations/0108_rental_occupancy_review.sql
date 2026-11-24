-- RR-01..04: serialize assignment, handover and capacity changes using the existing class lock.
-- The booking's class is immutable. Re-read changing facts after taking the lock.
create function gba.lock_rental_booking_class(p_tenant uuid, p_booking uuid)
returns void language plpgsql as $$
begin
    perform 1 from gba.rental_classes c
      join gba.rental_bookings b on b.tenant_id = c.tenant_id and b.class_id = c.id
    where b.tenant_id = p_tenant and b.id = p_booking for update of c;
end;
$$;
revoke all on function gba.lock_rental_booking_class(uuid, uuid) from public;
grant execute on function gba.lock_rental_booking_class(uuid, uuid) to gba_runtime;

create function gba.require_rental_before_handover(p_tenant uuid, p_booking uuid)
returns void language plpgsql as $$
begin
    if exists (
        select 1 from gba.rental_inspections i
        where i.tenant_id = p_tenant and i.booking_id = p_booking and i.kind = 'handover'
    ) then
        raise exception using errcode = 'check_violation',
            constraint = 'rental_booking_handover_check',
            message = 'the recorded handover keeps its booking, period and assignment';
    end if;
end;
$$;
revoke all on function gba.require_rental_before_handover(uuid, uuid) from public;
grant execute on function gba.require_rental_before_handover(uuid, uuid) to gba_runtime;

create function gba.rental_unit_is_out(p_tenant uuid, p_unit uuid) returns boolean
language sql stable as $$
    select exists (
        select 1 from gba.rental_assignments a
          join gba.rental_inspections h on h.tenant_id = a.tenant_id and h.assignment_id = a.id
        where a.tenant_id = p_tenant and a.unit_id = p_unit and h.kind = 'handover'
          and not exists (
              select 1 from gba.rental_inspections r
              where r.tenant_id = h.tenant_id and r.booking_id = h.booking_id and r.kind = 'return')
    );
$$;
revoke all on function gba.rental_unit_is_out(uuid, uuid) from public;
grant execute on function gba.rental_unit_is_out(uuid, uuid) to gba_runtime;


create or replace function gba.guard_rental_assignment() returns trigger language plpgsql as $$
begin
    perform gba.lock_rental_booking_class(new.tenant_id, new.booking_id);
    perform gba.require_rental_before_handover(new.tenant_id, new.booking_id);
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

create or replace function gba.guard_rental_booking_period() returns trigger language plpgsql as $$
declare
    booking record;
    latest integer;
begin
    select b.class_id into booking from gba.rental_bookings b
    where b.tenant_id = new.tenant_id and b.id = new.booking_id;
    perform 1 from gba.rental_classes c
    where c.tenant_id = new.tenant_id and c.id = booking.class_id for update;
    perform gba.require_rental_before_handover(new.tenant_id, new.booking_id);
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

create or replace function gba.guard_rental_assignment_release() returns trigger language plpgsql as $$
declare
    booking_id uuid;
begin
    select a.booking_id into booking_id from gba.rental_assignments a
    where a.tenant_id = new.tenant_id and a.id = new.assignment_id;
    perform gba.lock_rental_booking_class(new.tenant_id, booking_id);
    perform gba.require_rental_before_handover(new.tenant_id, booking_id);
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

create function gba.guard_rental_cancellation_handover() returns trigger language plpgsql as $$
begin
    perform gba.lock_rental_booking_class(new.tenant_id, new.booking_id);
    perform gba.require_rental_before_handover(new.tenant_id, new.booking_id);
    return new;
end;
$$;
revoke all on function gba.guard_rental_cancellation_handover() from public;
create trigger rental_booking_cancellations_handover
    before insert on gba.rental_booking_cancellations
    for each row execute function gba.guard_rental_cancellation_handover();

create or replace function gba.guard_rental_inspection() returns trigger language plpgsql as $$
declare
    booking record;
    handover record;
    handover_meter bigint;
    unit_id uuid;
begin
    select b.class_id, c.meter_kind into booking from gba.rental_bookings b
      join gba.rental_classes c on c.tenant_id = b.tenant_id and c.id = b.class_id
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
            constraint = 'rental_inspections_booking_check',
            message = 'an inspection belongs to a booking with an agreement that is not cancelled';
    end if;
    select a.unit_id into unit_id
    from gba.rental_assignments a
        where a.tenant_id = new.tenant_id and a.id = new.assignment_id and a.booking_id = new.booking_id
          and not exists (select 1 from gba.rental_assignment_releases r
              where r.tenant_id = a.tenant_id and r.assignment_id = a.id);
    if not found then
        raise exception using errcode = 'check_violation',
            constraint = 'rental_inspections_assignment_check',
            message = 'an inspection names the current assignment of its booking';
    end if;
    if new.kind = 'handover' and gba.rental_unit_is_out(new.tenant_id, unit_id)
       and not exists (
           select 1 from gba.rental_inspections i
           where i.tenant_id = new.tenant_id and i.booking_id = new.booking_id and i.kind = 'handover'
       ) then
        raise exception using errcode = 'check_violation',
            constraint = 'rental_inspections_unit_out_check',
            message = 'the unit has an open handover';
    end if;
    if new.kind = 'return' then
        select i.assignment_id, i.meter into handover from gba.rental_inspections i
        where i.tenant_id = new.tenant_id and i.booking_id = new.booking_id and i.kind = 'handover';
        if not found or handover.assignment_id <> new.assignment_id then
            raise exception using errcode = 'check_violation',
                constraint = 'rental_inspections_order_check',
                message = 'a return follows the handover of the same assignment';
        end if;
        handover_meter := handover.meter;
    end if;
    if (booking.meter_kind = 'none') <> (new.meter is null)
        or new.meter < handover_meter then
        raise exception using errcode = 'check_violation',
            constraint = 'rental_inspections_meter_check',
            message = 'a class with a meter records a reading that never goes back, a class without one none';
    end if;
    return new;
end;
$$;

create or replace function gba.guard_rental_unit() returns trigger language plpgsql as $$
declare
    last_end timestamptz;
    units integer;
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
    if new.location_id <> old.location_id or new.state <> old.state then
        perform 1 from gba.rental_classes c
        where c.tenant_id = old.tenant_id and c.id = old.class_id for update;
        if gba.rental_unit_is_out(old.tenant_id, old.id) or exists (
            select 1 from gba.resource_allocations x
            where x.tenant_id = old.tenant_id and x.resource_id = old.resource_id
              and x.state in ('held', 'confirmed') and upper(x.during) > statement_timestamp()
        ) then
            raise exception using errcode = 'check_violation',
                constraint = 'rental_units_held_check',
                message = 'a unit in use or held cannot be moved or retired';
        end if;
        select max(b.ends_at) into last_end
        from gba.rental_current_bookings(old.tenant_id) b
        where b.class_id = old.class_id and b.pickup_location_id = old.location_id
          and b.ends_at > statement_timestamp()
          and not exists (
              select 1 from gba.rental_booking_cancellations c
              where c.tenant_id = b.tenant_id and c.booking_id = b.id);
        if last_end is not null then
            select count(*) into units from gba.rental_units u
            where u.tenant_id = old.tenant_id and u.class_id = old.class_id
              and u.location_id = old.location_id and u.state = 'active' and u.id <> old.id;
            if gba.rental_booking_peak(
                old.tenant_id, old.class_id, old.location_id, statement_timestamp(), last_end
            ) > units then
                raise exception using errcode = 'check_violation',
                    constraint = 'rental_units_availability_check',
                    message = 'removing a unit leaves a booking without class capacity';
            end if;
        end if;
    end if;
    return new;
end;
$$;

create or replace function gba.guard_rental_unit_block() returns trigger language plpgsql as $$
declare
    unit record;
    units integer;
begin
    select u.class_id, u.location_id, u.state into unit from gba.rental_units u
    where u.tenant_id = new.tenant_id and u.id = new.unit_id;
    perform 1 from gba.rental_classes c
    where c.tenant_id = new.tenant_id and c.id = unit.class_id for update;
    select u.class_id, u.location_id, u.state into unit from gba.rental_units u
    where u.tenant_id = new.tenant_id and u.id = new.unit_id;
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
