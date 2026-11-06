-- R4b (package R, RENT-01): the rental agreement as the frozen accepted quote, and its change versions.
-- docs/plan/PACKAGE_R4B_DESIGN_2026-11-06.md. One agreement per booking; version 1 freezes the card in force for the
-- booking's class at its pickup branch when the booking was made, the booking period, the chosen extras copied from the
-- card and the amounts; a later version keeps the card and the period with a reason and new extras. Insert-only.
create table gba.rental_agreements (
    tenant_id uuid not null references gba.tenants(id),
    id uuid not null,
    booking_id uuid not null,
    created_by uuid not null references gba.users(id),
    created_at timestamptz not null default now(),
    primary key (tenant_id, id),
    unique (tenant_id, booking_id),
    foreign key (tenant_id, booking_id) references gba.rental_bookings (tenant_id, id)
);
create table gba.rental_agreement_versions (
    tenant_id uuid not null references gba.tenants(id),
    agreement_id uuid not null,
    version integer not null constraint rental_agreement_versions_version_check check (version > 0),
    rate_card_id uuid not null,
    starts_at timestamptz not null,
    ends_at timestamptz not null,
    month_count integer not null constraint rental_agreement_versions_month_check check (month_count >= 0),
    week_count integer not null constraint rental_agreement_versions_week_check check (week_count >= 0),
    day_count integer not null constraint rental_agreement_versions_day_check check (day_count >= 0),
    hour_count integer not null constraint rental_agreement_versions_hour_check check (hour_count >= 0),
    rental_amount bigint not null constraint rental_agreement_versions_rental_check check (rental_amount > 0),
    rental_days integer not null constraint rental_agreement_versions_days_check check (rental_days > 0),
    total bigint not null constraint rental_agreement_versions_total_check check (total > 0),
    source text not null constraint rental_agreement_versions_source_check
        check (source in ('platform', 'paper', 'email')),
    accepted_by text not null constraint rental_agreement_versions_accepted_by_check
        check (length(btrim(accepted_by)) between 1 and 200),
    accepted_at timestamptz not null,
    reason text constraint rental_agreement_versions_reason_check
        check (reason is null or length(btrim(reason)) between 1 and 500),
    recorded_by uuid not null references gba.users(id),
    created_at timestamptz not null default now(),
    creation_xid xid8 not null default pg_current_xact_id(),
    primary key (tenant_id, agreement_id, version),
    foreign key (tenant_id, agreement_id) references gba.rental_agreements (tenant_id, id),
    foreign key (tenant_id, rate_card_id) references gba.rental_rate_cards (tenant_id, id),
    constraint rental_agreement_versions_first_check check ((version = 1) = (reason is null)),
    constraint rental_agreement_versions_accepted_check check (accepted_at <= created_at)
);
create table gba.rental_agreement_version_extras (
    tenant_id uuid not null references gba.tenants(id),
    agreement_id uuid not null,
    version integer not null,
    code text not null,
    name text not null,
    price bigint not null,
    unit text not null,
    quantity integer not null constraint rental_agreement_version_extras_quantity_check
        check (quantity between 1 and 100),
    amount bigint not null constraint rental_agreement_version_extras_amount_check check (amount >= 0),
    primary key (tenant_id, agreement_id, version, code),
    foreign key (tenant_id, agreement_id, version)
        references gba.rental_agreement_versions (tenant_id, agreement_id, version)
);

-- A version follows its agreement's versions under the class row lock; version 1 names the card in force when the
-- booking was made and the booking period, a later one keeps them; the counts of whole units cover the period and
-- price to the rental amount with the card's rates; a cancelled booking takes no version.
create function gba.guard_rental_agreement_version() returns trigger language plpgsql as $$
declare
    booking record;
    card record;
    latest record;
    in_force uuid;
    hours bigint;
begin
    select b.id, b.class_id, b.pickup_location_id, b.starts_at, b.ends_at, b.booked_at into booking
    from gba.rental_agreements a
      join gba.rental_bookings b on b.tenant_id = a.tenant_id and b.id = a.booking_id
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
          or new.starts_at <> latest.starts_at or new.ends_at <> latest.ends_at then
        raise exception using errcode = 'check_violation',
            constraint = 'rental_agreement_versions_frozen_check',
            message = 'a change keeps the card and the period';
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
revoke all on function gba.guard_rental_agreement_version() from public;
create trigger rental_agreement_versions_guard
    before insert on gba.rental_agreement_versions
    for each row execute function gba.guard_rental_agreement_version();

-- An extra line is recorded with its version and copies its card extra; its amount is the price times the quantity,
-- per rental day for per_day.
create function gba.guard_rental_agreement_version_extra() returns trigger language plpgsql as $$
declare
    owner record;
    days integer;
