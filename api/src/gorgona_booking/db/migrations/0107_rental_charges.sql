-- R7b (package R, RENT-01): damage charges and refunds of a rental agreement.
-- docs/plan/PACKAGE_R7B_DESIGN_2026-11-08.md. After the settlement, a damage charge cites new marks of the return
-- inspection (each charged once) and names its FIN-03 receivable invoice; a refund is a FIN-03 credit note against an
-- obligation of the booking's settlement or charges, or a recorded external refund; refunds never exceed the
-- settlement total plus the damage charged. All insert-only and numbered 1, 2, 3 per booking.
create table gba.rental_damage_charges (
    tenant_id uuid not null references gba.tenants(id),
    booking_id uuid not null,
    number integer not null constraint rental_damage_charges_number_check check (number > 0),
    amount_minor bigint not null constraint rental_damage_charges_amount_check
        check (amount_minor > 0 and amount_minor < 1000000000000),
    reason text not null constraint rental_damage_charges_reason_check
        check (length(btrim(reason)) between 1 and 500),
    book_id uuid not null,
    invoice_document_id uuid not null,
    charged_by uuid not null references gba.users(id),
    charged_at timestamptz not null default now(),
    creation_xid xid8 not null default pg_current_xact_id(),
    primary key (tenant_id, booking_id, number),
    unique (tenant_id, book_id, invoice_document_id),
    foreign key (tenant_id, booking_id) references gba.rental_settlements (tenant_id, booking_id),
    foreign key (tenant_id, book_id, invoice_document_id)
        references gba.financial_documents (tenant_id, book_id, id)
);
-- One row per charged mark of the return inspection; a mark is charged at most once.
create table gba.rental_damage_charge_marks (
    tenant_id uuid not null references gba.tenants(id),
    booking_id uuid not null,
    number integer not null,
    position smallint not null,
    primary key (tenant_id, booking_id, position),
    foreign key (tenant_id, booking_id, number)
        references gba.rental_damage_charges (tenant_id, booking_id, number)
);
create table gba.rental_refunds (
    tenant_id uuid not null references gba.tenants(id),
    booking_id uuid not null,
    number integer not null constraint rental_refunds_number_check check (number > 0),
    amount_minor bigint not null constraint rental_refunds_amount_check
        check (amount_minor > 0 and amount_minor < 1000000000000),
    reason text not null constraint rental_refunds_reason_check
        check (length(btrim(reason)) between 1 and 500),
    method text not null constraint rental_refunds_method_check check (method in ('credit', 'external')),
    reference text constraint rental_refunds_reference_check
        check (reference is null or length(btrim(reference)) between 1 and 200),
    refunded_at timestamptz,
    book_id uuid,
    credit_document_id uuid,
    recorded_by uuid not null references gba.users(id),
    recorded_at timestamptz not null default now(),
    primary key (tenant_id, booking_id, number),
    unique (tenant_id, book_id, credit_document_id),
    foreign key (tenant_id, booking_id) references gba.rental_settlements (tenant_id, booking_id),
    foreign key (tenant_id, book_id, credit_document_id)
        references gba.financial_documents (tenant_id, book_id, id),
    constraint rental_refunds_fields_check check (
        (method = 'credit') = (book_id is not null and credit_document_id is not null)
        and (method = 'external') = (reference is not null and refunded_at is not null)),
    constraint rental_refunds_time_check check (refunded_at is null or refunded_at <= recorded_at)
);

-- A charge follows the earlier ones and names the receivable invoice of the customer for its amount, in the currency
-- of the settlement.
create function gba.guard_rental_damage_charge() returns trigger language plpgsql as $$
declare
    settled record;
begin
    select b.class_id, b.customer_id, s.book_id, s.invoice_document_id into settled
    from gba.rental_bookings b
      join gba.rental_settlements s on s.tenant_id = b.tenant_id and s.booking_id = b.id
    where b.tenant_id = new.tenant_id and b.id = new.booking_id;
    perform 1 from gba.rental_classes c
    where c.tenant_id = new.tenant_id and c.id = settled.class_id for update;
    if new.number <> 1 + coalesce((select max(c.number) from gba.rental_damage_charges c
        where c.tenant_id = new.tenant_id and c.booking_id = new.booking_id), 0) then
        raise exception using errcode = 'check_violation',
            constraint = 'rental_damage_charges_sequence_check',
            message = 'charges are numbered 1, 2, 3 per booking';
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
           and v.direction = 'receivable' and v.counterparty_id = settled.customer_id
           and v.principal_minor = new.amount_minor
           and v.currency = (select s.currency from gba.financial_document_versions s
                              where s.tenant_id = new.tenant_id and s.book_id = settled.book_id
                                and s.document_id = settled.invoice_document_id and s.revision = 1)
    ) then
        raise exception using errcode = 'check_violation',
            constraint = 'rental_damage_charges_document_check',
            message = 'a charge names the receivable invoice of the customer for its amount';
    end if;
    return new;
