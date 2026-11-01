-- O4a (package O, BUILD-01): the schedule, daily reports and completed quantities. ADR-0035,
-- docs/plan/PACKAGE_O4A_DESIGN_2026-11-01.md. Everything is insert-only and needs the contract. The
-- database checks that a schedule names budget phases with acyclic dependencies, that dates are not
-- after today on the site, and that the quantity completed on a line never exceeds what it contracts.
create table gba.construction_schedule_versions (
    tenant_id uuid not null references gba.tenants(id),
    project_id uuid not null,
    revision integer not null constraint construction_schedule_versions_revision_check
        check (revision between 1 and 100000),
    note text constraint construction_schedule_versions_note_check
        check (note is null or length(btrim(note)) between 1 and 1000),
    created_by uuid not null references gba.users(id),
    created_at timestamptz not null default now(),
    primary key (tenant_id, project_id, revision),
    foreign key (tenant_id, project_id) references gba.construction_contracts (tenant_id, project_id)
);
create table gba.construction_schedule_phases (
    tenant_id uuid not null references gba.tenants(id),
    project_id uuid not null,
    revision integer not null,
    phase text not null constraint construction_schedule_phases_phase_check
        check (length(btrim(phase)) between 1 and 64 and phase !~ '[[:cntrl:]]'),
    planned_start date not null,
    planned_finish date not null,
    primary key (tenant_id, project_id, revision, phase),
    foreign key (tenant_id, project_id, revision)
        references gba.construction_schedule_versions (tenant_id, project_id, revision),
    constraint construction_schedule_phases_dates_check check (
        planned_start >= date '2000-01-01' and planned_finish <= date '2100-12-31'
        and planned_finish >= planned_start)
);
-- Finish-to-start: `phase` starts after `depends_on` finishes. Both are phases of the same version.
create table gba.construction_schedule_dependencies (
    tenant_id uuid not null references gba.tenants(id),
    project_id uuid not null,
    revision integer not null,
    phase text not null,
    depends_on text not null,
    primary key (tenant_id, project_id, revision, phase, depends_on),
    foreign key (tenant_id, project_id, revision, phase)
        references gba.construction_schedule_phases (tenant_id, project_id, revision, phase),
    foreign key (tenant_id, project_id, revision, depends_on)
        references gba.construction_schedule_phases (tenant_id, project_id, revision, phase),
    constraint construction_schedule_dependencies_self_check check (phase <> depends_on)
);
-- One report per site date, corrected by later revisions; crew lines and photos go with a revision.
create table gba.construction_daily_reports (
    tenant_id uuid not null references gba.tenants(id),
    project_id uuid not null,
    report_date date not null constraint construction_daily_reports_floor_check
        check (report_date >= date '2000-01-01'),
    revision integer not null constraint construction_daily_reports_revision_check
        check (revision between 1 and 1000),
    weather text constraint construction_daily_reports_weather_check
        check (weather is null or (length(btrim(weather)) between 1 and 200
            and weather !~ '[[:cntrl:]]')),
    notes text constraint construction_daily_reports_notes_check
        check (notes is null or length(btrim(notes)) between 1 and 4000),
    created_by uuid not null references gba.users(id),
    created_at timestamptz not null default now(),
    primary key (tenant_id, project_id, report_date, revision),
    foreign key (tenant_id, project_id) references gba.construction_contracts (tenant_id, project_id)
);
create table gba.construction_daily_report_crew (
    tenant_id uuid not null references gba.tenants(id),
    project_id uuid not null,
    report_date date not null,
    revision integer not null,
    position smallint not null constraint construction_daily_report_crew_position_check
        check (position between 1 and 50),
    label text not null constraint construction_daily_report_crew_label_check
        check (length(btrim(label)) between 1 and 64 and label !~ '[[:cntrl:]]'),
    headcount integer not null constraint construction_daily_report_crew_headcount_check
        check (headcount between 1 and 1000),
    counterparty_id uuid,
    primary key (tenant_id, project_id, report_date, revision, position),
    foreign key (tenant_id, project_id, report_date, revision)
        references gba.construction_daily_reports (tenant_id, project_id, report_date, revision),
    foreign key (tenant_id, counterparty_id) references gba.counterparties (tenant_id, id)
);
create table gba.construction_daily_report_photos (
    tenant_id uuid not null references gba.tenants(id),
    project_id uuid not null,
    report_date date not null,
    revision integer not null,
    position smallint not null constraint construction_daily_report_photos_position_check
        check (position between 1 and 50),
    document_id uuid not null,
    document_revision integer not null,
    primary key (tenant_id, project_id, report_date, revision, position),
    foreign key (tenant_id, project_id, report_date, revision)
        references gba.construction_daily_reports (tenant_id, project_id, report_date, revision),
    foreign key (tenant_id, document_id, document_revision)
        references gba.document_versions (tenant_id, document_id, revision)
);
-- The quantity completed to date on one budget line; the latest measurement of a line counts.
create table gba.construction_progress_measurements (
    tenant_id uuid not null references gba.tenants(id),
    project_id uuid not null,
    number integer not null constraint construction_progress_measurements_number_check
        check (number between 1 and 1000000),
    change_order integer constraint construction_progress_measurements_change_order_check
        check (change_order between 1 and 100000),
    budget_position smallint not null constraint construction_progress_measurements_position_check
        check (budget_position between 1 and 500),
    measured_on date not null constraint construction_progress_measurements_floor_check
        check (measured_on >= date '2000-01-01'),
    quantity_to_date numeric(13, 4) not null
        constraint construction_progress_measurements_quantity_check check (quantity_to_date >= 0),
    note text constraint construction_progress_measurements_note_check
        check (note is null or length(btrim(note)) between 1 and 500),
    created_by uuid not null references gba.users(id),
    created_at timestamptz not null default now(),
    primary key (tenant_id, project_id, number),
    foreign key (tenant_id, project_id) references gba.construction_contracts (tenant_id, project_id)
);
create index construction_progress_measurements_line
    on gba.construction_progress_measurements (tenant_id, project_id, budget_position, number);

