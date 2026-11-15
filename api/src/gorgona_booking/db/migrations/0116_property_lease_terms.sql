-- PROPERTY-01 3b: immutable term events with the current interval on the lease.
alter table gba.property_leases
    add column term_revision integer not null default 1,
    add column occupied_through date,
    add constraint property_leases_term_pair check (
        (term_revision = 1 and occupied_through is null)
        or (term_revision > 1 and occupied_through is not null)
    );
alter table gba.property_leases drop constraint property_leases_no_overlap;
alter table gba.property_leases add constraint property_leases_no_overlap exclude using gist (
    tenant_id with =, object_id with =,
    daterange(starts_on, greatest(starts_on, coalesce(occupied_through, ends_on) + 1), '[)') with &&
);

create table gba.property_lease_term_events (
    tenant_id uuid not null,
    lease_id uuid not null,
    revision integer not null check (revision > 1),
    action text not null check (action in ('extend', 'release')),
    agreement_id uuid not null,
    agreement_revision integer not null,
    occupied_through date not null,
    recorded_by uuid not null references gba.users (id),
    recorded_at timestamptz not null default clock_timestamp(),
    creation_xid xid8 not null default pg_current_xact_id(),
    primary key (tenant_id, lease_id, revision),
    foreign key (tenant_id, lease_id) references gba.property_leases (tenant_id, id),
    foreign key (tenant_id, agreement_id, agreement_revision)
        references gba.agreement_versions (tenant_id, agreement_id, revision)
);

create function gba.guard_property_lease_term() returns trigger language plpgsql as $$
begin
    if tg_op = 'INSERT' then
        if new.term_revision <> 1 or new.occupied_through is not null then
            raise exception using errcode = 'check_violation',
                message = 'a lease starts with the registered term';
        end if;
        return new;
    end if;
    if tg_op = 'DELETE' or
       (new.tenant_id, new.id, new.object_id, new.agreement_id, new.agreement_revision,
        new.starts_on, new.ends_on, new.recorded_by, new.recorded_at)
        is distinct from
       (old.tenant_id, old.id, old.object_id, old.agreement_id, old.agreement_revision,
        old.starts_on, old.ends_on, old.recorded_by, old.recorded_at) then
        raise exception using errcode = 'check_violation',
            message = 'original lease registrations are kept unchanged';
    end if;
    if new.term_revision::bigint <> old.term_revision::bigint + 1 or not exists (
        select 1 from gba.property_lease_term_events e
        where e.tenant_id = new.tenant_id and e.lease_id = new.id
          and e.revision = new.term_revision and e.occupied_through = new.occupied_through
          and e.creation_xid = pg_current_xact_id()
    ) then
        raise exception using errcode = 'check_violation',
            message = 'the current term follows its next recorded event';
    end if;
    return new;
end;
$$;
revoke all on function gba.guard_property_lease_term() from public;
drop trigger property_leases_immutable on gba.property_leases;
create trigger property_leases_guard_term before insert or update or delete on gba.property_leases
    for each row execute function gba.guard_property_lease_term();

-- Use the same agreement-first lock ordering for registrations, extensions and agreements.
alter trigger property_leases_validate_input on gba.property_leases
    rename to property_leases_agreement_source;

create function gba.validate_property_lease_term_event() returns trigger language plpgsql as $$
declare
    lease gba.property_leases%rowtype;
    previous gba.property_lease_term_events%rowtype;
    agreement_version gba.agreement_versions%rowtype;
