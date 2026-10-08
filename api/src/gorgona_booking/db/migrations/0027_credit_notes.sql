-- H3 credit notes (ADR-0024 section 7). A credit note is a third kind of the immutable
-- financial document. It names the invoice or manual-accrual obligation it credits and,
-- on every line, the original line it reduces. At issue the unpaid part becomes C of
-- that obligation and the paid part a separate opposite-direction credit_refund
-- obligation: invoice 100, paid 70, credit 50 gives C 30 and a refund obligation of
-- 20. Historical cash and the original principal never change. One balanced G journal
-- of the new origin 'credit' records it. A credit needs no active (reserved or sent)
-- reserve on the credited obligation and never exceeds the uncredited amount of an
-- original line. Payment corrections and credit voids are not introduced here.
-- Migrations 0001-0026 are preserved; replaced functions keep their names.

alter table gba.journal_entries drop constraint journal_entries_source_kind_check;
alter table gba.journal_entries add constraint journal_entries_source_kind_check
    check (source_kind in ('manual', 'opening', 'reversal', 'invoice', 'accrual', 'payment', 'credit'));

alter table gba.financial_documents drop constraint financial_documents_kind_check;
alter table gba.financial_documents add constraint financial_documents_kind_check
    check (kind in ('invoice', 'manual_accrual', 'credit_note'));

alter table gba.financial_obligations drop constraint financial_obligations_source_kind_check;
alter table gba.financial_obligations add constraint financial_obligations_source_kind_check
    check (source_kind in ('invoice', 'manual', 'credit_refund'));

alter table gba.financial_command_receipts
    drop constraint financial_command_receipts_operation_check;
alter table gba.financial_command_receipts add constraint financial_command_receipts_operation_check
    check (operation in ('invoice_draft', 'invoice_issue', 'accrual_draft', 'accrual_issue', 'credit_draft', 'credit_issue'));

alter table gba.financial_command_cancellations
    drop constraint financial_command_cancellations_operation_check;
alter table gba.financial_command_cancellations
    add constraint financial_command_cancellations_operation_check
    check (operation in ('invoice_draft', 'invoice_issue', 'accrual_draft', 'accrual_issue', 'credit_draft', 'credit_issue', 'settlement_prepare', 'settlement_approve', 'settlement_reserve', 'settlement_sent', 'settlement_confirm', 'settlement_release', 'settlement_cancel'));
alter table gba.financial_command_cancellations
    drop constraint financial_command_cancellations_revision_check;
alter table gba.financial_command_cancellations
    add constraint financial_command_cancellations_revision_check
    check (revision >= 1
        and (operation in ('invoice_draft', 'accrual_draft', 'credit_draft', 'settlement_prepare') or revision >= 2)
        and (operation <> 'settlement_prepare' or revision = 1));

-- A credit note names the obligation it credits; at issue it records its unpaid part
-- (C) and, when part of the credit was already paid, the explicitly chosen control
-- account of the refund obligation. Invoices and manual accruals leave all three empty.
alter table gba.financial_document_versions add column credited_obligation_id uuid;
alter table gba.financial_document_versions add column applied_minor bigint
    constraint financial_document_versions_applied_minor_check
    check (applied_minor is null or applied_minor between 0 and 999999999999999999);
alter table gba.financial_document_versions add column refund_control_account_id uuid;
alter table gba.financial_document_versions add constraint financial_versions_credited_fk
    foreign key (tenant_id, book_id, credited_obligation_id)
    references gba.financial_obligations(tenant_id, book_id, id);
alter table gba.financial_document_versions add constraint financial_versions_refund_control_fk
    foreign key (tenant_id, book_id, refund_control_account_id)
    references gba.ledger_accounts(tenant_id, book_id, id);
alter table gba.financial_document_versions drop constraint financial_versions_issued_refs;
alter table gba.financial_document_versions add constraint financial_versions_issued_refs check (
    (state = 'draft' and entry_id is null and obligation_id is null and issued_on is null
        and attestation is null and applied_minor is null and refund_control_account_id is null)
    or (state = 'issued' and revision >= 2 and entry_id is not null and issued_on is not null
        and attestation is not null and attestation = 'confirmed_account_treatment'
        and ((credited_obligation_id is null and obligation_id is not null
                and applied_minor is null and refund_control_account_id is null)
            or (credited_obligation_id is not null and applied_minor is not null
                and applied_minor <= principal_minor
                and (obligation_id is null) = (applied_minor = principal_minor)
                and (refund_control_account_id is null) = (applied_minor = principal_minor))))
);
create index financial_versions_credited on gba.financial_document_versions
    (tenant_id, book_id, credited_obligation_id) where credited_obligation_id is not null;

