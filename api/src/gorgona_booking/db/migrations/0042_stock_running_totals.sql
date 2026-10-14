-- Finding M2 of the independent review of package J / ADR-0026: the checks at commit no
-- longer sum the whole history. Forward only.
--
-- Every movement carries its place in the history of its balance and the balance after
-- it; every valuation the quantity and the value of its owner's material after it. The
-- insert triggers write them from the head of the history, after checking that the stored
-- total still equals that head, and nobody else can: the runtime role may not insert or
-- update these columns, and movements and valuations are never updated or deleted. The
-- checks at commit compare a total with the head of its history, one row of an index.
-- A total changed outside a document is refused as before: at commit when nothing follows
-- it, and at once when a movement or a valuation follows it.

alter table gba.stock_movements add column sequence bigint;
alter table gba.stock_movements add column balance_after bigint;
alter table gba.stock_valuations add column sequence bigint;
alter table gba.stock_valuations add column quantity_after bigint;
alter table gba.stock_valuations add column value_after bigint;

-- The history posted so far, in the order of its transactions. A temporary policy of the
-- migration owner reads and fills the rows of every company; it is dropped below, and the
-- guards of immutability are off only while the new columns are filled.
create policy j6_upgrade_owner_backfill on gba.stock_documents for select to current_user using (true);
create policy j6_upgrade_owner_backfill on gba.stock_movements for all to current_user using (true) with check (true);
create policy j6_upgrade_owner_backfill on gba.stock_valuations for all to current_user using (true) with check (true);
alter table gba.stock_movements disable trigger stock_movements_immutable;
alter table gba.stock_valuations disable trigger stock_valuations_immutable;
update gba.stock_movements m set sequence=o.sequence,balance_after=o.balance_after
  from (select x.tenant_id,x.document_id,x.line_no,x.direction,
               row_number() over w as sequence,
               sum(case x.direction when 'in' then x.quantity else -x.quantity end) over w as balance_after
          from gba.stock_movements x
          join gba.stock_documents d on d.tenant_id=x.tenant_id and d.id=x.document_id
        window w as (partition by x.tenant_id,x.item_id,x.place_id,x.legal_entity_id
                     order by d.created_transaction,x.document_id,x.line_no,x.direction)) o
 where m.tenant_id=o.tenant_id and m.document_id=o.document_id and m.line_no=o.line_no
   and m.direction=o.direction;
update gba.stock_valuations v set sequence=o.sequence,quantity_after=o.quantity_after,
       value_after=o.value_after
  from (select x.tenant_id,x.document_id,x.line_no,
               row_number() over w as sequence,
               sum(case x.direction when 'in' then x.quantity else -x.quantity end) over w as quantity_after,
               sum(case x.direction when 'in' then x.amount_minor else -x.amount_minor end) over w as value_after
          from gba.stock_valuations x
          join gba.stock_documents d on d.tenant_id=x.tenant_id and d.id=x.document_id
        window w as (partition by x.tenant_id,x.legal_entity_id,x.item_id
                     order by d.created_transaction,x.document_id,x.line_no)) o
 where v.tenant_id=o.tenant_id and v.document_id=o.document_id and v.line_no=o.line_no;
alter table gba.stock_movements enable trigger stock_movements_immutable;
alter table gba.stock_valuations enable trigger stock_valuations_immutable;
drop policy j6_upgrade_owner_backfill on gba.stock_documents;
drop policy j6_upgrade_owner_backfill on gba.stock_movements;
drop policy j6_upgrade_owner_backfill on gba.stock_valuations;
alter table gba.stock_movements alter column sequence set not null;
alter table gba.stock_movements alter column balance_after set not null;
alter table gba.stock_valuations alter column sequence set not null;
alter table gba.stock_valuations alter column quantity_after set not null;
alter table gba.stock_valuations alter column value_after set not null;
-- One link per place in a history; the key also finds its head.
alter table gba.stock_movements add constraint stock_movements_sequence_key unique (tenant_id,item_id,place_id,legal_entity_id,sequence);
alter table gba.stock_valuations add constraint stock_valuations_sequence_key unique (tenant_id,legal_entity_id,item_id,sequence);
-- These keys begin with the columns of the two indexes of the totals and replace them: with
-- both, the planner could read a whole history through the old index and sort it.
drop index gba.stock_movements_balance;
drop index gba.stock_valuations_cost;

