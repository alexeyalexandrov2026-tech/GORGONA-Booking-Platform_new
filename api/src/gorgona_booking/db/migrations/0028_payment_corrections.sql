-- H3 payment corrections (ADR-0024 section 7). A confirmed external payment is never
-- edited: a void or a correction is a new revision of the same payment, recorded by a
-- new settlement event. Its external identity (book, direction, source account alias,
-- external reference) stays bound to that payment forever; neither state frees it.
-- One transaction reverses the journal of the version it replaces line by line, which
-- returns those allocations to the same reserve, and for a correction confirms the
-- replacement allocations within that reserve with their own journal. P and R are read
-- from the latest (effective) revision of every payment, never from every historical
-- fact. A payment touching an issued credit, a refund obligation or another settlement
-- whose sent outcome is unknown needs a separate reconciliation and is refused; so is a
-- payment of a settlement whose own sent outcome is still unresolved. Credit voids are
-- not introduced here. Migrations 0001-0027 are preserved; replaced functions keep their
-- names.

alter table gba.journal_entries drop constraint journal_entries_source_kind_check;
alter table gba.journal_entries add constraint journal_entries_source_kind_check
    check (source_kind in ('manual', 'opening', 'reversal', 'invoice', 'accrual', 'payment', 'credit', 'payment_correction'));

alter table gba.settlement_events drop constraint settlement_events_kind_check;
alter table gba.settlement_events add constraint settlement_events_kind_check
    check (kind in ('prepared', 'approved', 'reserved', 'sent', 'confirmed', 'released', 'cancelled', 'payment_voided', 'payment_corrected'));

alter table gba.settlement_command_receipts
    drop constraint settlement_command_receipts_operation_check;
alter table gba.settlement_command_receipts
    add constraint settlement_command_receipts_operation_check
    check (operation in ('settlement_prepare', 'settlement_approve', 'settlement_reserve', 'settlement_sent', 'settlement_confirm', 'settlement_release', 'settlement_cancel', 'settlement_payment_void', 'settlement_payment_correct'));

alter table gba.financial_command_cancellations
    drop constraint financial_command_cancellations_operation_check;
alter table gba.financial_command_cancellations
    add constraint financial_command_cancellations_operation_check
    check (operation in ('invoice_draft', 'invoice_issue', 'accrual_draft', 'accrual_issue', 'credit_draft', 'credit_issue', 'settlement_prepare', 'settlement_approve', 'settlement_reserve', 'settlement_sent', 'settlement_confirm', 'settlement_release', 'settlement_cancel', 'settlement_payment_void', 'settlement_payment_correct'));

-- Revision 1 of a payment is its external_payments row. Every later revision names the
-- settlement event that recorded it, the attested reason and evidence and the journal
-- that reverses the replaced version; a correction also carries its replacement facts
-- and journal. A void is final.
create table gba.external_payment_revisions (
    tenant_id uuid not null,
    book_id uuid not null,
    payment_id uuid not null,
    revision integer not null constraint external_payment_revisions_revision_check check (revision between 2 and 1000),
    settlement_id uuid not null,
    sequence integer not null,
    kind text not null constraint external_payment_revisions_kind_check check (kind in ('voided', 'corrected')),
    amount_minor bigint constraint external_payment_revisions_amount_minor_check check (
        amount_minor is null or amount_minor between 1 and 999999999999999999),
    actual_external_date date,
    cash_account_id uuid,
    entry_date date not null,
    attestation text not null constraint external_payment_revisions_attestation_check check (attestation = 'attested_erroneous_confirmation'),
    reason text not null constraint external_payment_revisions_reason_check check (
        length(btrim(reason)) between 1 and 500 and reason !~ '[[:cntrl:]]'),
    evidence_source text not null constraint external_payment_revisions_evidence_source_check check (
        length(btrim(evidence_source)) between 1 and 200 and evidence_source !~ '[[:cntrl:]]'),
    reversal_entry_id uuid not null,
    entry_id uuid,
    created_by uuid not null references gba.users(id),
    created_at timestamptz not null default now(),
    created_transaction xid8 not null default pg_catalog.pg_current_xact_id(),
    primary key (tenant_id, book_id, payment_id, revision),
    unique (tenant_id, book_id, settlement_id, sequence),
    unique (tenant_id, book_id, reversal_entry_id),
    unique (tenant_id, book_id, entry_id),
    constraint external_payment_revisions_kind_refs check (
        (kind = 'voided' and amount_minor is null and actual_external_date is null
            and cash_account_id is null and entry_id is null)
        or (kind = 'corrected' and amount_minor is not null and actual_external_date is not null
            and cash_account_id is not null and entry_id is not null)),
    foreign key (tenant_id, book_id, payment_id)
        references gba.external_payments(tenant_id, book_id, id),
    foreign key (tenant_id, book_id, settlement_id, sequence)
        references gba.settlement_events(tenant_id, book_id, settlement_id, sequence),
    foreign key (tenant_id, book_id, cash_account_id)
        references gba.ledger_accounts(tenant_id, book_id, id),
    constraint external_payment_revisions_reversal_fk foreign key (tenant_id, book_id, reversal_entry_id)
        references gba.journal_entries(tenant_id, book_id, id) deferrable initially deferred,
    constraint external_payment_revisions_entry_fk foreign key (tenant_id, book_id, entry_id)
        references gba.journal_entries(tenant_id, book_id, id) deferrable initially deferred
);

