-- L5 (package L, BEAUTY-01): commission plans and the commission accrual of a visit.
-- Design docs/plan/PACKAGE_L5_DESIGN_2026-10-22.md. A plan per specialist (an artist resource)
-- names the payee and the currency; its rules give a percentage (basis points) or a fixed amount
-- (minor units) per service, or as the default. The accrual is a FIN-03 manual accrual linked to
-- its visit once.

create table gba.commission_plans (
    tenant_id uuid not null references gba.tenants(id),
    resource_id uuid not null,
    counterparty_id uuid not null,
    currency text not null references gba.currencies(code),
    revision integer not null constraint commission_plans_revision_check check (revision > 0),
    updated_by uuid not null references gba.users(id),
    updated_at timestamptz not null default now(),
    primary key (tenant_id, resource_id),
    foreign key (tenant_id, resource_id) references gba.resources (tenant_id, id),
    foreign key (tenant_id, counterparty_id) references gba.counterparties (tenant_id, id)
);
create table gba.commission_rules (
    tenant_id uuid not null references gba.tenants(id),
    resource_id uuid not null,
    position smallint not null constraint commission_rules_position_check
        check (position between 1 and 50),
    -- Null is the default rule for every service without its own.
    service_id uuid,
    percent_bp integer constraint commission_rules_percent_check
        check (percent_bp between 0 and 10000),
    amount_minor bigint constraint commission_rules_amount_check
        check (amount_minor between 0 and 999999999999),
    primary key (tenant_id, resource_id, position),
    constraint commission_rules_one_per_service
        unique nulls not distinct (tenant_id, resource_id, service_id),
    constraint commission_rules_one_kind_check
        check ((percent_bp is null) <> (amount_minor is null)),
    foreign key (tenant_id, resource_id) references gba.commission_plans (tenant_id, resource_id),
    foreign key (tenant_id, service_id) references gba.services (tenant_id, id)
);
create table gba.visit_commissions (
    tenant_id uuid not null references gba.tenants(id),
    booking_id uuid not null,
    book_id uuid not null,
    document_id uuid not null,
    -- The tips of the visit invoice held for the specialist on a liability account (never
    -- revenue); FIN-03 lets a payable accrual name only expense or asset lines, so they are
    -- recorded here and paid out by a ledger entry.
    tips_account_id uuid,
    tips_minor bigint not null default 0 constraint visit_commissions_tips_check
        check (tips_minor between 0 and 999999999999),
    created_by uuid not null references gba.users(id),
    created_at timestamptz not null default now(),
    primary key (tenant_id, booking_id),
    unique (tenant_id, book_id, document_id),
    foreign key (tenant_id, booking_id) references gba.bookings (tenant_id, id),
    foreign key (tenant_id, book_id, document_id)
        references gba.financial_documents (tenant_id, book_id, id),
    constraint visit_commissions_tips_account_check
        check (tips_account_id is not null or tips_minor = 0)
);
alter table gba.commission_plans enable row level security;
alter table gba.commission_plans force row level security;
alter table gba.commission_rules enable row level security;
alter table gba.commission_rules force row level security;
alter table gba.visit_commissions enable row level security;
alter table gba.visit_commissions force row level security;
create policy commission_plans_tenant_isolation on gba.commission_plans
    using (tenant_id = gba.current_tenant_id())
    with check (tenant_id = gba.current_tenant_id());
create policy commission_rules_tenant_isolation on gba.commission_rules
    using (tenant_id = gba.current_tenant_id())
    with check (tenant_id = gba.current_tenant_id());
create policy visit_commissions_tenant_isolation on gba.visit_commissions
    using (tenant_id = gba.current_tenant_id())
    with check (tenant_id = gba.current_tenant_id());
grant select, insert, update on gba.commission_plans to gba_runtime;
grant select, insert, delete on gba.commission_rules to gba_runtime;
grant select, insert on gba.visit_commissions to gba_runtime;

-- Commission branch scope:
create policy commission_plans_location_scope on gba.commission_plans
    as restrictive to gba_runtime
    using (gba.current_location_id() is null or exists (
        select 1 from gba.resources r
        where r.tenant_id = commission_plans.tenant_id and r.id = commission_plans.resource_id))
    with check (gba.current_location_id() is null or exists (
        select 1 from gba.resources r
        where r.tenant_id = commission_plans.tenant_id and r.id = commission_plans.resource_id));
create policy commission_rules_location_scope on gba.commission_rules
    as restrictive to gba_runtime
    using (gba.current_location_id() is null or exists (
        select 1 from gba.resources r
        where r.tenant_id = commission_rules.tenant_id and r.id = commission_rules.resource_id))
    with check (gba.current_location_id() is null or exists (
        select 1 from gba.resources r
        where r.tenant_id = commission_rules.tenant_id and r.id = commission_rules.resource_id));
create policy visit_commissions_location_scope on gba.visit_commissions
    as restrictive to gba_runtime
    using (gba.current_location_id() is null or exists (
        select 1 from gba.bookings b
        where b.tenant_id = visit_commissions.tenant_id and b.id = visit_commissions.booking_id))
    with check (gba.current_location_id() is null or exists (
        select 1 from gba.bookings b
        where b.tenant_id = visit_commissions.tenant_id and b.id = visit_commissions.booking_id));
