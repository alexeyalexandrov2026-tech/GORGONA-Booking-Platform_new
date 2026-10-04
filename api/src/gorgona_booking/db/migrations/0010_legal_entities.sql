-- Owner-provided legal-entity records stay inside the existing tenant.
-- No default entity, registration fact, branch assignment or financial account is invented.
create table gba.legal_entities (
    tenant_id uuid not null references gba.tenants (id),
    id uuid not null,
    code text not null check (length(code) between 1 and 64 and code ~ '^[A-Z0-9][A-Z0-9_-]*$'),
    created_by uuid not null references gba.users (id),
    created_at timestamptz not null default now(),
    primary key (tenant_id, id),
    constraint legal_entities_code_unique unique (tenant_id, code)
);
alter table gba.legal_entities enable row level security;
alter table gba.legal_entities force row level security;
create policy legal_entities_tenant_isolation on gba.legal_entities
    using (tenant_id = gba.current_tenant_id())
    with check (tenant_id = gba.current_tenant_id());
grant select on gba.legal_entities to gba_runtime;
grant insert (tenant_id, id, code, created_by) on gba.legal_entities to gba_runtime;

create table gba.legal_entity_versions (
    tenant_id uuid not null,
    legal_entity_id uuid not null,
    revision integer not null check (revision > 0),
    legal_name text not null check (
        length(btrim(legal_name, E' \t\r\n')) between 1 and 200
        and legal_name !~ '[[:cntrl:]]'
    ),
    created_by uuid not null references gba.users (id),
    created_at timestamptz not null default now(),
    primary key (tenant_id, legal_entity_id, revision),
    foreign key (tenant_id, legal_entity_id) references gba.legal_entities (tenant_id, id)
);
alter table gba.legal_entity_versions enable row level security;
alter table gba.legal_entity_versions force row level security;
create policy legal_entity_versions_tenant_isolation on gba.legal_entity_versions
    using (tenant_id = gba.current_tenant_id())
    with check (tenant_id = gba.current_tenant_id());
grant select on gba.legal_entity_versions to gba_runtime;
grant insert (tenant_id, legal_entity_id, revision, legal_name, created_by)
    on gba.legal_entity_versions to gba_runtime;

create function gba.reject_legal_entity_mutation() returns trigger language plpgsql as $$
begin
    raise exception using errcode = 'check_violation',
        message = 'legal entity identifiers and saved versions are immutable';
end;
$$;
revoke all on function gba.reject_legal_entity_mutation() from public;
create trigger legal_entities_immutable before update or delete on gba.legal_entities
    for each row execute function gba.reject_legal_entity_mutation();
create trigger legal_entity_versions_immutable before update or delete on gba.legal_entity_versions
    for each row execute function gba.reject_legal_entity_mutation();

-- Legal-entity branch scope: reusable separately when restoring a damaged boundary in tests.
create policy legal_entities_unrestricted_scope on gba.legal_entities
    as restrictive to gba_runtime
    using (gba.current_location_id() is null) with check (gba.current_location_id() is null);
create policy legal_entity_versions_unrestricted_scope on gba.legal_entity_versions
    as restrictive to gba_runtime
    using (gba.current_location_id() is null) with check (gba.current_location_id() is null);
