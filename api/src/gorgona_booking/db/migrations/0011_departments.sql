-- Owner-provided departments stay inside the existing tenant (ADR-0016).
-- No default department, head, budget, employee assignment or link is invented.
create table gba.departments (
    tenant_id uuid not null references gba.tenants (id),
    id uuid not null,
    code text not null check (length(code) between 1 and 64 and code ~ '^[A-Z0-9][A-Z0-9_-]*$'),
    created_by uuid not null references gba.users (id),
    created_at timestamptz not null default now(),
    primary key (tenant_id, id),
    constraint departments_code_unique unique (tenant_id, code)
);
alter table gba.departments enable row level security;
alter table gba.departments force row level security;
create policy departments_tenant_isolation on gba.departments
    using (tenant_id = gba.current_tenant_id())
    with check (tenant_id = gba.current_tenant_id());
grant select on gba.departments to gba_runtime;
grant insert (tenant_id, id, code, created_by) on gba.departments to gba_runtime;

-- Optional links are company-bound: a parent department, legal entity or
-- location of another company cannot be referenced.
create table gba.department_versions (
    tenant_id uuid not null,
    department_id uuid not null,
    revision integer not null check (revision > 0),
    name text not null check (
        length(btrim(name, E' \t\r\n')) between 1 and 200
        and name !~ '[[:cntrl:]]'
    ),
    parent_department_id uuid,
    legal_entity_id uuid,
    location_id uuid,
    archived boolean not null,
    created_by uuid not null references gba.users (id),
    created_at timestamptz not null default now(),
    primary key (tenant_id, department_id, revision),
    foreign key (tenant_id, department_id) references gba.departments (tenant_id, id),
    constraint department_versions_parent_fk foreign key (tenant_id, parent_department_id)
        references gba.departments (tenant_id, id),
    constraint department_versions_legal_entity_fk foreign key (tenant_id, legal_entity_id)
        references gba.legal_entities (tenant_id, id),
    constraint department_versions_location_fk foreign key (tenant_id, location_id)
        references gba.locations (tenant_id, id),
    constraint department_versions_not_own_parent check (parent_department_id <> department_id)
);
alter table gba.department_versions enable row level security;
alter table gba.department_versions force row level security;
create policy department_versions_tenant_isolation on gba.department_versions
    using (tenant_id = gba.current_tenant_id())
    with check (tenant_id = gba.current_tenant_id());
grant select on gba.department_versions to gba_runtime;
grant insert (
    tenant_id, department_id, revision, name, parent_department_id, legal_entity_id,
    location_id, archived, created_by
) on gba.department_versions to gba_runtime;

create function gba.reject_department_mutation() returns trigger language plpgsql as $$
begin
    raise exception using errcode = 'check_violation',
        message = 'department identifiers and saved versions are immutable';
end;
$$;
revoke all on function gba.reject_department_mutation() from public;
create trigger departments_immutable before update or delete on gba.departments
    for each row execute function gba.reject_department_mutation();
create trigger department_versions_immutable before update or delete on gba.department_versions
    for each row execute function gba.reject_department_mutation();

-- Department branch scope: reusable separately when restoring a damaged boundary in tests.
create policy departments_unrestricted_scope on gba.departments
    as restrictive to gba_runtime
    using (gba.current_location_id() is null) with check (gba.current_location_id() is null);
create policy department_versions_unrestricted_scope on gba.department_versions
    as restrictive to gba_runtime
    using (gba.current_location_id() is null) with check (gba.current_location_id() is null);
