-- RENT-01 R-09: problem reports on a rental booking. A customer company reports through its live grant
-- (source platform, with the grant and the binding it answered under); otherwise the business records
-- the report with its source and the name of the person who reported it.
create table gba.rental_problem_reports (
    tenant_id uuid not null references gba.tenants(id),
    booking_id uuid not null,
    number integer not null constraint rental_problem_reports_number_check check (number > 0),
    kind text not null constraint rental_problem_reports_kind_check
        check (kind in ('breakdown', 'damage', 'accident', 'other')),
    description text not null constraint rental_problem_reports_description_check
        check (length(btrim(description)) between 1 and 2000),
    occurred_at timestamptz not null constraint rental_problem_reports_occurred_check
        check (occurred_at >= timestamptz '2000-01-01 00:00:00+00'),
    source text not null constraint rental_problem_reports_source_check
        check (source in ('platform', 'phone', 'email', 'paper')),
    reported_by text constraint rental_problem_reports_reported_by_check
        check (reported_by is null or length(btrim(reported_by)) between 1 and 200),
    company_id uuid,
    grant_id uuid,
    binding_revision integer,
    recorded_by uuid not null references gba.users(id),
    created_at timestamptz not null default now(),
    primary key (tenant_id, booking_id, number),
    foreign key (tenant_id, booking_id) references gba.rental_bookings(tenant_id, id),
    foreign key (tenant_id, booking_id, binding_revision)
        references gba.rental_customer_companies(tenant_id, booking_id, revision),
    foreign key (tenant_id, grant_id, company_id)
        references gba.delegation_grants(owner_tenant_id, id, servicer_tenant_id),
    constraint rental_problem_reports_proof_check check (
        (source = 'platform' and reported_by is null and company_id is not null
            and grant_id is not null and binding_revision is not null)
        or
        (source <> 'platform' and reported_by is not null and company_id is null
            and grant_id is null and binding_revision is null)
    )
);

-- A report follows the earlier ones of its booking under the booking's class lock, on a booking that is
-- not cancelled, for a moment that has already happened. A platform report needs the recording user to be
-- a current member of a live grant with rental.customer_answer for this business, the booking's current
-- customer company and a visible branch, as the R-09 acceptance proof does (0123).
create function gba.guard_rental_problem_report() returns trigger
language plpgsql security definer set search_path = pg_catalog as $$
declare
    visible_location uuid;
begin
    perform gba.lock_rental_booking_class(new.tenant_id, new.booking_id);
    if new.number <> 1 + coalesce((select max(r.number) from gba.rental_problem_reports r
        where (r.tenant_id, r.booking_id) = (new.tenant_id, new.booking_id)), 0) then
        raise exception using errcode = 'check_violation',
            constraint = 'rental_problem_reports_sequence_check',
            message = 'problem reports are numbered 1, 2, 3 per booking';
    end if;
    if exists (select 1 from gba.rental_booking_cancellations c
        where (c.tenant_id, c.booking_id) = (new.tenant_id, new.booking_id)) then
        raise exception using errcode = 'check_violation',
            constraint = 'rental_problem_reports_booking_check',
            message = 'a cancelled booking takes no problem report';
    end if;
    if new.occurred_at > pg_catalog.transaction_timestamp() then
        raise exception using errcode = 'check_violation',
            constraint = 'rental_problem_reports_time_check',
            message = 'a problem is reported after it happened';
    end if;
    if new.tenant_id is distinct from gba.current_tenant_id()
        or new.recorded_by is distinct from gba.current_user_id()
        or new.created_at is distinct from pg_catalog.transaction_timestamp() then
        raise exception using errcode = 'check_violation',
            constraint = 'rental_problem_reports_customer_scope',
            message = 'the report is recorded by the current user now';
    end if;
    if new.source <> 'platform' then
        return new;
    end if;

    select g.location_id into visible_location
    from gba.delegation_grants g
    join gba.delegation_grant_members m
      on (m.owner_tenant_id, m.grant_id, m.servicer_tenant_id)
       = (g.owner_tenant_id, g.id, g.servicer_tenant_id)
    where (g.owner_tenant_id, g.id, g.servicer_tenant_id)
        = (new.tenant_id, new.grant_id, new.company_id)
      and m.user_id = new.recorded_by and m.removed_at is null
      and g.status = 'active' and g.expires_at > pg_catalog.clock_timestamp()
      and 'rental.customer_answer' = any(g.permissions)
    for share of g, m;
    if not found then
        raise exception using errcode = 'check_violation',
            constraint = 'rental_problem_reports_customer_scope',
            message = 'Customer grant does not authorize this booking';
    end if;
    if not exists (
        select 1
        from gba.rental_bookings b
        join lateral (
            select c.customer_id, c.revision, c.company_id
            from gba.rental_customer_companies c
            where (c.tenant_id, c.booking_id) = (b.tenant_id, b.id)
            order by c.revision desc limit 1
        ) binding on binding.customer_id = b.customer_id
        where (b.tenant_id, b.id) = (new.tenant_id, new.booking_id)
          and (visible_location is null or visible_location = b.pickup_location_id)
          and (binding.company_id, binding.revision) = (new.company_id, new.binding_revision)
    ) then
        raise exception using errcode = 'check_violation',
            constraint = 'rental_problem_reports_customer_scope',
            message = 'Customer grant does not authorize this booking';
    end if;
    return new;
end;
$$;
revoke all on function gba.guard_rental_problem_report() from public;

create trigger rental_problem_reports_guard
    before insert on gba.rental_problem_reports
    for each row execute function gba.guard_rental_problem_report();

-- Writes need the rental module (ADR-0019 gate).
create trigger rental_problem_reports_module_gate
    before insert on gba.rental_problem_reports
    for each row execute function gba.require_enabled_module('rental');

alter table gba.rental_problem_reports enable row level security;
alter table gba.rental_problem_reports force row level security;
create policy rental_problem_reports_tenant_isolation on gba.rental_problem_reports
    using (tenant_id = gba.current_tenant_id())
    with check (tenant_id = gba.current_tenant_id());
grant select on gba.rental_problem_reports to gba_runtime;
grant insert (tenant_id, booking_id, number, kind, description, occurred_at, source, reported_by,
              company_id, grant_id, binding_revision, recorded_by)
    on gba.rental_problem_reports to gba_runtime;

-- Rental branch scope:
create policy rental_problem_reports_location_scope on gba.rental_problem_reports
    as restrictive to gba_runtime
    using (gba.current_location_id() is null or exists (
        select 1 from gba.rental_bookings b
        where b.tenant_id = rental_problem_reports.tenant_id and b.id = rental_problem_reports.booking_id))
    with check (gba.current_location_id() is null or exists (
        select 1 from gba.rental_bookings b
        where b.tenant_id = rental_problem_reports.tenant_id and b.id = rental_problem_reports.booking_id));