create table gba.external_payment_revision_allocations (
    tenant_id uuid not null,
    book_id uuid not null,
    payment_id uuid not null,
    revision integer not null,
    line_no smallint not null constraint external_payment_revision_allocations_line_no_check check (line_no between 1 and 50),
    obligation_id uuid not null,
    amount_minor bigint not null constraint external_payment_revision_allocations_amount_minor_check check (amount_minor between 1 and 999999999999999999),
    created_transaction xid8 not null default pg_catalog.pg_current_xact_id(),
    primary key (tenant_id, book_id, payment_id, revision, line_no),
    unique (tenant_id, book_id, payment_id, revision, obligation_id),
    foreign key (tenant_id, book_id, payment_id, revision)
        references gba.external_payment_revisions(tenant_id, book_id, payment_id, revision),
    foreign key (tenant_id, book_id, obligation_id)
        references gba.financial_obligations(tenant_id, book_id, id)
);

-- The effective allocations: the latest revision of a payment replaces every earlier
-- one and a void leaves none. A null obligation or settlement means any.
create function gba.effective_payment_allocations(tenant uuid, book uuid, obligation uuid, settlement uuid)
    returns table (payment_id uuid, settlement_id uuid, obligation_id uuid, amount_minor bigint)
    language plpgsql as $$
begin
    return query
    select a.payment_id, p.settlement_id, a.obligation_id, a.amount_minor
        from gba.external_payment_allocations a
        join gba.external_payments p on p.tenant_id = a.tenant_id and p.book_id = a.book_id
            and p.id = a.payment_id
        where a.tenant_id = tenant and a.book_id = book
        and (obligation is null or a.obligation_id = obligation)
        and (settlement is null or p.settlement_id = settlement)
        and not exists (select 1 from gba.external_payment_revisions r
            where r.tenant_id = a.tenant_id and r.book_id = a.book_id and r.payment_id = a.payment_id)
    union all
    select a.payment_id, r.settlement_id, a.obligation_id, a.amount_minor
        from gba.external_payment_revision_allocations a
        join gba.external_payment_revisions r on r.tenant_id = a.tenant_id
            and r.book_id = a.book_id and r.payment_id = a.payment_id and r.revision = a.revision
        where a.tenant_id = tenant and a.book_id = book
        and (obligation is null or a.obligation_id = obligation)
        and (settlement is null or r.settlement_id = settlement)
        and a.revision = (select max(x.revision) from gba.external_payment_revisions x
            where x.tenant_id = a.tenant_id and x.book_id = a.book_id and x.payment_id = a.payment_id);
end;
$$;
revoke all on function gba.effective_payment_allocations(uuid, uuid, uuid, uuid) from public;
grant execute on function gba.effective_payment_allocations(uuid, uuid, uuid, uuid) to gba_runtime;

