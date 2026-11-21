-- PROPERTY-01 5b: single-assignment contractor access through delegation grants.
-- docs/plan/PACKAGE_PROPERTY01_CONTRACTOR_ACCESS_DESIGN_2026-11-20.md.
-- Invoker rights only. Every write serializes via gba.lock_property_object.
alter table gba.delegation_grants drop constraint delegation_grants_permissions_check;
alter table gba.delegation_grants add constraint delegation_grants_permissions_check check (
    cardinality(permissions) between 1 and 9
    and permissions <@ array['booking.read','booking.write','catalog.read','staff.read',
                             'transport.read','transport.plan','transport.assign','transport.events',
                             'transport.tender','construction.customer_answer',
                             'rental.customer_answer','property.contractor_work']
);

create table gba.property_maintenance_contractor_links (
    tenant_id uuid not null references gba.tenants (id),
    request_id uuid not null,
    revision integer not null check (revision > 0),
    contractor_id uuid not null,
    company_id uuid,
    created_by uuid not null references gba.users (id),
    created_at timestamptz not null default now(),
    primary key (tenant_id, request_id, revision),
    foreign key (tenant_id, request_id)
        references gba.property_maintenance_requests (tenant_id, id),
    foreign key (tenant_id, contractor_id)
        references gba.counterparties (tenant_id, id),
    constraint property_maintenance_contractor_link_recipient
        foreign key (company_id) references gba.tenants (id),
    constraint property_maintenance_contractor_link_separate
        check (company_id is null or company_id <> tenant_id)
);

create table gba.property_maintenance_contractor_updates (
    tenant_id uuid not null references gba.tenants (id),
    request_id uuid not null,
    number integer not null check (number > 0),
    kind text not null check (kind in ('acknowledged', 'in_progress', 'parts_needed', 'work_done')),
    note text not null check (
        length(btrim(note)) between 1 and 2000
        and note !~ E'[\\x01-\\x08\\x0b-\\x1f\\x7f]'
    ),
    company_id uuid not null,
    grant_id uuid not null,
    binding_revision integer not null,
    recorded_by uuid not null references gba.users (id),
    created_at timestamptz not null default now(),
    primary key (tenant_id, request_id, number),
    foreign key (tenant_id, request_id)
        references gba.property_maintenance_requests (tenant_id, id),
    foreign key (tenant_id, request_id, binding_revision)
        references gba.property_maintenance_contractor_links (tenant_id, request_id, revision),
    foreign key (tenant_id, grant_id, company_id)
        references gba.delegation_grants (owner_tenant_id, id, servicer_tenant_id)
);

create function gba.guard_property_maintenance_contractor_link() returns trigger language plpgsql as $$
declare
    req gba.property_maintenance_requests%rowtype;
begin
    if pg_catalog.current_setting('transaction_isolation') <> 'read committed' then
        raise exception using errcode = 'serialization_failure',
            message = 'contractor bindings require a read committed transaction';
    end if;
    select r.* into req from gba.property_maintenance_requests r
    where r.tenant_id = new.tenant_id and r.id = new.request_id;
    if not found then
        raise exception using errcode = 'check_violation',
            constraint = 'property_maintenance_contractor_link_request',
            message = 'a contractor binding requires an assigned maintenance request';
    end if;
    perform gba.lock_property_object(new.tenant_id, req.object_id);
    select r.* into req from gba.property_maintenance_requests r
    where r.tenant_id = new.tenant_id and r.id = new.request_id;
    if req.state <> 'assigned' or req.contractor_id is distinct from new.contractor_id then
        raise exception using errcode = 'check_violation',
            constraint = 'property_maintenance_contractor_link_request',
            message = 'a contractor binding must name the assigned contractor on an assigned request';
    end if;
    if new.created_by is distinct from gba.current_user_id() then
        raise exception using errcode = 'check_violation',
            constraint = 'property_maintenance_contractor_link_author',
            message = 'a contractor binding must name the authenticated editor';
    end if;
    if new.revision <> coalesce((
        select max(l.revision) from gba.property_maintenance_contractor_links l
        where l.tenant_id = new.tenant_id and l.request_id = new.request_id
    ), 0) + 1 then
        raise exception using errcode = 'check_violation',
            constraint = 'property_maintenance_contractor_link_revision',
            message = 'the contractor binding revision changed';
    end if;
    return new;
