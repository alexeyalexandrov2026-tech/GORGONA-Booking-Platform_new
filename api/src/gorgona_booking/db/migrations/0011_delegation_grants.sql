-- 0011_delegation_grants: limited delegation between independent businesses (ADR-0016).
-- The owner business keeps its tenant, rows and audit trail. The serving business names its
-- own employees. Every delegated request re-checks both companies, the employee and the
-- current grant revision inside its own transaction; nothing here widens other paths.

-- Set only transaction-locally after a delegated request is authorized. It narrows access
-- through restrictive policies and never admits a row by itself.
create function gba.current_delegation_grant_id() returns uuid
    language sql stable parallel safe
as $$
    select nullif(pg_catalog.current_setting('gba.delegation_grant_id', true), '')::uuid
$$;
revoke all on function gba.current_delegation_grant_id() from public;
grant execute on function gba.current_delegation_grant_id() to gba_runtime;

create function gba.text_array_strictly_sorted(items text[]) returns boolean
    language sql immutable parallel safe
as $$
    select coalesce(bool_and(pair.earlier collate "C" < pair.later), true)
    from unnest(items[1:cardinality(items) - 1], items[2:]) as pair(earlier, later)
$$;
revoke all on function gba.text_array_strictly_sorted(text[]) from public;
grant execute on function gba.text_array_strictly_sorted(text[]) to gba_runtime;

-- Lets one composite foreign key prove that a designation's user owns its membership.
alter table gba.memberships
    add constraint memberships_tenant_id_user_key unique (tenant_id, id, user_id);

-- Grant identity: owner business -> one other serving business. Never updated or deleted.
create table gba.delegation_grants (
    tenant_id           uuid not null references gba.tenants (id),
    id                  uuid not null,
    grantee_business_id uuid not null references gba.tenants (id),
    created_by          uuid not null references gba.users (id),
    created_at          timestamptz not null default now(),
    primary key (tenant_id, id),
    constraint delegation_grants_grantee_grant_key unique (grantee_business_id, id),
    constraint delegation_grants_route_key unique (tenant_id, id, grantee_business_id),
    constraint delegation_grants_independent_business check (grantee_business_id <> tenant_id)
);
alter table gba.delegation_grants enable row level security;
alter table gba.delegation_grants force row level security;
grant select on gba.delegation_grants to gba_runtime;
grant insert (tenant_id, id, grantee_business_id, created_by) on gba.delegation_grants
    to gba_runtime;

-- Owner-controlled terms: append-only, sequential revisions; a revoked grant is terminal.
create table gba.delegation_grant_versions (
    tenant_id           uuid not null,
    grant_id            uuid not null,
    grantee_business_id uuid not null,
    revision            integer not null
                        constraint delegation_grant_versions_revision_positive check (revision > 0),
    state               text not null
                        constraint delegation_grant_versions_state_valid
                        check (state in ('active', 'revoked')),
    purpose             text not null
                        constraint delegation_grant_versions_purpose_valid check (
                            length(btrim(purpose, E' \t\r\n')) between 1 and 200
                            and purpose !~ '[[:cntrl:]]'),
    permissions         text[] not null
                        constraint delegation_grant_versions_permissions_valid check (
                            array_ndims(permissions) = 1
                            and cardinality(permissions) between 1 and 4
                            and array_position(permissions, null) is null
                            and permissions <@ array['booking.read', 'booking.write',
                                                     'catalog.read', 'staff.read']::text[]
                            and gba.text_array_strictly_sorted(permissions)
                            and (not permissions @> array['booking.write']::text[]
                                 or permissions @> array['booking.read', 'catalog.read',
                                                         'staff.read']::text[])),
    location_id         uuid,
    valid_from          timestamptz not null,
    valid_until         timestamptz not null,
    created_by          uuid not null references gba.users (id),
    created_at          timestamptz not null default now(),
    primary key (tenant_id, grant_id, revision),
    constraint delegation_grant_versions_grant_fk
        foreign key (tenant_id, grant_id, grantee_business_id)
        references gba.delegation_grants (tenant_id, id, grantee_business_id),
    constraint delegation_grant_versions_location_fk
        foreign key (tenant_id, location_id) references gba.locations (tenant_id, id),
    constraint delegation_grant_versions_term check (
        valid_until > valid_from and valid_until <= valid_from + interval '366 days')
);
alter table gba.delegation_grant_versions enable row level security;
alter table gba.delegation_grant_versions force row level security;
grant select on gba.delegation_grant_versions to gba_runtime;
grant insert (tenant_id, grant_id, grantee_business_id, revision, state, purpose, permissions,
              location_id, valid_from, valid_until, created_by)
    on gba.delegation_grant_versions to gba_runtime;