-- An account that ever received or paid external cash, in any payment revision.
create function gba.cash_account_used(tenant uuid, book uuid, account uuid) returns boolean
    language plpgsql as $$
begin
    return exists (select 1 from gba.external_payments p where p.tenant_id = tenant
            and p.book_id = book and p.cash_account_id = account)
        or exists (select 1 from gba.external_payment_revisions r where r.tenant_id = tenant
            and r.book_id = book and r.cash_account_id = account);
end;
$$;
revoke all on function gba.cash_account_used(uuid, uuid, uuid) from public;
grant execute on function gba.cash_account_used(uuid, uuid, uuid) to gba_runtime;

-- P is the effective confirmed money; R is what each held document still reserves after
-- its own effective confirmations.
create or replace function gba.obligation_balance(tenant uuid, book uuid, obligation uuid)
    returns table (principal_minor bigint, paid_minor bigint, credited_minor bigint, reserved_minor bigint)
    language plpgsql as $$
begin
    return query
    select o.principal_minor,
        coalesce((select sum(e.amount_minor)
            from gba.effective_payment_allocations(o.tenant_id, o.book_id, o.id, null::uuid) e), 0)::bigint,
        coalesce((select sum(v.applied_minor) from gba.financial_document_versions v
            where v.tenant_id = o.tenant_id and v.book_id = o.book_id
            and v.credited_obligation_id = o.id and v.state = 'issued'), 0)::bigint,
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

-- A payment of a held settlement is voided or corrected, and of a released one only
-- voided. A fully confirmed settlement stays final for every other fact, and a payment of
-- a sent settlement whose remainder is still unknown waits for that outcome.
create or replace function gba.enforce_settlement_event() returns trigger language plpgsql as $$
declare
    document gba.settlement_documents%rowtype;
    previous integer;
    phase text;
    planned numeric;
    settled numeric;
begin
    perform gba.lock_ledger(new.tenant_id);
    select * into document from gba.settlement_documents d
        where d.tenant_id = new.tenant_id and d.book_id = new.book_id and d.id = new.settlement_id;
    if document.id is null then
        raise exception using errcode = 'check_violation', message = 'settlement event needs its document';
    end if;
    select coalesce(max(e.sequence), 0) into previous from gba.settlement_events e
        where e.tenant_id = new.tenant_id and e.book_id = new.book_id
        and e.settlement_id = new.settlement_id;
    if new.sequence <> previous + 1 then
        raise exception using errcode = 'check_violation', message = 'settlement events are contiguous';
    end if;
    phase := gba.settlement_phase(new.tenant_id, new.book_id, new.settlement_id);
    if not coalesce(
        (new.kind = 'prepared' and phase is null and document.created_by = new.created_by
            and document.created_transaction = pg_catalog.pg_current_xact_id())
        or (new.kind = 'approved' and phase = 'prepared')
        or (new.kind = 'reserved' and phase = 'approved')
        or (new.kind = 'sent' and phase = 'reserved')
        or (new.kind = 'confirmed' and phase in ('reserved', 'sent'))
        or (new.kind = 'released' and phase = 'reserved' and new.resolution is null)
        or (new.kind = 'released' and phase = 'sent' and new.resolution = 'attested_no_payment')
        or (new.kind = 'cancelled' and phase in ('prepared', 'approved'))
        or (new.kind = 'payment_voided' and phase in ('reserved', 'sent', 'released'))
        or (new.kind = 'payment_corrected' and phase in ('reserved', 'sent')), false) then
        raise exception using errcode = 'check_violation',
            message = 'settlement event does not follow its state';
    end if;
    select coalesce(sum(a.amount_minor), 0) into planned from gba.settlement_allocations a
        where a.tenant_id = new.tenant_id and a.book_id = new.book_id
        and a.settlement_id = new.settlement_id;
    select coalesce(sum(e.amount_minor), 0) into settled
        from gba.effective_payment_allocations(new.tenant_id, new.book_id, null::uuid,
            new.settlement_id) e;
    if new.kind not in ('payment_voided', 'payment_corrected')
        and phase in ('reserved', 'sent') and planned = settled then
        raise exception using errcode = 'check_violation',
            message = 'a fully confirmed settlement is final';
    end if;
    if new.kind in ('payment_voided', 'payment_corrected') and phase = 'sent' and settled < planned then
        raise exception using errcode = 'check_violation',
            message = 'resolve the sent outcome before correcting a payment';
    end if;
    if not (new.kind = 'cancelled' or (new.kind = 'released' and new.resolution is null)) then
        perform gba.assert_financial_workflow(new.tenant_id);
    end if;
    return new;
