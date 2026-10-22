-- L6 (package L, BEAUTY-01): prepaid packages and gift certificates.
-- Design docs/plan/PACKAGE_L6_DESIGN_2026-10-22.md. A balance is sold by a FIN-03 invoice line on a
-- prepayment liability; each redemption is a FIN-03 credit note of a visit invoice. What is used
-- only grows and never passes what was sold; a balance is redeemed once per visit.

create table gba.prepaid_balances (
    tenant_id uuid not null references gba.tenants(id),
    id uuid not null,
    kind text not null constraint prepaid_balances_kind_check
        check (kind in ('package', 'certificate')),
    counterparty_id uuid not null,
    variant_id uuid,
    units integer constraint prepaid_balances_units_check check (units between 1 and 1000),
    price_minor bigint not null constraint prepaid_balances_price_check
        check (price_minor between 1 and 999999999999),
    currency text not null references gba.currencies(code),
    book_id uuid not null,
    sale_document_id uuid not null,
    prepayment_account_id uuid not null,
    used_units integer not null default 0,
    used_minor bigint not null default 0,
    created_by uuid not null references gba.users(id),
    created_at timestamptz not null default now(),
    primary key (tenant_id, id),
    unique (tenant_id, book_id, sale_document_id),
    foreign key (tenant_id, counterparty_id) references gba.counterparties (tenant_id, id),
    foreign key (tenant_id, variant_id) references gba.service_variants (tenant_id, id),
    foreign key (tenant_id, book_id, sale_document_id)
        references gba.financial_documents (tenant_id, book_id, id),
    constraint prepaid_balances_shape_check check (
        (kind = 'package') = (variant_id is not null and units is not null)),
    constraint prepaid_balances_used_check check (
        used_minor between 0 and price_minor
        and used_units between 0 and coalesce(units, 0))
);
create table gba.prepaid_redemptions (
    tenant_id uuid not null references gba.tenants(id),
    prepaid_id uuid not null,
    booking_id uuid not null,
    units smallint not null constraint prepaid_redemptions_units_check check (units in (0, 1)),
    amount_minor bigint not null constraint prepaid_redemptions_amount_check
        check (amount_minor between 1 and 999999999999),
    book_id uuid not null,
    credit_document_id uuid not null,
    created_by uuid not null references gba.users(id),
    created_at timestamptz not null default now(),
    primary key (tenant_id, prepaid_id, booking_id),
    unique (tenant_id, book_id, credit_document_id),
    foreign key (tenant_id, prepaid_id) references gba.prepaid_balances (tenant_id, id),
    foreign key (tenant_id, booking_id) references gba.bookings (tenant_id, id),
    foreign key (tenant_id, book_id, credit_document_id)
        references gba.financial_documents (tenant_id, book_id, id)
);

-- What is used only grows, by exactly the redemption written in the same transaction.
create function gba.guard_prepaid_use() returns trigger language plpgsql as $$
begin
    if new.used_units < old.used_units or new.used_minor <= old.used_minor
       or (new.tenant_id, new.id, new.kind, new.counterparty_id, new.variant_id, new.units,
           new.price_minor, new.currency, new.book_id, new.sale_document_id,
           new.prepayment_account_id, new.created_by, new.created_at)
          is distinct from
          (old.tenant_id, old.id, old.kind, old.counterparty_id, old.variant_id, old.units,
           old.price_minor, old.currency, old.book_id, old.sale_document_id,
           old.prepayment_account_id, old.created_by, old.created_at)
       or not exists (
           select 1 from gba.prepaid_redemptions r
           where r.tenant_id = new.tenant_id and r.prepaid_id = new.id
             and r.created_at = pg_catalog.now()
             and r.units = new.used_units - old.used_units
             and r.amount_minor = new.used_minor - old.used_minor) then
        raise exception using errcode = 'check_violation',
            constraint = 'prepaid_balances_use_check',
            message = 'a prepaid balance is used only by its redemption';
    end if;
    return new;
end;
$$;
revoke all on function gba.guard_prepaid_use() from public;
create trigger prepaid_balances_use_guard
    before update on gba.prepaid_balances
    for each row execute function gba.guard_prepaid_use();

alter table gba.prepaid_balances enable row level security;
alter table gba.prepaid_balances force row level security;
alter table gba.prepaid_redemptions enable row level security;
alter table gba.prepaid_redemptions force row level security;
create policy prepaid_balances_tenant_isolation on gba.prepaid_balances
    using (tenant_id = gba.current_tenant_id())
    with check (tenant_id = gba.current_tenant_id());
create policy prepaid_redemptions_tenant_isolation on gba.prepaid_redemptions
    using (tenant_id = gba.current_tenant_id())
    with check (tenant_id = gba.current_tenant_id());
grant select, insert on gba.prepaid_balances, gba.prepaid_redemptions to gba_runtime;
grant update (used_units, used_minor) on gba.prepaid_balances to gba_runtime;

-- Prepaid branch scope:
create policy prepaid_redemptions_location_scope on gba.prepaid_redemptions
    as restrictive to gba_runtime
    using (gba.current_location_id() is null or exists (
        select 1 from gba.bookings b
        where b.tenant_id = prepaid_redemptions.tenant_id and b.id = prepaid_redemptions.booking_id))
    with check (gba.current_location_id() is null or exists (
        select 1 from gba.bookings b
        where b.tenant_id = prepaid_redemptions.tenant_id and b.id = prepaid_redemptions.booking_id));
