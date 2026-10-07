-- H3 settlement guards (ADR-0024; independent H2 review of e93ca5c, F1-F3). Forward
-- only: migrations 0001-0024 are preserved and replaced functions keep their names.
-- F1 One external fact has one identity whatever its letter case, Unicode
--    compatibility form or invisible format characters. Whitespace inside an
--    identifier keeps its meaning unless the identifier's source says otherwise.
-- F2 A cash account and an issued control account are never the same account, so
--    H obligation balances and G control balances cannot drift apart.
-- F3 A payment is never posted before the accrual it settles, and an attested
--    external date is never later than today in the business time zone.

-- The comparison form of a source account alias or an external reference. NFKC
-- turns full-width and other compatibility forms, and every Unicode space, into
-- their plain form; default-ignorable (invisible) code points are removed; the
-- ends are trimmed and letters lowercased. Interior whitespace follows the rule of
-- the identifier's source. 'preserve', the conservative default, keeps every
-- interior space where the source put it, so `TX 123`, `TX  123` and `TX123` stay
-- three identifiers. It is the only rule while no source contract states that
-- its whitespace carries no meaning; such a provider rule needs its own accepted
-- change. The stored text always keeps its original form.
create function gba.external_identity_key(value text, whitespace_rule text) returns text
    language plpgsql as $$
begin
    if whitespace_rule is distinct from 'preserve' then
        raise exception using errcode = 'invalid_parameter_value',
            message = 'unknown external identity whitespace rule';
    end if;
    return lower(btrim(regexp_replace(normalize(value, NFKC) collate "pg_c_utf8",
        '[\u00ad\u034f\u061c\u115f\u1160\u17b4\u17b5\u180b-\u180f\u200b-\u200f\u202a-\u202e'
        '\u2060-\u206f\u3164\ufe00-\ufe0f\ufeff\uffa0\ufff0-\ufff8'
        '\U0001bca0-\U0001bca3\U0001d173-\U0001d17a\U000e0000-\U000e0fff]', '', 'g')));
end;
$$;
revoke all on function gba.external_identity_key(text, text) from public;
grant execute on function gba.external_identity_key(text, text) to gba_runtime;

-- The IANA time zone that decides "today" for a business: the one zone shared by
-- all its locations (each validated and governed by the confirmed timezone fact).
-- A ledger book has no zone of its own and H2 has no provider time zone: every
-- confirmation is a manual attestation. With no location, or locations in several
-- zones, no zone is authoritative and UTC is the documented fallback.
create function gba.business_timezone(tenant uuid) returns text language plpgsql as $$
declare zones text[];
begin
    select array_agg(distinct l.timezone) into zones from gba.locations l
        where l.tenant_id = tenant;
    if coalesce(array_length(zones, 1), 0) = 1 then
        return zones[1];
    end if;
    return 'UTC';
end;
$$;
revoke all on function gba.business_timezone(uuid) from public;
grant execute on function gba.business_timezone(uuid) to gba_runtime;

