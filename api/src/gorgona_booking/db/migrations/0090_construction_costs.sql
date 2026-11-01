-- O3b (package O, BUILD-01): actual costs are links of existing facts to budget lines. ADR-0035,
-- docs/plan/PACKAGE_O3B_DESIGN_2026-10-31.md. A link names one STOCK-01 write-off line, one line of an
-- issued FIN-03 payable or one approved WORK-01 time entry with a rate; each fact counts on one link at
-- a time; a reversal row instead of an edit. Links and reversals are insert-only.
create table gba.construction_cost_links (
    tenant_id uuid not null references gba.tenants(id),
    project_id uuid not null,
    number integer not null constraint construction_cost_links_number_check
        check (number between 1 and 1000000),
    kind text not null constraint construction_cost_links_kind_check
        check (kind in ('stock_write_off', 'payable', 'time_entry')),
    change_order integer constraint construction_cost_links_change_order_check
        check (change_order between 1 and 100000),
    budget_position smallint not null constraint construction_cost_links_position_check
        check (budget_position between 1 and 500),
    stock_document_id uuid,
    stock_line_no smallint,
    book_id uuid,
    document_id uuid,
    document_revision integer,
    line_id uuid,
    time_entry_id uuid,
    time_entry_revision integer,
    worked_microseconds bigint constraint construction_cost_links_worked_check
        check (worked_microseconds > 0),
    rate_per_hour_minor bigint constraint construction_cost_links_rate_check
        check (rate_per_hour_minor between 1 and 1000000000),
    fact_key text not null constraint construction_cost_links_fact_key_check
        check (length(fact_key) between 1 and 200),
    attempt integer not null constraint construction_cost_links_attempt_range_check
        check (attempt between 1 and 100000),
    amount_minor bigint not null constraint construction_cost_links_amount_range_check
        check (amount_minor between 1 and 1000000000000000),
    currency text not null references gba.currencies(code),
    note text constraint construction_cost_links_note_check
        check (note is null or length(note) between 1 and 500),
    created_by uuid not null references gba.users(id),
    created_at timestamptz not null default now(),
    primary key (tenant_id, project_id, number),
    constraint construction_cost_links_once unique (tenant_id, fact_key, attempt),
    constraint construction_cost_links_shape_check check (
        (kind = 'stock_write_off' and stock_document_id is not null and stock_line_no is not null
            and book_id is null and document_id is null and document_revision is null
            and line_id is null and time_entry_id is null and time_entry_revision is null
            and worked_microseconds is null and rate_per_hour_minor is null)
        or (kind = 'payable' and stock_document_id is null and stock_line_no is null
            and book_id is not null and document_id is not null and document_revision is not null
            and line_id is not null and time_entry_id is null and time_entry_revision is null
            and worked_microseconds is null and rate_per_hour_minor is null)
        or (kind = 'time_entry' and stock_document_id is null and stock_line_no is null
            and book_id is null and document_id is null and document_revision is null
            and line_id is null and time_entry_id is not null and time_entry_revision is not null
            and worked_microseconds is not null and rate_per_hour_minor is not null)),
    foreign key (tenant_id, project_id) references gba.construction_contracts (tenant_id, project_id),
    foreign key (tenant_id, stock_document_id, stock_line_no)
        references gba.stock_document_lines (tenant_id, document_id, line_no),
    foreign key (tenant_id, book_id, document_id, document_revision)
        references gba.financial_document_versions (tenant_id, book_id, document_id, revision),
    foreign key (tenant_id, time_entry_id, time_entry_revision)
        references gba.time_entry_revisions (tenant_id, entry_id, revision)
);
-- One reversal per link; a reversed link no longer counts and its fact may be linked again.
create table gba.construction_cost_reversals (
    tenant_id uuid not null references gba.tenants(id),
    project_id uuid not null,
    number integer not null,
    reason text not null constraint construction_cost_reversals_reason_check
        check (length(btrim(reason)) between 1 and 500),
    created_by uuid not null references gba.users(id),
    created_at timestamptz not null default now(),
    primary key (tenant_id, project_id, number),
    foreign key (tenant_id, project_id, number)
        references gba.construction_cost_links (tenant_id, project_id, number)
);

