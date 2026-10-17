-- K2a / ADR-0027, owner decisions of 2026-10-17. Forward only; no existing row is changed.
--
-- A separate NOLOGIN group gba_receipt_worker (created by bootstrap) turns each attested receipt
-- into one permanent decision linked to one canonical provider operation. The database decides:
-- the worker inserts only the lease that claimed an event, and the trigger classifies the stored
-- facts, links the operation and refuses a stale or forged lease. Every conflict or unkeyed fact
-- becomes needs_review. Nothing here reads or writes the ledger, settlements or obligations, and
-- an event without an attestation is never claimed.

grant usage on schema gba to gba_receipt_worker;
grant execute on function gba.current_tenant_id(),gba.current_location_id() to gba_receipt_worker;
grant select on gba.provider_event_inbox,gba.provider_event_deliveries,
    gba.provider_event_attestations to gba_receipt_worker;

-- Canonical identity and classification of one event's stored facts (rules version 1):
-- a PaymentIntent and its Charge are one payment; a refund is keyed by its own ID with the
-- PaymentIntent it refunds; a charge without a PaymentIntent, charge.refunded and a refund
-- without a PaymentIntent have no key.
create function gba.provider_receipt_operation(f jsonb, out kind text, out object_id text,
    out parent_id text, out consistent boolean, out success boolean, out amount_minor numeric,
    out currency text)
language plpgsql immutable parallel safe set search_path=pg_catalog as $$
declare
    r jsonb := f->'resource';
    t text := f->>'event_type';
    s text := f->'resource'->>'status';
begin
    currency := r->>'currency';
    if r->>'object'='payment_intent' then
        kind := 'payment';
        object_id := r->>'id';
        consistent := (t='payment_intent.succeeded') = (s='succeeded')
            and (t<>'payment_intent.processing' or s='processing')
            and (t<>'payment_intent.canceled' or s='canceled');
        success := s='succeeded';
        amount_minor := (r->>'amount_received_minor')::numeric;
    elsif r->>'object'='charge' then
        if t<>'charge.refunded' and r->'payment_intent_id'<>'null'::jsonb then
            kind := 'payment';
            object_id := r->>'payment_intent_id';
        end if;
        consistent := (t in ('charge.succeeded','charge.refunded')) = (s='succeeded')
            and (t<>'charge.failed' or s='failed') and (t<>'charge.pending' or s='pending')
            and (s<>'succeeded' or r->'paid'='true'::jsonb);
        success := s='succeeded' and r->'paid'='true'::jsonb and r->'captured'='true'::jsonb;
        amount_minor := (r->>'amount_minor')::numeric;
    else
        if r->'payment_intent_id'<>'null'::jsonb then
            kind := 'refund';
            object_id := r->>'id';
            parent_id := r->>'payment_intent_id';
        end if;
        consistent := t<>'refund.failed' or s in ('failed','canceled');
        success := s='succeeded';
        amount_minor := (r->>'amount_minor')::numeric;
    end if;
end;
$$;
revoke all on function gba.provider_receipt_operation(jsonb) from public;
grant execute on function gba.provider_receipt_operation(jsonb) to gba_receipt_worker;

create table gba.provider_operations (
    tenant_id uuid not null,
    id uuid not null default gen_random_uuid(),
    connection_id uuid not null,
    kind text not null check (kind in ('payment','refund')),
    provider_object_id text not null check (provider_object_id ~ '^(pi|re)_[A-Za-z0-9]{1,100}$'),
    parent_object_id text check (parent_object_id ~ '^pi_[A-Za-z0-9]{1,100}$'),
    currency text not null check (currency ~ '^[a-z]{3}$'),
    first_event_id uuid not null,
    created_by text not null default session_user,
    created_at timestamptz not null default now(),
    primary key (tenant_id,id),
    unique (tenant_id,connection_id,kind,provider_object_id),
    check ((kind='payment' and provider_object_id ~ '^pi_' and parent_object_id is null)
        or (kind='refund' and provider_object_id ~ '^re_' and parent_object_id is not null)),
    foreign key (tenant_id,connection_id) references gba.provider_receipt_connections (tenant_id,id),
    foreign key (tenant_id,first_event_id) references gba.provider_event_inbox (tenant_id,id)
);

create table gba.provider_event_leases (
    tenant_id uuid not null,
    event_id uuid not null,
    generation bigint not null check (generation > 0),
    holder uuid not null,
    expires_at timestamptz not null,
    claimed_at timestamptz not null default now(),
    primary key (tenant_id,event_id),
    foreign key (tenant_id,event_id) references gba.provider_event_inbox (tenant_id,id)
);

