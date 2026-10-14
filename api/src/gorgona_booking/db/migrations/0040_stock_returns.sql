-- J4 / ADR-0026: returns against a line of an earlier receipt or write-off.
-- Forward only; no relation is added. A return is a posted money document like a receipt
-- and a write-off: its lines, movements, balances, cost and journal entry are written in
-- one transaction, under the posting lock, and never change.
-- A return names one source document of the same owner and, in every line, one of the
-- lines of that document with the same material. It moves the opposite way: against a
-- receipt the material leaves, against a write-off it comes back. All returns of a line
-- together never exceed its quantity; the check runs under the lock of that source line.
-- A return line takes its share of the amount of its source line: what is left of that
-- amount, by the quantity returned of the quantity left, rounded half up. The return that
-- completes a line therefore takes all that is left of its amount.
-- Against a receipt the material leaves inventory at the moving average, the account the
-- receipt credited is debited by the share, and the difference goes to the account of
-- price differences. Against a write-off the material enters inventory at the share,
-- from the account the write-off debited.

-- What a return returns: its source document and, for every line, the source line.
alter table gba.stock_documents add column source_document_id uuid;
alter table gba.stock_documents add constraint stock_documents_source_fkey
    foreign key (tenant_id, source_document_id) references gba.stock_documents(tenant_id, id);
alter table gba.stock_documents add constraint stock_documents_source_check
    check ((kind = 'return') = (source_document_id is not null) and source_document_id is distinct from id);
alter table gba.stock_document_lines add column source_document_id uuid;
alter table gba.stock_document_lines add column source_line_no smallint;
alter table gba.stock_document_lines add constraint stock_document_lines_source_fkey
    foreign key (tenant_id, source_document_id, source_line_no) references gba.stock_document_lines(tenant_id, document_id, line_no);
alter table gba.stock_document_lines add constraint stock_document_lines_source_check
    check ((source_document_id is null) = (source_line_no is null));
-- One return names a source line once.
alter table gba.stock_document_lines add constraint stock_document_lines_source_key unique (tenant_id, document_id, source_line_no);
create index stock_document_lines_returned on gba.stock_document_lines (tenant_id, source_document_id, source_line_no)
    where source_document_id is not null;
-- What a return line takes of the amount of its source line, in minor units.
alter table gba.stock_valuations add column basis_minor bigint;
alter table gba.stock_valuations add constraint stock_valuations_basis_check
    check (basis_minor between 0 and 999999999999999);
grant insert (source_document_id) on gba.stock_documents to gba_runtime;
grant insert (source_document_id,source_line_no) on gba.stock_document_lines to gba_runtime;
grant insert (basis_minor) on gba.stock_valuations to gba_runtime;
-- The row lock of a source line. The immutability guard of the table still refuses
-- every change of a line.
grant update (line_no) on gba.stock_document_lines to gba_runtime;

-- Four kinds of documents, each with its own reasons. A return to the supplier may name
-- the supplier, as a purchase does.
alter table gba.stock_documents drop constraint stock_documents_kind_check;
alter table gba.stock_documents add constraint stock_documents_kind_check
    check (kind in ('receipt', 'write_off', 'transfer', 'return'));
alter table gba.stock_documents drop constraint stock_documents_reason_check;
alter table gba.stock_documents add constraint stock_documents_reason_check
    check ((kind = 'receipt' and reason in ('purchase', 'opening_balance', 'surplus'))
        or (kind = 'write_off' and reason in ('used', 'damaged', 'lost', 'expired', 'other'))
        or (kind = 'transfer' and reason = 'relocation')
        or (kind = 'return' and reason in ('supplier_return', 'unused', 'entry_error')));
alter table gba.stock_documents drop constraint stock_documents_supplier_check;
alter table gba.stock_documents add constraint stock_documents_supplier_check
    check ((supplier_id is null and supplier_document is null) or reason in ('purchase', 'supplier_return'));
-- A return can post an entry although nothing leaves the inventory account: the share of
-- the source line and the price difference. Whether a document has an entry is decided
-- by the check of the whole document below.
alter table gba.stock_document_postings drop constraint stock_document_postings_entry_check;
alter table gba.stock_document_postings add constraint stock_document_postings_entry_check
    check (entry_id is not null or total_minor = 0);

