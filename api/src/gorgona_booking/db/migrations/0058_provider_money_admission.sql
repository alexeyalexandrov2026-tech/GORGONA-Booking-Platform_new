-- K0b, master plan §11.2.1 / ADR-0027: provider money needs the connection's admission.
--
-- A provider payment (provenance) or a link of a manual payment to a provider operation is
-- refused unless the latest admission revision of the operation's connection is test access for
-- that operation: a payment needs charge, a refund needs refund. The check shares the
-- connection's admission lock (0057), so a suspension waits for an application in flight and
-- refuses the next. Payments and links that exist already are not re-checked.

create function gba.require_provider_money_admission() returns trigger language plpgsql as $$
declare
    operation gba.provider_operations%rowtype;
    latest gba.provider_connection_admissions%rowtype;
begin
    select * into operation from gba.provider_operations o
        where o.tenant_id = new.tenant_id and o.id = new.operation_id;
    perform pg_catalog.pg_advisory_xact_lock_shared(pg_catalog.hashtextextended(
        'gba:provider-admission:' || new.tenant_id::text || ':' || operation.connection_id::text, 0));
    select * into latest from gba.provider_connection_admissions a
        where a.tenant_id = new.tenant_id and a.connection_id = operation.connection_id
        order by a.revision desc limit 1;
    if operation.id is null or latest.state is distinct from 'test_access'
        or not (case operation.kind when 'payment' then latest.charge_allowed
            else latest.refund_allowed end) then
        raise exception using errcode = 'check_violation',
            message = 'provider money needs an admitted connection for this operation';
    end if;
    return new;
end;
$$;
revoke all on function gba.require_provider_money_admission() from public;
create trigger external_payment_provenance_admission before insert on gba.external_payment_provenance
    for each row execute function gba.require_provider_money_admission();
create trigger provider_payment_links_admission before insert on gba.provider_payment_links
    for each row execute function gba.require_provider_money_admission();
