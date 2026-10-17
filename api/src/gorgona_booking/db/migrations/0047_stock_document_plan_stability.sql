-- K1i, found by test_stock_scale (K1h finding) / ADR-0026. Forward only; no rule or row changes.
--
-- When statistics do not describe a company (gathered before it existed or before a burst of
-- postings), every index that starts with the company is estimated at one row. A check of one
-- document could then go through the running-total keys of migration 0042, which do not contain
-- the document, and read the material's whole history; PostgreSQL 18 can also use such an index
-- by skip scan when the company is not its first column.
--
-- The running-total keys become unique indexes of the same names that end with the company as
-- the expression (tenant_id::text). The uniqueness is the same (the text of a uuid is one-to-one),
-- the lookups by material, place, owner and latest sequence keep their index, and no plan can use
-- these indexes for tenant_id = ..., so one document is only reachable through its own key.
-- Item ids are chosen by clients and unique per company only, so the company stays in the key.
--
-- The check that every line of a document has its movement compared the material, place and
-- owner with equalities, which the running-total key (material first) could serve; for a material
-- the statistics do not describe it then read the material's whole history. The same comparisons
-- now use IS NOT DISTINCT FROM (every compared column is NOT NULL, so the meaning is unchanged),
-- which leaves the document key as the only usable index; the body is otherwise the 0040 text.
--
-- The line, movement and valuation triggers joined a return's source document on the company
-- and the source id; with the same uncertainty the planner scanned every document of the company.
-- The source is now read by a lateral lookup on its full key; the bodies are otherwise the texts
-- of 0040 and 0042 unchanged.
alter table gba.stock_movements drop constraint stock_movements_sequence_key;
create unique index stock_movements_sequence_key on gba.stock_movements
    (item_id,place_id,legal_entity_id,sequence,(tenant_id::text));
alter table gba.stock_valuations drop constraint stock_valuations_sequence_key;
create unique index stock_valuations_sequence_key on gba.stock_valuations
    (item_id,legal_entity_id,sequence,(tenant_id::text));

create or replace function gba.guard_stock_document_line() returns trigger language plpgsql as $$
declare closed boolean; doc record; source record; returned numeric;
begin
    select d.kind,d.source_document_id,s.kind as source_kind into doc
      from gba.stock_documents d
      left join lateral (select x.* from gba.stock_documents x where x.tenant_id=d.tenant_id
        and x.id=d.source_document_id limit 1) s on true
     where d.tenant_id=new.tenant_id and d.id=new.document_id and d.location_id=new.location_id
       and new.line_no<=d.line_count and d.created_transaction=pg_catalog.pg_current_xact_id();
    if not found then
        raise exception using errcode='23514', message='stock lines are written with their document';
    end if;
    if doc.kind='return' then
        select l.item_id,l.quantity into source from gba.stock_document_lines l
         where l.tenant_id=new.tenant_id and l.document_id=doc.source_document_id and l.line_no=new.source_line_no
         for update;
        if not found or new.source_document_id is distinct from doc.source_document_id or source.item_id<>new.item_id then
            raise exception using errcode='23514', message='a return line names a line of its source document with the same material';
        end if;
        select coalesce(sum(r.quantity),0) into returned from gba.stock_document_lines r
         where r.tenant_id=new.tenant_id and r.source_document_id=doc.source_document_id
           and r.source_line_no=new.source_line_no;
        if returned+new.quantity>source.quantity then
            raise exception using errcode='GBS03', message='returns take no more than the quantity of their source line';
        end if;
    elsif new.source_document_id is not null or new.source_line_no is not null then
        raise exception using errcode='23514', message='only a return line names a source line';
    end if;
    perform 1 from gba.stock_items s where s.tenant_id=new.tenant_id and s.id=new.item_id for share;
    select v.archived into closed from gba.stock_item_versions v
     where v.tenant_id=new.tenant_id and v.item_id=new.item_id order by v.revision desc limit 1;
    if closed and (doc.kind in ('receipt','transfer') or doc.source_kind='write_off') then
        raise exception using errcode='23514', message='an archived material takes no receipt, no transfer and no returned material';
    end if;
    return new;
