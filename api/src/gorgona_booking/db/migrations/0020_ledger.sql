-- Ledger foundation (ADR-0023, FIN-01): one book per legal entity, a chart of
-- accounts, balanced double-entry journal entries in integer minor units and
-- monthly periods that can be closed. Everything is inserted only: a correction is
-- a reversal and a new entry; closing and reopening are recorded events. Every insert
-- needs the finance module enabled by a published configuration. One entry has one
-- currency; currencies are never converted or summed together here.

-- ISO 4217 currencies with their minor-unit scale (built-in reference data shared by
-- all companies; adding a code is a migration). Fund and metal codes are not accepted.
-- Verified against SIX List One, published 2026-09-17, retrieved 2026-10-06.
-- https://www.six-group.com/dam/download/financial-information/data-center/iso-currrency/lists/list-one.xml
create table gba.currencies (
    code text primary key check (code ~ '^[A-Z]{3}$'),
    minor_units smallint not null check (minor_units in (0, 2, 3))
);
insert into gba.currencies (code, minor_units)
select code, 2 from unnest(array[
    'AED', 'AFN', 'ALL', 'AMD', 'AOA', 'ARS', 'AUD', 'AWG', 'AZN', 'BAM', 'BBD',
    'BDT', 'BMD', 'BND', 'BOB', 'BRL', 'BSD', 'BTN', 'BWP', 'BYN', 'BZD',
    'CAD', 'CDF', 'CHF', 'CNY', 'COP', 'CRC', 'CUP', 'CVE', 'CZK', 'DKK', 'DOP',
    'DZD', 'EGP', 'ERN', 'ETB', 'EUR', 'FJD', 'FKP', 'GBP', 'GEL', 'GHS', 'GIP',
    'GMD', 'GTQ', 'GYD', 'HKD', 'HNL', 'HTG', 'HUF', 'IDR', 'ILS', 'INR', 'IRR',
    'JMD', 'KES', 'KGS', 'KHR', 'KPW', 'KYD', 'KZT', 'LAK', 'LBP', 'LKR', 'LRD',
    'LSL', 'MAD', 'MDL', 'MGA', 'MKD', 'MMK', 'MNT', 'MOP', 'MRU', 'MUR', 'MVR',
    'MWK', 'MXN', 'MYR', 'MZN', 'NAD', 'NGN', 'NIO', 'NOK', 'NPR', 'NZD', 'PAB',
    'PEN', 'PGK', 'PHP', 'PKR', 'PLN', 'QAR', 'RON', 'RSD', 'RUB', 'SAR', 'SBD',
    'SCR', 'SDG', 'SEK', 'SGD', 'SHP', 'SLE', 'SOS', 'SRD', 'SSP', 'STN', 'SVC',
    'SYP', 'SZL', 'THB', 'TJS', 'TMT', 'TOP', 'TRY', 'TTD', 'TWD', 'TZS', 'UAH',
    'USD', 'UYU', 'UZS', 'VED', 'VES', 'WST', 'XCD', 'XCG', 'YER', 'ZAR', 'ZMW',
    'ZWG'
]) as code
union all
select code, 0 from unnest(array[
    'BIF', 'CLP', 'DJF', 'GNF', 'ISK', 'JPY', 'KMF', 'KRW', 'PYG', 'RWF', 'UGX',
    'VND', 'VUV', 'XAF', 'XOF', 'XPF'
]) as code
union all
select code, 3 from unnest(array['BHD', 'IQD', 'JOD', 'KWD', 'LYD', 'OMR', 'TND']) as code;
revoke all on gba.currencies from public;
grant select on gba.currencies to gba_runtime;
-- Every table forces row security; this shared reference table is readable by all.
alter table gba.currencies enable row level security;
alter table gba.currencies force row level security;
create policy currencies_read on gba.currencies for select to gba_runtime using (true);

create table gba.ledger_books (
    tenant_id uuid not null references gba.tenants (id),
    id uuid not null,
    legal_entity_id uuid not null,
    created_by uuid not null references gba.users (id),
    created_at timestamptz not null default now(),
    primary key (tenant_id, id),
    constraint ledger_books_one_per_entity unique (tenant_id, legal_entity_id),
    constraint ledger_books_legal_entity_fk foreign key (tenant_id, legal_entity_id)
        references gba.legal_entities (tenant_id, id)
);