-- A credit line names the original line it reduces. A counter account other than the
-- original line's needs a reason and may cite the G entry of this book and currency
-- that changed the recognition; the citation is context, never machine proof.
alter table gba.financial_document_lines add column credited_line_id uuid;
alter table gba.financial_document_lines add column reason text
    constraint financial_document_lines_reason_check check (
        reason is null or (length(btrim(reason)) between 1 and 500 and reason !~ '[[:cntrl:]]'));
alter table gba.financial_document_lines add column reference_entry_id uuid;
alter table gba.financial_document_lines add constraint financial_lines_reference_fk
    foreign key (tenant_id, book_id, reference_entry_id)
    references gba.journal_entries(tenant_id, book_id, id);
alter table gba.financial_document_lines add constraint financial_lines_credit_refs check (
    (reference_entry_id is null or reason is not null)
    and (credited_line_id is not null or reason is null));

grant insert (credited_obligation_id, applied_minor, refund_control_account_id)
    on gba.financial_document_versions to gba_runtime;
grant insert (credited_line_id, reason, reference_entry_id)
    on gba.financial_document_lines to gba_runtime;

-- C is the unpaid part of every issued credit note of the obligation.
create or replace function gba.obligation_balance(tenant uuid, book uuid, obligation uuid)
    returns table (principal_minor bigint, paid_minor bigint, credited_minor bigint, reserved_minor bigint)
    language plpgsql as $$
begin
    return query
    select o.principal_minor,
        coalesce((select sum(p.amount_minor) from gba.external_payment_allocations p
            where p.tenant_id = o.tenant_id and p.book_id = o.book_id
            and p.obligation_id = o.id), 0)::bigint,
        coalesce((select sum(v.applied_minor) from gba.financial_document_versions v
            where v.tenant_id = o.tenant_id and v.book_id = o.book_id
            and v.credited_obligation_id = o.id and v.state = 'issued'), 0)::bigint,
        coalesce((select sum(a.amount_minor - coalesce((
                select sum(p.amount_minor) from gba.external_payment_allocations p
                join gba.external_payments e on e.tenant_id = p.tenant_id
                    and e.book_id = p.book_id and e.id = p.payment_id
                where p.tenant_id = a.tenant_id and p.book_id = a.book_id
                and p.obligation_id = a.obligation_id and e.settlement_id = a.settlement_id), 0))
            from gba.settlement_allocations a
            where a.tenant_id = o.tenant_id and a.book_id = o.book_id and a.obligation_id = o.id
            and gba.settlement_phase(a.tenant_id, a.book_id, a.settlement_id)
                in ('reserved', 'sent')), 0)::bigint
    from gba.financial_obligations o
    where o.tenant_id = tenant and o.book_id = book and o.id = obligation;
end;
$$;

-- Only a credit note names the obligation it credits, and it follows that invoice or
-- accrual obligation; a refund account is an open control of the opposite direction
-- that never received external cash.
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
    select d.kind into document_kind from gba.financial_documents d
        where d.tenant_id = new.tenant_id and d.book_id = new.book_id and d.id = new.document_id;
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
        or exists (select 1 from gba.external_payments p where p.tenant_id = new.tenant_id
            and p.book_id = new.book_id and p.cash_account_id = new.refund_control_account_id)) then
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

-- A credit line names a line of the credited document, never more than that line; a
-- reason accompanies exactly another counter account and a cited entry shares the
-- book and currency of the credit.
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

-- A credit journal names its issued credit note of the same transaction; like every
-- H-owned origin it is never reversed by the generic G reversal.
create or replace function gba.enforce_invoice_origin() returns trigger language plpgsql as $$
declare original gba.journal_entries%rowtype;
begin
    perform gba.lock_ledger(new.tenant_id);
    if new.reverses_entry_id is not null then
        select * into original from gba.journal_entries e
            where e.tenant_id = new.tenant_id and e.id = new.reverses_entry_id;
        if original.source_kind in ('invoice', 'accrual', 'payment', 'credit') then
            raise exception using errcode = 'check_violation',
                message = 'H-owned journal correction requires its financial document';
        end if;
    end if;
    if new.source_kind in ('invoice', 'accrual', 'credit') then
        perform pg_catalog.pg_advisory_xact_lock_shared(
            pg_catalog.hashtextextended('gba:business-configuration:' || new.tenant_id::text, 0));
        if not exists (select 1 from gba.business_module_states s
            where s.tenant_id = new.tenant_id and s.module_id = 'finance_documents' and s.enabled) then
            raise exception using errcode = 'GBM01',
                message = 'the finance_documents module is disabled for this business';
        end if;
        if not exists (select 1 from gba.financial_document_versions v
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
    end if;
    return new;
end;
$$;

-- The whole document again at commit. An issued credit note has its exact journal
-- (each line against its counter account, then the unpaid part against the original
-- control and the paid part against the refund control), a refund obligation exactly
-- when part was paid, and leaves the credited obligation within its cap: no active
-- reserve, the unpaid balance credited before anything is refunded, and no original
-- line credited beyond its amount.
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
        if v.state = 'issued' then
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
                        and c.credited_line_id = o.line_id)) then
                    raise exception using errcode = 'check_violation',
                        message = 'a credit exceeds the uncredited amount of a line';
                end if;
            end if;
        end if;
    end loop;
