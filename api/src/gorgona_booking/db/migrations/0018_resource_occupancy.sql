-- Shared resource occupancy (ADR-0022, master plan §12.2.1, CORE-04).
-- gba.resource_allocations is the one authoritative occupancy table for every
-- module. Its exclusion constraint rejects two active (held or confirmed)
-- allocations of one resource that overlap, whatever module made them.
-- Booking keeps writing gba.booking_allocations (owner decision: it stays a
-- table until stage 1 closes); triggers mirror every booking allocation and
-- every booking status change into this table in the same transaction, so raw
-- SQL and every booking path go through the shared constraint too. Migrations
-- never bypass row security, so allocations that existed before this migration
-- are copied per company by gba.backfill_booking_occupancy() (operator command
-- `backfill-occupancy`) and checked with gba.booking_occupancy_mismatches().
-- Allocation rows are never deleted; only their state changes.

create table gba.resource_allocations (
    tenant_id uuid not null references gba.tenants (id),
    id uuid not null default uuidv7(),
    resource_id uuid not null,
    source_kind text not null
        constraint resource_allocations_source_kind check (source_kind in ('booking')),
    source_id uuid not null,
    during tstzrange not null,
    state text not null
        constraint resource_allocations_state check (state in ('held', 'confirmed', 'released')),
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    primary key (tenant_id, id),
    constraint resource_allocations_resource_fk
        foreign key (tenant_id, resource_id) references gba.resources (tenant_id, id),
    constraint resource_allocations_one_per_source
        unique (tenant_id, source_kind, source_id, resource_id),
    constraint resource_allocations_half_open check (
        not isempty(during)
        and lower_inc(during) and not upper_inc(during)
        and not lower_inf(during) and not upper_inf(during)
    ),
    constraint resource_allocations_no_overlap
        exclude using gist (tenant_id with =, resource_id with =, during with &&)
        where (state in ('held', 'confirmed'))
);

-- The occupancy state a booking status implies.
create function gba.booking_occupancy_state(status text) returns text
    language sql immutable parallel safe as $$
    select case status when 'HOLD' then 'held' when 'CONFIRMED' then 'confirmed'
                       else 'released' end
$$;
revoke all on function gba.booking_occupancy_state(text) from public;
grant execute on function gba.booking_occupancy_state(text) to gba_runtime;

alter table gba.resource_allocations enable row level security;
alter table gba.resource_allocations force row level security;
create policy resource_allocations_tenant_isolation on gba.resource_allocations
    using (tenant_id = gba.current_tenant_id())
    with check (tenant_id = gba.current_tenant_id());
grant select on gba.resource_allocations to gba_runtime;
grant insert (tenant_id, resource_id, source_kind, source_id, during, state)
    on gba.resource_allocations to gba_runtime;
grant update (state) on gba.resource_allocations to gba_runtime;

-- Rows are kept; identity and interval never change; state moves forward only.
-- A booking allocation must match its booking allocation row and booking status.
create function gba.guard_resource_allocation() returns trigger
    language plpgsql as $$
begin
    if tg_op = 'DELETE' then
        raise exception using errcode = 'check_violation',
            message = 'resource allocations are kept';
    end if;
    if tg_op = 'UPDATE' then
        if (new.tenant_id, new.id, new.resource_id, new.source_kind, new.source_id,
            new.during, new.created_at)
           is distinct from (old.tenant_id, old.id, old.resource_id, old.source_kind,
                             old.source_id, old.during, old.created_at) then
            raise exception using errcode = 'check_violation',
                message = 'an allocation keeps its resource, source and interval';
        end if;
        if new.state is distinct from old.state and not (
            (old.state = 'held' and new.state in ('confirmed', 'released'))
            or (old.state = 'confirmed' and new.state = 'released')
        ) then
            raise exception using errcode = 'check_violation',
                message = 'this allocation state change is not allowed';
        end if;
        new.updated_at := pg_catalog.now();
    end if;
    if new.source_kind = 'booking' and not exists (
        select 1 from gba.booking_allocations a
        where a.tenant_id = new.tenant_id and a.booking_id = new.source_id
          and a.resource_id = new.resource_id and a.during = new.during
          and gba.booking_occupancy_state(a.booking_status) = new.state
    ) then
        raise exception using errcode = 'check_violation',
            message = 'a booking allocation follows its booking';
    end if;
    return new;
