-- O5 (package O, BUILD-01): pay applications with retainage. ADR-0035,
-- docs/plan/PACKAGE_O5_DESIGN_2026-11-01.md. Everything is insert-only and needs the contract. A pay
-- application closes a billing period and bills completed value to date minus earlier billing; the
-- amount due is a FIN-03 receivable invoice and the retained amount a separate receivable accrual.
-- The database rechecks the period, the arithmetic, the rate, the contract sum and both documents.
create table gba.construction_retainage_rates (
    tenant_id uuid not null references gba.tenants(id),
    project_id uuid not null,
    revision integer not null constraint construction_retainage_rates_revision_check
        check (revision between 1 and 100000),
    rate_bp smallint not null constraint construction_retainage_rates_rate_check
        check (rate_bp between 0 and 5000),
    created_by uuid not null references gba.users(id),
    created_at timestamptz not null default now(),
    primary key (tenant_id, project_id, revision),
    foreign key (tenant_id, project_id) references gba.construction_contracts (tenant_id, project_id)
);
create table gba.construction_pay_applications (
    tenant_id uuid not null references gba.tenants(id),
    project_id uuid not null,
    number integer not null constraint construction_pay_applications_number_check
        check (number between 1 and 100000),
    period_end date not null constraint construction_pay_applications_floor_check
        check (period_end >= date '2000-01-01'),
    previous_billed_minor bigint not null,
    billed_to_date_minor bigint not null,
    this_period_minor bigint not null,
    rate_revision integer,
    rate_bp smallint not null constraint construction_pay_applications_rate_range_check
        check (rate_bp between 0 and 5000),
    retained_minor bigint not null,
    due_minor bigint not null,
    book_id uuid not null,
    invoice_document_id uuid not null,
    retainage_document_id uuid,
    created_by uuid not null references gba.users(id),
    created_at timestamptz not null default now(),
    primary key (tenant_id, project_id, number),
    unique (tenant_id, project_id, period_end),
    unique (tenant_id, book_id, invoice_document_id),
    unique (tenant_id, book_id, retainage_document_id),
    foreign key (tenant_id, project_id) references gba.construction_contracts (tenant_id, project_id),
    foreign key (tenant_id, project_id, rate_revision)
        references gba.construction_retainage_rates (tenant_id, project_id, revision),
    foreign key (tenant_id, book_id, invoice_document_id)
        references gba.financial_documents (tenant_id, book_id, id),
    foreign key (tenant_id, book_id, retainage_document_id)
        references gba.financial_documents (tenant_id, book_id, id)
);
-- One row per budget line: the quantity completed as of the period end and its completed value.
create table gba.construction_pay_application_lines (
    tenant_id uuid not null references gba.tenants(id),
    project_id uuid not null,
    number integer not null,
    change_order integer constraint construction_pay_application_lines_change_order_check
        check (change_order between 1 and 100000),
    budget_position smallint not null constraint construction_pay_application_lines_position_check
        check (budget_position between 1 and 500),
    quantity_to_date numeric(13, 4) not null
        constraint construction_pay_application_lines_quantity_range_check
        check (quantity_to_date >= 0),
    value_to_date_minor bigint not null constraint construction_pay_application_lines_value_check
        check (value_to_date_minor >= 0),
    foreign key (tenant_id, project_id, number)
        references gba.construction_pay_applications (tenant_id, project_id, number)
);
create unique index construction_pay_application_lines_key
    on gba.construction_pay_application_lines
    (tenant_id, project_id, number, coalesce(change_order, 0), budget_position);

-- The current contract sum as O2 computes it: original line amounts less approved removal amounts
-- plus approved added lines, each rounded half up. `p_also` counts that change order as approved.
create function gba.construction_contract_minor(
    p_tenant uuid, p_project uuid, p_also integer default null
) returns bigint language sql stable as $$
    with approved as (
        select o.number, o.position, o.action, o.contract_position, o.quantity, o.unit_price_minor
          from gba.construction_change_order_lines o
         where o.tenant_id = p_tenant and o.project_id = p_project
           and (o.number = p_also or exists (
                select 1 from gba.construction_change_order_decisions d
                 where d.tenant_id = o.tenant_id and d.project_id = o.project_id
                   and d.number = o.number and d.decision = 'approved'))
    ), original as (
        select l.position, l.quantity, l.unit_price_minor
          from gba.construction_contracts k
          join gba.construction_estimate_lines l
            on l.tenant_id = k.tenant_id and l.project_id = k.project_id and l.version = k.version
         where k.tenant_id = p_tenant and k.project_id = p_project
    )
    select (coalesce((select sum(round(quantity * unit_price_minor)) from original), 0)
          - coalesce((select sum(round(a.quantity * l.unit_price_minor))
                        from approved a join original l on l.position = a.contract_position
                       where a.action = 'remove'), 0)
          + coalesce((select sum(round(a.quantity * a.unit_price_minor))
                        from approved a where a.action = 'add'), 0))::bigint
