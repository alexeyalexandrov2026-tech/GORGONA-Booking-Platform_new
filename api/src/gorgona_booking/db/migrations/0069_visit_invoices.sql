-- L4 (package L, BEAUTY-01): one FIN-03 invoice per visit.
-- Design docs/plan/PACKAGE_L4_DESIGN_2026-10-22.md. The link is permanent: a visit names its
-- invoice once and a document belongs to one visit at most. The invoice itself, its issue and its
-- payments are FIN-03's own tables and rules.

create table gba.visit_invoices (
    tenant_id uuid not null references gba.tenants(id),
    booking_id uuid not null,
    book_id uuid not null,
    document_id uuid not null,
    created_by uuid not null references gba.users(id),
    created_at timestamptz not null default now(),
    primary key (tenant_id, booking_id),
    unique (tenant_id, book_id, document_id),
    foreign key (tenant_id, booking_id) references gba.bookings (tenant_id, id),
    foreign key (tenant_id, book_id, document_id)
        references gba.financial_documents (tenant_id, book_id, id)
);
alter table gba.visit_invoices enable row level security;
alter table gba.visit_invoices force row level security;
create policy visit_invoices_tenant_isolation on gba.visit_invoices
    using (tenant_id = gba.current_tenant_id())
    with check (tenant_id = gba.current_tenant_id());
grant select, insert on gba.visit_invoices to gba_runtime;

-- Visit invoice branch scope:
create policy visit_invoices_location_scope on gba.visit_invoices
    as restrictive to gba_runtime
    using (gba.current_location_id() is null or exists (
        select 1 from gba.bookings b
        where b.tenant_id = visit_invoices.tenant_id and b.id = visit_invoices.booking_id))
    with check (gba.current_location_id() is null or exists (
        select 1 from gba.bookings b
        where b.tenant_id = visit_invoices.tenant_id and b.id = visit_invoices.booking_id));
