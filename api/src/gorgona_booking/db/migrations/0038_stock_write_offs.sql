-- J3 / ADR-0026: write-offs at the moving-average cost.
-- Forward only; no relation is added. A write-off is a posted document like a receipt:
-- its lines, outbound movements, balances, cost and one `stock` journal entry are written
-- in one transaction and never change.
-- A balance never goes below zero: an outbound movement takes no more than its owner
-- holds in the place, under the lock of that balance row.
-- The database values every outbound line itself: value * quantity / held, rounded half
-- up, and the whole value when the whole quantity leaves. A writer repeats that amount
-- or is refused; the command of a write-off carries no amount.

-- Two kinds of documents, each with its own reasons.
alter table gba.stock_documents drop constraint stock_documents_kind_check;
alter table gba.stock_documents add constraint stock_documents_kind_check
    check (kind in ('receipt', 'write_off'));
alter table gba.stock_documents drop constraint stock_documents_reason_check;
alter table gba.stock_documents add constraint stock_documents_reason_check
    check ((kind = 'receipt' and reason in ('purchase', 'opening_balance', 'surplus'))
        or (kind = 'write_off' and reason in ('used', 'damaged', 'lost', 'expired', 'other')));

-- A stock document changes the books: only the authenticated company-wide owner or
-- manager posts it, under the posting lock. Its date is not in the future of the branch.
-- An archived place takes no receipt and still lets its balance leave.
create or replace function gba.guard_stock_document() returns trigger language plpgsql as $$
declare closed boolean; zone text;
begin
    perform 1 from gba.memberships m join gba.users u on u.id=m.user_id
     where m.tenant_id=new.tenant_id and m.user_id=new.created_by and m.status='active' and u.status='active'
       and m.role in ('owner','manager') and m.location_id is null
     for share of m;
    if not found or new.created_by is distinct from gba.current_user_id() or gba.current_location_id() is not null then
        raise exception using errcode='42501', message='a stock document needs its authenticated company-wide owner or manager';
    end if;
    perform gba.lock_ledger(new.tenant_id);
    perform 1 from gba.stock_places p where p.tenant_id=new.tenant_id and p.id=new.place_id for share;
    select v.archived into closed from gba.stock_place_versions v
     where v.tenant_id=new.tenant_id and v.place_id=new.place_id order by v.revision desc limit 1;
    if closed and new.kind='receipt' then
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
-- Lines are written with their document. An archived material takes no receipt and
-- still lets its balance leave.
create or replace function gba.guard_stock_document_line() returns trigger language plpgsql as $$
declare closed boolean; document_kind text;
begin
    select d.kind into document_kind from gba.stock_documents d
     where d.tenant_id=new.tenant_id and d.id=new.document_id and d.location_id=new.location_id
       and new.line_no<=d.line_count and d.created_transaction=pg_catalog.pg_current_xact_id();
    if not found then
        raise exception using errcode='23514', message='stock lines are written with their document';
    end if;
    perform 1 from gba.stock_items s where s.tenant_id=new.tenant_id and s.id=new.item_id for share;
    select v.archived into closed from gba.stock_item_versions v
     where v.tenant_id=new.tenant_id and v.item_id=new.item_id order by v.revision desc limit 1;
    if closed and document_kind='receipt' then
        raise exception using errcode='23514', message='an archived material takes no receipt';
    end if;
    return new;