create function gba.reject_delegation_grant_mutation() returns trigger
    language plpgsql
as $$
begin
    raise exception using errcode = 'check_violation',
        message = 'delegation grants and saved revisions are immutable',
        constraint = 'delegation_grants_immutable';
end;
$$;
revoke all on function gba.reject_delegation_grant_mutation() from public;
create trigger delegation_grants_immutable before update or delete on gba.delegation_grants
    for each row execute function gba.reject_delegation_grant_mutation();
create trigger delegation_grant_versions_immutable
    before update or delete on gba.delegation_grant_versions
    for each row execute function gba.reject_delegation_grant_mutation();

create function gba.enforce_delegation_grant_revision() returns trigger
    language plpgsql
as $$
declare
    previous_revision integer;
    previous_state    text;
begin
    select revision, state into previous_revision, previous_state
      from gba.delegation_grant_versions
     where tenant_id = new.tenant_id and grant_id = new.grant_id
     order by revision desc
     limit 1;
    if new.revision is distinct from coalesce(previous_revision, 0) + 1 then
        raise exception using errcode = 'check_violation',
            message = 'delegation grant revisions are sequential',
            constraint = 'delegation_grant_versions_sequential';
    end if;
    if previous_state = 'revoked' then
        raise exception using errcode = 'check_violation',
            message = 'a revoked delegation grant cannot change',
            constraint = 'delegation_grant_versions_revoked_terminal';
    end if;
    if previous_revision is null and new.state <> 'active' then
        raise exception using errcode = 'check_violation',
            message = 'a delegation grant starts active',
            constraint = 'delegation_grant_versions_starts_active';
    end if;
    return new;
end;
$$;
revoke all on function gba.enforce_delegation_grant_revision() from public;
create trigger delegation_grant_versions_sequential
    before insert on gba.delegation_grant_versions
    for each row execute function gba.enforce_delegation_grant_revision();

-- Serving-business decision: which of its own active memberships may use a grant.
create table gba.delegation_designations (
    tenant_id           uuid not null references gba.tenants (id),
    id                  uuid not null default uuidv7(),
    grantor_business_id uuid not null,
    grant_id            uuid not null,
    membership_id       uuid not null,
    user_id             uuid not null,
    status              text not null default 'active'
                        constraint delegation_designations_status_valid
                        check (status in ('active', 'removed')),
    created_by          uuid not null references gba.users (id),
    created_at          timestamptz not null default now(),
    removed_by          uuid references gba.users (id),
    removed_at          timestamptz,
    primary key (tenant_id, id),
    constraint delegation_designations_grant_fk
        foreign key (grantor_business_id, grant_id, tenant_id)
        references gba.delegation_grants (tenant_id, id, grantee_business_id),
    constraint delegation_designations_membership_fk
        foreign key (tenant_id, membership_id, user_id)
        references gba.memberships (tenant_id, id, user_id),
    constraint delegation_designations_removal_complete check (
        (status = 'removed') = (removed_by is not null and removed_at is not null))
);
create unique index delegation_designations_one_active
    on gba.delegation_designations (tenant_id, grantor_business_id, grant_id, membership_id)
    where status = 'active';
create index delegation_designations_grantor_idx
    on gba.delegation_designations (grantor_business_id, grant_id) where status = 'active';
create index delegation_designations_user_idx
    on gba.delegation_designations (user_id) where status = 'active';
alter table gba.delegation_designations enable row level security;
alter table gba.delegation_designations force row level security;
grant select on gba.delegation_designations to gba_runtime;
grant insert (tenant_id, grantor_business_id, grant_id, membership_id, user_id, created_by)
    on gba.delegation_designations to gba_runtime;
grant update (status, removed_by, removed_at) on gba.delegation_designations to gba_runtime;

create function gba.enforce_delegation_designation_transition() returns trigger
    language plpgsql
