-- H2 settlement documents and reserves (ADR-0024). A document plans exact amounts
-- against obligations of one book, party, direction and currency, then is approved,
-- reserved and released or cancelled. No journal is posted here: a reserve is not
-- money. At commit every touched obligation satisfies P + C + R <= A, computed from
-- immutable history under the ledger lock. Migrations 0001-0022 are preserved.

create table gba.settlement_documents (
    tenant_id uuid not null,
    book_id uuid not null,
    id uuid not null,
    direction text not null constraint settlement_documents_direction_check check (direction in ('receivable', 'payable')),
    counterparty_id uuid not null,
    currency text not null references gba.currencies(code),
    created_by uuid not null references gba.users(id),
    created_at timestamptz not null default now(),
    created_transaction xid8 not null default pg_catalog.pg_current_xact_id(),
    primary key (tenant_id, book_id, id),
    foreign key (tenant_id, book_id) references gba.ledger_books(tenant_id, id),
    foreign key (tenant_id, counterparty_id) references gba.counterparties(tenant_id, id)
);

create table gba.settlement_allocations (
    tenant_id uuid not null,
    book_id uuid not null,
    settlement_id uuid not null,
    line_no smallint not null constraint settlement_allocations_line_no_check check (line_no between 1 and 50),
    obligation_id uuid not null,
    amount_minor bigint not null constraint settlement_allocations_amount_minor_check check (amount_minor between 1 and 999999999999999999),
    created_transaction xid8 not null default pg_catalog.pg_current_xact_id(),
    primary key (tenant_id, book_id, settlement_id, line_no),
    unique (tenant_id, book_id, settlement_id, obligation_id),
    foreign key (tenant_id, book_id, settlement_id)
        references gba.settlement_documents(tenant_id, book_id, id),
    foreign key (tenant_id, book_id, obligation_id)
        references gba.financial_obligations(tenant_id, book_id, id)
);

create table gba.settlement_events (
    tenant_id uuid not null,
    book_id uuid not null,
    settlement_id uuid not null,
    sequence integer not null constraint settlement_events_sequence_check check (sequence > 0),
    kind text not null constraint settlement_events_kind_check check (kind in ('prepared', 'approved', 'reserved', 'sent', 'released', 'cancelled')),
    resolution text constraint settlement_events_resolution_check check (resolution is null or resolution = 'attested_no_payment'),
    reason text constraint settlement_events_reason_check check (
        reason is null or (length(btrim(reason)) between 1 and 500 and reason !~ '[[:cntrl:]]')),
    evidence_source text constraint settlement_events_evidence_source_check check (
        evidence_source is null or (length(btrim(evidence_source)) between 1 and 200 and evidence_source !~ '[[:cntrl:]]')),
    created_by uuid not null references gba.users(id),
    created_at timestamptz not null default now(),
    created_transaction xid8 not null default pg_catalog.pg_current_xact_id(),
    primary key (tenant_id, book_id, settlement_id, sequence),
    constraint settlement_events_resolution_refs check (
        (resolution is null and evidence_source is null)
        or (kind = 'released' and resolution is not null and reason is not null
            and evidence_source is not null)
    ),
    foreign key (tenant_id, book_id, settlement_id)
        references gba.settlement_documents(tenant_id, book_id, id)
);

-- Permanent reference-only outcomes of settlement commands; hashes, never bodies.
create table gba.settlement_command_receipts (
    tenant_id uuid not null,
    actor_key text not null,
    operation text not null constraint settlement_command_receipts_operation_check check (operation in ('settlement_prepare', 'settlement_approve', 'settlement_reserve', 'settlement_sent', 'settlement_release', 'settlement_cancel')),
    idempotency_key text not null constraint settlement_command_receipts_idempotency_key_check check (idempotency_key ~ '^[A-Za-z0-9._:-]{8,255}$'),
    request_hash text not null constraint settlement_command_receipts_request_hash_check check (request_hash ~ '^[0-9a-f]{64}$'),
    book_id uuid not null,
    settlement_id uuid not null,
    sequence integer not null constraint settlement_command_receipts_sequence_check check (
        sequence >= 1 and (operation = 'settlement_prepare') = (sequence = 1)),
    created_by uuid not null references gba.users(id),
    created_at timestamptz not null default now(),
    constraint settlement_command_receipts_actor_check
        check (actor_key = 'user:' || created_by::text),
    primary key (tenant_id, actor_key, operation, idempotency_key),
    foreign key (tenant_id, book_id, settlement_id, sequence)
        references gba.settlement_events(tenant_id, book_id, settlement_id, sequence)
);

