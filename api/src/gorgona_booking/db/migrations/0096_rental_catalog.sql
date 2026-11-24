-- R1 (package R, RENT-01): rental item classes and units. ADR-0036.
-- A class is company-wide with a typed attribute set per revision; a unit is one physical item of a class
-- with an identifier unique in the business, a branch, a state and values checked against its class.
-- Attribute sets and values are insert-only and written with their revision.
create table gba.rental_classes (
    tenant_id uuid not null references gba.tenants(id),
    id uuid not null,
    code text not null constraint rental_classes_code_check
        check (code ~ '^[A-Z0-9][A-Z0-9_-]{0,31}$'),
    name text not null constraint rental_classes_name_check
        check (length(btrim(name)) between 1 and 200 and name !~ '[[:cntrl:]]'),
    meter_kind text not null constraint rental_classes_meter_kind_check
        check (meter_kind in ('none', 'odometer', 'hours')),
    revision integer not null constraint rental_classes_revision_check check (revision > 0),
    created_by uuid not null references gba.users(id),
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    primary key (tenant_id, id),
    unique (tenant_id, code)
);
create table gba.rental_class_attributes (
    tenant_id uuid not null references gba.tenants(id),
    class_id uuid not null,
    revision integer not null,
    position smallint not null constraint rental_class_attributes_position_check
        check (position between 1 and 50),
    key text not null constraint rental_class_attributes_key_check
        check (key ~ '^[a-z][a-z0-9_]{0,31}$'),
    label text not null constraint rental_class_attributes_label_check
        check (length(btrim(label)) between 1 and 100 and label !~ '[[:cntrl:]]'),
    type text not null constraint rental_class_attributes_type_check
        check (type in ('text', 'number', 'boolean')),
    required boolean not null,
    primary key (tenant_id, class_id, revision, key),
    unique (tenant_id, class_id, revision, position),
    foreign key (tenant_id, class_id) references gba.rental_classes (tenant_id, id)
);
create table gba.rental_units (
    tenant_id uuid not null references gba.tenants(id),
    id uuid not null,
    class_id uuid not null,
    identifier text not null constraint rental_units_identifier_check
        check (length(btrim(identifier)) between 1 and 64 and identifier !~ '[[:cntrl:]]'),
    location_id uuid not null,
    state text not null constraint rental_units_state_check
        check (state in ('active', 'retired')),
    revision integer not null constraint rental_units_revision_check check (revision > 0),
    created_by uuid not null references gba.users(id),
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    primary key (tenant_id, id),
    unique (tenant_id, identifier),
    foreign key (tenant_id, class_id) references gba.rental_classes (tenant_id, id),
    foreign key (tenant_id, location_id) references gba.locations (tenant_id, id)
);
create table gba.rental_unit_values (
    tenant_id uuid not null references gba.tenants(id),
    unit_id uuid not null,
    revision integer not null,
    key text not null,
    value text not null constraint rental_unit_values_value_check
        check (length(value) between 1 and 500 and value !~ '[[:cntrl:]]'),
    primary key (tenant_id, unit_id, revision, key),
    foreign key (tenant_id, unit_id) references gba.rental_units (tenant_id, id)
);

-- A class keeps its code; its revisions follow each other.
create function gba.guard_rental_class() returns trigger language plpgsql as $$
begin
    if tg_op = 'INSERT' then
        if new.revision <> 1 then
            raise exception using errcode = 'check_violation',
                constraint = 'rental_classes_revision_sequence_check',
                message = 'a class starts at revision 1';
        end if;
        return new;
    end if;
    if new.code <> old.code or new.revision <> old.revision + 1 then
        raise exception using errcode = 'check_violation',
            constraint = 'rental_classes_revision_sequence_check',
            message = 'a class keeps its code and takes the next revision';
    end if;
    return new;
end;
$$;
revoke all on function gba.guard_rental_class() from public;
create trigger rental_classes_guard
    before insert or update on gba.rental_classes
    for each row execute function gba.guard_rental_class();

