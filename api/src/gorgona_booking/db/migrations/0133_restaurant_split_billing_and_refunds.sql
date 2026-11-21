-- REST-01 Slice 4 (ADR-0037): check splitting with strict total conservation,
-- per-share FIN-03 invoicing and coordinated refunds. Invoker rights only.

create table gba.restaurant_check_splits (
    tenant_id uuid not null,
    check_id uuid not null,
    location_id uuid not null,
    split_mode text not null check (split_mode in ('by_items', 'by_amounts')),
    share_count smallint not null check (share_count between 1 and 20),
    total_minor bigint not null check (total_minor between 1 and 999999999999),
    recorded_by uuid not null references gba.users (id),
    recorded_at timestamptz not null default clock_timestamp(),
    creation_xid xid8 not null default pg_current_xact_id(),
    primary key (tenant_id, check_id),
    unique (tenant_id, check_id, location_id),
    foreign key (tenant_id, check_id, location_id)
        references gba.restaurant_checks (tenant_id, id, location_id)
);

create table gba.restaurant_check_split_shares (
    tenant_id uuid not null,
    check_id uuid not null,
    share_no smallint not null check (share_no between 1 and 20),
    location_id uuid not null,
    label text not null check (char_length(btrim(label)) between 1 and 120),
    counterparty_id uuid,
    amount_minor bigint not null check (amount_minor between 1 and 999999999999),
    primary key (tenant_id, check_id, share_no),
    unique (tenant_id, check_id, share_no, location_id),
    foreign key (tenant_id, check_id, location_id)
        references gba.restaurant_check_splits (tenant_id, check_id, location_id),
    constraint restaurant_split_shares_counterparty_fk
        foreign key (tenant_id, counterparty_id) references gba.counterparties (tenant_id, id)
);

create table gba.restaurant_check_split_share_lines (
    tenant_id uuid not null,
    check_id uuid not null,
    share_no smallint not null check (share_no between 1 and 20),
    check_line_id uuid not null,
    location_id uuid not null,
    primary key (tenant_id, check_id, check_line_id),
    foreign key (tenant_id, check_id, share_no, location_id)
        references gba.restaurant_check_split_shares (tenant_id, check_id, share_no, location_id),
    foreign key (tenant_id, check_line_id, location_id)
        references gba.restaurant_check_lines (tenant_id, id, location_id)
);
create index restaurant_split_share_lines_share_idx
    on gba.restaurant_check_split_share_lines (tenant_id, check_id, share_no);

create table gba.restaurant_check_bills (
    tenant_id uuid not null,
    check_id uuid not null,
    share_no smallint not null check (share_no between 1 and 20),
    location_id uuid not null,
    counterparty_id uuid not null,
    amount_minor bigint not null check (amount_minor between 1 and 999999999999),
    book_id uuid not null,
    invoice_document_id uuid not null,
    billed_by uuid not null references gba.users (id),
    billed_at timestamptz not null default clock_timestamp(),
    primary key (tenant_id, check_id, share_no),
    unique (tenant_id, check_id, share_no, location_id),
    unique (tenant_id, book_id, invoice_document_id),
    foreign key (tenant_id, check_id, share_no, location_id)
        references gba.restaurant_check_split_shares (tenant_id, check_id, share_no, location_id),
    foreign key (tenant_id, counterparty_id) references gba.counterparties (tenant_id, id),
    foreign key (tenant_id, book_id, invoice_document_id)
        references gba.financial_documents (tenant_id, book_id, id)
);

create table gba.restaurant_check_refunds (
    tenant_id uuid not null,
    check_id uuid not null,
    number integer not null check (number >= 1),
    share_no smallint not null check (share_no between 1 and 20),
    location_id uuid not null,
    returned_line_id uuid,
    amount_minor bigint not null check (amount_minor between 1 and 999999999999),
    method text not null check (method in ('credit', 'external')),
    reason text not null check (char_length(btrim(reason)) between 1 and 500),
    reference text check (reference is null or char_length(btrim(reference)) between 1 and 120),
    refunded_at timestamptz,
    book_id uuid,
    credit_document_id uuid,
    recorded_by uuid not null references gba.users (id),
    recorded_at timestamptz not null default clock_timestamp(),
    primary key (tenant_id, check_id, number),
    foreign key (tenant_id, check_id, share_no, location_id)
        references gba.restaurant_check_bills (tenant_id, check_id, share_no, location_id),
    foreign key (tenant_id, returned_line_id, location_id)
        references gba.restaurant_check_lines (tenant_id, id, location_id),
    foreign key (tenant_id, book_id, credit_document_id)
        references gba.financial_documents (tenant_id, book_id, id),
    constraint restaurant_check_refunds_fields_check check (
        (method = 'credit') = (book_id is not null and credit_document_id is not null)
        and (method = 'external') = (reference is not null and refunded_at is not null)
    ),
    constraint restaurant_check_refunds_time_check
        check (refunded_at is null or refunded_at <= recorded_at)
);
create unique index restaurant_check_refunds_credit_uidx
    on gba.restaurant_check_refunds (tenant_id, book_id, credit_document_id)
    where credit_document_id is not null;

