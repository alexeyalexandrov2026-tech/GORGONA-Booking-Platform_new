-- O4b (package O, BUILD-01): inspections, defects and the punch list. ADR-0035,
-- docs/plan/PACKAGE_O4B_DESIGN_2026-11-01.md. Everything is insert-only and needs the contract. The
-- database checks that phases are phases of the budget, that dates are not after today on the site,
-- that a passed inspection raises nothing, and that an item's state moves only as its states allow.
create table gba.construction_inspections (
    tenant_id uuid not null references gba.tenants(id),
    project_id uuid not null,
    number integer not null constraint construction_inspections_number_check
        check (number between 1 and 1000000),
    inspected_on date not null constraint construction_inspections_floor_check
        check (inspected_on >= date '2000-01-01'),
    kind text not null constraint construction_inspections_kind_check
        check (kind in ('internal', 'customer', 'authority', 'third_party')),
    phase text constraint construction_inspections_phase_check
        check (phase is null or (length(btrim(phase)) between 1 and 64 and phase !~ '[[:cntrl:]]')),
    inspector text not null constraint construction_inspections_inspector_check
        check (length(btrim(inspector)) between 1 and 64 and inspector !~ '[[:cntrl:]]'),
    inspector_counterparty_id uuid,
    result text not null constraint construction_inspections_result_check
        check (result in ('passed', 'passed_with_items', 'failed')),
    notes text constraint construction_inspections_notes_check
        check (notes is null or length(btrim(notes)) between 1 and 4000),
    created_by uuid not null references gba.users(id),
    created_at timestamptz not null default now(),
    primary key (tenant_id, project_id, number),
    foreign key (tenant_id, project_id) references gba.construction_contracts (tenant_id, project_id),
    foreign key (tenant_id, inspector_counterparty_id) references gba.counterparties (tenant_id, id)
);
create table gba.construction_inspection_photos (
    tenant_id uuid not null references gba.tenants(id),
    project_id uuid not null,
    number integer not null,
    position smallint not null constraint construction_inspection_photos_position_check
        check (position between 1 and 50),
    document_id uuid not null,
    document_revision integer not null,
    primary key (tenant_id, project_id, number, position),
    foreign key (tenant_id, project_id, number)
        references gba.construction_inspections (tenant_id, project_id, number),
    foreign key (tenant_id, document_id, document_revision)
        references gba.document_versions (tenant_id, document_id, revision)
);
-- A defect (work that does not conform) or a punch item (work left before acceptance). The row never
-- changes; its state is the latest of its events, `open` before the first.
create table gba.construction_quality_items (
    tenant_id uuid not null references gba.tenants(id),
    project_id uuid not null,
    number integer not null constraint construction_quality_items_number_check
        check (number between 1 and 1000000),
    kind text not null constraint construction_quality_items_kind_check
        check (kind in ('defect', 'punch')),
    title text not null constraint construction_quality_items_title_check
        check (length(btrim(title)) between 1 and 120 and title !~ '[[:cntrl:]]'),
    description text constraint construction_quality_items_description_check
        check (description is null or length(btrim(description)) between 1 and 4000),
    phase text constraint construction_quality_items_phase_check
        check (phase is null or (length(btrim(phase)) between 1 and 64 and phase !~ '[[:cntrl:]]')),
    location text constraint construction_quality_items_location_check
        check (location is null or (length(btrim(location)) between 1 and 200
            and location !~ '[[:cntrl:]]')),
    severity text not null constraint construction_quality_items_severity_check
        check (severity in ('minor', 'major', 'critical')),
    raised_on date not null constraint construction_quality_items_floor_check
        check (raised_on >= date '2000-01-01'),
    due_on date,
    responsible_id uuid,
    inspection integer,
    created_by uuid not null references gba.users(id),
    created_at timestamptz not null default now(),
    constraint construction_quality_items_due_check
        check (due_on is null or (due_on >= raised_on and due_on <= date '2100-12-31')),
    primary key (tenant_id, project_id, number),
    foreign key (tenant_id, project_id) references gba.construction_contracts (tenant_id, project_id),
    foreign key (tenant_id, responsible_id) references gba.counterparties (tenant_id, id),
    foreign key (tenant_id, project_id, inspection)
        references gba.construction_inspections (tenant_id, project_id, number)
);
create index construction_quality_items_inspection
    on gba.construction_quality_items (tenant_id, project_id, inspection)
    where inspection is not null;