end;
$$;

-- Every confirmed, voided or corrected fact has its payment record, no line confirms
-- more than it reserved (effective allocations) and every touched obligation keeps
-- P + C + R <= A.
create or replace function gba.assert_settlement_consistent(tenant uuid, book uuid, settlement uuid)
    returns void language plpgsql as $$
declare
    document gba.settlement_documents%rowtype;
    line record;
    balance record;
begin
    select * into document from gba.settlement_documents d
        where d.tenant_id = tenant and d.book_id = book and d.id = settlement;
    if document.id is null or not exists (select 1 from gba.settlement_events e
        where e.tenant_id = tenant and e.book_id = book and e.settlement_id = settlement
        and e.sequence = 1 and e.kind = 'prepared' and e.created_by = document.created_by
        and e.created_transaction = document.created_transaction) then
        raise exception using errcode = 'check_violation',
            message = 'settlement document needs its prepared event';
    end if;
    if not exists (select 1 from gba.settlement_allocations a
        where a.tenant_id = tenant and a.book_id = book and a.settlement_id = settlement)
        or exists (select 1 from (
            select a.line_no, a.created_transaction,
                row_number() over (order by a.line_no) as position
            from gba.settlement_allocations a
            where a.tenant_id = tenant and a.book_id = book and a.settlement_id = settlement) x
            where x.line_no <> x.position or x.created_transaction <> document.created_transaction)
    then
        raise exception using errcode = 'check_violation',
            message = 'settlement allocations are complete with their document';
    end if;
    if exists (select 1 from gba.settlement_events e
        where e.tenant_id = tenant and e.book_id = book and e.settlement_id = settlement
        and e.kind = 'confirmed' and not exists (select 1 from gba.external_payments p
            where p.tenant_id = e.tenant_id and p.book_id = e.book_id
            and p.settlement_id = e.settlement_id and p.sequence = e.sequence
            and p.created_by = e.created_by
            and p.created_transaction = e.created_transaction)) then
        raise exception using errcode = 'check_violation',
            message = 'confirmed settlement event needs its external payment';
    end if;
    if exists (select 1 from gba.settlement_events e
        where e.tenant_id = tenant and e.book_id = book and e.settlement_id = settlement
        and e.kind in ('payment_voided', 'payment_corrected') and not exists (
            select 1 from gba.external_payment_revisions r
            where r.tenant_id = e.tenant_id and r.book_id = e.book_id
            and r.settlement_id = e.settlement_id and r.sequence = e.sequence
            and r.kind = case e.kind when 'payment_voided' then 'voided' else 'corrected' end
            and r.created_by = e.created_by
            and r.created_transaction = e.created_transaction)) then
        raise exception using errcode = 'check_violation',
            message = 'payment correction event needs its payment revision';
    end if;
    if exists (select 1 from gba.settlement_allocations a
        where a.tenant_id = tenant and a.book_id = book and a.settlement_id = settlement
        and a.amount_minor < coalesce((select sum(e.amount_minor)
            from gba.effective_payment_allocations(tenant, book, a.obligation_id, settlement) e), 0)) then
        raise exception using errcode = 'check_violation',
            message = 'confirmation exceeds the reserved settlement line';
    end if;
    for line in select a.obligation_id from gba.settlement_allocations a
        where a.tenant_id = tenant and a.book_id = book and a.settlement_id = settlement loop
        select * into balance from gba.obligation_balance(tenant, book, line.obligation_id);
        if balance.principal_minor is null or balance.paid_minor < 0
            or balance.credited_minor < 0 or balance.reserved_minor < 0
            or balance.paid_minor::numeric + balance.credited_minor + balance.reserved_minor
                > balance.principal_minor then
            raise exception using errcode = 'check_violation',
                message = 'obligation reserve cap exceeded';
        end if;
    end loop;
