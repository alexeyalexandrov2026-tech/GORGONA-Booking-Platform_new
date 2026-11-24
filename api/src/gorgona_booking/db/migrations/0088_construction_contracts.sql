-- O2 (package O, BUILD-01): the construction contract and change orders. ADR-0035,
-- docs/plan/PACKAGE_O2_DESIGN_2026-10-30.md. The contract is the accepted proposal (the frozen original);
-- change orders, their lines and their one decision are insert-only; sums are derived on read.
create table gba.construction_contracts (
    tenant_id uuid not null references gba.tenants(id),
    project_id uuid not null,
    version integer not null,
    signatory text not null constraint construction_contracts_signatory_check
        check (length(btrim(signatory)) between 1 and 200 and signatory !~ '[[:cntrl:]]'),
    source text not null constraint construction_contracts_source_check
        check (source in ('platform', 'paper', 'email')),
    note text constraint construction_contracts_note_check
        check (note is null or length(note) between 1 and 1000),
    recorded_by uuid not null references gba.users(id),
    recorded_at timestamptz not null default now(),
    primary key (tenant_id, project_id),
    foreign key (tenant_id, project_id, version)
        references gba.construction_estimate_versions (tenant_id, project_id, version)
);
create table gba.construction_change_orders (
    tenant_id uuid not null references gba.tenants(id),
    project_id uuid not null,
    number integer not null constraint construction_change_orders_number_check
        check (number between 1 and 100000),
    title text not null constraint construction_change_orders_title_check
        check (length(btrim(title)) between 1 and 200 and title !~ '[[:cntrl:]]'),
    reason text constraint construction_change_orders_reason_check
        check (reason is null or length(reason) between 1 and 1000),
    days_delta integer not null constraint construction_change_orders_days_check
        check (days_delta between -3650 and 3650),
    created_by uuid not null references gba.users(id),
    created_at timestamptz not null default now(),
    primary key (tenant_id, project_id, number),
    foreign key (tenant_id, project_id) references gba.construction_contracts (tenant_id, project_id)
);
create table gba.construction_change_order_lines (
    tenant_id uuid not null references gba.tenants(id),
    project_id uuid not null,
    number integer not null,
    position smallint not null constraint construction_change_order_lines_position_check
        check (position between 1 and 200),
    action text not null constraint construction_change_order_lines_action_check
        check (action in ('add', 'remove')),
    contract_position smallint constraint construction_change_order_lines_contract_position_check
        check (contract_position between 1 and 500),
    kind text constraint construction_change_order_lines_kind_check
        check (kind in ('material', 'labor', 'equipment', 'subcontract', 'other')),
    description text constraint construction_change_order_lines_description_check
        check (length(btrim(description)) between 1 and 500),
    phase text constraint construction_change_order_lines_phase_check
        check (length(btrim(phase)) between 1 and 64 and phase !~ '[[:cntrl:]]'),
    quantity numeric(13, 4) not null constraint construction_change_order_lines_quantity_check
        check (quantity > 0),
    unit text constraint construction_change_order_lines_unit_check
        check (length(btrim(unit)) between 1 and 16 and unit !~ '[[:cntrl:]]'),
    unit_cost_minor bigint constraint construction_change_order_lines_cost_check
        check (unit_cost_minor between 0 and 1000000000000),
    unit_price_minor bigint constraint construction_change_order_lines_price_check
        check (unit_price_minor between 0 and 1000000000000),
    material_id uuid,
    primary key (tenant_id, project_id, number, position),
    foreign key (tenant_id, project_id, number)
        references gba.construction_change_orders (tenant_id, project_id, number),
    foreign key (tenant_id, material_id) references gba.stock_items (tenant_id, id),
    -- An added line carries its own scope; a removal names a contract line and a quantity only.
    constraint construction_change_order_lines_shape_check check (
        (action = 'add' and contract_position is null and kind is not null
            and description is not null and phase is not null and unit is not null
            and unit_cost_minor is not null and unit_price_minor is not null)
        or (action = 'remove' and contract_position is not null and kind is null
            and description is null and phase is null and unit is null
            and unit_cost_minor is null and unit_price_minor is null and material_id is null))
);
create table gba.construction_change_order_decisions (
    tenant_id uuid not null references gba.tenants(id),
    project_id uuid not null,
    number integer not null,
    decision text not null constraint construction_change_order_decisions_decision_check
        check (decision in ('approved', 'rejected', 'withdrawn')),
    source text constraint construction_change_order_decisions_source_check
        check (source in ('platform', 'paper', 'email')),
    note text constraint construction_change_order_decisions_note_check
        check (note is null or length(note) between 1 and 1000),
    decided_by uuid not null references gba.users(id),
    decided_at timestamptz not null default now(),
    primary key (tenant_id, project_id, number),
    foreign key (tenant_id, project_id, number)
        references gba.construction_change_orders (tenant_id, project_id, number),
    -- The customer's answer has a source; a withdrawal by the business has none.
    constraint construction_change_order_decisions_answer_check
        check ((decision = 'withdrawn') = (source is null))
);