-- A move of an item's state. Voiding and reopening carry a note.
create table gba.construction_quality_item_events (
    tenant_id uuid not null references gba.tenants(id),
    project_id uuid not null,
    item integer not null,
    sequence integer not null constraint construction_quality_item_events_sequence_range_check
        check (sequence between 1 and 10000),
    state text not null constraint construction_quality_item_events_state_check
        check (state in ('open', 'fixed', 'closed', 'void')),
    note text,
    created_by uuid not null references gba.users(id),
    created_at timestamptz not null default now(),
    constraint construction_quality_item_events_note_check
        check ((note is null or length(btrim(note)) between 1 and 1000)
            and (state not in ('open', 'void') or note is not null)),
    primary key (tenant_id, project_id, item, sequence),
    foreign key (tenant_id, project_id, item)
        references gba.construction_quality_items (tenant_id, project_id, number)
);
-- Photos of an item: sequence 0 goes with the item itself, n with its event n.
create table gba.construction_quality_item_photos (
    tenant_id uuid not null references gba.tenants(id),
    project_id uuid not null,
    item integer not null,
    sequence integer not null constraint construction_quality_item_photos_sequence_check
        check (sequence between 0 and 10000),
    position smallint not null constraint construction_quality_item_photos_position_check
        check (position between 1 and 20),
    document_id uuid not null,
    document_revision integer not null,
    primary key (tenant_id, project_id, item, sequence, position),
    foreign key (tenant_id, project_id, item)
        references gba.construction_quality_items (tenant_id, project_id, number),
    foreign key (tenant_id, document_id, document_revision)
        references gba.document_versions (tenant_id, document_id, revision)
);

-- A photo is a document version whose file is a PNG or JPEG.
create function gba.construction_is_image(p_tenant uuid, p_document uuid, p_revision integer)
returns boolean language sql stable as $$
    select exists (
        select 1 from gba.document_versions v
          join gba.document_files f on f.tenant_id = v.tenant_id and f.id = v.file_id
         where v.tenant_id = p_tenant and v.document_id = p_document and v.revision = p_revision
           and f.media_type in ('image/png', 'image/jpeg'))
$$;
revoke all on function gba.construction_is_image(uuid, uuid, integer) from public;
grant execute on function gba.construction_is_image(uuid, uuid, integer) to gba_runtime;

-- Inspections follow each other under the project lock, name a budget phase (or none) and are not
-- dated after today on the site.
create function gba.guard_construction_inspection() returns trigger language plpgsql as $$
begin
    perform 1 from gba.construction_projects p
     where p.tenant_id = new.tenant_id and p.id = new.project_id for update;
    if new.number <> coalesce((
        select max(i.number) from gba.construction_inspections i
        where i.tenant_id = new.tenant_id and i.project_id = new.project_id), 0) + 1 then
        raise exception using errcode = 'check_violation',
            constraint = 'construction_inspections_sequence_check',
            message = 'an inspection follows the latest one';
    end if;
    if new.phase is not null
       and not gba.construction_budget_has_phase(new.tenant_id, new.project_id, new.phase) then
        raise exception using errcode = 'check_violation',
            constraint = 'construction_inspections_budget_check',
            message = 'an inspection names a phase of the budget';
    end if;
    if new.inspected_on > (
        select (now() at time zone p.time_zone)::date from gba.construction_projects p
        where p.tenant_id = new.tenant_id and p.id = new.project_id) then
        raise exception using errcode = 'check_violation',
            constraint = 'construction_inspections_date_check',
            message = 'an inspection date is not after today on the site';
    end if;
    return new;
end;
$$;
revoke all on function gba.guard_construction_inspection() from public;
create trigger construction_inspections_guard
    before insert on gba.construction_inspections
    for each row execute function gba.guard_construction_inspection();

create function gba.guard_construction_inspection_photo() returns trigger language plpgsql as $$
begin
    if not exists (
        select 1 from gba.construction_inspections i
        where i.tenant_id = new.tenant_id and i.project_id = new.project_id
          and i.number = new.number and i.created_at = now()
    ) then
        raise exception using errcode = 'check_violation',
            constraint = 'construction_inspection_photos_record_check',
            message = 'photos are written with their inspection';
    end if;
    if not gba.construction_is_image(new.tenant_id, new.document_id, new.document_revision) then
        raise exception using errcode = 'check_violation',
            constraint = 'construction_inspection_photos_image_check',
            message = 'a photo is a document version with a PNG or JPEG file';
    end if;
    return new;
end;
$$;
revoke all on function gba.guard_construction_inspection_photo() from public;
create trigger construction_inspection_photos_guard
    before insert on gba.construction_inspection_photos
    for each row execute function gba.guard_construction_inspection_photo();

