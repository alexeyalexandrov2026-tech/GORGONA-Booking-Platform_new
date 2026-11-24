-- R5a (package R, RENT-01): recorded security of payment for a rental booking.
-- docs/plan/PACKAGE_R5A_DESIGN_2026-11-07.md. One security per booking with an agreement, in the currency of the latest
-- agreement version's rate card; its states are derived from insert-only events numbered 1, 2, 3: held (once, first,
-- the full amount), captured (part of what is still held, with a basis), released or expired (the rest, once, closes).
-- Nothing here refers to charges, invoices or payments.
create table gba.rental_securities (
    tenant_id uuid not null references gba.tenants(id),
    id uuid not null,
    booking_id uuid not null,
    amount bigint not null constraint rental_securities_amount_check check (amount > 0 and amount < 1000000000000),
    currency text not null constraint rental_securities_currency_format_check check (currency ~ '^[A-Z]{3}$'),
    method text not null constraint rental_securities_method_check
        check (method in ('card_hold', 'cash', 'bank_transfer', 'other')),
    requested_by uuid not null references gba.users(id),
    created_at timestamptz not null default now(),
    creation_xid xid8 not null default pg_current_xact_id(),
    primary key (tenant_id, id),
    unique (tenant_id, booking_id),
    foreign key (tenant_id, booking_id) references gba.rental_bookings (tenant_id, id)
);
create table gba.rental_security_events (
    tenant_id uuid not null references gba.tenants(id),
    security_id uuid not null,
    sequence integer not null constraint rental_security_events_sequence_positive_check check (sequence > 0),
    kind text not null constraint rental_security_events_kind_check
        check (kind in ('held', 'captured', 'released', 'expired')),
    amount bigint not null constraint rental_security_events_amount_check
        check (amount >= 0 and amount < 1000000000000),
    reference text constraint rental_security_events_reference_check
        check (reference is null or length(btrim(reference)) between 1 and 200),
    hold_expires_at timestamptz,
    basis text constraint rental_security_events_basis_check
        check (basis is null or length(btrim(basis)) between 1 and 500),
    occurred_at timestamptz not null,
    recorded_by uuid not null references gba.users(id),
    created_at timestamptz not null default now(),
    creation_xid xid8 not null default pg_current_xact_id(),
    primary key (tenant_id, security_id, sequence),
    foreign key (tenant_id, security_id) references gba.rental_securities (tenant_id, id),
    constraint rental_security_events_fields_check check (
        (kind = 'held') = (reference is not null)
        and (kind = 'held' or hold_expires_at is null)
        and (kind = 'captured') = (basis is not null)),
    constraint rental_security_events_time_check check (occurred_at <= created_at)
);

-- A security is requested for a booking with an agreement that is not cancelled, in its agreement's currency.
create function gba.guard_rental_security() returns trigger language plpgsql as $$
declare
    booking record;
    card_currency text;
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
            constraint = 'rental_securities_booking_check',
            message = 'a security belongs to a booking with an agreement that is not cancelled';
    end if;
    select r.currency into card_currency
    from gba.rental_agreements a
      join gba.rental_agreement_versions v on v.tenant_id = a.tenant_id and v.agreement_id = a.id
      join gba.rental_rate_cards r on r.tenant_id = v.tenant_id and r.id = v.rate_card_id
    where a.tenant_id = new.tenant_id and a.booking_id = new.booking_id
    order by v.version desc limit 1;
    if new.currency is distinct from card_currency then
        raise exception using errcode = 'check_violation',
            constraint = 'rental_securities_currency_check',
            message = 'a security is in the currency of its agreement';
    end if;
    return new;
end;
$$;
revoke all on function gba.guard_rental_security() from public;
create trigger rental_securities_guard
    before insert on gba.rental_securities
    for each row execute function gba.guard_rental_security();

-- Events follow the states under the class row lock: the next number, nothing after a closing event, a hold first and
-- for the full amount, captures within what is still held, and a release or an expiry for exactly the rest.
create function gba.guard_rental_security_event() returns trigger language plpgsql as $$
declare
    security record;
    latest integer;
    held_amount bigint;
    captured_amount bigint;
    closed boolean;
    left_amount bigint;