-- The quantity a budget line contracts as the caller may see it: a contract line less its approved
-- removals, or the added line of an approved change order; null when the line is not in the budget.
create function gba.construction_contracted_quantity(
    p_tenant uuid, p_project uuid, p_change_order integer, p_position smallint
) returns numeric language sql stable as $$
    select case when p_change_order is null then (
        select l.quantity - coalesce((
            select sum(o.quantity) from gba.construction_change_order_lines o
              join gba.construction_change_order_decisions d
                on d.tenant_id = o.tenant_id and d.project_id = o.project_id
               and d.number = o.number and d.decision = 'approved'
             where o.tenant_id = p_tenant and o.project_id = p_project
               and o.action = 'remove' and o.contract_position = p_position), 0)
          from gba.construction_contracts k
          join gba.construction_estimate_lines l
            on l.tenant_id = k.tenant_id and l.project_id = k.project_id and l.version = k.version
         where k.tenant_id = p_tenant and k.project_id = p_project and l.position = p_position)
    else (
        select o.quantity from gba.construction_change_order_lines o
          join gba.construction_change_order_decisions d
            on d.tenant_id = o.tenant_id and d.project_id = o.project_id
           and d.number = o.number and d.decision = 'approved'
         where o.tenant_id = p_tenant and o.project_id = p_project and o.number = p_change_order
           and o.position = p_position and o.action = 'add')
    end
$$;
revoke all on function gba.construction_contracted_quantity(uuid, uuid, integer, smallint)
    from public;
grant execute on function gba.construction_contracted_quantity(uuid, uuid, integer, smallint)
    to gba_runtime;

