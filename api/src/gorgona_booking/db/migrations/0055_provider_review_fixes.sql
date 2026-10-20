-- K5a-fix, independent review findings 2 and 7 / ADR-0027 (owner decisions 2026-10-19). Forward
-- only; no row is changed. Migrations 0001-0054 are preserved.
--
-- 2: a refund event that failed or was canceled, and a success of the same refund, contradict each
-- other in either order: the later one is decided as conflicting facts, so the refund needs review
-- before money moves, or shows the conflict when it was already applied.
-- 7: a revocation of a receipt connection or a verification config takes the company ledger lock
-- (the advisory key of gba.lock_ledger), which every application and link holds until it commits,
-- so neither straddles a revocation.

create or replace function gba.decide_provider_event() returns trigger
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
                     <>fact.amount_minor))
           -- K5a-fix: a refund that failed or was canceled contradicts its success, in either order.
           or (fact.kind='refund' and event.facts->'resource'->>'status' in ('failed','canceled')
               and exists (select 1 from gba.provider_event_decisions p
                   where p.tenant_id=new.tenant_id and p.operation_id=operation.id
                     and p.reason='success'))
           or (fact.kind='refund' and fact.success and exists (select 1
               from gba.provider_event_decisions p
               join gba.provider_event_inbox e on e.tenant_id=p.tenant_id and e.id=p.event_id
               where p.tenant_id=new.tenant_id and p.operation_id=operation.id
                 and e.facts->'resource'->>'status' in ('failed','canceled'))) then
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

create or replace function gba.guard_provider_receipt_connection() returns trigger
language plpgsql set search_path=pg_catalog as $$
begin
    if tg_op='DELETE'
       or (to_jsonb(new)-array['revoked','revoked_reason','revoked_at','revoked_by'])
          is distinct from (to_jsonb(old)-array['revoked','revoked_reason','revoked_at','revoked_by'])
       or (old.revoked and to_jsonb(new) is distinct from to_jsonb(old)) then
        raise exception using errcode='check_violation', message='receipt connection identity and revocation are permanent';
    end if;
    if new.revoked and not old.revoked then
        if new.revoked_reason is null then
            raise exception using errcode='check_violation', message='receipt connection revocation needs a reason';
        end if;
        -- K5a-fix: wait for every application and link in progress. They hold the company
        -- ledger lock of gba.lock_ledger (0020); its advisory key is taken here directly, since
        -- the receipt roles that revoke have no right to call that function.
        perform pg_advisory_xact_lock(hashtextextended('gba:ledger:' || new.tenant_id::text, 0));
        new.revoked_at := now();
        new.revoked_by := session_user;
    elsif (new.revoked_reason,new.revoked_at,new.revoked_by)
          is distinct from (old.revoked_reason,old.revoked_at,old.revoked_by) then
        raise exception using errcode='check_violation', message='receipt connection revocation fields need a revocation';
    end if;
    return new;
end;
$$;

create or replace function gba.guard_provider_verification_config() returns trigger
language plpgsql set search_path=pg_catalog as $$
declare
    binding gba.provider_receipt_connections;
begin
    if tg_op='INSERT' then
        if new.tenant_id is distinct from gba.current_tenant_id() or gba.current_location_id() is not null then
            raise exception using errcode='check_violation', message='verification config requires company scope';
        end if;
        select c.* into binding from gba.provider_receipt_connections c
            where c.tenant_id=new.tenant_id and c.id=new.connection_id for share;
        if binding.id is null or binding.revoked or new.revoked then
            raise exception using errcode='check_violation', message='verification config connection refused';
        end if;
        new.version := coalesce((select max(v.version) from gba.provider_verification_configs v
            where v.tenant_id=new.tenant_id and v.connection_id=new.connection_id),0)+1;
        new.created_by := session_user;
        new.created_at := now();
        return new;
    end if;
    if tg_op='DELETE'
       or (to_jsonb(new)-array['revoked','revoked_reason','revoked_at','revoked_by'])
          is distinct from (to_jsonb(old)-array['revoked','revoked_reason','revoked_at','revoked_by'])
       or (old.revoked and to_jsonb(new) is distinct from to_jsonb(old)) then
        raise exception using errcode='check_violation', message='verification config is permanent; revoke it instead';
    end if;
    if new.revoked and not old.revoked then
        if new.revoked_reason is null then
            raise exception using errcode='check_violation', message='verification config revocation needs a reason';
        end if;
        -- K5a-fix: wait for every application and link in progress. They hold the company
        -- ledger lock of gba.lock_ledger (0020); its advisory key is taken here directly, since
        -- the receipt roles that revoke have no right to call that function.
        perform pg_advisory_xact_lock(hashtextextended('gba:ledger:' || new.tenant_id::text, 0));
        new.revoked_at := now();
        new.revoked_by := session_user;
    elsif (new.revoked_reason,new.revoked_at,new.revoked_by)
          is distinct from (old.revoked_reason,old.revoked_at,old.revoked_by) then
        raise exception using errcode='check_violation', message='verification config revocation fields need a revocation';
    end if;
    return new;
end;
$$;