end;
$$;
revoke all on function gba.guard_property_maintenance_contractor_link() from public;

-- Alphabetical order: immutable -> lock_guard -> require_module.
create trigger property_maintenance_contractor_links_immutable
    before update or delete on gba.property_maintenance_contractor_links
    for each row execute function gba.reject_agreement_mutation();
create trigger property_maintenance_contractor_links_lock_guard
    before insert on gba.property_maintenance_contractor_links
    for each row execute function gba.guard_property_maintenance_contractor_link();
create trigger property_maintenance_contractor_links_require_module
    before insert on gba.property_maintenance_contractor_links
    for each row execute function gba.require_enabled_module('property');

-- Recheck live grant, delegate, branch, and latest single-request binding in every session (0126 pattern).
create function gba.guard_property_maintenance_contractor_update() returns trigger language plpgsql as $$
declare
    visible_location uuid;
    req gba.property_maintenance_requests%rowtype;
begin
    if pg_catalog.current_setting('transaction_isolation') <> 'read committed' then
        raise exception using errcode = 'serialization_failure',
            message = 'contractor updates require a read committed transaction';
    end if;
    if new.tenant_id is distinct from gba.current_tenant_id()
        or new.recorded_by is distinct from gba.current_user_id()
        or new.created_at is distinct from pg_catalog.transaction_timestamp() then
        raise exception using errcode = 'check_violation',
            constraint = 'property_maintenance_contractor_updates_scope',
            message = 'Contractor grant does not authorize this maintenance request';
    end if;

    select g.location_id into visible_location
    from gba.delegation_grants g
    join gba.delegation_grant_members m
      on (m.owner_tenant_id, m.grant_id, m.servicer_tenant_id)
       = (g.owner_tenant_id, g.id, g.servicer_tenant_id)
    where (g.owner_tenant_id, g.id, g.servicer_tenant_id)
        = (new.tenant_id, new.grant_id, new.company_id)
      and m.user_id = new.recorded_by and m.removed_at is null
      and g.status = 'active' and g.expires_at > pg_catalog.clock_timestamp()
      and 'property.contractor_work' = any(g.permissions)
      and (gba.current_location_id() is null
           or g.location_id is not distinct from gba.current_location_id());
    if not found then
        raise exception using errcode = 'check_violation',
            constraint = 'property_maintenance_contractor_updates_scope',
            message = 'Contractor grant does not authorize this maintenance request';
    end if;

    select r.* into req from gba.property_maintenance_requests r
    where r.tenant_id = new.tenant_id and r.id = new.request_id;
    if not found then
        raise exception using errcode = 'check_violation',
            constraint = 'property_maintenance_contractor_updates_scope',
            message = 'Contractor grant does not authorize this maintenance request';
    end if;
    perform gba.lock_property_object(new.tenant_id, req.object_id);
    select r.* into req from gba.property_maintenance_requests r
    where r.tenant_id = new.tenant_id and r.id = new.request_id;

    if req.state <> 'assigned' then
        raise exception using errcode = 'check_violation',
            constraint = 'property_maintenance_contractor_updates_state',
            message = 'only an assigned maintenance request accepts contractor updates';
    end if;
    if new.number <> 1 + coalesce((
        select max(u.number) from gba.property_maintenance_contractor_updates u
        where u.tenant_id = new.tenant_id and u.request_id = new.request_id
    ), 0) then
        raise exception using errcode = 'check_violation',
            constraint = 'property_maintenance_contractor_updates_sequence',
            message = 'contractor updates are numbered 1, 2, 3 per request';
    end if;

    if not exists (
        select 1
        from gba.property_maintenance_requests r
        join lateral (
            select l.contractor_id, l.revision, l.company_id
            from gba.property_maintenance_contractor_links l
            where l.tenant_id = r.tenant_id and l.request_id = r.id
            order by l.revision desc limit 1
        ) binding on binding.contractor_id = r.contractor_id
        where r.tenant_id = new.tenant_id and r.id = new.request_id
          and (visible_location is null or visible_location = r.location_id)
          and (binding.company_id, binding.revision) = (new.company_id, new.binding_revision)
    ) then
        raise exception using errcode = 'check_violation',
            constraint = 'property_maintenance_contractor_updates_scope',
            message = 'Contractor grant does not authorize this maintenance request';
    end if;
    return new;
