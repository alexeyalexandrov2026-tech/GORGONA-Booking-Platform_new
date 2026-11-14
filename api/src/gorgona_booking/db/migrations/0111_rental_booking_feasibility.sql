-- RR-08: find a whole-period unit for each affected class booking without reserving a unit.
create function gba.rental_period_feasible(
    p_tenant uuid, p_class uuid, p_location uuid, p_start timestamptz, p_end timestamptz,
    p_extra integer default 0, p_removed uuid default null
) returns boolean language plpgsql stable as $$
declare
    periods tstzrange[];
    choices jsonb[];
    picked uuid[];
    positions integer[];
    depth integer := 1;
    candidate uuid;
    attempts integer := 0;
    total integer;
begin
    -- An overlap chain can extend beyond the changed period. Solve the entire affected group.
    with periods_and_pins as (
        select b.id, tstzrange(b.starts_at, b.ends_at, '[)') as period, a.unit_id
        from gba.rental_current_bookings(p_tenant) b
        left join gba.rental_assignments a on a.tenant_id = b.tenant_id and a.booking_id = b.id
          and not exists (select 1 from gba.rental_assignment_releases l
                          where l.tenant_id = a.tenant_id and l.assignment_id = a.id)
        where b.class_id = p_class and b.pickup_location_id = p_location
          and not exists (select 1 from gba.rental_booking_cancellations c
                          where c.tenant_id = b.tenant_id and c.booking_id = b.id)
        union all
        select null::uuid, tstzrange(p_start, p_end, '[)'), null::uuid
        from generate_series(1, p_extra)
    ), ordered as (
        select p.*, max(upper(period)) over (
            order by lower(period), upper(period), id
            rows between unbounded preceding and 1 preceding
        ) as previous_end
        from periods_and_pins p
    ), grouped as (
        select p.*, sum(case when previous_end is null or lower(period) >= previous_end
                            then 1 else 0 end) over (
            order by lower(period), upper(period), id rows unbounded preceding
        ) as component
        from ordered p
    ), relevant as (
        select p.* from grouped p
        where p.component in (
            select q.component from grouped q where q.period && tstzrange(p_start, p_end, '[)')
        )
    ), eligible as (
        select p.id, p.period, coalesce(u.ids, '[]'::jsonb) as units
        from relevant p
        cross join lateral (
            select jsonb_agg(u.id order by u.id) as ids
            from gba.rental_units u
            where u.tenant_id = p_tenant and u.class_id = p_class
              and u.location_id = p_location and u.state = 'active'
              and u.id is distinct from p_removed
              and (p.unit_id is null or u.id = p.unit_id)
              and not exists (
                  select 1 from gba.rental_unit_blocks b
                  where b.tenant_id = u.tenant_id and b.unit_id = u.id
                    and b.starts_at < upper(p.period) and b.ends_at > lower(p.period)
                    and not exists (select 1 from gba.rental_unit_block_releases e
                                    where e.tenant_id = b.tenant_id and e.block_id = b.id)
              )
        ) u
    )
    select array_agg(period order by jsonb_array_length(units), lower(period), upper(period), id),
           array_agg(units order by jsonb_array_length(units), lower(period), upper(period), id)
    into periods, choices from eligible;
    total := coalesce(cardinality(periods), 0);
    if total = 0 then
        return true;
    end if;
    if jsonb_array_length(choices[1]) = 0 then
        return false;
    end if;
    picked := array_fill(null::uuid, array[total]);
    positions := array_fill(0, array[total]);
    -- Deterministic backtracking. The first constrained booking branches before interchangeable ones.
    while depth > 0 loop
        attempts := attempts + 1;
        if attempts > 100000 then
            raise exception using errcode = 'check_violation',
                constraint = 'rental_feasibility_budget_check',
                message = 'the rental feasibility search exceeded its work budget';
        end if;
        candidate := (choices[depth]->>positions[depth])::uuid;
        if candidate is null then
            positions[depth] := 0;
            picked[depth] := null;
            depth := depth - 1;
        else
            positions[depth] := positions[depth] + 1;
            if not exists (
                select 1 from generate_series(1, depth - 1) i
                where picked[i] = candidate and periods[i] && periods[depth]
            ) then
                picked[depth] := candidate;
                depth := depth + 1;
                if depth > total then
                    return true;
                end if;
            end if;
        end if;
    end loop;
    return false;
end;
$$;
revoke all on function gba.rental_period_feasible(
    uuid, uuid, uuid, timestamptz, timestamptz, integer, uuid) from public;
grant execute on function gba.rental_period_feasible(
    uuid, uuid, uuid, timestamptz, timestamptz, integer, uuid) to gba_runtime;

create or replace function gba.guard_rental_booking() returns trigger language plpgsql as $$
declare
    units integer;
