-- O3a (package O, BUILD-01): commitments against the construction budget. ADR-0035,
-- docs/plan/PACKAGE_O3A_DESIGN_2026-10-31.md. The budget is derived from the contract and approved change
-- orders; nothing of it is stored. Commitments, their versions and their lines are insert-only.
create table gba.construction_commitments (
    tenant_id uuid not null references gba.tenants(id),
    project_id uuid not null,
    number integer not null constraint construction_commitments_number_check
        check (number between 1 and 100000),
    kind text not null constraint construction_commitments_kind_check
        check (kind in ('subcontract', 'purchase_order')),
    counterparty_id uuid not null,
    created_by uuid not null references gba.users(id),
    created_at timestamptz not null default now(),
    primary key (tenant_id, project_id, number),
    foreign key (tenant_id, project_id) references gba.construction_contracts (tenant_id, project_id),
    foreign key (tenant_id, counterparty_id) references gba.counterparties (tenant_id, id)
);
create table gba.construction_commitment_versions (
    tenant_id uuid not null references gba.tenants(id),
    project_id uuid not null,
    number integer not null,
    revision integer not null constraint construction_commitment_versions_revision_check
        check (revision between 1 and 100000),
    state text not null constraint construction_commitment_versions_state_check
        check (state in ('open', 'cancelled')),
    title text not null constraint construction_commitment_versions_title_check
        check (length(btrim(title)) between 1 and 200 and title !~ '[[:cntrl:]]'),
    reference text constraint construction_commitment_versions_reference_check
        check (reference is null
            or (length(btrim(reference)) between 1 and 64 and reference !~ '[[:cntrl:]]')),
    note text constraint construction_commitment_versions_note_check
        check (note is null or length(note) between 1 and 1000),
    created_by uuid not null references gba.users(id),
    created_at timestamptz not null default now(),
    primary key (tenant_id, project_id, number, revision),
    foreign key (tenant_id, project_id, number)
        references gba.construction_commitments (tenant_id, project_id, number)
);
-- A line names one budget line: a contract line (change_order null) or an added line of a change order.
create table gba.construction_commitment_lines (
    tenant_id uuid not null references gba.tenants(id),
    project_id uuid not null,
    number integer not null,
    revision integer not null,
    line_no smallint not null constraint construction_commitment_lines_line_no_check
        check (line_no between 1 and 200),
    change_order integer constraint construction_commitment_lines_change_order_check
        check (change_order between 1 and 100000),
    budget_position smallint not null constraint construction_commitment_lines_position_check
        check (budget_position between 1 and 500),
    amount_minor bigint not null constraint construction_commitment_lines_amount_check
        check (amount_minor between 1 and 1000000000000),
    primary key (tenant_id, project_id, number, revision, line_no),
    constraint construction_commitment_lines_budget_key unique nulls not distinct
        (tenant_id, project_id, number, revision, change_order, budget_position),
    foreign key (tenant_id, project_id, number, revision)
        references gba.construction_commitment_versions (tenant_id, project_id, number, revision)
);

-- Commitments follow each other; the counterparty is active and has the role of the kind.
create function gba.guard_construction_commitment() returns trigger language plpgsql as $$
begin
    if new.number <> coalesce((
        select max(c.number) from gba.construction_commitments c
        where c.tenant_id = new.tenant_id and c.project_id = new.project_id), 0) + 1 then
        raise exception using errcode = 'check_violation',
            constraint = 'construction_commitments_sequence_check',
            message = 'a commitment follows the latest one';
    end if;
    if not exists (
        select 1 from gba.counterparty_versions v
        where v.tenant_id = new.tenant_id and v.counterparty_id = new.counterparty_id
          and v.state = 'active'
          and (case new.kind when 'subcontract' then 'contractor' else 'supplier' end) = any(v.roles)
          and v.revision = (
              select max(x.revision) from gba.counterparty_versions x
              where x.tenant_id = v.tenant_id and x.counterparty_id = v.counterparty_id)
    ) then
        raise exception using errcode = 'check_violation',
            constraint = 'construction_commitments_counterparty_check',
            message = 'a commitment names an active counterparty with the role of its kind';
    end if;
    return new;
end;
$$;
revoke all on function gba.guard_construction_commitment() from public;
create trigger construction_commitments_guard
    before insert on gba.construction_commitments
    for each row execute function gba.guard_construction_commitment();

-- Versions follow each other; the first is written with its commitment; a cancellation is final.
create function gba.guard_construction_commitment_version() returns trigger language plpgsql as $$
begin
    if exists (
        select 1 from gba.construction_commitment_versions v
        where v.tenant_id = new.tenant_id and v.project_id = new.project_id
          and v.number = new.number and v.state = 'cancelled'
    ) then
        raise exception using errcode = 'check_violation',
            constraint = 'construction_commitment_versions_cancelled_check',
            message = 'a cancelled commitment takes no new version';
    end if;
    if new.revision <> coalesce((
        select max(v.revision) from gba.construction_commitment_versions v
        where v.tenant_id = new.tenant_id and v.project_id = new.project_id
          and v.number = new.number), 0) + 1
       or (new.revision = 1 and not exists (
        select 1 from gba.construction_commitments c
        where c.tenant_id = new.tenant_id and c.project_id = new.project_id
          and c.number = new.number and c.created_at = now())) then
        raise exception using errcode = 'check_violation',
            constraint = 'construction_commitment_versions_sequence_check',
            message = 'a commitment version follows the latest one';
    end if;
    return new;
