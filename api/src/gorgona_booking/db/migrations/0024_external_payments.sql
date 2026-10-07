-- H2 externally attested confirmations (ADR-0024). A confirmation records a fact a
-- human attests about money that moved outside this program; nothing is sent and no
-- provider is consulted. It moves exactly its allocations from the reserve of one
-- settlement to confirmed money, posts one balanced G journal of the new origin
-- 'payment' and binds a permanent external identity to one payment. No unallocated
-- advance and no FX. Migrations 0001-0023 are preserved.

alter table gba.journal_entries drop constraint journal_entries_source_kind_check;
alter table gba.journal_entries add constraint journal_entries_source_kind_check
    check (source_kind in ('manual', 'opening', 'reversal', 'invoice', 'accrual', 'payment'));

alter table gba.settlement_events drop constraint settlement_events_kind_check;
alter table gba.settlement_events add constraint settlement_events_kind_check
    check (kind in ('prepared', 'approved', 'reserved', 'sent', 'confirmed', 'released', 'cancelled'));

alter table gba.settlement_command_receipts
    drop constraint settlement_command_receipts_operation_check;
alter table gba.settlement_command_receipts
    add constraint settlement_command_receipts_operation_check
    check (operation in ('settlement_prepare', 'settlement_approve', 'settlement_reserve', 'settlement_sent', 'settlement_confirm', 'settlement_release', 'settlement_cancel'));

alter table gba.financial_command_cancellations
    drop constraint financial_command_cancellations_operation_check;
alter table gba.financial_command_cancellations
    add constraint financial_command_cancellations_operation_check
    check (operation in ('invoice_draft', 'invoice_issue', 'accrual_draft', 'accrual_issue', 'settlement_prepare', 'settlement_approve', 'settlement_reserve', 'settlement_sent', 'settlement_confirm', 'settlement_release', 'settlement_cancel'));

-- One real external fact: the same book, direction, source account alias and
-- reference stay bound to this payment forever, whatever idempotency key was used.
create table gba.external_payments (
    tenant_id uuid not null,
    book_id uuid not null,
    id uuid not null,
    settlement_id uuid not null,
    sequence integer not null,
    direction text not null constraint external_payments_direction_check check (direction in ('receivable', 'payable')),
    currency text not null references gba.currencies(code),
    amount_minor bigint not null constraint external_payments_amount_minor_check check (amount_minor between 1 and 999999999999999999),
    actual_external_date date not null,
    entry_date date not null,
    cash_account_id uuid not null,
    source_account_alias text not null constraint external_payments_source_account_alias_check check (
        source_account_alias = btrim(source_account_alias)
        and length(source_account_alias) between 1 and 100 and source_account_alias !~ '[[:cntrl:]]'),
    external_reference text not null constraint external_payments_external_reference_check check (
        external_reference = btrim(external_reference)
        and length(external_reference) between 1 and 200 and external_reference !~ '[[:cntrl:]]'),
    attestation text not null constraint external_payments_attestation_check check (attestation = 'manual_attestation'),
    entry_id uuid not null,
    created_by uuid not null references gba.users(id),
    created_at timestamptz not null default now(),
    created_transaction xid8 not null default pg_catalog.pg_current_xact_id(),
    primary key (tenant_id, book_id, id),
    constraint external_payments_identity
        unique (tenant_id, book_id, direction, source_account_alias, external_reference),
    unique (tenant_id, book_id, entry_id),
    unique (tenant_id, book_id, settlement_id, sequence),
    foreign key (tenant_id, book_id, settlement_id, sequence)
        references gba.settlement_events(tenant_id, book_id, settlement_id, sequence),
    foreign key (tenant_id, book_id, cash_account_id)
        references gba.ledger_accounts(tenant_id, book_id, id),
    constraint external_payments_entry_fk foreign key (tenant_id, book_id, entry_id)
        references gba.journal_entries(tenant_id, book_id, id) deferrable initially deferred
);

