-- O6b (package O, BUILD-01): warranty claims after the final acceptance, their state as insert-only
-- events, and their repair cost as O3b cost links assigned to a claim. ADR-0035,
-- docs/plan/PACKAGE_O6B_DESIGN_2026-11-02.md. The O3b cost-link guard is not changed: a repair only
-- labels a link, so each fact still counts once. All three tables are insert-only.
create table gba.construction_warranty_claims (
    tenant_id uuid not null references gba.tenants(id),
    project_id uuid not null,
    number integer not null constraint construction_warranty_claims_number_check
        check (number between 1 and 1000000),
    title text not null constraint construction_warranty_claims_title_check
        check (length(btrim(title)) between 1 and 120 and title !~ '[[:cntrl:]]'),
    description text constraint construction_warranty_claims_description_check
        check (description is null or length(btrim(description)) between 1 and 4000),
    phase text constraint construction_warranty_claims_phase_shape_check
        check (phase is null or (length(btrim(phase)) between 1 and 64 and phase !~ '[[:cntrl:]]')),
    location text constraint construction_warranty_claims_location_check
        check (location is null or (length(btrim(location)) between 1 and 200
            and location !~ '[[:cntrl:]]')),
    reported_by text not null constraint construction_warranty_claims_reported_by_check
        check (length(btrim(reported_by)) between 1 and 200 and reported_by !~ '[[:cntrl:]]'),
    raised_on date not null constraint construction_warranty_claims_floor_check
        check (raised_on >= date '2000-01-01'),
    created_by uuid not null references gba.users(id),
    created_at timestamptz not null default now(),
    primary key (tenant_id, project_id, number),
    foreign key (tenant_id, project_id) references gba.construction_contracts (tenant_id, project_id)
);
-- A move of a claim's state; a claim starts open. Rejecting and reopening carry a note.
create table gba.construction_warranty_claim_events (
    tenant_id uuid not null references gba.tenants(id),
    project_id uuid not null,
    claim integer not null,
    sequence integer not null constraint construction_warranty_claim_events_sequence_range_check
        check (sequence between 1 and 10000),
    state text not null constraint construction_warranty_claim_events_state_check
        check (state in ('open', 'repaired', 'closed', 'rejected')),
    note text,
    created_by uuid not null references gba.users(id),
    created_at timestamptz not null default now(),
    constraint construction_warranty_claim_events_note_check
        check ((note is null or length(btrim(note)) between 1 and 1000)
            and (state not in ('open', 'rejected') or note is not null)),
    primary key (tenant_id, project_id, claim, sequence),
    foreign key (tenant_id, project_id, claim)
        references gba.construction_warranty_claims (tenant_id, project_id, number)
);
-- One claim per cost link: the link's cost is the repair of that claim while the link counts.
create table gba.construction_warranty_repairs (
    tenant_id uuid not null references gba.tenants(id),
    project_id uuid not null,
    cost_link integer not null,
    claim integer not null,
    created_by uuid not null references gba.users(id),
    created_at timestamptz not null default now(),
    primary key (tenant_id, project_id, cost_link),
    foreign key (tenant_id, project_id, cost_link)
        references gba.construction_cost_links (tenant_id, project_id, number),
    foreign key (tenant_id, project_id, claim)
        references gba.construction_warranty_claims (tenant_id, project_id, number)
);
create index construction_warranty_repairs_claim
    on gba.construction_warranty_repairs (tenant_id, project_id, claim);

-- The latest state of a claim (open until its first event).
create function gba.construction_warranty_claim_state(p_tenant uuid, p_project uuid, p_claim integer)
returns text language sql stable as $$
    select coalesce((
        select e.state from gba.construction_warranty_claim_events e
         where e.tenant_id = p_tenant and e.project_id = p_project and e.claim = p_claim
         order by e.sequence desc limit 1), 'open')
$$;
revoke all on function gba.construction_warranty_claim_state(uuid, uuid, integer) from public;
grant execute on function gba.construction_warranty_claim_state(uuid, uuid, integer) to gba_runtime;