-- A movement repeats its line, moves the balance and continues its history.
create or replace function gba.apply_stock_movement() returns trigger language plpgsql as $$
declare line record; way text; total bigint; head_sequence bigint; head_balance bigint;
begin
    if pg_catalog.current_setting('transaction_isolation')<>'read committed' then
        raise exception using errcode='40001', message='stock movements require read committed transactions';
    end if;
    select d.kind,d.place_id,d.location_id,d.to_place_id,d.to_location_id,d.legal_entity_id,
           s.kind as source_kind,l.item_id,l.quantity into line
      from gba.stock_documents d
      left join gba.stock_documents s on s.tenant_id=d.tenant_id and s.id=d.source_document_id
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
-- A valuation repeats its line, moves the cost and continues its history; see 0040.
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
      left join gba.stock_documents s on s.tenant_id=d.tenant_id and s.id=d.source_document_id
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

-- A balance equals the head of its history; a balance without one is refused, even at zero.
create or replace function gba.check_stock_balance() returns trigger language plpgsql as $$
declare held bigint; head bigint;
begin
    select b.quantity into held from gba.stock_balances b
     where b.tenant_id=new.tenant_id and b.item_id=new.item_id and b.place_id=new.place_id
       and b.legal_entity_id=new.legal_entity_id;
    select m.balance_after into head from gba.stock_movements m
     where m.tenant_id=new.tenant_id and m.item_id=new.item_id and m.place_id=new.place_id
       and m.legal_entity_id=new.legal_entity_id
     order by m.sequence desc limit 1;
    if held is distinct from head then
        raise exception using errcode='23514', message='a stock balance equals the sum of its movements';
    end if;
    return null;
end;
$$;
-- The cost row equals the head of its history and exists only through it, and its
-- quantity equals what the places hold.
create or replace function gba.check_stock_cost() returns trigger language plpgsql as $$
declare held gba.stock_costs%rowtype; head_quantity bigint; head_value bigint; placed numeric;
begin
    select * into held from gba.stock_costs c
     where c.tenant_id=new.tenant_id and c.legal_entity_id=new.legal_entity_id and c.item_id=new.item_id;
    select v.quantity_after,v.value_after into head_quantity,head_value from gba.stock_valuations v
     where v.tenant_id=new.tenant_id and v.legal_entity_id=new.legal_entity_id and v.item_id=new.item_id
     order by v.sequence desc limit 1;
    select coalesce(sum(b.quantity),0) into placed from gba.stock_balances b
     where b.tenant_id=new.tenant_id and b.legal_entity_id=new.legal_entity_id and b.item_id=new.item_id;
    if held.quantity is distinct from head_quantity or held.value_minor is distinct from head_value
       or held.quantity is distinct from placed then
        raise exception using errcode='23514', message='the cost of a material equals its valuations and its balances';
    end if;
    return null;
end;
$$;

-- A stock journal entry finds its document by the key of the document, not by a text
-- copy of it that no index serves: the guard read every stock document of the company.
-- A source that is not the text of an identifier finds nothing, as before.
create or replace function gba.enforce_stock_origin() returns trigger language plpgsql as $$
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
               and p.document_id=(case when new.source_id ~ '^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$'
                   then new.source_id::uuid end)
               and d.document_date=new.entry_date
               and d.created_by=new.created_by
               and p.created_transaction=pg_catalog.pg_current_xact_id()
        ) then
            raise exception using errcode='23514', message='a stock journal entry needs its stock document';
        end if;
    end if;
    return new;
end;
$$;
