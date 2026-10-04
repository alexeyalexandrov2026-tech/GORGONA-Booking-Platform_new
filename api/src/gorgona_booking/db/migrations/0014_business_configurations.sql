-- Configuration publication (ADR-0019). A company's configuration moves
-- draft -> validated -> published -> superseded; every version, its author, result and
-- predecessor are kept and a published version never changes. Once a business has
-- published, the effective state of each optional module is kept per business, and a
-- disabled booking module refuses new bookings in the database. Businesses that have
-- not published keep today's behaviour; nothing is created on their behalf.
create table gba.business_configuration_versions (
    tenant_id uuid not null references gba.tenants (id),
    id uuid not null default uuidv7(),
    version integer not null check (version > 0),
    state text not null default 'draft'
        check (state in ('draft', 'validated', 'published', 'superseded')),
    revision integer not null default 1 check (revision > 0),
    profile_revision integer not null,
    registry_version integer not null check (registry_version > 0),
    created_by uuid not null references gba.users (id),
    created_at timestamptz not null default now(),
    created_transaction xid8 not null default pg_catalog.pg_current_xact_id(),
    validated_by uuid references gba.users (id),
    validated_at timestamptz,
    validation jsonb check (validation is null or jsonb_typeof(validation) = 'object'),
    published_by uuid references gba.users (id),
    published_at timestamptz,
    superseded_by_version integer,
    superseded_at timestamptz,
    primary key (tenant_id, version),
    unique (tenant_id, id),
    foreign key (tenant_id, profile_revision)
        references gba.business_profile_versions (tenant_id, revision),
    foreign key (tenant_id, superseded_by_version)
        references gba.business_configuration_versions (tenant_id, version),
    constraint business_configuration_versions_validation_complete check (
        (validated_at is null) = (validated_by is null)
        and (validated_at is null) = (validation is null)
        and (state = 'draft') = (validated_at is null)
    ),
    constraint business_configuration_versions_publication_complete check (
        (published_at is null) = (published_by is null)
        and (state in ('published', 'superseded')) = (published_at is not null)
    ),
    constraint business_configuration_versions_supersession_complete check (
        (superseded_at is null) = (superseded_by_version is null)
        and (state = 'superseded') = (superseded_at is not null)
        and (superseded_by_version is null or superseded_by_version > version)
    )
);
create unique index business_configuration_versions_one_published
    on gba.business_configuration_versions (tenant_id) where state = 'published';

create table gba.business_configuration_modules (
    tenant_id uuid not null,
    version integer not null,
    module_id text not null check (module_id ~ '^[a-z][a-z_]{1,62}$'),
    primary key (tenant_id, version, module_id),
    foreign key (tenant_id, version)
        references gba.business_configuration_versions (tenant_id, version)
);

create table gba.business_module_states (
    tenant_id uuid not null references gba.tenants (id),
    module_id text not null check (module_id ~ '^[a-z][a-z_]{1,62}$'),
    enabled boolean not null,
    configuration_version integer not null,
    revision integer not null default 1 check (revision > 0),
    updated_by uuid not null references gba.users (id),
    updated_at timestamptz not null default now(),
    primary key (tenant_id, module_id),
    foreign key (tenant_id, configuration_version)
        references gba.business_configuration_versions (tenant_id, version)
);

alter table gba.business_configuration_versions enable row level security;
alter table gba.business_configuration_versions force row level security;
alter table gba.business_configuration_modules enable row level security;
alter table gba.business_configuration_modules force row level security;
alter table gba.business_module_states enable row level security;
alter table gba.business_module_states force row level security;

create policy business_configuration_versions_tenant_isolation
    on gba.business_configuration_versions
    using (tenant_id = gba.current_tenant_id())
    with check (tenant_id = gba.current_tenant_id());
grant select on gba.business_configuration_versions to gba_runtime;
grant insert (tenant_id, version, profile_revision, registry_version, created_by)
    on gba.business_configuration_versions to gba_runtime;
grant update (state, revision, validated_by, validated_at, validation, published_by,
              published_at, superseded_by_version, superseded_at)
    on gba.business_configuration_versions to gba_runtime;

create policy business_configuration_modules_tenant_isolation
    on gba.business_configuration_modules
    using (tenant_id = gba.current_tenant_id())
    with check (tenant_id = gba.current_tenant_id());
grant select, insert on gba.business_configuration_modules to gba_runtime;

-- Every session of the business reads the effective module state, including branch
-- sessions: booking enforcement and the workspace need it. Only company-wide sessions
-- write it (restrictive policies below).
create policy business_module_states_tenant_isolation on gba.business_module_states
    using (tenant_id = gba.current_tenant_id())
    with check (tenant_id = gba.current_tenant_id());
grant select on gba.business_module_states to gba_runtime;
grant insert (tenant_id, module_id, enabled, configuration_version, updated_by)
    on gba.business_module_states to gba_runtime;
grant update (enabled, configuration_version, revision, updated_by, updated_at)
    on gba.business_module_states to gba_runtime;

create function gba.enforce_business_configuration_version() returns trigger
    language plpgsql as $$
declare
    latest integer;
