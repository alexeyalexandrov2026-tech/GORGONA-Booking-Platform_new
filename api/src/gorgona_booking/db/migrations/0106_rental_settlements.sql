-- R7a (package R, RENT-01): the final settlement invoice of a rental agreement.
-- docs/plan/PACKAGE_R7A_DESIGN_2026-11-07.md. One settlement per booking, after its return: the latest agreement
-- version's total, the meter excess and the late return from the frozen card and the inspections, and the FIN-03
-- receivable invoice of the booking's customer for their sum. The database recomputes every figure. Insert-only.
create table gba.rental_settlements (
    tenant_id uuid not null references gba.tenants(id),
    booking_id uuid not null,
    agreement_version integer not null constraint rental_settlements_version_check check (agreement_version > 0),
    rental_minor bigint not null constraint rental_settlements_rental_check check (rental_minor > 0),
    excess_minor bigint not null constraint rental_settlements_excess_check check (excess_minor >= 0),
    late_minor bigint not null constraint rental_settlements_late_check check (late_minor >= 0),
    late_units integer not null constraint rental_settlements_units_check check (late_units >= 0),
    total_minor bigint not null constraint rental_settlements_total_check
        check (total_minor = rental_minor + excess_minor + late_minor),
    book_id uuid not null,
    invoice_document_id uuid not null,
    settled_by uuid not null references gba.users(id),
    settled_at timestamptz not null default now(),
    primary key (tenant_id, booking_id),
    unique (tenant_id, book_id, invoice_document_id),
    foreign key (tenant_id, booking_id) references gba.rental_bookings (tenant_id, id),
    foreign key (tenant_id, book_id, invoice_document_id)
        references gba.financial_documents (tenant_id, book_id, id)
);

-- The figures follow the frozen terms and the inspections, and the document is the receivable invoice for their sum.
create function gba.guard_rental_settlement() returns trigger language plpgsql as $$
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
    select b.class_id, b.customer_id, c.meter_kind into booking from gba.rental_bookings b
      join gba.rental_classes c on c.tenant_id = b.tenant_id and c.id = b.class_id
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
    if booking.meter_kind <> 'none' and terms.meter_allowance_per_day is not null
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
revoke all on function gba.guard_rental_settlement() from public;
create trigger rental_settlements_guard
    before insert on gba.rental_settlements
    for each row execute function gba.guard_rental_settlement();

-- Writes need the rental module (ADR-0019 gate).
create trigger rental_settlements_module_gate
    before insert on gba.rental_settlements
    for each row execute function gba.require_enabled_module('rental');

alter table gba.rental_settlements enable row level security;
alter table gba.rental_settlements force row level security;
create policy rental_settlements_tenant_isolation on gba.rental_settlements
    using (tenant_id = gba.current_tenant_id())
    with check (tenant_id = gba.current_tenant_id());
grant select, insert on gba.rental_settlements to gba_runtime;

-- Rental branch scope:
create policy rental_settlements_location_scope on gba.rental_settlements
    as restrictive to gba_runtime
    using (gba.current_location_id() is null or exists (
        select 1 from gba.rental_bookings b
        where b.tenant_id = rental_settlements.tenant_id and b.id = rental_settlements.booking_id))
    with check (gba.current_location_id() is null or exists (
        select 1 from gba.rental_bookings b
        where b.tenant_id = rental_settlements.tenant_id and b.id = rental_settlements.booking_id));
