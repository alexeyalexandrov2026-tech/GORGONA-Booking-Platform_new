-- N2 (package N): tenders of trip legs to other carriers. docs/plan/PACKAGE_N2_DESIGN_2026-10-27.md.
-- A tender is an insert-only offer; answers are insert-only facts with a source. The state is derived:
-- offered, accepted, declined, withdrawn or expired. A leg has at most one accepted tender at a time.
create table gba.transport_tenders (
    tenant_id uuid not null references gba.tenants(id),
    id uuid not null,
    trip_id uuid not null,
    legs smallint[] not null constraint transport_tenders_legs_check
        check (cardinality(legs) between 1 and 100 and array_position(legs, null) is null),
    counterparty_id uuid not null,
    currency text not null references gba.currencies(code),
    basis text not null constraint transport_tenders_basis_check
        check (basis in ('fixed', 'per_mile')),
    amount numeric(20, 3) not null constraint transport_tenders_amount_check check (amount > 0),
    terms text not null constraint transport_tenders_terms_check
        check (length(btrim(terms)) between 1 and 2000),
    offered_at timestamptz not null,
    expires_at timestamptz not null,
    created_by uuid not null references gba.users(id),
    created_at timestamptz not null default now(),
    primary key (tenant_id, id),
    foreign key (tenant_id, trip_id) references gba.transport_trips (tenant_id, id),
    foreign key (tenant_id, counterparty_id) references gba.counterparties (tenant_id, id),
    constraint transport_tenders_period_check check (expires_at > offered_at)
);
create table gba.transport_tender_answers (
    tenant_id uuid not null references gba.tenants(id),
    tender_id uuid not null,
    kind text not null constraint transport_tender_answers_kind_check
        check (kind in ('accepted', 'declined', 'withdrawn')),
    source text not null constraint transport_tender_answers_source_check
        check (source in ('email', 'phone', 'load_board', 'other')),
    occurred_at timestamptz not null,
    created_by uuid not null references gba.users(id),
    created_at timestamptz not null default now(),
    primary key (tenant_id, tender_id, kind),
    foreign key (tenant_id, tender_id) references gba.transport_tenders (tenant_id, id)
);

-- An answer follows the tender's state; an acceptance never overlaps another accepted tender's legs.
-- The trip-tender lock serialises the answers of one trip.
create function gba.guard_transport_tender_answer() returns trigger language plpgsql as $$
declare
    tender gba.transport_tenders%rowtype;
    answered timestamptz;
    took boolean;
    closed boolean;
begin
    select * into tender from gba.transport_tenders t
     where t.tenant_id = new.tenant_id and t.id = new.tender_id;
    perform pg_catalog.pg_advisory_xact_lock(
        pg_catalog.hashtextextended('gba:trip-tender:' || tender.trip_id::text, 0));
    select max(a.occurred_at), bool_or(a.kind = 'accepted'), bool_or(a.kind <> 'accepted')
      into answered, took, closed
      from gba.transport_tender_answers a
     where a.tenant_id = new.tenant_id and a.tender_id = new.tender_id;
    if new.occurred_at < coalesce(answered, tender.offered_at) then
        raise exception using errcode = 'check_violation',
            constraint = 'transport_tender_answers_time_check',
            message = 'an answer follows the offer and the previous answer';
    end if;
    if coalesce(closed, false)
       or (coalesce(took, false) and new.kind <> 'withdrawn')
       or (not coalesce(took, false) and new.occurred_at > tender.expires_at) then
        raise exception using errcode = 'check_violation',
            constraint = 'transport_tender_answers_state_check',
            message = 'the tender is closed';
    end if;
    if new.kind = 'accepted' and exists (
        select 1 from gba.transport_tenders o
          join gba.transport_tender_answers a
            on a.tenant_id = o.tenant_id and a.tender_id = o.id and a.kind = 'accepted'
         where o.tenant_id = new.tenant_id and o.trip_id = tender.trip_id and o.id <> tender.id
           and o.legs && tender.legs
           and not exists (
               select 1 from gba.transport_tender_answers w
                where w.tenant_id = o.tenant_id and w.tender_id = o.id and w.kind = 'withdrawn')
    ) then
        raise exception using errcode = 'check_violation',
            constraint = 'transport_tender_answers_leg_check',
            message = 'a leg has at most one accepted tender';
    end if;
    return new;
end;
$$;
revoke all on function gba.guard_transport_tender_answer() from public;
create trigger transport_tender_answers_guard before insert on gba.transport_tender_answers
    for each row execute function gba.guard_transport_tender_answer();

-- Writes need the transport module (ADR-0019 gate).
create trigger transport_tenders_module_gate before insert on gba.transport_tenders
    for each row execute function gba.require_enabled_module('transport');
create trigger transport_tender_answers_module_gate before insert on gba.transport_tender_answers
    for each row execute function gba.require_enabled_module('transport');

alter table gba.transport_tenders enable row level security;
alter table gba.transport_tenders force row level security;
alter table gba.transport_tender_answers enable row level security;
alter table gba.transport_tender_answers force row level security;
create policy transport_tenders_tenant_isolation on gba.transport_tenders
    using (tenant_id = gba.current_tenant_id())
    with check (tenant_id = gba.current_tenant_id());
create policy transport_tender_answers_tenant_isolation on gba.transport_tender_answers
    using (tenant_id = gba.current_tenant_id())
    with check (tenant_id = gba.current_tenant_id());
grant select on gba.transport_tenders, gba.transport_tender_answers to gba_runtime;
grant insert (tenant_id, id, trip_id, legs, counterparty_id, currency, basis, amount, terms,
              offered_at, expires_at, created_by)
    on gba.transport_tenders to gba_runtime;
grant insert (tenant_id, tender_id, kind, source, occurred_at, created_by)
    on gba.transport_tender_answers to gba_runtime;

-- Tender branch scope: brokerage is company-wide; a branch-limited session sees none of it.
create policy transport_tenders_company on gba.transport_tenders
    as restrictive to gba_runtime
    using (gba.current_location_id() is null)
    with check (gba.current_location_id() is null);
create policy transport_tender_answers_company on gba.transport_tender_answers
    as restrictive to gba_runtime
    using (gba.current_location_id() is null)
    with check (gba.current_location_id() is null);