create table gba.ledger_book_versions (
    tenant_id uuid not null,
    book_id uuid not null,
    revision integer not null check (revision > 0),
    base_currency text not null references gba.currencies (code),
    fiscal_year_start_month smallint not null check (fiscal_year_start_month between 1 and 12),
    accounting_start date not null,
    created_by uuid not null references gba.users (id),
    created_at timestamptz not null default now(),
    primary key (tenant_id, book_id, revision),
    foreign key (tenant_id, book_id) references gba.ledger_books (tenant_id, id)
);

create table gba.ledger_accounts (
    tenant_id uuid not null,
    id uuid not null,
    book_id uuid not null,
    code text not null check (code ~ '^[0-9A-Za-z][0-9A-Za-z.-]{0,31}$'),
    type text not null check (type in ('asset', 'liability', 'equity', 'revenue', 'expense')),
    created_by uuid not null references gba.users (id),
    created_at timestamptz not null default now(),
    primary key (tenant_id, id),
    constraint ledger_accounts_code_unique unique (tenant_id, book_id, code),
    -- Lines name the account together with its book.
    unique (tenant_id, book_id, id),
    foreign key (tenant_id, book_id) references gba.ledger_books (tenant_id, id)
);

create table gba.ledger_account_versions (
    tenant_id uuid not null,
    account_id uuid not null,
    revision integer not null check (revision > 0),
    name text not null check (
        length(btrim(name, E' \t\r\n')) between 1 and 200 and name !~ '[[:cntrl:]]'
    ),
    archived boolean not null,
    created_by uuid not null references gba.users (id),
    created_at timestamptz not null default now(),
    primary key (tenant_id, account_id, revision),
    foreign key (tenant_id, account_id) references gba.ledger_accounts (tenant_id, id)
);

create table gba.journal_entries (
    tenant_id uuid not null,
    id uuid not null,
    book_id uuid not null,
    entry_date date not null,
    period date generated always as (date_trunc('month', entry_date::timestamp)::date) stored,
    currency text not null references gba.currencies (code),
    source_kind text not null check (source_kind in ('manual', 'opening', 'reversal')),
    source_id text not null check (source_id ~ '^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$'),
    memo text check (memo is null or (length(memo) between 1 and 500 and memo !~ '[[:cntrl:]]')),
    reverses_entry_id uuid,
    created_by uuid not null references gba.users (id),
    created_at timestamptz not null default now(),
    primary key (tenant_id, id),
    unique (tenant_id, book_id, id),
    -- One business operation posts once.
    constraint journal_entries_operation_unique unique (tenant_id, book_id, source_kind, source_id),
    -- An entry is reversed at most once.
    constraint journal_entries_reversed_once unique (tenant_id, reverses_entry_id),
    constraint journal_entries_reversal_link
        check ((source_kind = 'reversal') = (reverses_entry_id is not null)),
    foreign key (tenant_id, book_id) references gba.ledger_books (tenant_id, id),
    constraint journal_entries_reverses_fk foreign key (tenant_id, book_id, reverses_entry_id)
        references gba.journal_entries (tenant_id, book_id, id)
);
create index journal_entries_period on gba.journal_entries (tenant_id, book_id, period, id);

create table gba.journal_lines (
    tenant_id uuid not null,
    entry_id uuid not null,
    line_no smallint not null check (line_no between 1 and 200),
    book_id uuid not null,
    account_id uuid not null,
    side text not null check (side in ('debit', 'credit')),
    amount_minor bigint not null check (amount_minor between 1 and 999999999999999999),
    primary key (tenant_id, entry_id, line_no),
    foreign key (tenant_id, book_id, entry_id)
        references gba.journal_entries (tenant_id, book_id, id),
    constraint journal_lines_account_fk foreign key (tenant_id, book_id, account_id)
        references gba.ledger_accounts (tenant_id, book_id, id)
);
create index journal_lines_account on gba.journal_lines (tenant_id, account_id);

-- Closing and reopening a month of a book, in order: closed, reopened, closed ...
create table gba.ledger_period_events (
    tenant_id uuid not null,
    id uuid not null default uuidv7(),
    book_id uuid not null,
    period date not null check (extract(day from period) = 1),
    sequence integer not null check (sequence > 0),
    action text not null check (action in ('closed', 'reopened')),
    reason text check (
        reason is null or (length(reason) between 1 and 500 and reason !~ '[[:cntrl:]]')
    ),
    decided_by uuid not null references gba.users (id),
    decided_at timestamptz not null default now(),
    primary key (tenant_id, book_id, period, sequence),
    unique (tenant_id, id),
    constraint ledger_period_events_reopen_reason check (action = 'closed' or reason is not null),
    foreign key (tenant_id, book_id) references gba.ledger_books (tenant_id, id)
);

