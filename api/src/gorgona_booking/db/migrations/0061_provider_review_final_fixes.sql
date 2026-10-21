-- K5r, K5 final review R1 and R2 (ADR-0027). No receipt fact changes.
--
-- R1: the money checks, the link check and the operation list look up the events of one
-- operation. Each event now stores the operation key its facts decode to, and an index on that key
-- replaces decoding every event of the connection. Stored columns, not an expression index: under
-- FORCE RLS a condition on a function that is not leakproof cannot be an index condition, while a
-- plain text comparison can. The receipt writer, which inserts events, may evaluate the key.
-- R2: a refused delivery is lost to a suspended connection (Stripe stops retrying), so a later
-- re-admission could make a stale success applicable; a suspension is therefore final.

grant execute on function gba.provider_receipt_operation(jsonb) to gba_receipt_writer;

alter table gba.provider_event_inbox
    add column operation_kind text generated always as ((gba.provider_receipt_operation(facts)).kind) stored,
    add column operation_object_id text generated always as ((gba.provider_receipt_operation(facts)).object_id) stored;

create index provider_event_inbox_operation on gba.provider_event_inbox
    (tenant_id, connection_id, operation_object_id);

create or replace function gba.guard_provider_connection_admission() returns trigger
language plpgsql set search_path=pg_catalog as $$
declare
    binding gba.provider_receipt_connections;
    latest gba.provider_connection_admissions;
begin
    if tg_op <> 'INSERT' then
        raise exception using errcode='check_violation',
            message='provider connection admissions are permanent; record a new revision';
    end if;
    if new.tenant_id is distinct from gba.current_tenant_id() or gba.current_location_id() is not null then
        raise exception using errcode='check_violation',
            message='provider connection admission requires company scope';
    end if;
    perform pg_advisory_xact_lock(hashtextextended(
        'gba:provider-admission:' || new.tenant_id::text || ':' || new.connection_id::text, 0));
    select c.* into binding from gba.provider_receipt_connections c
        where c.tenant_id=new.tenant_id and c.id=new.connection_id;
    select a.* into latest from gba.provider_connection_admissions a
        where a.tenant_id=new.tenant_id and a.connection_id=new.connection_id
        order by a.revision desc limit 1;
    if binding.id is null or binding.revoked or binding.livemode
       or new.account_id is distinct from binding.account_id
       or (latest.revision is null and new.state <> 'test_access') then
        raise exception using errcode='check_violation',
            message='provider connection admission refused';
    end if;
    -- K5r (review R2): deliveries refused while suspended are lost to the connection, so a
    -- suspension is final; a new connection is provisioned instead of re-admitting this one.
    if new.state = 'test_access' and exists (select 1 from gba.provider_connection_admissions a
            where a.tenant_id=new.tenant_id and a.connection_id=new.connection_id
            and a.state='suspended') then
        raise exception using errcode='check_violation',
            message='a suspended provider connection stays suspended; provision a new connection';
    end if;
    new.revision := coalesce(latest.revision, 0) + 1;
    new.recorded_by := session_user;
    new.recorded_at := now();
    return new;
end;
$$;
revoke all on function gba.guard_provider_connection_admission() from public;