-- Items follow each other under the project lock, name a budget phase (or none), are not raised after
-- today on the site, and never come from an inspection that passed.
create function gba.guard_construction_quality_item() returns trigger language plpgsql as $$
begin
    perform 1 from gba.construction_projects p
     where p.tenant_id = new.tenant_id and p.id = new.project_id for update;
    if new.number <> coalesce((
        select max(q.number) from gba.construction_quality_items q
        where q.tenant_id = new.tenant_id and q.project_id = new.project_id), 0) + 1 then
        raise exception using errcode = 'check_violation',
            constraint = 'construction_quality_items_sequence_check',
            message = 'an item follows the latest one';
    end if;
    if new.phase is not null
       and not gba.construction_budget_has_phase(new.tenant_id, new.project_id, new.phase) then
        raise exception using errcode = 'check_violation',
            constraint = 'construction_quality_items_budget_check',
            message = 'an item names a phase of the budget';
    end if;
    if new.raised_on > (
        select (now() at time zone p.time_zone)::date from gba.construction_projects p
        where p.tenant_id = new.tenant_id and p.id = new.project_id) then
        raise exception using errcode = 'check_violation',
            constraint = 'construction_quality_items_date_check',
            message = 'an item is not raised after today on the site';
    end if;
    if new.inspection is not null and exists (
        select 1 from gba.construction_inspections i
        where i.tenant_id = new.tenant_id and i.project_id = new.project_id
          and i.number = new.inspection and i.result = 'passed'
    ) then
        raise exception using errcode = 'check_violation',
            constraint = 'construction_quality_items_inspection_check',
            message = 'an inspection that passed raises no items';
    end if;
    return new;
end;
$$;
revoke all on function gba.guard_construction_quality_item() from public;
create trigger construction_quality_items_guard
    before insert on gba.construction_quality_items
    for each row execute function gba.guard_construction_quality_item();

-- Events of an item follow each other under the project lock and move its state only as allowed:
-- open -> fixed or void, fixed -> closed or open; closed and void are final.
create function gba.guard_construction_quality_item_event() returns trigger
language plpgsql as $$
declare
    previous text;
begin
    perform 1 from gba.construction_projects p
     where p.tenant_id = new.tenant_id and p.id = new.project_id for update;
    if new.sequence <> coalesce((
        select max(e.sequence) from gba.construction_quality_item_events e
        where e.tenant_id = new.tenant_id and e.project_id = new.project_id
          and e.item = new.item), 0) + 1 then
        raise exception using errcode = 'check_violation',
            constraint = 'construction_quality_item_events_sequence_check',
            message = 'an event follows the latest one of its item';
    end if;
    previous := coalesce((
        select e.state from gba.construction_quality_item_events e
        where e.tenant_id = new.tenant_id and e.project_id = new.project_id
          and e.item = new.item
        order by e.sequence desc limit 1), 'open');
    if (previous, new.state) not in (
        ('open', 'fixed'), ('open', 'void'), ('fixed', 'closed'), ('fixed', 'open')) then
        raise exception using errcode = 'check_violation',
            constraint = 'construction_quality_item_events_transition_check',
            message = 'an item moves only as its state allows';
    end if;
    return new;
end;
$$;
revoke all on function gba.guard_construction_quality_item_event() from public;
create trigger construction_quality_item_events_guard
    before insert on gba.construction_quality_item_events
    for each row execute function gba.guard_construction_quality_item_event();

create function gba.guard_construction_quality_item_photo() returns trigger language plpgsql as $$
begin
    if new.sequence = 0 and not exists (
        select 1 from gba.construction_quality_items q
        where q.tenant_id = new.tenant_id and q.project_id = new.project_id
          and q.number = new.item and q.created_at = now()
    ) or new.sequence > 0 and not exists (
        select 1 from gba.construction_quality_item_events e
        where e.tenant_id = new.tenant_id and e.project_id = new.project_id
          and e.item = new.item and e.sequence = new.sequence and e.created_at = now()
    ) then
        raise exception using errcode = 'check_violation',
            constraint = 'construction_quality_item_photos_record_check',
            message = 'photos are written with their item or event';
    end if;
    if not gba.construction_is_image(new.tenant_id, new.document_id, new.document_revision) then
        raise exception using errcode = 'check_violation',
            constraint = 'construction_quality_item_photos_image_check',
            message = 'a photo is a document version with a PNG or JPEG file';
    end if;
    return new;
end;
$$;
revoke all on function gba.guard_construction_quality_item_photo() from public;
create trigger construction_quality_item_photos_guard
    before insert on gba.construction_quality_item_photos
    for each row execute function gba.guard_construction_quality_item_photo();

-- Writes need the construction module (ADR-0019 gate).
create trigger construction_inspections_module_gate
    before insert on gba.construction_inspections
    for each row execute function gba.require_enabled_module('construction');
create trigger construction_inspection_photos_module_gate
    before insert on gba.construction_inspection_photos
    for each row execute function gba.require_enabled_module('construction');
