-- N5 (package N): the carrier's pay is one FIN-03 payable per accepted tender (ADR-0033 extended).
-- docs/plan/PACKAGE_N5_DESIGN_2026-10-28.md. One row per tender links its manual accrual document and the
-- rate confirmation revision it was booked for; the margin per order is derived, never stored.
create table gba.transport_tender_accruals (
    tenant_id uuid not null references gba.tenants(id),
    tender_id uuid not null,
    revision integer not null constraint transport_tender_accruals_revision_check
        check (revision > 0),
    miles numeric(9, 1) constraint transport_tender_accruals_miles_check
        check (miles is null or miles > 0),
    book_id uuid not null,
    document_id uuid not null,
    created_by uuid not null references gba.users(id),
    created_at timestamptz not null default now(),
    primary key (tenant_id, tender_id),
    unique (tenant_id, book_id, document_id),
    foreign key (tenant_id, tender_id, revision)
        references gba.transport_rate_confirmations (tenant_id, tender_id, revision),
    foreign key (tenant_id, book_id, document_id)
        references gba.financial_documents (tenant_id, book_id, id)
);

-- Writes need the transport module (ADR-0019 gate).
create trigger transport_tender_accruals_module_gate
    before insert on gba.transport_tender_accruals
    for each row execute function gba.require_enabled_module('transport');

alter table gba.transport_tender_accruals enable row level security;
alter table gba.transport_tender_accruals force row level security;
create policy transport_tender_accruals_tenant_isolation on gba.transport_tender_accruals
    using (tenant_id = gba.current_tenant_id())
    with check (tenant_id = gba.current_tenant_id());
grant select on gba.transport_tender_accruals to gba_runtime;
grant insert (tenant_id, tender_id, revision, miles, book_id, document_id, created_by)
    on gba.transport_tender_accruals to gba_runtime;

-- Carrier pay branch scope: brokerage is company-wide; a branch-limited session sees none of it.
create policy transport_tender_accruals_company on gba.transport_tender_accruals
    as restrictive to gba_runtime
    using (gba.current_location_id() is null)
    with check (gba.current_location_id() is null);