-- The phases of the budget: those of the contract lines and of added lines of approved changes.
create function gba.construction_budget_has_phase(p_tenant uuid, p_project uuid, p_phase text)
returns boolean language sql stable as $$
    select exists (
        select 1 from gba.construction_contracts k
          join gba.construction_estimate_lines l
            on l.tenant_id = k.tenant_id and l.project_id = k.project_id and l.version = k.version
         where k.tenant_id = p_tenant and k.project_id = p_project and l.phase = p_phase
    ) or exists (
        select 1 from gba.construction_change_order_lines o
          join gba.construction_change_order_decisions d
            on d.tenant_id = o.tenant_id and d.project_id = o.project_id
           and d.number = o.number and d.decision = 'approved'
         where o.tenant_id = p_tenant and o.project_id = p_project and o.action = 'add'
           and o.phase = p_phase
    )
$$;
revoke all on function gba.construction_budget_has_phase(uuid, uuid, text) from public;
grant execute on function gba.construction_budget_has_phase(uuid, uuid, text) to gba_runtime;

-- Schedule versions follow each other; phases and dependencies are written with their version.
create function gba.guard_construction_schedule_version() returns trigger language plpgsql as $$
begin
    if new.revision <> coalesce((
        select max(v.revision) from gba.construction_schedule_versions v
        where v.tenant_id = new.tenant_id and v.project_id = new.project_id), 0) + 1 then
        raise exception using errcode = 'check_violation',
            constraint = 'construction_schedule_versions_sequence_check',
            message = 'a schedule version follows the latest one';
    end if;
    return new;
end;
$$;
revoke all on function gba.guard_construction_schedule_version() from public;
create trigger construction_schedule_versions_guard
    before insert on gba.construction_schedule_versions
    for each row execute function gba.guard_construction_schedule_version();

create function gba.guard_construction_schedule_phase() returns trigger language plpgsql as $$
begin
    if not exists (
        select 1 from gba.construction_schedule_versions v
        where v.tenant_id = new.tenant_id and v.project_id = new.project_id
          and v.revision = new.revision and v.created_at = now()
    ) then
        raise exception using errcode = 'check_violation',
            constraint = 'construction_schedule_phases_version_check',
            message = 'schedule phases are written with their version';
    end if;
    if not gba.construction_budget_has_phase(new.tenant_id, new.project_id, new.phase) then
        raise exception using errcode = 'check_violation',
            constraint = 'construction_schedule_phases_budget_check',
            message = 'a schedule names phases of the budget';
    end if;
    return new;
end;
$$;
revoke all on function gba.guard_construction_schedule_phase() from public;
create trigger construction_schedule_phases_guard
    before insert on gba.construction_schedule_phases
    for each row execute function gba.guard_construction_schedule_phase();

-- A dependency is written with its version and never closes a cycle: the predecessor must not
-- already depend, directly or through others, on the phase. A phase on itself is the check above.
create function gba.guard_construction_schedule_dependency() returns trigger language plpgsql as $$
begin
    if not exists (
        select 1 from gba.construction_schedule_versions v
        where v.tenant_id = new.tenant_id and v.project_id = new.project_id
          and v.revision = new.revision and v.created_at = now()
    ) then
        raise exception using errcode = 'check_violation',
            constraint = 'construction_schedule_dependencies_version_check',
            message = 'schedule dependencies are written with their version';
    end if;
    if new.phase <> new.depends_on and exists (
        with recursive reach (node) as (
            select d.depends_on from gba.construction_schedule_dependencies d
             where d.tenant_id = new.tenant_id and d.project_id = new.project_id
               and d.revision = new.revision and d.phase = new.depends_on
            union
            select d.depends_on from gba.construction_schedule_dependencies d
              join reach r on d.phase = r.node
             where d.tenant_id = new.tenant_id and d.project_id = new.project_id
               and d.revision = new.revision
        )
        select 1 from reach where node = new.phase
    ) then
        raise exception using errcode = 'check_violation',
            constraint = 'construction_schedule_dependencies_cycle_check',
            message = 'schedule dependencies never form a cycle';
    end if;
    return new;