alter table gba.ledger_books enable row level security;
alter table gba.ledger_books force row level security;
alter table gba.ledger_book_versions enable row level security;
alter table gba.ledger_book_versions force row level security;
alter table gba.ledger_accounts enable row level security;
alter table gba.ledger_accounts force row level security;
alter table gba.ledger_account_versions enable row level security;
alter table gba.ledger_account_versions force row level security;
alter table gba.journal_entries enable row level security;
alter table gba.journal_entries force row level security;
alter table gba.journal_lines enable row level security;
alter table gba.journal_lines force row level security;
alter table gba.ledger_period_events enable row level security;
alter table gba.ledger_period_events force row level security;

create policy ledger_books_tenant_isolation on gba.ledger_books
    using (tenant_id = gba.current_tenant_id()) with check (tenant_id = gba.current_tenant_id());
grant select on gba.ledger_books to gba_runtime;
grant insert (tenant_id, id, legal_entity_id, created_by) on gba.ledger_books to gba_runtime;

create policy ledger_book_versions_tenant_isolation on gba.ledger_book_versions
    using (tenant_id = gba.current_tenant_id()) with check (tenant_id = gba.current_tenant_id());
grant select on gba.ledger_book_versions to gba_runtime;
grant insert (tenant_id, book_id, revision, base_currency, fiscal_year_start_month,
              accounting_start, created_by)
    on gba.ledger_book_versions to gba_runtime;

create policy ledger_accounts_tenant_isolation on gba.ledger_accounts
    using (tenant_id = gba.current_tenant_id()) with check (tenant_id = gba.current_tenant_id());
grant select on gba.ledger_accounts to gba_runtime;
grant insert (tenant_id, id, book_id, code, type, created_by) on gba.ledger_accounts to gba_runtime;

create policy ledger_account_versions_tenant_isolation on gba.ledger_account_versions
    using (tenant_id = gba.current_tenant_id()) with check (tenant_id = gba.current_tenant_id());
grant select on gba.ledger_account_versions to gba_runtime;
grant insert (tenant_id, account_id, revision, name, archived, created_by)
    on gba.ledger_account_versions to gba_runtime;

create policy journal_entries_tenant_isolation on gba.journal_entries
    using (tenant_id = gba.current_tenant_id()) with check (tenant_id = gba.current_tenant_id());
grant select on gba.journal_entries to gba_runtime;
grant insert (tenant_id, id, book_id, entry_date, currency, source_kind, source_id, memo,
              reverses_entry_id, created_by)
    on gba.journal_entries to gba_runtime;

create policy journal_lines_tenant_isolation on gba.journal_lines
    using (tenant_id = gba.current_tenant_id()) with check (tenant_id = gba.current_tenant_id());
grant select on gba.journal_lines to gba_runtime;
grant insert (tenant_id, entry_id, line_no, book_id, account_id, side, amount_minor)
    on gba.journal_lines to gba_runtime;

create policy ledger_period_events_tenant_isolation on gba.ledger_period_events
    using (tenant_id = gba.current_tenant_id()) with check (tenant_id = gba.current_tenant_id());
grant select on gba.ledger_period_events to gba_runtime;
grant insert (tenant_id, book_id, period, sequence, action, reason, decided_by)
    on gba.ledger_period_events to gba_runtime;

create function gba.reject_ledger_mutation() returns trigger language plpgsql as $$
begin
    raise exception using errcode = 'check_violation',
        message = 'ledger records are kept unchanged; post a reversal instead';
end;
$$;
revoke all on function gba.reject_ledger_mutation() from public;
create trigger ledger_books_immutable before update or delete on gba.ledger_books
    for each row execute function gba.reject_ledger_mutation();
create trigger ledger_book_versions_immutable before update or delete on gba.ledger_book_versions
    for each row execute function gba.reject_ledger_mutation();
create trigger ledger_accounts_immutable before update or delete on gba.ledger_accounts
    for each row execute function gba.reject_ledger_mutation();
create trigger ledger_account_versions_immutable
    before update or delete on gba.ledger_account_versions
    for each row execute function gba.reject_ledger_mutation();
create trigger journal_entries_immutable before update or delete on gba.journal_entries
    for each row execute function gba.reject_ledger_mutation();