end;
$$;

create or replace function gba.apply_stock_movement() returns trigger language plpgsql as $$
declare line record; way text; total bigint; head_sequence bigint; head_balance bigint;
begin
    if pg_catalog.current_setting('transaction_isolation')<>'read committed' then
        raise exception using errcode='40001', message='stock movements require read committed transactions';
    end if;
    select d.kind,d.place_id,d.location_id,d.to_place_id,d.to_location_id,d.legal_entity_id,
           s.kind as source_kind,l.item_id,l.quantity into line
      from gba.stock_documents d
      left join lateral (select x.* from gba.stock_documents x where x.tenant_id=d.tenant_id
        and x.id=d.source_document_id limit 1) s on true
      join gba.stock_document_lines l on l.tenant_id=d.tenant_id and l.document_id=d.id
     where d.tenant_id=new.tenant_id and d.id=new.document_id and l.line_no=new.line_no
       and d.created_transaction=pg_catalog.pg_current_xact_id();
    if not found then
        raise exception using errcode='23514', message='a stock movement repeats its document line';
    end if;
    way := case when line.kind='receipt' or line.source_kind='write_off' then 'in' else 'out' end;
    if (line.kind<>'transfer' and new.direction<>way)
       or new.place_id<>(case when line.kind='transfer' and new.direction='in' then line.to_place_id else line.place_id end)
       or new.location_id<>(case when line.kind='transfer' and new.direction='in' then line.to_location_id else line.location_id end)
       or new.legal_entity_id<>line.legal_entity_id or new.item_id<>line.item_id or new.quantity<>line.quantity then
        raise exception using errcode='23514', message='a stock movement repeats its document line';
    end if;
    if new.direction='in' then
        insert into gba.stock_balances (tenant_id,item_id,place_id,legal_entity_id,location_id,quantity)
        values (new.tenant_id,new.item_id,new.place_id,new.legal_entity_id,new.location_id,new.quantity)
        on conflict (tenant_id,item_id,place_id,legal_entity_id)
        do update set quantity=gba.stock_balances.quantity+excluded.quantity
        returning quantity into total;
    else
        -- Waits for a concurrent writer of the row and then compares with what that writer left.
        update gba.stock_balances b set quantity=b.quantity-new.quantity
         where b.tenant_id=new.tenant_id and b.item_id=new.item_id and b.place_id=new.place_id
           and b.legal_entity_id=new.legal_entity_id and b.quantity>=new.quantity
        returning b.quantity into total;
        if not found then
            raise exception using errcode='GBS02', message='an outbound movement takes no more than its owner holds in the place';
        end if;
    end if;
    -- The history goes on from its head, which the balance before this movement must equal.
    -- The row of the balance is locked above, so the head of an earlier writer is committed.
    select m.sequence,m.balance_after into head_sequence,head_balance from gba.stock_movements m
     where m.tenant_id=new.tenant_id and m.item_id=new.item_id and m.place_id=new.place_id
       and m.legal_entity_id=new.legal_entity_id
     order by m.sequence desc limit 1;
    if coalesce(head_balance,0)<>total-(case new.direction when 'in' then new.quantity else -new.quantity end) then
        raise exception using errcode='23514', message='a stock balance equals the sum of its movements';
    end if;
    new.sequence := coalesce(head_sequence,0)+1;
    new.balance_after := total;
    return new;
end;
$$;

create or replace function gba.apply_stock_valuation() returns trigger language plpgsql as $$
declare line record; held gba.stock_costs%rowtype; worth numeric; way text;
    source_amount numeric; source_quantity numeric; back_quantity numeric; back_basis numeric;
    left_quantity numeric; left_amount numeric; total_quantity bigint; total_value bigint;
    head_sequence bigint; head_quantity bigint; head_value bigint;