-- Prevent modifying check lines after the check has been split.
create or replace function gba.guard_restaurant_check_line() returns trigger language plpgsql as $$
declare
    chk record;
    rev_currency text;
begin
    if tg_op = 'DELETE' then
        raise exception using errcode = '23514', message = 'check lines are kept';
    end if;
    if exists (
        select 1 from gba.restaurant_check_consumptions c
        where c.tenant_id = new.tenant_id and c.check_id = new.check_id
    ) then
        raise exception using errcode = '23514',
            message = 'check lines cannot change after ingredient write-off is posted';
    end if;
    if exists (
        select 1 from gba.restaurant_check_splits s
        where s.tenant_id = new.tenant_id and s.check_id = new.check_id
    ) then
        raise exception using errcode = '23514',
            message = 'check lines cannot change after the check is split';
    end if;
    if tg_op = 'INSERT' then
        if new.status <> 'draft' then
            raise exception using errcode = '23514',
                message = 'a new check line starts in draft state';
        end if;
        select status, currency into strict chk
        from gba.restaurant_checks
        where tenant_id = new.tenant_id and id = new.check_id;
        if chk.status <> 'open' then
            raise exception using errcode = '23514',
                message = 'lines can only be added to an open check';
        end if;
        select currency into strict rev_currency
        from gba.restaurant_menu_item_revisions
        where tenant_id = new.tenant_id
          and menu_item_id = new.menu_item_id
          and revision = new.menu_item_revision;
        if rev_currency <> chk.currency then
            raise exception using errcode = '23514',
                message = 'menu item currency must match check currency';
        end if;
        return new;
    end if;
    if (old.tenant_id, old.id, old.check_id, old.location_id, old.line_no,
        old.menu_item_id, old.menu_item_revision, old.recipe_revision,
        old.item_code, old.item_name, old.kitchen_station, old.quantity,
        old.base_price_minor, old.modifiers_delta_minor, old.unit_price_minor,
        old.line_total_minor, old.note, old.creation_xid)
       is distinct from (new.tenant_id, new.id, new.check_id, new.location_id, new.line_no,
                         new.menu_item_id, new.menu_item_revision, new.recipe_revision,
                         new.item_code, new.item_name, new.kitchen_station, new.quantity,
                         new.base_price_minor, new.modifiers_delta_minor, new.unit_price_minor,
                         new.line_total_minor, new.note, new.creation_xid) then
        raise exception using errcode = '23514',
            message = 'check line commercial snapshot is immutable';
    end if;
    if not (
        (old.status = 'draft' and new.status in ('fired', 'voided'))
        or (old.status = 'fired' and new.status in ('served', 'voided'))
        or (old.status = 'served' and new.status = 'voided')
    ) then
        raise exception using errcode = '23514',
            message = 'invalid check line status transition';
    end if;
    if old.kitchen_ticket_id is not null and new.kitchen_ticket_id is distinct from old.kitchen_ticket_id then
        raise exception using errcode = '23514',
            message = 'check line kitchen ticket cannot change once fired';
    end if;
    return new;
end;
$$;

create function gba.guard_restaurant_check_split() returns trigger language plpgsql as $$
declare
    chk record;
begin
    if tg_op <> 'INSERT' then
        raise exception using errcode = '23514', message = 'check splits are immutable';
    end if;
    select status, subtotal_minor into chk
    from gba.restaurant_checks
    where tenant_id = new.tenant_id and id = new.check_id
    for update;
    if not found then
        return new;
    end if;
    if chk.status = 'voided' then
        raise exception using errcode = '23514', message = 'cannot split a voided check';
    end if;
    if chk.subtotal_minor <= 0 or new.total_minor <> chk.subtotal_minor then
        raise exception using errcode = '23514',
            message = 'split total must equal check subtotal';
    end if;
    if exists (
        select 1 from gba.restaurant_check_lines l
        where l.tenant_id = new.tenant_id and l.check_id = new.check_id and l.status = 'draft'
    ) then
        raise exception using errcode = '23514',
            message = 'fire or void all draft lines before splitting the check';
    end if;
    return new;
