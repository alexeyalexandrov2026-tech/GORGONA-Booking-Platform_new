-- N1 (package N): broker authority and carrier profiles as dated facts. ADR-0034.
-- A business keeps insert-only versions of its broker authority; each carrier (a counterparty) has
-- insert-only versions of its profile. Eligibility is computed for a date and never stored.
create table gba.transport_broker_authorities (
    tenant_id uuid not null references gba.tenants(id),
    revision integer not null constraint transport_broker_authorities_revision_check
        check (revision > 0),
    jurisdiction text not null constraint transport_broker_authorities_jurisdiction_check
        check (jurisdiction ~ '^[A-Z]{2}$'),
    authority_number text not null constraint transport_broker_authorities_number_check
        check (length(btrim(authority_number)) between 1 and 32
               and authority_number !~ '[[:cntrl:]]'),
    bond_reference text not null constraint transport_broker_authorities_bond_check
        check (length(btrim(bond_reference)) between 1 and 64 and bond_reference !~ '[[:cntrl:]]'),
    status text not null constraint transport_broker_authorities_status_check
        check (status in ('active', 'withdrawn')),
    effective_from date not null,
    expires_on date,
    source text not null constraint transport_broker_authorities_source_check
        check (source ~ '^[a-z][a-z0-9_.-]{0,31}$'),
    checked_on date not null,
    created_by uuid not null references gba.users(id),
    created_at timestamptz not null default now(),
    primary key (tenant_id, revision),
    constraint transport_broker_authorities_period_check
        check (expires_on is null or expires_on >= effective_from)
);
create table gba.transport_carrier_profiles (
    tenant_id uuid not null references gba.tenants(id),
    counterparty_id uuid not null,
    revision integer not null constraint transport_carrier_profiles_revision_check
        check (revision > 0),
    jurisdiction text not null constraint transport_carrier_profiles_jurisdiction_check
        check (jurisdiction ~ '^[A-Z]{2}$'),
    authority_number text constraint transport_carrier_profiles_number_check
        check (authority_number is null or (length(btrim(authority_number)) between 1 and 32
               and authority_number !~ '[[:cntrl:]]')),
    liability_expires_on date,
    cargo_expires_on date,
    safety_rating text not null constraint transport_carrier_profiles_rating_check
        check (safety_rating in ('satisfactory', 'conditional', 'unsatisfactory', 'unrated')),
    source text not null constraint transport_carrier_profiles_source_check
        check (source ~ '^[a-z][a-z0-9_.-]{0,31}$'),
    checked_on date not null,
    created_by uuid not null references gba.users(id),
    created_at timestamptz not null default now(),
    primary key (tenant_id, counterparty_id, revision),
    foreign key (tenant_id, counterparty_id) references gba.counterparties (tenant_id, id)
);

-- A version follows the previous one (of the business, or of the carrier).
create function gba.guard_transport_broker_authority() returns trigger language plpgsql as $$
begin
    perform pg_catalog.pg_advisory_xact_lock(
        pg_catalog.hashtextextended('gba:broker-authority:' || new.tenant_id::text, 0));
    if new.revision <> coalesce((
        select max(a.revision) from gba.transport_broker_authorities a
         where a.tenant_id = new.tenant_id), 0) + 1 then
        raise exception using errcode = 'check_violation',
            constraint = 'transport_broker_authorities_revision_check',
            message = 'an authority version follows the previous one';
    end if;
    return new;
end;
$$;
revoke all on function gba.guard_transport_broker_authority() from public;
create trigger transport_broker_authorities_guard before insert on gba.transport_broker_authorities
    for each row execute function gba.guard_transport_broker_authority();
create function gba.guard_transport_carrier_profile() returns trigger language plpgsql as $$
begin
    perform pg_catalog.pg_advisory_xact_lock(
        pg_catalog.hashtextextended('gba:carrier-profile:' || new.counterparty_id::text, 0));
    if new.revision <> coalesce((
        select max(p.revision) from gba.transport_carrier_profiles p
         where p.tenant_id = new.tenant_id and p.counterparty_id = new.counterparty_id), 0) + 1 then
        raise exception using errcode = 'check_violation',
            constraint = 'transport_carrier_profiles_revision_check',
            message = 'a profile version follows the previous one';
    end if;
    return new;
end;
$$;
revoke all on function gba.guard_transport_carrier_profile() from public;
create trigger transport_carrier_profiles_guard before insert on gba.transport_carrier_profiles
    for each row execute function gba.guard_transport_carrier_profile();

-- Writes need the transport module (ADR-0019 gate).
create trigger transport_broker_authorities_module_gate
    before insert on gba.transport_broker_authorities
    for each row execute function gba.require_enabled_module('transport');
create trigger transport_carrier_profiles_module_gate before insert on gba.transport_carrier_profiles
    for each row execute function gba.require_enabled_module('transport');

alter table gba.transport_broker_authorities enable row level security;
alter table gba.transport_broker_authorities force row level security;
alter table gba.transport_carrier_profiles enable row level security;
alter table gba.transport_carrier_profiles force row level security;
create policy transport_broker_authorities_tenant_isolation on gba.transport_broker_authorities
    using (tenant_id = gba.current_tenant_id())
    with check (tenant_id = gba.current_tenant_id());
create policy transport_carrier_profiles_tenant_isolation on gba.transport_carrier_profiles
    using (tenant_id = gba.current_tenant_id())
    with check (tenant_id = gba.current_tenant_id());
grant select on gba.transport_broker_authorities, gba.transport_carrier_profiles to gba_runtime;
grant insert (tenant_id, revision, jurisdiction, authority_number, bond_reference, status,
              effective_from, expires_on, source, checked_on, created_by)
    on gba.transport_broker_authorities to gba_runtime;
grant insert (tenant_id, counterparty_id, revision, jurisdiction, authority_number,
              liability_expires_on, cargo_expires_on, safety_rating, source, checked_on, created_by)
    on gba.transport_carrier_profiles to gba_runtime;

-- Broker branch scope: company-wide facts; a branch-limited session sees none of them.
create policy transport_broker_authorities_company on gba.transport_broker_authorities
    as restrictive to gba_runtime
    using (gba.current_location_id() is null)
    with check (gba.current_location_id() is null);
create policy transport_carrier_profiles_company on gba.transport_carrier_profiles
    as restrictive to gba_runtime
    using (gba.current_location_id() is null)
    with check (gba.current_location_id() is null);
