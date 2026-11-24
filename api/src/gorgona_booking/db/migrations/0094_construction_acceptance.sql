-- O6a (package O, BUILD-01): stage and final acceptance, retainage release. ADR-0035,
-- docs/plan/PACKAGE_O6A_DESIGN_2026-11-02.md. Everything is insert-only and needs the contract. A phase
-- or the whole project is accepted once, only when its work is finished and no open or fixed item
-- blocks it; the final acceptance needs the contract billed in full and records the warranty period.
-- Accepted work is closed; retainage is released once per acceptance by an amount the database checks.
create table gba.construction_acceptances (
    tenant_id uuid not null references gba.tenants(id),
    project_id uuid not null,
    number integer not null constraint construction_acceptances_number_check
        check (number between 1 and 1000),
    scope text not null constraint construction_acceptances_scope_check
        check (scope in ('phase', 'final')),
    phase text constraint construction_acceptances_phase_text_check
        check (phase is null or (length(btrim(phase)) between 1 and 64 and phase !~ '[[:cntrl:]]')),
    accepted_on date not null constraint construction_acceptances_floor_check
        check (accepted_on >= date '2000-01-01'),
    signatory text not null constraint construction_acceptances_signatory_check
        check (length(btrim(signatory)) between 1 and 200 and signatory !~ '[[:cntrl:]]'),
    source text not null constraint construction_acceptances_source_check
        check (source in ('platform', 'paper', 'email')),
    note text constraint construction_acceptances_note_check
        check (note is null or length(btrim(note)) between 1 and 1000),
    warranty_ends_on date,
    recorded_by uuid not null references gba.users(id),
    recorded_at timestamptz not null default now(),
    primary key (tenant_id, project_id, number),
    foreign key (tenant_id, project_id) references gba.construction_contracts (tenant_id, project_id),
    -- A phase acceptance names its phase; the final one names none and starts the warranty.
    constraint construction_acceptances_shape_check check ((scope = 'phase') = (phase is not null)),
    constraint construction_acceptances_warranty_check check (
        (scope = 'phase' and warranty_ends_on is null)
        or (scope = 'final' and warranty_ends_on > accepted_on
            and warranty_ends_on <= accepted_on + interval '10 years'
            and warranty_ends_on <= date '2100-12-31'))
);
-- Each phase once and the project once finally.
create unique index construction_acceptances_scope_key
    on gba.construction_acceptances (tenant_id, project_id, coalesce(phase, ''));
create table gba.construction_retainage_releases (
    tenant_id uuid not null references gba.tenants(id),
    project_id uuid not null,
    acceptance integer not null,
    released_on date not null constraint construction_retainage_releases_floor_check
        check (released_on >= date '2000-01-01'),
    amount_minor bigint not null constraint construction_retainage_releases_positive_check
        check (amount_minor > 0),
    note text constraint construction_retainage_releases_note_check
        check (note is null or length(btrim(note)) between 1 and 1000),
    recorded_by uuid not null references gba.users(id),
    recorded_at timestamptz not null default now(),
    primary key (tenant_id, project_id, acceptance),
    foreign key (tenant_id, project_id, acceptance)
        references gba.construction_acceptances (tenant_id, project_id, number)
);

-- Every line of the budget with its phase: the contract lines and the added lines of approved changes.
create function gba.construction_budget_line_phases(p_tenant uuid, p_project uuid)
returns table (change_order integer, budget_position smallint, phase text)
language sql stable as $$
    select null::integer, l.position, l.phase
      from gba.construction_contracts k
      join gba.construction_estimate_lines l
        on l.tenant_id = k.tenant_id and l.project_id = k.project_id and l.version = k.version
     where k.tenant_id = p_tenant and k.project_id = p_project
    union all
    select o.number, o.position, o.phase
      from gba.construction_change_order_lines o
      join gba.construction_change_order_decisions d
        on d.tenant_id = o.tenant_id and d.project_id = o.project_id
       and d.number = o.number and d.decision = 'approved'
     where o.tenant_id = p_tenant and o.project_id = p_project and o.action = 'add'
$$;
revoke all on function gba.construction_budget_line_phases(uuid, uuid) from public;
grant execute on function gba.construction_budget_line_phases(uuid, uuid) to gba_runtime;

