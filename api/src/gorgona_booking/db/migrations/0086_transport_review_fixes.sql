-- N8 (package N review fixes): docs/plan/PACKAGE_N8_DESIGN_2026-10-30.md. Triggers only; no table changes.
-- RN-02 a tendered trip keeps its plan; RN-04 a paid tender is neither withdrawn nor repriced, and a closed
-- tender agrees no further version. Each takes the trip-tender lock that the API takes first.

-- RN-02: an open offer or an accepted, not withdrawn tender holds the legs and stops of its trip.
create function gba.guard_transport_tendered_plan() returns trigger language plpgsql as $$
declare
    checked_tenant uuid;
    checked_trip uuid;
begin
    if tg_op = 'DELETE' then
        checked_tenant := old.tenant_id;
        checked_trip := old.trip_id;
    else
        checked_tenant := new.tenant_id;
        checked_trip := new.trip_id;
    end if;
    perform pg_catalog.pg_advisory_xact_lock(
        pg_catalog.hashtextextended('gba:trip-tender:' || checked_trip::text, 0));
    if exists (
        select 1 from gba.transport_tenders t
         where t.tenant_id = checked_tenant and t.trip_id = checked_trip
           and not exists (
               select 1 from gba.transport_tender_answers a
                where a.tenant_id = t.tenant_id and a.tender_id = t.id
                  and a.kind in ('declined', 'withdrawn'))
           and (t.expires_at > pg_catalog.statement_timestamp() or exists (
               select 1 from gba.transport_tender_answers a
                where a.tenant_id = t.tenant_id and a.tender_id = t.id and a.kind = 'accepted'))
    ) then
        raise exception using errcode = 'check_violation',
            constraint = 'transport_trips_tendered_check',
            message = 'a tendered trip keeps its plan';
    end if;
    if tg_op = 'DELETE' then
        return old;
    end if;
    return new;
end;
$$;
revoke all on function gba.guard_transport_tendered_plan() from public;
create trigger transport_stops_tender_guard before insert or delete on gba.transport_stops
    for each row execute function gba.guard_transport_tendered_plan();
create trigger transport_legs_tender_guard before insert or delete on gba.transport_legs
    for each row execute function gba.guard_transport_tendered_plan();

-- RN-04: once the carrier's pay is accrued, the tender keeps its answer and its rate.
create function gba.transport_tender_paid(checked_tenant uuid, checked_tender uuid)
    returns boolean language plpgsql as $$
declare
    paid_trip uuid;
begin
    select t.trip_id into paid_trip from gba.transport_tenders t
     where t.tenant_id = checked_tenant and t.id = checked_tender;
    perform pg_catalog.pg_advisory_xact_lock(
        pg_catalog.hashtextextended('gba:trip-tender:' || paid_trip::text, 0));
    return exists (
        select 1 from gba.transport_tender_accruals x
         where x.tenant_id = checked_tenant and x.tender_id = checked_tender);
end;
$$;
revoke all on function gba.transport_tender_paid(uuid, uuid) from public;
grant execute on function gba.transport_tender_paid(uuid, uuid) to gba_runtime;

create function gba.guard_transport_paid_withdrawal() returns trigger language plpgsql as $$
begin
    if new.kind = 'withdrawn' and gba.transport_tender_paid(new.tenant_id, new.tender_id) then
        raise exception using errcode = 'check_violation',
            constraint = 'transport_tenders_accrued_check',
            message = 'a paid tender keeps its answer';
    end if;
    return new;
end;
$$;
revoke all on function gba.guard_transport_paid_withdrawal() from public;
create trigger transport_tender_answers_paid_guard before insert on gba.transport_tender_answers
    for each row execute function gba.guard_transport_paid_withdrawal();

create function gba.guard_transport_paid_rate() returns trigger language plpgsql as $$
begin
    if gba.transport_tender_paid(new.tenant_id, new.tender_id) then
        raise exception using errcode = 'check_violation',
            constraint = 'transport_tenders_accrued_check',
            message = 'a paid tender keeps its rate';
    end if;
    return new;
end;
$$;
revoke all on function gba.guard_transport_paid_rate() from public;
create trigger transport_rate_confirmations_paid_guard
    before insert on gba.transport_rate_confirmations
    for each row execute function gba.guard_transport_paid_rate();

create function gba.guard_transport_closed_rate_answer() returns trigger language plpgsql as $$
begin
    if gba.transport_tender_paid(new.tenant_id, new.tender_id) then
        raise exception using errcode = 'check_violation',
            constraint = 'transport_tenders_accrued_check',
            message = 'a paid tender keeps its rate';
    end if;
    if exists (
        select 1 from gba.transport_tender_answers a
         where a.tenant_id = new.tenant_id and a.tender_id = new.tender_id
           and a.kind in ('declined', 'withdrawn')
    ) then
        raise exception using errcode = 'check_violation',
            constraint = 'transport_rate_confirmations_state_check',
            message = 'a closed tender agrees no further version';
    end if;
    return new;
end;
$$;
revoke all on function gba.guard_transport_closed_rate_answer() from public;
create trigger transport_rate_confirmation_answers_paid_guard
    before insert on gba.transport_rate_confirmation_answers
    for each row execute function gba.guard_transport_closed_rate_answer();