begin
    perform 1 from gba.rental_classes c
    where c.tenant_id = new.tenant_id and c.id = new.class_id for update;
    if new.number <> coalesce((
        select max(b.number) from gba.rental_bookings b
        where b.tenant_id = new.tenant_id and b.pickup_location_id = new.pickup_location_id), 0) + 1 then
        raise exception using errcode = 'check_violation',
            constraint = 'rental_bookings_sequence_check',
            message = 'a booking follows the latest one of its pickup branch';
    end if;
    if not exists (
        select 1 from gba.counterparty_versions v
        where v.tenant_id = new.tenant_id and v.counterparty_id = new.customer_id
          and v.state = 'active' and 'customer' = any(v.roles)
          and v.revision = (
              select max(x.revision) from gba.counterparty_versions x
              where x.tenant_id = v.tenant_id and x.counterparty_id = v.counterparty_id)
    ) then
        raise exception using errcode = 'check_violation',
            constraint = 'rental_bookings_customer_check',
            message = 'a booking names an active customer';
    end if;
    select count(*) into units from gba.rental_units u
    where u.tenant_id = new.tenant_id and u.class_id = new.class_id
      and u.location_id = new.pickup_location_id and u.state = 'active';
    if gba.rental_booking_peak(new.tenant_id, new.class_id, new.pickup_location_id,
                               new.starts_at, new.ends_at) + 1 > units then
        raise exception using errcode = 'check_violation',
            constraint = 'rental_bookings_availability_check',
            message = 'a booking fits the units of its class at the pickup branch';
    end if;
    if not gba.rental_period_feasible(new.tenant_id, new.class_id, new.pickup_location_id,
                                      new.starts_at, new.ends_at, 1) then
        raise exception using errcode = 'check_violation',
            constraint = 'rental_bookings_availability_check',
            message = 'no whole-period assignment preserves the booking';
    end if;
    return new;
end;
$$;

create or replace function gba.guard_rental_unit() returns trigger language plpgsql as $$
declare
    last_end timestamptz;
    units integer;
begin
    if tg_op = 'INSERT' then
        if new.revision <> 1 then
            raise exception using errcode = 'check_violation',
                constraint = 'rental_units_revision_sequence_check',
                message = 'a unit starts at revision 1';
        end if;
        return new;
    end if;
    if old.state = 'retired' then
        raise exception using errcode = 'check_violation',
            constraint = 'rental_units_retired_check',
            message = 'a retired unit takes no new revision';
    end if;
    if new.class_id <> old.class_id or new.identifier <> old.identifier
       or new.revision <> old.revision + 1 then
        raise exception using errcode = 'check_violation',
            constraint = 'rental_units_revision_sequence_check',
            message = 'a unit keeps its class and identifier and takes the next revision';
    end if;
    if new.location_id <> old.location_id or new.state <> old.state then
        perform 1 from gba.rental_classes c
        where c.tenant_id = old.tenant_id and c.id = old.class_id for update;
        if gba.rental_unit_is_out(old.tenant_id, old.id) or exists (
            select 1 from gba.resource_allocations x
            where x.tenant_id = old.tenant_id and x.resource_id = old.resource_id
              and x.state in ('held', 'confirmed') and upper(x.during) > statement_timestamp()
        ) then
            raise exception using errcode = 'check_violation',
                constraint = 'rental_units_held_check',
                message = 'a unit in use or held cannot be moved or retired';
        end if;
        select max(b.ends_at) into last_end
        from gba.rental_current_bookings(old.tenant_id) b
        where b.class_id = old.class_id and b.pickup_location_id = old.location_id
          and b.ends_at > statement_timestamp()
          and not exists (
              select 1 from gba.rental_booking_cancellations c
              where c.tenant_id = b.tenant_id and c.booking_id = b.id);
        if last_end is not null then
            select count(*) into units from gba.rental_units u
            where u.tenant_id = old.tenant_id and u.class_id = old.class_id
              and u.location_id = old.location_id and u.state = 'active' and u.id <> old.id;
            if gba.rental_booking_peak(
                old.tenant_id, old.class_id, old.location_id, statement_timestamp(), last_end
            ) > units or not gba.rental_period_feasible(
                old.tenant_id, old.class_id, old.location_id,
                statement_timestamp(), last_end, 0, old.id
            ) then
                raise exception using errcode = 'check_violation',
                    constraint = 'rental_units_availability_check',
                    message = 'removing a unit leaves a booking without class capacity';
            end if;
        end if;
    end if;
    return new;
end;
$$;

create function gba.check_rental_period_feasibility() returns trigger language plpgsql as $$
declare
    context record;
begin
    if tg_table_name = 'rental_unit_blocks' then
        select u.class_id, u.location_id, new.starts_at as starts, new.ends_at as ends into context
        from gba.rental_units u where u.tenant_id = new.tenant_id and u.id = new.unit_id;
    else
        select b.class_id, b.pickup_location_id as location_id, b.starts_at as starts,
               b.ends_at as ends into context
        from gba.rental_current_bookings(new.tenant_id) b where b.id = new.booking_id;
    end if;
    if not gba.rental_period_feasible(new.tenant_id, context.class_id, context.location_id,
                                      context.starts, context.ends) then
        raise exception using errcode = 'check_violation',
            constraint = 'rental_period_feasibility_check',
            message = 'the change leaves a rental without a whole-period unit';
    end if;
    return null;
end;
$$;
revoke all on function gba.check_rental_period_feasibility() from public;
create constraint trigger rental_assignments_feasibility after insert on gba.rental_assignments
    deferrable initially deferred for each row execute function gba.check_rental_period_feasibility();
create constraint trigger rental_periods_feasibility after insert on gba.rental_booking_periods
    deferrable initially deferred for each row execute function gba.check_rental_period_feasibility();
create constraint trigger rental_blocks_feasibility after insert on gba.rental_unit_blocks
    deferrable initially deferred for each row execute function gba.check_rental_period_feasibility();