begin
    perform gba.lock_ledger(new.tenant_id);
    select d.kind,d.legal_entity_id,d.source_document_id,s.kind as source_kind,
           l.item_id,l.quantity,l.source_line_no into line
      from gba.stock_documents d
      left join lateral (select x.* from gba.stock_documents x where x.tenant_id=d.tenant_id
        and x.id=d.source_document_id limit 1) s on true
      join gba.stock_document_postings p on p.tenant_id=d.tenant_id and p.document_id=d.id
      join gba.stock_document_lines l on l.tenant_id=d.tenant_id and l.document_id=d.id
     where d.tenant_id=new.tenant_id and d.id=new.document_id and l.line_no=new.line_no
       and d.created_transaction=pg_catalog.pg_current_xact_id();
    if not found then
        raise exception using errcode='23514', message='a stock valuation repeats its document line';
    end if;
    way := case when line.kind='receipt' or line.source_kind='write_off' then 'in' else 'out' end;
    if new.direction<>way or new.legal_entity_id<>line.legal_entity_id
       or new.item_id<>line.item_id or new.quantity<>line.quantity then
        raise exception using errcode='23514', message='a stock valuation repeats its document line';
    end if;
    if line.kind='return' then
        select v.amount_minor,l.quantity into source_amount,source_quantity
          from gba.stock_document_lines l join gba.stock_valuations v
            on v.tenant_id=l.tenant_id and v.document_id=l.document_id and v.line_no=l.line_no
         where l.tenant_id=new.tenant_id and l.document_id=line.source_document_id and l.line_no=line.source_line_no;
        select coalesce(sum(r.quantity),0),coalesce(sum(v.basis_minor),0) into back_quantity,back_basis
          from gba.stock_document_lines r join gba.stock_valuations v
            on v.tenant_id=r.tenant_id and v.document_id=r.document_id and v.line_no=r.line_no
         where r.tenant_id=new.tenant_id and r.source_document_id=line.source_document_id
           and r.source_line_no=line.source_line_no and r.document_id<>new.document_id;
        left_quantity := source_quantity-back_quantity;
        left_amount := source_amount-back_basis;
        if left_quantity is null or left_quantity<new.quantity then
            raise exception using errcode='GBS03', message='returns take no more than the quantity of their source line';
        end if;
        -- Half up without a rounded quotient, like the moving average below.
        if new.basis_minor is distinct from (case when new.quantity=left_quantity then left_amount
            else pg_catalog.div(2*left_amount*new.quantity+left_quantity,2*left_quantity) end) then
            raise exception using errcode='23514', message='a return line takes its share of what is left of its source line';
        end if;
        if way='in' and new.amount_minor<>new.basis_minor then
            raise exception using errcode='23514', message='a returned write-off enters at its share of the cost';
        end if;
    elsif new.basis_minor is not null then
        raise exception using errcode='23514', message='only a return line carries a share of a source line';
    end if;
    if new.direction='in' then
        insert into gba.stock_costs (tenant_id,legal_entity_id,item_id,quantity,value_minor)
        values (new.tenant_id,new.legal_entity_id,new.item_id,new.quantity,new.amount_minor)
        on conflict (tenant_id,legal_entity_id,item_id)
        do update set quantity=gba.stock_costs.quantity+excluded.quantity,
                      value_minor=gba.stock_costs.value_minor+excluded.value_minor
        returning quantity,value_minor into total_quantity,total_value;
    else
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
         where c.tenant_id=new.tenant_id and c.legal_entity_id=new.legal_entity_id and c.item_id=new.item_id
        returning c.quantity,c.value_minor into total_quantity,total_value;
    end if;
    -- The history goes on from its head, which the cost before this line must equal. The
    -- row of the cost is locked above and the ledger lock is held.
    select v.sequence,v.quantity_after,v.value_after into head_sequence,head_quantity,head_value
      from gba.stock_valuations v
     where v.tenant_id=new.tenant_id and v.legal_entity_id=new.legal_entity_id and v.item_id=new.item_id
     order by v.sequence desc limit 1;
    if coalesce(head_quantity,0)<>total_quantity-(case new.direction when 'in' then new.quantity else -new.quantity end)
       or coalesce(head_value,0)<>total_value-(case new.direction when 'in' then new.amount_minor else -new.amount_minor end) then
        raise exception using errcode='23514', message='the cost of a material equals its valuations and its balances';
    end if;
    new.sequence := coalesce(head_sequence,0)+1;
    new.quantity_after := total_quantity;
    new.value_after := total_value;
    return new;