end;
$$;
revoke all on function gba.guard_restaurant_check_split() from public;
create trigger restaurant_check_splits_guard
    before insert or update or delete on gba.restaurant_check_splits
    for each row execute function gba.guard_restaurant_check_split();

create function gba.guard_restaurant_split_share() returns trigger language plpgsql as $$
begin
    if tg_op <> 'INSERT' then
        raise exception using errcode = '23514', message = 'check split shares are immutable';
    end if;
    perform 1 from gba.restaurant_check_splits s
    where s.tenant_id = new.tenant_id and s.check_id = new.check_id
      and s.location_id = new.location_id
      and new.share_no <= s.share_count
      and s.creation_xid = pg_current_xact_id();
    if not found then
        raise exception using errcode = '23514',
            message = 'split shares are written with their check split';
    end if;
    return new;
end;
$$;
revoke all on function gba.guard_restaurant_split_share() from public;
create trigger restaurant_check_split_shares_guard
    before insert or update or delete on gba.restaurant_check_split_shares
    for each row execute function gba.guard_restaurant_split_share();

create function gba.guard_restaurant_split_share_line() returns trigger language plpgsql as $$
declare
    sp_mode text;
    line_row record;
begin
    if tg_op <> 'INSERT' then
        raise exception using errcode = '23514', message = 'split share lines are immutable';
    end if;
    select s.split_mode into sp_mode
    from gba.restaurant_check_splits s
    where s.tenant_id = new.tenant_id and s.check_id = new.check_id
      and s.location_id = new.location_id
      and s.creation_xid = pg_current_xact_id();
    if sp_mode is null or sp_mode <> 'by_items' then
        raise exception using errcode = '23514',
            message = 'share lines are only written with a by_items split';
    end if;
    select check_id, status into strict line_row
    from gba.restaurant_check_lines
    where tenant_id = new.tenant_id and id = new.check_line_id;
    if line_row.check_id <> new.check_id or line_row.status not in ('fired', 'served') then
        raise exception using errcode = '23514',
            message = 'split share line must reference an active line of this check';
    end if;
    return new;
end;
$$;
revoke all on function gba.guard_restaurant_split_share_line() from public;
create trigger restaurant_check_split_share_lines_guard
    before insert or update or delete on gba.restaurant_check_split_share_lines
    for each row execute function gba.guard_restaurant_split_share_line();

create function gba.check_restaurant_split_conserved() returns trigger language plpgsql as $$
declare
    cnt integer;
    min_no integer;
    max_no integer;
    sum_amt bigint;
    active_lines integer;
    assigned_lines integer;
begin
    select count(*), min(share_no), max(share_no), coalesce(sum(amount_minor), 0)
      into cnt, min_no, max_no, sum_amt
    from gba.restaurant_check_split_shares
    where tenant_id = new.tenant_id and check_id = new.check_id;

    if cnt <> new.share_count or min_no <> 1 or max_no <> new.share_count then
        raise exception using errcode = '23514',
            message = 'check split shares must be numbered 1..share_count';
    end if;
    if sum_amt <> new.total_minor then
        raise exception using errcode = '23514',
            message = 'sum of split share amounts must equal check subtotal';
    end if;

    if new.split_mode = 'by_items' then
        select count(*) into active_lines
        from gba.restaurant_check_lines
        where tenant_id = new.tenant_id and check_id = new.check_id
          and status in ('fired', 'served');
        select count(*) into assigned_lines
        from gba.restaurant_check_split_share_lines
        where tenant_id = new.tenant_id and check_id = new.check_id;
        if assigned_lines <> active_lines then
            raise exception using errcode = '23514',
                message = 'by_items split must assign every active line exactly once';
        end if;
        if exists (
            select 1
            from gba.restaurant_check_split_shares sh
            where sh.tenant_id = new.tenant_id and sh.check_id = new.check_id
              and sh.amount_minor <> (
                  select coalesce(sum(l.line_total_minor), 0)
                  from gba.restaurant_check_split_share_lines sl
                  join gba.restaurant_check_lines l
                    on l.tenant_id = sl.tenant_id and l.id = sl.check_line_id
                  where sl.tenant_id = sh.tenant_id
                    and sl.check_id = sh.check_id
                    and sl.share_no = sh.share_no
              )
        ) then
            raise exception using errcode = '23514',
                message = 'each by_items share amount must equal the sum of its assigned lines';
        end if;
    end if;
    return null;
