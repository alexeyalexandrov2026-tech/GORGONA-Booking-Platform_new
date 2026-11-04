-- R4a (package R, RENT-01): rental rate cards and their extras.
-- docs/plan/PACKAGE_R4A_DESIGN_2026-11-04.md. A rate card belongs to a class and a branch and is insert-only: a change is
-- the next version of that class and branch, taking effect no earlier than it is recorded. The card in force at an
-- instant is the version with the latest effective_from at or before it. Extras are recorded only with their card.
create table gba.rental_rate_cards (
    tenant_id uuid not null references gba.tenants(id),
    id uuid not null,
    class_id uuid not null,
    location_id uuid not null,
    version integer not null constraint rental_rate_cards_version_check check (version > 0),
    currency text not null constraint rental_rate_cards_currency_check check (currency ~ '^[A-Z]{3}$'),
    effective_from timestamptz not null default now(),
    hour_rate bigint constraint rental_rate_cards_hour_rate_check
        check (hour_rate is null or hour_rate between 1 and 1000000000000),
    day_rate bigint constraint rental_rate_cards_day_rate_check
        check (day_rate is null or day_rate between 1 and 1000000000000),
    week_rate bigint constraint rental_rate_cards_week_rate_check
        check (week_rate is null or week_rate between 1 and 1000000000000),
    month_rate bigint constraint rental_rate_cards_month_rate_check
        check (month_rate is null or month_rate between 1 and 1000000000000),
    meter_allowance_per_day integer constraint rental_rate_cards_allowance_check
        check (meter_allowance_per_day is null or meter_allowance_per_day between 0 and 1000000),
    excess_rate bigint constraint rental_rate_cards_excess_rate_check
        check (excess_rate is null or excess_rate between 0 and 1000000000000),
    created_by uuid not null references gba.users(id),
    created_at timestamptz not null default now(),
    creation_xid xid8 not null default pg_current_xact_id(),
    primary key (tenant_id, id),
    unique (tenant_id, class_id, location_id, version),
    foreign key (tenant_id, class_id) references gba.rental_classes (tenant_id, id),
    foreign key (tenant_id, location_id) references gba.locations (tenant_id, id),
    constraint rental_rate_cards_rates_check
        check (num_nonnulls(hour_rate, day_rate, week_rate, month_rate) > 0)
);
create index rental_rate_cards_in_force on gba.rental_rate_cards
    (tenant_id, class_id, location_id, effective_from desc, version desc);
create table gba.rental_rate_card_extras (
    tenant_id uuid not null references gba.tenants(id),
    card_id uuid not null,
    code text not null constraint rental_rate_card_extras_code_check check (code ~ '^[a-z][a-z0-9_]{0,39}$'),
    name text not null constraint rental_rate_card_extras_name_check
        check (length(btrim(name)) between 1 and 200),
    price bigint not null constraint rental_rate_card_extras_price_check
        check (price between 0 and 1000000000000),
    unit text not null constraint rental_rate_card_extras_unit_check check (unit in ('per_day', 'per_rental')),
    primary key (tenant_id, card_id, code),
    foreign key (tenant_id, card_id) references gba.rental_rate_cards (tenant_id, id)
);

-- A card takes the next version of its class and branch (under the class row lock) and no earlier start than now.
create function gba.guard_rental_rate_card() returns trigger language plpgsql as $$
declare
    latest integer;
begin
    perform 1 from gba.rental_classes c
    where c.tenant_id = new.tenant_id and c.id = new.class_id for update;
    select max(r.version) into latest from gba.rental_rate_cards r
    where r.tenant_id = new.tenant_id and r.class_id = new.class_id and r.location_id = new.location_id;
    if new.version <> coalesce(latest, 0) + 1 then
        raise exception using errcode = 'check_violation',
            constraint = 'rental_rate_cards_version_sequence_check',
            message = 'a rate card takes the next version of its class and branch';
    end if;
    if new.effective_from < now() then
        raise exception using errcode = 'check_violation',
            constraint = 'rental_rate_cards_effective_check',
            message = 'a rate card takes effect no earlier than it is recorded';
    end if;
    return new;
end;
$$;
revoke all on function gba.guard_rental_rate_card() from public;
create trigger rental_rate_cards_guard
    before insert on gba.rental_rate_cards
    for each row execute function gba.guard_rental_rate_card();

-- An extra is recorded in the transaction that recorded its card.
create function gba.guard_rental_rate_card_extra() returns trigger language plpgsql as $$
begin
    if not exists (
        select 1 from gba.rental_rate_cards r
        where r.tenant_id = new.tenant_id and r.id = new.card_id and r.creation_xid = pg_current_xact_id()
    ) then
        raise exception using errcode = 'check_violation',
            constraint = 'rental_rate_card_extras_card_check',
            message = 'an extra is recorded with its card';
    end if;
    return new;
end;
$$;
revoke all on function gba.guard_rental_rate_card_extra() from public;
create trigger rental_rate_card_extras_guard
    before insert on gba.rental_rate_card_extras
    for each row execute function gba.guard_rental_rate_card_extra();

-- Writes need the rental module (ADR-0019 gate).
create trigger rental_rate_cards_module_gate
    before insert on gba.rental_rate_cards
    for each row execute function gba.require_enabled_module('rental');
create trigger rental_rate_card_extras_module_gate
    before insert on gba.rental_rate_card_extras
    for each row execute function gba.require_enabled_module('rental');

alter table gba.rental_rate_cards enable row level security;
alter table gba.rental_rate_cards force row level security;
alter table gba.rental_rate_card_extras enable row level security;
alter table gba.rental_rate_card_extras force row level security;
create policy rental_rate_cards_tenant_isolation on gba.rental_rate_cards
    using (tenant_id = gba.current_tenant_id())
    with check (tenant_id = gba.current_tenant_id());
create policy rental_rate_card_extras_tenant_isolation on gba.rental_rate_card_extras
    using (tenant_id = gba.current_tenant_id())
    with check (tenant_id = gba.current_tenant_id());
grant select, insert on gba.rental_rate_cards, gba.rental_rate_card_extras to gba_runtime;

-- Rental branch scope:
create policy rental_rate_cards_location_scope on gba.rental_rate_cards
    as restrictive to gba_runtime
    using (gba.current_location_id() is null or location_id = gba.current_location_id())
    with check (gba.current_location_id() is null or location_id = gba.current_location_id());
create policy rental_rate_card_extras_location_scope on gba.rental_rate_card_extras
    as restrictive to gba_runtime
    using (gba.current_location_id() is null or exists (
        select 1 from gba.rental_rate_cards r
        where r.tenant_id = rental_rate_card_extras.tenant_id and r.id = rental_rate_card_extras.card_id))
    with check (gba.current_location_id() is null or exists (
        select 1 from gba.rental_rate_cards r
        where r.tenant_id = rental_rate_card_extras.tenant_id and r.id = rental_rate_card_extras.card_id));
