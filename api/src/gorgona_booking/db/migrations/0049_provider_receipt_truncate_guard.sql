-- K1k, review findings IR-09 and IR-08 / ADR-0027. Forward only; no row is changed.
--
-- Receipt history and authority were permanent for UPDATE and DELETE, but TRUNCATE, also a
-- TRUNCATE ... CASCADE from a referenced table, emptied them for the owner and a superuser.
-- A statement-level trigger now refuses it on every receipt table. A route also gets a random
-- ingress ID when provisioning names none; an explicit ID is still accepted.

create function gba.reject_provider_receipt_truncate() returns trigger
language plpgsql set search_path=pg_catalog as $$
begin
    raise exception using errcode='check_violation', message='receipt records are permanent; truncate is refused';
end;
$$;
revoke all on function gba.reject_provider_receipt_truncate() from public;

create trigger provider_receipt_connections_no_truncate before truncate on gba.provider_receipt_connections
    for each statement execute function gba.reject_provider_receipt_truncate();
create trigger provider_event_inbox_no_truncate before truncate on gba.provider_event_inbox
    for each statement execute function gba.reject_provider_receipt_truncate();
create trigger provider_event_deliveries_no_truncate before truncate on gba.provider_event_deliveries
    for each statement execute function gba.reject_provider_receipt_truncate();
create trigger provider_event_attestations_no_truncate before truncate on gba.provider_event_attestations
    for each statement execute function gba.reject_provider_receipt_truncate();
create trigger provider_verification_configs_no_truncate before truncate on gba.provider_verification_configs
    for each statement execute function gba.reject_provider_receipt_truncate();
create trigger provider_receipt_routes_no_truncate before truncate on gba.provider_receipt_routes
    for each statement execute function gba.reject_provider_receipt_truncate();

alter table gba.provider_receipt_routes alter column ingress_id set default gen_random_uuid();
