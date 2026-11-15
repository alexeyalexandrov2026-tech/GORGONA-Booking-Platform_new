-- PROPERTY-01 3a: the recorded civil days of exclusive possession of one unit.
create table gba.property_leases (
    tenant_id uuid not null,
    id uuid not null,
    object_id uuid not null,
    agreement_id uuid not null,
    agreement_revision integer not null,
    starts_on date not null,
    ends_on date not null,
    recorded_by uuid not null references gba.users (id),
    recorded_at timestamptz not null default clock_timestamp(),
    primary key (tenant_id, id),
    constraint property_leases_one_registration unique (tenant_id, agreement_id),
    foreign key (tenant_id, object_id) references gba.property_objects (tenant_id, id),
    foreign key (tenant_id, agreement_id, agreement_revision)
        references gba.agreement_versions (tenant_id, agreement_id, revision),
    constraint property_leases_no_overlap exclude using gist (
        tenant_id with =, object_id with =, daterange(starts_on, ends_on, '[]') with &&
    )
);

-- Serialize with agreement changes. A draft amendment leaves the signed term current.
-- An immutable non-null file reference uses the existing document FK and file integrity checks.
create function gba.validate_property_lease() returns trigger language plpgsql as $$
begin
    -- Advisory locks do not refresh an older REPEATABLE READ/SERIALIZABLE snapshot.
    if pg_catalog.current_setting('transaction_isolation') <> 'read committed' then
        raise exception using errcode = 'serialization_failure',
            message = 'lease registration requires a read committed transaction';
    end if;
    perform pg_catalog.pg_advisory_xact_lock(
        pg_catalog.hashtextextended('gba:counterparties:' || new.tenant_id::text, 0));
    if not exists (
        select 1 from gba.property_objects o
        where o.tenant_id = new.tenant_id and o.id = new.object_id and o.kind = 'unit'
    ) then
        raise exception using errcode = 'check_violation', constraint = 'property_leases_unit',
            message = 'an exclusive lease requires a property unit';
    end if;

    select v.effective_from, v.effective_until into new.starts_on, new.ends_on
    from gba.agreement_versions v
    join gba.document_versions d
      on d.tenant_id = v.tenant_id and d.document_id = v.document_id
     and d.revision = v.document_revision
    where v.tenant_id = new.tenant_id and v.agreement_id = new.agreement_id
      and v.revision = new.agreement_revision and v.state = 'agreed'
      and v.attestation = 'signed_outside_platform'
      and v.signed_on between date '0001-01-01' and date '9999-12-31'
      and v.effective_from >= date '0001-01-01'
      and v.effective_until <= date '9999-12-31'
      and d.category = 'agreement' and not d.archived and d.file_id is not null
      and not exists (
          select 1 from gba.agreement_versions later
          where later.tenant_id = v.tenant_id and later.agreement_id = v.agreement_id
            and later.revision > v.revision and later.state <> 'draft'
      );
    if not found then
        raise exception using errcode = 'check_violation',
            constraint = 'property_leases_signed_source',
            message = 'an exclusive lease requires the current agreed term and its signed file';
    end if;
    return new;
end;
$$;
revoke all on function gba.validate_property_lease() from public;
create trigger property_leases_validate_input before insert on gba.property_leases
    for each row execute function gba.validate_property_lease();

create trigger property_leases_immutable before update or delete on gba.property_leases
    for each row execute function gba.reject_agreement_mutation();
create trigger property_leases_require_module before insert on gba.property_leases
    for each row execute function gba.require_enabled_module('property');

alter table gba.property_leases enable row level security;
alter table gba.property_leases force row level security;
create policy property_leases_tenant_isolation on gba.property_leases
    using (tenant_id = gba.current_tenant_id()) with check (tenant_id = gba.current_tenant_id());
grant select on gba.property_leases to gba_runtime;
grant insert (tenant_id, id, object_id, agreement_id, agreement_revision, recorded_by)
    on gba.property_leases to gba_runtime;

-- Property lease company scope:
create policy property_leases_unrestricted_scope on gba.property_leases as restrictive to gba_runtime
    using (gba.current_location_id() is null) with check (gba.current_location_id() is null);