create trigger construction_quality_items_module_gate
    before insert on gba.construction_quality_items
    for each row execute function gba.require_enabled_module('construction');
create trigger construction_quality_item_events_module_gate
    before insert on gba.construction_quality_item_events
    for each row execute function gba.require_enabled_module('construction');
create trigger construction_quality_item_photos_module_gate
    before insert on gba.construction_quality_item_photos
    for each row execute function gba.require_enabled_module('construction');

alter table gba.construction_inspections enable row level security;
alter table gba.construction_inspections force row level security;
alter table gba.construction_inspection_photos enable row level security;
alter table gba.construction_inspection_photos force row level security;
alter table gba.construction_quality_items enable row level security;
alter table gba.construction_quality_items force row level security;
alter table gba.construction_quality_item_events enable row level security;
alter table gba.construction_quality_item_events force row level security;
alter table gba.construction_quality_item_photos enable row level security;
alter table gba.construction_quality_item_photos force row level security;
create policy construction_inspections_tenant_isolation on gba.construction_inspections
    using (tenant_id = gba.current_tenant_id())
    with check (tenant_id = gba.current_tenant_id());
create policy construction_inspection_photos_tenant_isolation
    on gba.construction_inspection_photos
    using (tenant_id = gba.current_tenant_id())
    with check (tenant_id = gba.current_tenant_id());
create policy construction_quality_items_tenant_isolation on gba.construction_quality_items
    using (tenant_id = gba.current_tenant_id())
    with check (tenant_id = gba.current_tenant_id());
create policy construction_quality_item_events_tenant_isolation
    on gba.construction_quality_item_events
    using (tenant_id = gba.current_tenant_id())
    with check (tenant_id = gba.current_tenant_id());
create policy construction_quality_item_photos_tenant_isolation
    on gba.construction_quality_item_photos
    using (tenant_id = gba.current_tenant_id())
    with check (tenant_id = gba.current_tenant_id());
grant select, insert on gba.construction_inspections, gba.construction_inspection_photos,
    gba.construction_quality_items, gba.construction_quality_item_events,
    gba.construction_quality_item_photos to gba_runtime;

-- Construction branch scope:
create policy construction_inspections_location_scope on gba.construction_inspections
    as restrictive to gba_runtime
    using (gba.current_location_id() is null or exists (
        select 1 from gba.construction_projects p
        where p.tenant_id = construction_inspections.tenant_id
          and p.id = construction_inspections.project_id))
    with check (gba.current_location_id() is null or exists (
        select 1 from gba.construction_projects p
        where p.tenant_id = construction_inspections.tenant_id
          and p.id = construction_inspections.project_id));
create policy construction_inspection_photos_location_scope
    on gba.construction_inspection_photos
    as restrictive to gba_runtime
    using (gba.current_location_id() is null or exists (
        select 1 from gba.construction_projects p
        where p.tenant_id = construction_inspection_photos.tenant_id
          and p.id = construction_inspection_photos.project_id))
    with check (gba.current_location_id() is null or exists (
        select 1 from gba.construction_projects p
        where p.tenant_id = construction_inspection_photos.tenant_id
          and p.id = construction_inspection_photos.project_id));
create policy construction_quality_items_location_scope on gba.construction_quality_items
    as restrictive to gba_runtime
    using (gba.current_location_id() is null or exists (
        select 1 from gba.construction_projects p
        where p.tenant_id = construction_quality_items.tenant_id
          and p.id = construction_quality_items.project_id))
    with check (gba.current_location_id() is null or exists (
        select 1 from gba.construction_projects p
        where p.tenant_id = construction_quality_items.tenant_id
          and p.id = construction_quality_items.project_id));
create policy construction_quality_item_events_location_scope
    on gba.construction_quality_item_events
    as restrictive to gba_runtime
    using (gba.current_location_id() is null or exists (
        select 1 from gba.construction_projects p
        where p.tenant_id = construction_quality_item_events.tenant_id
          and p.id = construction_quality_item_events.project_id))
    with check (gba.current_location_id() is null or exists (
        select 1 from gba.construction_projects p
        where p.tenant_id = construction_quality_item_events.tenant_id
          and p.id = construction_quality_item_events.project_id));
create policy construction_quality_item_photos_location_scope
    on gba.construction_quality_item_photos
    as restrictive to gba_runtime
    using (gba.current_location_id() is null or exists (
        select 1 from gba.construction_projects p
        where p.tenant_id = construction_quality_item_photos.tenant_id
          and p.id = construction_quality_item_photos.project_id))
    with check (gba.current_location_id() is null or exists (
        select 1 from gba.construction_projects p
        where p.tenant_id = construction_quality_item_photos.tenant_id
          and p.id = construction_quality_item_photos.project_id));
