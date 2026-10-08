-- H3 credit voids (ADR-0024 section 7). An issued credit note issued in error is voided
-- by one more immutable version of the same document (state 'voided') that keeps every
-- issued fact and adds the void journal, date, reason and evidence. One transaction
-- mirrors the credit journal line by line (new origin 'credit_void'), undoes the C of
-- the credited obligation and cancels its untouched refund obligation, whose C becomes
-- its principal so that it can never be reserved or paid. A refund that has an
-- effective payment, an active reserve or an unknown sent outcome is not undone: the
-- void is refused, as it is while another credit of the same obligation refunded money
-- on the strength of this one. A void is final. Migrations 0001-0028 are preserved;
-- replaced functions keep their names.

alter table gba.journal_entries drop constraint journal_entries_source_kind_check;
alter table gba.journal_entries add constraint journal_entries_source_kind_check
    check (source_kind in ('manual', 'opening', 'reversal', 'invoice', 'accrual', 'payment', 'credit', 'payment_correction', 'credit_void'));

alter table gba.financial_document_versions drop constraint financial_document_versions_state_check;
alter table gba.financial_document_versions add constraint financial_document_versions_state_check
    check (state in ('draft', 'issued', 'voided'));

alter table gba.financial_command_receipts
    drop constraint financial_command_receipts_operation_check;
alter table gba.financial_command_receipts add constraint financial_command_receipts_operation_check
    check (operation in ('invoice_draft', 'invoice_issue', 'accrual_draft', 'accrual_issue', 'credit_draft', 'credit_issue', 'credit_void'));

alter table gba.financial_command_cancellations
    drop constraint financial_command_cancellations_operation_check;
alter table gba.financial_command_cancellations
    add constraint financial_command_cancellations_operation_check
    check (operation in ('invoice_draft', 'invoice_issue', 'accrual_draft', 'accrual_issue', 'credit_draft', 'credit_issue', 'credit_void', 'settlement_prepare', 'settlement_approve', 'settlement_reserve', 'settlement_sent', 'settlement_confirm', 'settlement_release', 'settlement_cancel', 'settlement_payment_void', 'settlement_payment_correct'));

-- A voided version keeps the issued facts (journal, refund obligation, split, issue
-- date and attestation) and adds its own journal, date, reason and evidence source.
alter table gba.financial_document_versions add column void_entry_id uuid;
alter table gba.financial_document_versions add column voided_on date;
alter table gba.financial_document_versions add column void_reason text
    constraint financial_document_versions_void_reason_check check (
        void_reason is null or (length(btrim(void_reason)) between 1 and 500 and void_reason !~ '[[:cntrl:]]'));
alter table gba.financial_document_versions add column void_evidence_source text
    constraint financial_document_versions_void_evidence_source_check check (
        void_evidence_source is null or (length(btrim(void_evidence_source)) between 1 and 200
            and void_evidence_source !~ '[[:cntrl:]]'));
alter table gba.financial_document_versions add constraint financial_versions_void_entry_fk
    foreign key (tenant_id, book_id, void_entry_id)
    references gba.journal_entries(tenant_id, book_id, id) deferrable initially deferred;
alter table gba.financial_document_versions drop constraint financial_versions_issued_refs;
alter table gba.financial_document_versions add constraint financial_versions_issued_refs check (
    (state = 'draft' and entry_id is null and obligation_id is null and issued_on is null
        and attestation is null and applied_minor is null and refund_control_account_id is null)
    or (state in ('issued', 'voided') and revision >= 2 and entry_id is not null
        and issued_on is not null and attestation is not null
        and attestation = 'confirmed_account_treatment'
        and ((credited_obligation_id is null and obligation_id is not null
                and applied_minor is null and refund_control_account_id is null)
            or (credited_obligation_id is not null and applied_minor is not null
                and applied_minor <= principal_minor
                and (obligation_id is null) = (applied_minor = principal_minor)
                and (refund_control_account_id is null) = (applied_minor = principal_minor))))
);
alter table gba.financial_document_versions add constraint financial_versions_void_refs check (
    (state = 'voided') = (void_entry_id is not null)
    and (state = 'voided') = (voided_on is not null)
    and (state = 'voided') = (void_reason is not null)
    and (state = 'voided') = (void_evidence_source is not null)
    and (state <> 'voided' or (credited_obligation_id is not null and revision >= 3))
);

grant insert (void_entry_id, voided_on, void_reason, void_evidence_source)
    on gba.financial_document_versions to gba_runtime;

-- Whether a credit note was voided.
create function gba.credit_voided(tenant uuid, book uuid, document uuid) returns boolean
    language plpgsql as $$
begin
    return exists (select 1 from gba.financial_document_versions x
        where x.tenant_id = tenant and x.book_id = book and x.document_id = document
        and x.state = 'voided');