end;
$$;
revoke all on function gba.guard_property_maintenance_contractor_update() from public;

-- Alphabetical order: immutable -> lock_guard -> require_module.
create trigger property_maintenance_contractor_updates_immutable
    before update or delete on gba.property_maintenance_contractor_updates
    for each row execute function gba.reject_agreement_mutation();
create trigger property_maintenance_contractor_updates_lock_guard
    before insert on gba.property_maintenance_contractor_updates
    for each row execute function gba.guard_property_maintenance_contractor_update();
create trigger property_maintenance_contractor_updates_require_module
    before insert on gba.property_maintenance_contractor_updates
    for each row execute function gba.require_enabled_module('property');

alter table gba.property_maintenance_contractor_links enable row level security;
alter table gba.property_maintenance_contractor_links force row level security;
alter table gba.property_maintenance_contractor_updates enable row level security;
alter table gba.property_maintenance_contractor_updates force row level security;

create policy property_maintenance_contractor_links_tenant_isolation
    on gba.property_maintenance_contractor_links
    using (tenant_id = gba.current_tenant_id()) with check (tenant_id = gba.current_tenant_id());
create policy property_maintenance_contractor_updates_tenant_isolation
    on gba.property_maintenance_contractor_updates
    using (tenant_id = gba.current_tenant_id()) with check (tenant_id = gba.current_tenant_id());

grant select on gba.property_maintenance_contractor_links,
                gba.property_maintenance_contractor_updates
    to gba_runtime;
grant insert (tenant_id, request_id, revision, contractor_id, company_id, created_by)
    on gba.property_maintenance_contractor_links to gba_runtime;
grant insert (tenant_id, request_id, number, kind, note, company_id, grant_id,
              binding_revision, recorded_by)
    on gba.property_maintenance_contractor_updates to gba_runtime;

-- Property maintenance contractor branch scope:
create policy property_maintenance_contractor_links_location_scope
    on gba.property_maintenance_contractor_links
    as restrictive to gba_runtime
    using (gba.current_location_id() is null or exists (
        select 1 from gba.property_maintenance_requests r
        where r.tenant_id = property_maintenance_contractor_links.tenant_id
          and r.id = property_maintenance_contractor_links.request_id))
    with check (gba.current_location_id() is null or exists (
        select 1 from gba.property_maintenance_requests r
        where r.tenant_id = property_maintenance_contractor_links.tenant_id
          and r.id = property_maintenance_contractor_links.request_id));
create policy property_maintenance_contractor_links_unrestricted_insert
    on gba.property_maintenance_contractor_links
    as restrictive for insert to gba_runtime
    with check (gba.current_location_id() is null);
create policy property_maintenance_contractor_updates_location_scope
    on gba.property_maintenance_contractor_updates
    as restrictive to gba_runtime
    using (gba.current_location_id() is null or exists (
        select 1 from gba.property_maintenance_requests r
        where r.tenant_id = property_maintenance_contractor_updates.tenant_id
          and r.id = property_maintenance_contractor_updates.request_id))
    with check (gba.current_location_id() is null or exists (
        select 1 from gba.property_maintenance_requests r
        where r.tenant_id = property_maintenance_contractor_updates.tenant_id
          and r.id = property_maintenance_contractor_updates.request_id));