-- Claims follow each other under the project lock; a site date not after today, inside the warranty
-- period of the final acceptance (from its date to the warranty end); a phase of the budget.
create function gba.guard_construction_warranty_claim() returns trigger language plpgsql as $$
declare
    final record;
begin
    perform 1 from gba.construction_projects p
     where p.tenant_id = new.tenant_id and p.id = new.project_id for update;
    if new.number <> coalesce((
        select max(c.number) from gba.construction_warranty_claims c
        where c.tenant_id = new.tenant_id and c.project_id = new.project_id), 0) + 1 then
        raise exception using errcode = 'check_violation',
            constraint = 'construction_warranty_claims_sequence_check',
            message = 'a claim follows the latest one';
    end if;
    if new.raised_on > (
        select (now() at time zone p.time_zone)::date from gba.construction_projects p
        where p.tenant_id = new.tenant_id and p.id = new.project_id) then
        raise exception using errcode = 'check_violation',
            constraint = 'construction_warranty_claims_date_check',
            message = 'a claim is not dated after today on the site';
    end if;
    select a.accepted_on, a.warranty_ends_on into final from gba.construction_acceptances a
     where a.tenant_id = new.tenant_id and a.project_id = new.project_id and a.scope = 'final';
    if not found or new.raised_on < final.accepted_on or new.raised_on > final.warranty_ends_on then
        raise exception using errcode = 'check_violation',
            constraint = 'construction_warranty_claims_warranty_check',
            message = 'a claim is raised inside the warranty period';
    end if;
    if new.phase is not null
       and not gba.construction_budget_has_phase(new.tenant_id, new.project_id, new.phase) then
        raise exception using errcode = 'check_violation',
            constraint = 'construction_warranty_claims_phase_check',
            message = 'a claim names a phase of the budget';
    end if;
    return new;
end;
$$;
revoke all on function gba.guard_construction_warranty_claim() from public;
create trigger construction_warranty_claims_guard
    before insert on gba.construction_warranty_claims
    for each row execute function gba.guard_construction_warranty_claim();

-- Events follow each other under the project lock and move the state as it allows.
create function gba.guard_construction_warranty_claim_event() returns trigger
language plpgsql as $$
begin
    perform 1 from gba.construction_projects p
     where p.tenant_id = new.tenant_id and p.id = new.project_id for update;
    if new.sequence <> coalesce((
        select max(e.sequence) from gba.construction_warranty_claim_events e
        where e.tenant_id = new.tenant_id and e.project_id = new.project_id
          and e.claim = new.claim), 0) + 1 then
        raise exception using errcode = 'check_violation',
            constraint = 'construction_warranty_claim_events_sequence_check',
            message = 'an event follows the latest one of its claim';
    end if;
    if (gba.construction_warranty_claim_state(new.tenant_id, new.project_id, new.claim), new.state)
       not in (('open', 'repaired'), ('open', 'rejected'), ('repaired', 'closed'),
               ('repaired', 'open')) then
        raise exception using errcode = 'check_violation',
            constraint = 'construction_warranty_claim_events_transition_check',
            message = 'a claim moves only as its state allows';
    end if;
    return new;
end;
$$;
revoke all on function gba.guard_construction_warranty_claim_event() from public;
create trigger construction_warranty_claim_events_guard
    before insert on gba.construction_warranty_claim_events
    for each row execute function gba.guard_construction_warranty_claim_event();

-- A repair names a cost link of the project that still counts and a claim that is open or repaired.
create function gba.guard_construction_warranty_repair() returns trigger language plpgsql as $$
begin
    perform 1 from gba.construction_projects p
     where p.tenant_id = new.tenant_id and p.id = new.project_id for update;
    if not exists (
        select 1 from gba.construction_cost_links c
        where c.tenant_id = new.tenant_id and c.project_id = new.project_id
          and c.number = new.cost_link)
       or exists (
        select 1 from gba.construction_cost_reversals r
        where r.tenant_id = new.tenant_id and r.project_id = new.project_id
          and r.number = new.cost_link) then
        raise exception using errcode = 'check_violation',
            constraint = 'construction_warranty_repairs_link_check',
            message = 'a repair names a cost link of the project that still counts';
    end if;
    if not exists (
        select 1 from gba.construction_warranty_claims c
        where c.tenant_id = new.tenant_id and c.project_id = new.project_id
          and c.number = new.claim)
       or gba.construction_warranty_claim_state(new.tenant_id, new.project_id, new.claim)
            not in ('open', 'repaired') then
        raise exception using errcode = 'check_violation',
            constraint = 'construction_warranty_repairs_claim_check',
            message = 'a repair names a claim that is open or repaired';
    end if;
    return new;
