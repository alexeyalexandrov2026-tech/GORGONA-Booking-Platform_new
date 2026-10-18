-- K3a provider provenance in H (ADR-0027; owner decisions 2026-10-17). A finance user confirms
-- a reserved settlement with one observed provider operation: the amount, currency, date and
-- reference come from attested and decided facts (migration 0050), never from the request. A
-- provider payment always has exactly its provenance row; voids and corrections follow the
-- existing human paths and keep it. USD only. One registered clearing account per connection.
-- Migrations 0001-0051 are preserved.

alter table gba.external_payments drop constraint external_payments_attestation_check;
alter table gba.external_payments add constraint external_payments_attestation_check
    check (attestation in ('manual_attestation', 'provider_observed'));

-- The asset account a connection's observed gross money goes to, registered once.
create table gba.provider_clearing_accounts (
    tenant_id uuid not null,
    connection_id uuid not null,
    book_id uuid not null,
    account_id uuid not null,
    created_by uuid not null references gba.users(id),
    created_at timestamptz not null default now(),
    created_transaction xid8 not null default pg_catalog.pg_current_xact_id(),
    primary key (tenant_id, connection_id),
    foreign key (tenant_id, connection_id)
        references gba.provider_receipt_connections(tenant_id, id),
    foreign key (tenant_id, book_id, account_id)
        references gba.ledger_accounts(tenant_id, book_id, id)
);

-- One observed provider operation moves money at most once in the company, whatever happens
-- to the payment later; the success event fixes its amount and date.
create table gba.external_payment_provenance (
    tenant_id uuid not null,
    book_id uuid not null,
    payment_id uuid not null,
    operation_id uuid not null,
    success_event_id uuid not null,
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

create function gba.enforce_provider_clearing_account() returns trigger language plpgsql as $$
begin
    perform gba.lock_ledger(new.tenant_id);
    perform gba.assert_financial_workflow(new.tenant_id);
    if not exists (select 1 from gba.provider_receipt_connections c
        where c.tenant_id = new.tenant_id and c.id = new.connection_id
        and c.book_id = new.book_id and not c.revoked) then
        raise exception using errcode = 'check_violation',
            message = 'a clearing account belongs to an active connection of its book';
    end if;
    if not exists (select 1 from gba.ledger_accounts a
        join gba.ledger_account_versions v on v.tenant_id = a.tenant_id and v.account_id = a.id
        where a.tenant_id = new.tenant_id and a.book_id = new.book_id and a.id = new.account_id
        and a.type = 'asset' and not v.archived
        and v.revision = (select max(x.revision) from gba.ledger_account_versions x
            where x.tenant_id = a.tenant_id and x.account_id = a.id))
        or exists (select 1 from gba.financial_obligations o where o.tenant_id = new.tenant_id
            and o.book_id = new.book_id and o.control_account_id = new.account_id) then
        raise exception using errcode = 'check_violation',
            message = 'a clearing account is an open asset account and never a control account';
    end if;
    return new;
end;
$$;
revoke all on function gba.enforce_provider_clearing_account() from public;

-- The provenance follows its observed payment in the same transaction. It locks the operation,
-- so a decision of another event of it, or a second application, waits for this one.
create function gba.enforce_external_payment_provenance() returns trigger language plpgsql as $$
declare p gba.external_payments%rowtype;
begin
    perform gba.lock_ledger(new.tenant_id);
    select * into p from gba.external_payments x
        where x.tenant_id = new.tenant_id and x.book_id = new.book_id and x.id = new.payment_id;
    if p.id is null or p.attestation <> 'provider_observed' or p.created_by <> new.created_by
        or p.created_transaction <> pg_catalog.pg_current_xact_id() then
        raise exception using errcode = 'check_violation',
            message = 'provider provenance is recorded with its observed payment';
    end if;
    perform 1 from gba.provider_operations o
        where o.tenant_id = new.tenant_id and o.id = new.operation_id for update;
    select d.event_id into new.success_event_id from gba.provider_event_decisions d
        join gba.provider_event_inbox e on e.tenant_id = d.tenant_id and e.id = d.event_id
        where d.tenant_id = new.tenant_id and d.operation_id = new.operation_id
        and d.reason = 'success'
        order by (e.facts->>'created')::bigint, e.id limit 1;
    if new.success_event_id is null then
        raise exception using errcode = 'check_violation',
            message = 'provider provenance needs an observed success';
    end if;
    return new;
end;
$$;
revoke all on function gba.enforce_external_payment_provenance() from public;

-- Every fact of an observed payment, checked once in the transaction that applies it. Later
-- facts never change money; a void or correction is a human attestation of its own.
create function gba.assert_provider_payment(tenant uuid, book uuid, payment uuid)
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
            and (c.revoked or a.book_id <> book))
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
        or exists (select 1 from gba.external_payments m
            where m.tenant_id = tenant and m.book_id = book and m.attestation = 'manual_attestation'
            and m.external_reference
                ~ ('(^|[^A-Za-z0-9_])' || operation.provider_object_id || '($|[^A-Za-z0-9_])')) then
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
            or (select sum(r.amount_minor) from gba.external_payments r
                join gba.external_payment_provenance y on y.tenant_id = r.tenant_id
                    and y.book_id = r.book_id and y.payment_id = r.id
                join gba.provider_operations o on o.tenant_id = y.tenant_id and o.id = y.operation_id
                where r.tenant_id = tenant and r.book_id = book
                and o.connection_id = operation.connection_id and o.kind = 'refund'
                and o.parent_object_id = operation.parent_object_id) > parent.amount_minor then
            raise exception using errcode = 'check_violation',
                message = 'a provider refund follows its applied payment within its amount';
        end if;
    end if;