-- The retainage held on one phase: for every pay application, the change of the phase's billed value
-- from the previous application times that application's rate, rounded down, summed.
create function gba.construction_phase_retained(p_tenant uuid, p_project uuid, p_phase text)
returns bigint language sql stable as $$
    with phased as (
        select b.change_order, b.budget_position
          from gba.construction_budget_line_phases(p_tenant, p_project) b
         where b.phase = p_phase
    ), billed as (
        select a.number, a.rate_bp, coalesce((
            select sum(l.value_to_date_minor)
              from gba.construction_pay_application_lines l
              join phased x
                on x.change_order is not distinct from l.change_order
               and x.budget_position = l.budget_position
             where l.tenant_id = a.tenant_id and l.project_id = a.project_id
               and l.number = a.number), 0) as value_minor
          from gba.construction_pay_applications a
         where a.tenant_id = p_tenant and a.project_id = p_project
    )
    select coalesce(sum(floor(s.step * s.rate_bp / 10000)), 0)::bigint
      from (select b.rate_bp,
                   (b.value_minor - coalesce(lag(b.value_minor) over (order by b.number), 0))::numeric
                       as step
              from billed b) s
$$;
revoke all on function gba.construction_phase_retained(uuid, uuid, text) from public;
grant execute on function gba.construction_phase_retained(uuid, uuid, text) to gba_runtime;

-- An acceptance follows the previous one under the project lock and is checked as a whole.
create function gba.guard_construction_acceptance() returns trigger language plpgsql as $$
begin
    perform 1 from gba.construction_projects p
     where p.tenant_id = new.tenant_id and p.id = new.project_id for update;
    if new.number <> coalesce((
        select max(a.number) from gba.construction_acceptances a
        where a.tenant_id = new.tenant_id and a.project_id = new.project_id), 0) + 1 then
        raise exception using errcode = 'check_violation',
            constraint = 'construction_acceptances_sequence_check',
            message = 'an acceptance follows the latest one';
    end if;
    if exists (
        select 1 from gba.construction_acceptances a
        where a.tenant_id = new.tenant_id and a.project_id = new.project_id
          and (a.scope = 'final' or (new.scope = 'phase' and a.phase = new.phase))
    ) then
        raise exception using errcode = 'check_violation',
            constraint = 'construction_acceptances_accepted_check',
            message = 'a scope is accepted once and nothing after the final acceptance';
    end if;
    if new.accepted_on > (
        select (now() at time zone p.time_zone)::date from gba.construction_projects p
        where p.tenant_id = new.tenant_id and p.id = new.project_id) then
        raise exception using errcode = 'check_violation',
            constraint = 'construction_acceptances_date_check',
            message = 'an acceptance is not dated after today on the site';
    end if;
    if new.scope = 'phase'
       and not gba.construction_budget_has_phase(new.tenant_id, new.project_id, new.phase) then
        raise exception using errcode = 'check_violation',
            constraint = 'construction_acceptances_phase_check',
            message = 'a phase acceptance names a phase of the budget';
    end if;
    if exists (
        select 1 from gba.construction_budget_line_phases(new.tenant_id, new.project_id) b
         where (new.scope = 'final' or b.phase = new.phase)
           and gba.construction_contracted_quantity(
                new.tenant_id, new.project_id, b.change_order, b.budget_position) > 0
           and not exists (
                select 1 from (
                    select m.measured_on, m.quantity_to_date
                      from gba.construction_progress_measurements m
                     where m.tenant_id = new.tenant_id and m.project_id = new.project_id
                       and m.change_order is not distinct from b.change_order
                       and m.budget_position = b.budget_position
                     order by m.number desc limit 1) latest
                 where latest.measured_on <= new.accepted_on
                   and latest.quantity_to_date >= gba.construction_contracted_quantity(
                        new.tenant_id, new.project_id, b.change_order, b.budget_position))
    ) then
        raise exception using errcode = 'check_violation',
            constraint = 'construction_acceptances_completed_check',
            message = 'only finished work, measured by the acceptance date, is accepted';
    end if;
    if exists (
        select 1 from gba.construction_quality_items i
         where i.tenant_id = new.tenant_id and i.project_id = new.project_id
           and (new.scope = 'final' or i.phase = new.phase)
           and coalesce((
                select e.state from gba.construction_quality_item_events e
                 where e.tenant_id = i.tenant_id and e.project_id = i.project_id
                   and e.item = i.number
                 order by e.sequence desc limit 1), 'open') in ('open', 'fixed')
    ) then
        raise exception using errcode = 'check_violation',
            constraint = 'construction_acceptances_items_check',
            message = 'open or fixed items block the acceptance';
    end if;
    if new.scope = 'final' and coalesce((
        select a.billed_to_date_minor from gba.construction_pay_applications a
        where a.tenant_id = new.tenant_id and a.project_id = new.project_id
        order by a.number desc limit 1), 0)
        <> gba.construction_contract_minor(new.tenant_id, new.project_id) then
        raise exception using errcode = 'check_violation',
            constraint = 'construction_acceptances_billed_check',
            message = 'the final acceptance needs the contract billed in full';
    end if;
    return new;