create table gba.provider_event_decisions (
    tenant_id uuid not null,
    event_id uuid not null,
    generation bigint not null,
    holder uuid not null,
    rules_version integer not null default 1 check (rules_version = 1),
    outcome text not null check (outcome in ('observed','needs_review')),
    reason text not null check (reason in ('success','not_final','conflicting_facts',
        'unkeyed_operation','refund_without_payment')),
    operation_id uuid,
    decided_by text not null default session_user,
    decided_at timestamptz not null default now(),
    primary key (tenant_id,event_id),
    check ((outcome='observed') = (reason in ('success','not_final'))),
    check ((operation_id is null) = (reason in ('unkeyed_operation','refund_without_payment'))),
    foreign key (tenant_id,event_id) references gba.provider_event_leases (tenant_id,event_id),
    foreign key (tenant_id,operation_id) references gba.provider_operations (tenant_id,id)
);

create function gba.guard_provider_operation() returns trigger
language plpgsql set search_path=pg_catalog as $$
declare
    event gba.provider_event_inbox;
    expected record;
begin
    if new.tenant_id is distinct from gba.current_tenant_id() or gba.current_location_id() is not null then
        raise exception using errcode='check_violation', message='provider operation requires company scope';
    end if;
    select e.* into event from gba.provider_event_inbox e
        where e.tenant_id=new.tenant_id and e.id=new.first_event_id;
    select * into expected from gba.provider_receipt_operation(event.facts);
    if event.id is null or event.connection_id is distinct from new.connection_id
       or not exists (select 1 from gba.provider_event_attestations a
           where a.tenant_id=new.tenant_id and a.event_id=new.first_event_id)
       or (new.kind,new.provider_object_id,new.parent_object_id,new.currency)
          is distinct from (expected.kind,expected.object_id,expected.parent_id,expected.currency) then
        raise exception using errcode='check_violation', message='provider operation refused';
    end if;
    new.created_by := session_user;
    new.created_at := now();
    return new;
end;
$$;
revoke all on function gba.guard_provider_operation() from public;

-- A lease is created only for an attested, undecided event, for at most ten minutes, and is
-- taken over only after it expired, with the next generation. It is never deleted.
create function gba.guard_provider_event_lease() returns trigger
language plpgsql set search_path=pg_catalog as $$
begin
    if tg_op='DELETE' then
        raise exception using errcode='check_violation', message='provider event leases are kept';
    end if;
    if new.tenant_id is distinct from gba.current_tenant_id() or gba.current_location_id() is not null then
        raise exception using errcode='check_violation', message='provider event lease requires company scope';
    end if;
    if new.expires_at<=now() or new.expires_at>now()+interval '10 minutes'
       or not exists (select 1 from gba.provider_event_attestations a
           where a.tenant_id=new.tenant_id and a.event_id=new.event_id)
       or exists (select 1 from gba.provider_event_decisions d
           where d.tenant_id=new.tenant_id and d.event_id=new.event_id)
       or (tg_op='INSERT' and new.generation<>1)
       or (tg_op='UPDATE' and ((new.tenant_id,new.event_id) is distinct from (old.tenant_id,old.event_id)
           or old.expires_at>=now() or new.generation<>old.generation+1)) then
        raise exception using errcode='check_violation', message='provider event lease refused';
    end if;
    new.claimed_at := now();
    return new;
end;
$$;
revoke all on function gba.guard_provider_event_lease() from public;

-- The decision of one event: only the holder of its unexpired lease may record it, and the
-- outcome, reason and operation come from the stored facts, never from the worker.
create function gba.decide_provider_event() returns trigger
language plpgsql set search_path=pg_catalog as $$
declare
    lease gba.provider_event_leases;
    event gba.provider_event_inbox;
    fact record;
    operation gba.provider_operations;
begin
    if new.tenant_id is distinct from gba.current_tenant_id() or gba.current_location_id() is not null then
        raise exception using errcode='check_violation', message='provider event decision requires company scope';
    end if;
    select l.* into lease from gba.provider_event_leases l
        where l.tenant_id=new.tenant_id and l.event_id=new.event_id for update;
    if lease.event_id is null or lease.holder is distinct from new.holder
       or lease.generation is distinct from new.generation or lease.expires_at<=now() then
        raise exception using errcode='check_violation', message='provider event lease refused';
    end if;
    select e.* into event from gba.provider_event_inbox e
        where e.tenant_id=new.tenant_id and e.id=new.event_id;
    if not exists (select 1 from gba.provider_event_attestations a
        where a.tenant_id=new.tenant_id and a.event_id=new.event_id) then
        raise exception using errcode='check_violation', message='provider event lease refused';
    end if;
    select * into fact from gba.provider_receipt_operation(event.facts);
    new.rules_version := 1;
    new.operation_id := null;
    if fact.kind is null then
        new.outcome := 'needs_review';
        new.reason := case when event.facts->'resource'->>'object'='refund'
            then 'refund_without_payment' else 'unkeyed_operation' end;
    else
        insert into gba.provider_operations (tenant_id,connection_id,kind,provider_object_id,
            parent_object_id,currency,first_event_id)
            values (new.tenant_id,event.connection_id,fact.kind,fact.object_id,fact.parent_id,
                fact.currency,event.id)
            on conflict (tenant_id,connection_id,kind,provider_object_id) do nothing;
        -- Events of one operation wait here for each other, so every conflict is seen.
        select o.* into operation from gba.provider_operations o
            where o.tenant_id=new.tenant_id and o.connection_id=event.connection_id
              and o.kind=fact.kind and o.provider_object_id=fact.object_id for update;
        new.operation_id := operation.id;
        if not coalesce(fact.consistent,false) or operation.currency<>fact.currency
           or operation.parent_object_id is distinct from fact.parent_id
           or exists (select 1 from gba.provider_event_deliveries d
               where d.tenant_id=new.tenant_id and d.event_id=new.event_id and not d.matches_original)
           or (fact.success and exists (select 1 from gba.provider_event_decisions p
               join gba.provider_event_inbox e on e.tenant_id=p.tenant_id and e.id=p.event_id
               where p.tenant_id=new.tenant_id and p.operation_id=operation.id and p.reason='success'
                 and (select x.amount_minor from gba.provider_receipt_operation(e.facts) x)
                     <>fact.amount_minor)) then
            new.outcome := 'needs_review';
            new.reason := 'conflicting_facts';
        else
            new.outcome := 'observed';
            new.reason := case when fact.success then 'success' else 'not_final' end;
        end if;
    end if;
    new.decided_by := session_user;
    new.decided_at := now();
    return new;