end;
$$;

-- A receipt names the exact fact its command recorded; an unknown fact matches none.
create or replace function gba.check_settlement_integrity() returns trigger language plpgsql as $$
declare settlement uuid;
begin
    if tg_table_name = 'settlement_documents' then settlement := new.id;
    else settlement := new.settlement_id; end if;
    -- A separate statement: only receipts have the sequence and operation fields.
    if tg_table_name = 'settlement_command_receipts' then
      if not exists (
        select 1 from gba.settlement_events e where e.tenant_id = new.tenant_id
        and e.book_id = new.book_id and e.settlement_id = settlement
        and e.sequence = new.sequence and e.created_by = new.created_by
        and new.operation = ('settlement_' || case e.kind
            when 'prepared' then 'prepare' when 'approved' then 'approve'
            when 'reserved' then 'reserve' when 'sent' then 'sent'
            when 'confirmed' then 'confirm' when 'released' then 'release'
            when 'cancelled' then 'cancel' when 'payment_voided' then 'payment_void'
            when 'payment_corrected' then 'payment_correct' end)
    ) then
        raise exception using errcode = 'check_violation',
            message = 'receipt needs its exact settlement event';
      end if;
    end if;
    perform gba.assert_settlement_consistent(new.tenant_id, new.book_id, settlement);
    return null;
end;
$$;

-- A revision follows the latest one of its payment, under its own settlement event of
-- the same transaction; nothing follows a void. A correction takes an open cash or bank
-- asset that is no control account and no external date after today.
create function gba.enforce_external_payment_revision() returns trigger language plpgsql as $$
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
revoke all on function gba.enforce_external_payment_revision() from public;

create function gba.enforce_external_payment_revision_allocation() returns trigger language plpgsql as $$
declare amended gba.external_payment_revisions%rowtype;
begin
    perform gba.lock_ledger(new.tenant_id);
    select * into amended from gba.external_payment_revisions r
        where r.tenant_id = new.tenant_id and r.book_id = new.book_id
        and r.payment_id = new.payment_id and r.revision = new.revision;
    if amended.payment_id is null or amended.kind <> 'corrected'
        or amended.created_transaction <> pg_catalog.pg_current_xact_id() then
        raise exception using errcode = 'check_violation',
            message = 'correction allocations are written with their revision';
    end if;
    if not exists (select 1 from gba.settlement_allocations a
        where a.tenant_id = new.tenant_id and a.book_id = new.book_id
        and a.settlement_id = amended.settlement_id and a.obligation_id = new.obligation_id) then
        raise exception using errcode = 'check_violation',
            message = 'payment allocation needs a line of its settlement';
    end if;
    return new;
end;
$$;
revoke all on function gba.enforce_external_payment_revision_allocation() from public;

-- The complete payment and every revision: the original as before; each revision
-- reverses exactly the journal of the version it replaces, never earlier than it was
-- posted; a correction carries complete allocations, its amount, and a replacement
-- journal of the cash line and every allocation. A revision of this transaction touches
-- no obligation with an issued credit, no refund obligation and no obligation another
-- settlement holds with a sent outcome still unknown.
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
                and v.credited_obligation_id = any(touched)) then
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

-- Payment and correction journals, their lines and every payment record recheck the
-- complete payment.
create or replace function gba.check_payment_integrity() returns trigger language plpgsql as $$
declare tenant uuid; book uuid; payment uuid; entry gba.journal_entries%rowtype;
begin
    tenant := new.tenant_id;
    if tg_table_name = 'external_payments' then
        book := new.book_id; payment := new.id;
    elsif tg_table_name in ('external_payment_allocations', 'external_payment_revisions',
        'external_payment_revision_allocations') then
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