$$;
revoke all on function gba.construction_contract_minor(uuid, uuid, integer) from public;
grant execute on function gba.construction_contract_minor(uuid, uuid, integer) to gba_runtime;

-- Rate versions follow each other under the project lock.
create function gba.guard_construction_retainage_rate() returns trigger language plpgsql as $$
begin
    perform 1 from gba.construction_projects p
     where p.tenant_id = new.tenant_id and p.id = new.project_id for update;
    if new.revision <> coalesce((
        select max(r.revision) from gba.construction_retainage_rates r
        where r.tenant_id = new.tenant_id and r.project_id = new.project_id), 0) + 1 then
        raise exception using errcode = 'check_violation',
            constraint = 'construction_retainage_rates_sequence_check',
            message = 'a retainage rate version follows the latest one';
    end if;
    return new;
end;
$$;
revoke all on function gba.guard_construction_retainage_rate() from public;
create trigger construction_retainage_rates_guard
    before insert on gba.construction_retainage_rates
    for each row execute function gba.guard_construction_retainage_rate();

-- An application follows the previous one under the project lock and is checked as a whole.
create function gba.guard_construction_pay_application() returns trigger language plpgsql as $$
declare
    project record;
    previous bigint;
    current_revision integer;
    current_rate smallint;
begin
    select p.customer_id, p.currency, (now() at time zone p.time_zone)::date as today
      into project
      from gba.construction_projects p
     where p.tenant_id = new.tenant_id and p.id = new.project_id for update;
    if new.number <> coalesce((
        select max(a.number) from gba.construction_pay_applications a
        where a.tenant_id = new.tenant_id and a.project_id = new.project_id), 0) + 1 then
        raise exception using errcode = 'check_violation',
            constraint = 'construction_pay_applications_sequence_check',
            message = 'a pay application follows the latest one';
    end if;
    if exists (
        select 1 from gba.construction_pay_applications a
        where a.tenant_id = new.tenant_id and a.project_id = new.project_id
          and a.period_end >= new.period_end
    ) then
        raise exception using errcode = 'check_violation',
            constraint = 'construction_pay_applications_period_check',
            message = 'a pay application closes a period after the previous one';
    end if;
    if new.period_end > project.today then
        raise exception using errcode = 'check_violation',
            constraint = 'construction_pay_applications_date_check',
            message = 'a period does not end after today on the site';
    end if;
    previous := coalesce((
        select a.billed_to_date_minor from gba.construction_pay_applications a
        where a.tenant_id = new.tenant_id and a.project_id = new.project_id
        order by a.number desc limit 1), 0);
    if new.previous_billed_minor <> previous then
        raise exception using errcode = 'check_violation',
            constraint = 'construction_pay_applications_previous_check',
            message = 'an application starts from what the previous one billed';
    end if;
    if new.this_period_minor <> new.billed_to_date_minor - new.previous_billed_minor
       or new.this_period_minor <= 0
       or new.retained_minor <> (new.this_period_minor * new.rate_bp) / 10000
       or new.due_minor <> new.this_period_minor - new.retained_minor then
        raise exception using errcode = 'check_violation',
            constraint = 'construction_pay_applications_amounts_check',
            message = 'this period, retained and due follow from billed to date and the rate';
    end if;
    select r.revision, r.rate_bp into current_revision, current_rate
      from gba.construction_retainage_rates r
     where r.tenant_id = new.tenant_id and r.project_id = new.project_id
     order by r.revision desc limit 1;
    if new.rate_revision is distinct from current_revision
       or new.rate_bp <> coalesce(current_rate, 0) then
        raise exception using errcode = 'check_violation',
            constraint = 'construction_pay_applications_rate_check',
            message = 'an application uses the current retainage rate';
    end if;
    if new.billed_to_date_minor > gba.construction_contract_minor(new.tenant_id, new.project_id) then
        raise exception using errcode = 'check_violation',
            constraint = 'construction_pay_applications_contract_check',
            message = 'billed never exceeds the contract sum';
    end if;
    if not exists (
        select 1 from gba.financial_documents d
          join gba.financial_document_versions v
            on v.tenant_id = d.tenant_id and v.book_id = d.book_id and v.document_id = d.id
         where d.tenant_id = new.tenant_id and d.book_id = new.book_id
           and d.id = new.invoice_document_id and d.kind = 'invoice'
           and v.revision = (select max(x.revision) from gba.financial_document_versions x
                              where x.tenant_id = d.tenant_id and x.book_id = d.book_id
                                and x.document_id = d.id)
           and v.direction = 'receivable' and v.counterparty_id = project.customer_id
           and v.currency = project.currency and v.principal_minor = new.due_minor
    ) or (new.retained_minor = 0) <> (new.retainage_document_id is null)
      or new.retained_minor > 0 and not exists (
        select 1 from gba.financial_documents d
          join gba.financial_document_versions v
            on v.tenant_id = d.tenant_id and v.book_id = d.book_id and v.document_id = d.id
         where d.tenant_id = new.tenant_id and d.book_id = new.book_id
           and d.id = new.retainage_document_id and d.kind = 'manual_accrual'
           and v.revision = (select max(x.revision) from gba.financial_document_versions x
                              where x.tenant_id = d.tenant_id and x.book_id = d.book_id
                                and x.document_id = d.id)
           and v.direction = 'receivable' and v.counterparty_id = project.customer_id
           and v.currency = project.currency and v.principal_minor = new.retained_minor
           and v.due_date is null
    ) then
        raise exception using errcode = 'check_violation',
            constraint = 'construction_pay_applications_document_check',
            message = 'the due amount is a receivable invoice and the retained one an accrual';
    end if;
    return new;
