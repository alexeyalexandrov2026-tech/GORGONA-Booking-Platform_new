-- K3b links an earlier manual payment to the observed provider operation it names (ADR-0027;
-- owner decisions 2026-10-19). Linking writes no journal and changes no payment: the money stays
-- as the finance user recorded it, and the operation can never be applied (K3a refuses any
-- operation whose ID a manual payment names). One manual payment links to one operation, amount,
-- currency and direction exactly equal, the dates at most 3 days apart. A later void or
-- correction of the payment stays possible; the link is permanent history.
-- Migrations 0001-0053 are preserved.

create table gba.provider_payment_links (
    tenant_id uuid not null,
    book_id uuid not null,
    payment_id uuid not null,
    operation_id uuid not null,
    success_event_id uuid not null,
    note text not null constraint provider_payment_links_note_check check (
        length(btrim(note)) between 1 and 500 and note !~ '[[:cntrl:]]'),
    created_by uuid not null references gba.users(id),
    created_at timestamptz not null default now(),
    created_transaction xid8 not null default pg_catalog.pg_current_xact_id(),
    primary key (tenant_id, book_id, payment_id),
    unique (tenant_id, operation_id),
    foreign key (tenant_id, book_id, payment_id)
        references gba.external_payments(tenant_id, book_id, id),
    foreign key (tenant_id, operation_id)
        references gba.provider_operations(tenant_id, id),
    foreign key (tenant_id, success_event_id)
        references gba.provider_event_decisions(tenant_id, event_id)
);

-- Every fact is checked where the link is recorded, under the ledger lock and the operation row
-- lock, so an application or a decision of the same operation waits for it.
create function gba.enforce_provider_payment_link() returns trigger language plpgsql as $$
declare
    p gba.external_payments%rowtype;
    operation gba.provider_operations%rowtype;
    last_kind text;
    effective bigint;
    effective_date date;
    success record;
begin
    perform gba.lock_ledger(new.tenant_id);
    select * into operation from gba.provider_operations o
        where o.tenant_id = new.tenant_id and o.id = new.operation_id for update;
    select * into p from gba.external_payments x
        where x.tenant_id = new.tenant_id and x.book_id = new.book_id and x.id = new.payment_id;
    select r.kind, r.amount_minor, r.actual_external_date into last_kind, effective, effective_date
        from gba.external_payment_revisions r
        where r.tenant_id = p.tenant_id and r.book_id = p.book_id and r.payment_id = p.id
        order by r.revision desc limit 1;
    if last_kind is null then
        effective := p.amount_minor;
        effective_date := p.actual_external_date;
    end if;
    if operation.id is null or p.id is null or p.attestation <> 'manual_attestation'
        or last_kind = 'voided'
        or not exists (select 1 from gba.provider_receipt_connections c
            where c.tenant_id = new.tenant_id and c.id = operation.connection_id
            and c.book_id = new.book_id and not c.revoked)
        or exists (select 1 from gba.external_payment_provenance v
            where v.tenant_id = new.tenant_id and v.operation_id = operation.id)
        or exists (select 1 from gba.provider_event_inbox e
            cross join lateral gba.provider_receipt_operation(e.facts) f
            where e.tenant_id = new.tenant_id and e.connection_id = operation.connection_id
            and f.kind = operation.kind and f.object_id = operation.provider_object_id
            and exists (select 1 from gba.provider_event_attestations a
                where a.tenant_id = e.tenant_id and a.event_id = e.id)
            and not exists (select 1 from gba.provider_event_decisions d
                where d.tenant_id = e.tenant_id and d.event_id = e.id
                and d.outcome = 'observed' and d.operation_id = operation.id))
        or exists (select 1 from gba.provider_event_decisions d
            join gba.provider_event_attestations a
                on a.tenant_id = d.tenant_id and a.event_id = d.event_id
            join gba.provider_verification_configs c
                on c.tenant_id = a.tenant_id and c.id = a.verification_config_id
            where d.tenant_id = new.tenant_id and d.operation_id = operation.id
            and (c.revoked or a.book_id <> new.book_id))
        or exists (select 1 from gba.provider_event_decisions d
            join gba.provider_event_deliveries x
                on x.tenant_id = d.tenant_id and x.event_id = d.event_id
            where d.tenant_id = new.tenant_id and d.operation_id = operation.id
            and not x.matches_original) then
        raise exception using errcode = 'check_violation',
            message = 'only a decided operation of the book links to a manual payment';
    end if;
    select e.id, (gba.provider_receipt_operation(e.facts)).amount_minor as amount,
        (pg_catalog.to_timestamp((e.facts->>'created')::bigint)
            at time zone gba.business_timezone(new.tenant_id))::date as happened into success
        from gba.provider_event_decisions d
        join gba.provider_event_inbox e on e.tenant_id = d.tenant_id and e.id = d.event_id
        where d.tenant_id = new.tenant_id and d.operation_id = operation.id
        and d.reason = 'success'
        order by (e.facts->>'created')::bigint, e.id limit 1;
    if success.id is null or effective is distinct from success.amount
        or p.currency <> pg_catalog.upper(operation.currency)
        or p.direction <> (case operation.kind when 'payment' then 'receivable' else 'payable' end)
        or abs(effective_date - success.happened) > 3
        or p.external_reference
            !~ ('(^|[^A-Za-z0-9_])' || operation.provider_object_id || '($|[^A-Za-z0-9_])') then
        raise exception using errcode = 'check_violation',
            message = 'a linked manual payment must match its provider operation';
    end if;
    new.success_event_id := success.id;
    return new;
end;
$$;
revoke all on function gba.enforce_provider_payment_link() from public;

alter table gba.provider_payment_links enable row level security;
alter table gba.provider_payment_links force row level security;
create policy provider_payment_links_tenant_isolation on gba.provider_payment_links
    using (tenant_id=gba.current_tenant_id()) with check (tenant_id=gba.current_tenant_id());
revoke all on gba.provider_payment_links from public;
grant select on gba.provider_payment_links to gba_runtime;
grant insert (tenant_id,book_id,payment_id,operation_id,note,created_by) on gba.provider_payment_links to gba_runtime;
create trigger provider_payment_links_immutable before update or delete on gba.provider_payment_links
    for each row execute function gba.reject_ledger_mutation();
create trigger provider_payment_links_lock before insert on gba.provider_payment_links
    for each row execute function gba.lock_financial_record();
create trigger provider_payment_links_check before insert on gba.provider_payment_links
    for each row execute function gba.enforce_provider_payment_link();

-- Company scope: restore independently in disposable drift tests.
create policy provider_payment_links_unrestricted_scope on gba.provider_payment_links as restrictive to gba_runtime
    using (gba.current_location_id() is null) with check (gba.current_location_id() is null);

-- Approved PostgreSQL 18 CHECK deparse forms. Readiness never learns them from a target database.
-- CHECK_APPROVAL {"table":"provider_payment_links","name":"provider_payment_links_note_check","expression":"(((length(btrim(note)) >= 1) AND (length(btrim(note)) <= 500)) AND (note !~ '[[:cntrl:]]'::text))"}
