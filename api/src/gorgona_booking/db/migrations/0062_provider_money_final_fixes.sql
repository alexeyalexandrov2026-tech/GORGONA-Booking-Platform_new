-- K5r, K5 final review R1, R5 and R6 (ADR-0027). Forward only; no row is changed.
--
-- R1: the commit-time check of a provider payment and the link check find the events of one
-- operation by the 0061 stored key and its index instead of decoding every event of the connection.
-- R5: the refund cap counts every refund whose money counts now, applied or linked.
-- R6: "names the provider ID" follows the direction: a received payment names a payment, a paid one
-- names a refund; a refund recorded by hand never blocks the payment it mentions, or the reverse.

create or replace function gba.provider_manual_payment(tenant uuid, book uuid, object_id text)
    returns uuid language plpgsql as $$
begin
    return (select m.id from gba.external_payments m
        where m.tenant_id = tenant and m.book_id = book and m.attestation = 'manual_attestation'
        and pg_catalog.lower(object_id) = any(gba.provider_reference_ids(m.external_reference))
        -- K5r (review R6): a refund ID is named by a paid payment, any other by a received one.
        and m.direction = (case when pg_catalog.left(pg_catalog.lower(object_id), 3) = 're_'
            then 'payable' else 'receivable' end)
        and not exists (select 1 from gba.external_payment_revisions r
            where r.tenant_id = m.tenant_id and r.book_id = m.book_id and r.payment_id = m.id
            and r.kind = 'voided')
        order by m.id limit 1);
end;
$$;

create or replace function gba.enforce_manual_provider_identity() returns trigger language plpgsql as $$
declare ids text[];
begin
    if new.attestation <> 'manual_attestation' then
        return new;
    end if;
    ids := gba.provider_reference_ids(new.external_reference);
    if exists (select 1 from gba.provider_operations o
            where o.tenant_id = new.tenant_id and pg_catalog.lower(o.provider_object_id) = any(ids)
            and (o.kind = 'payment') = (new.direction = 'receivable')
            and gba.provider_operation_payment(o.tenant_id, o.id) is not null) then
        raise exception using errcode = 'check_violation',
            message = 'a manual payment cannot name a provider operation whose money already counts';
    end if;
    return new;
end;
$$;

create or replace function gba.assert_provider_payment(tenant uuid, book uuid, payment uuid)
    returns void language plpgsql as $$
declare
    p gba.external_payments%rowtype;
    provenance gba.external_payment_provenance%rowtype;
    operation gba.provider_operations%rowtype;
    document gba.settlement_documents%rowtype;
    success record;
    parent gba.external_payments%rowtype;
begin
    select * into p from gba.external_payments x
        where x.tenant_id = tenant and x.book_id = book and x.id = payment;
    select * into provenance from gba.external_payment_provenance x
        where x.tenant_id = tenant and x.book_id = book and x.payment_id = payment;
    select * into operation from gba.provider_operations o
        where o.tenant_id = tenant and o.id = provenance.operation_id;
    select * into document from gba.settlement_documents d
        where d.tenant_id = tenant and d.book_id = book and d.id = p.settlement_id;
    if operation.id is null or not exists (select 1 from gba.provider_receipt_connections c
            where c.tenant_id = tenant and c.id = operation.connection_id and c.book_id = book
            and not c.revoked)
        or exists (select 1 from gba.provider_event_inbox e
            where e.tenant_id = tenant and e.connection_id = operation.connection_id
            and e.operation_object_id = operation.provider_object_id
            and e.operation_kind = operation.kind
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
            where d.tenant_id = tenant and d.operation_id = operation.id
            and ((c.revoked and c.revoked_reason = 'compromise') or a.book_id <> book))
        or exists (select 1 from gba.provider_event_decisions d
            join gba.provider_event_deliveries x
                on x.tenant_id = d.tenant_id and x.event_id = d.event_id
            where d.tenant_id = tenant and d.operation_id = operation.id
            and not x.matches_original) then
        raise exception using errcode = 'check_violation',
            message = 'a provider payment needs a decided operation of its book and connection';
    end if;
    select e.id, (gba.provider_receipt_operation(e.facts)).amount_minor as amount,
        (e.facts->>'created')::bigint as created into success
        from gba.provider_event_decisions d
        join gba.provider_event_inbox e on e.tenant_id = d.tenant_id and e.id = d.event_id
        where d.tenant_id = tenant and d.operation_id = operation.id and d.reason = 'success'
        order by (e.facts->>'created')::bigint, e.id limit 1;
    if success.id is null or provenance.success_event_id is distinct from success.id
        or pg_catalog.upper(operation.currency) <> 'USD' or p.currency <> 'USD'
        or p.amount_minor <> success.amount
        or p.actual_external_date <> (pg_catalog.to_timestamp(success.created)
            at time zone gba.business_timezone(tenant))::date
        or p.source_account_alias <> 'stripe_connect'
        or p.external_reference <> operation.provider_object_id
        or p.direction <> (case operation.kind when 'payment' then 'receivable' else 'payable' end)
        or not exists (select 1 from gba.provider_clearing_accounts k
            where k.tenant_id = tenant and k.connection_id = operation.connection_id
            and k.book_id = book and k.account_id = p.cash_account_id)
        or exists (select 1 from gba.external_payment_allocations a
            join gba.financial_obligations o on o.tenant_id = a.tenant_id
                and o.book_id = a.book_id and o.id = a.obligation_id
            where a.tenant_id = tenant and a.book_id = book and a.payment_id = payment
            and (o.source_kind = 'credit_refund') <> (operation.kind = 'refund'))
        or gba.provider_manual_payment(tenant, book, operation.provider_object_id) is not null then
        raise exception using errcode = 'check_violation',
            message = 'a provider payment must match its observed facts';
    end if;
    if operation.kind = 'refund' then
        select x.* into parent from gba.external_payments x
            join gba.external_payment_provenance y on y.tenant_id = x.tenant_id
                and y.book_id = x.book_id and y.payment_id = x.id
            join gba.provider_operations o on o.tenant_id = y.tenant_id and o.id = y.operation_id
            where x.tenant_id = tenant and x.book_id = book
            and o.connection_id = operation.connection_id and o.kind = 'payment'
            and o.provider_object_id = operation.parent_object_id;
        if parent.id is null
            or exists (select 1 from gba.external_payment_revisions r
                where r.tenant_id = tenant and r.book_id = book and r.payment_id = parent.id
                and r.kind = 'voided')
            or (select d.counterparty_id from gba.settlement_documents d
                where d.tenant_id = tenant and d.book_id = book and d.id = parent.settlement_id)
                is distinct from document.counterparty_id
            -- K5r (review R5): applied and linked refunds of the parent both count.
            or (select sum(gba.effective_payment_amount(tenant, book,
                    gba.provider_operation_payment(tenant, o.id)))
                from gba.provider_operations o
                where o.tenant_id = tenant and o.connection_id = operation.connection_id
                and o.kind = 'refund' and o.parent_object_id = operation.parent_object_id)
                > gba.effective_payment_amount(tenant, book, parent.id) then
            raise exception using errcode = 'check_violation',
                message = 'a provider refund follows its applied payment within its amount';
        end if;
    end if;
end;
$$;

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
            where e.tenant_id = new.tenant_id and e.connection_id = operation.connection_id
            and e.operation_object_id = operation.provider_object_id
            and e.operation_kind = operation.kind
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