end;
$$;
revoke all on function gba.guard_construction_pay_application() from public;
create trigger construction_pay_applications_guard
    before insert on gba.construction_pay_applications
    for each row execute function gba.guard_construction_pay_application();

-- At commit, an application's lines add up to what it bills to date.
create function gba.check_construction_pay_application_lines() returns trigger
language plpgsql as $$
begin
    if new.billed_to_date_minor <> coalesce((
        select sum(l.value_to_date_minor) from gba.construction_pay_application_lines l
        where l.tenant_id = new.tenant_id and l.project_id = new.project_id
          and l.number = new.number), 0) then
        raise exception using errcode = 'check_violation',
            constraint = 'construction_pay_applications_lines_check',
            message = 'the lines of an application add up to what it bills to date';
    end if;
    return null;
end;
$$;
revoke all on function gba.check_construction_pay_application_lines() from public;
create constraint trigger construction_pay_applications_lines
    after insert on gba.construction_pay_applications deferrable initially deferred
    for each row execute function gba.check_construction_pay_application_lines();

-- A line is written with its application, names a budget line and holds the quantity of the line's
-- latest measurement dated on or before the period end.
create function gba.guard_construction_pay_application_line() returns trigger
language plpgsql as $$
declare
    closing date;
begin
    select a.period_end into closing from gba.construction_pay_applications a
     where a.tenant_id = new.tenant_id and a.project_id = new.project_id
       and a.number = new.number and a.created_at = now();
    if not found then
        raise exception using errcode = 'check_violation',
            constraint = 'construction_pay_application_lines_record_check',
            message = 'lines are written with their application';
    end if;
    if gba.construction_contracted_quantity(
        new.tenant_id, new.project_id, new.change_order, new.budget_position) is null then
        raise exception using errcode = 'check_violation',
            constraint = 'construction_pay_application_lines_budget_check',
            message = 'a line names a line of the budget';
    end if;
    if new.quantity_to_date <> coalesce((
        select m.quantity_to_date from gba.construction_progress_measurements m
        where m.tenant_id = new.tenant_id and m.project_id = new.project_id
          and m.budget_position = new.budget_position
          and m.change_order is not distinct from new.change_order
          and m.measured_on <= closing
        order by m.number desc limit 1), 0) then
        raise exception using errcode = 'check_violation',
            constraint = 'construction_pay_application_lines_quantity_check',
            message = 'a line holds the latest measurement as of the period end';
    end if;
    return new;
end;
$$;
revoke all on function gba.guard_construction_pay_application_line() from public;
create trigger construction_pay_application_lines_guard
    before insert on gba.construction_pay_application_lines
    for each row execute function gba.guard_construction_pay_application_line();