end;
$$;
revoke all on function gba.guard_resource_allocation() from public;
create trigger resource_allocations_guard
    before insert or update or delete on gba.resource_allocations
    for each row execute function gba.guard_resource_allocation();

-- Every booking allocation write path goes through the shared table.
create function gba.mirror_booking_allocation() returns trigger
    language plpgsql as $$
begin
    if tg_op = 'INSERT' then
        insert into gba.resource_allocations (tenant_id, resource_id, source_kind, source_id,
                                              during, state)
        values (new.tenant_id, new.resource_id, 'booking', new.booking_id, new.during,
                gba.booking_occupancy_state(new.booking_status));
    elsif new.booking_status is distinct from old.booking_status then
        update gba.resource_allocations r
           set state = gba.booking_occupancy_state(new.booking_status)
         where r.tenant_id = new.tenant_id and r.source_kind = 'booking'
           and r.source_id = new.booking_id and r.resource_id = new.resource_id
           and r.state <> gba.booking_occupancy_state(new.booking_status);
        -- Nothing to update means an allocation from before 0018; the backfill copies
        -- it later with the booking's state. The status cascade runs this trigger in
        -- the foreign-key context, so branch row security never hides the row.
    end if;
    return null;
end;
$$;
revoke all on function gba.mirror_booking_allocation() from public;
create trigger booking_allocations_mirror_occupancy
    after insert or update of booking_status on gba.booking_allocations
    for each row execute function gba.mirror_booking_allocation();

-- Copy the current company's booking allocations that the shared table does not
-- hold yet (from before migration 0018) and move stale copies forward to their
-- booking's state; returns how many rows changed. Safe to repeat. Booking
-- allocations of every company wait while it runs (SHARE lock until commit).
create function gba.backfill_booking_occupancy() returns bigint
    language plpgsql volatile as $$
declare
    copied bigint;
    healed bigint;
begin
    lock table gba.booking_allocations in share mode;
    insert into gba.resource_allocations (tenant_id, resource_id, source_kind, source_id,
                                          during, state)
    select a.tenant_id, a.resource_id, 'booking', a.booking_id, a.during,
           gba.booking_occupancy_state(a.booking_status)
    from gba.booking_allocations a
    where a.tenant_id = gba.current_tenant_id()
      and not exists (
          select 1 from gba.resource_allocations r
          where r.tenant_id = a.tenant_id and r.source_kind = 'booking'
            and r.source_id = a.booking_id and r.resource_id = a.resource_id);
    get diagnostics copied = row_count;
    update gba.resource_allocations r
       set state = gba.booking_occupancy_state(a.booking_status)
      from gba.booking_allocations a
     where r.tenant_id = gba.current_tenant_id() and a.tenant_id = r.tenant_id
       and r.source_kind = 'booking' and r.source_id = a.booking_id
       and r.resource_id = a.resource_id
       and r.state <> gba.booking_occupancy_state(a.booking_status)
       and (r.state = 'held' or gba.booking_occupancy_state(a.booking_status) = 'released');
    get diagnostics healed = row_count;
    return copied + healed;
end;
$$;
revoke all on function gba.backfill_booking_occupancy() from public;

-- Booking allocations of the current company that the shared table does not
-- mirror exactly (0 when consistent). Runs with the caller's row security.
create function gba.booking_occupancy_mismatches() returns bigint
    language sql stable as $$
    select count(*) from gba.booking_allocations a
    full join gba.resource_allocations r
      on r.tenant_id = a.tenant_id and r.source_kind = 'booking'
     and r.source_id = a.booking_id and r.resource_id = a.resource_id
    where (r.id is null or r.source_kind = 'booking')
      and (a.booking_id is null or r.id is null or r.during <> a.during
           or r.state <> gba.booking_occupancy_state(a.booking_status))
$$;
revoke all on function gba.booking_occupancy_mismatches() from public;
grant execute on function gba.booking_occupancy_mismatches() to gba_runtime;

-- Occupancy branch scope: reusable separately when restoring a damaged boundary in tests.
create policy resource_allocations_location_scope on gba.resource_allocations
    as restrictive to gba_runtime
    using (gba.current_location_id() is null or exists (
        select 1 from gba.resources r
        where r.tenant_id = resource_allocations.tenant_id and r.id = resource_id))
    with check (gba.current_location_id() is null or exists (
        select 1 from gba.resources r
        where r.tenant_id = resource_allocations.tenant_id and r.id = resource_id));