begin
    select s.amount, b.class_id into security
    from gba.rental_securities s
      join gba.rental_bookings b on b.tenant_id = s.tenant_id and b.id = s.booking_id
    where s.tenant_id = new.tenant_id and s.id = new.security_id;
    perform 1 from gba.rental_classes c
    where c.tenant_id = new.tenant_id and c.id = security.class_id for update;
    select max(e.sequence),
           coalesce(sum(e.amount) filter (where e.kind = 'held'), 0),
           coalesce(sum(e.amount) filter (where e.kind = 'captured'), 0),
           coalesce(bool_or(e.kind in ('released', 'expired')), false)
      into latest, held_amount, captured_amount, closed
    from gba.rental_security_events e
    where e.tenant_id = new.tenant_id and e.security_id = new.security_id;
    if new.sequence <> coalesce(latest, 0) + 1 then
        raise exception using errcode = 'check_violation',
            constraint = 'rental_security_events_sequence_check',
            message = 'a security event takes the next number of its security';
    end if;
    if closed then
        raise exception using errcode = 'check_violation',
            constraint = 'rental_security_events_closed_check',
            message = 'nothing follows a release or an expiry';
    end if;
    left_amount := held_amount - captured_amount;
    if new.kind = 'held' and (latest is not null or new.amount <> security.amount) then
        raise exception using errcode = 'check_violation',
            constraint = 'rental_security_events_held_check',
            message = 'a hold comes first, once, for the full amount';
    end if;
    if new.kind = 'captured' and (held_amount = 0 or new.amount = 0 or new.amount > left_amount) then
        raise exception using errcode = 'check_violation',
            constraint = 'rental_security_events_captured_check',
            message = 'a capture takes part of what is still held';
    end if;
    if new.kind = 'released' and (held_amount = 0 or new.amount <> left_amount) then
        raise exception using errcode = 'check_violation',
            constraint = 'rental_security_events_released_check',
            message = 'a release frees exactly what is still held';
    end if;
    if new.kind = 'expired' and new.amount <> left_amount then
        raise exception using errcode = 'check_violation',
            constraint = 'rental_security_events_expired_check',
            message = 'an expiry closes exactly what is still held';
    end if;
    return new;
end;
$$;
revoke all on function gba.guard_rental_security_event() from public;
create trigger rental_security_events_guard
    before insert on gba.rental_security_events
    for each row execute function gba.guard_rental_security_event();

-- Writes need the rental module (ADR-0019 gate).
create trigger rental_securities_module_gate
    before insert on gba.rental_securities
    for each row execute function gba.require_enabled_module('rental');
create trigger rental_security_events_module_gate
    before insert on gba.rental_security_events
    for each row execute function gba.require_enabled_module('rental');

alter table gba.rental_securities enable row level security;
alter table gba.rental_securities force row level security;
alter table gba.rental_security_events enable row level security;
alter table gba.rental_security_events force row level security;
create policy rental_securities_tenant_isolation on gba.rental_securities
    using (tenant_id = gba.current_tenant_id())
    with check (tenant_id = gba.current_tenant_id());
create policy rental_security_events_tenant_isolation on gba.rental_security_events
    using (tenant_id = gba.current_tenant_id())
    with check (tenant_id = gba.current_tenant_id());
grant select, insert on gba.rental_securities, gba.rental_security_events to gba_runtime;

-- Rental branch scope:
create policy rental_securities_location_scope on gba.rental_securities
    as restrictive to gba_runtime
    using (gba.current_location_id() is null or exists (
        select 1 from gba.rental_bookings b
        where b.tenant_id = rental_securities.tenant_id and b.id = rental_securities.booking_id))
    with check (gba.current_location_id() is null or exists (
        select 1 from gba.rental_bookings b
        where b.tenant_id = rental_securities.tenant_id and b.id = rental_securities.booking_id));
create policy rental_security_events_location_scope on gba.rental_security_events
    as restrictive to gba_runtime
    using (gba.current_location_id() is null or exists (
        select 1 from gba.rental_securities s
        where s.tenant_id = rental_security_events.tenant_id and s.id = rental_security_events.security_id))
    with check (gba.current_location_id() is null or exists (
        select 1 from gba.rental_securities s
        where s.tenant_id = rental_security_events.tenant_id and s.id = rental_security_events.security_id));
