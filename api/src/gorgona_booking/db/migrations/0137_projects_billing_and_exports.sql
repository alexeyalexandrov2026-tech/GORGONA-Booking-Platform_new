-- PRO-01 Slice 4 (ADR-0038): FIN-03 matter invoicing and ACL-enforced audited exports.
-- Invoker rights only.

create table gba.project_matter_invoices (
    tenant_id uuid not null,
    id uuid not null,
    location_id uuid not null,
    matter_id uuid not null,
    book_id uuid not null,
    invoice_document_id uuid not null,
    counterparty_id uuid not null,
    total_minor bigint not null check (total_minor > 0),
    currency char(3) not null check (currency ~ '^[A-Z]{3}$'),
    title text not null check (char_length(btrim(title)) between 1 and 200),
    number text check (number is null or char_length(btrim(number)) between 1 and 64),
    invoice_date date not null,
    due_date date not null check (due_date >= invoice_date),
    recorded_by uuid not null references gba.users (id),
    recorded_at timestamptz not null default clock_timestamp(),
    primary key (tenant_id, id),
    unique (tenant_id, id, matter_id, location_id, currency),
    unique (tenant_id, book_id, invoice_document_id),
    foreign key (tenant_id, matter_id, location_id, currency)
        references gba.project_matters (tenant_id, id, location_id, currency),
    foreign key (tenant_id, book_id, invoice_document_id)
        references gba.financial_documents (tenant_id, book_id, id),
    foreign key (tenant_id, counterparty_id)
        references gba.counterparties (tenant_id, id)
);
create index project_matter_invoices_matter_idx
    on gba.project_matter_invoices (tenant_id, matter_id, invoice_date desc, id);

create table gba.project_matter_invoice_items (
    tenant_id uuid not null,
    id uuid not null,
    location_id uuid not null,
    matter_id uuid not null,
    matter_invoice_id uuid not null,
    item_kind text not null check (item_kind in ('time_entry', 'stage_fee', 'recurring_run')),
    time_entry_id uuid,
    stage_id uuid,
    recurring_run_id uuid,
    description text not null check (char_length(btrim(description)) between 1 and 500),
    amount_minor bigint not null check (amount_minor > 0),
    currency char(3) not null check (currency ~ '^[A-Z]{3}$'),
    recorded_at timestamptz not null default clock_timestamp(),
    primary key (tenant_id, id),
    foreign key (tenant_id, matter_invoice_id, matter_id, location_id, currency)
        references gba.project_matter_invoices (tenant_id, id, matter_id, location_id, currency),
    foreign key (tenant_id, time_entry_id, matter_id, location_id)
        references gba.project_time_entries (tenant_id, id, matter_id, location_id),
    foreign key (tenant_id, stage_id, matter_id, location_id)
        references gba.project_stages (tenant_id, id, matter_id, location_id),
    foreign key (tenant_id, recurring_run_id, matter_id, location_id)
        references gba.project_recurring_runs (tenant_id, id, matter_id, location_id),
    check (
        (item_kind = 'time_entry' and time_entry_id is not null and stage_id is null and recurring_run_id is null)
        or (item_kind = 'stage_fee' and stage_id is not null and time_entry_id is null and recurring_run_id is null)
        or (item_kind = 'recurring_run' and recurring_run_id is not null and time_entry_id is null and stage_id is null)
    )
);
create unique index project_matter_invoice_items_time_uidx
    on gba.project_matter_invoice_items (tenant_id, time_entry_id)
    where time_entry_id is not null;
create unique index project_matter_invoice_items_stage_uidx
    on gba.project_matter_invoice_items (tenant_id, stage_id)
    where stage_id is not null;
create unique index project_matter_invoice_items_run_uidx
    on gba.project_matter_invoice_items (tenant_id, recurring_run_id)
    where recurring_run_id is not null;
create index project_matter_invoice_items_inv_idx
    on gba.project_matter_invoice_items (tenant_id, matter_invoice_id, id);

create table gba.project_exports (
    tenant_id uuid not null,
    id uuid not null,
    location_id uuid not null,
    scope text not null check (scope in ('matter', 'portfolio')),
    matter_id uuid,
    requested_by uuid not null references gba.users (id),
    matter_count integer not null check (matter_count >= 0),
    stage_count integer not null check (stage_count >= 0),
    task_count integer not null check (task_count >= 0),
    file_count integer not null check (file_count >= 0),
    time_entry_count integer not null check (time_entry_count >= 0),
    recurring_run_count integer not null check (recurring_run_count >= 0),
    invoice_count integer not null check (invoice_count >= 0),
    recorded_at timestamptz not null default clock_timestamp(),
    primary key (tenant_id, id),
    foreign key (tenant_id, location_id) references gba.locations (tenant_id, id),
    foreign key (tenant_id, matter_id, location_id)
        references gba.project_matters (tenant_id, id, location_id),
    check (
        (scope = 'matter' and matter_id is not null)
        or (scope = 'portfolio' and matter_id is null)
    )
);
create index project_exports_loc_idx
    on gba.project_exports (tenant_id, location_id, recorded_at desc, id);

