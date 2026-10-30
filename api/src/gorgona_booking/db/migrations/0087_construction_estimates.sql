-- O1 (package O, BUILD-01): construction projects and estimate versions. ADR-0035.
-- A project has one currency and a site time zone; estimate versions and their lines are insert-only
-- (only the one-time proposal stamp of the latest version may be set); totals are derived on read.
create table gba.construction_projects (
    tenant_id uuid not null references gba.tenants(id),
    id uuid not null,
    location_id uuid not null,
    number text not null constraint construction_projects_number_check
        check (length(btrim(number)) between 1 and 64 and number !~ '[[:cntrl:]]'),
    name text not null constraint construction_projects_name_check
        check (length(btrim(name)) between 1 and 200 and name !~ '[[:cntrl:]]'),
    customer_id uuid not null,
    site_address text not null constraint construction_projects_site_address_check
        check (length(btrim(site_address)) between 1 and 500),
    time_zone text not null,
    currency text not null references gba.currencies (code),
    revision integer not null constraint construction_projects_revision_check
        check (revision > 0),
    created_by uuid not null references gba.users(id),
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    primary key (tenant_id, id),
    unique (tenant_id, number),
    foreign key (tenant_id, location_id) references gba.locations (tenant_id, id),
    foreign key (tenant_id, customer_id) references gba.counterparties (tenant_id, id)
);
create table gba.construction_estimate_versions (
    tenant_id uuid not null references gba.tenants(id),
    project_id uuid not null,
    version integer not null constraint construction_estimate_versions_version_check
        check (version between 1 and 100000),
    note text constraint construction_estimate_versions_note_check
        check (note is null or length(note) between 1 and 1000),
    created_by uuid not null references gba.users(id),
    created_at timestamptz not null default now(),
    proposed_at timestamptz,
    proposed_by uuid references gba.users(id),
    primary key (tenant_id, project_id, version),
    foreign key (tenant_id, project_id) references gba.construction_projects (tenant_id, id),
    constraint construction_estimate_versions_stamp_check
        check ((proposed_at is null) = (proposed_by is null))
);
create table gba.construction_estimate_lines (
    tenant_id uuid not null references gba.tenants(id),
    project_id uuid not null,
    version integer not null,
    position smallint not null constraint construction_estimate_lines_position_check
        check (position between 1 and 500),
    kind text not null constraint construction_estimate_lines_kind_check
        check (kind in ('material', 'labor', 'equipment', 'subcontract', 'other')),
    description text not null constraint construction_estimate_lines_description_check
        check (length(btrim(description)) between 1 and 500),
    phase text not null constraint construction_estimate_lines_phase_check
        check (length(btrim(phase)) between 1 and 64 and phase !~ '[[:cntrl:]]'),
    quantity numeric(13, 4) not null constraint construction_estimate_lines_quantity_check
        check (quantity > 0),
    unit text not null constraint construction_estimate_lines_unit_check
        check (length(btrim(unit)) between 1 and 16 and unit !~ '[[:cntrl:]]'),
    unit_cost_minor bigint not null constraint construction_estimate_lines_cost_check
        check (unit_cost_minor between 0 and 1000000000000),
    unit_price_minor bigint not null constraint construction_estimate_lines_price_check
        check (unit_price_minor between 0 and 1000000000000),
    material_id uuid,
    primary key (tenant_id, project_id, version, position),
    foreign key (tenant_id, project_id, version)
        references gba.construction_estimate_versions (tenant_id, project_id, version),
    foreign key (tenant_id, material_id) references gba.stock_items (tenant_id, id)
);

-- A project names a time zone PostgreSQL knows; its currency is fixed once it has an estimate.
create function gba.guard_construction_project() returns trigger language plpgsql as $$
begin
    if not exists (select 1 from pg_catalog.pg_timezone_names z where z.name = new.time_zone) then
        raise exception using errcode = 'check_violation',
            constraint = 'construction_projects_time_zone_check',
            message = 'a project names a known time zone';
    end if;
    if tg_op = 'UPDATE' and new.currency <> old.currency and exists (
        select 1 from gba.construction_estimate_versions v
        where v.tenant_id = new.tenant_id and v.project_id = new.id
    ) then
        raise exception using errcode = 'check_violation',
            constraint = 'construction_projects_currency_check',
            message = 'a project with an estimate keeps its currency';
    end if;
    return new;
end;
$$;
revoke all on function gba.guard_construction_project() from public;
create trigger construction_projects_guard
    before insert or update on gba.construction_projects
    for each row execute function gba.guard_construction_project();

