-- H1 internal invoices (ADR-0024): insert-only drafts and one atomic accrual.
-- No provider, payment, reserve, credit, tax or FX operation is introduced here.
-- Old G migrations and checksums are preserved. H-owned journals have explicit
-- origins; their complete line set is tied to an issued invoice and obligation.

alter table gba.journal_entries drop constraint journal_entries_source_kind_check;
alter table gba.journal_entries add constraint journal_entries_source_kind_check
    check (source_kind in ('manual', 'opening', 'reversal', 'invoice'));

create table gba.financial_documents (
    tenant_id uuid not null,
    book_id uuid not null,
    id uuid not null,
    created_by uuid not null references gba.users(id),
    created_at timestamptz not null default now(),
    primary key (tenant_id, book_id, id),
    foreign key (tenant_id, book_id) references gba.ledger_books(tenant_id, id)
);

create table gba.financial_document_versions (
    tenant_id uuid not null,
    book_id uuid not null,
    document_id uuid not null,
    revision integer not null constraint financial_document_versions_revision_check check (revision > 0),
    state text not null constraint financial_document_versions_state_check check (state in ('draft', 'issued')),
    direction text not null constraint financial_document_versions_direction_check check (direction in ('receivable', 'payable')),
    counterparty_id uuid not null,
    counterparty_revision integer not null,
    currency text not null references gba.currencies(code),
    invoice_date date not null,
    due_date date constraint financial_document_versions_due_date_check check (due_date is null or due_date >= invoice_date),
    control_account_id uuid not null,
    title text not null constraint financial_document_versions_title_check check (length(btrim(title)) between 1 and 200 and title !~ '[[:cntrl:]]'),
    number text not null constraint financial_document_versions_number_check check (length(btrim(number)) between 1 and 64 and number !~ '[[:cntrl:]]'),
    principal_minor bigint not null constraint financial_document_versions_principal_minor_check check (principal_minor between 1 and 999999999999999999),
    line_count smallint not null constraint financial_document_versions_line_count_check check (line_count between 1 and 199),
    entry_id uuid,
    obligation_id uuid,
    issued_on date,
    attestation text,
    created_by uuid not null references gba.users(id),
    created_at timestamptz not null default now(),
    created_transaction xid8 not null default pg_catalog.pg_current_xact_id(),
    primary key (tenant_id, book_id, document_id, revision),
    constraint financial_versions_document_fk foreign key (tenant_id, book_id, document_id)
        references gba.financial_documents(tenant_id, book_id, id),
    constraint financial_versions_party_fk foreign key (tenant_id, counterparty_id, counterparty_revision)
        references gba.counterparty_versions(tenant_id, counterparty_id, revision),
    constraint financial_versions_control_fk foreign key (tenant_id, book_id, control_account_id)
        references gba.ledger_accounts(tenant_id, book_id, id),
    constraint financial_versions_issued_refs check (
        (state = 'draft' and entry_id is null and obligation_id is null
            and issued_on is null and attestation is null)
        or (state = 'issued' and revision >= 2 and entry_id is not null
            and obligation_id is not null and issued_on is not null
            and attestation is not null and attestation = 'confirmed_account_treatment')
    ),
    constraint financial_versions_entry_fk foreign key (tenant_id, book_id, entry_id)
        references gba.journal_entries(tenant_id, book_id, id) deferrable initially deferred
);

create table gba.financial_document_lines (
    tenant_id uuid not null,
    book_id uuid not null,
    document_id uuid not null,
    revision integer not null,
    line_no smallint not null constraint financial_document_lines_line_no_check check (line_no between 1 and 199),
    line_id uuid not null,
    counter_account_id uuid not null,
    description text not null constraint financial_document_lines_description_check check (
        length(btrim(description)) between 1 and 500 and description !~ '[[:cntrl:]]'),
    amount_minor bigint not null constraint financial_document_lines_amount_minor_check check (amount_minor between 1 and 999999999999999999),
    primary key (tenant_id, book_id, document_id, revision, line_no),
    unique (tenant_id, book_id, document_id, revision, line_id),
    foreign key (tenant_id, book_id, document_id, revision)
        references gba.financial_document_versions(tenant_id, book_id, document_id, revision),
    foreign key (tenant_id, book_id, counter_account_id)
        references gba.ledger_accounts(tenant_id, book_id, id)
);