end;
$$;
revoke all on function gba.guard_construction_schedule_dependency() from public;
create trigger construction_schedule_dependencies_guard
    before insert on gba.construction_schedule_dependencies
    for each row execute function gba.guard_construction_schedule_dependency();

-- A report revision follows the latest of its date, which is not after today on the site.
create function gba.guard_construction_daily_report() returns trigger language plpgsql as $$
begin
    if new.revision <> coalesce((
        select max(r.revision) from gba.construction_daily_reports r
        where r.tenant_id = new.tenant_id and r.project_id = new.project_id
          and r.report_date = new.report_date), 0) + 1 then
        raise exception using errcode = 'check_violation',
            constraint = 'construction_daily_reports_sequence_check',
            message = 'a daily report revision follows the latest one of its date';
    end if;
    if new.report_date > (
        select (now() at time zone p.time_zone)::date from gba.construction_projects p
        where p.tenant_id = new.tenant_id and p.id = new.project_id) then
        raise exception using errcode = 'check_violation',
            constraint = 'construction_daily_reports_date_check',
            message = 'a daily report date is not after today on the site';
    end if;
    return new;
end;
$$;
revoke all on function gba.guard_construction_daily_report() from public;
create trigger construction_daily_reports_guard
    before insert on gba.construction_daily_reports
    for each row execute function gba.guard_construction_daily_report();

create function gba.guard_construction_daily_report_crew() returns trigger language plpgsql as $$
begin
    if not exists (
        select 1 from gba.construction_daily_reports r
        where r.tenant_id = new.tenant_id and r.project_id = new.project_id
          and r.report_date = new.report_date and r.revision = new.revision
          and r.created_at = now()
    ) then
        raise exception using errcode = 'check_violation',
            constraint = 'construction_daily_report_crew_report_check',
            message = 'crew lines are written with their report';
    end if;
    return new;
end;
$$;
revoke all on function gba.guard_construction_daily_report_crew() from public;
create trigger construction_daily_report_crew_guard
    before insert on gba.construction_daily_report_crew
    for each row execute function gba.guard_construction_daily_report_crew();

-- A photo is written with its report and is a document version whose file is a PNG or JPEG.
create function gba.guard_construction_daily_report_photo() returns trigger language plpgsql as $$
begin
    if not exists (
        select 1 from gba.construction_daily_reports r
        where r.tenant_id = new.tenant_id and r.project_id = new.project_id
          and r.report_date = new.report_date and r.revision = new.revision
          and r.created_at = now()
    ) then
        raise exception using errcode = 'check_violation',
            constraint = 'construction_daily_report_photos_report_check',
            message = 'photos are written with their report';
    end if;
    if not exists (
        select 1 from gba.document_versions v
          join gba.document_files f on f.tenant_id = v.tenant_id and f.id = v.file_id
         where v.tenant_id = new.tenant_id and v.document_id = new.document_id
           and v.revision = new.document_revision
           and f.media_type in ('image/png', 'image/jpeg')
    ) then
        raise exception using errcode = 'check_violation',
            constraint = 'construction_daily_report_photos_image_check',
            message = 'a photo is a document version with a PNG or JPEG file';
    end if;
    return new;
end;
$$;
revoke all on function gba.guard_construction_daily_report_photo() from public;
create trigger construction_daily_report_photos_guard
    before insert on gba.construction_daily_report_photos
    for each row execute function gba.guard_construction_daily_report_photo();

-- Measurements follow each other under the project lock, on a budget line, on a site date not after
-- today and not before the line's latest one; to date never exceeds the contracted quantity, and a
-- lower value than the line's latest is a correction with a note.
create function gba.guard_construction_progress_measurement() returns trigger
language plpgsql as $$
declare
    contracted numeric;
    latest record;
