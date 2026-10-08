-- H3 independent-review corrections F1-F5. Forward only; 0001-0029 are frozen.
-- This file runs in one owner transaction through apply_migrations. Preflight
-- inspects EVERY tenant, refuses conflicts, and never rewrites financial facts.
-- ACCESS EXCLUSIVE locks protect temporary SELECT policies for the dedicated
-- migration owner only. RLS and FORCE stay enabled throughout; runtime receives
-- no new policy. On failure PostgreSQL rolls back every DDL change, including the
-- new identity definition, and leaves 0030 unapplied.
lock table gba.external_payments, gba.external_payment_revisions,
    gba.financial_documents, gba.financial_document_versions in access exclusive mode;
do $$
declare table_name text;
begin
    foreach table_name in array array['external_payments','external_payment_revisions',
        'financial_documents','financial_document_versions'] loop
        execute pg_catalog.format(
            'create policy h3_upgrade_owner_read on gba.%I for select to %I using (true)',
            table_name,current_user);
    end loop;
end;
$$;

create or replace function gba.external_identity_key(value text, whitespace_rule text) returns text
    language plpgsql as $$
begin
    if whitespace_rule is distinct from 'preserve' then
        raise exception using errcode = 'invalid_parameter_value',
            message = 'unknown external identity whitespace rule';
    end if;
    return btrim(normalize(pg_catalog.casefold(normalize(regexp_replace(value,
        '[\u00ad\u034f\u061c\u115f\u1160\u17b4\u17b5\u180b-\u180f\u200b-\u200f\u202a-\u202e'
        '\u2060-\u206f\u3164\ufe00-\ufe0f\ufeff\uffa0\ufff0-\ufff8'
        '\U0001bca0-\U0001bca3\U0001d173-\U0001d17a\U000e0000-\U000e0fff]', '', 'g'),
        NFKC) collate pg_catalog."pg_unicode_fast"), NFKC));
end;
$$;

do $$
declare conflicts bigint;
begin
    select count(*) into conflicts from (
        select tenant_id,book_id,direction,
            gba.external_identity_key(source_account_alias,'preserve'),
            gba.external_identity_key(external_reference,'preserve')
        from gba.external_payments
        group by tenant_id,book_id,direction,
            gba.external_identity_key(source_account_alias,'preserve'),
            gba.external_identity_key(external_reference,'preserve')
        having count(*) > 1
    ) collisions;
    if conflicts > 0 then
        raise exception using errcode = 'check_violation',
            message = '0030 preflight: external identity conflicts require reconciliation',
            detail = 'conflicting identity groups: ' || conflicts::text;
    end if;
    select count(*) into conflicts from (
        select r.sequence,lag(r.sequence,1,p.sequence) over (
            partition by r.tenant_id,r.book_id,r.payment_id order by r.revision
        ) previous_sequence
        from gba.external_payment_revisions r join gba.external_payments p
            on p.tenant_id=r.tenant_id and p.book_id=r.book_id and p.id=r.payment_id
    ) history where sequence <= previous_sequence;
    if conflicts > 0 then
        raise exception using errcode = 'check_violation',
            message = '0030 preflight: payment event order requires reconciliation',
            detail = 'out-of-order revisions: ' || conflicts::text;
    end if;
    select count(*) into conflicts from gba.financial_document_versions v
        join gba.financial_documents d on d.tenant_id=v.tenant_id and d.book_id=v.book_id
            and d.id=v.document_id
        where d.kind='credit_note' and v.line_count > 198;
    if conflicts > 0 then
        raise exception using errcode = 'check_violation',
            message = '0030 preflight: credit line capacity requires reconciliation',
            detail = 'incompatible credit versions: ' || conflicts::text;
    end if;
end;
$$;
drop policy h3_upgrade_owner_read on gba.external_payments;
drop policy h3_upgrade_owner_read on gba.external_payment_revisions;
drop policy h3_upgrade_owner_read on gba.financial_documents;
drop policy h3_upgrade_owner_read on gba.financial_document_versions;

create or replace function gba.enforce_external_payment_revision() returns trigger language plpgsql as $$
declare
    payment gba.external_payments%rowtype;
    latest gba.external_payment_revisions%rowtype;