end;
$$;
revoke all on function gba.guard_construction_acceptance() from public;
create trigger construction_acceptances_guard
    before insert on gba.construction_acceptances
    for each row execute function gba.guard_construction_acceptance();

-- A release follows its acceptance once, under the project lock, by the amount the acceptance frees.
create function gba.guard_construction_retainage_release() returns trigger language plpgsql as $$
declare
    accepted record;
    latest integer;
    held bigint;
    expected bigint;
begin
    perform 1 from gba.construction_projects p
     where p.tenant_id = new.tenant_id and p.id = new.project_id for update;
    select a.scope, a.phase, a.accepted_on into accepted
      from gba.construction_acceptances a
     where a.tenant_id = new.tenant_id and a.project_id = new.project_id
       and a.number = new.acceptance;
    if not found then
        return new;  -- the foreign key refuses it
    end if;
    if exists (
        select 1 from gba.construction_retainage_releases r
          join gba.construction_acceptances a
            on a.tenant_id = r.tenant_id and a.project_id = r.project_id and a.number = r.acceptance
         where r.tenant_id = new.tenant_id and r.project_id = new.project_id
           and (r.acceptance = new.acceptance or a.scope = 'final')
    ) then
        raise exception using errcode = 'check_violation',
            constraint = 'construction_retainage_releases_released_check',
            message = 'retainage is released once per acceptance and nothing after the final release';
    end if;
    if new.released_on < accepted.accepted_on or new.released_on > (
        select (now() at time zone p.time_zone)::date from gba.construction_projects p
        where p.tenant_id = new.tenant_id and p.id = new.project_id) then
        raise exception using errcode = 'check_violation',
            constraint = 'construction_retainage_releases_date_check',
            message = 'a release is dated from its acceptance to today on the site';
    end if;
    select max(a.number) into latest from gba.construction_pay_applications a
     where a.tenant_id = new.tenant_id and a.project_id = new.project_id;
    if accepted.scope = 'phase' and exists (
        select 1 from gba.construction_budget_line_phases(new.tenant_id, new.project_id) b
         where b.phase = accepted.phase
           and gba.construction_contracted_quantity(
                new.tenant_id, new.project_id, b.change_order, b.budget_position) > coalesce((
                select l.quantity_to_date from gba.construction_pay_application_lines l
                 where l.tenant_id = new.tenant_id and l.project_id = new.project_id
                   and l.number = latest and l.change_order is not distinct from b.change_order
                   and l.budget_position = b.budget_position), 0)
    ) then
        raise exception using errcode = 'check_violation',
            constraint = 'construction_retainage_releases_billed_check',
            message = 'a phase''s retainage is released once the phase is billed in full';
    end if;
    held := coalesce((
        select sum(a.retained_minor) from gba.construction_pay_applications a
        where a.tenant_id = new.tenant_id and a.project_id = new.project_id), 0)
        - coalesce((
        select sum(r.amount_minor) from gba.construction_retainage_releases r
        where r.tenant_id = new.tenant_id and r.project_id = new.project_id), 0);
    expected := case when accepted.scope = 'final' then held
        else least(greatest(gba.construction_phase_retained(
            new.tenant_id, new.project_id, accepted.phase), 0), held) end;
    if new.amount_minor <> expected then
        raise exception using errcode = 'check_violation',
            constraint = 'construction_retainage_releases_amount_check',
            message = 'a release frees exactly the retainage its acceptance releases';
    end if;
    return new;
end;
$$;
revoke all on function gba.guard_construction_retainage_release() from public;
create trigger construction_retainage_releases_guard
    before insert on gba.construction_retainage_releases
    for each row execute function gba.guard_construction_retainage_release();

-- Accepted work is closed. These are new triggers beside the O4a, O2 and O5 guards, whose bodies stay
-- as 0093 left them; each takes the project lock first.
create function gba.guard_construction_accepted_measurement() returns trigger
language plpgsql as $$
begin
    perform 1 from gba.construction_projects p
     where p.tenant_id = new.tenant_id and p.id = new.project_id for update;
    if exists (
        select 1 from gba.construction_acceptances a
         where a.tenant_id = new.tenant_id and a.project_id = new.project_id
           and (a.scope = 'final' or a.phase = (
                select b.phase from gba.construction_budget_line_phases(
                    new.tenant_id, new.project_id) b
                 where b.change_order is not distinct from new.change_order
                   and b.budget_position = new.budget_position))
    ) then
        raise exception using errcode = 'check_violation',
            constraint = 'construction_progress_measurements_accepted_check',
            message = 'accepted work is closed for measurements';
    end if;
    return new;
