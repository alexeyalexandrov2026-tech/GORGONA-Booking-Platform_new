-- J2 / ADR-0026: accounts of materials for a book and receipts with amounts.
-- Forward only. A receipt is one posted document: its lines, movements, balances, cost
-- and one `stock` journal entry in the book of its owner are written in one transaction
-- and never change. Quantities are visible by branch; amounts, cost and the link to the
-- book are visible to company-wide members only, like the ledger itself.
-- A balance and a cost row are running totals: at commit each must equal the sum of its
-- movements, so nothing but a movement of a posted document can change them.

-- A document names its place together with the branch of that place.
alter table gba.stock_places add constraint stock_places_branch_key unique (tenant_id, id, location_id);

-- The journal learns one more origin; package H keeps its own origins and guards.
alter table gba.journal_entries drop constraint journal_entries_source_kind_check;
alter table gba.journal_entries add constraint journal_entries_source_kind_check
    check (source_kind in ('manual', 'opening', 'reversal', 'invoice', 'accrual', 'payment', 'credit', 'payment_correction', 'credit_void', 'stock'));

-- Seven accounts of one book, chosen by a person. The inventory account differs from the rest.
create table gba.stock_posting_rules (
    tenant_id uuid not null references gba.tenants(id),
    book_id uuid not null,
    revision integer not null constraint stock_posting_rules_revision_check check (revision > 0),
    inventory_account_id uuid not null,
    receipt_account_id uuid not null,
    opening_account_id uuid not null,
    surplus_account_id uuid not null,
    consumption_account_id uuid not null,
    loss_account_id uuid not null,
    difference_account_id uuid not null,
    created_by uuid not null references gba.users(id),
    created_at timestamptz not null default now(),
    primary key (tenant_id, book_id, revision),
    constraint stock_posting_rules_distinct_check check (inventory_account_id <> receipt_account_id and inventory_account_id <> opening_account_id and inventory_account_id <> surplus_account_id and inventory_account_id <> consumption_account_id and inventory_account_id <> loss_account_id and inventory_account_id <> difference_account_id),
    foreign key (tenant_id, book_id) references gba.ledger_books(tenant_id, id),
    foreign key (tenant_id, book_id, inventory_account_id) references gba.ledger_accounts(tenant_id, book_id, id),
    foreign key (tenant_id, book_id, receipt_account_id) references gba.ledger_accounts(tenant_id, book_id, id),
    foreign key (tenant_id, book_id, opening_account_id) references gba.ledger_accounts(tenant_id, book_id, id),
    foreign key (tenant_id, book_id, surplus_account_id) references gba.ledger_accounts(tenant_id, book_id, id),
    foreign key (tenant_id, book_id, consumption_account_id) references gba.ledger_accounts(tenant_id, book_id, id),
    foreign key (tenant_id, book_id, loss_account_id) references gba.ledger_accounts(tenant_id, book_id, id),
    foreign key (tenant_id, book_id, difference_account_id) references gba.ledger_accounts(tenant_id, book_id, id)
);
-- A posted document. Later slices add the other kinds and their reasons.
create table gba.stock_documents (
    tenant_id uuid not null references gba.tenants(id),
    id uuid not null,
    kind text not null constraint stock_documents_kind_check check (kind = 'receipt'),
    reason text not null constraint stock_documents_reason_check check (reason in ('purchase', 'opening_balance', 'surplus')),
    legal_entity_id uuid not null,
    place_id uuid not null,
    location_id uuid not null,
    document_date date not null,
    supplier_id uuid,
    supplier_document text constraint stock_documents_number_check check (length(supplier_document) between 1 and 64 and supplier_document = btrim(supplier_document) and supplier_document !~ '[[:cntrl:]]'),
    line_count smallint not null constraint stock_documents_lines_check check (line_count between 1 and 100),
    created_by uuid not null references gba.users(id),
    created_at timestamptz not null default now(),
    created_transaction xid8 not null default pg_current_xact_id(),
    primary key (tenant_id, id),
    unique (tenant_id, id, location_id),
    constraint stock_documents_supplier_check check ((supplier_id is null and supplier_document is null) or reason = 'purchase'),
    foreign key (tenant_id, legal_entity_id) references gba.legal_entities(tenant_id, id),
    foreign key (tenant_id, place_id, location_id) references gba.stock_places(tenant_id, id, location_id),
    foreign key (tenant_id, supplier_id) references gba.counterparties(tenant_id, id)
);
-- A quantity is a whole count of the smallest fraction of the material's unit.
create table gba.stock_document_lines (
    tenant_id uuid not null references gba.tenants(id),
    document_id uuid not null,
    line_no smallint not null constraint stock_document_lines_number_check check (line_no between 1 and 100),
    location_id uuid not null,
    item_id uuid not null,
    quantity bigint not null constraint stock_document_lines_quantity_check check (quantity between 1 and 999999999999),
    primary key (tenant_id, document_id, line_no),
    foreign key (tenant_id, document_id, location_id) references gba.stock_documents(tenant_id, id, location_id),
    foreign key (tenant_id, item_id) references gba.stock_items(tenant_id, id)
);
-- The key refuses a second movement of one line in one direction.
create table gba.stock_movements (
    tenant_id uuid not null references gba.tenants(id),
    document_id uuid not null,
    line_no smallint not null,
    direction text not null constraint stock_movements_direction_check check (direction in ('in', 'out')),
    location_id uuid not null,
    place_id uuid not null,
    item_id uuid not null,
    legal_entity_id uuid not null,
    quantity bigint not null constraint stock_movements_quantity_check check (quantity between 1 and 999999999999),
    created_at timestamptz not null default now(),
    primary key (tenant_id, document_id, line_no, direction),
    foreign key (tenant_id, document_id, line_no) references gba.stock_document_lines(tenant_id, document_id, line_no),
    foreign key (tenant_id, place_id, location_id) references gba.stock_places(tenant_id, id, location_id),
    foreign key (tenant_id, item_id) references gba.stock_items(tenant_id, id),
    foreign key (tenant_id, legal_entity_id) references gba.legal_entities(tenant_id, id)
);
create index stock_movements_balance on gba.stock_movements (tenant_id, item_id, place_id, legal_entity_id);
-- What one legal entity holds of one material in one place. Never below zero.
create table gba.stock_balances (
    tenant_id uuid not null references gba.tenants(id),
    item_id uuid not null,
    place_id uuid not null,
    legal_entity_id uuid not null,
    location_id uuid not null,
    quantity bigint not null constraint stock_balances_quantity_check check (quantity between 0 and 999999999999999),
    primary key (tenant_id, item_id, place_id, legal_entity_id),
    foreign key (tenant_id, item_id) references gba.stock_items(tenant_id, id),
    foreign key (tenant_id, place_id, location_id) references gba.stock_places(tenant_id, id, location_id),
    foreign key (tenant_id, legal_entity_id) references gba.legal_entities(tenant_id, id)
);
-- The money side of a document: its book, the rules it was posted with and its entry.
-- A zero total posts no entry.
create table gba.stock_document_postings (
    tenant_id uuid not null references gba.tenants(id),
    document_id uuid not null,
    book_id uuid not null,
    rule_revision integer not null,
    entry_id uuid,
    total_minor bigint not null constraint stock_document_postings_total_check check (total_minor between 0 and 999999999999999999),
    created_by uuid not null references gba.users(id),
    created_at timestamptz not null default now(),
    created_transaction xid8 not null default pg_current_xact_id(),
    primary key (tenant_id, document_id),
    constraint stock_document_postings_entry_check check ((entry_id is null) = (total_minor = 0)),
    foreign key (tenant_id, document_id) references gba.stock_documents(tenant_id, id),
    foreign key (tenant_id, book_id, rule_revision) references gba.stock_posting_rules(tenant_id, book_id, revision)
);
-- The value one line moves into or out of the inventory account, in minor units.
create table gba.stock_valuations (
    tenant_id uuid not null references gba.tenants(id),
    document_id uuid not null,
    line_no smallint not null,
    direction text not null constraint stock_valuations_direction_check check (direction in ('in', 'out')),
    legal_entity_id uuid not null,
    item_id uuid not null,
    quantity bigint not null constraint stock_valuations_quantity_check check (quantity between 1 and 999999999999),
    amount_minor bigint not null constraint stock_valuations_amount_check check (amount_minor between 0 and 999999999999999),
    primary key (tenant_id, document_id, line_no),
    foreign key (tenant_id, document_id, line_no) references gba.stock_document_lines(tenant_id, document_id, line_no),
    foreign key (tenant_id, document_id) references gba.stock_document_postings(tenant_id, document_id),
    foreign key (tenant_id, item_id) references gba.stock_items(tenant_id, id),
    foreign key (tenant_id, legal_entity_id) references gba.legal_entities(tenant_id, id)
);
create index stock_valuations_cost on gba.stock_valuations (tenant_id, legal_entity_id, item_id);
-- Moving average: the whole quantity and the whole value of a material of one legal entity.
create table gba.stock_costs (
    tenant_id uuid not null references gba.tenants(id),
    legal_entity_id uuid not null,
    item_id uuid not null,
    quantity bigint not null constraint stock_costs_quantity_check check (quantity between 0 and 999999999999999),
    value_minor bigint not null constraint stock_costs_value_check check (value_minor between 0 and 999999999999999999),
    primary key (tenant_id, legal_entity_id, item_id),
    constraint stock_costs_empty_check check (quantity > 0 or value_minor = 0),
    foreign key (tenant_id, legal_entity_id) references gba.legal_entities(tenant_id, id),
    foreign key (tenant_id, item_id) references gba.stock_items(tenant_id, id)
);

