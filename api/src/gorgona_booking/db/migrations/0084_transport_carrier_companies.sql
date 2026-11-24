-- N4 (package N): a carrier on the platform answers in its own company (ADR-0017) and tracks its
-- tendered work with stop events (ADR-0030). docs/plan/PACKAGE_N4_DESIGN_2026-10-28.md.
-- The broker links a carrier counterparty to that company in insert-only versions; the company's
-- delegates answer through a grant with the right transport.tender.
create table gba.transport_carrier_companies (
    tenant_id uuid not null references gba.tenants(id),
    counterparty_id uuid not null,
    revision integer not null constraint transport_carrier_companies_revision_check
        check (revision > 0),
    carrier_business_id uuid references gba.tenants(id),
    created_by uuid not null references gba.users(id),
    created_at timestamptz not null default now(),
    primary key (tenant_id, counterparty_id, revision),
    foreign key (tenant_id, counterparty_id) references gba.counterparties (tenant_id, id),
    constraint transport_carrier_companies_own_check check (carrier_business_id <> tenant_id)
);
create index transport_carrier_companies_business_idx
    on gba.transport_carrier_companies (tenant_id, carrier_business_id);

-- A version follows the previous one; a company is linked to at most one carrier at a time.
create function gba.guard_transport_carrier_company() returns trigger language plpgsql as $$
begin
    perform pg_catalog.pg_advisory_xact_lock(
        pg_catalog.hashtextextended('gba:carrier-company:' || new.tenant_id::text, 0));
    if new.revision <> coalesce((
        select max(c.revision) from gba.transport_carrier_companies c
         where c.tenant_id = new.tenant_id and c.counterparty_id = new.counterparty_id), 0) + 1 then
        raise exception using errcode = 'check_violation',
            constraint = 'transport_carrier_companies_revision_check',
            message = 'a version follows the previous one';
    end if;
    if new.carrier_business_id is not null and exists (
        select 1 from (
            select distinct on (c.counterparty_id) c.counterparty_id, c.carrier_business_id
              from gba.transport_carrier_companies c
             where c.tenant_id = new.tenant_id and c.counterparty_id <> new.counterparty_id
             order by c.counterparty_id, c.revision desc) latest
         where latest.carrier_business_id = new.carrier_business_id) then
        raise exception using errcode = 'check_violation',
            constraint = 'transport_carrier_companies_business_check',
            message = 'a company is linked to one carrier at a time';
    end if;
    return new;
end;
$$;
revoke all on function gba.guard_transport_carrier_company() from public;
create trigger transport_carrier_companies_guard before insert on gba.transport_carrier_companies
    for each row execute function gba.guard_transport_carrier_company();
create trigger transport_carrier_companies_module_gate
    before insert on gba.transport_carrier_companies
    for each row execute function gba.require_enabled_module('transport');

alter table gba.transport_carrier_companies enable row level security;
alter table gba.transport_carrier_companies force row level security;
create policy transport_carrier_companies_tenant_isolation on gba.transport_carrier_companies
    using (tenant_id = gba.current_tenant_id())
    with check (tenant_id = gba.current_tenant_id());
grant select on gba.transport_carrier_companies to gba_runtime;
grant insert (tenant_id, counterparty_id, revision, carrier_business_id, created_by)
    on gba.transport_carrier_companies to gba_runtime;

-- An answer given by the carrier's company through its grant has the source 'platform' and names it.
alter table gba.transport_tender_answers add column servicer_business_id uuid references gba.tenants(id);
alter table gba.transport_tender_answers drop constraint transport_tender_answers_source_check;
alter table gba.transport_tender_answers add constraint transport_tender_answers_source_check check (
    source in ('email', 'phone', 'load_board', 'other', 'platform')
    and (source = 'platform') = (servicer_business_id is not null)
);
grant insert (servicer_business_id) on gba.transport_tender_answers to gba_runtime;
alter table gba.transport_rate_confirmation_answers
    add column servicer_business_id uuid references gba.tenants(id);
alter table gba.transport_rate_confirmation_answers
    drop constraint transport_rate_confirmation_answers_source_check;
alter table gba.transport_rate_confirmation_answers
    add constraint transport_rate_confirmation_answers_source_check check (
    source in ('email', 'phone', 'load_board', 'other', 'platform')
    and (source = 'platform') = (servicer_business_id is not null)
);
grant insert (servicer_business_id) on gba.transport_rate_confirmation_answers to gba_runtime;

-- Grant terms may name transport.tender: the carrier's answers to the tenders addressed to it.
alter table gba.delegation_grants drop constraint delegation_grants_permissions_check;
alter table gba.delegation_grants add constraint delegation_grants_permissions_check check (
    cardinality(permissions) between 1 and 9
    and permissions <@ array['booking.read', 'booking.write', 'catalog.read', 'staff.read',
                             'transport.read', 'transport.plan', 'transport.assign',
                             'transport.events', 'transport.tender']
);

-- Carrier company branch scope: brokerage is company-wide; a branch-limited session sees none of it.
create policy transport_carrier_companies_company on gba.transport_carrier_companies
    as restrictive to gba_runtime
    using (gba.current_location_id() is null)
    with check (gba.current_location_id() is null);