create table gba.financial_obligations (
    tenant_id uuid not null,
    book_id uuid not null,
    id uuid not null,
    source_kind text not null constraint financial_obligations_source_kind_check check (source_kind = 'invoice'),
    source_id uuid not null,
    source_revision integer not null,
    component text not null constraint financial_obligations_component_check check (component = 'principal'),
    counterparty_id uuid not null,
    counterparty_revision integer not null,
    direction text not null constraint financial_obligations_direction_check check (direction in ('receivable', 'payable')),
    currency text not null references gba.currencies(code),
    control_account_id uuid not null,
    principal_minor bigint not null constraint financial_obligations_principal_minor_check check (principal_minor between 1 and 999999999999999999),
    created_by uuid not null references gba.users(id),
    created_at timestamptz not null default now(),
    created_transaction xid8 not null default pg_catalog.pg_current_xact_id(),
    primary key (tenant_id, book_id, id),
    unique (tenant_id, book_id, source_kind, source_id, component),
    foreign key (tenant_id, book_id, source_id, source_revision)
        references gba.financial_document_versions(tenant_id, book_id, document_id, revision),
    foreign key (tenant_id, counterparty_id, counterparty_revision)
        references gba.counterparty_versions(tenant_id, counterparty_id, revision),
    foreign key (tenant_id, book_id, control_account_id)
        references gba.ledger_accounts(tenant_id, book_id, id)
);
alter table gba.financial_document_versions add constraint financial_versions_obligation_fk
    foreign key (tenant_id, book_id, obligation_id)
    references gba.financial_obligations(tenant_id, book_id, id) deferrable initially deferred;

create table gba.financial_operation_entries (
    tenant_id uuid not null,
    book_id uuid not null,
    document_id uuid not null,
    revision integer not null,
    component text not null constraint financial_operation_entries_component_check check (component = 'principal'),
    entry_id uuid not null,
    obligation_id uuid not null,
    created_transaction xid8 not null default pg_catalog.pg_current_xact_id(),
    primary key (tenant_id, book_id, document_id, revision, component),
    unique (tenant_id, book_id, entry_id),
    unique (tenant_id, book_id, obligation_id),
    foreign key (tenant_id, book_id, document_id, revision)
        references gba.financial_document_versions(tenant_id, book_id, document_id, revision),
    foreign key (tenant_id, book_id, entry_id) references gba.journal_entries(tenant_id, book_id, id),
    foreign key (tenant_id, book_id, obligation_id)
        references gba.financial_obligations(tenant_id, book_id, id)
);

-- Permanent reference-only command outcomes support exact replay after ordinary
-- idempotency receipts expire. Fingerprints are hashes, never financial bodies.
create table gba.financial_command_receipts (
    tenant_id uuid not null,
    actor_key text not null,
    operation text not null constraint financial_command_receipts_operation_check check (operation in ('invoice_draft', 'invoice_issue')),
    idempotency_key text not null constraint financial_command_receipts_idempotency_key_check check (idempotency_key ~ '^[A-Za-z0-9._:-]{8,255}$'),
    request_hash text not null constraint financial_command_receipts_request_hash_check check (request_hash ~ '^[0-9a-f]{64}$'),
    book_id uuid not null,
    document_id uuid not null,
    revision integer not null,
    created_by uuid not null references gba.users(id),
    created_at timestamptz not null default now(),
    constraint financial_command_receipts_actor_check
        check (actor_key = 'user:' || created_by::text),
    primary key (tenant_id, actor_key, operation, idempotency_key),
    foreign key (tenant_id, book_id, document_id, revision)
        references gba.financial_document_versions(tenant_id, book_id, document_id, revision)
);

