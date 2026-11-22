-- 0143_enterprise_sso_and_lifecycle.sql
-- ADR-0041 / ENTERPRISE-01 Slice 1: corporate SSO identity providers, SCIM-style directory
-- employee links, and append-only lifecycle deprovisioning events. Invoker rights only.

create table gba.enterprise_sso_providers (
    id uuid not null,
    tenant_id uuid not null,
    location_id uuid null,
    code text not null,
    display_name text not null,
    protocol text not null,
    issuer_url text not null,
    email_domain text not null,
    status text not null default 'active',
    revision integer not null default 1,
    recorded_by uuid not null references gba.users(id),
    recorded_at timestamptz not null default now(),
    primary key (tenant_id, id),
    constraint enterprise_sso_providers_location_fk
        foreign key (tenant_id, location_id)
        references gba.locations(tenant_id, id) on delete restrict,
    constraint enterprise_sso_providers_code_unique
        unique (tenant_id, code),
    constraint enterprise_sso_providers_domain_unique
        unique (tenant_id, email_domain),
    constraint enterprise_sso_providers_checks
        check (
            btrim(code) = code and char_length(code) between 2 and 64
            and code ~ '^[A-Z0-9][A-Z0-9_-]*$'
            and btrim(display_name) = display_name and char_length(display_name) between 1 and 200
            and protocol in ('oidc', 'saml')
            and issuer_url ~ '^https?://[^ ]+$'
            and btrim(email_domain) = email_domain
            and email_domain ~ '^[a-z0-9][a-z0-9.-]*\.[a-z]{2,}$'
            and status in ('active', 'disabled')
            and revision >= 1
        )
);

create table gba.enterprise_directory_links (
    id uuid not null,
    tenant_id uuid not null,
    location_id uuid null,
    provider_id uuid not null,
    user_id uuid not null references gba.users(id),
    external_subject text not null,
    employee_code text not null,
    status text not null default 'active',
    deprovisioned_at timestamptz null,
    deprovision_reason text null,
    revision integer not null default 1,
    recorded_by uuid not null references gba.users(id),
    recorded_at timestamptz not null default now(),
    primary key (tenant_id, id),
    constraint enterprise_directory_links_provider_fk
        foreign key (tenant_id, provider_id)
        references gba.enterprise_sso_providers(tenant_id, id) on delete restrict,
    constraint enterprise_directory_links_location_fk
        foreign key (tenant_id, location_id)
        references gba.locations(tenant_id, id) on delete restrict,
    constraint enterprise_directory_links_ext_unique
        unique (tenant_id, provider_id, external_subject),
    constraint enterprise_directory_links_user_unique
        unique (tenant_id, provider_id, user_id),
    constraint enterprise_directory_links_checks
        check (
            btrim(external_subject) = external_subject
            and char_length(external_subject) between 1 and 200
            and btrim(employee_code) = employee_code
            and char_length(employee_code) between 1 and 64
            and status in ('active', 'deprovisioned')
            and ((status = 'deprovisioned') = (deprovisioned_at is not null))
            and revision >= 1
        )
);

create index enterprise_directory_links_user_idx
    on gba.enterprise_directory_links (tenant_id, user_id, status);

create table gba.enterprise_lifecycle_events (
    id uuid not null,
    tenant_id uuid not null,
    location_id uuid null,
    directory_link_id uuid not null,
    user_id uuid not null references gba.users(id),
    event_kind text not null,
    reason text null,
    memberships_suspended integer not null default 0,
    delegations_removed integer not null default 0,
    recorded_by uuid not null references gba.users(id),
    recorded_at timestamptz not null default now(),
    primary key (tenant_id, id),
    constraint enterprise_lifecycle_events_link_fk
        foreign key (tenant_id, directory_link_id)
        references gba.enterprise_directory_links(tenant_id, id) on delete restrict,
    constraint enterprise_lifecycle_events_location_fk
        foreign key (tenant_id, location_id)
        references gba.locations(tenant_id, id) on delete restrict,
    constraint enterprise_lifecycle_events_checks
        check (
            event_kind in ('provisioned', 'deprovisioned')
            and memberships_suspended >= 0
            and delegations_removed >= 0
        )
);

create index enterprise_lifecycle_events_link_idx
    on gba.enterprise_lifecycle_events (tenant_id, directory_link_id, recorded_at);

-- RLS, grants and module write gates
alter table gba.enterprise_sso_providers enable row level security;
alter table gba.enterprise_sso_providers force row level security;
create policy enterprise_sso_providers_tenant_isolation on gba.enterprise_sso_providers
    using (tenant_id = gba.current_tenant_id())
    with check (tenant_id = gba.current_tenant_id());
grant select, insert, update, delete on gba.enterprise_sso_providers to gba_runtime;
create trigger enterprise_sso_providers_require_module
    before insert on gba.enterprise_sso_providers
    for each row execute function gba.require_enabled_module('analytics');

alter table gba.enterprise_directory_links enable row level security;
alter table gba.enterprise_directory_links force row level security;
create policy enterprise_directory_links_tenant_isolation on gba.enterprise_directory_links
    using (tenant_id = gba.current_tenant_id())
    with check (tenant_id = gba.current_tenant_id());
grant select, insert, update, delete on gba.enterprise_directory_links to gba_runtime;
create trigger enterprise_directory_links_require_module
    before insert on gba.enterprise_directory_links
    for each row execute function gba.require_enabled_module('analytics');

alter table gba.enterprise_lifecycle_events enable row level security;
alter table gba.enterprise_lifecycle_events force row level security;
create policy enterprise_lifecycle_events_tenant_isolation on gba.enterprise_lifecycle_events
    using (tenant_id = gba.current_tenant_id())
    with check (tenant_id = gba.current_tenant_id());
grant select, insert on gba.enterprise_lifecycle_events to gba_runtime;
create trigger enterprise_lifecycle_events_require_module
    before insert on gba.enterprise_lifecycle_events
    for each row execute function gba.require_enabled_module('analytics');

-- Enterprise SSO branch scope:
create policy enterprise_sso_providers_location_scope on gba.enterprise_sso_providers
    as restrictive to gba_runtime
    using (gba.current_location_id() is null or location_id = gba.current_location_id())
    with check (gba.current_location_id() is null or location_id = gba.current_location_id());

create policy enterprise_directory_links_location_scope on gba.enterprise_directory_links
    as restrictive to gba_runtime
    using (gba.current_location_id() is null or location_id = gba.current_location_id())
    with check (gba.current_location_id() is null or location_id = gba.current_location_id());

create policy enterprise_lifecycle_events_location_scope on gba.enterprise_lifecycle_events
    as restrictive to gba_runtime
    using (gba.current_location_id() is null or location_id = gba.current_location_id())
    with check (gba.current_location_id() is null or location_id = gba.current_location_id());
