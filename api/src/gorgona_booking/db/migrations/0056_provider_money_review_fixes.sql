-- K5a-fix, independent review findings 1, 4, 5, 11 and 13 / ADR-0027 (owner decisions 2026-10-19).
-- Forward only; no row is changed. Migrations 0001-0055 are preserved.
--
-- 1: a manual payment cannot name a provider operation whose money already counts (its provider
--    payment, or a linked manual payment, that is not voided); applying and linking already
--    refused the other order.
-- 4: only a `compromise` revocation of a verification config blocks money; `rotation` and
--    `retired` keep earlier attested facts usable. A revoked connection still blocks.
-- 5: a voided manual payment no longer names an operation, so it never blocks it for good.
-- 11: the refund cap compares effective amounts (the latest correction; a void counts nothing).
-- 13: "names the ID" uses the H identity key: case and invisible characters do not hide an ID.

-- The word tokens of a reference under the H identity key. Provider IDs are ASCII letters, digits
-- and underscores (0050), so the lowercase ID is one token exactly when the reference names it.
create function gba.provider_reference_ids(reference text) returns text[] language plpgsql as $$
begin
    return array(select m[1] from regexp_matches(
        gba.external_identity_key(reference, 'preserve'), '([a-z0-9_]+)', 'g') m);
end;
$$;
revoke all on function gba.provider_reference_ids(text) from public;
grant execute on function gba.provider_reference_ids(text) to gba_runtime;

-- What a payment states now: its latest correction, or the original; nothing once voided.
create function gba.effective_payment_amount(tenant uuid, book uuid, payment uuid)
    returns bigint language plpgsql as $$
declare last_kind text; corrected bigint; original bigint;
begin
    select r.kind, r.amount_minor into last_kind, corrected from gba.external_payment_revisions r
        where r.tenant_id = tenant and r.book_id = book and r.payment_id = payment
        order by r.revision desc limit 1;
    if last_kind = 'voided' then
        return null;
    end if;
    select x.amount_minor into original from gba.external_payments x
        where x.tenant_id = tenant and x.book_id = book and x.id = payment;
    return coalesce(corrected, original);
end;
$$;
revoke all on function gba.effective_payment_amount(uuid, uuid, uuid) from public;
grant execute on function gba.effective_payment_amount(uuid, uuid, uuid) to gba_runtime;

-- The first manual payment of the book that names the provider ID and is not voided.
create function gba.provider_manual_payment(tenant uuid, book uuid, object_id text)
    returns uuid language plpgsql as $$
begin
    return (select m.id from gba.external_payments m
        where m.tenant_id = tenant and m.book_id = book and m.attestation = 'manual_attestation'
        and pg_catalog.lower(object_id) = any(gba.provider_reference_ids(m.external_reference))
        and not exists (select 1 from gba.external_payment_revisions r
            where r.tenant_id = m.tenant_id and r.book_id = m.book_id and r.payment_id = m.id
            and r.kind = 'voided')
        order by m.id limit 1);
end;
$$;
revoke all on function gba.provider_manual_payment(uuid, uuid, text) from public;
grant execute on function gba.provider_manual_payment(uuid, uuid, text) to gba_runtime;

-- The payment whose money is this operation now: its provider payment or its linked manual
-- payment, unless that payment is voided.
create function gba.provider_operation_payment(tenant uuid, operation uuid)
    returns uuid language plpgsql as $$
begin
    return (select x.id from gba.external_payments x
        where x.tenant_id = tenant
        and (exists (select 1 from gba.external_payment_provenance v
                where v.tenant_id = x.tenant_id and v.book_id = x.book_id and v.payment_id = x.id
                and v.operation_id = operation)
            or exists (select 1 from gba.provider_payment_links l
                where l.tenant_id = x.tenant_id and l.book_id = x.book_id and l.payment_id = x.id
                and l.operation_id = operation))
        and not exists (select 1 from gba.external_payment_revisions r
            where r.tenant_id = x.tenant_id and r.book_id = x.book_id and r.payment_id = x.id
            and r.kind = 'voided')
        order by x.id limit 1);
end;
$$;
revoke all on function gba.provider_operation_payment(uuid, uuid) from public;
grant execute on function gba.provider_operation_payment(uuid, uuid) to gba_runtime;

-- Runs after the ledger lock trigger, so an application or a link of the same operation either
-- committed before (and is seen) or waits for this payment.
create function gba.enforce_manual_provider_identity() returns trigger language plpgsql as $$
declare ids text[];
begin
    if new.attestation <> 'manual_attestation' then
        return new;
    end if;
    ids := gba.provider_reference_ids(new.external_reference);
    if exists (select 1 from gba.provider_operations o
            where o.tenant_id = new.tenant_id and pg_catalog.lower(o.provider_object_id) = any(ids)
            and gba.provider_operation_payment(o.tenant_id, o.id) is not null) then
        raise exception using errcode = 'check_violation',
            message = 'a manual payment cannot name a provider operation whose money already counts';
    end if;
    return new;
end;
$$;
revoke all on function gba.enforce_manual_provider_identity() from public;

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
            cross join lateral gba.provider_receipt_operation(e.facts) f
            where e.tenant_id = tenant and e.connection_id = operation.connection_id
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
            or (select sum(gba.effective_payment_amount(tenant, book, r.id))
                from gba.external_payments r
                join gba.external_payment_provenance y on y.tenant_id = r.tenant_id
                    and y.book_id = r.book_id and y.payment_id = r.id
                join gba.provider_operations o on o.tenant_id = y.tenant_id and o.id = y.operation_id
                where r.tenant_id = tenant and r.book_id = book
                and o.connection_id = operation.connection_id and o.kind = 'refund'
                and o.parent_object_id = operation.parent_object_id)
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
        or abs(effective_date - success.happened) > 3
        or not (pg_catalog.lower(operation.provider_object_id)
            = any(gba.provider_reference_ids(p.external_reference))) then
        raise exception using errcode = 'check_violation',
            message = 'a linked manual payment must match its provider operation';
    end if;
    new.success_event_id := success.id;
    return new;
end;
$$;

create trigger external_payments_provider_identity before insert on gba.external_payments
    for each row execute function gba.enforce_manual_provider_identity();
