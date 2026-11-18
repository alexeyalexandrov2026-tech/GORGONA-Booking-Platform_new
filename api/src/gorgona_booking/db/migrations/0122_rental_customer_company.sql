-- RENT-01 R-09: keep the booking's customer-company binding and every revision.
create table gba.rental_customer_companies (
    tenant_id uuid not null references gba.tenants(id),
    booking_id uuid not null,
    revision integer not null check (revision > 0),
    customer_id uuid not null,
    company_id uuid,
    created_by uuid not null references gba.users(id),
    created_at timestamptz not null default now(),
    primary key (tenant_id, booking_id, revision),
    foreign key (tenant_id, booking_id) references gba.rental_bookings(tenant_id, id),
    foreign key (tenant_id, customer_id) references gba.counterparties(tenant_id, id),
    constraint rental_customer_company_recipient foreign key (company_id) references gba.tenants(id),
    constraint rental_customer_company_separate check (company_id <> tenant_id)
);

create function gba.guard_rental_customer_company() returns trigger language plpgsql as $$
declare
    booking_customer uuid;
begin
    perform gba.lock_rental_booking_class(new.tenant_id, new.booking_id);
    select b.customer_id into booking_customer
    from gba.rental_bookings b where (b.tenant_id, b.id) = (new.tenant_id, new.booking_id);
    if booking_customer is distinct from new.customer_id or exists (
        select 1 from gba.rental_booking_cancellations c
        where (c.tenant_id, c.booking_id) = (new.tenant_id, new.booking_id)
    ) then
        raise exception using errcode = 'check_violation',
            constraint = 'rental_customer_company_booking',
            message = 'The company binding must name the customer on an open booking';
    end if;
    if new.created_by is distinct from gba.current_user_id() then
        raise exception using errcode = 'check_violation',
            constraint = 'rental_customer_company_author',
            message = 'The company binding must name the authenticated editor';
    end if;
    if new.revision <> coalesce((
        select max(c.revision) from gba.rental_customer_companies c
        where (c.tenant_id, c.booking_id) = (new.tenant_id, new.booking_id)
    ), 0) + 1 then
        raise exception using errcode = 'check_violation',
            constraint = 'rental_customer_company_revision',
            message = 'The company binding revision changed';
    end if;
    return new;
end;
$$;
revoke all on function gba.guard_rental_customer_company() from public;

create trigger rental_customer_companies_guard
    before insert on gba.rental_customer_companies
    for each row execute function gba.guard_rental_customer_company();
create trigger rental_customer_companies_module_gate
    before insert on gba.rental_customer_companies
    for each row execute function gba.require_enabled_module('rental');

alter table gba.rental_customer_companies enable row level security;
alter table gba.rental_customer_companies force row level security;
create policy rental_customer_companies_tenant on gba.rental_customer_companies
    using (tenant_id = gba.current_tenant_id() and exists (
        select 1 from gba.rental_bookings b
        where (b.tenant_id, b.id) = (
            rental_customer_companies.tenant_id, rental_customer_companies.booking_id)
    ))
    with check (tenant_id = gba.current_tenant_id() and gba.current_location_id() is null);

grant select on gba.rental_customer_companies to gba_runtime;
grant insert (tenant_id, booking_id, revision, customer_id, company_id, created_by)
    on gba.rental_customer_companies to gba_runtime;