create table gba.external_payment_allocations (
    tenant_id uuid not null,
    book_id uuid not null,
    payment_id uuid not null,
    line_no smallint not null constraint external_payment_allocations_line_no_check check (line_no between 1 and 50),
    obligation_id uuid not null,
    amount_minor bigint not null constraint external_payment_allocations_amount_minor_check check (amount_minor between 1 and 999999999999999999),
    created_transaction xid8 not null default pg_catalog.pg_current_xact_id(),
    primary key (tenant_id, book_id, payment_id, line_no),
    unique (tenant_id, book_id, payment_id, obligation_id),
    foreign key (tenant_id, book_id, payment_id)
        references gba.external_payments(tenant_id, book_id, id),
    foreign key (tenant_id, book_id, obligation_id)
        references gba.financial_obligations(tenant_id, book_id, id)
);

-- P is every confirmed allocation; R is what each reserving document still holds
-- after its own confirmations. C has no source before credits exist.
create or replace function gba.obligation_balance(tenant uuid, book uuid, obligation uuid)
    returns table (principal_minor bigint, paid_minor bigint, credited_minor bigint, reserved_minor bigint)
    language plpgsql as $$
begin
    return query
    select o.principal_minor,
        coalesce((select sum(p.amount_minor) from gba.external_payment_allocations p
            where p.tenant_id = o.tenant_id and p.book_id = o.book_id
            and p.obligation_id = o.id), 0)::bigint,
        0::bigint,
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

-- A confirmation follows a reserve (also a sent one). A fully confirmed settlement
-- is final: nothing remains to send, confirm or release.
create or replace function gba.enforce_settlement_event() returns trigger language plpgsql as $$
declare
    document gba.settlement_documents%rowtype;
    previous integer;
    phase text;
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
        or (new.kind = 'cancelled' and phase in ('prepared', 'approved')), false) then
        raise exception using errcode = 'check_violation',
            message = 'settlement event does not follow its state';
    end if;
    if phase in ('reserved', 'sent') and
        (select coalesce(sum(a.amount_minor), 0) from gba.settlement_allocations a
            where a.tenant_id = new.tenant_id and a.book_id = new.book_id
            and a.settlement_id = new.settlement_id)
        = (select coalesce(sum(p.amount_minor), 0) from gba.external_payments p
            where p.tenant_id = new.tenant_id and p.book_id = new.book_id
            and p.settlement_id = new.settlement_id) then
        raise exception using errcode = 'check_violation',
            message = 'a fully confirmed settlement is final';
    end if;
    if not (new.kind = 'cancelled' or (new.kind = 'released' and new.resolution is null)) then
        perform gba.assert_financial_workflow(new.tenant_id);
    end if;
    return new;
end;
$$;

create function gba.enforce_external_payment() returns trigger language plpgsql as $$
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
    return new;
end;
$$;
revoke all on function gba.enforce_external_payment() from public;

create function gba.enforce_external_payment_allocation() returns trigger language plpgsql as $$
declare payment gba.external_payments%rowtype;
begin
    perform gba.lock_ledger(new.tenant_id);
    select * into payment from gba.external_payments p
        where p.tenant_id = new.tenant_id and p.book_id = new.book_id and p.id = new.payment_id;
    if payment.id is null or payment.created_transaction <> pg_catalog.pg_current_xact_id() then
        raise exception using errcode = 'check_violation',
            message = 'payment allocations are written with their payment';
    end if;
    if not exists (select 1 from gba.settlement_allocations a
        where a.tenant_id = new.tenant_id and a.book_id = new.book_id
        and a.settlement_id = payment.settlement_id and a.obligation_id = new.obligation_id) then
        raise exception using errcode = 'check_violation',
            message = 'payment allocation needs a line of its settlement';
    end if;
    return new;
end;
$$;
revoke all on function gba.enforce_external_payment_allocation() from public;

-- Every confirmed fact has its payment, no line confirms more than it reserved and
-- every touched obligation keeps P + C + R <= A.
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
    if exists (select 1 from gba.settlement_allocations a
        where a.tenant_id = tenant and a.book_id = book and a.settlement_id = settlement
        and a.amount_minor < coalesce((select sum(p.amount_minor)
            from gba.external_payment_allocations p
            join gba.external_payments e on e.tenant_id = p.tenant_id
                and e.book_id = p.book_id and e.id = p.payment_id
            where p.tenant_id = a.tenant_id and p.book_id = a.book_id
            and p.obligation_id = a.obligation_id and e.settlement_id = a.settlement_id), 0)) then
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
            when 'cancelled' then 'cancel' end)
    ) then
        raise exception using errcode = 'check_violation',
            message = 'receipt needs its exact settlement event';
      end if;
    end if;
    perform gba.assert_settlement_consistent(new.tenant_id, new.book_id, settlement);
    return null;
