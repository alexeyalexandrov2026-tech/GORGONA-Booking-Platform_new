-- PROPERTY-01 internal catalog. Revisions and counterparty snapshots are append-only.
create table gba.property_objects (
    tenant_id uuid not null,
    id uuid not null,
    location_id uuid not null,
    kind text not null check (kind in ('parcel', 'building', 'unit')),
    first_revision integer generated always as (1) stored,
    primary key (tenant_id, id),
    unique (tenant_id, id, location_id, kind),
    constraint property_objects_location_fk
        foreign key (tenant_id, location_id) references gba.locations (tenant_id, id)
);
create index property_objects_location_id_index on gba.property_objects (tenant_id, location_id, id);

create table gba.property_revisions (
    tenant_id uuid not null,
    object_id uuid not null,
    revision integer not null check (revision > 0),
    location_id uuid not null,
    kind text not null,
    name text not null check (length(btrim(name)) between 1 and 200 and name !~ '[[:cntrl:]]'),
    parent_id uuid,
    parent_kind text generated always as (
        case kind when 'building' then 'parcel' when 'unit' then 'building' end
    ) stored,
    recorded_at timestamptz not null default clock_timestamp(),
    primary key (tenant_id, object_id, revision),
    foreign key (tenant_id, object_id, location_id, kind)
        references gba.property_objects (tenant_id, id, location_id, kind),
    constraint property_revisions_parent_fk
        foreign key (tenant_id, parent_id, location_id, parent_kind)
        references gba.property_objects (tenant_id, id, location_id, kind),
    check ((kind <> 'parcel' or parent_id is null) and (kind <> 'unit' or parent_id is not null))
);

create table gba.property_parties (
    tenant_id uuid not null,
    object_id uuid not null,
    revision integer not null,
    owner_id uuid,
    manager_id uuid,
    recorded_by uuid not null references gba.users(id),
    primary key (tenant_id, object_id, revision),
    foreign key (tenant_id, object_id, revision)
        references gba.property_revisions (tenant_id, object_id, revision),
    constraint property_parties_owner_fk
        foreign key (tenant_id, owner_id) references gba.counterparties (tenant_id, id),
    constraint property_parties_manager_fk
        foreign key (tenant_id, manager_id) references gba.counterparties (tenant_id, id)
);

alter table gba.property_objects add constraint property_objects_have_initial_revision
    foreign key (tenant_id, id, first_revision)
    references gba.property_revisions (tenant_id, object_id, revision) deferrable initially deferred;
alter table gba.property_revisions add constraint property_revisions_have_party_snapshot
    foreign key (tenant_id, object_id, revision)
    references gba.property_parties (tenant_id, object_id, revision) deferrable initially deferred;

-- The API and direct inserts acquire the same per-object lock before reading the current revision.
create function gba.lock_property_object(business_id uuid, property_id uuid) returns void
    language sql as $$
    select pg_catalog.pg_advisory_xact_lock(
        pg_catalog.hashtextextended('gba:property:' || business_id || ':' || property_id, 0)
    )
$$;
revoke all on function gba.lock_property_object(uuid, uuid) from public;
grant execute on function gba.lock_property_object(uuid, uuid) to gba_runtime;

create function gba.lock_new_property_object() returns trigger language plpgsql as $$
begin
    perform gba.lock_property_object(new.tenant_id, new.id);
    return new;
end;
$$;
revoke all on function gba.lock_new_property_object() from public;
create trigger property_objects_lock before insert on gba.property_objects
    for each row execute function gba.lock_new_property_object();

create function gba.guard_property_revision() returns trigger language plpgsql as $$
begin
    perform gba.lock_property_object(new.tenant_id, new.object_id);
    if new.revision <> coalesce((
        select max(v.revision) from gba.property_revisions v
        where v.tenant_id = new.tenant_id and v.object_id = new.object_id
    ), 0) + 1 then
        raise exception using errcode = 'check_violation',
            constraint = 'property_revisions_sequence_check',
            message = 'a property revision follows the current revision';
    end if;
    return new;
end;
$$;
revoke all on function gba.guard_property_revision() from public;
create trigger property_revisions_lock_sequence before insert on gba.property_revisions
    for each row execute function gba.guard_property_revision();

create trigger property_objects_require_module before insert on gba.property_objects
    for each row execute function gba.require_enabled_module('property');
create trigger property_revisions_require_module before insert on gba.property_revisions
    for each row execute function gba.require_enabled_module('property');
create trigger property_parties_require_module before insert on gba.property_parties
    for each row execute function gba.require_enabled_module('property');

alter table gba.property_objects enable row level security;
alter table gba.property_objects force row level security;
alter table gba.property_revisions enable row level security;
alter table gba.property_revisions force row level security;
alter table gba.property_parties enable row level security;
alter table gba.property_parties force row level security;

create policy property_objects_tenant_isolation on gba.property_objects
    using (tenant_id = gba.current_tenant_id()) with check (tenant_id = gba.current_tenant_id());
create policy property_revisions_tenant_isolation on gba.property_revisions
    using (tenant_id = gba.current_tenant_id()) with check (tenant_id = gba.current_tenant_id());
create policy property_parties_tenant_isolation on gba.property_parties
    using (tenant_id = gba.current_tenant_id()) with check (tenant_id = gba.current_tenant_id());

create policy property_objects_location_scope on gba.property_objects as restrictive to gba_runtime
    using (gba.current_location_id() is null or location_id = gba.current_location_id())
    with check (gba.current_location_id() is null or location_id = gba.current_location_id());
create policy property_revisions_location_scope on gba.property_revisions as restrictive to gba_runtime
    using (gba.current_location_id() is null or location_id = gba.current_location_id())
    with check (gba.current_location_id() is null or location_id = gba.current_location_id());
create policy property_objects_unrestricted_insert on gba.property_objects
    as restrictive for insert to gba_runtime with check (gba.current_location_id() is null);
create policy property_revisions_unrestricted_insert on gba.property_revisions
    as restrictive for insert to gba_runtime with check (gba.current_location_id() is null);
create policy property_parties_unrestricted_scope on gba.property_parties as restrictive to gba_runtime
    using (gba.current_location_id() is null) with check (gba.current_location_id() is null);

grant select, insert on gba.property_objects, gba.property_revisions, gba.property_parties
    to gba_runtime;