-- An invoice or accrual never takes an account that already received external cash.
create or replace function gba.enforce_financial_version() returns trigger language plpgsql as $$
declare previous gba.financial_document_versions%rowtype;
begin
    perform gba.lock_ledger(new.tenant_id);
    select * into previous from gba.financial_document_versions v
        where v.tenant_id = new.tenant_id and v.book_id = new.book_id and v.document_id = new.document_id
        order by v.revision desc limit 1;
    if new.revision <> coalesce(previous.revision, 0) + 1
        or previous.state = 'issued' or (previous.revision is null and new.state <> 'draft') then
        raise exception using errcode = 'check_violation', message = 'financial version must follow a draft';
    end if;
    if not exists (
        select 1 from gba.counterparty_versions v where v.tenant_id = new.tenant_id
        and v.counterparty_id = new.counterparty_id and v.state = 'active'
        and v.revision = (select max(x.revision) from gba.counterparty_versions x
            where x.tenant_id = v.tenant_id and x.counterparty_id = v.counterparty_id)
    ) then
        raise exception using errcode = 'check_violation', message = 'invoice needs an active counterparty';
    end if;
    if not exists (select 1 from gba.ledger_accounts a
        join gba.ledger_account_versions v on v.tenant_id = a.tenant_id and v.account_id = a.id
        where a.tenant_id = new.tenant_id and a.book_id = new.book_id and a.id = new.control_account_id
        and a.type = case new.direction when 'receivable' then 'asset' else 'liability' end
        and not v.archived and v.revision = (select max(x.revision) from gba.ledger_account_versions x
            where x.tenant_id = a.tenant_id and x.account_id = a.id)) then
        raise exception using errcode = 'check_violation', message = 'invoice needs an open control account';
    end if;
    if exists (select 1 from gba.external_payments p where p.tenant_id = new.tenant_id
        and p.book_id = new.book_id and p.cash_account_id = new.control_account_id) then
        raise exception using errcode = 'check_violation',
            message = 'a cash account cannot be a financial control account';
    end if;
    if new.state = 'issued' and
       row(new.direction,new.counterparty_id,new.counterparty_revision,new.currency,
           new.invoice_date,new.due_date,new.control_account_id,new.title,new.number,
           new.principal_minor,new.line_count)
       is distinct from
       row(previous.direction,previous.counterparty_id,previous.counterparty_revision,previous.currency,
           previous.invoice_date,previous.due_date,previous.control_account_id,previous.title,previous.number,
           previous.principal_minor,previous.line_count) then
        raise exception using errcode = 'check_violation', message = 'issue preserves the saved draft';
    end if;
    return new;
end;
$$;

-- A payment takes no control account of any obligation, no external date after
-- today in the business time zone and no identity whose comparison form is recorded.
create or replace function gba.enforce_external_payment() returns trigger language plpgsql as $$
declare document gba.settlement_documents%rowtype;
begin
    perform gba.lock_ledger(new.tenant_id);
    select * into document from gba.settlement_documents d
        where d.tenant_id = new.tenant_id and d.book_id = new.book_id and d.id = new.settlement_id;
    if document.id is null or document.direction <> new.direction
        or document.currency <> new.currency or not exists (
            select 1 from gba.settlement_events e where e.tenant_id = new.tenant_id
            and e.book_id = new.book_id and e.settlement_id = new.settlement_id
            and e.sequence = new.sequence and e.kind = 'confirmed'
            and e.created_by = new.created_by
            and e.created_transaction = pg_catalog.pg_current_xact_id()) then
        raise exception using errcode = 'check_violation',
            message = 'external payment is recorded with its confirmed settlement event';
    end if;
    if not exists (select 1 from gba.ledger_accounts a
        join gba.ledger_account_versions v on v.tenant_id = a.tenant_id and v.account_id = a.id
        where a.tenant_id = new.tenant_id and a.book_id = new.book_id and a.id = new.cash_account_id
        and a.type = 'asset' and not v.archived
        and v.revision = (select max(x.revision) from gba.ledger_account_versions x
            where x.tenant_id = a.tenant_id and x.account_id = a.id)) then
        raise exception using errcode = 'check_violation',
            message = 'external payment needs an open cash or bank asset account';
    end if;
    if exists (select 1 from gba.financial_obligations o where o.tenant_id = new.tenant_id
        and o.book_id = new.book_id and o.control_account_id = new.cash_account_id) then
        raise exception using errcode = 'check_violation',
            message = 'a cash account cannot be a financial control account';
    end if;
    if new.actual_external_date
        > (pg_catalog.now() at time zone gba.business_timezone(new.tenant_id))::date then
        raise exception using errcode = 'check_violation',
            message = 'an attested external date cannot be in the future';
    end if;
    -- Manual attestations have no provider contract, so the conservative rule applies.
    if exists (select 1 from gba.external_payments p where p.tenant_id = new.tenant_id
        and p.book_id = new.book_id and p.direction = new.direction
        and gba.external_identity_key(p.source_account_alias, 'preserve')
            = gba.external_identity_key(new.source_account_alias, 'preserve')
        and gba.external_identity_key(p.external_reference, 'preserve')
            = gba.external_identity_key(new.external_reference, 'preserve')) then
        raise exception using errcode = 'unique_violation',
            message = 'this external payment identity is already recorded';
    end if;
    return new;
end;
$$;

-- The complete payment, posted no earlier than any accrual it settles.
create or replace function gba.assert_payment_consistent(tenant uuid, book uuid, payment uuid)
    returns void language plpgsql as $$