create table gba.financial_command_cancellations (
    tenant_id uuid not null,
    actor_key text not null,
    operation text not null constraint financial_command_cancellations_operation_check check (operation in ('invoice_draft', 'invoice_issue')),
    idempotency_key text not null constraint financial_command_cancellations_idempotency_key_check check (idempotency_key ~ '^[A-Za-z0-9._:-]{8,255}$'),
    book_id uuid not null,
    document_id uuid not null,
    revision integer not null constraint financial_command_cancellations_revision_check check (revision >= 1 and (operation <> 'invoice_issue' or revision >= 2)),
    cancelled_by uuid not null references gba.users(id),
    cancelled_at timestamptz not null default now(),
    constraint financial_command_cancellations_actor_check
        check (actor_key = 'user:' || cancelled_by::text),
    primary key (tenant_id, actor_key, operation, idempotency_key),
    foreign key (tenant_id, book_id) references gba.ledger_books(tenant_id, id)
);

create function gba.lock_financial_record() returns trigger language plpgsql as $$
begin
    perform gba.lock_ledger(new.tenant_id);
    if tg_table_name = 'financial_command_receipts' then
      if exists (
        select 1 from gba.financial_command_cancellations c where c.tenant_id = new.tenant_id
        and c.actor_key = new.actor_key and c.operation = new.operation
        and c.idempotency_key = new.idempotency_key
    ) then
        raise exception using errcode = 'check_violation', message = 'financial command was cancelled';
      end if;
    elsif tg_table_name = 'financial_command_cancellations' then
      if exists (
        select 1 from gba.financial_command_receipts c where c.tenant_id = new.tenant_id
        and c.actor_key = new.actor_key and c.operation = new.operation
        and c.idempotency_key = new.idempotency_key
    ) then
        raise exception using errcode = 'check_violation', message = 'financial command already committed';
      end if;
    end if;
    return new;
end;
$$;
revoke all on function gba.lock_financial_record() from public;

create function gba.require_financial_workflow() returns trigger language plpgsql as $$
declare required text;
begin
    perform gba.lock_ledger(new.tenant_id);
    perform pg_catalog.pg_advisory_xact_lock_shared(
        pg_catalog.hashtextextended('gba:business-configuration:' || new.tenant_id::text, 0));
    foreach required in array array['finance', 'counterparties', 'finance_documents'] loop
        if not exists (select 1 from gba.business_module_states s
            where s.tenant_id = new.tenant_id and s.module_id = required and s.enabled) then
            raise exception using errcode = 'GBM01',
                message = 'the ' || required || ' module is disabled for this business';
        end if;
    end loop;
    return new;
end;
$$;
revoke all on function gba.require_financial_workflow() from public;

create function gba.enforce_financial_version() returns trigger language plpgsql as $$
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
revoke all on function gba.enforce_financial_version() from public;
create trigger financial_versions_next before insert on gba.financial_document_versions
    for each row execute function gba.enforce_financial_version();

create function gba.enforce_financial_line() returns trigger language plpgsql as $$
declare version gba.financial_document_versions%rowtype;
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
    return new;
end;
$$;
revoke all on function gba.enforce_financial_line() from public;
create trigger financial_lines_check before insert on gba.financial_document_lines
    for each row execute function gba.enforce_financial_line();

create function gba.enforce_invoice_origin() returns trigger language plpgsql as $$
declare original gba.journal_entries%rowtype;
begin
    perform gba.lock_ledger(new.tenant_id);
    if new.reverses_entry_id is not null then
        select * into original from gba.journal_entries e
            where e.tenant_id = new.tenant_id and e.id = new.reverses_entry_id;
        if original.source_kind = 'invoice' then
            raise exception using errcode = 'check_violation',
                message = 'H-owned journal correction requires its financial document';
        end if;
    end if;
    if new.source_kind = 'invoice' then
        perform pg_catalog.pg_advisory_xact_lock_shared(
            pg_catalog.hashtextextended('gba:business-configuration:' || new.tenant_id::text, 0));
        if not exists (select 1 from gba.business_module_states s
            where s.tenant_id = new.tenant_id and s.module_id = 'finance_documents' and s.enabled) then
            raise exception using errcode = 'GBM01',
                message = 'the finance_documents module is disabled for this business';
        end if;
        if not exists (select 1 from gba.financial_document_versions v
            where v.tenant_id = new.tenant_id and v.book_id = new.book_id and v.state = 'issued'
            and v.document_id::text = new.source_id and v.entry_id = new.id
            and v.currency = new.currency and v.issued_on = new.entry_date
            and v.created_by = new.created_by
            and v.created_transaction = pg_catalog.pg_current_xact_id()) then
            raise exception using errcode = 'check_violation', message = 'invoice origin needs its issued version';
        end if;
    end if;
    return new;