end;
$$;
revoke all on function gba.guard_rental_damage_charge() from public;
create trigger rental_damage_charges_guard
    before insert on gba.rental_damage_charges
    for each row execute function gba.guard_rental_damage_charge();

-- A charged mark is written with its charge and is a new mark of the booking's return inspection.
create function gba.guard_rental_damage_charge_mark() returns trigger language plpgsql as $$
begin
    if not exists (
        select 1 from gba.rental_damage_charges c
        where c.tenant_id = new.tenant_id and c.booking_id = new.booking_id and c.number = new.number
          and c.creation_xid = pg_current_xact_id()
    ) or not exists (
        select 1 from gba.rental_inspections i
          join gba.rental_inspection_marks m on m.tenant_id = i.tenant_id and m.inspection_id = i.id
        where i.tenant_id = new.tenant_id and i.booking_id = new.booking_id and i.kind = 'return'
          and m.position = new.position and m.new
    ) then
        raise exception using errcode = 'check_violation',
            constraint = 'rental_damage_charge_marks_basis_check',
            message = 'a charged mark is written with its charge and is new on the return';
    end if;
    return new;
end;
$$;
revoke all on function gba.guard_rental_damage_charge_mark() from public;
create trigger rental_damage_charge_marks_guard
    before insert on gba.rental_damage_charge_marks
    for each row execute function gba.guard_rental_damage_charge_mark();

-- Every charge has its basis by the end of the transaction.
create function gba.check_rental_damage_charge_basis() returns trigger language plpgsql as $$
begin
    if not exists (
        select 1 from gba.rental_damage_charge_marks m
        where m.tenant_id = new.tenant_id and m.booking_id = new.booking_id and m.number = new.number
    ) then
        raise exception using errcode = 'check_violation',
            constraint = 'rental_damage_charges_basis_check',
            message = 'a charge cites at least one new mark of the return';
    end if;
    return null;
end;
$$;
revoke all on function gba.check_rental_damage_charge_basis() from public;
create constraint trigger rental_damage_charges_basis
    after insert on gba.rental_damage_charges
    deferrable initially deferred
    for each row execute function gba.check_rental_damage_charge_basis();

-- A refund follows the earlier ones, keeps all refunds within the settlement total plus the damage charged, and a
-- credit refund names a credit note of an obligation of the booking's settlement or charges for its amount.
create function gba.guard_rental_refund() returns trigger language plpgsql as $$
declare
    settled record;
begin
    select b.class_id, s.total_minor, s.book_id, s.invoice_document_id into settled
    from gba.rental_bookings b
      join gba.rental_settlements s on s.tenant_id = b.tenant_id and s.booking_id = b.id
    where b.tenant_id = new.tenant_id and b.id = new.booking_id;
    perform 1 from gba.rental_classes c
    where c.tenant_id = new.tenant_id and c.id = settled.class_id for update;
    if new.number <> 1 + coalesce((select max(r.number) from gba.rental_refunds r
        where r.tenant_id = new.tenant_id and r.booking_id = new.booking_id), 0) then
        raise exception using errcode = 'check_violation',
            constraint = 'rental_refunds_sequence_check',
            message = 'refunds are numbered 1, 2, 3 per booking';
    end if;
    if new.amount_minor + coalesce((select sum(r.amount_minor) from gba.rental_refunds r
        where r.tenant_id = new.tenant_id and r.booking_id = new.booking_id), 0)
        > settled.total_minor + coalesce((select sum(c.amount_minor) from gba.rental_damage_charges c
            where c.tenant_id = new.tenant_id and c.booking_id = new.booking_id), 0) then
        raise exception using errcode = 'check_violation',
            constraint = 'rental_refunds_ceiling_check',
            message = 'refunds never exceed the settlement total plus the damage charged';
    end if;
    if new.method = 'credit' and not exists (
        select 1 from gba.financial_documents d
          join gba.financial_document_versions v
            on v.tenant_id = d.tenant_id and v.book_id = d.book_id and v.document_id = d.id
          join gba.financial_obligations o
            on o.tenant_id = v.tenant_id and o.book_id = v.book_id and o.id = v.credited_obligation_id
         where d.tenant_id = new.tenant_id and d.book_id = new.book_id
           and d.id = new.credit_document_id and d.kind = 'credit_note'
           and v.revision = (select max(x.revision) from gba.financial_document_versions x
                              where x.tenant_id = d.tenant_id and x.book_id = d.book_id
                                and x.document_id = d.id)
           and v.principal_minor = new.amount_minor and o.source_kind = 'invoice'
           and (o.source_id = settled.invoice_document_id and o.book_id = settled.book_id
                or exists (select 1 from gba.rental_damage_charges c
                    where c.tenant_id = new.tenant_id and c.booking_id = new.booking_id
                      and c.book_id = o.book_id and c.invoice_document_id = o.source_id))
    ) then
        raise exception using errcode = 'check_violation',
            constraint = 'rental_refunds_document_check',
            message = 'a credit refund names a credit note of an obligation of the booking for its amount';
    end if;
    return new;