-- Cancelled keys of every H command live in one table; its references are generic.
alter table gba.financial_command_cancellations
    drop constraint financial_command_cancellations_operation_check;
alter table gba.financial_command_cancellations
    add constraint financial_command_cancellations_operation_check
    check (operation in ('invoice_draft', 'invoice_issue', 'accrual_draft', 'accrual_issue', 'settlement_prepare', 'settlement_approve', 'settlement_reserve', 'settlement_sent', 'settlement_release', 'settlement_cancel'));
alter table gba.financial_command_cancellations
    drop constraint financial_command_cancellations_revision_check;
alter table gba.financial_command_cancellations
    add constraint financial_command_cancellations_revision_check
    check (revision >= 1
        and (operation in ('invoice_draft', 'accrual_draft', 'settlement_prepare') or revision >= 2)
        and (operation <> 'settlement_prepare' or revision = 1));

-- A cancelled key never commits and a committed key is never cancelled, in either
-- receipt table; both inserts wait on the same ledger lock.
create or replace function gba.lock_financial_record() returns trigger language plpgsql as $$
begin
    perform gba.lock_ledger(new.tenant_id);
    if tg_table_name in ('financial_command_receipts', 'settlement_command_receipts') then
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
    ) or exists (
        select 1 from gba.settlement_command_receipts c where c.tenant_id = new.tenant_id
        and c.actor_key = new.actor_key and c.operation = new.operation
        and c.idempotency_key = new.idempotency_key
    ) then
        raise exception using errcode = 'check_violation', message = 'financial command already committed';
      end if;
    end if;
    return new;
end;
$$;

create function gba.assert_financial_workflow(tenant uuid) returns void language plpgsql as $$
declare required text;
begin
    perform gba.lock_ledger(tenant);
    perform pg_catalog.pg_advisory_xact_lock_shared(
        pg_catalog.hashtextextended('gba:business-configuration:' || tenant::text, 0));
    foreach required in array array['finance', 'counterparties', 'finance_documents'] loop
        if not exists (select 1 from gba.business_module_states s
            where s.tenant_id = tenant and s.module_id = required and s.enabled) then
            raise exception using errcode = 'GBM01',
                message = 'the ' || required || ' module is disabled for this business';
        end if;
    end loop;
end;
$$;
revoke all on function gba.assert_financial_workflow(uuid) from public;
grant execute on function gba.assert_financial_workflow(uuid) to gba_runtime;

-- The phase follows from which facts exist, never from a stored status.
create function gba.settlement_phase(tenant uuid, book uuid, settlement uuid) returns text
    language plpgsql as $$
declare phase text;
begin
    select case
        when bool_or(e.kind = 'cancelled') then 'cancelled'
        when bool_or(e.kind = 'released') then 'released'
        when bool_or(e.kind = 'sent') then 'sent'
        when bool_or(e.kind = 'reserved') then 'reserved'
        when bool_or(e.kind = 'approved') then 'approved'
        when bool_or(e.kind = 'prepared') then 'prepared'
    end into phase
    from gba.settlement_events e
    where e.tenant_id = tenant and e.book_id = book and e.settlement_id = settlement;
    return phase;
end;
$$;
revoke all on function gba.settlement_phase(uuid, uuid, uuid) from public;
grant execute on function gba.settlement_phase(uuid, uuid, uuid) to gba_runtime;

-- A (principal), P (confirmed money), C (credit) and R (active reserves) of one
-- obligation. The service and the commit-time check read this one definition.
-- P and C have no source before external confirmations and credits exist.
create function gba.obligation_balance(tenant uuid, book uuid, obligation uuid)
    returns table (principal_minor bigint, paid_minor bigint, credited_minor bigint, reserved_minor bigint)
    language plpgsql as $$
