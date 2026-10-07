-- H2 manual accruals (ADR-0024): a second kind of the immutable financial document.
-- A manual obligation is one new accrual with explicit accounts and its own balanced
-- G journal. An existing manual or opening entry is never linked or accrued again.
-- No reserve, payment, credit, tax or FX operation is introduced here. Migrations
-- 0001-0021 and their checksums are preserved; replaced functions keep their names.

alter table gba.journal_entries drop constraint journal_entries_source_kind_check;
alter table gba.journal_entries add constraint journal_entries_source_kind_check
    check (source_kind in ('manual', 'opening', 'reversal', 'invoice', 'accrual'));

-- The kind belongs to the insert-only anchor, so it cannot change between revisions.
alter table gba.financial_documents add column kind text not null default 'invoice'
    constraint financial_documents_kind_check check (kind in ('invoice', 'manual_accrual'));
grant insert (kind) on gba.financial_documents to gba_runtime;

alter table gba.financial_obligations drop constraint financial_obligations_source_kind_check;
alter table gba.financial_obligations add constraint financial_obligations_source_kind_check
    check (source_kind in ('invoice', 'manual'));

alter table gba.financial_command_receipts
    drop constraint financial_command_receipts_operation_check;
alter table gba.financial_command_receipts add constraint financial_command_receipts_operation_check
    check (operation in ('invoice_draft', 'invoice_issue', 'accrual_draft', 'accrual_issue'));

alter table gba.financial_command_cancellations
    drop constraint financial_command_cancellations_operation_check;
alter table gba.financial_command_cancellations
    add constraint financial_command_cancellations_operation_check
    check (operation in ('invoice_draft', 'invoice_issue', 'accrual_draft', 'accrual_issue'));
alter table gba.financial_command_cancellations
    drop constraint financial_command_cancellations_revision_check;
alter table gba.financial_command_cancellations
    add constraint financial_command_cancellations_revision_check
    check (revision >= 1 and (operation not in ('invoice_issue', 'accrual_issue') or revision >= 2));

-- An H-owned journal names the issued version of its own document kind, written in
-- the same transaction. Generic G reversal refuses every H-owned origin.
create or replace function gba.enforce_invoice_origin() returns trigger language plpgsql as $$
declare original gba.journal_entries%rowtype;
begin
    perform gba.lock_ledger(new.tenant_id);
    if new.reverses_entry_id is not null then
        select * into original from gba.journal_entries e
            where e.tenant_id = new.tenant_id and e.id = new.reverses_entry_id;
        if original.source_kind in ('invoice', 'accrual') then
            raise exception using errcode = 'check_violation',
                message = 'H-owned journal correction requires its financial document';
        end if;
    end if;
    if new.source_kind in ('invoice', 'accrual') then
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
            and d.kind = case new.source_kind when 'invoice' then 'invoice' else 'manual_accrual' end
            and v.currency = new.currency and v.issued_on = new.entry_date
            and v.created_by = new.created_by
            and v.created_transaction = pg_catalog.pg_current_xact_id()) then
            raise exception using errcode = 'check_violation',
                message = 'financial journal origin needs its issued version';
        end if;
    end if;
    return new;
end;
$$;

create or replace function gba.assert_invoice_consistent(tenant uuid, book uuid, document uuid)
    returns void language plpgsql as $$
declare
    v gba.financial_document_versions%rowtype;
    obligation gba.financial_obligations%rowtype;
    entry gba.journal_entries%rowtype;
    count_lines integer;
    total numeric;
    document_kind text;
    obligation_source text;
    journal_source text;
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
                (select line_no,line_id,counter_account_id,description,amount_minor
                    from gba.financial_document_lines l where l.tenant_id = tenant and l.book_id = book
                    and l.document_id = document and l.revision = v.revision
                 except all
                 select line_no,line_id,counter_account_id,description,amount_minor
                    from gba.financial_document_lines l where l.tenant_id = tenant and l.book_id = book
                    and l.document_id = document and l.revision = v.revision - 1)
                union all
                (select line_no,line_id,counter_account_id,description,amount_minor
                    from gba.financial_document_lines l where l.tenant_id = tenant and l.book_id = book
                    and l.document_id = document and l.revision = v.revision - 1
                 except all
                 select line_no,line_id,counter_account_id,description,amount_minor
                    from gba.financial_document_lines l where l.tenant_id = tenant and l.book_id = book
                    and l.document_id = document and l.revision = v.revision)
            ) then
                raise exception using errcode = 'check_violation', message = 'issued lines preserve the draft';
            end if;
            select * into obligation from gba.financial_obligations o where o.tenant_id = tenant
                and o.book_id = book and o.id = v.obligation_id;
            select * into entry from gba.journal_entries e where e.tenant_id = tenant
                and e.book_id = book and e.id = v.entry_id;
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
        end if;
    end loop;
end;
$$;

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
        if entry.source_kind not in ('invoice', 'accrual') then return null; end if;
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
            and new.operation = (case d.kind when 'invoice' then 'invoice' else 'accrual' end
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

-- Approved PostgreSQL 18 CHECK deparse forms; a later migration's approval of the
-- same constraint replaces the earlier one. Readiness never learns them from a DB.
-- CHECK_APPROVAL {"table":"journal_entries","name":"journal_entries_source_kind_check","expression":"(source_kind = ANY (ARRAY['manual'::text, 'opening'::text, 'reversal'::text, 'invoice'::text, 'accrual'::text]))"}
-- CHECK_APPROVAL {"table":"financial_documents","name":"financial_documents_kind_check","expression":"(kind = ANY (ARRAY['invoice'::text, 'manual_accrual'::text]))"}
-- CHECK_APPROVAL {"table":"financial_obligations","name":"financial_obligations_source_kind_check","expression":"(source_kind = ANY (ARRAY['invoice'::text, 'manual'::text]))"}
-- CHECK_APPROVAL {"table":"financial_command_receipts","name":"financial_command_receipts_operation_check","expression":"(operation = ANY (ARRAY['invoice_draft'::text, 'invoice_issue'::text, 'accrual_draft'::text, 'accrual_issue'::text]))"}
-- CHECK_APPROVAL {"table":"financial_command_cancellations","name":"financial_command_cancellations_operation_check","expression":"(operation = ANY (ARRAY['invoice_draft'::text, 'invoice_issue'::text, 'accrual_draft'::text, 'accrual_issue'::text]))"}
-- CHECK_APPROVAL {"table":"financial_command_cancellations","name":"financial_command_cancellations_revision_check","expression":"((revision >= 1) AND ((operation <> ALL (ARRAY['invoice_issue'::text, 'accrual_issue'::text])) OR (revision >= 2)))"}