-- A correction journal names its payment revision of the same transaction; like every
-- H-owned origin it is never reversed by the generic G reversal.
create or replace function gba.enforce_invoice_origin() returns trigger language plpgsql as $$
declare original gba.journal_entries%rowtype;
begin
    perform gba.lock_ledger(new.tenant_id);
    if new.reverses_entry_id is not null then
        select * into original from gba.journal_entries e
            where e.tenant_id = new.tenant_id and e.id = new.reverses_entry_id;
        if original.source_kind in ('invoice', 'accrual', 'payment', 'credit', 'payment_correction') then
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

-- A control or refund account never is an account that received external cash in any
-- payment revision.
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
    if gba.cash_account_used(new.tenant_id, new.book_id, new.control_account_id) then
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

alter table gba.external_payment_revisions enable row level security;
alter table gba.external_payment_revisions force row level security;
create policy external_payment_revisions_tenant_isolation on gba.external_payment_revisions
    using (tenant_id=gba.current_tenant_id()) with check (tenant_id=gba.current_tenant_id());
revoke all on gba.external_payment_revisions from public;
grant select on gba.external_payment_revisions to gba_runtime;
grant insert (tenant_id,book_id,payment_id,revision,settlement_id,sequence,kind,amount_minor,actual_external_date,cash_account_id,entry_date,attestation,reason,evidence_source,reversal_entry_id,entry_id,created_by) on gba.external_payment_revisions to gba_runtime;
create trigger external_payment_revisions_immutable before update or delete on gba.external_payment_revisions
    for each row execute function gba.reject_ledger_mutation();
create trigger external_payment_revisions_lock before insert on gba.external_payment_revisions
    for each row execute function gba.lock_financial_record();
create trigger external_payment_revisions_require_workflow before insert on gba.external_payment_revisions
    for each row execute function gba.require_financial_workflow();
create trigger external_payment_revisions_check before insert on gba.external_payment_revisions
    for each row execute function gba.enforce_external_payment_revision();
create constraint trigger external_payment_revisions_consistent after insert on gba.external_payment_revisions
    deferrable initially deferred for each row execute function gba.check_payment_integrity();

alter table gba.external_payment_revision_allocations enable row level security;
alter table gba.external_payment_revision_allocations force row level security;
create policy external_payment_revision_allocations_tenant_isolation on gba.external_payment_revision_allocations
    using (tenant_id=gba.current_tenant_id()) with check (tenant_id=gba.current_tenant_id());
revoke all on gba.external_payment_revision_allocations from public;
grant select on gba.external_payment_revision_allocations to gba_runtime;
grant insert (tenant_id,book_id,payment_id,revision,line_no,obligation_id,amount_minor) on gba.external_payment_revision_allocations to gba_runtime;
create trigger external_payment_revision_allocations_immutable before update or delete on gba.external_payment_revision_allocations
    for each row execute function gba.reject_ledger_mutation();
create trigger external_payment_revision_allocations_lock before insert on gba.external_payment_revision_allocations
    for each row execute function gba.lock_financial_record();
create trigger external_payment_revision_allocations_require_workflow before insert on gba.external_payment_revision_allocations
    for each row execute function gba.require_financial_workflow();
create trigger external_payment_revision_allocations_check before insert on gba.external_payment_revision_allocations
    for each row execute function gba.enforce_external_payment_revision_allocation();
create constraint trigger external_payment_revision_allocations_consistent after insert on gba.external_payment_revision_allocations
    deferrable initially deferred for each row execute function gba.check_payment_integrity();

-- Correction branch scope: restore independently in disposable drift tests.
create policy external_payment_revisions_unrestricted_scope on gba.external_payment_revisions as restrictive to gba_runtime
    using (gba.current_location_id() is null) with check (gba.current_location_id() is null);
create policy external_payment_revision_allocations_unrestricted_scope on gba.external_payment_revision_allocations as restrictive to gba_runtime
    using (gba.current_location_id() is null) with check (gba.current_location_id() is null);