begin
    return query
    select o.principal_minor, 0::bigint, 0::bigint,
        coalesce((select sum(a.amount_minor) from gba.settlement_allocations a
            where a.tenant_id = o.tenant_id and a.book_id = o.book_id and a.obligation_id = o.id
            and gba.settlement_phase(a.tenant_id, a.book_id, a.settlement_id)
                in ('reserved', 'sent')), 0)::bigint
    from gba.financial_obligations o
    where o.tenant_id = tenant and o.book_id = book and o.id = obligation;
end;
$$;
revoke all on function gba.obligation_balance(uuid, uuid, uuid) from public;
grant execute on function gba.obligation_balance(uuid, uuid, uuid) to gba_runtime;

create function gba.enforce_settlement_allocation() returns trigger language plpgsql as $$
declare
    document gba.settlement_documents%rowtype;
    obligation gba.financial_obligations%rowtype;
begin
    perform gba.lock_ledger(new.tenant_id);
    select * into document from gba.settlement_documents d
        where d.tenant_id = new.tenant_id and d.book_id = new.book_id and d.id = new.settlement_id;
    if document.id is null or document.created_transaction <> pg_catalog.pg_current_xact_id() then
        raise exception using errcode = 'check_violation',
            message = 'settlement allocations are written with their document';
    end if;
    select * into obligation from gba.financial_obligations o
        where o.tenant_id = new.tenant_id and o.book_id = new.book_id and o.id = new.obligation_id;
    if obligation.id is null or obligation.counterparty_id <> document.counterparty_id
        or obligation.direction <> document.direction or obligation.currency <> document.currency then
        raise exception using errcode = 'check_violation',
            message = 'settlement allocation needs an obligation of the same party, direction and currency';
    end if;
    if new.amount_minor > obligation.principal_minor then
        raise exception using errcode = 'check_violation',
            message = 'settlement allocation exceeds the obligation principal';
    end if;
    return new;
end;
$$;
revoke all on function gba.enforce_settlement_allocation() from public;

-- Contiguous facts in a fixed order. A plain release or a cancel posts no money and
-- stays possible while the module is off; a sent or unknown outcome is released only
-- by an explicit attestation, with the module on.
create function gba.enforce_settlement_event() returns trigger language plpgsql as $$
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
        or (new.kind = 'released' and phase = 'reserved' and new.resolution is null)
        or (new.kind = 'released' and phase = 'sent' and new.resolution = 'attested_no_payment')
        or (new.kind = 'cancelled' and phase in ('prepared', 'approved')), false) then
        raise exception using errcode = 'check_violation',
            message = 'settlement event does not follow its state';
    end if;
    if not (new.kind = 'cancelled' or (new.kind = 'released' and new.resolution is null)) then
        perform gba.assert_financial_workflow(new.tenant_id);
    end if;
    return new;
end;
$$;
revoke all on function gba.enforce_settlement_event() from public;

create function gba.assert_settlement_consistent(tenant uuid, book uuid, settlement uuid)
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
revoke all on function gba.assert_settlement_consistent(uuid, uuid, uuid) from public;
grant execute on function gba.assert_settlement_consistent(uuid, uuid, uuid) to gba_runtime;

create function gba.check_settlement_integrity() returns trigger language plpgsql as $$
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
            when 'released' then 'release' else 'cancel' end)
    ) then
        raise exception using errcode = 'check_violation',
            message = 'receipt needs its exact settlement event';
      end if;
    end if;
    perform gba.assert_settlement_consistent(new.tenant_id, new.book_id, settlement);
    return null;
end;
$$;
revoke all on function gba.check_settlement_integrity() from public;

alter table gba.settlement_documents enable row level security;
alter table gba.settlement_documents force row level security;
create policy settlement_documents_tenant_isolation on gba.settlement_documents
    using (tenant_id=gba.current_tenant_id()) with check (tenant_id=gba.current_tenant_id());
revoke all on gba.settlement_documents from public;
grant select on gba.settlement_documents to gba_runtime;
grant insert (tenant_id,book_id,id,direction,counterparty_id,currency,created_by) on gba.settlement_documents to gba_runtime;
create trigger settlement_documents_immutable before update or delete on gba.settlement_documents
    for each row execute function gba.reject_ledger_mutation();
create trigger settlement_documents_lock before insert on gba.settlement_documents
    for each row execute function gba.lock_financial_record();
create trigger settlement_documents_require_workflow before insert on gba.settlement_documents
    for each row execute function gba.require_financial_workflow();