end;
$$;

-- A credit journal and a credit receipt name their credit note like the other kinds.
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
        if entry.source_kind not in ('invoice', 'accrual', 'credit') then return null; end if;
        book := entry.book_id;
        select v.document_id into document from gba.financial_document_versions v
            where v.tenant_id = tenant and v.book_id = book and v.state = 'issued' and v.entry_id = entry.id;
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
                || case v.state when 'issued' then '_issue' else '_draft' end)
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

-- Approved PostgreSQL 18 CHECK deparse forms; they replace earlier approvals of the
-- same constraint. Readiness never learns them from a target database.
-- CHECK_APPROVAL {"table":"journal_entries","name":"journal_entries_source_kind_check","expression":"(source_kind = ANY (ARRAY['manual'::text, 'opening'::text, 'reversal'::text, 'invoice'::text, 'accrual'::text, 'payment'::text, 'credit'::text]))"}
-- CHECK_APPROVAL {"table":"financial_documents","name":"financial_documents_kind_check","expression":"(kind = ANY (ARRAY['invoice'::text, 'manual_accrual'::text, 'credit_note'::text]))"}
-- CHECK_APPROVAL {"table":"financial_obligations","name":"financial_obligations_source_kind_check","expression":"(source_kind = ANY (ARRAY['invoice'::text, 'manual'::text, 'credit_refund'::text]))"}
-- CHECK_APPROVAL {"table":"financial_command_receipts","name":"financial_command_receipts_operation_check","expression":"(operation = ANY (ARRAY['invoice_draft'::text, 'invoice_issue'::text, 'accrual_draft'::text, 'accrual_issue'::text, 'credit_draft'::text, 'credit_issue'::text]))"}
-- CHECK_APPROVAL {"table":"financial_command_cancellations","name":"financial_command_cancellations_operation_check","expression":"(operation = ANY (ARRAY['invoice_draft'::text, 'invoice_issue'::text, 'accrual_draft'::text, 'accrual_issue'::text, 'credit_draft'::text, 'credit_issue'::text, 'settlement_prepare'::text, 'settlement_approve'::text, 'settlement_reserve'::text, 'settlement_sent'::text, 'settlement_confirm'::text, 'settlement_release'::text, 'settlement_cancel'::text]))"}
-- CHECK_APPROVAL {"table":"financial_command_cancellations","name":"financial_command_cancellations_revision_check","expression":"((revision >= 1) AND ((operation = ANY (ARRAY['invoice_draft'::text, 'accrual_draft'::text, 'credit_draft'::text, 'settlement_prepare'::text])) OR (revision >= 2)) AND ((operation <> 'settlement_prepare'::text) OR (revision = 1)))"}
-- CHECK_APPROVAL {"table":"financial_document_versions","name":"financial_document_versions_applied_minor_check","expression":"((applied_minor IS NULL) OR ((applied_minor >= 0) AND (applied_minor <= '999999999999999999'::bigint)))"}
-- CHECK_APPROVAL {"table":"financial_document_versions","name":"financial_versions_issued_refs","expression":"(((state = 'draft'::text) AND (entry_id IS NULL) AND (obligation_id IS NULL) AND (issued_on IS NULL) AND (attestation IS NULL) AND (applied_minor IS NULL) AND (refund_control_account_id IS NULL)) OR ((state = 'issued'::text) AND (revision >= 2) AND (entry_id IS NOT NULL) AND (issued_on IS NOT NULL) AND (attestation IS NOT NULL) AND (attestation = 'confirmed_account_treatment'::text) AND (((credited_obligation_id IS NULL) AND (obligation_id IS NOT NULL) AND (applied_minor IS NULL) AND (refund_control_account_id IS NULL)) OR ((credited_obligation_id IS NOT NULL) AND (applied_minor IS NOT NULL) AND (applied_minor <= principal_minor) AND ((obligation_id IS NULL) = (applied_minor = principal_minor)) AND ((refund_control_account_id IS NULL) = (applied_minor = principal_minor))))))"}
-- CHECK_APPROVAL {"table":"financial_document_lines","name":"financial_document_lines_reason_check","expression":"((reason IS NULL) OR (((length(btrim(reason)) >= 1) AND (length(btrim(reason)) <= 500)) AND (reason !~ '[[:cntrl:]]'::text)))"}
-- CHECK_APPROVAL {"table":"financial_document_lines","name":"financial_lines_credit_refs","expression":"(((reference_entry_id IS NULL) OR (reason IS NOT NULL)) AND ((credited_line_id IS NOT NULL) OR (reason IS NULL)))"}