end;
$$;
revoke all on function gba.check_restaurant_split_conserved() from public;
create constraint trigger restaurant_check_splits_conserved
    after insert on gba.restaurant_check_splits
    deferrable initially deferred for each row
    execute function gba.check_restaurant_split_conserved();

create function gba.guard_restaurant_check_bill() returns trigger language plpgsql as $$
declare
    chk_currency text;
    share_amt bigint;
begin
    if tg_op <> 'INSERT' then
        raise exception using errcode = '23514', message = 'check bills are immutable';
    end if;
    select currency into strict chk_currency
    from gba.restaurant_checks
    where tenant_id = new.tenant_id and id = new.check_id;

    select amount_minor into strict share_amt
    from gba.restaurant_check_split_shares
    where tenant_id = new.tenant_id and check_id = new.check_id and share_no = new.share_no;

    if new.amount_minor <> share_amt then
        raise exception using errcode = '23514',
            message = 'bill amount must equal split share amount';
    end if;
    if not exists (
        select 1
        from gba.financial_documents d
        join gba.financial_document_versions v
          on v.tenant_id = d.tenant_id and v.book_id = d.book_id and v.document_id = d.id
        where d.tenant_id = new.tenant_id and d.book_id = new.book_id
          and d.id = new.invoice_document_id and d.kind = 'invoice'
          and v.revision = (
              select max(x.revision) from gba.financial_document_versions x
              where x.tenant_id = d.tenant_id and x.book_id = d.book_id and x.document_id = d.id
          )
          and v.direction = 'receivable'
          and v.counterparty_id = new.counterparty_id
          and v.currency = chk_currency
          and v.principal_minor = new.amount_minor
    ) then
        raise exception using errcode = '23514',
            message = 'bill must reference the receivable FIN-03 invoice for this share';
    end if;
    return new;
end;
$$;
revoke all on function gba.guard_restaurant_check_bill() from public;
create trigger restaurant_check_bills_guard
    before insert or update or delete on gba.restaurant_check_bills
    for each row execute function gba.guard_restaurant_check_bill();

create function gba.guard_restaurant_check_refund() returns trigger language plpgsql as $$
declare
    bill record;
    latest_num integer;
    share_refunded bigint;
    line_chk uuid;
begin
    if tg_op <> 'INSERT' then
        raise exception using errcode = '23514', message = 'check refunds are immutable';
    end if;
    perform 1 from gba.restaurant_checks c
    where c.tenant_id = new.tenant_id and c.id = new.check_id
    for update;

    select coalesce(max(r.number), 0) into latest_num
    from gba.restaurant_check_refunds r
    where r.tenant_id = new.tenant_id and r.check_id = new.check_id;
    if new.number <> latest_num + 1 then
        raise exception using errcode = '23514',
            message = 'check refunds are numbered 1, 2, 3 per check';
    end if;

    select amount_minor, book_id, invoice_document_id into strict bill
    from gba.restaurant_check_bills
    where tenant_id = new.tenant_id and check_id = new.check_id and share_no = new.share_no;

    if new.returned_line_id is not null then
        select check_id into strict line_chk
        from gba.restaurant_check_lines
        where tenant_id = new.tenant_id and id = new.returned_line_id;
        if line_chk <> new.check_id then
            raise exception using errcode = '23514',
                message = 'returned line must belong to this check';
        end if;
    end if;

    select coalesce(sum(r.amount_minor), 0) into share_refunded
    from gba.restaurant_check_refunds r
    where r.tenant_id = new.tenant_id
      and r.check_id = new.check_id
      and r.share_no = new.share_no
      and (
          r.method = 'external'
          or not gba.credit_voided(r.tenant_id, r.book_id, r.credit_document_id)
      );
    if share_refunded + new.amount_minor > bill.amount_minor then
        raise exception using errcode = '23514',
            constraint = 'restaurant_check_refunds_ceiling_check',
            message = 'refunds for a share cannot exceed the billed share amount';
    end if;

    if new.method = 'credit' and not exists (
        select 1
        from gba.financial_documents d
        join gba.financial_document_versions v
          on v.tenant_id = d.tenant_id and v.book_id = d.book_id and v.document_id = d.id
        join gba.financial_obligations o
          on o.tenant_id = v.tenant_id and o.book_id = v.book_id
         and o.id = v.credited_obligation_id
        where d.tenant_id = new.tenant_id and d.book_id = new.book_id
          and d.id = new.credit_document_id and d.kind = 'credit_note'
          and v.revision = (
              select max(x.revision) from gba.financial_document_versions x
              where x.tenant_id = d.tenant_id and x.book_id = d.book_id and x.document_id = d.id
          )
          and v.principal_minor = new.amount_minor
          and o.source_kind = 'invoice'
          and o.book_id = bill.book_id
          and o.source_id = bill.invoice_document_id
    ) then
        raise exception using errcode = '23514',
            message = 'credit refund must reference a FIN-03 credit note against this share invoice';
    end if;
    return new;