create constraint trigger settlement_documents_consistent after insert on gba.settlement_documents
    deferrable initially deferred for each row execute function gba.check_settlement_integrity();

alter table gba.settlement_allocations enable row level security;
alter table gba.settlement_allocations force row level security;
create policy settlement_allocations_tenant_isolation on gba.settlement_allocations
    using (tenant_id=gba.current_tenant_id()) with check (tenant_id=gba.current_tenant_id());
revoke all on gba.settlement_allocations from public;
grant select on gba.settlement_allocations to gba_runtime;
grant insert (tenant_id,book_id,settlement_id,line_no,obligation_id,amount_minor) on gba.settlement_allocations to gba_runtime;
create trigger settlement_allocations_immutable before update or delete on gba.settlement_allocations
    for each row execute function gba.reject_ledger_mutation();
create trigger settlement_allocations_lock before insert on gba.settlement_allocations
    for each row execute function gba.lock_financial_record();
create trigger settlement_allocations_require_workflow before insert on gba.settlement_allocations
    for each row execute function gba.require_financial_workflow();
create trigger settlement_allocations_check before insert on gba.settlement_allocations
    for each row execute function gba.enforce_settlement_allocation();
create constraint trigger settlement_allocations_consistent after insert on gba.settlement_allocations
    deferrable initially deferred for each row execute function gba.check_settlement_integrity();

alter table gba.settlement_events enable row level security;
alter table gba.settlement_events force row level security;
create policy settlement_events_tenant_isolation on gba.settlement_events
    using (tenant_id=gba.current_tenant_id()) with check (tenant_id=gba.current_tenant_id());
revoke all on gba.settlement_events from public;
grant select on gba.settlement_events to gba_runtime;
grant insert (tenant_id,book_id,settlement_id,sequence,kind,resolution,reason,evidence_source,created_by) on gba.settlement_events to gba_runtime;
create trigger settlement_events_immutable before update or delete on gba.settlement_events
    for each row execute function gba.reject_ledger_mutation();
create trigger settlement_events_lock before insert on gba.settlement_events
    for each row execute function gba.lock_financial_record();
create trigger settlement_events_next before insert on gba.settlement_events
    for each row execute function gba.enforce_settlement_event();
create constraint trigger settlement_events_consistent after insert on gba.settlement_events
    deferrable initially deferred for each row execute function gba.check_settlement_integrity();

alter table gba.settlement_command_receipts enable row level security;
alter table gba.settlement_command_receipts force row level security;
create policy settlement_command_receipts_tenant_isolation on gba.settlement_command_receipts
    using (tenant_id=gba.current_tenant_id()) with check (tenant_id=gba.current_tenant_id());
revoke all on gba.settlement_command_receipts from public;
grant select on gba.settlement_command_receipts to gba_runtime;
grant insert (tenant_id,actor_key,operation,idempotency_key,request_hash,book_id,settlement_id,sequence,created_by) on gba.settlement_command_receipts to gba_runtime;
create trigger settlement_command_receipts_immutable before update or delete on gba.settlement_command_receipts
    for each row execute function gba.reject_ledger_mutation();
create trigger settlement_command_receipts_lock before insert on gba.settlement_command_receipts
    for each row execute function gba.lock_financial_record();
create constraint trigger settlement_command_receipts_consistent after insert on gba.settlement_command_receipts
    deferrable initially deferred for each row execute function gba.check_settlement_integrity();

-- Settlement branch scope: restore independently in disposable drift tests.
create policy settlement_documents_unrestricted_scope on gba.settlement_documents as restrictive to gba_runtime
    using (gba.current_location_id() is null) with check (gba.current_location_id() is null);
create policy settlement_allocations_unrestricted_scope on gba.settlement_allocations as restrictive to gba_runtime
    using (gba.current_location_id() is null) with check (gba.current_location_id() is null);
create policy settlement_events_unrestricted_scope on gba.settlement_events as restrictive to gba_runtime
    using (gba.current_location_id() is null) with check (gba.current_location_id() is null);
create policy settlement_command_receipts_unrestricted_scope on gba.settlement_command_receipts as restrictive to gba_runtime
    using (gba.current_location_id() is null) with check (gba.current_location_id() is null);

