-- K5b, K5a review findings 8 and 15 (ADR-0027): the link of a manual payment to a provider
-- operation needs the enabled finance workflow in SQL too, and the date window calls the
-- catalog's abs().
--
-- 8: like every H money table, an insert into provider_payment_links takes the ledger lock and
-- needs the finance, counterparties and finance_documents modules (GBM01); before, only the
-- Python route checked the modules. 15: the function body is the 0056 body with
-- `pg_catalog.abs`, so a same-named function earlier on a caller's search path is never used.
-- Links that exist already are not re-checked; no row is changed.

create trigger provider_payment_links_require_workflow before insert on gba.provider_payment_links
    for each row execute function gba.require_financial_workflow();

create or replace function gba.enforce_provider_payment_link() returns trigger language plpgsql as $$
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
            and ((c.revoked and c.revoked_reason = 'compromise') or a.book_id <> new.book_id))
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
        or pg_catalog.abs(effective_date - success.happened) > 3
        or not (pg_catalog.lower(operation.provider_object_id)
            = any(gba.provider_reference_ids(p.external_reference))) then
        raise exception using errcode = 'check_violation',
            message = 'a linked manual payment must match its provider operation';
    end if;
    new.success_event_id := success.id;
    return new;
end;
$$;
