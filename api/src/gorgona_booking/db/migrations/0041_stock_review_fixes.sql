-- Independent review of package J / ADR-0026: running totals exist only through documents.
-- Forward only; no relation is added. A balance row and a cost row are written only by the
-- movement and valuation triggers of a posted document. A row that no movement (or no
-- valuation) of its key explains is refused at commit, even when it holds zero.

create or replace function gba.check_stock_balance() returns trigger language plpgsql as $$
declare moved numeric; counted bigint; held bigint;
begin
    select coalesce(sum(case m.direction when 'in' then m.quantity else -m.quantity end),0),count(*)
      into moved,counted
      from gba.stock_movements m
     where m.tenant_id=new.tenant_id and m.item_id=new.item_id and m.place_id=new.place_id
       and m.legal_entity_id=new.legal_entity_id;
    select b.quantity into held from gba.stock_balances b
     where b.tenant_id=new.tenant_id and b.item_id=new.item_id and b.place_id=new.place_id
       and b.legal_entity_id=new.legal_entity_id;
    if held is distinct from moved or (held is not null and counted=0) then
        raise exception using errcode='23514', message='a stock balance equals the sum of its movements';
    end if;
    return null;
end;
$$;
-- The cost row equals its valuations and exists only through them, and its quantity
-- equals what the places hold.
create or replace function gba.check_stock_cost() returns trigger language plpgsql as $$
declare valued_quantity numeric; valued_amount numeric; counted bigint; held gba.stock_costs%rowtype; placed numeric;
begin
    select coalesce(sum(case v.direction when 'in' then v.quantity else -v.quantity end),0),
           coalesce(sum(case v.direction when 'in' then v.amount_minor else -v.amount_minor end),0),count(*)
      into valued_quantity,valued_amount,counted
      from gba.stock_valuations v
     where v.tenant_id=new.tenant_id and v.legal_entity_id=new.legal_entity_id and v.item_id=new.item_id;
    select * into held from gba.stock_costs c
     where c.tenant_id=new.tenant_id and c.legal_entity_id=new.legal_entity_id and c.item_id=new.item_id;
    select coalesce(sum(b.quantity),0) into placed from gba.stock_balances b
     where b.tenant_id=new.tenant_id and b.legal_entity_id=new.legal_entity_id and b.item_id=new.item_id;
    if held.quantity is distinct from valued_quantity or held.value_minor is distinct from valued_amount
       or held.quantity is distinct from placed or (held.quantity is not null and counted=0) then
        raise exception using errcode='23514', message='the cost of a material equals its valuations and its balances';
    end if;
    return null;
end;
$$;