-- Approved PostgreSQL 18 CHECK deparse forms; they replace earlier approvals of the
-- same constraint. Readiness never learns them from a target database.
-- CHECK_APPROVAL {"table":"settlement_documents","name":"settlement_documents_direction_check","expression":"(direction = ANY (ARRAY['receivable'::text, 'payable'::text]))"}
-- CHECK_APPROVAL {"table":"settlement_allocations","name":"settlement_allocations_line_no_check","expression":"((line_no >= 1) AND (line_no <= 50))"}
-- CHECK_APPROVAL {"table":"settlement_allocations","name":"settlement_allocations_amount_minor_check","expression":"((amount_minor >= 1) AND (amount_minor <= '999999999999999999'::bigint))"}
-- CHECK_APPROVAL {"table":"settlement_events","name":"settlement_events_sequence_check","expression":"(sequence > 0)"}
-- CHECK_APPROVAL {"table":"settlement_events","name":"settlement_events_kind_check","expression":"(kind = ANY (ARRAY['prepared'::text, 'approved'::text, 'reserved'::text, 'sent'::text, 'released'::text, 'cancelled'::text]))"}
-- CHECK_APPROVAL {"table":"settlement_events","name":"settlement_events_resolution_check","expression":"((resolution IS NULL) OR (resolution = 'attested_no_payment'::text))"}
-- CHECK_APPROVAL {"table":"settlement_events","name":"settlement_events_reason_check","expression":"((reason IS NULL) OR (((length(btrim(reason)) >= 1) AND (length(btrim(reason)) <= 500)) AND (reason !~ '[[:cntrl:]]'::text)))"}
-- CHECK_APPROVAL {"table":"settlement_events","name":"settlement_events_evidence_source_check","expression":"((evidence_source IS NULL) OR (((length(btrim(evidence_source)) >= 1) AND (length(btrim(evidence_source)) <= 200)) AND (evidence_source !~ '[[:cntrl:]]'::text)))"}
-- CHECK_APPROVAL {"table":"settlement_events","name":"settlement_events_resolution_refs","expression":"(((resolution IS NULL) AND (evidence_source IS NULL)) OR ((kind = 'released'::text) AND (resolution IS NOT NULL) AND (reason IS NOT NULL) AND (evidence_source IS NOT NULL)))"}
-- CHECK_APPROVAL {"table":"settlement_command_receipts","name":"settlement_command_receipts_operation_check","expression":"(operation = ANY (ARRAY['settlement_prepare'::text, 'settlement_approve'::text, 'settlement_reserve'::text, 'settlement_sent'::text, 'settlement_release'::text, 'settlement_cancel'::text]))"}
-- CHECK_APPROVAL {"table":"settlement_command_receipts","name":"settlement_command_receipts_idempotency_key_check","expression":"(idempotency_key ~ '^[A-Za-z0-9._:-]{8,255}$'::text)"}
-- CHECK_APPROVAL {"table":"settlement_command_receipts","name":"settlement_command_receipts_request_hash_check","expression":"(request_hash ~ '^[0-9a-f]{64}$'::text)"}
-- CHECK_APPROVAL {"table":"settlement_command_receipts","name":"settlement_command_receipts_sequence_check","expression":"((sequence >= 1) AND ((operation = 'settlement_prepare'::text) = (sequence = 1)))"}
-- CHECK_APPROVAL {"table":"settlement_command_receipts","name":"settlement_command_receipts_actor_check","expression":"(actor_key = ('user:'::text || (created_by)::text))"}
-- CHECK_APPROVAL {"table":"financial_command_cancellations","name":"financial_command_cancellations_operation_check","expression":"(operation = ANY (ARRAY['invoice_draft'::text, 'invoice_issue'::text, 'accrual_draft'::text, 'accrual_issue'::text, 'settlement_prepare'::text, 'settlement_approve'::text, 'settlement_reserve'::text, 'settlement_sent'::text, 'settlement_release'::text, 'settlement_cancel'::text]))"}
-- CHECK_APPROVAL {"table":"financial_command_cancellations","name":"financial_command_cancellations_revision_check","expression":"((revision >= 1) AND ((operation = ANY (ARRAY['invoice_draft'::text, 'accrual_draft'::text, 'settlement_prepare'::text])) OR (revision >= 2)) AND ((operation <> 'settlement_prepare'::text) OR (revision = 1)))"}
