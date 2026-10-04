-- Departments share the company's structure, not independent tenant identities.
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

create table gba.department_versions (
    tenant_id uuid not null,
    department_id uuid not null,
    revision integer not null check (revision > 0),
    name text not null check (
        length(btrim(name, E' \t\r\n')) between 1 and 200 and name !~ '[[:cntrl:]]'
    ),
    parent_department_id uuid,
    location_id uuid,
    legal_entity_id uuid,
    created_by uuid not null references gba.users (id),
    created_at timestamptz not null default now(),
    primary key (tenant_id, department_id, revision),
    foreign key (tenant_id, department_id) references gba.departments (tenant_id, id),
    foreign key (tenant_id, parent_department_id) references gba.departments (tenant_id, id),
    foreign key (tenant_id, location_id) references gba.locations (tenant_id, id),
    foreign key (tenant_id, legal_entity_id) references gba.legal_entities (tenant_id, id)
);
alter table gba.department_versions enable row level security;
alter table gba.department_versions force row level security;
create policy department_versions_tenant_isolation on gba.department_versions
    using (tenant_id = gba.current_tenant_id())
    with check (tenant_id = gba.current_tenant_id());
grant select on gba.department_versions to gba_runtime;
grant insert (tenant_id, department_id, revision, name, parent_department_id,
              location_id, legal_entity_id, created_by)
    on gba.department_versions to gba_runtime;

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

create function gba.validate_department_version() returns trigger language plpgsql as $$
declare
    previous_revision integer;
    ancestor uuid := new.parent_department_id;
    visited uuid[] := array[new.department_id];
begin
    -- Same company structure lock as authorized writes; direct inserts also serialize.
    if pg_catalog.current_setting('transaction_isolation') <> 'read committed' then
        raise exception using errcode = 'check_violation',
            constraint = 'department_isolation',
            message = 'department writes require READ COMMITTED';
    end if;
    perform pg_catalog.pg_advisory_xact_lock(
        pg_catalog.hashtextextended('gba:business-structure:' || new.tenant_id::text, 0)
    );
    select coalesce(max(revision), 0) into previous_revision
        from gba.department_versions
        where tenant_id = new.tenant_id and department_id = new.department_id;
    if new.revision <> previous_revision + 1 then
        raise exception using errcode = 'check_violation',
            constraint = 'department_revision_order', message = 'department version is not consecutive';
    end if;
    while ancestor is not null loop
        if ancestor = any(visited) then
            raise exception using errcode = 'check_violation',
                constraint = 'department_hierarchy', message = 'department hierarchy cannot cycle';
        end if;
        visited := array_append(visited, ancestor);
        select parent_department_id into ancestor from gba.department_versions
            where tenant_id = new.tenant_id and department_id = ancestor
            order by revision desc limit 1;
        if not found then
            raise exception using errcode = 'check_violation',
                constraint = 'department_hierarchy', message = 'parent must have a saved version';
        end if;
    end loop;
    return new;
end;
$$;
revoke all on function gba.validate_department_version() from public;
create trigger department_versions_validate before insert on gba.department_versions
    for each row execute function gba.validate_department_version();

-- Department access scopes: reusable when restoring a damaged boundary in tests.
create policy departments_unrestricted_scope on gba.departments
    as restrictive to gba_runtime
    using (gba.current_location_id() is null) with check (gba.current_location_id() is null);
create policy department_versions_unrestricted_scope on gba.department_versions
    as restrictive to gba_runtime
    using (gba.current_location_id() is null) with check (gba.current_location_id() is null);
-- Department delegation scopes:
create policy departments_delegation_scope on gba.departments
    as restrictive to gba_runtime
    using (gba.current_delegation_grant_id() is null)
    with check (gba.current_delegation_grant_id() is null);
create policy department_versions_delegation_scope on gba.department_versions
    as restrictive to gba_runtime
    using (gba.current_delegation_grant_id() is null)
    with check (gba.current_delegation_grant_id() is null);