end;
$$;
revoke all on function gba.enforce_invoice_origin() from public;
create trigger journal_entries_invoice_origin before insert on gba.journal_entries
    for each row execute function gba.enforce_invoice_origin();

create function gba.assert_invoice_consistent(tenant uuid, book uuid, document uuid)
    returns void language plpgsql as $$
declare
    v gba.financial_document_versions%rowtype;
    obligation gba.financial_obligations%rowtype;
    entry gba.journal_entries%rowtype;
    count_lines integer;
    total numeric;
begin
    if not exists (select 1 from gba.financial_document_versions x
        where x.tenant_id = tenant and x.book_id = book and x.document_id = document) then
        raise exception using errcode = 'check_violation', message = 'financial document needs a saved version';
    end if;
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
                or obligation.source_kind is distinct from 'invoice'
                or obligation.component is distinct from 'principal'
                or row(obligation.source_id,obligation.source_revision,obligation.counterparty_id,
                    obligation.counterparty_revision,obligation.direction,obligation.currency,
                    obligation.control_account_id,obligation.principal_minor,obligation.created_by,
                    obligation.created_transaction)
                is distinct from row(document,v.revision,v.counterparty_id,v.counterparty_revision,
                    v.direction,v.currency,v.control_account_id,v.principal_minor,v.created_by,
                    v.created_transaction)
                or row(entry.source_kind,entry.source_id,entry.currency,entry.entry_date,entry.created_by)
                is distinct from row('invoice'::text,document::text,v.currency,v.issued_on,v.created_by)
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
revoke all on function gba.assert_invoice_consistent(uuid,uuid,uuid) from public;
grant execute on function gba.assert_invoice_consistent(uuid,uuid,uuid) to gba_runtime;

create function gba.check_invoice_integrity() returns trigger language plpgsql as $$
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
        if entry.source_kind <> 'invoice' then return null; end if;
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
            select 1 from gba.financial_document_versions v where v.tenant_id = tenant and v.book_id = book
            and v.document_id = document and v.revision = new.revision and v.created_by = new.created_by
            and (v.state = 'issued') = (new.operation = 'invoice_issue')
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
revoke all on function gba.check_invoice_integrity() from public;

alter table gba.financial_documents enable row level security;
alter table gba.financial_documents force row level security;
create policy financial_documents_tenant_isolation on gba.financial_documents
    using (tenant_id=gba.current_tenant_id()) with check (tenant_id=gba.current_tenant_id());
revoke all on gba.financial_documents from public;
grant select on gba.financial_documents to gba_runtime;
grant insert (tenant_id,book_id,id,created_by) on gba.financial_documents to gba_runtime;
create trigger financial_documents_immutable before update or delete on gba.financial_documents
    for each row execute function gba.reject_ledger_mutation();
create trigger financial_documents_lock before insert on gba.financial_documents
    for each row execute function gba.lock_financial_record();
create trigger financial_documents_require_workflow before insert on gba.financial_documents
    for each row execute function gba.require_financial_workflow();
create constraint trigger financial_documents_consistent after insert on gba.financial_documents
    deferrable initially deferred for each row execute function gba.check_invoice_integrity();

alter table gba.financial_document_versions enable row level security;
alter table gba.financial_document_versions force row level security;
create policy financial_document_versions_tenant_isolation on gba.financial_document_versions
    using (tenant_id=gba.current_tenant_id()) with check (tenant_id=gba.current_tenant_id());
revoke all on gba.financial_document_versions from public;
grant select on gba.financial_document_versions to gba_runtime;
grant insert (tenant_id,book_id,document_id,revision,state,direction,counterparty_id,counterparty_revision,currency,invoice_date,due_date,control_account_id,title,number,principal_minor,line_count,entry_id,obligation_id,issued_on,attestation,created_by) on gba.financial_document_versions to gba_runtime;
create trigger financial_document_versions_immutable before update or delete on gba.financial_document_versions
    for each row execute function gba.reject_ledger_mutation();
create trigger financial_document_versions_lock before insert on gba.financial_document_versions
    for each row execute function gba.lock_financial_record();