-- O1 guards, replaced: after the contract the customer stays and no estimate version is added.
create or replace function gba.guard_construction_project() returns trigger language plpgsql as $$
begin
    if not exists (select 1 from pg_catalog.pg_timezone_names z where z.name = new.time_zone) then
        raise exception using errcode = 'check_violation',
            constraint = 'construction_projects_time_zone_check',
            message = 'a project names a known time zone';
    end if;
    if tg_op = 'UPDATE' and new.currency <> old.currency and exists (
        select 1 from gba.construction_estimate_versions v
        where v.tenant_id = new.tenant_id and v.project_id = new.id
    ) then
        raise exception using errcode = 'check_violation',
            constraint = 'construction_projects_currency_check',
            message = 'a project with an estimate keeps its currency';
    end if;
    if tg_op = 'UPDATE' and new.customer_id <> old.customer_id and exists (
        select 1 from gba.construction_contracts k
        where k.tenant_id = new.tenant_id and k.project_id = new.id
    ) then
        raise exception using errcode = 'check_violation',
            constraint = 'construction_projects_customer_check',
            message = 'a project with a contract keeps its customer';
    end if;
    return new;
end;
$$;

create or replace function gba.guard_construction_estimate_version() returns trigger
language plpgsql as $$
begin
    if tg_op = 'INSERT' then
        if exists (
            select 1 from gba.construction_contracts k
            where k.tenant_id = new.tenant_id and k.project_id = new.project_id
        ) then
            raise exception using errcode = 'check_violation',
                constraint = 'construction_estimate_versions_contract_check',
                message = 'a project with a contract takes no new estimate version';
        end if;
        if new.proposed_at is not null or new.version <> coalesce((
            select max(v.version) from gba.construction_estimate_versions v
            where v.tenant_id = new.tenant_id and v.project_id = new.project_id), 0) + 1 then
            raise exception using errcode = 'check_violation',
                constraint = 'construction_estimate_versions_sequence_check',
                message = 'an estimate version follows the latest one, unproposed';
        end if;
        return new;
    end if;
    if old.proposed_at is not null or new.proposed_at is null
       or (new.tenant_id, new.project_id, new.version, new.note, new.created_by, new.created_at)
          is distinct from
          (old.tenant_id, old.project_id, old.version, old.note, old.created_by, old.created_at)
       or exists (
           select 1 from gba.construction_estimate_versions v
           where v.tenant_id = new.tenant_id and v.project_id = new.project_id
             and v.version > new.version) then
        raise exception using errcode = 'check_violation',
            constraint = 'construction_estimate_versions_proposal_check',
            message = 'only the latest estimate version is proposed, once';
    end if;
    return new;
end;
$$;