-- Rules are set by the authenticated company-wide owner or manager, under the posting
-- lock: open accounts of this book, an asset for inventory, an asset or an expense for
-- receipts (so a supplier's bill can use the same account). The inventory account is
-- fixed once a document is posted in the book.
create function gba.guard_stock_posting_rule() returns trigger language plpgsql as $$
declare latest gba.stock_posting_rules%rowtype;
begin
    perform 1 from gba.memberships m join gba.users u on u.id=m.user_id
     where m.tenant_id=new.tenant_id and m.user_id=new.created_by and m.status='active' and u.status='active'
       and m.role in ('owner','manager') and m.location_id is null
     for share of m;
    if not found or new.created_by is distinct from gba.current_user_id() then
        raise exception using errcode='42501', message='posting rules need their authenticated company-wide owner or manager';
    end if;
    perform gba.lock_ledger(new.tenant_id);
    select * into latest from gba.stock_posting_rules r
     where r.tenant_id=new.tenant_id and r.book_id=new.book_id order by r.revision desc limit 1;
    if new.revision <> coalesce(latest.revision,0)+1 then
        raise exception using errcode='GBS01', message='stale posting rules revision';
    end if;
    if exists (
        select 1 from unnest(array[new.inventory_account_id,new.receipt_account_id,new.opening_account_id,
            new.surplus_account_id,new.consumption_account_id,new.loss_account_id,new.difference_account_id])
            with ordinality as wanted(id, position)
        left join gba.ledger_accounts a on a.tenant_id=new.tenant_id and a.book_id=new.book_id and a.id=wanted.id
        left join lateral (select v.archived from gba.ledger_account_versions v
            where v.tenant_id=a.tenant_id and v.account_id=a.id order by v.revision desc limit 1) v on true
        where a.id is null or v.archived is not false
           or (wanted.position=1 and a.type<>'asset')
           or (wanted.position=2 and a.type not in ('asset','expense'))
    ) then
        raise exception using errcode='23514', message='posting rules need open accounts of the book';
    end if;
    if latest.revision is not null and new.inventory_account_id<>latest.inventory_account_id and exists (
        select 1 from gba.stock_document_postings p where p.tenant_id=new.tenant_id and p.book_id=new.book_id
    ) then
        raise exception using errcode='23514', message='the inventory account is fixed once a document is posted';
    end if;
    return new;
end;
$$;
-- A receipt changes the books: only the authenticated company-wide owner or manager
-- posts it, under the posting lock. Its place is open and its date is not in the future
-- of the branch. A supplier is an active counterparty with that role.
create function gba.guard_stock_document() returns trigger language plpgsql as $$
declare closed boolean; zone text;
begin
    perform 1 from gba.memberships m join gba.users u on u.id=m.user_id
     where m.tenant_id=new.tenant_id and m.user_id=new.created_by and m.status='active' and u.status='active'
       and m.role in ('owner','manager') and m.location_id is null
     for share of m;
    if not found or new.created_by is distinct from gba.current_user_id() or gba.current_location_id() is not null then
        raise exception using errcode='42501', message='a stock receipt needs its authenticated company-wide owner or manager';
    end if;
    perform gba.lock_ledger(new.tenant_id);
    perform 1 from gba.stock_places p where p.tenant_id=new.tenant_id and p.id=new.place_id for share;
    select v.archived into closed from gba.stock_place_versions v
     where v.tenant_id=new.tenant_id and v.place_id=new.place_id order by v.revision desc limit 1;
    if closed then
        raise exception using errcode='23514', message='an archived storage place takes no receipt';
    end if;
    select l.timezone into zone from gba.locations l where l.tenant_id=new.tenant_id and l.id=new.location_id;
    if new.document_date > (pg_catalog.now() at time zone coalesce(zone,'UTC'))::date then
        raise exception using errcode='23514', message='a stock document is not dated in the future of its branch';
    end if;
    if new.supplier_id is not null and not exists (
        select 1 from gba.counterparty_versions v
         where v.tenant_id=new.tenant_id and v.counterparty_id=new.supplier_id and v.state='active'
           and 'supplier'=any(v.roles)
           and v.revision=(select max(x.revision) from gba.counterparty_versions x
               where x.tenant_id=v.tenant_id and x.counterparty_id=v.counterparty_id)
    ) then
        raise exception using errcode='23514', message='a supplier is an active counterparty with the supplier role';
    end if;
    return new;
end;
$$;
-- Lines are written with their document. A receipt takes no archived material.
create function gba.guard_stock_document_line() returns trigger language plpgsql as $$
declare closed boolean;
begin
    if not exists (select 1 from gba.stock_documents d
        where d.tenant_id=new.tenant_id and d.id=new.document_id and d.location_id=new.location_id
          and new.line_no<=d.line_count and d.created_transaction=pg_catalog.pg_current_xact_id()) then
        raise exception using errcode='23514', message='stock lines are written with their document';
    end if;
    perform 1 from gba.stock_items s where s.tenant_id=new.tenant_id and s.id=new.item_id for share;
    select v.archived into closed from gba.stock_item_versions v
     where v.tenant_id=new.tenant_id and v.item_id=new.item_id order by v.revision desc limit 1;
    if closed then
        raise exception using errcode='23514', message='an archived material takes no receipt';
    end if;
    return new;
end;
$$;
-- A movement repeats its document line of the same transaction and moves the balance
-- under the lock of the balance row.
create function gba.apply_stock_movement() returns trigger language plpgsql as $$
declare line record;
begin
    if pg_catalog.current_setting('transaction_isolation')<>'read committed' then
        raise exception using errcode='40001', message='stock movements require read committed transactions';
    end if;
    select d.place_id,d.location_id,d.legal_entity_id,l.item_id,l.quantity into line
      from gba.stock_documents d join gba.stock_document_lines l
        on l.tenant_id=d.tenant_id and l.document_id=d.id
     where d.tenant_id=new.tenant_id and d.id=new.document_id and l.line_no=new.line_no
       and d.created_transaction=pg_catalog.pg_current_xact_id();
    if not found or new.direction<>'in' or new.place_id<>line.place_id or new.location_id<>line.location_id
       or new.legal_entity_id<>line.legal_entity_id or new.item_id<>line.item_id or new.quantity<>line.quantity then
        raise exception using errcode='23514', message='a stock movement repeats its document line';
    end if;
    insert into gba.stock_balances (tenant_id,item_id,place_id,legal_entity_id,location_id,quantity)
    values (new.tenant_id,new.item_id,new.place_id,new.legal_entity_id,new.location_id,new.quantity)
    on conflict (tenant_id,item_id,place_id,legal_entity_id)
    do update set quantity=gba.stock_balances.quantity+excluded.quantity;
    return new;
end;
$$;
create function gba.check_stock_balance() returns trigger language plpgsql as $$
declare moved numeric; held bigint;
begin
    select coalesce(sum(case m.direction when 'in' then m.quantity else -m.quantity end),0) into moved
      from gba.stock_movements m
     where m.tenant_id=new.tenant_id and m.item_id=new.item_id and m.place_id=new.place_id
       and m.legal_entity_id=new.legal_entity_id;
    select b.quantity into held from gba.stock_balances b
     where b.tenant_id=new.tenant_id and b.item_id=new.item_id and b.place_id=new.place_id
       and b.legal_entity_id=new.legal_entity_id;
    if held is distinct from moved then
        raise exception using errcode='23514', message='a stock balance equals the sum of its movements';
    end if;
    return null;
end;
$$;
-- The money side is written with its document: the book of the owner, its current rules,
-- a date from the accounting start in an open period.
create function gba.guard_stock_posting() returns trigger language plpgsql as $$
declare doc gba.stock_documents%rowtype; started date;
begin
    perform gba.lock_ledger(new.tenant_id);
    select * into doc from gba.stock_documents d
     where d.tenant_id=new.tenant_id and d.id=new.document_id
       and d.created_transaction=pg_catalog.pg_current_xact_id();
    if doc.id is null or new.created_by is distinct from doc.created_by then
        raise exception using errcode='23514', message='a stock posting is written with its document';
    end if;
    select v.accounting_start into started from gba.ledger_books b join gba.ledger_book_versions v
        on v.tenant_id=b.tenant_id and v.book_id=b.id
     where b.tenant_id=new.tenant_id and b.id=new.book_id and b.legal_entity_id=doc.legal_entity_id
     order by v.revision desc limit 1;
    if started is null then
        raise exception using errcode='23514', message='a stock document posts to the book of its owner';
    end if;
    if new.rule_revision is distinct from (select max(r.revision) from gba.stock_posting_rules r
        where r.tenant_id=new.tenant_id and r.book_id=new.book_id) then
        raise exception using errcode='23514', message='a stock document uses the current posting rules';
    end if;
    if doc.document_date<started then
        raise exception using errcode='23514', message='a stock document is dated from the accounting start';
    end if;
    if gba.ledger_period_closed(new.tenant_id,new.book_id,date_trunc('month',doc.document_date::timestamp)::date) then
        raise exception using errcode='23514', message='the period of this stock document is closed';
    end if;
    return new;
end;
$$;
-- A valuation repeats its line of a money document of the same transaction and moves
-- the cost of the material: a receipt adds its quantity and its amount.
create function gba.apply_stock_valuation() returns trigger language plpgsql as $$
declare line record;
begin
    perform gba.lock_ledger(new.tenant_id);
    select d.legal_entity_id,l.item_id,l.quantity into line
      from gba.stock_documents d
      join gba.stock_document_postings p on p.tenant_id=d.tenant_id and p.document_id=d.id
      join gba.stock_document_lines l on l.tenant_id=d.tenant_id and l.document_id=d.id
     where d.tenant_id=new.tenant_id and d.id=new.document_id and l.line_no=new.line_no
       and d.created_transaction=pg_catalog.pg_current_xact_id();
    if not found or new.direction<>'in' or new.legal_entity_id<>line.legal_entity_id
       or new.item_id<>line.item_id or new.quantity<>line.quantity then
        raise exception using errcode='23514', message='a stock valuation repeats its document line';
    end if;
    insert into gba.stock_costs (tenant_id,legal_entity_id,item_id,quantity,value_minor)
    values (new.tenant_id,new.legal_entity_id,new.item_id,new.quantity,new.amount_minor)
    on conflict (tenant_id,legal_entity_id,item_id)
    do update set quantity=gba.stock_costs.quantity+excluded.quantity,
                  value_minor=gba.stock_costs.value_minor+excluded.value_minor;
    return new;
end;
$$;
-- The cost row equals its valuations, and its quantity equals what the places hold.
create function gba.check_stock_cost() returns trigger language plpgsql as $$
declare valued_quantity numeric; valued_amount numeric; held gba.stock_costs%rowtype; placed numeric;
begin
    select coalesce(sum(case v.direction when 'in' then v.quantity else -v.quantity end),0),
           coalesce(sum(case v.direction when 'in' then v.amount_minor else -v.amount_minor end),0)
      into valued_quantity,valued_amount
      from gba.stock_valuations v
     where v.tenant_id=new.tenant_id and v.legal_entity_id=new.legal_entity_id and v.item_id=new.item_id;
    select * into held from gba.stock_costs c
     where c.tenant_id=new.tenant_id and c.legal_entity_id=new.legal_entity_id and c.item_id=new.item_id;
    select coalesce(sum(b.quantity),0) into placed from gba.stock_balances b
     where b.tenant_id=new.tenant_id and b.legal_entity_id=new.legal_entity_id and b.item_id=new.item_id;
    if held.quantity is distinct from valued_quantity or held.value_minor is distinct from valued_amount
       or held.quantity is distinct from placed then
        raise exception using errcode='23514', message='the cost of a material equals its valuations and its balances';
    end if;
    return null;
end;
$$;
-- The whole document again at commit: numbered lines, one inbound movement and one
-- valuation per line, a total that is the sum of the line amounts, and for a total above
-- zero exactly one journal entry: inventory debited, the account of the reason credited.
create function gba.assert_stock_document(tenant uuid, document uuid) returns void language plpgsql as $$
declare doc gba.stock_documents%rowtype; posting gba.stock_document_postings%rowtype;
    rules gba.stock_posting_rules%rowtype; counter uuid; base text; counted bigint; total numeric;
begin
    select * into doc from gba.stock_documents d where d.tenant_id=tenant and d.id=document;
    if doc.id is null then
        raise exception using errcode='23514', message='a stock record needs its document';
    end if;
    if (select count(*)<>doc.line_count or min(l.line_no)<>1 or max(l.line_no)<>doc.line_count
          from gba.stock_document_lines l where l.tenant_id=tenant and l.document_id=document) is not false then
        raise exception using errcode='23514', message='a stock document keeps its numbered lines';
    end if;
    if (select count(*) from gba.stock_movements m where m.tenant_id=tenant and m.document_id=document)<>doc.line_count
       or exists (select 1 from gba.stock_document_lines l left join gba.stock_movements m
            on m.tenant_id=l.tenant_id and m.document_id=l.document_id and m.line_no=l.line_no
           and m.direction='in' and m.item_id=l.item_id and m.quantity=l.quantity
           and m.place_id=doc.place_id and m.legal_entity_id=doc.legal_entity_id
         where l.tenant_id=tenant and l.document_id=document and m.document_id is null) then
        raise exception using errcode='23514', message='a stock document moves every line once';
    end if;
    select * into posting from gba.stock_document_postings p where p.tenant_id=tenant and p.document_id=document;
    select count(*),coalesce(sum(v.amount_minor),0) into counted,total
      from gba.stock_valuations v where v.tenant_id=tenant and v.document_id=document;
    if posting.document_id is null or counted<>doc.line_count or total<>posting.total_minor then
        raise exception using errcode='23514', message='a stock receipt values every line';
    end if;
    if posting.total_minor=0 then
        if exists (select 1 from gba.journal_entries e
            where e.tenant_id=tenant and e.source_kind='stock' and e.source_id=document::text) then
            raise exception using errcode='23514', message='a stock receipt posts its exact journal entry';
        end if;
        return;
    end if;
    select * into rules from gba.stock_posting_rules r
     where r.tenant_id=tenant and r.book_id=posting.book_id and r.revision=posting.rule_revision;
    counter := case doc.reason when 'purchase' then rules.receipt_account_id
        when 'opening_balance' then rules.opening_account_id else rules.surplus_account_id end;
    select v.base_currency into base from gba.ledger_book_versions v
     where v.tenant_id=tenant and v.book_id=posting.book_id order by v.revision desc limit 1;
    if not exists (select 1 from gba.journal_entries e
        where e.tenant_id=tenant and e.book_id=posting.book_id and e.id=posting.entry_id
          and e.source_kind='stock' and e.source_id=document::text and e.entry_date=doc.document_date
          and e.created_by=doc.created_by and e.currency=base and e.reverses_entry_id is null)
       or exists (
        (select l.line_no::integer,l.account_id,l.side,l.amount_minor from gba.journal_lines l
          where l.tenant_id=tenant and l.entry_id=posting.entry_id
         except all
         values (1,rules.inventory_account_id,'debit',posting.total_minor),(2,counter,'credit',posting.total_minor))
        union all
        (values (1,rules.inventory_account_id,'debit',posting.total_minor),(2,counter,'credit',posting.total_minor)
         except all
         select l.line_no::integer,l.account_id,l.side,l.amount_minor from gba.journal_lines l
          where l.tenant_id=tenant and l.entry_id=posting.entry_id)
    ) then
        raise exception using errcode='23514', message='a stock receipt posts its exact journal entry';
    end if;
end;
$$;
create function gba.check_stock_document() returns trigger language plpgsql as $$
declare origin text; source text;
begin
    if tg_table_name='stock_documents' then
        perform gba.assert_stock_document(new.tenant_id,new.id);
    elsif tg_table_name='journal_entries' then
        if new.source_kind='stock' then
            perform gba.assert_stock_document(new.tenant_id,new.source_id::uuid);
        end if;
    elsif tg_table_name='journal_lines' then
        select e.source_kind,e.source_id into origin,source from gba.journal_entries e
         where e.tenant_id=new.tenant_id and e.id=new.entry_id;
        if origin='stock' then
            perform gba.assert_stock_document(new.tenant_id,source::uuid);
        end if;
    else
        perform gba.assert_stock_document(new.tenant_id,new.document_id);
    end if;
    return null;
end;
$$;
-- A `stock` journal entry belongs to its document of the same transaction, book, date
-- and author, in the base currency of the book. The generic ledger reversal never
-- corrects it: a stock document is the only correction.
create function gba.enforce_stock_origin() returns trigger language plpgsql as $$
declare base text;
begin
    if new.reverses_entry_id is not null and exists (select 1 from gba.journal_entries e
        where e.tenant_id=new.tenant_id and e.id=new.reverses_entry_id and e.source_kind='stock') then
        raise exception using errcode='23514', message='a stock journal entry is corrected only by a stock document';
    end if;
    if new.source_kind='stock' then
        perform gba.lock_ledger(new.tenant_id);
        select v.base_currency into base from gba.ledger_book_versions v
         where v.tenant_id=new.tenant_id and v.book_id=new.book_id order by v.revision desc limit 1;
        if new.currency is distinct from base or not exists (
            select 1 from gba.stock_document_postings p join gba.stock_documents d
                on d.tenant_id=p.tenant_id and d.id=p.document_id
             where p.tenant_id=new.tenant_id and p.book_id=new.book_id and p.entry_id=new.id
               and p.document_id::text=new.source_id and d.document_date=new.entry_date
               and d.created_by=new.created_by
               and p.created_transaction=pg_catalog.pg_current_xact_id()
        ) then
            raise exception using errcode='23514', message='a stock journal entry needs its stock document';
        end if;
    end if;
    return new;
end;
$$;
revoke all on function gba.guard_stock_posting_rule() from public;
revoke all on function gba.guard_stock_document() from public;
revoke all on function gba.guard_stock_document_line() from public;
revoke all on function gba.apply_stock_movement() from public;
revoke all on function gba.check_stock_balance() from public;
revoke all on function gba.guard_stock_posting() from public;
revoke all on function gba.apply_stock_valuation() from public;
revoke all on function gba.check_stock_cost() from public;
revoke all on function gba.assert_stock_document(uuid,uuid) from public;
grant execute on function gba.assert_stock_document(uuid,uuid) to gba_runtime;
revoke all on function gba.check_stock_document() from public;
revoke all on function gba.enforce_stock_origin() from public;

create trigger stock_posting_rules_guard before insert on gba.stock_posting_rules
    for each row execute function gba.guard_stock_posting_rule();
create trigger stock_documents_guard before insert on gba.stock_documents
    for each row execute function gba.guard_stock_document();
create trigger stock_document_lines_guard before insert on gba.stock_document_lines
    for each row execute function gba.guard_stock_document_line();
create trigger stock_movements_apply before insert on gba.stock_movements
    for each row execute function gba.apply_stock_movement();
create trigger stock_document_postings_guard before insert on gba.stock_document_postings
    for each row execute function gba.guard_stock_posting();
create trigger stock_valuations_apply before insert on gba.stock_valuations
    for each row execute function gba.apply_stock_valuation();
create constraint trigger stock_movements_balanced after insert on gba.stock_movements
    deferrable initially deferred for each row execute function gba.check_stock_balance();
create constraint trigger stock_balances_balanced after insert or update on gba.stock_balances
    deferrable initially deferred for each row execute function gba.check_stock_balance();
create constraint trigger stock_valuations_balanced after insert on gba.stock_valuations
    deferrable initially deferred for each row execute function gba.check_stock_cost();
create constraint trigger stock_costs_balanced after insert or update on gba.stock_costs
    deferrable initially deferred for each row execute function gba.check_stock_cost();
-- An early SET CONSTRAINTS must not let a later row evade the final check: every table
-- of a document carries it.
create constraint trigger stock_documents_consistent after insert on gba.stock_documents
    deferrable initially deferred for each row execute function gba.check_stock_document();
create constraint trigger stock_document_lines_consistent after insert on gba.stock_document_lines
    deferrable initially deferred for each row execute function gba.check_stock_document();
create constraint trigger stock_movements_consistent after insert on gba.stock_movements
    deferrable initially deferred for each row execute function gba.check_stock_document();
create constraint trigger stock_document_postings_consistent after insert on gba.stock_document_postings
    deferrable initially deferred for each row execute function gba.check_stock_document();
create constraint trigger stock_valuations_consistent after insert on gba.stock_valuations
    deferrable initially deferred for each row execute function gba.check_stock_document();
create trigger journal_entries_stock_origin before insert on gba.journal_entries
    for each row execute function gba.enforce_stock_origin();
create constraint trigger journal_entries_stock_consistent after insert on gba.journal_entries
    deferrable initially deferred for each row execute function gba.check_stock_document();
create constraint trigger journal_lines_stock_consistent after insert on gba.journal_lines
    deferrable initially deferred for each row execute function gba.check_stock_document();

-- Grants, tenant/location policies and immutable/module guards are declared below.
-- A balance and a cost row change only in their running totals; nothing is deleted.
grant update (quantity) on gba.stock_balances to gba_runtime;
grant update (quantity,value_minor) on gba.stock_costs to gba_runtime;

alter table gba.stock_posting_rules enable row level security;
alter table gba.stock_posting_rules force row level security;
create policy stock_posting_rules_tenant_isolation on gba.stock_posting_rules
    using (tenant_id=gba.current_tenant_id()) with check (tenant_id=gba.current_tenant_id());
create policy stock_posting_rules_location_scope on gba.stock_posting_rules as restrictive to gba_runtime
    using (gba.current_location_id() is null) with check (gba.current_location_id() is null);
grant select on gba.stock_posting_rules to gba_runtime;
grant insert (tenant_id,book_id,revision,inventory_account_id,receipt_account_id,opening_account_id,surplus_account_id,consumption_account_id,loss_account_id,difference_account_id,created_by) on gba.stock_posting_rules to gba_runtime;
create trigger stock_posting_rules_immutable before update or delete on gba.stock_posting_rules
    for each row execute function gba.reject_counterparty_mutation();
create trigger stock_posting_rules_require_inventory before insert on gba.stock_posting_rules
    for each row execute function gba.require_enabled_module('inventory');

alter table gba.stock_documents enable row level security;
alter table gba.stock_documents force row level security;
create policy stock_documents_tenant_isolation on gba.stock_documents
    using (tenant_id=gba.current_tenant_id()) with check (tenant_id=gba.current_tenant_id());
create policy stock_documents_location_scope on gba.stock_documents as restrictive to gba_runtime
    using (gba.current_location_id() is null or location_id=gba.current_location_id())
    with check (gba.current_location_id() is null or location_id=gba.current_location_id());
grant select on gba.stock_documents to gba_runtime;
grant insert (tenant_id,id,kind,reason,legal_entity_id,place_id,location_id,document_date,supplier_id,supplier_document,line_count,created_by) on gba.stock_documents to gba_runtime;
create trigger stock_documents_immutable before update or delete on gba.stock_documents
    for each row execute function gba.reject_counterparty_mutation();
create trigger stock_documents_require_inventory before insert on gba.stock_documents
    for each row execute function gba.require_enabled_module('inventory');

alter table gba.stock_document_lines enable row level security;
alter table gba.stock_document_lines force row level security;
create policy stock_document_lines_tenant_isolation on gba.stock_document_lines
    using (tenant_id=gba.current_tenant_id()) with check (tenant_id=gba.current_tenant_id());
create policy stock_document_lines_location_scope on gba.stock_document_lines as restrictive to gba_runtime
    using (gba.current_location_id() is null or location_id=gba.current_location_id())
    with check (gba.current_location_id() is null or location_id=gba.current_location_id());
grant select on gba.stock_document_lines to gba_runtime;
grant insert (tenant_id,document_id,line_no,location_id,item_id,quantity) on gba.stock_document_lines to gba_runtime;
create trigger stock_document_lines_immutable before update or delete on gba.stock_document_lines
    for each row execute function gba.reject_counterparty_mutation();
create trigger stock_document_lines_require_inventory before insert on gba.stock_document_lines
    for each row execute function gba.require_enabled_module('inventory');

alter table gba.stock_movements enable row level security;
alter table gba.stock_movements force row level security;
create policy stock_movements_tenant_isolation on gba.stock_movements
    using (tenant_id=gba.current_tenant_id()) with check (tenant_id=gba.current_tenant_id());
create policy stock_movements_location_scope on gba.stock_movements as restrictive to gba_runtime
    using (gba.current_location_id() is null or location_id=gba.current_location_id())
    with check (gba.current_location_id() is null or location_id=gba.current_location_id());
grant select on gba.stock_movements to gba_runtime;
grant insert (tenant_id,document_id,line_no,direction,location_id,place_id,item_id,legal_entity_id,quantity) on gba.stock_movements to gba_runtime;
create trigger stock_movements_immutable before update or delete on gba.stock_movements
    for each row execute function gba.reject_counterparty_mutation();
create trigger stock_movements_require_inventory before insert on gba.stock_movements
    for each row execute function gba.require_enabled_module('inventory');

alter table gba.stock_balances enable row level security;
alter table gba.stock_balances force row level security;
create policy stock_balances_tenant_isolation on gba.stock_balances
    using (tenant_id=gba.current_tenant_id()) with check (tenant_id=gba.current_tenant_id());
create policy stock_balances_location_scope on gba.stock_balances as restrictive to gba_runtime
    using (gba.current_location_id() is null or location_id=gba.current_location_id())
    with check (gba.current_location_id() is null or location_id=gba.current_location_id());
grant select on gba.stock_balances to gba_runtime;
grant insert (tenant_id,item_id,place_id,legal_entity_id,location_id,quantity) on gba.stock_balances to gba_runtime;
create trigger stock_balances_immutable before delete on gba.stock_balances
    for each row execute function gba.reject_counterparty_mutation();
create trigger stock_balances_require_inventory before insert on gba.stock_balances
    for each row execute function gba.require_enabled_module('inventory');

alter table gba.stock_document_postings enable row level security;
alter table gba.stock_document_postings force row level security;
create policy stock_document_postings_tenant_isolation on gba.stock_document_postings
    using (tenant_id=gba.current_tenant_id()) with check (tenant_id=gba.current_tenant_id());
create policy stock_document_postings_location_scope on gba.stock_document_postings as restrictive to gba_runtime
    using (gba.current_location_id() is null) with check (gba.current_location_id() is null);
grant select on gba.stock_document_postings to gba_runtime;
grant insert (tenant_id,document_id,book_id,rule_revision,entry_id,total_minor,created_by) on gba.stock_document_postings to gba_runtime;
create trigger stock_document_postings_immutable before update or delete on gba.stock_document_postings
    for each row execute function gba.reject_counterparty_mutation();
create trigger stock_document_postings_require_inventory before insert on gba.stock_document_postings
    for each row execute function gba.require_enabled_module('inventory');

alter table gba.stock_valuations enable row level security;
alter table gba.stock_valuations force row level security;
create policy stock_valuations_tenant_isolation on gba.stock_valuations
    using (tenant_id=gba.current_tenant_id()) with check (tenant_id=gba.current_tenant_id());
create policy stock_valuations_location_scope on gba.stock_valuations as restrictive to gba_runtime
    using (gba.current_location_id() is null) with check (gba.current_location_id() is null);
grant select on gba.stock_valuations to gba_runtime;
grant insert (tenant_id,document_id,line_no,direction,legal_entity_id,item_id,quantity,amount_minor) on gba.stock_valuations to gba_runtime;
create trigger stock_valuations_immutable before update or delete on gba.stock_valuations
    for each row execute function gba.reject_counterparty_mutation();
create trigger stock_valuations_require_inventory before insert on gba.stock_valuations
    for each row execute function gba.require_enabled_module('inventory');

alter table gba.stock_costs enable row level security;
alter table gba.stock_costs force row level security;
create policy stock_costs_tenant_isolation on gba.stock_costs
    using (tenant_id=gba.current_tenant_id()) with check (tenant_id=gba.current_tenant_id());
create policy stock_costs_location_scope on gba.stock_costs as restrictive to gba_runtime
    using (gba.current_location_id() is null) with check (gba.current_location_id() is null);
grant select on gba.stock_costs to gba_runtime;
grant insert (tenant_id,legal_entity_id,item_id,quantity,value_minor) on gba.stock_costs to gba_runtime;
create trigger stock_costs_immutable before delete on gba.stock_costs
    for each row execute function gba.reject_counterparty_mutation();
create trigger stock_costs_require_inventory before insert on gba.stock_costs
    for each row execute function gba.require_enabled_module('inventory');

-- CHECK_APPROVAL {"table":"journal_entries","name":"journal_entries_source_kind_check","expression":"(source_kind = ANY (ARRAY['manual'::text, 'opening'::text, 'reversal'::text, 'invoice'::text, 'accrual'::text, 'payment'::text, 'credit'::text, 'payment_correction'::text, 'credit_void'::text, 'stock'::text]))"}