end;
$$;
-- A movement repeats its document line of the same transaction, in the direction of its
-- document, and moves the balance under the lock of the balance row. An outbound
-- movement takes no more than that row holds.
create or replace function gba.apply_stock_movement() returns trigger language plpgsql as $$
declare line record;
begin
    if pg_catalog.current_setting('transaction_isolation')<>'read committed' then
        raise exception using errcode='40001', message='stock movements require read committed transactions';
    end if;
    select d.kind,d.place_id,d.location_id,d.legal_entity_id,l.item_id,l.quantity into line
      from gba.stock_documents d join gba.stock_document_lines l
        on l.tenant_id=d.tenant_id and l.document_id=d.id
     where d.tenant_id=new.tenant_id and d.id=new.document_id and l.line_no=new.line_no
       and d.created_transaction=pg_catalog.pg_current_xact_id();
    if not found or new.direction<>(case line.kind when 'receipt' then 'in' else 'out' end)
       or new.place_id<>line.place_id or new.location_id<>line.location_id
       or new.legal_entity_id<>line.legal_entity_id or new.item_id<>line.item_id or new.quantity<>line.quantity then
        raise exception using errcode='23514', message='a stock movement repeats its document line';
    end if;
    if new.direction='in' then
        insert into gba.stock_balances (tenant_id,item_id,place_id,legal_entity_id,location_id,quantity)
        values (new.tenant_id,new.item_id,new.place_id,new.legal_entity_id,new.location_id,new.quantity)
        on conflict (tenant_id,item_id,place_id,legal_entity_id)
        do update set quantity=gba.stock_balances.quantity+excluded.quantity;
        return new;
    end if;
    -- Waits for a concurrent writer of the row and then compares with what that writer left.
    update gba.stock_balances b set quantity=b.quantity-new.quantity
     where b.tenant_id=new.tenant_id and b.item_id=new.item_id and b.place_id=new.place_id
       and b.legal_entity_id=new.legal_entity_id and b.quantity>=new.quantity;
    if not found then
        raise exception using errcode='GBS02', message='an outbound movement takes no more than its owner holds in the place';
    end if;
    return new;
end;
$$;
-- A valuation repeats its line of a money document of the same transaction and moves
-- the cost of the material. A receipt adds its quantity and its amount. An outbound line
-- leaves at the moving average, computed here with exact arithmetic.
create or replace function gba.apply_stock_valuation() returns trigger language plpgsql as $$
declare line record; held gba.stock_costs%rowtype; worth numeric;
begin
    perform gba.lock_ledger(new.tenant_id);
    select d.kind,d.legal_entity_id,l.item_id,l.quantity into line
      from gba.stock_documents d
      join gba.stock_document_postings p on p.tenant_id=d.tenant_id and p.document_id=d.id
      join gba.stock_document_lines l on l.tenant_id=d.tenant_id and l.document_id=d.id
     where d.tenant_id=new.tenant_id and d.id=new.document_id and l.line_no=new.line_no
       and d.created_transaction=pg_catalog.pg_current_xact_id();
    if not found or new.direction<>(case line.kind when 'receipt' then 'in' else 'out' end)
       or new.legal_entity_id<>line.legal_entity_id
       or new.item_id<>line.item_id or new.quantity<>line.quantity then
        raise exception using errcode='23514', message='a stock valuation repeats its document line';
    end if;
    if new.direction='in' then
        insert into gba.stock_costs (tenant_id,legal_entity_id,item_id,quantity,value_minor)
        values (new.tenant_id,new.legal_entity_id,new.item_id,new.quantity,new.amount_minor)
        on conflict (tenant_id,legal_entity_id,item_id)
        do update set quantity=gba.stock_costs.quantity+excluded.quantity,
                      value_minor=gba.stock_costs.value_minor+excluded.value_minor;
        return new;
    end if;
    select * into held from gba.stock_costs c
     where c.tenant_id=new.tenant_id and c.legal_entity_id=new.legal_entity_id and c.item_id=new.item_id
     for update;
    if held.quantity is null or held.quantity<new.quantity then
        raise exception using errcode='GBS02', message='an outbound line takes no more than its owner holds';
    end if;
    -- Half up without a rounded quotient: floor((2 * V * q + Q) / (2 * Q)).
    worth := case when new.quantity=held.quantity then held.value_minor
        else pg_catalog.div(2*held.value_minor::numeric*new.quantity+held.quantity,2*held.quantity::numeric) end;
    if new.amount_minor is distinct from worth then
        raise exception using errcode='23514', message='an outbound line leaves at the moving average';
    end if;
    update gba.stock_costs c set quantity=c.quantity-new.quantity,value_minor=c.value_minor-new.amount_minor
     where c.tenant_id=new.tenant_id and c.legal_entity_id=new.legal_entity_id and c.item_id=new.item_id;
    return new;