create trigger journal_lines_immutable before update or delete on gba.journal_lines
    for each row execute function gba.reject_ledger_mutation();
create trigger ledger_period_events_immutable before update or delete on gba.ledger_period_events
    for each row execute function gba.reject_ledger_mutation();

-- The posting lock; the API takes the same key through authorized_tenant("ledger").
create function gba.lock_ledger(tenant uuid) returns void language plpgsql as $$
begin
    -- Advisory locks do not refresh an older REPEATABLE READ/SERIALIZABLE snapshot.
    if pg_catalog.current_setting('transaction_isolation') <> 'read committed' then
        raise exception using errcode = 'serialization_failure',
            message = 'ledger writes require read committed transactions';
    end if;
    perform pg_catalog.pg_advisory_xact_lock(
        pg_catalog.hashtextextended('gba:ledger:' || tenant::text, 0));
end;
$$;
revoke all on function gba.lock_ledger(uuid) from public;
grant execute on function gba.lock_ledger(uuid) to gba_runtime;

-- Book versions are contiguous; the base currency and accounting start are fixed
-- once entries exist.
create function gba.enforce_ledger_book_version() returns trigger
    language plpgsql as $$
declare
    previous gba.ledger_book_versions%rowtype;
begin
    perform gba.lock_ledger(new.tenant_id);
    select * into previous from gba.ledger_book_versions v
     where v.tenant_id = new.tenant_id and v.book_id = new.book_id
     order by v.revision desc limit 1;
    if new.revision <> coalesce(previous.revision, 0) + 1 then
        raise exception using errcode = 'check_violation',
            message = 'a book version follows the latest revision';
    end if;
    if previous.revision is not null and exists (
        select 1 from gba.journal_entries e
        where e.tenant_id = new.tenant_id and e.book_id = new.book_id
    ) and (new.base_currency, new.accounting_start)
          is distinct from (previous.base_currency, previous.accounting_start) then
        raise exception using errcode = 'check_violation',
            message = 'base currency and accounting start are fixed once entries exist';
    end if;
    return new;
end;
$$;
revoke all on function gba.enforce_ledger_book_version() from public;
create trigger ledger_book_versions_next_revision before insert on gba.ledger_book_versions
    for each row execute function gba.enforce_ledger_book_version();

create function gba.enforce_ledger_account_version() returns trigger
    language plpgsql as $$
begin
    perform gba.lock_ledger(new.tenant_id);
    if new.revision <> coalesce((
        select max(v.revision) from gba.ledger_account_versions v
        where v.tenant_id = new.tenant_id and v.account_id = new.account_id
    ), 0) + 1 then
        raise exception using errcode = 'check_violation',
            message = 'an account version follows the latest revision';
    end if;
    return new;
end;
$$;
revoke all on function gba.enforce_ledger_account_version() from public;
create trigger ledger_account_versions_next_revision before insert on gba.ledger_account_versions
    for each row execute function gba.enforce_ledger_account_version();

-- The latest event of a month decides whether it is closed.
create function gba.ledger_period_closed(tenant uuid, book uuid, month date) returns boolean
    language sql stable as $$
    select coalesce((
        select e.action = 'closed' from gba.ledger_period_events e
        where e.tenant_id = tenant and e.book_id = book and e.period = month
        order by e.sequence desc limit 1
    ), false);
$$;
revoke all on function gba.ledger_period_closed(uuid, uuid, date) from public;
grant execute on function gba.ledger_period_closed(uuid, uuid, date) to gba_runtime;

-- An entry needs a configured book, a date from the accounting start, an open month
-- and, for a reversal, an original of the same book and currency that is not itself
-- a reversal. The posting lock orders it against closing.
create function gba.enforce_journal_entry() returns trigger
    language plpgsql as $$
declare
    book gba.ledger_book_versions%rowtype;
    original gba.journal_entries%rowtype;
begin
    perform gba.lock_ledger(new.tenant_id);
    select * into book from gba.ledger_book_versions v
     where v.tenant_id = new.tenant_id and v.book_id = new.book_id
     order by v.revision desc limit 1;
    if book.revision is null or new.entry_date < book.accounting_start then
        raise exception using errcode = 'check_violation',
            message = 'an entry needs a configured book and a date from its accounting start';
    end if;
    if gba.ledger_period_closed(new.tenant_id, new.book_id,
                                date_trunc('month', new.entry_date::timestamp)::date) then
        raise exception using errcode = 'check_violation',
            message = 'the period of this entry is closed';
    end if;
    if new.reverses_entry_id is not null then
        select * into original from gba.journal_entries o
         where o.tenant_id = new.tenant_id and o.id = new.reverses_entry_id;
        if original.id is null or original.book_id <> new.book_id
           or original.currency <> new.currency or original.source_kind = 'reversal'
           or new.entry_date < original.entry_date then
            raise exception using errcode = 'check_violation',
                message = 'a reversal follows an original entry of the same book and currency';
        end if;
    end if;
    return new;