end;
$$;
revoke all on function gba.guard_construction_warranty_repair() from public;
create trigger construction_warranty_repairs_guard
    before insert on gba.construction_warranty_repairs
    for each row execute function gba.guard_construction_warranty_repair();

-- Writes need the construction module (ADR-0019 gate).
create trigger construction_warranty_claims_module_gate
    before insert on gba.construction_warranty_claims
    for each row execute function gba.require_enabled_module('construction');
create trigger construction_warranty_claim_events_module_gate
    before insert on gba.construction_warranty_claim_events
    for each row execute function gba.require_enabled_module('construction');
create trigger construction_warranty_repairs_module_gate
    before insert on gba.construction_warranty_repairs
    for each row execute function gba.require_enabled_module('construction');

alter table gba.construction_warranty_claims enable row level security;
alter table gba.construction_warranty_claims force row level security;
alter table gba.construction_warranty_claim_events enable row level security;
alter table gba.construction_warranty_claim_events force row level security;
alter table gba.construction_warranty_repairs enable row level security;
alter table gba.construction_warranty_repairs force row level security;
create policy construction_warranty_claims_tenant_isolation on gba.construction_warranty_claims
    using (tenant_id = gba.current_tenant_id())
    with check (tenant_id = gba.current_tenant_id());
create policy construction_warranty_claim_events_tenant_isolation
    on gba.construction_warranty_claim_events
    using (tenant_id = gba.current_tenant_id())
    with check (tenant_id = gba.current_tenant_id());
create policy construction_warranty_repairs_tenant_isolation on gba.construction_warranty_repairs
    using (tenant_id = gba.current_tenant_id())
    with check (tenant_id = gba.current_tenant_id());
grant select, insert on gba.construction_warranty_claims, gba.construction_warranty_claim_events,
    gba.construction_warranty_repairs to gba_runtime;

-- Construction branch scope:
create policy construction_warranty_claims_location_scope on gba.construction_warranty_claims
    as restrictive to gba_runtime
    using (gba.current_location_id() is null or exists (
        select 1 from gba.construction_projects p
        where p.tenant_id = construction_warranty_claims.tenant_id
          and p.id = construction_warranty_claims.project_id))
    with check (gba.current_location_id() is null or exists (
        select 1 from gba.construction_projects p
        where p.tenant_id = construction_warranty_claims.tenant_id
          and p.id = construction_warranty_claims.project_id));
create policy construction_warranty_claim_events_location_scope
    on gba.construction_warranty_claim_events
    as restrictive to gba_runtime
    using (gba.current_location_id() is null or exists (
        select 1 from gba.construction_projects p
        where p.tenant_id = construction_warranty_claim_events.tenant_id
          and p.id = construction_warranty_claim_events.project_id))
    with check (gba.current_location_id() is null or exists (
        select 1 from gba.construction_projects p
        where p.tenant_id = construction_warranty_claim_events.tenant_id
          and p.id = construction_warranty_claim_events.project_id));
create policy construction_warranty_repairs_location_scope on gba.construction_warranty_repairs
    as restrictive to gba_runtime
    using (gba.current_location_id() is null or exists (
        select 1 from gba.construction_projects p
        where p.tenant_id = construction_warranty_repairs.tenant_id
          and p.id = construction_warranty_repairs.project_id))
    with check (gba.current_location_id() is null or exists (
        select 1 from gba.construction_projects p
        where p.tenant_id = construction_warranty_repairs.tenant_id
          and p.id = construction_warranty_repairs.project_id));