-- O4a's measurement guard, replaced: a billed period is closed, so a measurement is never dated on or
-- before the latest application's period end.
create or replace function gba.guard_construction_progress_measurement() returns trigger
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
    if exists (
        select 1 from gba.construction_pay_applications a
        where a.tenant_id = new.tenant_id and a.project_id = new.project_id
          and a.period_end >= new.measured_on
    ) then
        raise exception using errcode = 'check_violation',
            constraint = 'construction_progress_measurements_period_check',
            message = 'a billed period is closed for measurements';
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

-- The approval guard, replaced again: besides its O2 and O4a checks, an approval never takes the
-- contract sum below what the project has billed to date.
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
    if gba.construction_contract_minor(new.tenant_id, new.project_id, new.number) < coalesce((
        select a.billed_to_date_minor from gba.construction_pay_applications a
        where a.tenant_id = new.tenant_id and a.project_id = new.project_id
        order by a.number desc limit 1), 0) then
        raise exception using errcode = 'check_violation',
            constraint = 'construction_change_order_decisions_billed_check',
            message = 'an approval never takes the contract sum below what was billed';
    end if;
    return new;
end;
$$;

-- Writes need the construction module (ADR-0019 gate); FIN-03 checks its own modules.
create trigger construction_retainage_rates_module_gate
    before insert on gba.construction_retainage_rates
    for each row execute function gba.require_enabled_module('construction');
create trigger construction_pay_applications_module_gate
    before insert on gba.construction_pay_applications
    for each row execute function gba.require_enabled_module('construction');
create trigger construction_pay_application_lines_module_gate
    before insert on gba.construction_pay_application_lines
    for each row execute function gba.require_enabled_module('construction');

alter table gba.construction_retainage_rates enable row level security;
alter table gba.construction_retainage_rates force row level security;
alter table gba.construction_pay_applications enable row level security;
alter table gba.construction_pay_applications force row level security;
alter table gba.construction_pay_application_lines enable row level security;
alter table gba.construction_pay_application_lines force row level security;
create policy construction_retainage_rates_tenant_isolation on gba.construction_retainage_rates
    using (tenant_id = gba.current_tenant_id())
    with check (tenant_id = gba.current_tenant_id());
create policy construction_pay_applications_tenant_isolation
    on gba.construction_pay_applications
    using (tenant_id = gba.current_tenant_id())
    with check (tenant_id = gba.current_tenant_id());
create policy construction_pay_application_lines_tenant_isolation
    on gba.construction_pay_application_lines
    using (tenant_id = gba.current_tenant_id())
    with check (tenant_id = gba.current_tenant_id());
grant select, insert on gba.construction_retainage_rates, gba.construction_pay_applications,
    gba.construction_pay_application_lines to gba_runtime;

-- Construction branch scope:
create policy construction_retainage_rates_location_scope on gba.construction_retainage_rates
    as restrictive to gba_runtime
    using (gba.current_location_id() is null or exists (
        select 1 from gba.construction_projects p
        where p.tenant_id = construction_retainage_rates.tenant_id
          and p.id = construction_retainage_rates.project_id))
    with check (gba.current_location_id() is null or exists (
        select 1 from gba.construction_projects p
        where p.tenant_id = construction_retainage_rates.tenant_id
          and p.id = construction_retainage_rates.project_id));
create policy construction_pay_applications_location_scope
    on gba.construction_pay_applications
    as restrictive to gba_runtime
    using (gba.current_location_id() is null or exists (
        select 1 from gba.construction_projects p
        where p.tenant_id = construction_pay_applications.tenant_id
          and p.id = construction_pay_applications.project_id))
    with check (gba.current_location_id() is null or exists (
        select 1 from gba.construction_projects p
        where p.tenant_id = construction_pay_applications.tenant_id
          and p.id = construction_pay_applications.project_id));
create policy construction_pay_application_lines_location_scope
    on gba.construction_pay_application_lines
    as restrictive to gba_runtime
    using (gba.current_location_id() is null or exists (
        select 1 from gba.construction_projects p
        where p.tenant_id = construction_pay_application_lines.tenant_id
          and p.id = construction_pay_application_lines.project_id))
    with check (gba.current_location_id() is null or exists (
        select 1 from gba.construction_projects p
        where p.tenant_id = construction_pay_application_lines.tenant_id
          and p.id = construction_pay_application_lines.project_id));