begin
    if tg_op = 'DELETE' then
        raise exception using errcode = 'check_violation',
            message = 'configuration history is kept';
    end if;
    select max(v.version) into latest from gba.business_configuration_versions v
    where v.tenant_id = new.tenant_id;
    if tg_op = 'INSERT' then
        if new.state <> 'draft' or new.revision <> 1
           or new.version <> coalesce(latest, 0) + 1 then
            raise exception using errcode = 'check_violation',
                message = 'a configuration version starts as the next draft';
        end if;
        return new;
    end if;
    if (new.tenant_id, new.id, new.version, new.profile_revision, new.registry_version,
        new.created_by, new.created_at, new.created_transaction)
       is distinct from
       (old.tenant_id, old.id, old.version, old.profile_revision, old.registry_version,
        old.created_by, old.created_at, old.created_transaction)
       or new.revision <> old.revision + 1 then
        raise exception using errcode = 'check_violation',
            message = 'configuration content is immutable and revisions advance by one';
    end if;
    if not (
        (old.state = 'draft' and new.state = 'validated' and new.version = latest)
        or (old.state = 'validated' and new.state = 'published' and new.version = latest)
        or (old.state = 'published' and new.state = 'superseded' and exists (
            select 1 from gba.business_configuration_versions n
            where n.tenant_id = new.tenant_id and n.version = new.superseded_by_version
              and n.version = latest and n.state = 'validated'))
    ) then
        raise exception using errcode = 'check_violation',
            message = 'invalid configuration transition';
    end if;
    if ((new.validated_by, new.validated_at, new.validation)
            is distinct from (old.validated_by, old.validated_at, old.validation)
        and old.state <> 'draft')
       or ((new.published_by, new.published_at)
            is distinct from (old.published_by, old.published_at)
           and old.state <> 'validated') then
        raise exception using errcode = 'check_violation',
            message = 'a configuration decision is recorded once';
    end if;
    return new;
end;
$$;
revoke all on function gba.enforce_business_configuration_version() from public;
create trigger business_configuration_versions_enforce_change
    before insert or update or delete on gba.business_configuration_versions
    for each row execute function gba.enforce_business_configuration_version();

-- Module selections belong to the transaction that created their version.
create function gba.guard_business_configuration_modules() returns trigger
    language plpgsql as $$
begin
    if tg_op <> 'INSERT' then
        raise exception using errcode = 'check_violation',
            message = 'configuration module selections are immutable';
    end if;
    if not exists (
        select 1 from gba.business_configuration_versions v
        where v.tenant_id = new.tenant_id and v.version = new.version
          and v.created_transaction = pg_catalog.pg_current_xact_id()
    ) then
        raise exception using errcode = 'check_violation',
            message = 'cannot change the modules of a committed configuration version';
    end if;
    return new;
end;
$$;
revoke all on function gba.guard_business_configuration_modules() from public;
create trigger business_configuration_modules_immutable
    before insert or update or delete on gba.business_configuration_modules
    for each row execute function gba.guard_business_configuration_modules();

-- A module state always mirrors a published version; it cannot be toggled on its own.
create function gba.enforce_business_module_state() returns trigger
    language plpgsql as $$
begin
    if tg_op = 'DELETE' then
        raise exception using errcode = 'check_violation',
            message = 'module states are kept';
    end if;
    if tg_op = 'UPDATE' and ((new.tenant_id, new.module_id)
                             is distinct from (old.tenant_id, old.module_id)
                             or new.revision <> old.revision + 1) then
        raise exception using errcode = 'check_violation',
            message = 'module state identity is immutable and revisions advance by one';
    end if;
    if tg_op = 'INSERT' and new.revision <> 1 then
        raise exception using errcode = 'check_violation',
            message = 'a module state starts at revision 1';
    end if;
    if not exists (
        select 1 from gba.business_configuration_versions v
        where v.tenant_id = new.tenant_id and v.version = new.configuration_version
          and v.state = 'published'
    ) or new.enabled <> exists (
        select 1 from gba.business_configuration_modules m
        where m.tenant_id = new.tenant_id and m.version = new.configuration_version
          and m.module_id = new.module_id
    ) then
        raise exception using errcode = 'check_violation',
            message = 'a module state must match the published configuration';
    end if;
    return new;
end;
$$;
revoke all on function gba.enforce_business_module_state() from public;
create trigger business_module_states_enforce_change
    before insert or update or delete on gba.business_module_states
    for each row execute function gba.enforce_business_module_state();

-- New bookings respect the booking module. The shared advisory lock pairs with the
-- exclusive lock a publication takes, so a booking is ordered entirely before or after
-- it. Updates (cancel, confirm an existing hold) are not affected.
create function gba.enforce_booking_module() returns trigger
    language plpgsql as $$
begin
    perform pg_catalog.pg_advisory_xact_lock_shared(
        pg_catalog.hashtextextended('gba:business-configuration:' || new.tenant_id::text, 0));
    if exists (
        select 1 from gba.business_module_states s
        where s.tenant_id = new.tenant_id and s.module_id = 'booking_resources'
          and not s.enabled
    ) then
        raise exception using errcode = 'GBM01',
            message = 'the booking module is disabled for this business';
    end if;
    return new;
end;
$$;
revoke all on function gba.enforce_booking_module() from public;
create trigger bookings_require_booking_module
    before insert on gba.bookings
    for each row execute function gba.enforce_booking_module();

-- Company-wide scope: reusable separately when restoring a damaged boundary in tests.
create policy business_configuration_versions_unrestricted_scope
    on gba.business_configuration_versions as restrictive to gba_runtime
    using (gba.current_location_id() is null) with check (gba.current_location_id() is null);
create policy business_configuration_modules_unrestricted_scope
    on gba.business_configuration_modules as restrictive to gba_runtime
    using (gba.current_location_id() is null) with check (gba.current_location_id() is null);
create policy business_module_states_unrestricted_insert
    on gba.business_module_states as restrictive for insert to gba_runtime
    with check (gba.current_location_id() is null);
create policy business_module_states_unrestricted_update
    on gba.business_module_states as restrictive for update to gba_runtime
    using (gba.current_location_id() is null) with check (gba.current_location_id() is null);