end;
$$;
revoke all on function gba.guard_restaurant_check_refund() from public;
create trigger restaurant_check_refunds_guard
    before insert or update or delete on gba.restaurant_check_refunds
    for each row execute function gba.guard_restaurant_check_refund();

-- RLS, module write gates and minimal runtime privileges
alter table gba.restaurant_check_splits enable row level security;
alter table gba.restaurant_check_splits force row level security;
create policy restaurant_check_splits_tenant_isolation on gba.restaurant_check_splits
    using (tenant_id = gba.current_tenant_id()) with check (tenant_id = gba.current_tenant_id());
grant select, insert on gba.restaurant_check_splits to gba_runtime;
create trigger restaurant_check_splits_require_module before insert on gba.restaurant_check_splits
    for each row execute function gba.require_enabled_module('restaurant');

alter table gba.restaurant_check_split_shares enable row level security;
alter table gba.restaurant_check_split_shares force row level security;
create policy restaurant_check_split_shares_tenant_isolation on gba.restaurant_check_split_shares
    using (tenant_id = gba.current_tenant_id()) with check (tenant_id = gba.current_tenant_id());
grant select, insert on gba.restaurant_check_split_shares to gba_runtime;

alter table gba.restaurant_check_split_share_lines enable row level security;
alter table gba.restaurant_check_split_share_lines force row level security;
create policy restaurant_check_split_share_lines_tenant_isolation
    on gba.restaurant_check_split_share_lines
    using (tenant_id = gba.current_tenant_id()) with check (tenant_id = gba.current_tenant_id());
grant select, insert on gba.restaurant_check_split_share_lines to gba_runtime;

alter table gba.restaurant_check_bills enable row level security;
alter table gba.restaurant_check_bills force row level security;
create policy restaurant_check_bills_tenant_isolation on gba.restaurant_check_bills
    using (tenant_id = gba.current_tenant_id()) with check (tenant_id = gba.current_tenant_id());
grant select, insert on gba.restaurant_check_bills to gba_runtime;
create trigger restaurant_check_bills_require_module before insert on gba.restaurant_check_bills
    for each row execute function gba.require_enabled_module('restaurant');

alter table gba.restaurant_check_refunds enable row level security;
alter table gba.restaurant_check_refunds force row level security;
create policy restaurant_check_refunds_tenant_isolation on gba.restaurant_check_refunds
    using (tenant_id = gba.current_tenant_id()) with check (tenant_id = gba.current_tenant_id());
grant select, insert on gba.restaurant_check_refunds to gba_runtime;
create trigger restaurant_check_refunds_require_module before insert on gba.restaurant_check_refunds
    for each row execute function gba.require_enabled_module('restaurant');

-- Restaurant billing branch scope:
create policy restaurant_check_splits_location_scope on gba.restaurant_check_splits as restrictive to gba_runtime
    using (gba.current_location_id() is null or location_id = gba.current_location_id())
    with check (gba.current_location_id() is null or location_id = gba.current_location_id());

create policy restaurant_check_split_shares_location_scope on gba.restaurant_check_split_shares as restrictive to gba_runtime
    using (gba.current_location_id() is null or location_id = gba.current_location_id())
    with check (gba.current_location_id() is null or location_id = gba.current_location_id());

create policy restaurant_check_split_share_lines_location_scope on gba.restaurant_check_split_share_lines as restrictive to gba_runtime
    using (gba.current_location_id() is null or location_id = gba.current_location_id())
    with check (gba.current_location_id() is null or location_id = gba.current_location_id());

create policy restaurant_check_bills_location_scope on gba.restaurant_check_bills as restrictive to gba_runtime
    using (gba.current_location_id() is null or location_id = gba.current_location_id())
    with check (gba.current_location_id() is null or location_id = gba.current_location_id());

create policy restaurant_check_refunds_location_scope on gba.restaurant_check_refunds as restrictive to gba_runtime
    using (gba.current_location_id() is null or location_id = gba.current_location_id())
    with check (gba.current_location_id() is null or location_id = gba.current_location_id());
