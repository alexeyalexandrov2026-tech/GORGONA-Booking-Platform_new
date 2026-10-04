-- Explicitly authorized branch work adds a restrictive boundary to tenant RLS.
-- Empty scope preserves existing tenant-wide, public and worker transactions.
-- No privileged functions, copied data or alternative booking engine.
create function gba.current_location_id() returns uuid
    language sql stable parallel safe
as $$
    select nullif(pg_catalog.current_setting('gba.location_id', true), '')::uuid
$$;
revoke all on function gba.current_location_id() from public;
grant execute on function gba.current_location_id() to gba_runtime;

create policy locations_location_scope on gba.locations as restrictive to gba_runtime
    using (gba.current_location_id() is null or id = gba.current_location_id())
    with check (gba.current_location_id() is null or id = gba.current_location_id());

do $$
declare table_name text;
begin
    foreach table_name in array array['resources', 'bookings', 'business_hours'] loop
        execute format(
            'create policy %I on gba.%I as restrictive to gba_runtime '
            'using (gba.current_location_id() is null or location_id = gba.current_location_id()) '
            'with check (gba.current_location_id() is null or location_id = gba.current_location_id())',
            table_name || '_location_scope', table_name);
    end loop;
    foreach table_name in array array['resource_services', 'resource_hours', 'resource_blocks'] loop
        execute format(
            'create policy %I on gba.%I as restrictive to gba_runtime '
            'using (gba.current_location_id() is null or exists '
            '(select 1 from gba.resources r where r.tenant_id = %I.tenant_id and r.id = %I.resource_id)) '
            'with check (gba.current_location_id() is null or exists '
            '(select 1 from gba.resources r where r.tenant_id = %I.tenant_id and r.id = %I.resource_id))',
            table_name || '_location_scope', table_name,
            table_name, table_name, table_name, table_name);
    end loop;
    foreach table_name in array array['booking_customers', 'booking_events'] loop
        execute format(
            'create policy %I on gba.%I as restrictive to gba_runtime '
            'using (gba.current_location_id() is null or exists '
            '(select 1 from gba.bookings b where b.tenant_id = %I.tenant_id and b.id = %I.booking_id)) '
            'with check (gba.current_location_id() is null or exists '
            '(select 1 from gba.bookings b where b.tenant_id = %I.tenant_id and b.id = %I.booking_id))',
            table_name || '_location_scope', table_name,
            table_name, table_name, table_name, table_name);
    end loop;
    -- Company configuration has no branch owner. Keep it outside scoped work.
    foreach table_name in array array[
        'business_profile_versions', 'business_profile_industries', 'business_profile_formats',
        'salon_fact_confirmations', 'tenant_embed_origins', 'invitations'
    ] loop
        execute format(
            'create policy %I on gba.%I as restrictive to gba_runtime '
            'using (gba.current_location_id() is null) with check (gba.current_location_id() is null)',
            table_name || '_unrestricted_scope', table_name);
    end loop;
end;
$$;

create policy booking_allocations_location_scope on gba.booking_allocations
    as restrictive to gba_runtime
    using (gba.current_location_id() is null or (
        exists (select 1 from gba.bookings b
                where b.tenant_id = booking_allocations.tenant_id and b.id = booking_id)
        and exists (select 1 from gba.resources r
                    where r.tenant_id = booking_allocations.tenant_id and r.id = resource_id)))
    with check (gba.current_location_id() is null or (
        exists (select 1 from gba.bookings b
                where b.tenant_id = booking_allocations.tenant_id and b.id = booking_id)
        and exists (select 1 from gba.resources r
                    where r.tenant_id = booking_allocations.tenant_id and r.id = resource_id)));

-- Historical company audit events lack a trusted location. Do not infer one
-- from arbitrary JSON. Inserts from existing triggers still record the audit.
create policy audit_events_unrestricted_read on gba.audit_events
    as restrictive for select to gba_runtime using (gba.current_location_id() is null);

-- A company owner can invite a colleague directly into one branch. Existing
-- invitations remain unrestricted. The grant cannot be widened after issuance.
alter table gba.invitations add column location_id uuid,
    add constraint invitations_location_fk foreign key (tenant_id, location_id)
        references gba.locations (tenant_id, id);

create function gba.enforce_invitation_location() returns trigger language plpgsql as $$
begin
    if new.location_id is distinct from old.location_id then
        raise exception using errcode = 'check_violation',
            message = 'invitation location is immutable',
            constraint = 'invitations_location_immutable';
    end if;
    return new;
end;
$$;
revoke all on function gba.enforce_invitation_location() from public;
create trigger invitations_enforce_location before update on gba.invitations
    for each row execute function gba.enforce_invitation_location();
