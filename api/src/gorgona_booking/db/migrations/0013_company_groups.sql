-- Company groups preserve independent ownership. Membership never grants business data.
create table gba.company_groups (
    tenant_id uuid not null references gba.tenants(id),
    id uuid not null,
    code text not null check (length(code) between 1 and 64 and code ~ '^[A-Z0-9][A-Z0-9_-]*$'),
    created_by uuid not null references gba.users(id),
    created_at timestamptz not null default now(),
    primary key (tenant_id, id),
    constraint company_groups_code_unique unique (tenant_id, code)
);
create table gba.company_group_versions (
    tenant_id uuid not null,
    group_id uuid not null,
    revision integer not null check (revision > 0),
    name text not null check (length(btrim(name, E' \t\r\n')) between 1 and 200
                             and name !~ '[[:cntrl:]]'),
    created_by uuid not null references gba.users(id),
    created_at timestamptz not null default now(),
    primary key (tenant_id, group_id, revision),
    foreign key (tenant_id, group_id) references gba.company_groups(tenant_id, id)
);
create table gba.company_group_invitations (
    tenant_id uuid not null,
    id uuid not null,
    group_id uuid not null,
    participant_business_id uuid not null references gba.tenants(id),
    state text not null default 'active' check (state in ('active', 'withdrawn')),
    revision integer not null default 1 check ((state = 'active' and revision = 1)
                                         or (state = 'withdrawn' and revision = 2)),
    created_by uuid not null references gba.users(id),
    created_at timestamptz not null default now(),
    primary key (tenant_id, id),
    constraint company_group_invitation_id_unique unique (id),
    constraint company_group_invitation_route unique (tenant_id, id, participant_business_id),
    foreign key (tenant_id, group_id) references gba.company_groups(tenant_id, id),
    check (tenant_id <> participant_business_id)
);
create unique index company_group_invitation_active on gba.company_group_invitations
    (tenant_id, group_id, participant_business_id) where state = 'active';
create index company_group_invitation_recipient on gba.company_group_invitations
    (participant_business_id, id);
create table gba.company_group_consents (
    id uuid not null default uuidv7(),
    tenant_id uuid not null references gba.tenants(id),
    operator_business_id uuid not null,
    invitation_id uuid not null,
    revision integer not null check (revision in (1, 2)),
    state text not null check ((revision = 1 and state = 'accepted')
                          or (revision = 2 and state = 'withdrawn')),
    created_by uuid not null references gba.users(id),
    created_at timestamptz not null default now(),
    primary key (tenant_id, invitation_id, revision),
    foreign key (operator_business_id, invitation_id, tenant_id)
        references gba.company_group_invitations(tenant_id, id, participant_business_id)
);

create function gba.reject_company_group_mutation() returns trigger language plpgsql as $$
begin
    raise exception using errcode = 'check_violation',
        message = 'company group records and revisions are immutable';
end;
$$;
revoke all on function gba.reject_company_group_mutation() from public;
create trigger company_groups_immutable before update or delete on gba.company_groups
    for each row execute function gba.reject_company_group_mutation();
create trigger company_group_versions_immutable before update or delete on gba.company_group_versions
    for each row execute function gba.reject_company_group_mutation();
create trigger company_group_consents_immutable before update or delete on gba.company_group_consents
    for each row execute function gba.reject_company_group_mutation();

create function gba.validate_company_group_version() returns trigger language plpgsql as $$
declare previous_revision integer;
begin
    if current_setting('transaction_isolation') <> 'read committed' then
        raise exception using errcode = 'check_violation', constraint = 'company_group_isolation',
            message = 'group writes require READ COMMITTED';
    end if;
    perform pg_advisory_xact_lock(hashtextextended('gba:company-groups:' || new.tenant_id, 0));
    select max(revision) into previous_revision from gba.company_group_versions
        where tenant_id = new.tenant_id and group_id = new.group_id;
    if new.revision <> coalesce(previous_revision, 0) + 1 then
        raise exception using errcode = 'check_violation', message = 'group revisions are sequential';
    end if;
    return new;
end;
$$;
revoke all on function gba.validate_company_group_version() from public;
create trigger company_group_version_sequence before insert on gba.company_group_versions
    for each row execute function gba.validate_company_group_version();

create function gba.validate_company_group_consent() returns trigger language plpgsql as $$
declare previous_revision integer;
begin
    if current_setting('transaction_isolation') <> 'read committed' then
        raise exception using errcode = 'check_violation', constraint = 'company_group_isolation',
            message = 'consent writes require READ COMMITTED';
    end if;
    perform pg_advisory_xact_lock(hashtextextended('gba:group-invitation:' || new.invitation_id, 0));
    if new.state = 'accepted' and not exists (
        select 1 from gba.company_group_invitations
        where tenant_id = new.operator_business_id and id = new.invitation_id
          and participant_business_id = new.tenant_id and state = 'active'
    ) then
        raise exception using errcode = 'check_violation', message = 'accept only an active invitation';
    end if;
    select max(revision) into previous_revision from gba.company_group_consents
        where tenant_id = new.tenant_id and invitation_id = new.invitation_id;
    if new.revision <> coalesce(previous_revision, 0) + 1 then
        raise exception using errcode = 'check_violation', message = 'consent revisions are sequential';
    end if;
    return new;
end;
$$;
revoke all on function gba.validate_company_group_consent() from public;
create trigger company_group_consent_sequence before insert on gba.company_group_consents
    for each row execute function gba.validate_company_group_consent();