end;
$$;

-- The complete payment: exact allocations, its own journal with the cash line and
-- one control line per allocation, and a consistent settlement.
create function gba.assert_payment_consistent(tenant uuid, book uuid, payment uuid)
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
revoke all on function gba.assert_payment_consistent(uuid, uuid, uuid) from public;
grant execute on function gba.assert_payment_consistent(uuid, uuid, uuid) to gba_runtime;

create function gba.check_payment_integrity() returns trigger language plpgsql as $$
declare tenant uuid; book uuid; payment uuid; entry gba.journal_entries%rowtype;
begin
    tenant := new.tenant_id;
    if tg_table_name = 'external_payments' then
        book := new.book_id; payment := new.id;
    elsif tg_table_name = 'external_payment_allocations' then
        book := new.book_id; payment := new.payment_id;
    else
        if tg_table_name = 'journal_entries' then entry := new;
        else select * into entry from gba.journal_entries e
            where e.tenant_id = tenant and e.id = new.entry_id; end if;
        if entry.source_kind is distinct from 'payment' then return null; end if;
        book := entry.book_id;
        select x.id into payment from gba.external_payments x
            where x.tenant_id = tenant and x.book_id = book and x.entry_id = entry.id;
        if payment is null then
            raise exception using errcode = 'check_violation',
                message = 'payment journal cannot be orphaned';
        end if;
    end if;
    perform gba.assert_payment_consistent(tenant, book, payment);
    return null;
end;
$$;
revoke all on function gba.check_payment_integrity() from public;

-- A payment journal names its payment of the same transaction; like every H-owned
-- origin it is never reversed by the generic G reversal.
create or replace function gba.enforce_invoice_origin() returns trigger language plpgsql as $$
declare original gba.journal_entries%rowtype;
begin
    perform gba.lock_ledger(new.tenant_id);
    if new.reverses_entry_id is not null then
        select * into original from gba.journal_entries e
            where e.tenant_id = new.tenant_id and e.id = new.reverses_entry_id;
        if original.source_kind in ('invoice', 'accrual', 'payment') then
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

alter table gba.external_payments enable row level security;
alter table gba.external_payments force row level security;
create policy external_payments_tenant_isolation on gba.external_payments
    using (tenant_id=gba.current_tenant_id()) with check (tenant_id=gba.current_tenant_id());
revoke all on gba.external_payments from public;
grant select on gba.external_payments to gba_runtime;
grant insert (tenant_id,book_id,id,settlement_id,sequence,direction,currency,amount_minor,actual_external_date,entry_date,cash_account_id,source_account_alias,external_reference,attestation,entry_id,created_by) on gba.external_payments to gba_runtime;
create trigger external_payments_immutable before update or delete on gba.external_payments
    for each row execute function gba.reject_ledger_mutation();
create trigger external_payments_lock before insert on gba.external_payments
    for each row execute function gba.lock_financial_record();
create trigger external_payments_require_workflow before insert on gba.external_payments
    for each row execute function gba.require_financial_workflow();
create trigger external_payments_check before insert on gba.external_payments
    for each row execute function gba.enforce_external_payment();
create constraint trigger external_payments_consistent after insert on gba.external_payments
    deferrable initially deferred for each row execute function gba.check_payment_integrity();

alter table gba.external_payment_allocations enable row level security;
alter table gba.external_payment_allocations force row level security;
create policy external_payment_allocations_tenant_isolation on gba.external_payment_allocations
    using (tenant_id=gba.current_tenant_id()) with check (tenant_id=gba.current_tenant_id());
revoke all on gba.external_payment_allocations from public;
grant select on gba.external_payment_allocations to gba_runtime;
grant insert (tenant_id,book_id,payment_id,line_no,obligation_id,amount_minor) on gba.external_payment_allocations to gba_runtime;
create trigger external_payment_allocations_immutable before update or delete on gba.external_payment_allocations
    for each row execute function gba.reject_ledger_mutation();
create trigger external_payment_allocations_lock before insert on gba.external_payment_allocations
    for each row execute function gba.lock_financial_record();
