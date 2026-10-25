-- M7a (package M): transport money through FIN-03. ADR-0033.
-- An order's agreed rate is kept as insert-only versions and frozen by its one invoice; a trip's pay
-- components are registered once (one per recipient and role) and each accrues once as a FIN-03
-- payable accrual. FIN-03 keeps every payment within an obligation's open balance.
create table gba.transport_order_rates (
    tenant_id uuid not null references gba.tenants(id),
    order_id uuid not null,
    revision integer not null constraint transport_order_rates_revision_check check (revision > 0),
    currency text not null references gba.currencies(code),
    basis text not null constraint transport_order_rates_basis_check
        check (basis in ('fixed', 'per_mile')),
    amount numeric(20, 3) not null constraint transport_order_rates_amount_check check (amount > 0),
    created_by uuid not null references gba.users(id),
    created_at timestamptz not null default now(),
    primary key (tenant_id, order_id, revision),
    foreign key (tenant_id, order_id) references gba.transport_orders (tenant_id, id)
);
create table gba.transport_order_invoices (
    tenant_id uuid not null references gba.tenants(id),
    order_id uuid not null,
    rate_revision integer not null,
    miles numeric(9, 1) constraint transport_order_invoices_miles_check
        check (miles is null or miles > 0),
    book_id uuid not null,
    document_id uuid not null,
    created_by uuid not null references gba.users(id),
    created_at timestamptz not null default now(),
    primary key (tenant_id, order_id),
    unique (tenant_id, book_id, document_id),
    foreign key (tenant_id, order_id, rate_revision)
        references gba.transport_order_rates (tenant_id, order_id, revision),
    foreign key (tenant_id, book_id, document_id)
        references gba.financial_documents (tenant_id, book_id, id)
);
create table gba.transport_pay_components (
    tenant_id uuid not null references gba.tenants(id),
    id uuid not null,
    trip_id uuid not null,
    counterparty_id uuid not null,
    role text not null constraint transport_pay_components_role_check
        check (role in ('driver', 'owner_operator', 'dispatch_fee', 'other')),
    currency text not null references gba.currencies(code),
    basis text not null constraint transport_pay_components_basis_check
        check (basis in ('fixed', 'per_mile', 'percent')),
    amount numeric(20, 3) constraint transport_pay_components_amount_check
        check (amount is null or amount > 0),
    rate numeric(20, 3) constraint transport_pay_components_rate_check
        check (rate is null or rate > 0),
    percent numeric(5, 2) constraint transport_pay_components_percent_check
        check (percent is null or (percent > 0 and percent <= 100)),
    base numeric(20, 3) constraint transport_pay_components_base_check
        check (base is null or base > 0),
    created_by uuid not null references gba.users(id),
    created_at timestamptz not null default now(),
    primary key (tenant_id, id),
    -- §7.5: one recipient has one component of a kind on a trip.
    unique (tenant_id, trip_id, counterparty_id, role),
    foreign key (tenant_id, trip_id) references gba.transport_trips (tenant_id, id),
    foreign key (tenant_id, counterparty_id) references gba.counterparties (tenant_id, id),
    constraint transport_pay_components_formula_check check (
        (basis = 'fixed' and amount is not null and rate is null and percent is null and base is null)
        or (basis = 'per_mile' and rate is not null and amount is null and percent is null
            and base is null)
        or (basis = 'percent' and percent is not null and base is not null and amount is null
            and rate is null))
);
create table gba.transport_pay_accruals (
    tenant_id uuid not null references gba.tenants(id),
    component_id uuid not null,
    miles numeric(9, 1) constraint transport_pay_accruals_miles_check
        check (miles is null or miles > 0),
    book_id uuid not null,
    document_id uuid not null,
    created_by uuid not null references gba.users(id),
    created_at timestamptz not null default now(),
    primary key (tenant_id, component_id),
    unique (tenant_id, book_id, document_id),
    foreign key (tenant_id, component_id) references gba.transport_pay_components (tenant_id, id),
    foreign key (tenant_id, book_id, document_id)
        references gba.financial_documents (tenant_id, book_id, id)
);

-- A rate version follows the previous one of its order and never follows the order's invoice.
create function gba.guard_transport_order_rate() returns trigger language plpgsql as $$
begin
    perform pg_catalog.pg_advisory_xact_lock(
        pg_catalog.hashtextextended('gba:order-rate:' || new.order_id::text, 0));
    if exists (select 1 from gba.transport_order_invoices i
                where i.tenant_id = new.tenant_id and i.order_id = new.order_id) then
        raise exception using errcode = 'check_violation',
            constraint = 'transport_order_rates_invoiced_check',
            message = 'an invoiced order keeps its rate';
    end if;
    if new.revision <> coalesce((
        select max(r.revision) from gba.transport_order_rates r
         where r.tenant_id = new.tenant_id and r.order_id = new.order_id), 0) + 1 then
        raise exception using errcode = 'check_violation',
            constraint = 'transport_order_rates_revision_check',
            message = 'a rate version follows the previous one';
    end if;
    return new;
