-- M5 (package M, TMS-03): hours-of-service profiles and telematics freshness. ADR-0032.
-- A business keeps insert-only versions of its rule profile; drivers' duty records and vehicles'
-- telematics pings are insert-only facts with a source and the source's record id; a driver's
-- records never overlap. Clearance is computed from these facts and never stored.
create table gba.transport_hos_profiles (
    tenant_id uuid not null references gba.tenants(id),
    revision integer not null constraint transport_hos_profiles_revision_check check (revision > 0),
    code text not null constraint transport_hos_profiles_code_check
        check (code ~ '^[A-Z][A-Z0-9_]{0,63}$'),
    max_driving_minutes integer not null constraint transport_hos_profiles_driving_check
        check (max_driving_minutes between 1 and 1440),
    max_window_minutes integer not null constraint transport_hos_profiles_window_check
        check (max_window_minutes between 1 and 1440),
    reset_minutes integer not null constraint transport_hos_profiles_reset_check
        check (reset_minutes between 1 and 2880),
    cycle_minutes integer not null constraint transport_hos_profiles_cycle_check
        check (cycle_minutes between 1 and 20160),
    cycle_days integer not null constraint transport_hos_profiles_cycle_days_check
        check (cycle_days between 1 and 14),
    max_data_age_minutes integer not null constraint transport_hos_profiles_data_age_check
        check (max_data_age_minutes between 1 and 1440),
    created_by uuid not null references gba.users(id),
    created_at timestamptz not null default now(),
    primary key (tenant_id, revision)
);
create table gba.transport_duty_records (
    tenant_id uuid not null references gba.tenants(id),
    id uuid not null,
    driver_id uuid not null,
    status text not null constraint transport_duty_records_status_check
        check (status in ('off_duty', 'sleeper', 'driving', 'on_duty')),
    starts_at timestamptz not null,
    ends_at timestamptz not null,
    source text not null constraint transport_duty_records_source_check
        check (source ~ '^[a-z][a-z0-9_.-]{0,31}$'),
    source_record_id text not null constraint transport_duty_records_source_record_check
        check (length(btrim(source_record_id)) between 1 and 200
               and source_record_id !~ '[[:cntrl:]]'),
    recorded_by uuid not null references gba.users(id),
    recorded_at timestamptz not null default now(),
    primary key (tenant_id, id),
    unique (tenant_id, source, source_record_id),
    foreign key (tenant_id, driver_id) references gba.transport_drivers (tenant_id, id),
    constraint transport_duty_records_interval_check check (starts_at < ends_at),
    constraint transport_duty_records_no_overlap exclude using gist (
        tenant_id with =, driver_id with =, tstzrange(starts_at, ends_at, '[)') with &&)
);
create table gba.transport_telematics_pings (
    tenant_id uuid not null references gba.tenants(id),
    id uuid not null,
    vehicle_id uuid not null,
    observed_at timestamptz not null,
    source text not null constraint transport_telematics_pings_source_check
        check (source ~ '^[a-z][a-z0-9_.-]{0,31}$'),
    source_record_id text not null constraint transport_telematics_pings_source_record_check
        check (length(btrim(source_record_id)) between 1 and 200
               and source_record_id !~ '[[:cntrl:]]'),
    recorded_by uuid not null references gba.users(id),
    recorded_at timestamptz not null default now(),
    primary key (tenant_id, id),
    unique (tenant_id, source, source_record_id),
    foreign key (tenant_id, vehicle_id) references gba.transport_vehicles (tenant_id, id)
);

-- A profile version follows the previous one of its business.
create function gba.guard_transport_hos_profile() returns trigger language plpgsql as $$
begin
    perform pg_catalog.pg_advisory_xact_lock(
        pg_catalog.hashtextextended('gba:hos-profile:' || new.tenant_id::text, 0));
    if new.revision <> coalesce((
        select max(p.revision) from gba.transport_hos_profiles p
         where p.tenant_id = new.tenant_id), 0) + 1 then
        raise exception using errcode = 'check_violation',
            constraint = 'transport_hos_profiles_revision_check',
            message = 'a profile version follows the previous one';
    end if;
    return new;
end;
$$;
revoke all on function gba.guard_transport_hos_profile() from public;
create trigger transport_hos_profiles_guard before insert on gba.transport_hos_profiles
    for each row execute function gba.guard_transport_hos_profile();

-- Writes need the transport module (ADR-0019 gate).
create trigger transport_hos_profiles_module_gate before insert on gba.transport_hos_profiles
    for each row execute function gba.require_enabled_module('transport');
create trigger transport_duty_records_module_gate before insert on gba.transport_duty_records
    for each row execute function gba.require_enabled_module('transport');
create trigger transport_telematics_pings_module_gate
    before insert on gba.transport_telematics_pings
    for each row execute function gba.require_enabled_module('transport');

alter table gba.transport_hos_profiles enable row level security;
alter table gba.transport_hos_profiles force row level security;
alter table gba.transport_duty_records enable row level security;
alter table gba.transport_duty_records force row level security;
alter table gba.transport_telematics_pings enable row level security;
alter table gba.transport_telematics_pings force row level security;
create policy transport_hos_profiles_tenant_isolation on gba.transport_hos_profiles
    using (tenant_id = gba.current_tenant_id())
    with check (tenant_id = gba.current_tenant_id());
create policy transport_duty_records_tenant_isolation on gba.transport_duty_records
    using (tenant_id = gba.current_tenant_id())
    with check (tenant_id = gba.current_tenant_id());
create policy transport_telematics_pings_tenant_isolation on gba.transport_telematics_pings
    using (tenant_id = gba.current_tenant_id())
    with check (tenant_id = gba.current_tenant_id());
grant select on gba.transport_hos_profiles, gba.transport_duty_records,
    gba.transport_telematics_pings to gba_runtime;
grant insert (tenant_id, revision, code, max_driving_minutes, max_window_minutes, reset_minutes,
              cycle_minutes, cycle_days, max_data_age_minutes, created_by)
    on gba.transport_hos_profiles to gba_runtime;
grant insert (tenant_id, id, driver_id, status, starts_at, ends_at, source, source_record_id,
              recorded_by)
    on gba.transport_duty_records to gba_runtime;
grant insert (tenant_id, id, vehicle_id, observed_at, source, source_record_id, recorded_by)
    on gba.transport_telematics_pings to gba_runtime;

-- Transport clearance branch scope:
create policy transport_duty_records_location_scope on gba.transport_duty_records
    as restrictive to gba_runtime
    using (gba.current_location_id() is null or exists (
        select 1 from gba.transport_drivers d
        where d.tenant_id = transport_duty_records.tenant_id
          and d.id = transport_duty_records.driver_id))
    with check (gba.current_location_id() is null or exists (
        select 1 from gba.transport_drivers d
        where d.tenant_id = transport_duty_records.tenant_id
          and d.id = transport_duty_records.driver_id));
create policy transport_telematics_pings_location_scope on gba.transport_telematics_pings
    as restrictive to gba_runtime
    using (gba.current_location_id() is null or exists (
        select 1 from gba.transport_vehicles v
        where v.tenant_id = transport_telematics_pings.tenant_id
          and v.id = transport_telematics_pings.vehicle_id))
    with check (gba.current_location_id() is null or exists (
        select 1 from gba.transport_vehicles v
        where v.tenant_id = transport_telematics_pings.tenant_id
          and v.id = transport_telematics_pings.vehicle_id));