end;
$$;
revoke all on function gba.guard_construction_commitment_version() from public;
create trigger construction_commitment_versions_guard
    before insert on gba.construction_commitment_versions
    for each row execute function gba.guard_construction_commitment_version();

-- Lines are written with an open version and name a line of the budget: a contract line, or an added
-- line of an approved change order.
create function gba.guard_construction_commitment_line() returns trigger language plpgsql as $$
begin
    if not exists (
        select 1 from gba.construction_commitment_versions v
        where v.tenant_id = new.tenant_id and v.project_id = new.project_id
          and v.number = new.number and v.revision = new.revision
          and v.state = 'open' and v.created_at = now()
    ) then
        raise exception using errcode = 'check_violation',
            constraint = 'construction_commitment_lines_version_check',
            message = 'commitment lines are written with their open version';
    end if;
    if (new.change_order is null and not exists (
        select 1 from gba.construction_contracts k
        join gba.construction_estimate_lines l
          on l.tenant_id = k.tenant_id and l.project_id = k.project_id and l.version = k.version
        where k.tenant_id = new.tenant_id and k.project_id = new.project_id
          and l.position = new.budget_position
    )) or (new.change_order is not null and not exists (
        select 1 from gba.construction_change_order_lines o
        join gba.construction_change_order_decisions d
          on d.tenant_id = o.tenant_id and d.project_id = o.project_id and d.number = o.number
        where o.tenant_id = new.tenant_id and o.project_id = new.project_id
          and o.number = new.change_order and o.position = new.budget_position
          and o.action = 'add' and d.decision = 'approved'
    )) then
        raise exception using errcode = 'check_violation',
            constraint = 'construction_commitment_lines_budget_check',
            message = 'a commitment line names a line of the budget';
    end if;
    return new;
end;
$$;
revoke all on function gba.guard_construction_commitment_line() from public;
create trigger construction_commitment_lines_guard
    before insert on gba.construction_commitment_lines
    for each row execute function gba.guard_construction_commitment_line();

-- Writes need the construction module (ADR-0019 gate).
create trigger construction_commitments_module_gate
    before insert on gba.construction_commitments
    for each row execute function gba.require_enabled_module('construction');
create trigger construction_commitment_versions_module_gate
    before insert on gba.construction_commitment_versions
    for each row execute function gba.require_enabled_module('construction');

alter table gba.construction_commitments enable row level security;
alter table gba.construction_commitments force row level security;
alter table gba.construction_commitment_versions enable row level security;
alter table gba.construction_commitment_versions force row level security;
alter table gba.construction_commitment_lines enable row level security;
alter table gba.construction_commitment_lines force row level security;
create policy construction_commitments_tenant_isolation on gba.construction_commitments
    using (tenant_id = gba.current_tenant_id())
    with check (tenant_id = gba.current_tenant_id());
create policy construction_commitment_versions_tenant_isolation
    on gba.construction_commitment_versions
    using (tenant_id = gba.current_tenant_id())
    with check (tenant_id = gba.current_tenant_id());
create policy construction_commitment_lines_tenant_isolation on gba.construction_commitment_lines
    using (tenant_id = gba.current_tenant_id())
    with check (tenant_id = gba.current_tenant_id());
grant select, insert on gba.construction_commitments, gba.construction_commitment_versions,
    gba.construction_commitment_lines to gba_runtime;

-- Construction branch scope:
create policy construction_commitments_location_scope on gba.construction_commitments
    as restrictive to gba_runtime
    using (gba.current_location_id() is null or exists (
        select 1 from gba.construction_projects p
        where p.tenant_id = construction_commitments.tenant_id
          and p.id = construction_commitments.project_id))
    with check (gba.current_location_id() is null or exists (
        select 1 from gba.construction_projects p
        where p.tenant_id = construction_commitments.tenant_id
          and p.id = construction_commitments.project_id));
create policy construction_commitment_versions_location_scope
    on gba.construction_commitment_versions
    as restrictive to gba_runtime
    using (gba.current_location_id() is null or exists (
        select 1 from gba.construction_projects p
        where p.tenant_id = construction_commitment_versions.tenant_id
          and p.id = construction_commitment_versions.project_id))
    with check (gba.current_location_id() is null or exists (
        select 1 from gba.construction_projects p
        where p.tenant_id = construction_commitment_versions.tenant_id
          and p.id = construction_commitment_versions.project_id));
create policy construction_commitment_lines_location_scope on gba.construction_commitment_lines
    as restrictive to gba_runtime
    using (gba.current_location_id() is null or exists (
        select 1 from gba.construction_projects p
        where p.tenant_id = construction_commitment_lines.tenant_id
          and p.id = construction_commitment_lines.project_id))
    with check (gba.current_location_id() is null or exists (
        select 1 from gba.construction_projects p
        where p.tenant_id = construction_commitment_lines.tenant_id
          and p.id = construction_commitment_lines.project_id));