-- Approved PostgreSQL 18 CHECK deparse forms; they replace earlier approvals of the
-- same constraint. Readiness never learns them from a target database.
-- CHECK_APPROVAL {"table":"journal_entries","name":"journal_entries_source_kind_check","expression":"(source_kind = ANY (ARRAY['manual'::text, 'opening'::text, 'reversal'::text, 'invoice'::text, 'accrual'::text, 'payment'::text, 'credit'::text, 'payment_correction'::text]))"}
-- CHECK_APPROVAL {"table":"settlement_events","name":"settlement_events_kind_check","expression":"(kind = ANY (ARRAY['prepared'::text, 'approved'::text, 'reserved'::text, 'sent'::text, 'confirmed'::text, 'released'::text, 'cancelled'::text, 'payment_voided'::text, 'payment_corrected'::text]))"}
-- CHECK_APPROVAL {"table":"settlement_command_receipts","name":"settlement_command_receipts_operation_check","expression":"(operation = ANY (ARRAY['settlement_prepare'::text, 'settlement_approve'::text, 'settlement_reserve'::text, 'settlement_sent'::text, 'settlement_confirm'::text, 'settlement_release'::text, 'settlement_cancel'::text, 'settlement_payment_void'::text, 'settlement_payment_correct'::text]))"}
-- CHECK_APPROVAL {"table":"financial_command_cancellations","name":"financial_command_cancellations_operation_check","expression":"(operation = ANY (ARRAY['invoice_draft'::text, 'invoice_issue'::text, 'accrual_draft'::text, 'accrual_issue'::text, 'credit_draft'::text, 'credit_issue'::text, 'settlement_prepare'::text, 'settlement_approve'::text, 'settlement_reserve'::text, 'settlement_sent'::text, 'settlement_confirm'::text, 'settlement_release'::text, 'settlement_cancel'::text, 'settlement_payment_void'::text, 'settlement_payment_correct'::text]))"}
-- CHECK_APPROVAL {"table":"external_payment_revisions","name":"external_payment_revisions_revision_check","expression":"((revision >= 2) AND (revision <= 1000))"}
-- CHECK_APPROVAL {"table":"external_payment_revisions","name":"external_payment_revisions_kind_check","expression":"(kind = ANY (ARRAY['voided'::text, 'corrected'::text]))"}
-- CHECK_APPROVAL {"table":"external_payment_revisions","name":"external_payment_revisions_amount_minor_check","expression":"((amount_minor IS NULL) OR ((amount_minor >= 1) AND (amount_minor <= '999999999999999999'::bigint)))"}
-- CHECK_APPROVAL {"table":"external_payment_revisions","name":"external_payment_revisions_attestation_check","expression":"(attestation = 'attested_erroneous_confirmation'::text)"}
-- CHECK_APPROVAL {"table":"external_payment_revisions","name":"external_payment_revisions_reason_check","expression":"(((length(btrim(reason)) >= 1) AND (length(btrim(reason)) <= 500)) AND (reason !~ '[[:cntrl:]]'::text))"}
-- CHECK_APPROVAL {"table":"external_payment_revisions","name":"external_payment_revisions_evidence_source_check","expression":"(((length(btrim(evidence_source)) >= 1) AND (length(btrim(evidence_source)) <= 200)) AND (evidence_source !~ '[[:cntrl:]]'::text))"}
-- CHECK_APPROVAL {"table":"external_payment_revisions","name":"external_payment_revisions_kind_refs","expression":"(((kind = 'voided'::text) AND (amount_minor IS NULL) AND (actual_external_date IS NULL) AND (cash_account_id IS NULL) AND (entry_id IS NULL)) OR ((kind = 'corrected'::text) AND (amount_minor IS NOT NULL) AND (actual_external_date IS NOT NULL) AND (cash_account_id IS NOT NULL) AND (entry_id IS NOT NULL)))"}
-- CHECK_APPROVAL {"table":"external_payment_revision_allocations","name":"external_payment_revision_allocations_line_no_check","expression":"((line_no >= 1) AND (line_no <= 50))"}
-- CHECK_APPROVAL {"table":"external_payment_revision_allocations","name":"external_payment_revision_allocations_amount_minor_check","expression":"((amount_minor >= 1) AND (amount_minor <= '999999999999999999'::bigint))"}