-- The contract is the latest version, proposed.
create function gba.guard_construction_contract() returns trigger language plpgsql as $$
begin
    if not exists (
        select 1 from gba.construction_estimate_versions v
        where v.tenant_id = new.tenant_id and v.project_id = new.project_id
          and v.version = new.version and v.proposed_at is not null
    ) or exists (
        select 1 from gba.construction_estimate_versions v
        where v.tenant_id = new.tenant_id and v.project_id = new.project_id
          and v.version > new.version
    ) then
        raise exception using errcode = 'check_violation',
            constraint = 'construction_contracts_proposal_check',
            message = 'the contract is the latest proposed estimate version';
    end if;
    return new;
end;
$$;
revoke all on function gba.guard_construction_contract() from public;
create trigger construction_contracts_guard
    before insert on gba.construction_contracts
    for each row execute function gba.guard_construction_contract();

-- Change orders follow each other.
create function gba.guard_construction_change_order() returns trigger language plpgsql as $$
begin
    if new.number <> coalesce((
        select max(o.number) from gba.construction_change_orders o
        where o.tenant_id = new.tenant_id and o.project_id = new.project_id), 0) + 1 then
        raise exception using errcode = 'check_violation',
            constraint = 'construction_change_orders_sequence_check',
            message = 'a change order follows the latest one';
    end if;
    return new;
end;
$$;
revoke all on function gba.guard_construction_change_order() from public;
create trigger construction_change_orders_guard
    before insert on gba.construction_change_orders
    for each row execute function gba.guard_construction_change_order();

-- Lines are written with their change order, before a decision; a removal names a contract line
-- and never takes more than that line holds after the approved removals.
create function gba.guard_construction_change_order_line() returns trigger language plpgsql as $$
declare
    contracted numeric;
begin
    if not exists (
        select 1 from gba.construction_change_orders o
        where o.tenant_id = new.tenant_id and o.project_id = new.project_id
          and o.number = new.number and o.created_at = now()
    ) or exists (
        select 1 from gba.construction_change_order_decisions d
        where d.tenant_id = new.tenant_id and d.project_id = new.project_id
          and d.number = new.number
    ) then
        raise exception using errcode = 'check_violation',
            constraint = 'construction_change_order_lines_order_check',
            message = 'change order lines are written with their change order';
    end if;
    if new.action = 'remove' then
        select l.quantity into contracted
        from gba.construction_contracts k
        join gba.construction_estimate_lines l
          on l.tenant_id = k.tenant_id and l.project_id = k.project_id and l.version = k.version
        where k.tenant_id = new.tenant_id and k.project_id = new.project_id
          and l.position = new.contract_position;
        if not found then
            raise exception using errcode = 'check_violation',
                constraint = 'construction_change_order_lines_contract_check',
                message = 'a removal names a line of the contract';
        end if;
        if new.quantity + coalesce((
            select sum(o.quantity) from gba.construction_change_order_lines o
            where o.tenant_id = new.tenant_id and o.project_id = new.project_id
              and o.action = 'remove' and o.contract_position = new.contract_position
              and (o.number = new.number or exists (
                  select 1 from gba.construction_change_order_decisions d
                  where d.tenant_id = o.tenant_id and d.project_id = o.project_id
                    and d.number = o.number and d.decision = 'approved'))), 0) > contracted then
            raise exception using errcode = 'check_violation',
                constraint = 'construction_change_order_lines_scope_check',
                message = 'a removal never takes more than the contract line holds';
        end if;
    end if;
    return new;
end;
$$;
revoke all on function gba.guard_construction_change_order_line() from public;
create trigger construction_change_order_lines_guard
    before insert on gba.construction_change_order_lines
    for each row execute function gba.guard_construction_change_order_line();