-- A receipt, a write-off and a return change the books: only the authenticated
-- company-wide owner or manager posts them, under the posting lock. A return names a
-- receipt or a write-off of its owner and a reason of that kind. A transfer moves
-- quantities only: its author is the authenticated owner or manager whose membership
-- covers both branches. A date is not in the future of the branch of the document. An
-- archived place takes nothing in and still lets its balance leave.
create or replace function gba.guard_stock_document() returns trigger language plpgsql as $$
declare closed boolean; zone text; source record; inbound boolean;
begin
    if new.kind='transfer' then
        perform 1 from gba.memberships m join gba.users u on u.id=m.user_id
         where m.tenant_id=new.tenant_id and m.user_id=new.created_by and m.status='active' and u.status='active'
           and m.role in ('owner','manager')
           and (m.location_id is null or (m.location_id=new.location_id and m.location_id=new.to_location_id))
         for share of m;
        if not found or new.created_by is distinct from gba.current_user_id() then
            raise exception using errcode='42501', message='a stock transfer needs its authenticated owner or manager of both branches';
        end if;
        perform 1 from gba.stock_places p where p.tenant_id=new.tenant_id and p.id=new.to_place_id for share;
        select v.archived into closed from gba.stock_place_versions v
         where v.tenant_id=new.tenant_id and v.place_id=new.to_place_id order by v.revision desc limit 1;
        if closed then
            raise exception using errcode='23514', message='an archived storage place takes no transfer';
        end if;
        perform 1 from gba.stock_places p where p.tenant_id=new.tenant_id and p.id=new.place_id for share;
    else
        perform 1 from gba.memberships m join gba.users u on u.id=m.user_id
         where m.tenant_id=new.tenant_id and m.user_id=new.created_by and m.status='active' and u.status='active'
           and m.role in ('owner','manager') and m.location_id is null
         for share of m;
        if not found or new.created_by is distinct from gba.current_user_id() or gba.current_location_id() is not null then
            raise exception using errcode='42501', message='a stock document needs its authenticated company-wide owner or manager';
        end if;
        perform gba.lock_ledger(new.tenant_id);
        inbound := new.kind='receipt';
        if new.kind='return' then
            select s.kind,s.legal_entity_id into source from gba.stock_documents s
             where s.tenant_id=new.tenant_id and s.id=new.source_document_id;
            if not found or source.kind not in ('receipt','write_off')
               or source.legal_entity_id<>new.legal_entity_id
               or new.reason not in ('entry_error', case source.kind when 'receipt' then 'supplier_return' else 'unused' end) then
                raise exception using errcode='23514', message='a return names a receipt or a write-off of its owner and a reason of that kind';
            end if;
            inbound := source.kind='write_off';
        end if;
        perform 1 from gba.stock_places p where p.tenant_id=new.tenant_id and p.id=new.place_id for share;
        select v.archived into closed from gba.stock_place_versions v
         where v.tenant_id=new.tenant_id and v.place_id=new.place_id order by v.revision desc limit 1;
        if closed and inbound then
            raise exception using errcode='23514', message='an archived storage place takes no receipt and no returned material';
        end if;
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
-- Lines are written with their document. A return line names a line of the source
-- document with the same material, and all returns of that line stay within its
-- quantity, under its row lock. An archived material takes nothing in and still lets
-- its balance leave.
create or replace function gba.guard_stock_document_line() returns trigger language plpgsql as $$
declare closed boolean; doc record; source record; returned numeric;
begin
    select d.kind,d.source_document_id,s.kind as source_kind into doc
      from gba.stock_documents d
      left join gba.stock_documents s on s.tenant_id=d.tenant_id and s.id=d.source_document_id
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
-- A movement repeats its document line of the same transaction and moves the balance
-- under the lock of the balance row. A receipt moves in and a write-off moves out, at
-- the place of the document; a return moves against its source. A transfer moves out of
-- that place and into its destination. An outbound movement takes no more than its row
-- holds.
create or replace function gba.apply_stock_movement() returns trigger language plpgsql as $$
declare line record; way text;
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
-- leaves at the moving average, computed here with exact arithmetic. A return line also
-- carries its share of the source line, computed here the same way from what earlier
-- returns left of that line; a returned write-off enters at exactly that share.
create or replace function gba.apply_stock_valuation() returns trigger language plpgsql as $$
declare line record; held gba.stock_costs%rowtype; worth numeric; way text;
    source_amount numeric; source_quantity numeric; back_quantity numeric; back_basis numeric;
    left_quantity numeric; left_amount numeric;
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
-- The whole document again at commit: numbered lines and every line moved once. A
-- transfer moves each line out of its place and into its destination and carries no
-- money at all. A money document has one movement and one valuation per line in its
-- direction and a total that is the sum of the line amounts. Its journal entry carries
-- one line per account and exactly these amounts, and there is no entry when they are
-- all zero:
--   receipt      inventory debited, the account of its reason credited;
--   write-off    consumption or losses debited, inventory credited;
--   return of a receipt    the account the receipt credited debited by the shares of its
--                lines, inventory credited by the value at the average, the difference
--                on the account of price differences of the current rules;
--   return of a write-off  inventory debited, the account the write-off debited credited.
-- The accounts of a source document come from the rules it was posted with.
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
              and o.direction='out' and o.item_id=l.item_id and o.quantity=l.quantity
              and o.place_id=doc.place_id and o.legal_entity_id=doc.legal_entity_id
             left join gba.stock_movements i
               on i.tenant_id=l.tenant_id and i.document_id=l.document_id and i.line_no=l.line_no
              and i.direction='in' and i.item_id=l.item_id and i.quantity=l.quantity
              and i.place_id=doc.to_place_id and i.legal_entity_id=doc.legal_entity_id
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
           and m.direction=way and m.item_id=l.item_id and m.quantity=l.quantity
           and m.place_id=doc.place_id and m.legal_entity_id=doc.legal_entity_id
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