-- Versions follow each other; only the latest version gets its proposal stamp, once.
create function gba.guard_construction_estimate_version() returns trigger language plpgsql as $$
begin
    if tg_op = 'INSERT' then
        if new.proposed_at is not null or new.version <> coalesce((
            select max(v.version) from gba.construction_estimate_versions v
            where v.tenant_id = new.tenant_id and v.project_id = new.project_id), 0) + 1 then
            raise exception using errcode = 'check_violation',
                constraint = 'construction_estimate_versions_sequence_check',
                message = 'an estimate version follows the latest one, unproposed';
        end if;
        return new;
    end if;
    if old.proposed_at is not null or new.proposed_at is null
       or (new.tenant_id, new.project_id, new.version, new.note, new.created_by, new.created_at)
          is distinct from
          (old.tenant_id, old.project_id, old.version, old.note, old.created_by, old.created_at)
       or exists (
           select 1 from gba.construction_estimate_versions v
           where v.tenant_id = new.tenant_id and v.project_id = new.project_id
             and v.version > new.version) then
        raise exception using errcode = 'check_violation',
            constraint = 'construction_estimate_versions_proposal_check',
            message = 'only the latest estimate version is proposed, once';
    end if;
    return new;
end;
$$;
revoke all on function gba.guard_construction_estimate_version() from public;
create trigger construction_estimate_versions_guard
    before insert or update on gba.construction_estimate_versions
    for each row execute function gba.guard_construction_estimate_version();

-- A version's lines are written with the version, in the same transaction, before any proposal.
create function gba.guard_construction_estimate_line() returns trigger language plpgsql as $$
begin
    if not exists (
        select 1 from gba.construction_estimate_versions v
        where v.tenant_id = new.tenant_id and v.project_id = new.project_id
          and v.version = new.version and v.created_at = now() and v.proposed_at is null
    ) then
        raise exception using errcode = 'check_violation',
            constraint = 'construction_estimate_lines_version_check',
            message = 'estimate lines are written with their version';
    end if;
    return new;
end;
$$;
revoke all on function gba.guard_construction_estimate_line() from public;
create trigger construction_estimate_lines_guard
    before insert on gba.construction_estimate_lines
    for each row execute function gba.guard_construction_estimate_line();

-- Writes need the construction module (ADR-0019 gate).
create trigger construction_projects_module_gate
    before insert on gba.construction_projects
    for each row execute function gba.require_enabled_module('construction');
create trigger construction_estimate_versions_module_gate
    before insert on gba.construction_estimate_versions
    for each row execute function gba.require_enabled_module('construction');

alter table gba.construction_projects enable row level security;
alter table gba.construction_projects force row level security;
alter table gba.construction_estimate_versions enable row level security;
alter table gba.construction_estimate_versions force row level security;
alter table gba.construction_estimate_lines enable row level security;
alter table gba.construction_estimate_lines force row level security;
create policy construction_projects_tenant_isolation on gba.construction_projects
    using (tenant_id = gba.current_tenant_id())
    with check (tenant_id = gba.current_tenant_id());
create policy construction_estimate_versions_tenant_isolation
    on gba.construction_estimate_versions
    using (tenant_id = gba.current_tenant_id())
    with check (tenant_id = gba.current_tenant_id());
create policy construction_estimate_lines_tenant_isolation on gba.construction_estimate_lines
    using (tenant_id = gba.current_tenant_id())
    with check (tenant_id = gba.current_tenant_id());
grant select, insert on gba.construction_projects, gba.construction_estimate_versions,
    gba.construction_estimate_lines to gba_runtime;
grant update (location_id, number, name, customer_id, site_address, time_zone, currency, revision,
    updated_at) on gba.construction_projects to gba_runtime;
grant update (proposed_at, proposed_by) on gba.construction_estimate_versions to gba_runtime;

-- Construction branch scope:
create policy construction_projects_location_scope on gba.construction_projects
    as restrictive to gba_runtime
    using (gba.current_location_id() is null or location_id = gba.current_location_id())
    with check (gba.current_location_id() is null or location_id = gba.current_location_id());
create policy construction_estimate_versions_location_scope on gba.construction_estimate_versions
    as restrictive to gba_runtime
    using (gba.current_location_id() is null or exists (
        select 1 from gba.construction_projects p
        where p.tenant_id = construction_estimate_versions.tenant_id
          and p.id = construction_estimate_versions.project_id))
    with check (gba.current_location_id() is null or exists (
        select 1 from gba.construction_projects p
        where p.tenant_id = construction_estimate_versions.tenant_id
          and p.id = construction_estimate_versions.project_id));
create policy construction_estimate_lines_location_scope on gba.construction_estimate_lines
    as restrictive to gba_runtime
    using (gba.current_location_id() is null or exists (
        select 1 from gba.construction_projects p
        where p.tenant_id = construction_estimate_lines.tenant_id
          and p.id = construction_estimate_lines.project_id))
    with check (gba.current_location_id() is null or exists (
        select 1 from gba.construction_projects p
        where p.tenant_id = construction_estimate_lines.tenant_id
          and p.id = construction_estimate_lines.project_id));