-- An approval never removes more than a contract line holds after the earlier approvals.
create function gba.guard_construction_change_order_decision() returns trigger language plpgsql as $$
begin
    if new.decision = 'approved' and exists (
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
    return new;
end;
$$;
revoke all on function gba.guard_construction_change_order_decision() from public;
create trigger construction_change_order_decisions_guard
    before insert on gba.construction_change_order_decisions
    for each row execute function gba.guard_construction_change_order_decision();

-- Writes need the construction module (ADR-0019 gate).
create trigger construction_contracts_module_gate
    before insert on gba.construction_contracts
    for each row execute function gba.require_enabled_module('construction');
create trigger construction_change_orders_module_gate
    before insert on gba.construction_change_orders
    for each row execute function gba.require_enabled_module('construction');
create trigger construction_change_order_decisions_module_gate
    before insert on gba.construction_change_order_decisions
    for each row execute function gba.require_enabled_module('construction');

alter table gba.construction_contracts enable row level security;
alter table gba.construction_contracts force row level security;
alter table gba.construction_change_orders enable row level security;
alter table gba.construction_change_orders force row level security;
alter table gba.construction_change_order_lines enable row level security;
alter table gba.construction_change_order_lines force row level security;
alter table gba.construction_change_order_decisions enable row level security;
alter table gba.construction_change_order_decisions force row level security;
create policy construction_contracts_tenant_isolation on gba.construction_contracts
    using (tenant_id = gba.current_tenant_id())
    with check (tenant_id = gba.current_tenant_id());
create policy construction_change_orders_tenant_isolation on gba.construction_change_orders
    using (tenant_id = gba.current_tenant_id())
    with check (tenant_id = gba.current_tenant_id());
create policy construction_change_order_lines_tenant_isolation
    on gba.construction_change_order_lines
    using (tenant_id = gba.current_tenant_id())
    with check (tenant_id = gba.current_tenant_id());
create policy construction_change_order_decisions_tenant_isolation
    on gba.construction_change_order_decisions
    using (tenant_id = gba.current_tenant_id())
    with check (tenant_id = gba.current_tenant_id());
grant select, insert on gba.construction_contracts, gba.construction_change_orders,
    gba.construction_change_order_lines, gba.construction_change_order_decisions to gba_runtime;

-- Construction branch scope:
create policy construction_contracts_location_scope on gba.construction_contracts
    as restrictive to gba_runtime
    using (gba.current_location_id() is null or exists (
        select 1 from gba.construction_projects p
        where p.tenant_id = construction_contracts.tenant_id
          and p.id = construction_contracts.project_id))
    with check (gba.current_location_id() is null or exists (
        select 1 from gba.construction_projects p
        where p.tenant_id = construction_contracts.tenant_id
          and p.id = construction_contracts.project_id));
create policy construction_change_orders_location_scope on gba.construction_change_orders
    as restrictive to gba_runtime
    using (gba.current_location_id() is null or exists (
        select 1 from gba.construction_projects p
        where p.tenant_id = construction_change_orders.tenant_id
          and p.id = construction_change_orders.project_id))
    with check (gba.current_location_id() is null or exists (
        select 1 from gba.construction_projects p
        where p.tenant_id = construction_change_orders.tenant_id
          and p.id = construction_change_orders.project_id));
create policy construction_change_order_lines_location_scope
    on gba.construction_change_order_lines
    as restrictive to gba_runtime
    using (gba.current_location_id() is null or exists (
        select 1 from gba.construction_projects p
        where p.tenant_id = construction_change_order_lines.tenant_id
          and p.id = construction_change_order_lines.project_id))
    with check (gba.current_location_id() is null or exists (
        select 1 from gba.construction_projects p
        where p.tenant_id = construction_change_order_lines.tenant_id
          and p.id = construction_change_order_lines.project_id));
create policy construction_change_order_decisions_location_scope
    on gba.construction_change_order_decisions
    as restrictive to gba_runtime
    using (gba.current_location_id() is null or exists (
        select 1 from gba.construction_projects p
        where p.tenant_id = construction_change_order_decisions.tenant_id
          and p.id = construction_change_order_decisions.project_id))
    with check (gba.current_location_id() is null or exists (
        select 1 from gba.construction_projects p
        where p.tenant_id = construction_change_order_decisions.tenant_id
          and p.id = construction_change_order_decisions.project_id));