as $$
begin
    if tg_op = 'DELETE' then
        raise exception using errcode = 'check_violation',
            message = 'delegation designations are kept as history',
            constraint = 'delegation_designations_history';
    end if;
    if new.tenant_id is distinct from old.tenant_id
       or new.id is distinct from old.id
       or new.grantor_business_id is distinct from old.grantor_business_id
       or new.grant_id is distinct from old.grant_id
       or new.membership_id is distinct from old.membership_id
       or new.user_id is distinct from old.user_id
       or new.created_by is distinct from old.created_by
       or new.created_at is distinct from old.created_at then
        raise exception using errcode = 'check_violation',
            message = 'delegation designation identity is immutable',
            constraint = 'delegation_designations_identity_immutable';
    end if;
    if old.status = 'removed' then
        raise exception using errcode = 'check_violation',
            message = 'a removed delegation designation can no longer change',
            constraint = 'delegation_designations_removed_terminal';
    end if;
    return new;
end;
$$;
revoke all on function gba.enforce_delegation_designation_transition() from public;
create trigger delegation_designations_enforce_transition
    before update or delete on gba.delegation_designations
    for each row execute function gba.enforce_delegation_designation_transition();
create trigger delegation_designations_audit after insert or update on gba.delegation_designations
    for each row execute function gba.audit_row_change('delegation_designation');

-- Row visibility. Owners manage their grants; the addressed serving business reads them; the
-- owner reads designations for its own grants; a designated user reads only its own records.
create policy delegation_grants_tenant_isolation on gba.delegation_grants
    using (tenant_id = gba.current_tenant_id())
    with check (tenant_id = gba.current_tenant_id());
create policy delegation_grants_grantee_read on gba.delegation_grants
    for select using (grantee_business_id = gba.current_tenant_id());
create policy delegation_grants_delegate_read on gba.delegation_grants
    for select using (exists (
        select 1 from gba.delegation_designations d
        where d.grantor_business_id = delegation_grants.tenant_id
          and d.grant_id = delegation_grants.id
          and d.user_id = gba.current_user_id()
          and d.status = 'active'));

create policy delegation_grant_versions_tenant_isolation on gba.delegation_grant_versions
    using (tenant_id = gba.current_tenant_id())
    with check (tenant_id = gba.current_tenant_id());
create policy delegation_grant_versions_grantee_read on gba.delegation_grant_versions
    for select using (grantee_business_id = gba.current_tenant_id());
create policy delegation_grant_versions_delegate_read on gba.delegation_grant_versions
    for select using (exists (
        select 1 from gba.delegation_designations d
        where d.grantor_business_id = delegation_grant_versions.tenant_id
          and d.grant_id = delegation_grant_versions.grant_id
          and d.user_id = gba.current_user_id()
          and d.status = 'active'));

create policy delegation_designations_tenant_isolation on gba.delegation_designations
    using (tenant_id = gba.current_tenant_id())
    with check (tenant_id = gba.current_tenant_id());
create policy delegation_designations_grantor_read on gba.delegation_designations
    for select using (grantor_business_id = gba.current_tenant_id());
create policy delegation_designations_self_read on gba.delegation_designations
    for select using (user_id = gba.current_user_id());

-- Branch-scoped and delegated transactions never read or write delegation records.
do $$
declare table_name text;
begin
    foreach table_name in array array[
        'delegation_grants', 'delegation_grant_versions', 'delegation_designations'
    ] loop
        execute format(
            'create policy %I on gba.%I as restrictive to gba_runtime '
            'using (gba.current_location_id() is null) '
            'with check (gba.current_location_id() is null)',
            table_name || '_unrestricted_scope', table_name);
    end loop;
end;
$$;

-- A delegated transaction works with operational data only. Company administration,
-- identity, audit history and delegation records stay with the owner's own members.
do $$
declare table_name text;
begin
    foreach table_name in array array[
        'memberships', 'invitations', 'legal_entities', 'legal_entity_versions',
        'business_profile_versions', 'business_profile_industries', 'business_profile_formats',
        'salon_fact_confirmations', 'tenant_embed_origins',
        'delegation_grants', 'delegation_grant_versions', 'delegation_designations'
    ] loop
        execute format(
            'create policy %I on gba.%I as restrictive to gba_runtime '
            'using (gba.current_delegation_grant_id() is null) '
            'with check (gba.current_delegation_grant_id() is null)',
            table_name || '_delegation_scope', table_name);
    end loop;
end;
$$;
create policy users_delegation_scope on gba.users as restrictive to gba_runtime
    using (gba.current_delegation_grant_id() is null or id = gba.current_user_id())
    with check (gba.current_delegation_grant_id() is null);
create policy audit_events_delegation_read on gba.audit_events
    as restrictive for select to gba_runtime
    using (gba.current_delegation_grant_id() is null);