create trigger project_matter_invoices_append_only
    before update or delete on gba.project_matter_invoices
    for each row execute function gba.guard_project_append_only();
create trigger project_matter_invoice_items_append_only
    before update or delete on gba.project_matter_invoice_items
    for each row execute function gba.guard_project_append_only();
create trigger project_exports_append_only
    before update or delete on gba.project_exports
    for each row execute function gba.guard_project_append_only();

-- Deferred total conservation check: sum(items.amount_minor) = invoice.total_minor
create function gba.check_project_invoice_total() returns trigger language plpgsql as $$
declare
    v_sum bigint;
begin
    select coalesce(sum(amount_minor), 0) into v_sum
      from gba.project_matter_invoice_items
     where tenant_id = new.tenant_id and matter_invoice_id = new.id;
    if v_sum <> new.total_minor then
        raise exception using errcode = '23514',
            message = 'project invoice total must equal the sum of billed items';
    end if;
    return null;
end;
$$;
revoke all on function gba.check_project_invoice_total() from public;
grant execute on function gba.check_project_invoice_total() to gba_runtime;
create constraint trigger project_matter_invoices_total_conserved
    after insert on gba.project_matter_invoices
    deferrable initially deferred
    for each row execute function gba.check_project_invoice_total();

-- RLS, module write gates and minimal runtime privileges
alter table gba.project_matter_invoices enable row level security;
alter table gba.project_matter_invoices force row level security;
create policy project_matter_invoices_tenant_isolation on gba.project_matter_invoices
    using (tenant_id = gba.current_tenant_id()) with check (tenant_id = gba.current_tenant_id());
grant select, insert on gba.project_matter_invoices to gba_runtime;
create trigger project_matter_invoices_require_module before insert on gba.project_matter_invoices
    for each row execute function gba.require_enabled_module('projects');

alter table gba.project_matter_invoice_items enable row level security;
alter table gba.project_matter_invoice_items force row level security;
create policy project_matter_invoice_items_tenant_isolation on gba.project_matter_invoice_items
    using (tenant_id = gba.current_tenant_id()) with check (tenant_id = gba.current_tenant_id());
grant select, insert on gba.project_matter_invoice_items to gba_runtime;

alter table gba.project_exports enable row level security;
alter table gba.project_exports force row level security;
create policy project_exports_tenant_isolation on gba.project_exports
    using (tenant_id = gba.current_tenant_id()) with check (tenant_id = gba.current_tenant_id());
grant select, insert on gba.project_exports to gba_runtime;
create trigger project_exports_require_module before insert on gba.project_exports
    for each row execute function gba.require_enabled_module('projects');

-- Projects billing & exports ethical-wall matter access scope (PostgreSQL 18 FORCE RLS, invoker rights):
create policy project_matter_invoices_matter_access on gba.project_matter_invoices as restrictive to gba_runtime
    using (
        exists (
            select 1 from gba.project_matters pm
            where pm.tenant_id = project_matter_invoices.tenant_id
              and pm.id = project_matter_invoices.matter_id
        )
    )
    with check (
        exists (
            select 1 from gba.project_matters pm
            where pm.tenant_id = project_matter_invoices.tenant_id
              and pm.id = project_matter_invoices.matter_id
        )
    );

create policy project_matter_invoice_items_matter_access on gba.project_matter_invoice_items as restrictive to gba_runtime
    using (
        exists (
            select 1 from gba.project_matters pm
            where pm.tenant_id = project_matter_invoice_items.tenant_id
              and pm.id = project_matter_invoice_items.matter_id
        )
    )
    with check (
        exists (
            select 1 from gba.project_matters pm
            where pm.tenant_id = project_matter_invoice_items.tenant_id
              and pm.id = project_matter_invoice_items.matter_id
        )
    );

create policy project_exports_matter_access on gba.project_exports as restrictive to gba_runtime
    using (
        (scope = 'portfolio' and requested_by = gba.current_user_id())
        or (
            scope = 'matter'
            and exists (
                select 1 from gba.project_matters pm
                where pm.tenant_id = project_exports.tenant_id
                  and pm.id = project_exports.matter_id
            )
        )
    )
    with check (
        (scope = 'portfolio' and requested_by = gba.current_user_id())
        or (
            scope = 'matter'
            and exists (
                select 1 from gba.project_matters pm
                where pm.tenant_id = project_exports.tenant_id
                  and pm.id = project_exports.matter_id
            )
        )
    );

-- Projects billing branch scope:
create policy project_matter_invoices_location_scope on gba.project_matter_invoices as restrictive to gba_runtime
    using (gba.current_location_id() is null or location_id = gba.current_location_id())
    with check (gba.current_location_id() is null or location_id = gba.current_location_id());

create policy project_matter_invoice_items_location_scope on gba.project_matter_invoice_items as restrictive to gba_runtime
    using (gba.current_location_id() is null or location_id = gba.current_location_id())
    with check (gba.current_location_id() is null or location_id = gba.current_location_id());

create policy project_exports_location_scope on gba.project_exports as restrictive to gba_runtime
    using (gba.current_location_id() is null or location_id = gba.current_location_id())
    with check (gba.current_location_id() is null or location_id = gba.current_location_id());