end;
$$;
revoke all on function gba.decide_provider_event() from public;

alter table gba.provider_operations enable row level security;
alter table gba.provider_operations force row level security;
alter table gba.provider_event_leases enable row level security;
alter table gba.provider_event_leases force row level security;
alter table gba.provider_event_decisions enable row level security;
alter table gba.provider_event_decisions force row level security;
create policy provider_operations_tenant on gba.provider_operations
    using (tenant_id=gba.current_tenant_id()) with check (tenant_id=gba.current_tenant_id());
create policy provider_operations_company on gba.provider_operations as restrictive
    using (gba.current_location_id() is null) with check (gba.current_location_id() is null);
create policy provider_event_leases_tenant on gba.provider_event_leases
    using (tenant_id=gba.current_tenant_id()) with check (tenant_id=gba.current_tenant_id());
create policy provider_event_leases_company on gba.provider_event_leases as restrictive
    using (gba.current_location_id() is null) with check (gba.current_location_id() is null);
create policy provider_event_decisions_tenant on gba.provider_event_decisions
    using (tenant_id=gba.current_tenant_id()) with check (tenant_id=gba.current_tenant_id());
create policy provider_event_decisions_company on gba.provider_event_decisions as restrictive
    using (gba.current_location_id() is null) with check (gba.current_location_id() is null);
-- Discovery without a company context, for the worker group only, like routes for the writer.
create policy provider_event_attestations_discover on gba.provider_event_attestations
    for select to gba_receipt_worker using (true);
create policy provider_event_decisions_discover on gba.provider_event_decisions
    for select to gba_receipt_worker using (true);

revoke all on gba.provider_operations,gba.provider_event_leases,gba.provider_event_decisions from public;
grant select on gba.provider_operations,gba.provider_event_leases,gba.provider_event_decisions
    to gba_receipt_worker;
grant insert (tenant_id,connection_id,kind,provider_object_id,parent_object_id,currency,first_event_id)
    on gba.provider_operations to gba_receipt_worker;
-- UPDATE on one column only permits SELECT FOR UPDATE; the immutable trigger refuses every update.
grant update (currency) on gba.provider_operations to gba_receipt_worker;
grant insert (tenant_id,event_id,generation,holder,expires_at) on gba.provider_event_leases
    to gba_receipt_worker;
grant update (generation,holder,expires_at) on gba.provider_event_leases to gba_receipt_worker;
grant insert (tenant_id,event_id,generation,holder) on gba.provider_event_decisions
    to gba_receipt_worker;

create trigger provider_operations_check before insert on gba.provider_operations
    for each row execute function gba.guard_provider_operation();
create trigger provider_operations_immutable before update or delete on gba.provider_operations
    for each row execute function gba.reject_ledger_mutation();
create trigger provider_event_leases_guard before insert or update or delete on gba.provider_event_leases
    for each row execute function gba.guard_provider_event_lease();
create trigger provider_event_decisions_decide before insert on gba.provider_event_decisions
    for each row execute function gba.decide_provider_event();
create trigger provider_event_decisions_immutable before update or delete on gba.provider_event_decisions
    for each row execute function gba.reject_ledger_mutation();
create trigger provider_operations_no_truncate before truncate on gba.provider_operations
    for each statement execute function gba.reject_provider_receipt_truncate();
create trigger provider_event_leases_no_truncate before truncate on gba.provider_event_leases
    for each statement execute function gba.reject_provider_receipt_truncate();
create trigger provider_event_decisions_no_truncate before truncate on gba.provider_event_decisions
    for each statement execute function gba.reject_provider_receipt_truncate();