end;
$$;
revoke all on function gba.credit_voided(uuid, uuid, uuid) from public;
grant execute on function gba.credit_voided(uuid, uuid, uuid) to gba_runtime;

-- C is the unpaid part of every issued credit note of the obligation that was not
-- voided; a refund obligation of a voided credit is cancelled: its C is its principal.
create or replace function gba.obligation_balance(tenant uuid, book uuid, obligation uuid)
    returns table (principal_minor bigint, paid_minor bigint, credited_minor bigint, reserved_minor bigint)
    language plpgsql as $$
begin
    return query
    select o.principal_minor,
        coalesce((select sum(e.amount_minor)
            from gba.effective_payment_allocations(o.tenant_id, o.book_id, o.id, null::uuid) e), 0)::bigint,
        (coalesce((select sum(v.applied_minor) from gba.financial_document_versions v
            where v.tenant_id = o.tenant_id and v.book_id = o.book_id
            and v.credited_obligation_id = o.id and v.state = 'issued'
            and not gba.credit_voided(v.tenant_id, v.book_id, v.document_id)), 0)
        + case when o.source_kind = 'credit_refund'
            and gba.credit_voided(o.tenant_id, o.book_id, o.source_id)
            then o.principal_minor else 0 end)::bigint,
        coalesce((select sum(a.amount_minor - coalesce((select sum(e.amount_minor)
                from gba.effective_payment_allocations(a.tenant_id, a.book_id, a.obligation_id,
                    a.settlement_id) e), 0))
            from gba.settlement_allocations a
            where a.tenant_id = o.tenant_id and a.book_id = o.book_id and a.obligation_id = o.id
            and gba.settlement_phase(a.tenant_id, a.book_id, a.settlement_id)
                in ('reserved', 'sent')), 0)::bigint
    from gba.financial_obligations o
    where o.tenant_id = tenant and o.book_id = book and o.id = obligation;
end;
$$;

-- A void follows the issued version of a credit note once and preserves every issued
-- fact; nothing follows a void. Drafts and issues keep their earlier rules.
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

-- A credit void journal names its voided version of the same transaction; like every
-- H-owned origin it is never reversed by the generic G reversal.
create or replace function gba.enforce_invoice_origin() returns trigger language plpgsql as $$
declare original gba.journal_entries%rowtype;
begin
    perform gba.lock_ledger(new.tenant_id);
    if new.reverses_entry_id is not null then
        select * into original from gba.journal_entries e
            where e.tenant_id = new.tenant_id and e.id = new.reverses_entry_id;
        if original.source_kind in ('invoice', 'accrual', 'payment', 'credit', 'payment_correction',
            'credit_void') then
            raise exception using errcode = 'check_violation',
                message = 'H-owned journal correction requires its financial document';
        end if;
    end if;
    if new.source_kind in ('invoice', 'accrual', 'credit', 'credit_void') then
        perform pg_catalog.pg_advisory_xact_lock_shared(
            pg_catalog.hashtextextended('gba:business-configuration:' || new.tenant_id::text, 0));
        if not exists (select 1 from gba.business_module_states s
            where s.tenant_id = new.tenant_id and s.module_id = 'finance_documents' and s.enabled) then
            raise exception using errcode = 'GBM01',
                message = 'the finance_documents module is disabled for this business';
        end if;
        if new.source_kind = 'credit_void' then
            if not exists (select 1 from gba.financial_document_versions v
                join gba.financial_documents d on d.tenant_id = v.tenant_id
                    and d.book_id = v.book_id and d.id = v.document_id
                where v.tenant_id = new.tenant_id and v.book_id = new.book_id
                and v.state = 'voided' and d.kind = 'credit_note'
                and v.document_id::text = new.source_id and v.void_entry_id = new.id
                and v.currency = new.currency and v.voided_on = new.entry_date
                and v.created_by = new.created_by
                and v.created_transaction = pg_catalog.pg_current_xact_id()) then
                raise exception using errcode = 'check_violation',
                    message = 'credit void journal origin needs its voided version';
            end if;
        elsif not exists (select 1 from gba.financial_document_versions v
            join gba.financial_documents d on d.tenant_id = v.tenant_id
                and d.book_id = v.book_id and d.id = v.document_id
            where v.tenant_id = new.tenant_id and v.book_id = new.book_id and v.state = 'issued'
            and v.document_id::text = new.source_id and v.entry_id = new.id
            and d.kind = case new.source_kind when 'invoice' then 'invoice'
                when 'accrual' then 'manual_accrual' else 'credit_note' end
            and v.currency = new.currency and v.issued_on = new.entry_date
            and v.created_by = new.created_by
            and v.created_transaction = pg_catalog.pg_current_xact_id()) then
            raise exception using errcode = 'check_violation',
                message = 'financial journal origin needs its issued version';
        end if;
    elsif new.source_kind = 'payment' then
        perform gba.assert_financial_workflow(new.tenant_id);
        if not exists (select 1 from gba.external_payments p
            where p.tenant_id = new.tenant_id and p.book_id = new.book_id
            and p.id::text = new.source_id and p.entry_id = new.id
            and p.currency = new.currency and p.entry_date = new.entry_date
            and p.created_by = new.created_by
            and p.created_transaction = pg_catalog.pg_current_xact_id()) then
            raise exception using errcode = 'check_violation',
                message = 'payment journal origin needs its external payment';
        end if;
    elsif new.source_kind = 'payment_correction' then
        perform gba.assert_financial_workflow(new.tenant_id);
        if not exists (select 1 from gba.external_payment_revisions r
            join gba.external_payments p on p.tenant_id = r.tenant_id and p.book_id = r.book_id
                and p.id = r.payment_id
            where r.tenant_id = new.tenant_id and r.book_id = new.book_id
            and ((r.reversal_entry_id = new.id
                    and new.source_id = r.payment_id::text || ':' || r.revision || ':reversal')
                or (r.entry_id = new.id
                    and new.source_id = r.payment_id::text || ':' || r.revision || ':replacement'))
            and p.currency = new.currency and r.entry_date = new.entry_date
            and r.created_by = new.created_by
            and r.created_transaction = pg_catalog.pg_current_xact_id()) then
            raise exception using errcode = 'check_violation',
                message = 'payment correction journal origin needs its payment revision';
        end if;
    end if;
    return new;