begin
    perform gba.lock_ledger(new.tenant_id);
    select * into payment from gba.external_payments p
        where p.tenant_id = new.tenant_id and p.book_id = new.book_id and p.id = new.payment_id;
    if payment.id is null or payment.settlement_id <> new.settlement_id or not exists (
        select 1 from gba.settlement_events e where e.tenant_id = new.tenant_id
        and e.book_id = new.book_id and e.settlement_id = new.settlement_id
        and e.sequence = new.sequence
        and e.kind = case new.kind when 'voided' then 'payment_voided' else 'payment_corrected' end
        and e.created_by = new.created_by
        and e.created_transaction = pg_catalog.pg_current_xact_id()) then
        raise exception using errcode = 'check_violation',
            message = 'a payment revision is recorded with its settlement event';
    end if;
    select * into latest from gba.external_payment_revisions r
        where r.tenant_id = new.tenant_id and r.book_id = new.book_id
        and r.payment_id = new.payment_id
        order by r.revision desc limit 1;
    if latest.kind = 'voided' then
        raise exception using errcode = 'check_violation', message = 'a voided payment is final';
    end if;
    if new.revision <> coalesce(latest.revision, 1) + 1 then
        raise exception using errcode = 'check_violation',
            message = 'payment revisions are contiguous';
    end if;
    if new.sequence <= coalesce(latest.sequence,payment.sequence) then
        raise exception using errcode = 'check_violation',
            message = 'a payment revision follows its previous confirmation event';
    end if;
    if new.kind = 'corrected' then
        if not exists (select 1 from gba.ledger_accounts a
            join gba.ledger_account_versions v on v.tenant_id = a.tenant_id and v.account_id = a.id
            where a.tenant_id = new.tenant_id and a.book_id = new.book_id
            and a.id = new.cash_account_id and a.type = 'asset' and not v.archived
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
    end if;
    return new;
end;
$$;

create or replace function gba.assert_payment_consistent(tenant uuid, book uuid, payment uuid)
    returns void language plpgsql as $$
declare
    p gba.external_payments%rowtype;
    r gba.external_payment_revisions%rowtype;
    entry gba.journal_entries%rowtype;
    total numeric;
    cash_side text;
    control_side text;
    replaced uuid;
    replaced_on date;
    expected integer;
    previous_sequence integer;
    touched uuid[];
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
    replaced := p.entry_id;
    replaced_on := p.entry_date;
    expected := 2;
    previous_sequence := p.sequence;
    for r in select * from gba.external_payment_revisions x
        where x.tenant_id = tenant and x.book_id = book and x.payment_id = payment
        order by x.revision loop
        if replaced is null or r.revision <> expected or r.settlement_id <> p.settlement_id then
            raise exception using errcode = 'check_violation',
                message = 'payment revisions are contiguous and a voided payment is final';
        end if;
        if r.sequence <= previous_sequence then
            raise exception using errcode = 'check_violation',
                message = 'a payment revision follows its previous confirmation event';
        end if;
        previous_sequence := r.sequence;
        if r.entry_date < replaced_on then
            raise exception using errcode = 'check_violation',
                message = 'a payment correction cannot be posted before the version it replaces';
        end if;
        select * into entry from gba.journal_entries e
            where e.tenant_id = tenant and e.book_id = book and e.id = r.reversal_entry_id;
        if entry.id is null
            or row(entry.source_kind,entry.source_id,entry.currency,entry.entry_date,entry.created_by)
            is distinct from row('payment_correction'::text,
                p.id::text || ':' || r.revision || ':reversal', p.currency, r.entry_date,
                r.created_by)
            or exists (
                (select j.line_no,j.account_id,j.side,j.amount_minor from gba.journal_lines j
                    where j.tenant_id = tenant and j.entry_id = r.reversal_entry_id
                 except all
                 select j.line_no,j.account_id,
                    case j.side when 'debit' then 'credit' else 'debit' end,j.amount_minor
                    from gba.journal_lines j where j.tenant_id = tenant and j.entry_id = replaced)
                union all
                (select j.line_no,j.account_id,
                    case j.side when 'debit' then 'credit' else 'debit' end,j.amount_minor
                    from gba.journal_lines j where j.tenant_id = tenant and j.entry_id = replaced
                 except all
                 select j.line_no,j.account_id,j.side,j.amount_minor from gba.journal_lines j
                    where j.tenant_id = tenant and j.entry_id = r.reversal_entry_id)) then
            raise exception using errcode = 'check_violation',
                message = 'payment reversal must mirror the journal it replaces';
        end if;
        if r.kind = 'corrected' then
            if not exists (select 1 from gba.external_payment_revision_allocations a
                where a.tenant_id = tenant and a.book_id = book and a.payment_id = payment
                and a.revision = r.revision) or exists (select 1 from (
                select a.line_no, a.created_transaction,
                    row_number() over (order by a.line_no) as position
                from gba.external_payment_revision_allocations a
                where a.tenant_id = tenant and a.book_id = book and a.payment_id = payment
                and a.revision = r.revision) x
                where x.line_no <> x.position or x.created_transaction <> r.created_transaction) then
                raise exception using errcode = 'check_violation',
                    message = 'correction allocations are complete with their revision';
            end if;
            select coalesce(sum(a.amount_minor), 0) into total
                from gba.external_payment_revision_allocations a
                where a.tenant_id = tenant and a.book_id = book and a.payment_id = payment
                and a.revision = r.revision;
            if total <> r.amount_minor then
                raise exception using errcode = 'check_violation',
                    message = 'correction allocations must equal the corrected amount';
            end if;
            if exists (select 1 from gba.external_payment_revision_allocations a
                join gba.financial_obligations o on o.tenant_id = a.tenant_id
                    and o.book_id = a.book_id and o.id = a.obligation_id
                where a.tenant_id = tenant and a.book_id = book and a.payment_id = payment
                and a.revision = r.revision and o.control_account_id = r.cash_account_id) then
                raise exception using errcode = 'check_violation',
                    message = 'cash account cannot be an obligation control account';
            end if;
            if exists (select 1 from gba.external_payment_revision_allocations a
                join gba.financial_obligations o on o.tenant_id = a.tenant_id
                    and o.book_id = a.book_id and o.id = a.obligation_id
                join gba.financial_document_versions v on v.tenant_id = o.tenant_id
                    and v.book_id = o.book_id and v.document_id = o.source_id
                    and v.revision = o.source_revision
                where a.tenant_id = tenant and a.book_id = book and a.payment_id = payment
                and a.revision = r.revision and v.issued_on > r.entry_date) then
                raise exception using errcode = 'check_violation',
                    message = 'a payment cannot be posted before the accrual it settles';
            end if;
            select * into entry from gba.journal_entries e
                where e.tenant_id = tenant and e.book_id = book and e.id = r.entry_id;
            if entry.id is null
                or row(entry.source_kind,entry.source_id,entry.currency,entry.entry_date,
                    entry.created_by)
                is distinct from row('payment_correction'::text,
                    p.id::text || ':' || r.revision || ':replacement', p.currency, r.entry_date,
                    r.created_by) then
                raise exception using errcode = 'check_violation',
                    message = 'payment correction journal lineage must match';
            end if;
            if exists (
                (select j.line_no,j.account_id,j.side,j.amount_minor from gba.journal_lines j
                    where j.tenant_id = tenant and j.entry_id = r.entry_id
                 except all
                 (select 1::smallint,r.cash_account_id,cash_side,r.amount_minor
                  union all
                  select (a.line_no+1)::smallint,o.control_account_id,control_side,a.amount_minor
                    from gba.external_payment_revision_allocations a
                    join gba.financial_obligations o on o.tenant_id = a.tenant_id
                        and o.book_id = a.book_id and o.id = a.obligation_id
                    where a.tenant_id = tenant and a.book_id = book and a.payment_id = payment
                    and a.revision = r.revision))
                union all
                ((select 1::smallint,r.cash_account_id,cash_side,r.amount_minor
                  union all
                  select (a.line_no+1)::smallint,o.control_account_id,control_side,a.amount_minor
                    from gba.external_payment_revision_allocations a
                    join gba.financial_obligations o on o.tenant_id = a.tenant_id
                        and o.book_id = a.book_id and o.id = a.obligation_id
                    where a.tenant_id = tenant and a.book_id = book and a.payment_id = payment
                    and a.revision = r.revision)
                 except all
                 select j.line_no,j.account_id,j.side,j.amount_minor from gba.journal_lines j
                    where j.tenant_id = tenant and j.entry_id = r.entry_id)
            ) then
                raise exception using errcode = 'check_violation',
                    message = 'payment correction journal must match the cash line and every allocation';
            end if;
        elsif exists (select 1 from gba.external_payment_revision_allocations a
            where a.tenant_id = tenant and a.book_id = book and a.payment_id = payment
            and a.revision = r.revision) then
            raise exception using errcode = 'check_violation',
                message = 'a voided payment has no allocations';
        end if;
        if r.created_transaction = pg_catalog.pg_current_xact_id() then
            select array_agg(distinct t.obligation_id) into touched from (
                select a.obligation_id from gba.external_payment_allocations a
                    where a.tenant_id = tenant and a.book_id = book and a.payment_id = payment
                    and r.revision = 2
                union all
                select a.obligation_id from gba.external_payment_revision_allocations a
                    where a.tenant_id = tenant and a.book_id = book and a.payment_id = payment
                    and a.revision in (r.revision - 1, r.revision)) t;
            if exists (select 1 from gba.financial_document_versions v
                where v.tenant_id = tenant and v.book_id = book and v.state = 'issued'
                and v.credited_obligation_id = any(touched)
                and not gba.credit_voided(tenant, book, v.document_id)) then
                raise exception using errcode = 'check_violation',
                    message = 'an issued credit depends on this payment; reconcile it separately';
            end if;
            if exists (select 1 from gba.financial_obligations o
                where o.tenant_id = tenant and o.book_id = book and o.id = any(touched)
                and o.source_kind = 'credit_refund') then
                raise exception using errcode = 'check_violation',
                    message = 'a refund payment is reconciled separately';
            end if;
            if exists (select 1 from gba.settlement_allocations s
                where s.tenant_id = tenant and s.book_id = book
                and s.settlement_id <> p.settlement_id and s.obligation_id = any(touched)
                and gba.settlement_phase(tenant, book, s.settlement_id) = 'sent'
                and (select coalesce(sum(x.amount_minor), 0) from gba.settlement_allocations x
                    where x.tenant_id = tenant and x.book_id = book
                    and x.settlement_id = s.settlement_id)
                    > (select coalesce(sum(e.amount_minor), 0)
                    from gba.effective_payment_allocations(tenant, book, null::uuid,
                        s.settlement_id) e)) then
                raise exception using errcode = 'check_violation',
                    message = 'a sent outcome depends on this payment; reconcile it separately';
            end if;
        end if;
        replaced := r.entry_id;
        replaced_on := r.entry_date;
        expected := expected + 1;
    end loop;
    perform gba.assert_settlement_consistent(tenant, book, p.settlement_id);
end;
$$;

create or replace function gba.enforce_financial_version() returns trigger language plpgsql as $$
declare
    previous gba.financial_document_versions%rowtype;
    credited gba.financial_obligations%rowtype;
    document_kind text;
begin
    perform gba.lock_ledger(new.tenant_id);
    select * into previous from gba.financial_document_versions v
        where v.tenant_id = new.tenant_id and v.book_id = new.book_id and v.document_id = new.document_id
        order by v.revision desc limit 1;
    select d.kind into document_kind from gba.financial_documents d
        where d.tenant_id = new.tenant_id and d.book_id = new.book_id and d.id = new.document_id;
    if document_kind = 'credit_note' and new.line_count > 198 then
        raise exception using errcode = 'check_violation',
            message = 'a credit note has at most 198 lines';
    end if;
    if new.state = 'voided' then
        if document_kind is distinct from 'credit_note' or previous.state is distinct from 'issued'
            or new.revision <> previous.revision + 1 then
            raise exception using errcode = 'check_violation',
                message = 'only an issued credit note is voided, once';
        end if;
        if row(new.direction,new.counterparty_id,new.counterparty_revision,new.currency,
               new.invoice_date,new.due_date,new.control_account_id,new.title,new.number,
               new.principal_minor,new.line_count,new.credited_obligation_id,new.entry_id,
               new.obligation_id,new.issued_on,new.attestation,new.applied_minor,
               new.refund_control_account_id)
           is distinct from
           row(previous.direction,previous.counterparty_id,previous.counterparty_revision,
               previous.currency,previous.invoice_date,previous.due_date,previous.control_account_id,
               previous.title,previous.number,previous.principal_minor,previous.line_count,
               previous.credited_obligation_id,previous.entry_id,previous.obligation_id,
               previous.issued_on,previous.attestation,previous.applied_minor,
               previous.refund_control_account_id) then
            raise exception using errcode = 'check_violation',
                message = 'a void preserves the issued credit note';
        end if;
        return new;
    end if;
    if new.revision <> coalesce(previous.revision, 0) + 1
        or previous.state in ('issued', 'voided') or (previous.revision is null and new.state <> 'draft') then
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
    if gba.cash_account_used(new.tenant_id, new.book_id, new.control_account_id) then
        raise exception using errcode = 'check_violation',
            message = 'a cash account cannot be a financial control account';
    end if;
    if coalesce(document_kind = 'credit_note', false) <> (new.credited_obligation_id is not null) then
        raise exception using errcode = 'check_violation',
            message = 'only a credit note names the obligation it credits';
    end if;
    if new.credited_obligation_id is not null then
        select * into credited from gba.financial_obligations o where o.tenant_id = new.tenant_id
            and o.book_id = new.book_id and o.id = new.credited_obligation_id;
        if credited.id is null or credited.source_kind not in ('invoice', 'manual')
            or row(credited.direction, credited.counterparty_id, credited.currency,
                credited.control_account_id)
            is distinct from row(new.direction, new.counterparty_id, new.currency,
                new.control_account_id) then
            raise exception using errcode = 'check_violation',
                message = 'a credit note follows the invoice or accrual obligation it credits';
        end if;
    end if;
    if new.refund_control_account_id is not null and (not exists (select 1 from gba.ledger_accounts a
        join gba.ledger_account_versions v on v.tenant_id = a.tenant_id and v.account_id = a.id
        where a.tenant_id = new.tenant_id and a.book_id = new.book_id
        and a.id = new.refund_control_account_id
        and a.type = case new.direction when 'receivable' then 'liability' else 'asset' end
        and not v.archived and v.revision = (select max(x.revision) from gba.ledger_account_versions x
            where x.tenant_id = a.tenant_id and x.account_id = a.id))
        or gba.cash_account_used(new.tenant_id, new.book_id, new.refund_control_account_id)) then
        raise exception using errcode = 'check_violation',
            message = 'a refund needs an open opposite control account that is not cash';
    end if;
    if new.state = 'issued' and
       row(new.direction,new.counterparty_id,new.counterparty_revision,new.currency,
           new.invoice_date,new.due_date,new.control_account_id,new.title,new.number,
           new.principal_minor,new.line_count,new.credited_obligation_id)
       is distinct from
       row(previous.direction,previous.counterparty_id,previous.counterparty_revision,previous.currency,
           previous.invoice_date,previous.due_date,previous.control_account_id,previous.title,previous.number,
           previous.principal_minor,previous.line_count,previous.credited_obligation_id) then
        raise exception using errcode = 'check_violation', message = 'issue preserves the saved draft';
    end if;
    return new;
end;
$$;

create or replace function gba.assert_invoice_consistent(tenant uuid, book uuid, document uuid)
    returns void language plpgsql as $$
declare
    v gba.financial_document_versions%rowtype;
    obligation gba.financial_obligations%rowtype;
    credited gba.financial_obligations%rowtype;
    entry gba.journal_entries%rowtype;
    balance record;
    count_lines integer;
    total numeric;
    refund bigint;
    accrued date;
    document_kind text;
    obligation_source text;
    journal_source text;
    reduce_side text;
    reverse_side text;
begin
    select d.kind into document_kind from gba.financial_documents d
        where d.tenant_id = tenant and d.book_id = book and d.id = document;
    if document_kind is null or not exists (select 1 from gba.financial_document_versions x
        where x.tenant_id = tenant and x.book_id = book and x.document_id = document) then
        raise exception using errcode = 'check_violation', message = 'financial document needs a saved version';
    end if;
    obligation_source := case document_kind when 'invoice' then 'invoice' else 'manual' end;
    journal_source := case document_kind when 'invoice' then 'invoice' else 'accrual' end;
    -- Whole-document recheck also protects draft1->issue2->late draft1 append.
    for v in select * from gba.financial_document_versions x
        where x.tenant_id = tenant and x.book_id = book and x.document_id = document loop
        if document_kind = 'credit_note' and v.line_count > 198 then
            raise exception using errcode = 'check_violation',
                message = 'a credit note has at most 198 lines';
        end if;
        select count(*), coalesce(sum(l.amount_minor),0) into count_lines,total
            from gba.financial_document_lines l
            where l.tenant_id = tenant and l.book_id = book and l.document_id = document
            and l.revision = v.revision;
        if count_lines <> v.line_count or total <> v.principal_minor or exists (
            select 1 from generate_series(1,v.line_count) n where not exists (
                select 1 from gba.financial_document_lines l where l.tenant_id = tenant
                and l.book_id = book and l.document_id = document
                and l.revision = v.revision and l.line_no = n)
        ) then
            raise exception using errcode = 'check_violation', message = 'invoice total and complete lines must match';
        end if;
        if v.state in ('issued', 'voided') then
            if exists (
                (select line_no,line_id,counter_account_id,description,amount_minor,
                        credited_line_id,reason,reference_entry_id
                    from gba.financial_document_lines l where l.tenant_id = tenant and l.book_id = book
                    and l.document_id = document and l.revision = v.revision
                 except all
                 select line_no,line_id,counter_account_id,description,amount_minor,
                        credited_line_id,reason,reference_entry_id
                    from gba.financial_document_lines l where l.tenant_id = tenant and l.book_id = book
                    and l.document_id = document and l.revision = v.revision - 1)
                union all
                (select line_no,line_id,counter_account_id,description,amount_minor,
                        credited_line_id,reason,reference_entry_id
                    from gba.financial_document_lines l where l.tenant_id = tenant and l.book_id = book
                    and l.document_id = document and l.revision = v.revision - 1
                 except all
                 select line_no,line_id,counter_account_id,description,amount_minor,
                        credited_line_id,reason,reference_entry_id
                    from gba.financial_document_lines l where l.tenant_id = tenant and l.book_id = book
                    and l.document_id = document and l.revision = v.revision)
            ) then
                raise exception using errcode = 'check_violation', message = 'issued lines preserve the draft';
            end if;
        end if;
        if v.state = 'issued' then
            select * into obligation from gba.financial_obligations o where o.tenant_id = tenant
                and o.book_id = book and o.id = v.obligation_id;
            select * into entry from gba.journal_entries e where e.tenant_id = tenant
                and e.book_id = book and e.id = v.entry_id;
            if document_kind <> 'credit_note' then
                if obligation.id is null or entry.id is null
                    or obligation.source_kind is distinct from obligation_source
                    or obligation.component is distinct from 'principal'
                    or row(obligation.source_id,obligation.source_revision,obligation.counterparty_id,
                        obligation.counterparty_revision,obligation.direction,obligation.currency,
                        obligation.control_account_id,obligation.principal_minor,obligation.created_by,
                        obligation.created_transaction)
                    is distinct from row(document,v.revision,v.counterparty_id,v.counterparty_revision,
                        v.direction,v.currency,v.control_account_id,v.principal_minor,v.created_by,
                        v.created_transaction)
                    or row(entry.source_kind,entry.source_id,entry.currency,entry.entry_date,entry.created_by)
                    is distinct from row(journal_source,document::text,v.currency,v.issued_on,v.created_by)
                    or not exists (select 1 from gba.financial_operation_entries o
                        where o.tenant_id = tenant and o.book_id = book and o.document_id = document
                        and o.revision = v.revision and o.component = 'principal' and o.entry_id = v.entry_id
                        and o.obligation_id = v.obligation_id and o.created_transaction = v.created_transaction)
                then
                    raise exception using errcode = 'check_violation', message = 'invoice obligation and journal lineage must match';
                end if;
                if exists (
                    (select line_no,account_id,side,amount_minor from gba.journal_lines j
                        where j.tenant_id = tenant and j.entry_id = v.entry_id
                     except all
                     (select 1::smallint,v.control_account_id,
                        case v.direction when 'receivable' then 'debit' else 'credit' end,v.principal_minor
                      union all
                      select (l.line_no+1)::smallint,l.counter_account_id,
                        case v.direction when 'receivable' then 'credit' else 'debit' end,l.amount_minor
                        from gba.financial_document_lines l where l.tenant_id = tenant and l.book_id = book
                        and l.document_id = document and l.revision = v.revision))
                    union all
                    ((select 1::smallint,v.control_account_id,
                        case v.direction when 'receivable' then 'debit' else 'credit' end,v.principal_minor
                      union all
                      select (l.line_no+1)::smallint,l.counter_account_id,
                        case v.direction when 'receivable' then 'credit' else 'debit' end,l.amount_minor
                        from gba.financial_document_lines l where l.tenant_id = tenant and l.book_id = book
                        and l.document_id = document and l.revision = v.revision)
                     except all
                     select line_no,account_id,side,amount_minor from gba.journal_lines j
                        where j.tenant_id = tenant and j.entry_id = v.entry_id)
                ) then
                    raise exception using errcode = 'check_violation', message = 'invoice journal must match the complete issued lines';
                end if;
            else
                refund := v.principal_minor - v.applied_minor;
                if entry.id is null
                    or row(entry.source_kind,entry.source_id,entry.currency,entry.entry_date,entry.created_by)
                    is distinct from row('credit'::text,document::text,v.currency,v.issued_on,v.created_by)
                    or (refund > 0 and (obligation.id is null
                        or row(obligation.source_kind,obligation.component,obligation.source_id,
                            obligation.source_revision,obligation.counterparty_id,
                            obligation.counterparty_revision,obligation.direction,obligation.currency,
                            obligation.control_account_id,obligation.principal_minor,
                            obligation.created_by,obligation.created_transaction)
                        is distinct from row('credit_refund'::text,'principal'::text,document,
                            v.revision,v.counterparty_id,v.counterparty_revision,
                            case v.direction when 'receivable' then 'payable' else 'receivable' end,
                            v.currency,v.refund_control_account_id,refund,v.created_by,
                            v.created_transaction)))
                    or (refund > 0) <> exists (select 1 from gba.financial_operation_entries o
                        where o.tenant_id = tenant and o.book_id = book and o.document_id = document
                        and o.revision = v.revision)
                    or exists (select 1 from gba.financial_operation_entries o
                        where o.tenant_id = tenant and o.book_id = book and o.document_id = document
                        and o.revision = v.revision
                        and (o.component <> 'principal' or o.entry_id <> v.entry_id
                            or o.obligation_id is distinct from v.obligation_id
                            or o.created_transaction <> v.created_transaction))
                then
                    raise exception using errcode = 'check_violation',
                        message = 'credit refund obligation and journal lineage must match';
                end if;
                reduce_side := case v.direction when 'receivable' then 'credit' else 'debit' end;
                reverse_side := case v.direction when 'receivable' then 'debit' else 'credit' end;
                if exists (
                    with expected as (
                        select l.line_no,l.counter_account_id as account_id,reverse_side as side,l.amount_minor
                            from gba.financial_document_lines l where l.tenant_id = tenant
                            and l.book_id = book and l.document_id = document and l.revision = v.revision
                        union all
                        select (v.line_count+1)::smallint,v.control_account_id,reduce_side,v.applied_minor
                            where v.applied_minor > 0
                        union all
                        select (v.line_count+1+(v.applied_minor > 0)::integer)::smallint,
                            v.refund_control_account_id,reduce_side,refund
                            where refund > 0
                    ), actual as (
                        select j.line_no,j.account_id,j.side,j.amount_minor from gba.journal_lines j
                            where j.tenant_id = tenant and j.entry_id = v.entry_id
                    )
                    (select * from actual except all select * from expected)
                    union all
                    (select * from expected except all select * from actual)
                ) then
                    raise exception using errcode = 'check_violation',
                        message = 'credit journal must match its lines and split';
                end if;
                select * into credited from gba.financial_obligations o where o.tenant_id = tenant
                    and o.book_id = book and o.id = v.credited_obligation_id;
                select x.issued_on into accrued from gba.financial_document_versions x
                    where x.tenant_id = tenant and x.book_id = book
                    and x.document_id = credited.source_id and x.revision = credited.source_revision;
                if credited.id is null or accrued is null or v.issued_on < accrued then
                    raise exception using errcode = 'check_violation',
                        message = 'a credit cannot be posted before the accrual it credits';
                end if;
                if v.created_transaction = pg_catalog.pg_current_xact_id() then
                    select * into balance from gba.obligation_balance(tenant, book, credited.id);
                    if balance.reserved_minor <> 0 then
                        raise exception using errcode = 'check_violation',
                            message = 'resolve active reserves before issuing a credit';
                    end if;
                    if balance.paid_minor < 0 or balance.credited_minor < 0
                        or balance.paid_minor::numeric + balance.credited_minor > balance.principal_minor then
                        raise exception using errcode = 'check_violation',
                            message = 'obligation credit cap exceeded';
                    end if;
                    if refund > 0 and balance.paid_minor::numeric + balance.credited_minor
                        <> balance.principal_minor then
                        raise exception using errcode = 'check_violation',
                            message = 'a credit refunds only what remains after the unpaid balance';
                    end if;
                    if exists (select 1 from gba.financial_document_lines o
                        where o.tenant_id = tenant and o.book_id = book
                        and o.document_id = credited.source_id and o.revision = credited.source_revision
                        and o.amount_minor < (select coalesce(sum(c.amount_minor), 0)
                            from gba.financial_document_lines c
                            join gba.financial_document_versions x on x.tenant_id = c.tenant_id
                                and x.book_id = c.book_id and x.document_id = c.document_id
                                and x.revision = c.revision
                            where x.tenant_id = tenant and x.book_id = book
                            and x.credited_obligation_id = credited.id and x.state = 'issued'
                            and not gba.credit_voided(tenant, book, x.document_id)
                            and c.credited_line_id = o.line_id)) then
                        raise exception using errcode = 'check_violation',
                            message = 'a credit exceeds the uncredited amount of a line';
                    end if;
                end if;
            end if;
        elsif v.state = 'voided' then
            select * into entry from gba.journal_entries e where e.tenant_id = tenant
                and e.book_id = book and e.id = v.void_entry_id;
            if document_kind <> 'credit_note' or entry.id is null
                or row(entry.source_kind,entry.source_id,entry.currency,entry.entry_date,entry.created_by)
                is distinct from row('credit_void'::text,document::text,v.currency,v.voided_on,
                    v.created_by) then
                raise exception using errcode = 'check_violation',
                    message = 'credit void journal lineage must match';
            end if;
            if exists (
                (select j.line_no,j.account_id,j.side,j.amount_minor from gba.journal_lines j
                    where j.tenant_id = tenant and j.entry_id = v.void_entry_id
                 except all
                 select j.line_no,j.account_id,
                    case j.side when 'debit' then 'credit' else 'debit' end,j.amount_minor
                    from gba.journal_lines j where j.tenant_id = tenant and j.entry_id = v.entry_id)
                union all
                (select j.line_no,j.account_id,
                    case j.side when 'debit' then 'credit' else 'debit' end,j.amount_minor
                    from gba.journal_lines j where j.tenant_id = tenant and j.entry_id = v.entry_id
                 except all
                 select j.line_no,j.account_id,j.side,j.amount_minor from gba.journal_lines j
                    where j.tenant_id = tenant and j.entry_id = v.void_entry_id)) then
                raise exception using errcode = 'check_violation',
                    message = 'a credit void must mirror the credit journal';
            end if;
            if v.voided_on < v.issued_on then
                raise exception using errcode = 'check_violation',
                    message = 'a credit void cannot be posted before the credit';
            end if;
            if v.created_transaction = pg_catalog.pg_current_xact_id() then
                if v.obligation_id is not null then
                    select * into balance from gba.obligation_balance(tenant, book, v.obligation_id);
                    if balance.paid_minor <> 0 or balance.reserved_minor <> 0 then
                        raise exception using errcode = 'check_violation',
                            message = 'a refund that was paid or is reserved is reconciled separately';
                    end if;
                end if;
                if v.applied_minor > 0 and exists (select 1 from gba.financial_document_versions x
                    where x.tenant_id = tenant and x.book_id = book and x.document_id <> document
                    and x.credited_obligation_id = v.credited_obligation_id and x.state = 'issued'
                    and x.applied_minor < x.principal_minor
                    and not gba.credit_voided(tenant, book, x.document_id)) then
                    raise exception using errcode = 'check_violation',
                        message = 'a refunded credit depends on this credit; reconcile it separately';
                end if;
            end if;
        end if;
    end loop;
end;
$$;

create or replace function gba.enforce_financial_line() returns trigger language plpgsql as $$
declare
    version gba.financial_document_versions%rowtype;
    original gba.financial_document_lines%rowtype;
begin
    perform gba.lock_ledger(new.tenant_id);
    select * into version from gba.financial_document_versions v
        where v.tenant_id = new.tenant_id and v.book_id = new.book_id
        and v.document_id = new.document_id and v.revision = new.revision;
    if version.revision is null or version.created_transaction <> pg_catalog.pg_current_xact_id() then
        raise exception using errcode = 'check_violation', message = 'invoice lines are written with their version';
    end if;
    -- A void keeps the exact issued line; it creates no new account treatment.
    -- Only this immutable copy may name a counter account archived since issue.
    if version.state = 'voided' then
        select l.* into original from gba.financial_document_lines l
            where l.tenant_id=new.tenant_id and l.book_id=new.book_id
            and l.document_id=new.document_id and l.revision=new.revision-1
            and l.line_no=new.line_no;
        if original.line_id is null or
            row(new.line_id,new.credited_line_id,new.counter_account_id,new.description,
                new.amount_minor,new.reason,new.reference_entry_id)
            is distinct from row(original.line_id,original.credited_line_id,
                original.counter_account_id,original.description,original.amount_minor,
                original.reason,original.reference_entry_id) then
            raise exception using errcode = 'check_violation',
                message = 'a void preserves every issued credit line';
        end if;
        return new;
    end if;
    if not exists (select 1 from gba.ledger_accounts a
        join gba.ledger_account_versions v on v.tenant_id = a.tenant_id and v.account_id = a.id
        where a.tenant_id = new.tenant_id and a.book_id = new.book_id and a.id = new.counter_account_id
        and ((version.direction = 'receivable' and a.type in ('revenue','liability'))
            or (version.direction = 'payable' and a.type in ('expense','asset')))
        and not v.archived and v.revision = (select max(x.revision) from gba.ledger_account_versions x
            where x.tenant_id = a.tenant_id and x.account_id = a.id)) then
        raise exception using errcode = 'check_violation', message = 'invoice needs an open counter account';
    end if;
    if (version.credited_obligation_id is not null) <> (new.credited_line_id is not null) then
        raise exception using errcode = 'check_violation',
            message = 'only a credit line names the line it credits';
    end if;
    if new.credited_line_id is not null then
        select l.* into original from gba.financial_obligations o
            join gba.financial_document_lines l on l.tenant_id = o.tenant_id
                and l.book_id = o.book_id and l.document_id = o.source_id
                and l.revision = o.source_revision
            where o.tenant_id = new.tenant_id and o.book_id = new.book_id
            and o.id = version.credited_obligation_id and l.line_id = new.credited_line_id;
        if original.line_id is null then
            raise exception using errcode = 'check_violation',
                message = 'a credit line needs a line of the credited document';
        end if;
        if new.amount_minor > original.amount_minor then
            raise exception using errcode = 'check_violation',
                message = 'a credit line exceeds its original line';
        end if;
        if (new.counter_account_id <> original.counter_account_id) <> (new.reason is not null) then
            raise exception using errcode = 'check_violation',
                message = 'a reason accompanies exactly another account than the credited line';
        end if;
        if new.reference_entry_id is not null and not exists (select 1 from gba.journal_entries e
            where e.tenant_id = new.tenant_id and e.book_id = new.book_id
            and e.id = new.reference_entry_id and e.currency = version.currency) then
            raise exception using errcode = 'check_violation',
                message = 'a cited entry shares the book and currency of the credit';
        end if;
    end if;
    return new;
end;
$$;

-- Explicit H lineage, not a caller-supplied archive exemption. A replacement
-- entry NEVER resolves here. Only the current transaction's historical mirror
-- targets resolve to their immediately preceding effective journal.
create function gba.financial_mirror_original(tenant uuid, book uuid, entry uuid, kind text)
    returns uuid language plpgsql as $$
declare original uuid;
begin
    if kind = 'credit_void' then
        select v.entry_id into original from gba.financial_document_versions v
            join gba.financial_documents d on d.tenant_id=v.tenant_id
                and d.book_id=v.book_id and d.id=v.document_id
            where v.tenant_id=tenant and v.book_id=book and v.void_entry_id=entry
            and v.state='voided' and d.kind='credit_note'
            and v.created_transaction=pg_catalog.pg_current_xact_id();
    elsif kind = 'payment_correction' then
        select case when r.revision=2 then p.entry_id else previous.entry_id end into original
            from gba.external_payment_revisions r join gba.external_payments p
                on p.tenant_id=r.tenant_id and p.book_id=r.book_id and p.id=r.payment_id
            left join gba.external_payment_revisions previous
                on previous.tenant_id=r.tenant_id and previous.book_id=r.book_id
                and previous.payment_id=r.payment_id and previous.revision=r.revision-1
                and previous.kind='corrected'
            where r.tenant_id=tenant and r.book_id=book and r.reversal_entry_id=entry
            and r.created_transaction=pg_catalog.pg_current_xact_id();
    end if;
    return original;
end;
$$;
revoke all on function gba.financial_mirror_original(uuid,uuid,uuid,text) from public;
grant execute on function gba.financial_mirror_original(uuid,uuid,uuid,text) to gba_runtime;



create or replace function gba.enforce_journal_line() returns trigger
    language plpgsql as $$
declare
    entry gba.journal_entries%rowtype;
    original uuid;
begin
    select * into entry from gba.journal_entries e
     where e.tenant_id = new.tenant_id and e.id = new.entry_id
       and e.book_id = new.book_id and e.created_at = pg_catalog.now();
    if entry.id is null then
        raise exception using errcode = 'check_violation',
            message = 'journal lines are written with their entry';
    end if;
    if exists (select 1 from gba.journal_entries r
               where r.tenant_id = entry.tenant_id and r.reverses_entry_id = entry.id) then
        raise exception using errcode = 'check_violation',
            message = 'a reversed entry cannot receive additional lines';
    end if;
    if entry.reverses_entry_id is null and not exists (
        select 1 from gba.ledger_account_versions v
        where v.tenant_id = new.tenant_id and v.account_id = new.account_id and not v.archived
          and v.revision = (select max(x.revision) from gba.ledger_account_versions x
              where x.tenant_id = v.tenant_id and x.account_id = v.account_id)
    ) then
        original := gba.financial_mirror_original(
            new.tenant_id,new.book_id,new.entry_id,entry.source_kind);
        if original is null or not exists (select 1 from gba.journal_lines l
            where l.tenant_id=new.tenant_id and l.book_id=new.book_id and l.entry_id=original
            and l.line_no=new.line_no and l.account_id=new.account_id
            and l.amount_minor=new.amount_minor
            and l.side=case new.side when 'debit' then 'credit' else 'debit' end) then
            raise exception using errcode = 'check_violation',
                message = 'a line needs an open account or its verified historical mirror';
        end if;
    end if;
    return new;
end;
$$;