end;
$$;
revoke all on function gba.enforce_journal_entry() from public;
create trigger journal_entries_check before insert on gba.journal_entries
    for each row execute function gba.enforce_journal_entry();

-- Lines are written with their entry, to an open account of the same book. A
-- reversal may name an account archived since: it must mirror its original exactly.
create function gba.enforce_journal_line() returns trigger
    language plpgsql as $$
declare
    entry gba.journal_entries%rowtype;
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
        raise exception using errcode = 'check_violation',
            message = 'a line needs an open account of the book';
    end if;
    return new;
end;
$$;
revoke all on function gba.enforce_journal_line() from public;
create trigger journal_lines_check before insert on gba.journal_lines
    for each row execute function gba.enforce_journal_line();

-- At commit: at least two lines, debits equal credits, and a reversal mirrors its
-- original exactly (same accounts and amounts, opposite sides).
create function gba.check_journal_balance() returns trigger
    language plpgsql as $$
declare
    lines integer;
    balance numeric;
    entry gba.journal_entries%rowtype;
begin
    if tg_table_name = 'journal_entries' then
        entry := new;
    else
        select * into entry from gba.journal_entries e
         where e.tenant_id = new.tenant_id and e.id = new.entry_id;
    end if;
    select count(*), coalesce(sum(case l.side when 'debit' then l.amount_minor
                                               else -l.amount_minor end), 0)
      into lines, balance
      from gba.journal_lines l
     where l.tenant_id = entry.tenant_id and l.entry_id = entry.id;
    if lines < 2 or balance <> 0 then
        raise exception using errcode = 'check_violation',
            message = 'a journal entry needs at least two lines and balanced debits and credits';
    end if;
    if entry.reverses_entry_id is not null and exists (
        (select l.account_id, case l.side when 'debit' then 'credit' else 'debit' end,
                l.amount_minor
           from gba.journal_lines l
          where l.tenant_id = entry.tenant_id and l.entry_id = entry.reverses_entry_id
         except all
         select r.account_id, r.side, r.amount_minor from gba.journal_lines r
          where r.tenant_id = entry.tenant_id and r.entry_id = entry.id)
        union all
        (select r.account_id, r.side, r.amount_minor from gba.journal_lines r
          where r.tenant_id = entry.tenant_id and r.entry_id = entry.id
         except all
         select l.account_id, case l.side when 'debit' then 'credit' else 'debit' end,
                l.amount_minor
           from gba.journal_lines l
          where l.tenant_id = entry.tenant_id and l.entry_id = entry.reverses_entry_id)
    ) then
        raise exception using errcode = 'check_violation',
            message = 'a reversal mirrors its original entry exactly';
    end if;
    return null;
end;
$$;
revoke all on function gba.check_journal_balance() from public;
create constraint trigger journal_entries_balanced after insert on gba.journal_entries
    deferrable initially deferred
    for each row execute function gba.check_journal_balance();
-- An early SET CONSTRAINTS must not let later line inserts evade the final check.
create constraint trigger journal_lines_balanced after insert on gba.journal_lines
    deferrable initially deferred
    for each row execute function gba.check_journal_balance();

-- Period events alternate, starting with a close.
create function gba.enforce_ledger_period_event() returns trigger
    language plpgsql as $$
declare
    last_sequence integer;
    last_action text;
begin
    perform gba.lock_ledger(new.tenant_id);
    select e.sequence, e.action into last_sequence, last_action
      from gba.ledger_period_events e
     where e.tenant_id = new.tenant_id and e.book_id = new.book_id and e.period = new.period
     order by e.sequence desc limit 1;
    if new.sequence <> coalesce(last_sequence, 0) + 1
       or (new.action = 'closed' and last_action = 'closed')
       or (new.action = 'reopened' and last_action is distinct from 'closed') then
        raise exception using errcode = 'check_violation',
            message = 'invalid period change';
    end if;
    return new;
