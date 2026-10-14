-- Finding H1 of the independent review of J5 and J6 / ADR-0026. Forward only.
--
-- A check at commit that cannot see the total it was called for refuses it. The runtime
-- role sets the company and the branch of its own session, and could hide a forged total,
-- or a total without any history, from the checks of migration 0042 by changing them
-- before commit: then neither the total nor the head of its history is visible, and an
-- unseen total equalled an unseen head. The row that called a check always exists, so a
-- total that the check cannot see is refused. Migration 0041 refused this through the sum
-- of an empty history.

-- A balance equals the head of its history and is seen by the check.
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
    if held is null or held is distinct from head then
        raise exception using errcode='23514', message='a stock balance equals the sum of its movements';
    end if;
    return null;
end;
$$;
-- The cost row equals the head of its history and the places, and is seen by the check.
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
    if held.quantity is null or held.quantity is distinct from head_quantity
       or held.value_minor is distinct from head_value
       or held.quantity is distinct from placed then
        raise exception using errcode='23514', message='the cost of a material equals its valuations and its balances';
    end if;
    return null;
end;
$$;