begin
    select v.rate_card_id, v.rental_days, v.creation_xid into owner
    from gba.rental_agreement_versions v
    where v.tenant_id = new.tenant_id and v.agreement_id = new.agreement_id and v.version = new.version;
    days := 1;
    if new.unit = 'per_day' then
        days := owner.rental_days;
    end if;
    if owner.creation_xid is distinct from pg_current_xact_id() or not exists (
        select 1 from gba.rental_rate_card_extras e
        where e.tenant_id = new.tenant_id and e.card_id = owner.rate_card_id and e.code = new.code
          and e.name = new.name and e.price = new.price and e.unit = new.unit
    ) or new.amount <> new.price * new.quantity * days then
        raise exception using errcode = 'check_violation',
            constraint = 'rental_agreement_version_extras_card_check',
            message = 'an extra line is recorded with its version and copies its card extra';
    end if;
    return new;
end;
$$;
revoke all on function gba.guard_rental_agreement_version_extra() from public;
create trigger rental_agreement_version_extras_guard
    before insert on gba.rental_agreement_version_extras
    for each row execute function gba.guard_rental_agreement_version_extra();

-- At commit, a version's total is its rental amount plus its extra lines.
create function gba.check_rental_agreement_version_total() returns trigger language plpgsql as $$
begin
    if new.total <> new.rental_amount + coalesce((
        select sum(e.amount) from gba.rental_agreement_version_extras e
        where e.tenant_id = new.tenant_id and e.agreement_id = new.agreement_id and e.version = new.version
    ), 0) then
        raise exception using errcode = 'check_violation',
            constraint = 'rental_agreement_versions_total_sum_check',
            message = 'a version total is its rental amount plus its extras';
    end if;
    return null;
end;
$$;
revoke all on function gba.check_rental_agreement_version_total() from public;
create constraint trigger rental_agreement_versions_total
    after insert on gba.rental_agreement_versions
    deferrable initially deferred
    for each row execute function gba.check_rental_agreement_version_total();

-- Writes need the rental module (ADR-0019 gate).
create trigger rental_agreements_module_gate
    before insert on gba.rental_agreements
    for each row execute function gba.require_enabled_module('rental');
create trigger rental_agreement_versions_module_gate
    before insert on gba.rental_agreement_versions
    for each row execute function gba.require_enabled_module('rental');
create trigger rental_agreement_version_extras_module_gate
    before insert on gba.rental_agreement_version_extras
    for each row execute function gba.require_enabled_module('rental');

alter table gba.rental_agreements enable row level security;
alter table gba.rental_agreements force row level security;
alter table gba.rental_agreement_versions enable row level security;
alter table gba.rental_agreement_versions force row level security;
alter table gba.rental_agreement_version_extras enable row level security;
alter table gba.rental_agreement_version_extras force row level security;
create policy rental_agreements_tenant_isolation on gba.rental_agreements
    using (tenant_id = gba.current_tenant_id())
    with check (tenant_id = gba.current_tenant_id());
create policy rental_agreement_versions_tenant_isolation on gba.rental_agreement_versions
    using (tenant_id = gba.current_tenant_id())
    with check (tenant_id = gba.current_tenant_id());
create policy rental_agreement_version_extras_tenant_isolation on gba.rental_agreement_version_extras
    using (tenant_id = gba.current_tenant_id())
    with check (tenant_id = gba.current_tenant_id());
grant select, insert on gba.rental_agreements, gba.rental_agreement_versions, gba.rental_agreement_version_extras
    to gba_runtime;

-- Rental branch scope:
create policy rental_agreements_location_scope on gba.rental_agreements
    as restrictive to gba_runtime
    using (gba.current_location_id() is null or exists (
        select 1 from gba.rental_bookings b
        where b.tenant_id = rental_agreements.tenant_id and b.id = rental_agreements.booking_id))
    with check (gba.current_location_id() is null or exists (
        select 1 from gba.rental_bookings b
        where b.tenant_id = rental_agreements.tenant_id and b.id = rental_agreements.booking_id));
create policy rental_agreement_versions_location_scope on gba.rental_agreement_versions
    as restrictive to gba_runtime
    using (gba.current_location_id() is null or exists (
        select 1 from gba.rental_agreements a
        where a.tenant_id = rental_agreement_versions.tenant_id and a.id = rental_agreement_versions.agreement_id))
    with check (gba.current_location_id() is null or exists (
        select 1 from gba.rental_agreements a
        where a.tenant_id = rental_agreement_versions.tenant_id and a.id = rental_agreement_versions.agreement_id));
create policy rental_agreement_version_extras_location_scope on gba.rental_agreement_version_extras
    as restrictive to gba_runtime
    using (gba.current_location_id() is null or exists (
        select 1 from gba.rental_agreements a
        where a.tenant_id = rental_agreement_version_extras.tenant_id
          and a.id = rental_agreement_version_extras.agreement_id))
    with check (gba.current_location_id() is null or exists (
        select 1 from gba.rental_agreements a
        where a.tenant_id = rental_agreement_version_extras.tenant_id
          and a.id = rental_agreement_version_extras.agreement_id));