create trigger financial_document_versions_require_workflow before insert on gba.financial_document_versions
    for each row execute function gba.require_financial_workflow();
create constraint trigger financial_document_versions_consistent after insert on gba.financial_document_versions
    deferrable initially deferred for each row execute function gba.check_invoice_integrity();

alter table gba.financial_document_lines enable row level security;
alter table gba.financial_document_lines force row level security;
create policy financial_document_lines_tenant_isolation on gba.financial_document_lines
    using (tenant_id=gba.current_tenant_id()) with check (tenant_id=gba.current_tenant_id());
revoke all on gba.financial_document_lines from public;
grant select on gba.financial_document_lines to gba_runtime;
grant insert (tenant_id,book_id,document_id,revision,line_no,line_id,counter_account_id,description,amount_minor) on gba.financial_document_lines to gba_runtime;
create trigger financial_document_lines_immutable before update or delete on gba.financial_document_lines
    for each row execute function gba.reject_ledger_mutation();
create trigger financial_document_lines_lock before insert on gba.financial_document_lines
    for each row execute function gba.lock_financial_record();
create trigger financial_document_lines_require_workflow before insert on gba.financial_document_lines
    for each row execute function gba.require_financial_workflow();
create constraint trigger financial_document_lines_consistent after insert on gba.financial_document_lines
    deferrable initially deferred for each row execute function gba.check_invoice_integrity();

alter table gba.financial_obligations enable row level security;
alter table gba.financial_obligations force row level security;
create policy financial_obligations_tenant_isolation on gba.financial_obligations
    using (tenant_id=gba.current_tenant_id()) with check (tenant_id=gba.current_tenant_id());
revoke all on gba.financial_obligations from public;
grant select on gba.financial_obligations to gba_runtime;
grant insert (tenant_id,book_id,id,source_kind,source_id,source_revision,component,counterparty_id,counterparty_revision,direction,currency,control_account_id,principal_minor,created_by) on gba.financial_obligations to gba_runtime;
create trigger financial_obligations_immutable before update or delete on gba.financial_obligations
    for each row execute function gba.reject_ledger_mutation();
create trigger financial_obligations_lock before insert on gba.financial_obligations
    for each row execute function gba.lock_financial_record();
create trigger financial_obligations_require_workflow before insert on gba.financial_obligations
    for each row execute function gba.require_financial_workflow();
create constraint trigger financial_obligations_consistent after insert on gba.financial_obligations
    deferrable initially deferred for each row execute function gba.check_invoice_integrity();

alter table gba.financial_operation_entries enable row level security;
alter table gba.financial_operation_entries force row level security;
create policy financial_operation_entries_tenant_isolation on gba.financial_operation_entries
    using (tenant_id=gba.current_tenant_id()) with check (tenant_id=gba.current_tenant_id());
revoke all on gba.financial_operation_entries from public;
grant select on gba.financial_operation_entries to gba_runtime;
grant insert (tenant_id,book_id,document_id,revision,component,entry_id,obligation_id) on gba.financial_operation_entries to gba_runtime;
create trigger financial_operation_entries_immutable before update or delete on gba.financial_operation_entries
    for each row execute function gba.reject_ledger_mutation();
create trigger financial_operation_entries_lock before insert on gba.financial_operation_entries
    for each row execute function gba.lock_financial_record();
create trigger financial_operation_entries_require_workflow before insert on gba.financial_operation_entries
    for each row execute function gba.require_financial_workflow();
create constraint trigger financial_operation_entries_consistent after insert on gba.financial_operation_entries
    deferrable initially deferred for each row execute function gba.check_invoice_integrity();

alter table gba.financial_command_receipts enable row level security;
alter table gba.financial_command_receipts force row level security;
create policy financial_command_receipts_tenant_isolation on gba.financial_command_receipts
    using (tenant_id=gba.current_tenant_id()) with check (tenant_id=gba.current_tenant_id());
revoke all on gba.financial_command_receipts from public;
grant select on gba.financial_command_receipts to gba_runtime;
grant insert (tenant_id,actor_key,operation,idempotency_key,request_hash,book_id,document_id,revision,created_by) on gba.financial_command_receipts to gba_runtime;
create trigger financial_command_receipts_immutable before update or delete on gba.financial_command_receipts
    for each row execute function gba.reject_ledger_mutation();
