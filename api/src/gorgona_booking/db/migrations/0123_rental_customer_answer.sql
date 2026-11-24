-- RENT-01 R-09: a platform acceptance records its active grant, binding and reviewed terms.
alter table gba.delegation_grants drop constraint delegation_grants_permissions_check;
alter table gba.delegation_grants add constraint delegation_grants_permissions_check check (
    cardinality(permissions) between 1 and 9
    and permissions <@ array['booking.read','booking.write','catalog.read','staff.read',
                             'transport.read','transport.plan','transport.assign','transport.events',
                             'transport.tender','construction.customer_answer','rental.customer_answer']
);

alter table gba.rental_agreement_versions
    add column customer_company_id uuid,
    add column customer_grant_id uuid,
    add column customer_binding_revision integer,
    add column customer_review_hash text,
    add foreign key (tenant_id, customer_grant_id, customer_company_id)
        references gba.delegation_grants(owner_tenant_id, id, servicer_tenant_id),
    add constraint rental_agreement_customer_proof check (
        (source = 'platform' and version = 1 and customer_company_id is not null
            and customer_grant_id is not null and customer_binding_revision is not null
            and customer_binding_revision > 0 and customer_review_hash is not null
            and customer_review_hash ~ '^[0-9a-f]{64}$')
        or
        (source <> 'platform' and customer_company_id is null and customer_grant_id is null
            and customer_binding_revision is null and customer_review_hash is null)
    ) not valid;

-- Authorization locks the active grant, checks its member and permission and applies its branch
-- scope before this trigger runs, as for construction answers (0119). The foreign key ties the
-- grant to its recipient company. The trigger runs with the caller's own row security: it binds
-- the row to the active tenant, the recorded user and this moment, rechecks the grant and its
-- delegate where the session can read them, takes the booking class lock and requires the
-- booking's current customer binding; a branch-scoped caller sees only bookings of its branch.
create function gba.guard_rental_agreement_customer_proof() returns trigger language plpgsql as $$
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

    -- Company-wide sessions can read the grant tables: require a live grant with
    -- rental.customer_answer whose current delegate is the recording user. A branch-scoped
    -- session cannot read them (0012); authorization has locked and checked the grant there.
    if gba.current_location_id() is null then
        select g.location_id into visible_location
        from gba.delegation_grants g
        join gba.delegation_grant_members m
          on (m.owner_tenant_id, m.grant_id, m.servicer_tenant_id)
           = (g.owner_tenant_id, g.id, g.servicer_tenant_id)
        where (g.owner_tenant_id, g.id, g.servicer_tenant_id)
            = (new.tenant_id, new.customer_grant_id, new.customer_company_id)
          and m.user_id = new.recorded_by and m.removed_at is null
          and g.status = 'active' and g.expires_at > pg_catalog.clock_timestamp()
          and 'rental.customer_answer' = any(g.permissions);
        if not found then
            raise exception using errcode = 'check_violation',
                constraint = 'rental_agreement_customer_scope',
                message = 'Customer grant does not authorize this booking';
        end if;
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

create trigger rental_agreement_customer_proof_guard
    before insert on gba.rental_agreement_versions
    for each row execute function gba.guard_rental_agreement_customer_proof();