begin
    perform 1 from gba.construction_projects p
     where p.tenant_id = new.tenant_id and p.id = new.project_id for update;
    if new.number <> coalesce((
        select max(m.number) from gba.construction_progress_measurements m
        where m.tenant_id = new.tenant_id and m.project_id = new.project_id), 0) + 1 then
        raise exception using errcode = 'check_violation',
            constraint = 'construction_progress_measurements_sequence_check',
            message = 'a measurement follows the latest one';
    end if;
    contracted := gba.construction_contracted_quantity(
        new.tenant_id, new.project_id, new.change_order, new.budget_position);
    if contracted is null then
        raise exception using errcode = 'check_violation',
            constraint = 'construction_progress_measurements_budget_check',
            message = 'a measurement names a line of the budget';
    end if;
    if new.measured_on > (
        select (now() at time zone p.time_zone)::date from gba.construction_projects p
        where p.tenant_id = new.tenant_id and p.id = new.project_id) then
        raise exception using errcode = 'check_violation',
            constraint = 'construction_progress_measurements_date_check',
            message = 'a measurement date is not after today on the site';
    end if;
    select m.measured_on, m.quantity_to_date into latest
      from gba.construction_progress_measurements m
     where m.tenant_id = new.tenant_id and m.project_id = new.project_id
       and m.budget_position = new.budget_position
       and m.change_order is not distinct from new.change_order
     order by m.number desc limit 1;
    if found and new.measured_on < latest.measured_on then
        raise exception using errcode = 'check_violation',
            constraint = 'construction_progress_measurements_order_check',
            message = 'a measurement is not dated before the line''s latest one';
    end if;
    if new.quantity_to_date > contracted then
        raise exception using errcode = 'check_violation',
            constraint = 'construction_progress_measurements_contract_check',
            message = 'completed never exceeds the contracted quantity';
    end if;
    if found and new.quantity_to_date < latest.quantity_to_date and new.note is null then
        raise exception using errcode = 'check_violation',
            constraint = 'construction_progress_measurements_note_check',
            message = 'a lower quantity than the latest is a correction with a note';
    end if;
    return new;
end;
$$;
revoke all on function gba.guard_construction_progress_measurement() from public;
create trigger construction_progress_measurements_guard
    before insert on gba.construction_progress_measurements
    for each row execute function gba.guard_construction_progress_measurement();

-- O2's approval guard, replaced: besides never removing more than a contract line holds, an approval
-- never leaves a contract line below its completed quantity. It takes the project lock that
-- measurements take, so the two serialise even through direct SQL.
create or replace function gba.guard_construction_change_order_decision() returns trigger
language plpgsql as $$
begin
    if new.decision <> 'approved' then
        return new;
    end if;
    perform 1 from gba.construction_projects p
     where p.tenant_id = new.tenant_id and p.id = new.project_id for update;
    if exists (
        select 1
        from gba.construction_change_order_lines n
        join gba.construction_contracts k
          on k.tenant_id = n.tenant_id and k.project_id = n.project_id
        join gba.construction_estimate_lines l
          on l.tenant_id = k.tenant_id and l.project_id = k.project_id and l.version = k.version
         and l.position = n.contract_position
        where n.tenant_id = new.tenant_id and n.project_id = new.project_id
          and n.number = new.number and n.action = 'remove'
        group by n.contract_position, l.quantity
        having sum(n.quantity) + coalesce((
            select sum(o.quantity) from gba.construction_change_order_lines o
            join gba.construction_change_order_decisions d
              on d.tenant_id = o.tenant_id and d.project_id = o.project_id
             and d.number = o.number and d.decision = 'approved'
            where o.tenant_id = new.tenant_id and o.project_id = new.project_id
              and o.action = 'remove' and o.contract_position = n.contract_position), 0)
            > l.quantity
    ) then
        raise exception using errcode = 'check_violation',
            constraint = 'construction_change_order_decisions_scope_check',
            message = 'an approval never removes more than the contract line holds';
    end if;
    if exists (
        select 1
        from gba.construction_change_order_lines n
        where n.tenant_id = new.tenant_id and n.project_id = new.project_id
          and n.number = new.number and n.action = 'remove'
        group by n.contract_position
        having gba.construction_contracted_quantity(
                new.tenant_id, new.project_id, null, n.contract_position) - sum(n.quantity)
            < coalesce((
                select m.quantity_to_date from gba.construction_progress_measurements m
                where m.tenant_id = new.tenant_id and m.project_id = new.project_id
                  and m.change_order is null and m.budget_position = n.contract_position
                order by m.number desc limit 1), 0)
    ) then
        raise exception using errcode = 'check_violation',
            constraint = 'construction_change_order_decisions_completed_check',
            message = 'an approval never leaves a contract line below its completed quantity';
    end if;
    return new;