end;
$$;
revoke all on function gba.guard_construction_accepted_measurement() from public;
create trigger construction_progress_measurements_acceptance
    before insert on gba.construction_progress_measurements
    for each row execute function gba.guard_construction_accepted_measurement();

create function gba.guard_construction_accepted_decision() returns trigger
language plpgsql as $$
begin
    if new.decision <> 'approved' then
        return new;
    end if;
    perform 1 from gba.construction_projects p
     where p.tenant_id = new.tenant_id and p.id = new.project_id for update;
    if exists (
        select 1 from gba.construction_acceptances a
         where a.tenant_id = new.tenant_id and a.project_id = new.project_id
           and (a.scope = 'final' or a.phase in (
                select coalesce(o.phase, l.phase)
                  from gba.construction_change_order_lines o
                  left join gba.construction_contracts k
                    on k.tenant_id = o.tenant_id and k.project_id = o.project_id
                  left join gba.construction_estimate_lines l
                    on l.tenant_id = k.tenant_id and l.project_id = k.project_id
                   and l.version = k.version and l.position = o.contract_position
                 where o.tenant_id = new.tenant_id and o.project_id = new.project_id
                   and o.number = new.number))
    ) then
        raise exception using errcode = 'check_violation',
            constraint = 'construction_change_order_decisions_accepted_check',
            message = 'an approval never changes accepted work';
    end if;
    return new;
end;
$$;
revoke all on function gba.guard_construction_accepted_decision() from public;
create trigger construction_change_order_decisions_acceptance
    before insert on gba.construction_change_order_decisions
    for each row execute function gba.guard_construction_accepted_decision();

create function gba.guard_construction_accepted_pay_application() returns trigger
language plpgsql as $$
begin
    perform 1 from gba.construction_projects p
     where p.tenant_id = new.tenant_id and p.id = new.project_id for update;
    if exists (
        select 1 from gba.construction_acceptances a
         where a.tenant_id = new.tenant_id and a.project_id = new.project_id
           and a.scope = 'final'
    ) then
        raise exception using errcode = 'check_violation',
            constraint = 'construction_pay_applications_accepted_check',
            message = 'the final acceptance closes billing';
    end if;
    return new;
end;
$$;
revoke all on function gba.guard_construction_accepted_pay_application() from public;
create trigger construction_pay_applications_acceptance
    before insert on gba.construction_pay_applications
    for each row execute function gba.guard_construction_accepted_pay_application();

-- Writes need the construction module (ADR-0019 gate).
create trigger construction_acceptances_module_gate
    before insert on gba.construction_acceptances
    for each row execute function gba.require_enabled_module('construction');
create trigger construction_retainage_releases_module_gate
    before insert on gba.construction_retainage_releases
    for each row execute function gba.require_enabled_module('construction');

alter table gba.construction_acceptances enable row level security;
alter table gba.construction_acceptances force row level security;
alter table gba.construction_retainage_releases enable row level security;
alter table gba.construction_retainage_releases force row level security;
create policy construction_acceptances_tenant_isolation on gba.construction_acceptances
    using (tenant_id = gba.current_tenant_id())
    with check (tenant_id = gba.current_tenant_id());
create policy construction_retainage_releases_tenant_isolation
    on gba.construction_retainage_releases
    using (tenant_id = gba.current_tenant_id())
    with check (tenant_id = gba.current_tenant_id());
grant select, insert on gba.construction_acceptances, gba.construction_retainage_releases
    to gba_runtime;

-- Construction branch scope:
create policy construction_acceptances_location_scope on gba.construction_acceptances
    as restrictive to gba_runtime
    using (gba.current_location_id() is null or exists (
        select 1 from gba.construction_projects p
        where p.tenant_id = construction_acceptances.tenant_id
          and p.id = construction_acceptances.project_id))
    with check (gba.current_location_id() is null or exists (
        select 1 from gba.construction_projects p
        where p.tenant_id = construction_acceptances.tenant_id
          and p.id = construction_acceptances.project_id));
create policy construction_retainage_releases_location_scope
    on gba.construction_retainage_releases
    as restrictive to gba_runtime
    using (gba.current_location_id() is null or exists (
        select 1 from gba.construction_projects p
        where p.tenant_id = construction_retainage_releases.tenant_id
          and p.id = construction_retainage_releases.project_id))
    with check (gba.current_location_id() is null or exists (
        select 1 from gba.construction_projects p
        where p.tenant_id = construction_retainage_releases.tenant_id
          and p.id = construction_retainage_releases.project_id));