end;
$$;

create or replace function gba.assert_stock_document(tenant uuid, document uuid) returns void language plpgsql as $$
declare doc gba.stock_documents%rowtype; source gba.stock_documents%rowtype;
    posting gba.stock_document_postings%rowtype; origin gba.stock_document_postings%rowtype;
    rules gba.stock_posting_rules%rowtype; earlier gba.stock_posting_rules%rowtype;
    way text; base text; counted bigint; shared bigint; total numeric; basis numeric;
    accounts uuid[]; nets numeric[];
begin
    select * into doc from gba.stock_documents d where d.tenant_id=tenant and d.id=document;
    if doc.id is null then
        raise exception using errcode='23514', message='a stock record needs its document';
    end if;
    if (select count(*)<>doc.line_count or min(l.line_no)<>1 or max(l.line_no)<>doc.line_count
          from gba.stock_document_lines l where l.tenant_id=tenant and l.document_id=document) is not false then
        raise exception using errcode='23514', message='a stock document keeps its numbered lines';
    end if;
    if doc.kind='transfer' then
        if (select count(*) from gba.stock_movements m where m.tenant_id=tenant and m.document_id=document)<>2*doc.line_count
           or exists (select 1 from gba.stock_document_lines l
             left join gba.stock_movements o
               on o.tenant_id=l.tenant_id and o.document_id=l.document_id and o.line_no=l.line_no
              and o.direction='out' and (o.item_id,o.quantity,o.place_id,o.legal_entity_id)
              is not distinct from (l.item_id,l.quantity,doc.place_id,doc.legal_entity_id)
             left join gba.stock_movements i
               on i.tenant_id=l.tenant_id and i.document_id=l.document_id and i.line_no=l.line_no
              and i.direction='in' and (i.item_id,i.quantity,i.place_id,i.legal_entity_id)
              is not distinct from (l.item_id,l.quantity,doc.to_place_id,doc.legal_entity_id)
            where l.tenant_id=tenant and l.document_id=document
              and (o.document_id is null or i.document_id is null)) then
            raise exception using errcode='23514', message='a stock document moves every line once';
        end if;
        if exists (select 1 from gba.stock_document_postings p where p.tenant_id=tenant and p.document_id=document)
           or exists (select 1 from gba.stock_valuations v where v.tenant_id=tenant and v.document_id=document)
           or exists (select 1 from gba.journal_entries e
            where e.tenant_id=tenant and e.source_kind='stock' and e.source_id=document::text) then
            raise exception using errcode='23514', message='a stock transfer moves no money';
        end if;
        return;
    end if;
    if doc.kind='return' then
        select * into source from gba.stock_documents s where s.tenant_id=tenant and s.id=doc.source_document_id;
    end if;
    way := case when doc.kind='receipt' or source.kind='write_off' then 'in' else 'out' end;
    if (select count(*) from gba.stock_movements m where m.tenant_id=tenant and m.document_id=document)<>doc.line_count
       or exists (select 1 from gba.stock_document_lines l left join gba.stock_movements m
            on m.tenant_id=l.tenant_id and m.document_id=l.document_id and m.line_no=l.line_no
           and m.direction=way and (m.item_id,m.quantity,m.place_id,m.legal_entity_id)
           is not distinct from (l.item_id,l.quantity,doc.place_id,doc.legal_entity_id)
         where l.tenant_id=tenant and l.document_id=document and m.document_id is null) then
        raise exception using errcode='23514', message='a stock document moves every line once';
    end if;
    select * into posting from gba.stock_document_postings p where p.tenant_id=tenant and p.document_id=document;
    select count(*) filter (where v.direction=way),count(v.basis_minor),
           coalesce(sum(v.amount_minor),0),coalesce(sum(v.basis_minor),0) into counted,shared,total,basis
      from gba.stock_valuations v where v.tenant_id=tenant and v.document_id=document;
    if posting.document_id is null or counted<>doc.line_count or total<>posting.total_minor
       or shared<>(case doc.kind when 'return' then doc.line_count else 0 end) then
        raise exception using errcode='23514', message='a stock document values every line';
    end if;
    select * into rules from gba.stock_posting_rules r
     where r.tenant_id=tenant and r.book_id=posting.book_id and r.revision=posting.rule_revision;
    if doc.kind='receipt' then
        accounts := array[rules.inventory_account_id,case doc.reason when 'purchase' then rules.receipt_account_id
            when 'opening_balance' then rules.opening_account_id else rules.surplus_account_id end];
        nets := array[total,-total];
    elsif doc.kind='write_off' then
        accounts := array[case doc.reason when 'used' then rules.consumption_account_id else rules.loss_account_id end,
            rules.inventory_account_id];
        nets := array[total,-total];
    else
        select * into origin from gba.stock_document_postings p where p.tenant_id=tenant and p.document_id=source.id;
        select * into earlier from gba.stock_posting_rules r
         where r.tenant_id=tenant and r.book_id=origin.book_id and r.revision=origin.rule_revision;
        if earlier.revision is null or origin.book_id<>posting.book_id then
            raise exception using errcode='23514', message='a return posts to the book of its source document';
        end if;
        if source.kind='receipt' then
            accounts := array[case source.reason when 'purchase' then earlier.receipt_account_id
                when 'opening_balance' then earlier.opening_account_id else earlier.surplus_account_id end,
                rules.inventory_account_id,rules.difference_account_id];
            nets := array[basis,-total,total-basis];
        else
            accounts := array[rules.inventory_account_id,
                case source.reason when 'used' then earlier.consumption_account_id else earlier.loss_account_id end];
            nets := array[total,-total];
        end if;
    end if;
    if not exists (select 1 from unnest(accounts,nets) as w(account,net) group by w.account having sum(w.net)<>0) then
        if posting.entry_id is not null or exists (select 1 from gba.journal_entries e
            where e.tenant_id=tenant and e.source_kind='stock' and e.source_id=document::text) then
            raise exception using errcode='23514', message='a stock document posts its exact journal entry';
        end if;
        return;
    end if;
    select v.base_currency into base from gba.ledger_book_versions v
     where v.tenant_id=tenant and v.book_id=posting.book_id order by v.revision desc limit 1;
    if not exists (select 1 from gba.journal_entries e
        where e.tenant_id=tenant and e.book_id=posting.book_id and e.id=posting.entry_id
          and e.source_kind='stock' and e.source_id=document::text and e.entry_date=doc.document_date
          and e.created_by=doc.created_by and e.currency=base and e.reverses_entry_id is null)
       or exists (
        (select l.account_id,(case l.side when 'debit' then l.amount_minor else -l.amount_minor end)::numeric
           from gba.journal_lines l where l.tenant_id=tenant and l.entry_id=posting.entry_id
         except all
         select w.account,sum(w.net) from unnest(accounts,nets) as w(account,net)
          group by w.account having sum(w.net)<>0)
        union all
        (select w.account,sum(w.net) from unnest(accounts,nets) as w(account,net)
          group by w.account having sum(w.net)<>0
         except all
         select l.account_id,(case l.side when 'debit' then l.amount_minor else -l.amount_minor end)::numeric
           from gba.journal_lines l where l.tenant_id=tenant and l.entry_id=posting.entry_id)
    ) then
        raise exception using errcode='23514', message='a stock document posts its exact journal entry';
    end if;
end;
$$;