end;
$$;

-- Writes need the construction module (ADR-0019 gate).
create trigger construction_schedule_versions_module_gate
    before insert on gba.construction_schedule_versions
    for each row execute function gba.require_enabled_module('construction');
create trigger construction_schedule_phases_module_gate
    before insert on gba.construction_schedule_phases
    for each row execute function gba.require_enabled_module('construction');
create trigger construction_schedule_dependencies_module_gate
    before insert on gba.construction_schedule_dependencies
    for each row execute function gba.require_enabled_module('construction');
create trigger construction_daily_reports_module_gate
    before insert on gba.construction_daily_reports
    for each row execute function gba.require_enabled_module('construction');
create trigger construction_daily_report_crew_module_gate
    before insert on gba.construction_daily_report_crew
    for each row execute function gba.require_enabled_module('construction');
create trigger construction_daily_report_photos_module_gate
    before insert on gba.construction_daily_report_photos
    for each row execute function gba.require_enabled_module('construction');
create trigger construction_progress_measurements_module_gate
    before insert on gba.construction_progress_measurements
    for each row execute function gba.require_enabled_module('construction');

alter table gba.construction_schedule_versions enable row level security;
alter table gba.construction_schedule_versions force row level security;
alter table gba.construction_schedule_phases enable row level security;
alter table gba.construction_schedule_phases force row level security;
alter table gba.construction_schedule_dependencies enable row level security;
alter table gba.construction_schedule_dependencies force row level security;
alter table gba.construction_daily_reports enable row level security;
alter table gba.construction_daily_reports force row level security;
alter table gba.construction_daily_report_crew enable row level security;
alter table gba.construction_daily_report_crew force row level security;
alter table gba.construction_daily_report_photos enable row level security;
alter table gba.construction_daily_report_photos force row level security;
alter table gba.construction_progress_measurements enable row level security;
alter table gba.construction_progress_measurements force row level security;
create policy construction_schedule_versions_tenant_isolation
    on gba.construction_schedule_versions
    using (tenant_id = gba.current_tenant_id())
    with check (tenant_id = gba.current_tenant_id());
create policy construction_schedule_phases_tenant_isolation on gba.construction_schedule_phases
    using (tenant_id = gba.current_tenant_id())
    with check (tenant_id = gba.current_tenant_id());
create policy construction_schedule_dependencies_tenant_isolation
    on gba.construction_schedule_dependencies
    using (tenant_id = gba.current_tenant_id())
    with check (tenant_id = gba.current_tenant_id());
create policy construction_daily_reports_tenant_isolation on gba.construction_daily_reports
    using (tenant_id = gba.current_tenant_id())
    with check (tenant_id = gba.current_tenant_id());
create policy construction_daily_report_crew_tenant_isolation on gba.construction_daily_report_crew
    using (tenant_id = gba.current_tenant_id())
    with check (tenant_id = gba.current_tenant_id());
create policy construction_daily_report_photos_tenant_isolation
    on gba.construction_daily_report_photos
    using (tenant_id = gba.current_tenant_id())
    with check (tenant_id = gba.current_tenant_id());
create policy construction_progress_measurements_tenant_isolation
    on gba.construction_progress_measurements
    using (tenant_id = gba.current_tenant_id())
    with check (tenant_id = gba.current_tenant_id());