end;
$$;
revoke all on function gba.guard_rental_refund() from public;
create trigger rental_refunds_guard
    before insert on gba.rental_refunds
    for each row execute function gba.guard_rental_refund();

-- Writes need the rental module (ADR-0019 gate).
create trigger rental_damage_charges_module_gate
    before insert on gba.rental_damage_charges
    for each row execute function gba.require_enabled_module('rental');
create trigger rental_damage_charge_marks_module_gate
    before insert on gba.rental_damage_charge_marks
    for each row execute function gba.require_enabled_module('rental');
create trigger rental_refunds_module_gate
    before insert on gba.rental_refunds
    for each row execute function gba.require_enabled_module('rental');

alter table gba.rental_damage_charges enable row level security;
alter table gba.rental_damage_charges force row level security;
create policy rental_damage_charges_tenant_isolation on gba.rental_damage_charges
    using (tenant_id = gba.current_tenant_id())
    with check (tenant_id = gba.current_tenant_id());
alter table gba.rental_damage_charge_marks enable row level security;
alter table gba.rental_damage_charge_marks force row level security;
create policy rental_damage_charge_marks_tenant_isolation on gba.rental_damage_charge_marks
    using (tenant_id = gba.current_tenant_id())
    with check (tenant_id = gba.current_tenant_id());
alter table gba.rental_refunds enable row level security;
alter table gba.rental_refunds force row level security;
create policy rental_refunds_tenant_isolation on gba.rental_refunds
    using (tenant_id = gba.current_tenant_id())
    with check (tenant_id = gba.current_tenant_id());
grant select, insert on gba.rental_damage_charges, gba.rental_damage_charge_marks, gba.rental_refunds
    to gba_runtime;

-- Rental branch scope:
create policy rental_damage_charges_location_scope on gba.rental_damage_charges
    as restrictive to gba_runtime
    using (gba.current_location_id() is null or exists (
        select 1 from gba.rental_bookings b
        where b.tenant_id = rental_damage_charges.tenant_id and b.id = rental_damage_charges.booking_id))
    with check (gba.current_location_id() is null or exists (
        select 1 from gba.rental_bookings b
        where b.tenant_id = rental_damage_charges.tenant_id and b.id = rental_damage_charges.booking_id));
create policy rental_damage_charge_marks_location_scope on gba.rental_damage_charge_marks
    as restrictive to gba_runtime
    using (gba.current_location_id() is null or exists (
        select 1 from gba.rental_bookings b
        where b.tenant_id = rental_damage_charge_marks.tenant_id
          and b.id = rental_damage_charge_marks.booking_id))
    with check (gba.current_location_id() is null or exists (
        select 1 from gba.rental_bookings b
        where b.tenant_id = rental_damage_charge_marks.tenant_id
          and b.id = rental_damage_charge_marks.booking_id));
create policy rental_refunds_location_scope on gba.rental_refunds
    as restrictive to gba_runtime
    using (gba.current_location_id() is null or exists (
        select 1 from gba.rental_bookings b
        where b.tenant_id = rental_refunds.tenant_id and b.id = rental_refunds.booking_id))
    with check (gba.current_location_id() is null or exists (
        select 1 from gba.rental_bookings b
        where b.tenant_id = rental_refunds.tenant_id and b.id = rental_refunds.booking_id));
