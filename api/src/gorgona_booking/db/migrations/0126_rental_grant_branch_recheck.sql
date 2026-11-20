-- RENT-01 R-09 review: the 0123 and 0125 guards recheck the live customer grant in every session,
-- also in a delegate's branch-scoped session, and still run with the caller's own rights.
-- Until now the 0012 branch scope hid every grant and delegate row from a branch-scoped session, so
-- the guards skipped the recheck there; the foreign key ignores row security, so a platform row
-- naming a revoked or expired grant, a grant of another branch or a recording user who is no
-- delegate was accepted in that session (no API route wrote such a row).
--
-- The acceptance guard (0123) now always requires a live grant with rental.customer_answer whose
-- current delegate is the recording user; in a branch-scoped session the grant must be of that
-- branch. The error message and the constraint name are unchanged.
create or replace function gba.guard_rental_agreement_customer_proof() returns trigger
language plpgsql as $$
declare
    visible_location uuid;
    current_booking uuid;
begin
    if new.source <> 'platform' then
        return new;
    end if;
    if new.tenant_id is distinct from gba.current_tenant_id()
        or new.recorded_by is distinct from gba.current_user_id()
        or new.accepted_at is distinct from pg_catalog.transaction_timestamp()
    then
        raise exception using errcode = 'check_violation',
            constraint = 'rental_agreement_customer_scope',
            message = 'Customer grant does not authorize this booking';
    end if;

    select g.location_id into visible_location
    from gba.delegation_grants g
    join gba.delegation_grant_members m
      on (m.owner_tenant_id, m.grant_id, m.servicer_tenant_id)
       = (g.owner_tenant_id, g.id, g.servicer_tenant_id)
    where (g.owner_tenant_id, g.id, g.servicer_tenant_id)
        = (new.tenant_id, new.customer_grant_id, new.customer_company_id)
      and m.user_id = new.recorded_by and m.removed_at is null
      and g.status = 'active' and g.expires_at > pg_catalog.clock_timestamp()
      and 'rental.customer_answer' = any(g.permissions)
      and (gba.current_location_id() is null
           or g.location_id is not distinct from gba.current_location_id());
    if not found then
        raise exception using errcode = 'check_violation',
            constraint = 'rental_agreement_customer_scope',
            message = 'Customer grant does not authorize this booking';
    end if;

    select a.booking_id into current_booking from gba.rental_agreements a
    where (a.tenant_id, a.id) = (new.tenant_id, new.agreement_id);
    perform gba.lock_rental_booking_class(new.tenant_id, current_booking);
    if not exists (
        select 1
        from gba.rental_bookings b
        join lateral (
            select c.customer_id, c.revision, c.company_id
            from gba.rental_customer_companies c
            where (c.tenant_id, c.booking_id) = (b.tenant_id, b.id)
            order by c.revision desc limit 1
        ) binding on binding.customer_id = b.customer_id
        where (b.tenant_id, b.id) = (new.tenant_id, current_booking)
          and (visible_location is null or visible_location = b.pickup_location_id)
          and (binding.company_id, binding.revision)
            = (new.customer_company_id, new.customer_binding_revision)
    ) then
        raise exception using errcode = 'check_violation',
            constraint = 'rental_agreement_customer_scope',
            message = 'Customer grant does not authorize this booking';
    end if;

    return new;
end;
$$;
revoke all on function gba.guard_rental_agreement_customer_proof() from public;

-- The problem report guard (0125) makes the same recheck for every platform report.
create or replace function gba.guard_rental_problem_report() returns trigger
language plpgsql as $$
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
      and (gba.current_location_id() is null
           or g.location_id is not distinct from gba.current_location_id());
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

-- The 0012 branch scope is replaced: in a branch-scoped session reads see the session user's own
-- live delegate rows of the current business and the grants of that business at the current
-- branch that the user is a live delegate of. A branch-scoped employee who is no delegate still
-- sees no grant and no delegate row. Writes keep the 0012 rule: none from a branch-scoped session.
-- The runtime role has no delete privilege on either table (0012).
drop policy delegation_grants_unrestricted_scope on gba.delegation_grants;
drop policy delegation_grant_members_unrestricted_scope on gba.delegation_grant_members;

-- Delegation branch scope (0126): reusable separately when restoring a damaged boundary in tests.
create policy delegation_grant_members_delegate_scope on gba.delegation_grant_members
    as restrictive for select to gba_runtime
    using (gba.current_location_id() is null
           or (owner_tenant_id = gba.current_tenant_id()
               and user_id = gba.current_user_id()
               and removed_at is null));
create policy delegation_grant_members_unrestricted_insert on gba.delegation_grant_members
    as restrictive for insert to gba_runtime
    with check (gba.current_location_id() is null);
create policy delegation_grant_members_unrestricted_update on gba.delegation_grant_members
    as restrictive for update to gba_runtime
    using (gba.current_location_id() is null)
    with check (gba.current_location_id() is null);
create policy delegation_grants_delegate_scope on gba.delegation_grants
    as restrictive for select to gba_runtime
    using (gba.current_location_id() is null
           or (owner_tenant_id = gba.current_tenant_id()
               and location_id = gba.current_location_id()
               and exists (
                   select 1 from gba.delegation_grant_members m
                   where m.owner_tenant_id = delegation_grants.owner_tenant_id
                     and m.grant_id = delegation_grants.id
                     and m.servicer_tenant_id = delegation_grants.servicer_tenant_id
                     and m.user_id = gba.current_user_id()
                     and m.removed_at is null)));
create policy delegation_grants_unrestricted_insert on gba.delegation_grants
    as restrictive for insert to gba_runtime
    with check (gba.current_location_id() is null);
create policy delegation_grants_unrestricted_update on gba.delegation_grants
    as restrictive for update to gba_runtime
    using (gba.current_location_id() is null)
    with check (gba.current_location_id() is null);