create trigger financial_command_receipts_lock before insert on gba.financial_command_receipts
    for each row execute function gba.lock_financial_record();
create constraint trigger financial_command_receipts_consistent after insert on gba.financial_command_receipts
    deferrable initially deferred for each row execute function gba.check_invoice_integrity();

alter table gba.financial_command_cancellations enable row level security;
alter table gba.financial_command_cancellations force row level security;
create policy financial_command_cancellations_tenant_isolation on gba.financial_command_cancellations
    using (tenant_id=gba.current_tenant_id()) with check (tenant_id=gba.current_tenant_id());
revoke all on gba.financial_command_cancellations from public;
grant select on gba.financial_command_cancellations to gba_runtime;
grant insert (tenant_id,actor_key,operation,idempotency_key,book_id,document_id,revision,cancelled_by) on gba.financial_command_cancellations to gba_runtime;
create trigger financial_command_cancellations_immutable before update or delete on gba.financial_command_cancellations
    for each row execute function gba.reject_ledger_mutation();
create trigger financial_command_cancellations_lock before insert on gba.financial_command_cancellations
    for each row execute function gba.lock_financial_record();

create constraint trigger journal_entries_invoice_consistent after insert on gba.journal_entries
    deferrable initially deferred for each row execute function gba.check_invoice_integrity();
create constraint trigger journal_lines_invoice_consistent after insert on gba.journal_lines
    deferrable initially deferred for each row execute function gba.check_invoice_integrity();


-- Invoice branch scope: restore independently in disposable drift tests.
create policy financial_documents_unrestricted_scope on gba.financial_documents as restrictive to gba_runtime
    using (gba.current_location_id() is null) with check (gba.current_location_id() is null);
create policy financial_document_versions_unrestricted_scope on gba.financial_document_versions as restrictive to gba_runtime
    using (gba.current_location_id() is null) with check (gba.current_location_id() is null);
create policy financial_document_lines_unrestricted_scope on gba.financial_document_lines as restrictive to gba_runtime
    using (gba.current_location_id() is null) with check (gba.current_location_id() is null);
create policy financial_obligations_unrestricted_scope on gba.financial_obligations as restrictive to gba_runtime
    using (gba.current_location_id() is null) with check (gba.current_location_id() is null);
create policy financial_operation_entries_unrestricted_scope on gba.financial_operation_entries as restrictive to gba_runtime
    using (gba.current_location_id() is null) with check (gba.current_location_id() is null);
create policy financial_command_receipts_unrestricted_scope on gba.financial_command_receipts as restrictive to gba_runtime
    using (gba.current_location_id() is null) with check (gba.current_location_id() is null);
create policy financial_command_cancellations_unrestricted_scope on gba.financial_command_cancellations as restrictive to gba_runtime
    using (gba.current_location_id() is null) with check (gba.current_location_id() is null);