end;
$$;
-- The whole document again at commit: numbered lines, one movement and one valuation per
-- line in the direction of the document, a total that is the sum of the line amounts, and
-- for a total above zero exactly one journal entry. A receipt debits inventory and
-- credits the account of its reason; a write-off debits consumption or losses and
-- credits inventory.
create or replace function gba.assert_stock_document(tenant uuid, document uuid) returns void language plpgsql as $$
declare doc gba.stock_documents%rowtype; posting gba.stock_document_postings%rowtype;
    rules gba.stock_posting_rules%rowtype; way text; debited uuid; credited uuid; base text;
    counted bigint; total numeric;
begin
    select * into doc from gba.stock_documents d where d.tenant_id=tenant and d.id=document;
    if doc.id is null then
        raise exception using errcode='23514', message='a stock record needs its document';
    end if;
    way := case doc.kind when 'receipt' then 'in' else 'out' end;
    if (select count(*)<>doc.line_count or min(l.line_no)<>1 or max(l.line_no)<>doc.line_count
          from gba.stock_document_lines l where l.tenant_id=tenant and l.document_id=document) is not false then
        raise exception using errcode='23514', message='a stock document keeps its numbered lines';
    end if;
    if (select count(*) from gba.stock_movements m where m.tenant_id=tenant and m.document_id=document)<>doc.line_count
       or exists (select 1 from gba.stock_document_lines l left join gba.stock_movements m
            on m.tenant_id=l.tenant_id and m.document_id=l.document_id and m.line_no=l.line_no
           and m.direction=way and m.item_id=l.item_id and m.quantity=l.quantity
           and m.place_id=doc.place_id and m.legal_entity_id=doc.legal_entity_id
         where l.tenant_id=tenant and l.document_id=document and m.document_id is null) then
        raise exception using errcode='23514', message='a stock document moves every line once';
    end if;
    select * into posting from gba.stock_document_postings p where p.tenant_id=tenant and p.document_id=document;
    select count(*) filter (where v.direction=way),coalesce(sum(v.amount_minor),0) into counted,total
      from gba.stock_valuations v where v.tenant_id=tenant and v.document_id=document;
    if posting.document_id is null or counted<>doc.line_count or total<>posting.total_minor then
        raise exception using errcode='23514', message='a stock document values every line';
    end if;
    if posting.total_minor=0 then
        if exists (select 1 from gba.journal_entries e
            where e.tenant_id=tenant and e.source_kind='stock' and e.source_id=document::text) then
            raise exception using errcode='23514', message='a stock document posts its exact journal entry';
        end if;
        return;
    end if;
    select * into rules from gba.stock_posting_rules r
     where r.tenant_id=tenant and r.book_id=posting.book_id and r.revision=posting.rule_revision;
    if doc.kind='receipt' then
        debited := rules.inventory_account_id;
        credited := case doc.reason when 'purchase' then rules.receipt_account_id
            when 'opening_balance' then rules.opening_account_id else rules.surplus_account_id end;
    else
        debited := case doc.reason when 'used' then rules.consumption_account_id else rules.loss_account_id end;
        credited := rules.inventory_account_id;
    end if;
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
         values (1,debited,'debit',posting.total_minor),(2,credited,'credit',posting.total_minor))
        union all
        (values (1,debited,'debit',posting.total_minor),(2,credited,'credit',posting.total_minor)
         except all
         select l.line_no::integer,l.account_id,l.side,l.amount_minor from gba.journal_lines l
          where l.tenant_id=tenant and l.entry_id=posting.entry_id)
    ) then
        raise exception using errcode='23514', message='a stock document posts its exact journal entry';
    end if;
end;
$$;