-- The fact a link names, as the caller may see it (row-level security applies): its key, amount,
-- currency (null for time: the project's), branch (null for a payable), pinned revision and worked time.
-- Time is worked microseconds x the rate per hour, rounded half up to a whole minor unit.
create function gba.construction_cost_fact(
    p_tenant uuid,
    p_kind text,
    p_stock_document uuid,
    p_stock_line smallint,
    p_book uuid,
    p_document uuid,
    p_line uuid,
    p_time_entry uuid,
    p_rate bigint
) returns table (
    fact_key text,
    amount_minor bigint,
    currency text,
    location_id uuid,
    source_revision integer,
    worked_microseconds bigint
) language sql stable as $$
    select 'stock_write_off:' || d.id || ':' || l.line_no, v.amount_minor, b.base_currency,
           d.location_id, null::integer, null::bigint
      from gba.stock_documents d
      join gba.stock_document_lines l on l.tenant_id = d.tenant_id and l.document_id = d.id
      join gba.stock_valuations v on v.tenant_id = l.tenant_id and v.document_id = l.document_id
       and v.line_no = l.line_no and v.direction = 'out'
      join gba.stock_document_postings p on p.tenant_id = d.tenant_id and p.document_id = d.id
     cross join lateral (
            select x.base_currency from gba.ledger_book_versions x
             where x.tenant_id = p.tenant_id and x.book_id = p.book_id
             order by x.revision desc limit 1) b
     where p_kind = 'stock_write_off' and d.tenant_id = p_tenant and d.id = p_stock_document
       and l.line_no = p_stock_line and d.kind = 'write_off'
    union all
    select 'payable:' || f.book_id || ':' || f.id || ':' || l.line_id, l.amount_minor, v.currency,
           null::uuid, v.revision, null::bigint
      from gba.financial_documents f
      join gba.financial_document_versions v on v.tenant_id = f.tenant_id and v.book_id = f.book_id
       and v.document_id = f.id and v.state = 'issued' and v.direction = 'payable'
      join gba.financial_document_lines l on l.tenant_id = v.tenant_id and l.book_id = v.book_id
       and l.document_id = v.document_id and l.revision = v.revision and l.line_id = p_line
     where p_kind = 'payable' and f.tenant_id = p_tenant and f.book_id = p_book and f.id = p_document
       and f.kind in ('invoice', 'manual_accrual')
       and v.revision = (
            select max(y.revision) from gba.financial_document_versions y
             where y.tenant_id = f.tenant_id and y.book_id = f.book_id and y.document_id = f.id)
    union all
    select 'time_entry:' || e.id,
           floor((w.micro::numeric * p_rate + 1800000000) / 3600000000)::bigint,
           null::text, e.location_id, s.approved_revision, w.micro
      from gba.time_entries e
      join gba.time_entry_state s on s.tenant_id = e.tenant_id and s.entry_id = e.id
      join gba.time_entry_revisions r on r.tenant_id = s.tenant_id and r.entry_id = s.entry_id
       and r.revision = s.approved_revision
     cross join lateral (
            select (extract(epoch from (r.ends_at - r.starts_at)) * 1000000)::bigint
                   - coalesce((select sum((extract(epoch from (k.e - k.s)) * 1000000)::bigint)
                                 from unnest(r.break_starts, r.break_ends) as k(s, e)), 0) as micro) w
     where p_kind = 'time_entry' and e.tenant_id = p_tenant and e.id = p_time_entry
       and s.approved_revision is not null and r.ends_at is not null and p_rate is not null
$$;
revoke all on function gba.construction_cost_fact(
    uuid, text, uuid, smallint, uuid, uuid, uuid, uuid, bigint) from public;
grant execute on function gba.construction_cost_fact(
    uuid, text, uuid, smallint, uuid, uuid, uuid, uuid, bigint) to gba_runtime;

-- Links follow each other; the fact exists in the project's branch and currency, at the stored amount;
-- no earlier link of the fact still counts; the budget line exists (as for commitment lines).
create function gba.guard_construction_cost_link() returns trigger language plpgsql as $$
declare
    home record;
    fact record;
begin
    if new.number <> coalesce((
        select max(c.number) from gba.construction_cost_links c
        where c.tenant_id = new.tenant_id and c.project_id = new.project_id), 0) + 1 then
        raise exception using errcode = 'check_violation',
            constraint = 'construction_cost_links_sequence_check',
            message = 'a cost link follows the latest one';
    end if;
    select p.location_id, p.currency into home from gba.construction_projects p
     where p.tenant_id = new.tenant_id and p.id = new.project_id;
    select * into fact from gba.construction_cost_fact(
        new.tenant_id, new.kind, new.stock_document_id, new.stock_line_no, new.book_id,
        new.document_id, new.line_id, new.time_entry_id, new.rate_per_hour_minor);
    if not found or (fact.location_id is not null and fact.location_id <> home.location_id) then
        raise exception using errcode = 'check_violation',
            constraint = 'construction_cost_links_fact_check',
            message = 'a cost link names a fact of the project''s branch';
    end if;
    if coalesce(fact.currency, home.currency) <> home.currency or new.currency <> home.currency then
        raise exception using errcode = 'check_violation',
            constraint = 'construction_cost_links_currency_check',
            message = 'a cost link is in the project''s currency';
    end if;
    if new.fact_key <> fact.fact_key or new.amount_minor <> fact.amount_minor
       or new.document_revision is distinct from
            (case when new.kind = 'payable' then fact.source_revision end)
       or new.time_entry_revision is distinct from
            (case when new.kind = 'time_entry' then fact.source_revision end)
       or new.worked_microseconds is distinct from fact.worked_microseconds then
        raise exception using errcode = 'check_violation',
            constraint = 'construction_cost_links_amount_check',
            message = 'a cost link carries the amount of its fact';
    end if;
    if new.attempt <> (
        select count(*) from gba.construction_cost_links c
        where c.tenant_id = new.tenant_id and c.fact_key = new.fact_key) + 1
       or exists (
        select 1 from gba.construction_cost_links c
        where c.tenant_id = new.tenant_id and c.fact_key = new.fact_key
          and not exists (
            select 1 from gba.construction_cost_reversals r
            where r.tenant_id = c.tenant_id and r.project_id = c.project_id
              and r.number = c.number)) then
        raise exception using errcode = 'check_violation',
            constraint = 'construction_cost_links_attempt_check',
            message = 'a fact counts on one cost link at a time';
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
            constraint = 'construction_cost_links_budget_check',
            message = 'a cost link names a line of the budget';
    end if;
    return new;
end;
$$;
revoke all on function gba.guard_construction_cost_link() from public;
create trigger construction_cost_links_guard
    before insert on gba.construction_cost_links
    for each row execute function gba.guard_construction_cost_link();

-- Writes need the construction module (ADR-0019 gate).
create trigger construction_cost_links_module_gate
    before insert on gba.construction_cost_links
    for each row execute function gba.require_enabled_module('construction');
create trigger construction_cost_reversals_module_gate
    before insert on gba.construction_cost_reversals
    for each row execute function gba.require_enabled_module('construction');

alter table gba.construction_cost_links enable row level security;
alter table gba.construction_cost_links force row level security;
alter table gba.construction_cost_reversals enable row level security;
alter table gba.construction_cost_reversals force row level security;
create policy construction_cost_links_tenant_isolation on gba.construction_cost_links
    using (tenant_id = gba.current_tenant_id())
    with check (tenant_id = gba.current_tenant_id());
create policy construction_cost_reversals_tenant_isolation on gba.construction_cost_reversals
    using (tenant_id = gba.current_tenant_id())
    with check (tenant_id = gba.current_tenant_id());
grant select, insert on gba.construction_cost_links, gba.construction_cost_reversals to gba_runtime;

-- Construction branch scope:
create policy construction_cost_links_location_scope on gba.construction_cost_links
    as restrictive to gba_runtime
    using (gba.current_location_id() is null or exists (
        select 1 from gba.construction_projects p
        where p.tenant_id = construction_cost_links.tenant_id
          and p.id = construction_cost_links.project_id))
    with check (gba.current_location_id() is null or exists (
        select 1 from gba.construction_projects p
        where p.tenant_id = construction_cost_links.tenant_id
          and p.id = construction_cost_links.project_id));
create policy construction_cost_reversals_location_scope on gba.construction_cost_reversals
    as restrictive to gba_runtime
    using (gba.current_location_id() is null or exists (
        select 1 from gba.construction_projects p
        where p.tenant_id = construction_cost_reversals.tenant_id
          and p.id = construction_cost_reversals.project_id))
    with check (gba.current_location_id() is null or exists (
        select 1 from gba.construction_projects p
        where p.tenant_id = construction_cost_reversals.tenant_id
          and p.id = construction_cost_reversals.project_id));