end;
$$;
revoke all on function gba.assert_provider_payment(uuid, uuid, uuid) from public;
grant execute on function gba.assert_provider_payment(uuid, uuid, uuid) to gba_runtime;

create or replace function gba.check_payment_integrity() returns trigger language plpgsql as $$
declare tenant uuid; book uuid; payment uuid; entry gba.journal_entries%rowtype;
begin
    tenant := new.tenant_id;
    if tg_table_name = 'external_payments' then
        book := new.book_id; payment := new.id;
    elsif tg_table_name in ('external_payment_allocations', 'external_payment_revisions',
        'external_payment_revision_allocations', 'external_payment_provenance') then
        book := new.book_id; payment := new.payment_id;
    else
        if tg_table_name = 'journal_entries' then entry := new;
        else select * into entry from gba.journal_entries e
            where e.tenant_id = tenant and e.id = new.entry_id; end if;
        if entry.source_kind is distinct from 'payment'
            and entry.source_kind is distinct from 'payment_correction' then
            return null;
        end if;
        book := entry.book_id;
        if entry.source_kind = 'payment' then
            select x.id into payment from gba.external_payments x
                where x.tenant_id = tenant and x.book_id = book and x.entry_id = entry.id;
        else
            select x.payment_id into payment from gba.external_payment_revisions x
                where x.tenant_id = tenant and x.book_id = book
                and (x.reversal_entry_id = entry.id or x.entry_id = entry.id);
        end if;
        if payment is null then
            raise exception using errcode = 'check_violation',
                message = 'payment journal cannot be orphaned';
        end if;
    end if;
    perform gba.assert_payment_consistent(tenant, book, payment);
    return null;
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
    provenance gba.external_payment_provenance%rowtype;
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
    -- K3a: an observed payment has exactly its provenance, from the same transaction, and
    -- its facts are checked where it is applied; a later void or correction is a human fact.
    select * into provenance from gba.external_payment_provenance x
        where x.tenant_id = tenant and x.book_id = book and x.payment_id = payment;
    if (p.attestation = 'provider_observed') <> (provenance.payment_id is not null)
        or provenance.created_transaction <> p.created_transaction then
        raise exception using errcode = 'check_violation',
            message = 'a provider payment has exactly its provenance';
    end if;
    if provenance.created_transaction = pg_catalog.pg_current_xact_id() then
        perform gba.assert_provider_payment(tenant, book, payment);
    end if;
end;
$$;

alter table gba.provider_clearing_accounts enable row level security;
alter table gba.provider_clearing_accounts force row level security;
create policy provider_clearing_accounts_tenant_isolation on gba.provider_clearing_accounts
    using (tenant_id=gba.current_tenant_id()) with check (tenant_id=gba.current_tenant_id());
revoke all on gba.provider_clearing_accounts from public;
grant select on gba.provider_clearing_accounts to gba_runtime;
grant insert (tenant_id,connection_id,book_id,account_id,created_by) on gba.provider_clearing_accounts to gba_runtime;
create trigger provider_clearing_accounts_immutable before update or delete on gba.provider_clearing_accounts
    for each row execute function gba.reject_ledger_mutation();
create trigger provider_clearing_accounts_lock before insert on gba.provider_clearing_accounts
    for each row execute function gba.lock_financial_record();
create trigger provider_clearing_accounts_check before insert on gba.provider_clearing_accounts
    for each row execute function gba.enforce_provider_clearing_account();

alter table gba.external_payment_provenance enable row level security;
alter table gba.external_payment_provenance force row level security;
create policy external_payment_provenance_tenant_isolation on gba.external_payment_provenance
    using (tenant_id=gba.current_tenant_id()) with check (tenant_id=gba.current_tenant_id());
revoke all on gba.external_payment_provenance from public;
grant select on gba.external_payment_provenance to gba_runtime;
grant insert (tenant_id,book_id,payment_id,operation_id,created_by) on gba.external_payment_provenance to gba_runtime;
create trigger external_payment_provenance_immutable before update or delete on gba.external_payment_provenance
    for each row execute function gba.reject_ledger_mutation();
create trigger external_payment_provenance_lock before insert on gba.external_payment_provenance
    for each row execute function gba.lock_financial_record();
create trigger external_payment_provenance_require_workflow before insert on gba.external_payment_provenance
    for each row execute function gba.require_financial_workflow();
create trigger external_payment_provenance_check before insert on gba.external_payment_provenance
    for each row execute function gba.enforce_external_payment_provenance();
create constraint trigger external_payment_provenance_consistent after insert on gba.external_payment_provenance
    deferrable initially deferred for each row execute function gba.check_payment_integrity();

-- Company scope: restore independently in disposable drift tests.
create policy provider_clearing_accounts_unrestricted_scope on gba.provider_clearing_accounts as restrictive to gba_runtime
    using (gba.current_location_id() is null) with check (gba.current_location_id() is null);
create policy external_payment_provenance_unrestricted_scope on gba.external_payment_provenance as restrictive to gba_runtime
    using (gba.current_location_id() is null) with check (gba.current_location_id() is null);

-- Approved PostgreSQL 18 CHECK deparse forms; they replace earlier approvals of the
-- same constraint. Readiness never learns them from a target database.
-- CHECK_APPROVAL {"table":"external_payments","name":"external_payments_attestation_check","expression":"(attestation = ANY (ARRAY['manual_attestation'::text, 'provider_observed'::text]))"}