end;
$$;

-- The whole document again at commit. Every issued or voided version keeps its lines.
-- An issued credit note keeps its exact journal and refund lineage; its balance rules
-- (no active reserve, cap, unpaid balance first, line capacity) are checked by the
-- transaction that issues it. A voided credit note mirrors the credit journal line by
-- line on its own date, no earlier than the credit; the transaction that voids it leaves
-- its cancelled refund obligation without any payment or reserve and no other refunded
-- credit of the same obligation that relied on its unpaid part.
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

-- Credit and credit-void journals and every credit receipt name their credit note.
create or replace function gba.check_invoice_integrity() returns trigger language plpgsql as $$
declare tenant uuid; book uuid; document uuid; entry gba.journal_entries%rowtype;
begin
    tenant := new.tenant_id;
    if tg_table_name = 'financial_documents' then
        book := new.book_id; document := new.id;
    elsif tg_table_name = 'financial_obligations' then
        book := new.book_id; document := new.source_id;
        if not exists (select 1 from gba.financial_document_versions v where v.tenant_id = tenant
            and v.book_id = book and v.document_id = document and v.state = 'issued'
            and v.revision = new.source_revision and v.obligation_id = new.id) then
            raise exception using errcode = 'check_violation', message = 'obligation needs its issued invoice';
        end if;
    elsif tg_table_name in ('journal_entries','journal_lines') then
        if tg_table_name = 'journal_entries' then entry := new;
        else select * into entry from gba.journal_entries e
            where e.tenant_id = tenant and e.id = new.entry_id; end if;
        if entry.source_kind not in ('invoice', 'accrual', 'credit', 'credit_void') then return null; end if;
        book := entry.book_id;
        select v.document_id into document from gba.financial_document_versions v
            where v.tenant_id = tenant and v.book_id = book
            and ((v.state = 'issued' and v.entry_id = entry.id)
                or (v.state = 'voided' and v.void_entry_id = entry.id));
        if document is null then
            raise exception using errcode = 'check_violation', message = 'invoice journal cannot be orphaned';
        end if;
    else
        book := new.book_id; document := new.document_id;
        if tg_table_name = 'financial_command_receipts' then
          if not exists (
            select 1 from gba.financial_document_versions v
            join gba.financial_documents d on d.tenant_id = v.tenant_id
                and d.book_id = v.book_id and d.id = v.document_id
            where v.tenant_id = tenant and v.book_id = book
            and v.document_id = document and v.revision = new.revision and v.created_by = new.created_by
            and new.operation = (case d.kind when 'invoice' then 'invoice'
                when 'manual_accrual' then 'accrual' else 'credit' end
                || case v.state when 'issued' then '_issue' when 'voided' then '_void'
                    else '_draft' end)
        ) then
            raise exception using errcode = 'check_violation', message = 'receipt needs its exact financial version';
          end if;
        elsif tg_table_name = 'financial_operation_entries' then
          if not exists (
            select 1 from gba.financial_document_versions v where v.tenant_id = tenant and v.book_id = book
            and v.document_id = document and v.revision = new.revision and v.state = 'issued'
            and new.component = 'principal'
            and v.entry_id = new.entry_id and v.obligation_id = new.obligation_id
            and v.created_transaction = new.created_transaction
        ) then
            raise exception using errcode = 'check_violation', message = 'financial effect needs its issued version';
          end if;
        end if;
    end if;
    perform gba.assert_invoice_consistent(tenant,book,document);
    return null;