create trigger external_payment_allocations_require_workflow before insert on gba.external_payment_allocations
    for each row execute function gba.require_financial_workflow();
create trigger external_payment_allocations_check before insert on gba.external_payment_allocations
    for each row execute function gba.enforce_external_payment_allocation();
create constraint trigger external_payment_allocations_consistent after insert on gba.external_payment_allocations
    deferrable initially deferred for each row execute function gba.check_payment_integrity();

create constraint trigger journal_entries_payment_consistent after insert on gba.journal_entries
    deferrable initially deferred for each row execute function gba.check_payment_integrity();
create constraint trigger journal_lines_payment_consistent after insert on gba.journal_lines
    deferrable initially deferred for each row execute function gba.check_payment_integrity();

-- Payment branch scope: restore independently in disposable drift tests.
create policy external_payments_unrestricted_scope on gba.external_payments as restrictive to gba_runtime
    using (gba.current_location_id() is null) with check (gba.current_location_id() is null);
create policy external_payment_allocations_unrestricted_scope on gba.external_payment_allocations as restrictive to gba_runtime
    using (gba.current_location_id() is null) with check (gba.current_location_id() is null);

-- Approved PostgreSQL 18 CHECK deparse forms; they replace earlier approvals of the
-- same constraint. Readiness never learns them from a target database.
-- CHECK_APPROVAL {"table":"journal_entries","name":"journal_entries_source_kind_check","expression":"(source_kind = ANY (ARRAY['manual'::text, 'opening'::text, 'reversal'::text, 'invoice'::text, 'accrual'::text, 'payment'::text]))"}
-- CHECK_APPROVAL {"table":"settlement_events","name":"settlement_events_kind_check","expression":"(kind = ANY (ARRAY['prepared'::text, 'approved'::text, 'reserved'::text, 'sent'::text, 'confirmed'::text, 'released'::text, 'cancelled'::text]))"}
-- CHECK_APPROVAL {"table":"settlement_command_receipts","name":"settlement_command_receipts_operation_check","expression":"(operation = ANY (ARRAY['settlement_prepare'::text, 'settlement_approve'::text, 'settlement_reserve'::text, 'settlement_sent'::text, 'settlement_confirm'::text, 'settlement_release'::text, 'settlement_cancel'::text]))"}
-- CHECK_APPROVAL {"table":"financial_command_cancellations","name":"financial_command_cancellations_operation_check","expression":"(operation = ANY (ARRAY['invoice_draft'::text, 'invoice_issue'::text, 'accrual_draft'::text, 'accrual_issue'::text, 'settlement_prepare'::text, 'settlement_approve'::text, 'settlement_reserve'::text, 'settlement_sent'::text, 'settlement_confirm'::text, 'settlement_release'::text, 'settlement_cancel'::text]))"}
-- CHECK_APPROVAL {"table":"external_payments","name":"external_payments_direction_check","expression":"(direction = ANY (ARRAY['receivable'::text, 'payable'::text]))"}
-- CHECK_APPROVAL {"table":"external_payments","name":"external_payments_amount_minor_check","expression":"((amount_minor >= 1) AND (amount_minor <= '999999999999999999'::bigint))"}
-- CHECK_APPROVAL {"table":"external_payments","name":"external_payments_source_account_alias_check","expression":"((source_account_alias = btrim(source_account_alias)) AND ((length(source_account_alias) >= 1) AND (length(source_account_alias) <= 100)) AND (source_account_alias !~ '[[:cntrl:]]'::text))"}
-- CHECK_APPROVAL {"table":"external_payments","name":"external_payments_external_reference_check","expression":"((external_reference = btrim(external_reference)) AND ((length(external_reference) >= 1) AND (length(external_reference) <= 200)) AND (external_reference !~ '[[:cntrl:]]'::text))"}
-- CHECK_APPROVAL {"table":"external_payments","name":"external_payments_attestation_check","expression":"(attestation = 'manual_attestation'::text)"}
-- CHECK_APPROVAL {"table":"external_payment_allocations","name":"external_payment_allocations_line_no_check","expression":"((line_no >= 1) AND (line_no <= 50))"}
-- CHECK_APPROVAL {"table":"external_payment_allocations","name":"external_payment_allocations_amount_minor_check","expression":"((amount_minor >= 1) AND (amount_minor <= '999999999999999999'::bigint))"}