-- An attribute set is written with its class revision, in the same transaction.
create function gba.guard_rental_class_attribute() returns trigger language plpgsql as $$
begin
    if not exists (
        select 1 from gba.rental_classes c
        where c.tenant_id = new.tenant_id and c.id = new.class_id
          and c.revision = new.revision and c.updated_at = now()
    ) then
        raise exception using errcode = 'check_violation',
            constraint = 'rental_class_attributes_revision_check',
            message = 'an attribute set is written with its class revision';
    end if;
    return new;
end;
$$;
revoke all on function gba.guard_rental_class_attribute() from public;
create trigger rental_class_attributes_guard
    before insert on gba.rental_class_attributes
    for each row execute function gba.guard_rental_class_attribute();

-- A unit keeps its class and identifier, takes the next revision and stays retired once retired.
create function gba.guard_rental_unit() returns trigger language plpgsql as $$
begin
    if tg_op = 'INSERT' then
        if new.revision <> 1 then
            raise exception using errcode = 'check_violation',
                constraint = 'rental_units_revision_sequence_check',
                message = 'a unit starts at revision 1';
        end if;
        return new;
    end if;
    if old.state = 'retired' then
        raise exception using errcode = 'check_violation',
            constraint = 'rental_units_retired_check',
            message = 'a retired unit takes no new revision';
    end if;
    if new.class_id <> old.class_id or new.identifier <> old.identifier
       or new.revision <> old.revision + 1 then
        raise exception using errcode = 'check_violation',
            constraint = 'rental_units_revision_sequence_check',
            message = 'a unit keeps its class and identifier and takes the next revision';
    end if;
    return new;
end;
$$;
revoke all on function gba.guard_rental_unit() from public;
create trigger rental_units_guard
    before insert or update on gba.rental_units
    for each row execute function gba.guard_rental_unit();

-- A value is written with its unit revision and fits an attribute of the class's latest set.
create function gba.guard_rental_unit_value() returns trigger language plpgsql as $$
declare
    kind text;
begin
    if not exists (
        select 1 from gba.rental_units u
        where u.tenant_id = new.tenant_id and u.id = new.unit_id
          and u.revision = new.revision and u.updated_at = now()
    ) then
        raise exception using errcode = 'check_violation',
            constraint = 'rental_unit_values_revision_check',
            message = 'values are written with their unit revision';
    end if;
    select a.type into kind
    from gba.rental_units u
    join gba.rental_classes c on c.tenant_id = u.tenant_id and c.id = u.class_id
    join gba.rental_class_attributes a on a.tenant_id = c.tenant_id and a.class_id = c.id
        and a.revision = c.revision and a.key = new.key
    where u.tenant_id = new.tenant_id and u.id = new.unit_id;
    if kind is null
       or (kind = 'number' and new.value !~ '^-?(0|[1-9][0-9]{0,11})(\.[0-9]{1,6})?$')
       or (kind = 'boolean' and new.value not in ('true', 'false'))
       or (kind = 'text' and length(btrim(new.value)) = 0) then
        raise exception using errcode = 'check_violation',
            constraint = 'rental_unit_values_type_check',
            message = 'a value fits an attribute of the class';
    end if;
    return new;
end;
$$;
revoke all on function gba.guard_rental_unit_value() from public;
create trigger rental_unit_values_guard
    before insert on gba.rental_unit_values
    for each row execute function gba.guard_rental_unit_value();

-- At commit, every required attribute of the class has a value for the unit's revision.
create function gba.check_rental_unit_required() returns trigger language plpgsql as $$
begin
    if exists (
        select 1 from gba.rental_units u
        join gba.rental_classes c on c.tenant_id = u.tenant_id and c.id = u.class_id
        join gba.rental_class_attributes a on a.tenant_id = c.tenant_id and a.class_id = c.id
            and a.revision = c.revision and a.required
        where u.tenant_id = new.tenant_id and u.id = new.id
          and not exists (
              select 1 from gba.rental_unit_values v
              where v.tenant_id = u.tenant_id and v.unit_id = u.id
                and v.revision = u.revision and v.key = a.key)
    ) then
        raise exception using errcode = 'check_violation',
            constraint = 'rental_unit_values_required_check',
            message = 'a unit has a value for every required attribute of its class';
    end if;
    return null;