grant select, insert on gba.construction_schedule_versions, gba.construction_schedule_phases,
    gba.construction_schedule_dependencies, gba.construction_daily_reports,
    gba.construction_daily_report_crew, gba.construction_daily_report_photos,
    gba.construction_progress_measurements to gba_runtime;

-- Construction branch scope:
create policy construction_schedule_versions_location_scope on gba.construction_schedule_versions
    as restrictive to gba_runtime
    using (gba.current_location_id() is null or exists (
        select 1 from gba.construction_projects p
        where p.tenant_id = construction_schedule_versions.tenant_id
          and p.id = construction_schedule_versions.project_id))
    with check (gba.current_location_id() is null or exists (
        select 1 from gba.construction_projects p
        where p.tenant_id = construction_schedule_versions.tenant_id
          and p.id = construction_schedule_versions.project_id));
create policy construction_schedule_phases_location_scope on gba.construction_schedule_phases
    as restrictive to gba_runtime
    using (gba.current_location_id() is null or exists (
        select 1 from gba.construction_projects p
        where p.tenant_id = construction_schedule_phases.tenant_id
          and p.id = construction_schedule_phases.project_id))
    with check (gba.current_location_id() is null or exists (
        select 1 from gba.construction_projects p
        where p.tenant_id = construction_schedule_phases.tenant_id
          and p.id = construction_schedule_phases.project_id));
create policy construction_schedule_dependencies_location_scope
    on gba.construction_schedule_dependencies
    as restrictive to gba_runtime
    using (gba.current_location_id() is null or exists (
        select 1 from gba.construction_projects p
        where p.tenant_id = construction_schedule_dependencies.tenant_id
          and p.id = construction_schedule_dependencies.project_id))
    with check (gba.current_location_id() is null or exists (
        select 1 from gba.construction_projects p
        where p.tenant_id = construction_schedule_dependencies.tenant_id
          and p.id = construction_schedule_dependencies.project_id));
create policy construction_daily_reports_location_scope on gba.construction_daily_reports
    as restrictive to gba_runtime
    using (gba.current_location_id() is null or exists (
        select 1 from gba.construction_projects p
        where p.tenant_id = construction_daily_reports.tenant_id
          and p.id = construction_daily_reports.project_id))
    with check (gba.current_location_id() is null or exists (
        select 1 from gba.construction_projects p
        where p.tenant_id = construction_daily_reports.tenant_id
          and p.id = construction_daily_reports.project_id));
create policy construction_daily_report_crew_location_scope on gba.construction_daily_report_crew
    as restrictive to gba_runtime
    using (gba.current_location_id() is null or exists (
        select 1 from gba.construction_projects p
        where p.tenant_id = construction_daily_report_crew.tenant_id
          and p.id = construction_daily_report_crew.project_id))
    with check (gba.current_location_id() is null or exists (
        select 1 from gba.construction_projects p
        where p.tenant_id = construction_daily_report_crew.tenant_id
          and p.id = construction_daily_report_crew.project_id));
create policy construction_daily_report_photos_location_scope
    on gba.construction_daily_report_photos
    as restrictive to gba_runtime
    using (gba.current_location_id() is null or exists (
        select 1 from gba.construction_projects p
        where p.tenant_id = construction_daily_report_photos.tenant_id
          and p.id = construction_daily_report_photos.project_id))
    with check (gba.current_location_id() is null or exists (
        select 1 from gba.construction_projects p
        where p.tenant_id = construction_daily_report_photos.tenant_id
          and p.id = construction_daily_report_photos.project_id));
create policy construction_progress_measurements_location_scope
    on gba.construction_progress_measurements
    as restrictive to gba_runtime
    using (gba.current_location_id() is null or exists (
        select 1 from gba.construction_projects p
        where p.tenant_id = construction_progress_measurements.tenant_id
          and p.id = construction_progress_measurements.project_id))
    with check (gba.current_location_id() is null or exists (
        select 1 from gba.construction_projects p
        where p.tenant_id = construction_progress_measurements.tenant_id
          and p.id = construction_progress_measurements.project_id));
