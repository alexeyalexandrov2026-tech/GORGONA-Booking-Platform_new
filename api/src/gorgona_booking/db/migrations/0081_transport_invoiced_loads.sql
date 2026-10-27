-- Package M review R-03 (ADR-0033 amendment): once an order is invoiced its loads keep what was
-- billed. Adding a load, or changing a load's quantity, removal or order, is refused under the
-- order's rate lock, the same lock the order invoice takes.
create function gba.guard_transport_invoiced_load() returns trigger language plpgsql as $$
begin
    if tg_op = 'UPDATE' and new.quantity = old.quantity and new.removed = old.removed
       and new.order_id = old.order_id then
        return new;
    end if;
    perform pg_catalog.pg_advisory_xact_lock(
        pg_catalog.hashtextextended('gba:order-rate:' || new.order_id::text, 0));
    if exists (select 1 from gba.transport_order_invoices i
                where i.tenant_id = new.tenant_id
                  and (i.order_id = new.order_id
                       or (tg_op = 'UPDATE' and i.order_id = old.order_id))) then
        raise exception using errcode = 'check_violation',
            constraint = 'transport_loads_invoiced_check',
            message = 'an invoiced order keeps its loads';
    end if;
    return new;
end;
$$;
revoke all on function gba.guard_transport_invoiced_load() from public;
create trigger transport_loads_invoiced_guard before insert or update on gba.transport_loads
    for each row execute function gba.guard_transport_invoiced_load();
