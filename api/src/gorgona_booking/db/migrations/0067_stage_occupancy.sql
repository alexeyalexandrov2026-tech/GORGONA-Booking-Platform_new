-- L2a (package L, BEAUTY-01): stage-by-stage occupancy.
-- A staged visit holds one resource in several separate intervals (the specialist works in the
-- first stage, is free while a colour develops and finishes later). One allocation per booking,
-- resource and interval; the booking mirror, its backfill and its mismatch count match the
-- interval too. Every existing row already satisfies the new keys; nothing is rewritten.

alter table gba.booking_allocations drop constraint booking_allocations_one_per_resource;
alter table gba.booking_allocations add constraint booking_allocations_one_per_interval
    unique (tenant_id, booking_id, resource_id, during);

alter table gba.resource_allocations drop constraint resource_allocations_one_per_source;
alter table gba.resource_allocations add constraint resource_allocations_one_per_interval
    unique (tenant_id, source_kind, source_id, resource_id, during);

create or replace function gba.mirror_booking_allocation() returns trigger
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
           and r.during = new.during
           and r.state <> gba.booking_occupancy_state(new.booking_status);
        -- Nothing to update means an allocation from before 0018; the backfill copies
        -- it later with the booking's state. The status cascade runs this trigger in
        -- the foreign-key context, so branch row security never hides the row.
    end if;
    return null;
end;
$$;

create or replace function gba.backfill_booking_occupancy() returns bigint
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
            and r.source_id = a.booking_id and r.resource_id = a.resource_id
            and r.during = a.during);
    get diagnostics copied = row_count;
    update gba.resource_allocations r
       set state = gba.booking_occupancy_state(a.booking_status)
      from gba.booking_allocations a
     where r.tenant_id = gba.current_tenant_id() and a.tenant_id = r.tenant_id
       and r.source_kind = 'booking' and r.source_id = a.booking_id
       and r.resource_id = a.resource_id and r.during = a.during
       and r.state <> gba.booking_occupancy_state(a.booking_status)
       and (r.state = 'held' or gba.booking_occupancy_state(a.booking_status) = 'released');
    get diagnostics healed = row_count;
    return copied + healed;
end;
$$;

create or replace function gba.booking_occupancy_mismatches() returns bigint
    language sql stable as $$
    select count(*) from gba.booking_allocations a
    full join gba.resource_allocations r
      on r.tenant_id = a.tenant_id and r.source_kind = 'booking'
     and r.source_id = a.booking_id and r.resource_id = a.resource_id
     and r.during = a.during
    where (r.id is null or r.source_kind = 'booking')
      and (a.booking_id is null or r.id is null
           or r.state <> gba.booking_occupancy_state(a.booking_status))
$$;
