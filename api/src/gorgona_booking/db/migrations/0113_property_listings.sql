-- PROPERTY-01 step 2a: listings of catalog objects. docs/plan/PACKAGE_PROPERTY01_LISTINGS_DESIGN_2026-11-15.md.
-- One listing per object, in the object's company, branch and type; revisions are append-only.
create table gba.property_listings (
    tenant_id uuid not null,
    object_id uuid not null,
    location_id uuid not null,
    kind text not null,
    first_revision integer generated always as (1) stored,
    primary key (tenant_id, object_id),
    unique (tenant_id, object_id, location_id),
    constraint property_listings_object_fk
        foreign key (tenant_id, object_id, location_id, kind)
        references gba.property_objects (tenant_id, id, location_id, kind)
);
create index property_listings_location_id_index on gba.property_listings (tenant_id, location_id, object_id);

create table gba.property_listing_revisions (
    tenant_id uuid not null,
    object_id uuid not null,
    revision integer not null check (revision > 0),
    location_id uuid not null,
    state text not null check (state in ('draft', 'published', 'withdrawn')),
    headline text not null check (length(btrim(headline)) between 1 and 120 and headline !~ '[[:cntrl:]]'),
    description text check (
        description is null or (length(description) <= 4000 and description !~ E'[\\x01-\\x08\\x0b-\\x1f\\x7f]')
    ),
    monthly_rent bigint not null check (monthly_rent between 1 and 1000000000000),
    currency text not null check (currency ~ '^[A-Z]{3}$'),
    available_from date not null,
    recorded_by uuid not null references gba.users(id),
    recorded_at timestamptz not null default clock_timestamp(),
    primary key (tenant_id, object_id, revision),
    constraint property_listing_revisions_listing_fk
        foreign key (tenant_id, object_id, location_id)
        references gba.property_listings (tenant_id, object_id, location_id)
);

alter table gba.property_listings add constraint property_listings_have_initial_revision
    foreign key (tenant_id, object_id, first_revision)
    references gba.property_listing_revisions (tenant_id, object_id, revision) deferrable initially deferred;

-- Listing writes take the catalog object's lock, so they serialize with its other commands.
create function gba.lock_new_property_listing() returns trigger language plpgsql as $$
begin
    perform gba.lock_property_object(new.tenant_id, new.object_id);
    return new;
end;
$$;
revoke all on function gba.lock_new_property_listing() from public;
create trigger property_listings_lock before insert on gba.property_listings
    for each row execute function gba.lock_new_property_listing();

create function gba.guard_property_listing_revision() returns trigger language plpgsql as $$
begin
    perform gba.lock_property_object(new.tenant_id, new.object_id);
    if new.revision <> coalesce((
        select max(v.revision) from gba.property_listing_revisions v
        where v.tenant_id = new.tenant_id and v.object_id = new.object_id
    ), 0) + 1 then
        raise exception using errcode = 'check_violation',
            constraint = 'property_listing_revisions_sequence_check',
            message = 'a listing revision follows the current revision';
    end if;
    return new;
end;
$$;
revoke all on function gba.guard_property_listing_revision() from public;
create trigger property_listing_revisions_lock_sequence before insert on gba.property_listing_revisions
    for each row execute function gba.guard_property_listing_revision();

create trigger property_listings_require_module before insert on gba.property_listings
    for each row execute function gba.require_enabled_module('property');
create trigger property_listing_revisions_require_module before insert on gba.property_listing_revisions
    for each row execute function gba.require_enabled_module('property');

alter table gba.property_listings enable row level security;
alter table gba.property_listings force row level security;
alter table gba.property_listing_revisions enable row level security;
alter table gba.property_listing_revisions force row level security;

create policy property_listings_tenant_isolation on gba.property_listings
    using (tenant_id = gba.current_tenant_id()) with check (tenant_id = gba.current_tenant_id());
create policy property_listing_revisions_tenant_isolation on gba.property_listing_revisions
    using (tenant_id = gba.current_tenant_id()) with check (tenant_id = gba.current_tenant_id());

-- Property branch scope:
create policy property_listings_location_scope on gba.property_listings as restrictive to gba_runtime
    using (gba.current_location_id() is null or location_id = gba.current_location_id())
    with check (gba.current_location_id() is null or location_id = gba.current_location_id());
create policy property_listing_revisions_location_scope on gba.property_listing_revisions as restrictive to gba_runtime
    using (gba.current_location_id() is null or location_id = gba.current_location_id())
    with check (gba.current_location_id() is null or location_id = gba.current_location_id());
create policy property_listings_unrestricted_insert on gba.property_listings
    as restrictive for insert to gba_runtime with check (gba.current_location_id() is null);
create policy property_listing_revisions_unrestricted_insert on gba.property_listing_revisions
    as restrictive for insert to gba_runtime with check (gba.current_location_id() is null);

grant select, insert on gba.property_listings, gba.property_listing_revisions to gba_runtime;