declare
    p gba.external_payments%rowtype;
    entry gba.journal_entries%rowtype;
    total numeric;
    cash_side text;
    control_side text;
begin
    select * into p from gba.external_payments x
        where x.tenant_id = tenant and x.book_id = book and x.id = payment;
    if p.id is null then
        raise exception using errcode = 'check_violation', message = 'external payment is missing';
    end if;
    if exists (select 1 from (
        select a.line_no, a.created_transaction, row_number() over (order by a.line_no) as position
        from gba.external_payment_allocations a
        where a.tenant_id = tenant and a.book_id = book and a.payment_id = payment) x
        where x.line_no <> x.position or x.created_transaction <> p.created_transaction) then
        raise exception using errcode = 'check_violation',
            message = 'payment allocations are complete with their payment';
    end if;
    select coalesce(sum(a.amount_minor), 0) into total from gba.external_payment_allocations a
        where a.tenant_id = tenant and a.book_id = book and a.payment_id = payment;
    if total <> p.amount_minor then
        raise exception using errcode = 'check_violation',
            message = 'payment allocations must equal the confirmed amount';
    end if;
    if exists (select 1 from gba.external_payment_allocations a
        join gba.financial_obligations o on o.tenant_id = a.tenant_id
            and o.book_id = a.book_id and o.id = a.obligation_id
        where a.tenant_id = tenant and a.book_id = book and a.payment_id = payment
        and o.control_account_id = p.cash_account_id) then
        raise exception using errcode = 'check_violation',
            message = 'cash account cannot be an obligation control account';
    end if;
    if exists (select 1 from gba.external_payment_allocations a
        join gba.financial_obligations o on o.tenant_id = a.tenant_id
            and o.book_id = a.book_id and o.id = a.obligation_id
        join gba.financial_document_versions v on v.tenant_id = o.tenant_id
            and v.book_id = o.book_id and v.document_id = o.source_id
            and v.revision = o.source_revision
        where a.tenant_id = tenant and a.book_id = book and a.payment_id = payment
        and v.issued_on > p.entry_date) then
        raise exception using errcode = 'check_violation',
            message = 'a payment cannot be posted before the accrual it settles';
    end if;
    select * into entry from gba.journal_entries e
        where e.tenant_id = tenant and e.book_id = book and e.id = p.entry_id;
    if entry.id is null
        or row(entry.source_kind,entry.source_id,entry.currency,entry.entry_date,entry.created_by)
        is distinct from row('payment'::text,p.id::text,p.currency,p.entry_date,p.created_by) then
        raise exception using errcode = 'check_violation',
            message = 'payment journal lineage must match';
    end if;
    cash_side := case p.direction when 'receivable' then 'debit' else 'credit' end;
    control_side := case p.direction when 'receivable' then 'credit' else 'debit' end;
    if exists (
        (select j.line_no,j.account_id,j.side,j.amount_minor from gba.journal_lines j
            where j.tenant_id = tenant and j.entry_id = p.entry_id
         except all
         (select 1::smallint,p.cash_account_id,cash_side,p.amount_minor
          union all
          select (a.line_no+1)::smallint,o.control_account_id,control_side,a.amount_minor
            from gba.external_payment_allocations a
            join gba.financial_obligations o on o.tenant_id = a.tenant_id
                and o.book_id = a.book_id and o.id = a.obligation_id
            where a.tenant_id = tenant and a.book_id = book and a.payment_id = payment))
        union all
        ((select 1::smallint,p.cash_account_id,cash_side,p.amount_minor
          union all
          select (a.line_no+1)::smallint,o.control_account_id,control_side,a.amount_minor
            from gba.external_payment_allocations a
            join gba.financial_obligations o on o.tenant_id = a.tenant_id
                and o.book_id = a.book_id and o.id = a.obligation_id
            where a.tenant_id = tenant and a.book_id = book and a.payment_id = payment)
         except all
         select j.line_no,j.account_id,j.side,j.amount_minor from gba.journal_lines j
            where j.tenant_id = tenant and j.entry_id = p.entry_id)
    ) then
        raise exception using errcode = 'check_violation',
            message = 'payment journal must match the cash line and every allocation';
    end if;
    perform gba.assert_settlement_consistent(tenant, book, p.settlement_id);
end;
$$;