begin
    if pg_catalog.current_setting('transaction_isolation') <> 'read committed' then
        raise exception using errcode = 'serialization_failure',
            message = 'lease term changes require a read committed transaction';
    end if;
    perform pg_catalog.pg_advisory_xact_lock(
        pg_catalog.hashtextextended('gba:counterparties:' || new.tenant_id::text, 0));

    -- Like the optional-module gate, order new commitments against configuration publication.
    if new.action = 'extend' then
        perform pg_catalog.pg_advisory_xact_lock_shared(
            pg_catalog.hashtextextended('gba:business-configuration:' || new.tenant_id::text, 0));
        if not exists (
            select 1 from gba.business_module_states s
            where s.tenant_id = new.tenant_id and s.module_id = 'property' and s.enabled
        ) then
            raise exception using errcode = 'GBM01',
                message = 'the property module is disabled for this business';
        end if;
    end if;

    select l.* into lease from gba.property_leases l
    where l.tenant_id = new.tenant_id and l.id = new.lease_id;
    if not found then
        raise exception using errcode = 'check_violation', constraint = 'property_lease_term_lease',
            message = 'a lease term change requires an existing lease';
    end if;
    if new.revision::bigint <> lease.term_revision::bigint + 1 then
        raise exception using errcode = 'check_violation',
            constraint = 'property_lease_term_sequence',
            message = 'a lease term change follows the current revision';
    end if;
    select e.* into previous from gba.property_lease_term_events e
    where e.tenant_id = lease.tenant_id and e.lease_id = lease.id
      and e.revision = lease.term_revision;
    if previous.action = 'release' then
        raise exception using errcode = 'check_violation',
            constraint = 'property_lease_term_closed',
            message = 'a released lease keeps its last recorded term';
    end if;

    select v.* into agreement_version from gba.agreement_versions v
    where v.tenant_id = lease.tenant_id and v.agreement_id = lease.agreement_id
      and v.revision = new.agreement_revision
      and v.revision > coalesce(previous.agreement_revision, lease.agreement_revision)
      and v.attestation = 'signed_outside_platform'
      and not exists (
          select 1 from gba.agreement_versions later
          where later.tenant_id = v.tenant_id and later.agreement_id = v.agreement_id
            and later.revision > v.revision and later.state <> 'draft'
      );
    if not found then
        raise exception using errcode = 'check_violation',
            constraint = 'property_lease_term_source',
            message = 'a term change uses the current signed agreement version';
    end if;

    if new.action = 'extend' then
        if agreement_version.state <> 'agreed'
           or agreement_version.effective_from is distinct from lease.starts_on
           or agreement_version.effective_until is null
           or agreement_version.effective_until <= coalesce(lease.occupied_through, lease.ends_on)
           or agreement_version.effective_until > date '9999-12-31'
           or not exists (
              select 1 from gba.document_versions d
              where d.tenant_id = lease.tenant_id and d.document_id = agreement_version.document_id
                and d.revision = agreement_version.document_revision
                and d.category = 'agreement' and not d.archived and d.file_id is not null
           ) then
            raise exception using errcode = 'check_violation',
                constraint = 'property_lease_term_source',
                message = 'an extension requires a later signed end date and its stored file';
        end if;
        new.occupied_through := agreement_version.effective_until;
    else
        if agreement_version.state <> 'terminated'
           or agreement_version.terminated_on not between
               date '0001-01-01' and date '9999-12-31' then
            raise exception using errcode = 'check_violation',
                constraint = 'property_lease_term_source',
                message = 'a release requires the recorded agreement termination';
        end if;
        new.occupied_through := least(
            agreement_version.terminated_on, coalesce(lease.occupied_through, lease.ends_on));
    end if;
    new.agreement_id := lease.agreement_id;
    return new;
end;
$$;
revoke all on function gba.validate_property_lease_term_event() from public;
create trigger property_lease_term_events_validate before insert on gba.property_lease_term_events
    for each row execute function gba.validate_property_lease_term_event();

create function gba.apply_property_lease_term_event() returns trigger language plpgsql as $$
begin
    update gba.property_leases
    set term_revision = new.revision, occupied_through = new.occupied_through
    where tenant_id = new.tenant_id and id = new.lease_id;
    if not found then
        raise exception using errcode = 'check_violation',
            message = 'a recorded event must advance its lease';
    end if;
    return null;
end;
$$;
revoke all on function gba.apply_property_lease_term_event() from public;
create trigger property_lease_term_events_apply after insert on gba.property_lease_term_events
    for each row execute function gba.apply_property_lease_term_event();
create trigger property_lease_term_events_immutable before update or delete on gba.property_lease_term_events
    for each row execute function gba.reject_agreement_mutation();

grant update (term_revision, occupied_through) on gba.property_leases to gba_runtime;
alter table gba.property_lease_term_events enable row level security;
alter table gba.property_lease_term_events force row level security;
create policy property_lease_term_events_tenant_isolation on gba.property_lease_term_events
    using (tenant_id = gba.current_tenant_id()) with check (tenant_id = gba.current_tenant_id());
grant select on gba.property_lease_term_events to gba_runtime;
grant insert (tenant_id, lease_id, revision, action, agreement_revision, recorded_by)
    on gba.property_lease_term_events to gba_runtime;

-- Property lease term company scope:
create policy property_lease_term_events_unrestricted_scope on gba.property_lease_term_events
    as restrictive to gba_runtime
    using (gba.current_location_id() is null) with check (gba.current_location_id() is null);
