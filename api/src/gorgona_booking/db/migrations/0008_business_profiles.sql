-- Additive, append-only business profile drafts. Existing tenants, booking data
-- and permissions are not copied or rewritten. No industry workflow is enabled.
create table gba.business_profile_versions (
    tenant_id uuid not null references gba.tenants (id),
    id uuid not null default uuidv7(),
    revision integer not null check (revision > 0),
    catalog_version integer not null check (catalog_version = 1),
    custom_activity_name text check (
        custom_activity_name is null or length(btrim(custom_activity_name)) between 1 and 200
    ),
    created_by uuid not null references gba.users (id),
    created_at timestamptz not null default now(),
    created_transaction xid8 not null default pg_catalog.pg_current_xact_id(),
    primary key (tenant_id, revision),
    unique (tenant_id, id)
);
alter table gba.business_profile_versions enable row level security;
alter table gba.business_profile_versions force row level security;
create policy business_profile_versions_tenant_isolation on gba.business_profile_versions
    using (tenant_id = gba.current_tenant_id())
    with check (tenant_id = gba.current_tenant_id());
grant select on gba.business_profile_versions to gba_runtime;
grant insert (tenant_id, revision, catalog_version, custom_activity_name, created_by)
    on gba.business_profile_versions to gba_runtime;
-- The service writes one audit event with the complete selection in its transaction.

create table gba.business_profile_industries (
    tenant_id uuid not null,
    revision integer not null,
    industry_id smallint not null check (industry_id between 1 and 39),
    primary key (tenant_id, revision, industry_id),
    foreign key (tenant_id, revision)
        references gba.business_profile_versions (tenant_id, revision)
);
alter table gba.business_profile_industries enable row level security;
alter table gba.business_profile_industries force row level security;
create policy business_profile_industries_tenant_isolation on gba.business_profile_industries
    using (tenant_id = gba.current_tenant_id())
    with check (tenant_id = gba.current_tenant_id());
grant select, insert on gba.business_profile_industries to gba_runtime;

create table gba.business_profile_formats (
    tenant_id uuid not null,
    revision integer not null,
    format text not null check (format in ('b2b', 'b2c', 'marketplace', 'franchise', 'holding')),
    primary key (tenant_id, revision, format),
    foreign key (tenant_id, revision)
        references gba.business_profile_versions (tenant_id, revision)
);
alter table gba.business_profile_formats enable row level security;
alter table gba.business_profile_formats force row level security;
create policy business_profile_formats_tenant_isolation on gba.business_profile_formats
    using (tenant_id = gba.current_tenant_id())
    with check (tenant_id = gba.current_tenant_id());
grant select, insert on gba.business_profile_formats to gba_runtime;

-- A committed revision is an immutable snapshot, including its child selections.
-- Child rows may only be attached in the transaction which created the header.
create function gba.guard_business_profile_snapshot() returns trigger
    language plpgsql
as $$
begin
    if tg_op <> 'INSERT' then
        raise exception using errcode = 'check_violation',
            message = 'business profile revisions are immutable';
    end if;
    if not exists (
        select 1 from gba.business_profile_versions v
        where v.tenant_id = new.tenant_id and v.revision = new.revision
          and v.created_transaction = pg_catalog.pg_current_xact_id()
    ) then
        raise exception using errcode = 'check_violation',
            message = 'cannot append selections to a committed profile revision';
    end if;
    return new;
end;
$$;
revoke all on function gba.guard_business_profile_snapshot() from public;
create trigger business_profile_versions_immutable
    before update or delete on gba.business_profile_versions
    for each row execute function gba.guard_business_profile_snapshot();
create trigger business_profile_industries_immutable
    before insert or update or delete on gba.business_profile_industries
    for each row execute function gba.guard_business_profile_snapshot();
create trigger business_profile_formats_immutable
    before insert or update or delete on gba.business_profile_formats
    for each row execute function gba.guard_business_profile_snapshot();
