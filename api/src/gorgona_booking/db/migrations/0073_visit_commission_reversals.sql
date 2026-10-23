-- L9b (package L, BEAUTY-01): the reversal of a visit's commission after a refund. Design
-- docs/plan/PACKAGE_L9_DESIGN_2026-10-23.md decisions 81-84. One permanent row per refund credit
-- of the visit invoice, naming the FIN-03 credit note of the commission accrual that reversed its
-- share (none when the refund touched no service line).
create table gba.visit_commission_reversals (
    tenant_id uuid not null references gba.tenants(id),
    book_id uuid not null,
    refund_document_id uuid not null,
    booking_id uuid not null,
    reversal_document_id uuid,
    amount_minor bigint not null constraint visit_commission_reversals_amount_check
        check (amount_minor between 0 and 999999999999),
    created_by uuid not null references gba.users(id),
    created_at timestamptz not null default now(),
    primary key (tenant_id, book_id, refund_document_id),
    foreign key (tenant_id, booking_id) references gba.visit_commissions (tenant_id, booking_id),
    foreign key (tenant_id, book_id, refund_document_id)
        references gba.financial_documents (tenant_id, book_id, id),
    foreign key (tenant_id, book_id, reversal_document_id)
        references gba.financial_documents (tenant_id, book_id, id),
    constraint visit_commission_reversals_document_check
        check ((reversal_document_id is null) = (amount_minor = 0))
);
alter table gba.visit_commission_reversals enable row level security;
alter table gba.visit_commission_reversals force row level security;
create policy visit_commission_reversals_tenant_isolation on gba.visit_commission_reversals
    using (tenant_id = gba.current_tenant_id())
    with check (tenant_id = gba.current_tenant_id());
grant select, insert on gba.visit_commission_reversals to gba_runtime;

-- Visit branch scope:
create policy visit_commission_reversals_location_scope on gba.visit_commission_reversals
    as restrictive to gba_runtime
    using (gba.current_location_id() is null or exists (
        select 1 from gba.bookings b
        where b.tenant_id = visit_commission_reversals.tenant_id
          and b.id = visit_commission_reversals.booking_id))
    with check (gba.current_location_id() is null or exists (
        select 1 from gba.bookings b
        where b.tenant_id = visit_commission_reversals.tenant_id
          and b.id = visit_commission_reversals.booking_id));