end;
$$;

-- The complete payment and every revision, as in 0028, except that a voided credit
-- no longer depends on the payments of the obligation it credited.
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
    for r in select * from gba.external_payment_revisions x
        where x.tenant_id = tenant and x.book_id = book and x.payment_id = payment
        order by x.revision loop
        if replaced is null or r.revision <> expected or r.settlement_id <> p.settlement_id then
            raise exception using errcode = 'check_violation',
                message = 'payment revisions are contiguous and a voided payment is final';
        end if;
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

-- Approved PostgreSQL 18 CHECK deparse forms; they replace earlier approvals of the
-- same constraint. Readiness never learns them from a target database.
-- CHECK_APPROVAL {"table":"journal_entries","name":"journal_entries_source_kind_check","expression":"(source_kind = ANY (ARRAY['manual'::text, 'opening'::text, 'reversal'::text, 'invoice'::text, 'accrual'::text, 'payment'::text, 'credit'::text, 'payment_correction'::text, 'credit_void'::text]))"}
-- CHECK_APPROVAL {"table":"financial_document_versions","name":"financial_document_versions_state_check","expression":"(state = ANY (ARRAY['draft'::text, 'issued'::text, 'voided'::text]))"}
-- CHECK_APPROVAL {"table":"financial_command_receipts","name":"financial_command_receipts_operation_check","expression":"(operation = ANY (ARRAY['invoice_draft'::text, 'invoice_issue'::text, 'accrual_draft'::text, 'accrual_issue'::text, 'credit_draft'::text, 'credit_issue'::text, 'credit_void'::text]))"}
-- CHECK_APPROVAL {"table":"financial_command_cancellations","name":"financial_command_cancellations_operation_check","expression":"(operation = ANY (ARRAY['invoice_draft'::text, 'invoice_issue'::text, 'accrual_draft'::text, 'accrual_issue'::text, 'credit_draft'::text, 'credit_issue'::text, 'credit_void'::text, 'settlement_prepare'::text, 'settlement_approve'::text, 'settlement_reserve'::text, 'settlement_sent'::text, 'settlement_confirm'::text, 'settlement_release'::text, 'settlement_cancel'::text, 'settlement_payment_void'::text, 'settlement_payment_correct'::text]))"}
-- CHECK_APPROVAL {"table":"financial_document_versions","name":"financial_document_versions_void_reason_check","expression":"((void_reason IS NULL) OR (((length(btrim(void_reason)) >= 1) AND (length(btrim(void_reason)) <= 500)) AND (void_reason !~ '[[:cntrl:]]'::text)))"}
-- CHECK_APPROVAL {"table":"financial_document_versions","name":"financial_document_versions_void_evidence_source_check","expression":"((void_evidence_source IS NULL) OR (((length(btrim(void_evidence_source)) >= 1) AND (length(btrim(void_evidence_source)) <= 200)) AND (void_evidence_source !~ '[[:cntrl:]]'::text)))"}
-- CHECK_APPROVAL {"table":"financial_document_versions","name":"financial_versions_issued_refs","expression":"(((state = 'draft'::text) AND (entry_id IS NULL) AND (obligation_id IS NULL) AND (issued_on IS NULL) AND (attestation IS NULL) AND (applied_minor IS NULL) AND (refund_control_account_id IS NULL)) OR ((state = ANY (ARRAY['issued'::text, 'voided'::text])) AND (revision >= 2) AND (entry_id IS NOT NULL) AND (issued_on IS NOT NULL) AND (attestation IS NOT NULL) AND (attestation = 'confirmed_account_treatment'::text) AND (((credited_obligation_id IS NULL) AND (obligation_id IS NOT NULL) AND (applied_minor IS NULL) AND (refund_control_account_id IS NULL)) OR ((credited_obligation_id IS NOT NULL) AND (applied_minor IS NOT NULL) AND (applied_minor <= principal_minor) AND ((obligation_id IS NULL) = (applied_minor = principal_minor)) AND ((refund_control_account_id IS NULL) = (applied_minor = principal_minor))))))"}
-- CHECK_APPROVAL {"table":"financial_document_versions","name":"financial_versions_void_refs","expression":"(((state = 'voided'::text) = (void_entry_id IS NOT NULL)) AND ((state = 'voided'::text) = (voided_on IS NOT NULL)) AND ((state = 'voided'::text) = (void_reason IS NOT NULL)) AND ((state = 'voided'::text) = (void_evidence_source IS NOT NULL)) AND ((state <> 'voided'::text) OR ((credited_obligation_id IS NOT NULL) AND (revision >= 3))))"}