create function gba.validate_company_group_invitation() returns trigger language plpgsql as $$
begin
    if tg_op = 'DELETE' then
        raise exception using errcode = 'check_violation', message = 'invitations remain as history';
    end if;
    perform pg_advisory_xact_lock(hashtextextended('gba:group-invitation:' || old.id, 0));
    if old.state <> 'active' or new.state <> 'withdrawn'
       or new.tenant_id is distinct from old.tenant_id or new.id is distinct from old.id
       or new.group_id is distinct from old.group_id
       or new.participant_business_id is distinct from old.participant_business_id
       or new.created_by is distinct from old.created_by or new.created_at is distinct from old.created_at then
        raise exception using errcode = 'check_violation', message = 'invitation identity and withdrawal are final';
    end if;
    return new;
end;
$$;
revoke all on function gba.validate_company_group_invitation() from public;
create trigger company_group_invitation_transition before update or delete on gba.company_group_invitations
    for each row execute function gba.validate_company_group_invitation();
create trigger company_group_invitation_audit after insert or update on gba.company_group_invitations
    for each row execute function gba.audit_row_change('company_group_invitation');
create trigger company_group_consent_audit after insert on gba.company_group_consents
    for each row execute function gba.audit_row_change('company_group_consent');

grant select on gba.company_groups, gba.company_group_versions,
    gba.company_group_invitations, gba.company_group_consents to gba_runtime;
grant insert (tenant_id, id, code, created_by) on gba.company_groups to gba_runtime;
grant insert (tenant_id, group_id, revision, name, created_by) on gba.company_group_versions to gba_runtime;
grant insert (tenant_id, id, group_id, participant_business_id, created_by)
    on gba.company_group_invitations to gba_runtime;
grant update (state, revision) on gba.company_group_invitations to gba_runtime;
grant insert (tenant_id, operator_business_id, invitation_id, revision, state, created_by)
    on gba.company_group_consents to gba_runtime;

alter table gba.company_groups enable row level security;
alter table gba.company_groups force row level security;
alter table gba.company_group_versions enable row level security;
alter table gba.company_group_versions force row level security;
alter table gba.company_group_invitations enable row level security;
alter table gba.company_group_invitations force row level security;
alter table gba.company_group_consents enable row level security;
alter table gba.company_group_consents force row level security;
create policy company_groups_tenant_isolation on gba.company_groups
    using (tenant_id = gba.current_tenant_id()) with check (tenant_id = gba.current_tenant_id());
create policy company_group_versions_tenant_isolation on gba.company_group_versions
    using (tenant_id = gba.current_tenant_id()) with check (tenant_id = gba.current_tenant_id());
create policy company_group_invitations_tenant_isolation on gba.company_group_invitations
    using (tenant_id = gba.current_tenant_id()) with check (tenant_id = gba.current_tenant_id());
create policy company_group_consents_tenant_isolation on gba.company_group_consents
    using (tenant_id = gba.current_tenant_id()) with check (tenant_id = gba.current_tenant_id());
create policy company_group_invitations_recipient_read on gba.company_group_invitations
    for select using (participant_business_id = gba.current_tenant_id());
create policy company_group_consents_operator_read on gba.company_group_consents
    for select using (operator_business_id = gba.current_tenant_id());
create policy company_groups_recipient_read on gba.company_groups for select using (exists (
    select 1 from gba.company_group_invitations i where i.tenant_id = company_groups.tenant_id
    and i.group_id = company_groups.id and i.participant_business_id = gba.current_tenant_id()));
create policy company_group_versions_recipient_read on gba.company_group_versions for select using (exists (
    select 1 from gba.company_group_invitations i where i.tenant_id = company_group_versions.tenant_id
    and i.group_id = company_group_versions.group_id and i.participant_business_id = gba.current_tenant_id()));

-- Group branch scopes:
create policy company_groups_unrestricted_scope on gba.company_groups as restrictive to gba_runtime
    using (gba.current_location_id() is null) with check (gba.current_location_id() is null);
create policy company_group_versions_unrestricted_scope on gba.company_group_versions as restrictive to gba_runtime
    using (gba.current_location_id() is null) with check (gba.current_location_id() is null);
create policy company_group_invitations_unrestricted_scope on gba.company_group_invitations as restrictive to gba_runtime
    using (gba.current_location_id() is null) with check (gba.current_location_id() is null);
create policy company_group_consents_unrestricted_scope on gba.company_group_consents as restrictive to gba_runtime
    using (gba.current_location_id() is null) with check (gba.current_location_id() is null);
-- Group delegation scopes:
create policy company_groups_delegation_scope on gba.company_groups as restrictive to gba_runtime
    using (gba.current_delegation_grant_id() is null) with check (gba.current_delegation_grant_id() is null);
create policy company_group_versions_delegation_scope on gba.company_group_versions as restrictive to gba_runtime
    using (gba.current_delegation_grant_id() is null) with check (gba.current_delegation_grant_id() is null);
create policy company_group_invitations_delegation_scope on gba.company_group_invitations as restrictive to gba_runtime
    using (gba.current_delegation_grant_id() is null) with check (gba.current_delegation_grant_id() is null);
create policy company_group_consents_delegation_scope on gba.company_group_consents as restrictive to gba_runtime
    using (gba.current_delegation_grant_id() is null) with check (gba.current_delegation_grant_id() is null);

-- Report permission remains separate from access to individual bookings.
alter table gba.delegation_grant_versions drop constraint delegation_grant_versions_permissions_valid;
alter table gba.delegation_grant_versions add constraint delegation_grant_versions_permissions_valid check (
    array_ndims(permissions) = 1 and cardinality(permissions) between 1 and 5
    and array_position(permissions, null) is null
    and permissions <@ array['booking.read', 'booking.write', 'catalog.read', 'staff.read', 'report.booking.read']::text[]
    and gba.text_array_strictly_sorted(permissions)
    and (not permissions @> array['booking.write']::text[]
         or permissions @> array['booking.read', 'catalog.read', 'staff.read']::text[]));