end;
$$;
revoke all on function gba.guard_transport_order_rate() from public;
create trigger transport_order_rates_guard before insert on gba.transport_order_rates
    for each row execute function gba.guard_transport_order_rate();

-- An invoice uses the order's current rate; the rate cannot change after it (same lock as above).
create function gba.guard_transport_order_invoice() returns trigger language plpgsql as $$
begin
    perform pg_catalog.pg_advisory_xact_lock(
        pg_catalog.hashtextextended('gba:order-rate:' || new.order_id::text, 0));
    if new.rate_revision <> (
        select max(r.revision) from gba.transport_order_rates r
         where r.tenant_id = new.tenant_id and r.order_id = new.order_id) then
        raise exception using errcode = 'check_violation',
            constraint = 'transport_order_invoices_rate_check',
            message = 'an invoice uses the current rate';
    end if;
    return new;
end;
$$;
revoke all on function gba.guard_transport_order_invoice() from public;
create trigger transport_order_invoices_guard before insert on gba.transport_order_invoices
    for each row execute function gba.guard_transport_order_invoice();

-- Writes need the transport module (ADR-0019 gate); FIN-03 checks its own modules.
create trigger transport_order_rates_module_gate before insert on gba.transport_order_rates
    for each row execute function gba.require_enabled_module('transport');
create trigger transport_order_invoices_module_gate before insert on gba.transport_order_invoices
    for each row execute function gba.require_enabled_module('transport');
create trigger transport_pay_components_module_gate before insert on gba.transport_pay_components
    for each row execute function gba.require_enabled_module('transport');
create trigger transport_pay_accruals_module_gate before insert on gba.transport_pay_accruals
    for each row execute function gba.require_enabled_module('transport');

alter table gba.transport_order_rates enable row level security;
alter table gba.transport_order_rates force row level security;
alter table gba.transport_order_invoices enable row level security;
alter table gba.transport_order_invoices force row level security;
alter table gba.transport_pay_components enable row level security;
alter table gba.transport_pay_components force row level security;
alter table gba.transport_pay_accruals enable row level security;
alter table gba.transport_pay_accruals force row level security;
create policy transport_order_rates_tenant_isolation on gba.transport_order_rates
    using (tenant_id = gba.current_tenant_id())
    with check (tenant_id = gba.current_tenant_id());
create policy transport_order_invoices_tenant_isolation on gba.transport_order_invoices
    using (tenant_id = gba.current_tenant_id())
    with check (tenant_id = gba.current_tenant_id());
create policy transport_pay_components_tenant_isolation on gba.transport_pay_components
    using (tenant_id = gba.current_tenant_id())
    with check (tenant_id = gba.current_tenant_id());
create policy transport_pay_accruals_tenant_isolation on gba.transport_pay_accruals
    using (tenant_id = gba.current_tenant_id())
    with check (tenant_id = gba.current_tenant_id());
grant select on gba.transport_order_rates, gba.transport_order_invoices,
    gba.transport_pay_components, gba.transport_pay_accruals to gba_runtime;
grant insert (tenant_id, order_id, revision, currency, basis, amount, created_by)
    on gba.transport_order_rates to gba_runtime;
grant insert (tenant_id, order_id, rate_revision, miles, book_id, document_id, created_by)
    on gba.transport_order_invoices to gba_runtime;
grant insert (tenant_id, id, trip_id, counterparty_id, role, currency, basis, amount, rate,
              percent, base, created_by)
    on gba.transport_pay_components to gba_runtime;
grant insert (tenant_id, component_id, miles, book_id, document_id, created_by)
    on gba.transport_pay_accruals to gba_runtime;

-- Transport money branch scope:
create policy transport_pay_components_location_scope on gba.transport_pay_components
    as restrictive to gba_runtime
    using (gba.current_location_id() is null or exists (
        select 1 from gba.transport_trips t
        where t.tenant_id = transport_pay_components.tenant_id
          and t.id = transport_pay_components.trip_id))
    with check (gba.current_location_id() is null or exists (
        select 1 from gba.transport_trips t
        where t.tenant_id = transport_pay_components.tenant_id
          and t.id = transport_pay_components.trip_id));
create policy transport_pay_accruals_location_scope on gba.transport_pay_accruals
    as restrictive to gba_runtime
    using (gba.current_location_id() is null or exists (
        select 1 from gba.transport_pay_components c
        where c.tenant_id = transport_pay_accruals.tenant_id
          and c.id = transport_pay_accruals.component_id))
    with check (gba.current_location_id() is null or exists (
        select 1 from gba.transport_pay_components c
        where c.tenant_id = transport_pay_accruals.tenant_id
          and c.id = transport_pay_accruals.component_id));