-- Approved PostgreSQL 18 CHECK deparse forms. These repository-owned predicates
-- preserve literal contents; readiness never adopts definitions from a target DB.
-- CHECK_APPROVAL {"table":"financial_document_versions","name":"financial_document_versions_revision_check","expression":"(revision > 0)"}
-- CHECK_APPROVAL {"table":"financial_document_versions","name":"financial_document_versions_state_check","expression":"(state = ANY (ARRAY['draft'::text, 'issued'::text]))"}
-- CHECK_APPROVAL {"table":"financial_document_versions","name":"financial_document_versions_direction_check","expression":"(direction = ANY (ARRAY['receivable'::text, 'payable'::text]))"}
-- CHECK_APPROVAL {"table":"financial_document_versions","name":"financial_document_versions_due_date_check","expression":"((due_date IS NULL) OR (due_date >= invoice_date))"}
-- CHECK_APPROVAL {"table":"financial_document_versions","name":"financial_document_versions_title_check","expression":"(((length(btrim(title)) >= 1) AND (length(btrim(title)) <= 200)) AND (title !~ '[[:cntrl:]]'::text))"}
-- CHECK_APPROVAL {"table":"financial_document_versions","name":"financial_document_versions_number_check","expression":"(((length(btrim(number)) >= 1) AND (length(btrim(number)) <= 64)) AND (number !~ '[[:cntrl:]]'::text))"}
-- CHECK_APPROVAL {"table":"financial_document_versions","name":"financial_document_versions_principal_minor_check","expression":"((principal_minor >= 1) AND (principal_minor <= '999999999999999999'::bigint))"}
-- CHECK_APPROVAL {"table":"financial_document_versions","name":"financial_document_versions_line_count_check","expression":"((line_count >= 1) AND (line_count <= 199))"}
-- CHECK_APPROVAL {"table":"financial_document_lines","name":"financial_document_lines_line_no_check","expression":"((line_no >= 1) AND (line_no <= 199))"}
-- CHECK_APPROVAL {"table":"financial_document_lines","name":"financial_document_lines_description_check","expression":"(((length(btrim(description)) >= 1) AND (length(btrim(description)) <= 500)) AND (description !~ '[[:cntrl:]]'::text))"}
-- CHECK_APPROVAL {"table":"financial_document_lines","name":"financial_document_lines_amount_minor_check","expression":"((amount_minor >= 1) AND (amount_minor <= '999999999999999999'::bigint))"}
-- CHECK_APPROVAL {"table":"financial_obligations","name":"financial_obligations_source_kind_check","expression":"(source_kind = 'invoice'::text)"}
-- CHECK_APPROVAL {"table":"financial_obligations","name":"financial_obligations_component_check","expression":"(component = 'principal'::text)"}
-- CHECK_APPROVAL {"table":"financial_obligations","name":"financial_obligations_direction_check","expression":"(direction = ANY (ARRAY['receivable'::text, 'payable'::text]))"}
-- CHECK_APPROVAL {"table":"financial_obligations","name":"financial_obligations_principal_minor_check","expression":"((principal_minor >= 1) AND (principal_minor <= '999999999999999999'::bigint))"}
-- CHECK_APPROVAL {"table":"financial_operation_entries","name":"financial_operation_entries_component_check","expression":"(component = 'principal'::text)"}
-- CHECK_APPROVAL {"table":"financial_command_receipts","name":"financial_command_receipts_operation_check","expression":"(operation = ANY (ARRAY['invoice_draft'::text, 'invoice_issue'::text]))"}
-- CHECK_APPROVAL {"table":"financial_command_receipts","name":"financial_command_receipts_idempotency_key_check","expression":"(idempotency_key ~ '^[A-Za-z0-9._:-]{8,255}$'::text)"}
-- CHECK_APPROVAL {"table":"financial_command_receipts","name":"financial_command_receipts_request_hash_check","expression":"(request_hash ~ '^[0-9a-f]{64}$'::text)"}
-- CHECK_APPROVAL {"table":"financial_command_cancellations","name":"financial_command_cancellations_operation_check","expression":"(operation = ANY (ARRAY['invoice_draft'::text, 'invoice_issue'::text]))"}
-- CHECK_APPROVAL {"table":"financial_command_cancellations","name":"financial_command_cancellations_idempotency_key_check","expression":"(idempotency_key ~ '^[A-Za-z0-9._:-]{8,255}$'::text)"}
-- CHECK_APPROVAL {"table":"financial_command_cancellations","name":"financial_command_cancellations_revision_check","expression":"((revision >= 1) AND ((operation <> 'invoice_issue'::text) OR (revision >= 2)))"}
-- CHECK_APPROVAL {"table":"financial_document_versions","name":"financial_versions_issued_refs","expression":"(((state = 'draft'::text) AND (entry_id IS NULL) AND (obligation_id IS NULL) AND (issued_on IS NULL) AND (attestation IS NULL)) OR ((state = 'issued'::text) AND (revision >= 2) AND (entry_id IS NOT NULL) AND (obligation_id IS NOT NULL) AND (issued_on IS NOT NULL) AND (attestation IS NOT NULL) AND (attestation = 'confirmed_account_treatment'::text)))"}
-- CHECK_APPROVAL {"table":"financial_command_receipts","name":"financial_command_receipts_actor_check","expression":"(actor_key = ('user:'::text || (created_by)::text))"}
-- CHECK_APPROVAL {"table":"financial_command_cancellations","name":"financial_command_cancellations_actor_check","expression":"(actor_key = ('user:'::text || (cancelled_by)::text))"}
