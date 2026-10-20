-- K0b, master plan §11.2.1 / ADR-0027: the owner's admission of a receipt connection.
--
-- Only the database owner records an admission, inside the company's context (`gba-db
-- admit-receipt-connection`); the runtime, the receipt writer and the worker read it. This
-- migration accepts test access and suspension only: test access never allows production
-- payments, and an approved state needs a later decision. No row means "not checked".
-- Revisions are permanent; a suspended connection may get a new test-access revision.
-- A receipt is attested and decided only while the latest revision of its connection is test
-- access. Recording takes one advisory lock per connection; every gate takes it shared, so a
-- suspension waits for the receipts in flight and applies from the next one. No row is changed:
-- existing connections stay unadmitted, and the 0044 `admission` column keeps 'not_admitted'.

create table gba.provider_connection_admissions (
    tenant_id uuid not null,
    connection_id uuid not null,
    revision integer not null check (revision > 0),
    state text not null check (state in ('test_access','suspended')),
    environment text not null default 'test' check (environment = 'test'),
    charge_allowed boolean not null,
    refund_allowed boolean not null,
    currency text not null default 'USD' check (currency = 'USD'),
    account_id text not null check (account_id ~ '^acct_[A-Za-z0-9]{1,100}$'),
    evidence text not null check (length(btrim(evidence)) between 1 and 500 and evidence !~ '[[:cntrl:]]'),
    recorded_by text not null,
    recorded_at timestamptz not null,
    primary key (tenant_id,connection_id,revision),
    foreign key (tenant_id,connection_id) references gba.provider_receipt_connections (tenant_id,id),
    check (state = 'suspended' or charge_allowed or refund_allowed)
);

create function gba.guard_provider_connection_admission() returns trigger
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
    new.revision := coalesce(latest.revision, 0) + 1;
    new.recorded_by := session_user;
    new.recorded_at := now();
    return new;
end;
$$;
revoke all on function gba.guard_provider_connection_admission() from public;

-- Attestations and decisions: the event's connection must be admitted for test access now.
create function gba.require_provider_receipt_admission() returns trigger
language plpgsql set search_path=pg_catalog as $$
declare
    receipt_connection uuid;
    latest gba.provider_connection_admissions;
begin
    select e.connection_id into receipt_connection from gba.provider_event_inbox e
        where e.tenant_id=new.tenant_id and e.id=new.event_id;
    perform pg_advisory_xact_lock_shared(hashtextextended(
        'gba:provider-admission:' || new.tenant_id::text || ':' || receipt_connection::text, 0));
    select a.* into latest from gba.provider_connection_admissions a
        where a.tenant_id=new.tenant_id and a.connection_id=receipt_connection
        order by a.revision desc limit 1;
    if receipt_connection is null or latest.state is distinct from 'test_access' then
        raise exception using errcode='check_violation',
            message='provider connection is not admitted';
    end if;
    return new;
end;
$$;
revoke all on function gba.require_provider_receipt_admission() from public;

alter table gba.provider_connection_admissions enable row level security;
alter table gba.provider_connection_admissions force row level security;
create policy provider_connection_admissions_tenant on gba.provider_connection_admissions
    using (tenant_id=gba.current_tenant_id()) with check (tenant_id=gba.current_tenant_id());
create policy provider_connection_admissions_company on gba.provider_connection_admissions as restrictive
    using (gba.current_location_id() is null) with check (gba.current_location_id() is null);
-- The worker discovers undecided events of admitted connections without a company context.
create policy provider_connection_admissions_discover on gba.provider_connection_admissions
    for select to gba_receipt_worker using (true);
revoke all on gba.provider_connection_admissions from public;
grant select on gba.provider_connection_admissions to gba_runtime,gba_receipt_writer,gba_receipt_worker;
create trigger provider_connection_admissions_guard before insert or update or delete
    on gba.provider_connection_admissions for each row execute function gba.guard_provider_connection_admission();
create trigger provider_connection_admissions_no_truncate before truncate on gba.provider_connection_admissions
    for each statement execute function gba.reject_provider_receipt_truncate();
create trigger provider_event_attestations_admission before insert on gba.provider_event_attestations
    for each row execute function gba.require_provider_receipt_admission();
create trigger provider_event_decisions_admission before insert on gba.provider_event_decisions
    for each row execute function gba.require_provider_receipt_admission();