end;
$$;
revoke all on function gba.check_rental_unit_required() from public;
create constraint trigger rental_units_required_values
    after insert or update on gba.rental_units
    deferrable initially deferred
    for each row execute function gba.check_rental_unit_required();

-- Writes need the rental module (ADR-0019 gate); every revision writes its rows, so updates are gated too.
create trigger rental_classes_module_gate
    before insert on gba.rental_classes
    for each row execute function gba.require_enabled_module('rental');
create trigger rental_class_attributes_module_gate
    before insert on gba.rental_class_attributes
    for each row execute function gba.require_enabled_module('rental');
create trigger rental_units_module_gate
    before insert on gba.rental_units
    for each row execute function gba.require_enabled_module('rental');
create trigger rental_unit_values_module_gate
    before insert on gba.rental_unit_values
    for each row execute function gba.require_enabled_module('rental');
create trigger rental_classes_update_module_gate
    before update on gba.rental_classes
    for each row execute function gba.require_enabled_module('rental');
create trigger rental_units_update_module_gate
    before update on gba.rental_units
    for each row execute function gba.require_enabled_module('rental');

alter table gba.rental_classes enable row level security;
alter table gba.rental_classes force row level security;
alter table gba.rental_class_attributes enable row level security;
alter table gba.rental_class_attributes force row level security;
alter table gba.rental_units enable row level security;
alter table gba.rental_units force row level security;
alter table gba.rental_unit_values enable row level security;
alter table gba.rental_unit_values force row level security;
create policy rental_classes_tenant_isolation on gba.rental_classes
    using (tenant_id = gba.current_tenant_id())
    with check (tenant_id = gba.current_tenant_id());
create policy rental_class_attributes_tenant_isolation on gba.rental_class_attributes
    using (tenant_id = gba.current_tenant_id())
    with check (tenant_id = gba.current_tenant_id());
create policy rental_units_tenant_isolation on gba.rental_units
    using (tenant_id = gba.current_tenant_id())
    with check (tenant_id = gba.current_tenant_id());
create policy rental_unit_values_tenant_isolation on gba.rental_unit_values
    using (tenant_id = gba.current_tenant_id())
    with check (tenant_id = gba.current_tenant_id());
grant select, insert on gba.rental_classes, gba.rental_class_attributes, gba.rental_units,
    gba.rental_unit_values to gba_runtime;
grant update (name, meter_kind, revision, updated_at) on gba.rental_classes to gba_runtime;
grant update (location_id, state, revision, updated_at) on gba.rental_units to gba_runtime;

-- Rental branch scope:
-- Classes are company-wide: every member reads them, only a company-wide member writes them.
create policy rental_classes_location_scope on gba.rental_classes
    as restrictive to gba_runtime
    using (true)
    with check (gba.current_location_id() is null);
create policy rental_class_attributes_location_scope on gba.rental_class_attributes
    as restrictive to gba_runtime
    using (true)
    with check (gba.current_location_id() is null);
create policy rental_units_location_scope on gba.rental_units
    as restrictive to gba_runtime
    using (gba.current_location_id() is null or location_id = gba.current_location_id())
    with check (gba.current_location_id() is null or location_id = gba.current_location_id());
create policy rental_unit_values_location_scope on gba.rental_unit_values
    as restrictive to gba_runtime
    using (gba.current_location_id() is null or exists (
        select 1 from gba.rental_units u
        where u.tenant_id = rental_unit_values.tenant_id and u.id = rental_unit_values.unit_id))
    with check (gba.current_location_id() is null or exists (
        select 1 from gba.rental_units u
        where u.tenant_id = rental_unit_values.tenant_id and u.id = rental_unit_values.unit_id));