end;
$$;
revoke all on function gba.enforce_ledger_period_event() from public;
create trigger ledger_period_events_next before insert on gba.ledger_period_events
    for each row execute function gba.enforce_ledger_period_event();

create trigger ledger_books_require_module before insert on gba.ledger_books
    for each row execute function gba.require_enabled_module('finance');
create trigger ledger_book_versions_require_module before insert on gba.ledger_book_versions
    for each row execute function gba.require_enabled_module('finance');
create trigger ledger_accounts_require_module before insert on gba.ledger_accounts
    for each row execute function gba.require_enabled_module('finance');
create trigger ledger_account_versions_require_module
    before insert on gba.ledger_account_versions
    for each row execute function gba.require_enabled_module('finance');
create trigger journal_entries_require_module before insert on gba.journal_entries
    for each row execute function gba.require_enabled_module('finance');
create trigger journal_lines_require_module before insert on gba.journal_lines
    for each row execute function gba.require_enabled_module('finance');
create trigger ledger_period_events_require_module before insert on gba.ledger_period_events
    for each row execute function gba.require_enabled_module('finance');

-- Permanent cancellation of an unresolved operation prevents a delayed original
-- from arriving after recovery. Unlike ordinary receipts these rows never expire.
-- Recovery/cancellation remains available when finance is disabled; it creates no
-- book, account, financial entry or period event.
create table gba.ledger_command_cancellations (
    tenant_id uuid not null references gba.tenants (id),
    actor_key text not null check (actor_key ~ '^user:[0-9a-f-]{36}$'),
    operation text not null check (operation in ('business.ledger.book','business.ledger.account',
        'business.ledger.entry','business.ledger.reverse','business.ledger.close','business.ledger.reopen')),
    idempotency_key text not null check (idempotency_key ~ '^[A-Za-z0-9._:-]{8,255}$'),
    book_id uuid not null,
    cancelled_by uuid not null references gba.users (id),
    check (actor_key = 'user:' || cancelled_by::text),
    cancelled_at timestamptz not null default now(),
    primary key (tenant_id, actor_key, operation, idempotency_key)
);
alter table gba.ledger_command_cancellations enable row level security;
alter table gba.ledger_command_cancellations force row level security;
create policy ledger_command_cancellations_tenant_isolation on gba.ledger_command_cancellations
    using (tenant_id=gba.current_tenant_id()) with check (tenant_id=gba.current_tenant_id());
revoke all on gba.ledger_command_cancellations from public;
grant select on gba.ledger_command_cancellations to gba_runtime;
grant insert (tenant_id,actor_key,operation,idempotency_key,book_id,cancelled_by)
    on gba.ledger_command_cancellations to gba_runtime;
create trigger ledger_command_cancellations_immutable before update or delete
    on gba.ledger_command_cancellations for each row execute function gba.reject_ledger_mutation();

-- Ledger branch scope: reusable separately when restoring a damaged boundary in tests.
create policy ledger_command_cancellations_unrestricted_scope on gba.ledger_command_cancellations
    as restrictive to gba_runtime
    using (gba.current_location_id() is null) with check (gba.current_location_id() is null);
create policy ledger_books_unrestricted_scope on gba.ledger_books
    as restrictive to gba_runtime
    using (gba.current_location_id() is null) with check (gba.current_location_id() is null);
create policy ledger_book_versions_unrestricted_scope on gba.ledger_book_versions
    as restrictive to gba_runtime
    using (gba.current_location_id() is null) with check (gba.current_location_id() is null);
create policy ledger_accounts_unrestricted_scope on gba.ledger_accounts
    as restrictive to gba_runtime
    using (gba.current_location_id() is null) with check (gba.current_location_id() is null);
create policy ledger_account_versions_unrestricted_scope on gba.ledger_account_versions
    as restrictive to gba_runtime
    using (gba.current_location_id() is null) with check (gba.current_location_id() is null);
create policy journal_entries_unrestricted_scope on gba.journal_entries
    as restrictive to gba_runtime
    using (gba.current_location_id() is null) with check (gba.current_location_id() is null);
create policy journal_lines_unrestricted_scope on gba.journal_lines
    as restrictive to gba_runtime
    using (gba.current_location_id() is null) with check (gba.current_location_id() is null);
create policy ledger_period_events_unrestricted_scope on gba.ledger_period_events
    as restrictive to gba_runtime
    using (gba.current_location_id() is null) with check (gba.current_location_id() is null);
