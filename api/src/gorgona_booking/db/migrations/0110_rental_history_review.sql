-- RR-07 and RR-09: preserve rental measurement and terms; keep one owner per sandbox intent.
alter table gba.rental_inspections add column meter_kind text
    constraint rental_inspections_meter_kind_check
    check (meter_kind in ('none', 'odometer', 'hours'));

-- A hold is the first event; later evidence must match its intent under the existing guard.
-- An index enforces uniqueness across classes and branch-restricted sessions.
create unique index rental_security_provider_links_initial_intent
    on gba.rental_security_provider_links (tenant_id, intent) where sequence = 1;

create or replace function gba.guard_rental_inspection() returns trigger language plpgsql as $$
declare
    booking record;
    handover record;
    handover_meter bigint;
    unit_id uuid;
    meter_required boolean;
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
    select c.meter_kind into new.meter_kind from gba.rental_classes c
    where c.tenant_id = new.tenant_id and c.id = booking.class_id;
    meter_required := new.meter_kind <> 'none';
    if new.kind = 'return' then
        select i.assignment_id, i.meter, i.meter_kind into handover from gba.rental_inspections i
        where i.tenant_id = new.tenant_id and i.booking_id = new.booking_id and i.kind = 'handover';
        if not found or handover.assignment_id <> new.assignment_id then
            raise exception using errcode = 'check_violation',
                constraint = 'rental_inspections_order_check',
                message = 'a return follows the handover of the same assignment';
        end if;
        handover_meter := handover.meter;
        new.meter_kind := handover.meter_kind;
        meter_required := coalesce(new.meter_kind <> 'none', handover_meter is not null);
    end if;
    if meter_required <> (new.meter is not null)
        or new.meter < handover_meter then
        raise exception using errcode = 'check_violation',
            constraint = 'rental_inspections_meter_check',
            message = 'a class with a meter records a reading that never goes back, a class without one none';
    end if;
    return new;
end;
$$;

create or replace function gba.guard_rental_settlement() returns trigger language plpgsql as $$
declare
    booking record;
    terms record;
    handed bigint;
    back record;
    seconds bigint;
    units integer := 0;
    late bigint := 0;
    excess bigint := 0;
begin
    select b.class_id, b.customer_id into booking from gba.rental_bookings b
    where b.tenant_id = new.tenant_id and b.id = new.booking_id;
    perform 1 from gba.rental_classes c
    where c.tenant_id = new.tenant_id and c.id = booking.class_id for update;
    select v.version, v.total, v.ends_at, v.rental_days, r.currency, r.hour_rate, r.day_rate,
           r.meter_allowance_per_day, r.excess_rate into terms
    from gba.rental_agreements a
      join gba.rental_agreement_versions v on v.tenant_id = a.tenant_id and v.agreement_id = a.id
      join gba.rental_rate_cards r on r.tenant_id = v.tenant_id and r.id = v.rate_card_id
    where a.tenant_id = new.tenant_id and a.booking_id = new.booking_id
    order by v.version desc limit 1;
    select i.inspected_at, i.meter into back from gba.rental_inspections i
    where i.tenant_id = new.tenant_id and i.booking_id = new.booking_id and i.kind = 'return';
    if terms.version is null or back.inspected_at is null or exists (
        select 1 from gba.rental_booking_cancellations c
        where c.tenant_id = new.tenant_id and c.booking_id = new.booking_id
    ) then
        raise exception using errcode = 'check_violation',
            constraint = 'rental_settlements_state_check',
            message = 'a settlement follows the return of a booking with an agreement that is not cancelled';
    end if;
    select i.meter into handed from gba.rental_inspections i
    where i.tenant_id = new.tenant_id and i.booking_id = new.booking_id and i.kind = 'handover';
    if handed is not null and terms.meter_allowance_per_day is not null
        and terms.excess_rate is not null then
        excess := greatest(0, back.meter - handed - terms.meter_allowance_per_day * terms.rental_days)
            * terms.excess_rate;
    end if;
    seconds := greatest(0, floor(extract(epoch from back.inspected_at - terms.ends_at)))::bigint;
    if seconds > 0 then
        if terms.hour_rate is not null then
            units := ceil(seconds / 3600.0);
            late := units * terms.hour_rate;
        elsif terms.day_rate is not null then
            units := ceil(seconds / 86400.0);
            late := units * terms.day_rate;
        else
            raise exception using errcode = 'check_violation',
                constraint = 'rental_settlements_unpriced_check',
                message = 'an overdue return needs an hour or a day rate on the card';
        end if;
    end if;
    if new.agreement_version <> terms.version or new.rental_minor <> terms.total
        or new.excess_minor <> excess or new.late_minor <> late or new.late_units <> units then
        raise exception using errcode = 'check_violation',
            constraint = 'rental_settlements_figures_check',
            message = 'the settlement figures follow the latest agreement version, the card and the inspections';
    end if;
    if not exists (
        select 1 from gba.financial_documents d
          join gba.financial_document_versions v
            on v.tenant_id = d.tenant_id and v.book_id = d.book_id and v.document_id = d.id
         where d.tenant_id = new.tenant_id and d.book_id = new.book_id
           and d.id = new.invoice_document_id and d.kind = 'invoice'
           and v.revision = (select max(x.revision) from gba.financial_document_versions x
                              where x.tenant_id = d.tenant_id and x.book_id = d.book_id
                                and x.document_id = d.id)
           and v.direction = 'receivable' and v.counterparty_id = booking.customer_id
           and v.currency = terms.currency and v.principal_minor = new.total_minor
    ) then
        raise exception using errcode = 'check_violation',
            constraint = 'rental_settlements_document_check',
            message = 'the settlement names the receivable invoice of the customer for its total';
    end if;
    return new;
end;
$$;

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
    if exists (
        select 1 from gba.rental_settlements s
        where s.tenant_id = new.tenant_id and s.booking_id = booking.id
    ) then
        raise exception using errcode = 'check_violation',
            constraint = 'rental_agreement_versions_settled_check',
            message = 'a settled rental keeps its agreement terms';
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
