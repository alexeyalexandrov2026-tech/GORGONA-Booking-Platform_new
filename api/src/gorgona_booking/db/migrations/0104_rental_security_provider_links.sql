-- R5b (package R, RENT-01): provider evidence for a rental card hold, sandbox only.
-- docs/plan/PACKAGE_R5B_DESIGN_2026-11-07.md. A recorded security event (0103) of a card hold names the signature-checked
-- test-mode receipt that shows it. The receipt's stored facts are checked here; nothing is created at the provider and
-- no operation, payment or journal entry is written. Links are insert-only.
create table gba.rental_security_provider_links (
    tenant_id uuid not null references gba.tenants(id),
    security_id uuid not null,
    sequence integer not null,
    receipt_id uuid not null,
    intent text not null constraint rental_security_provider_links_intent_check
        check (intent ~ '^pi_[A-Za-z0-9]{1,100}$'),
    linked_by uuid not null references gba.users(id),
    created_at timestamptz not null default now(),
    creation_xid xid8 not null default pg_current_xact_id(),
    primary key (tenant_id, security_id, sequence),
    foreign key (tenant_id, security_id, sequence)
        references gba.rental_security_events (tenant_id, security_id, sequence),
    foreign key (tenant_id, receipt_id) references gba.provider_event_inbox (tenant_id, id)
);

-- The receipt shows the event: an attested test-mode receipt of a connection that is not revoked, for the security
-- currency and one intent per security; a hold by a paid charge of the intent with nothing captured (a charge receipt
-- keeps only the captured amount); a capture by the intent's success for the security amount with everything captured
-- so far received; a release or an expiry by the intent's cancellation with nothing captured, or by its success with
-- exactly what was captured received, each for the security amount.
create function gba.guard_rental_security_provider_link() returns trigger language plpgsql as $$
declare
    security record;
    happened record;
    receipt record;
    resource jsonb;
    held_intent text;
    captured_so_far bigint;
    shows boolean;
begin
    select s.method, s.amount, lower(s.currency) as currency, b.class_id into security
    from gba.rental_securities s
      join gba.rental_bookings b on b.tenant_id = s.tenant_id and b.id = s.booking_id
    where s.tenant_id = new.tenant_id and s.id = new.security_id;
    perform 1 from gba.rental_classes c
    where c.tenant_id = new.tenant_id and c.id = security.class_id for update;
    select e.kind, e.amount into happened from gba.rental_security_events e
    where e.tenant_id = new.tenant_id and e.security_id = new.security_id and e.sequence = new.sequence;
    select i.facts, i.connection_id into receipt from gba.provider_event_inbox i
    where i.tenant_id = new.tenant_id and i.id = new.receipt_id;
    perform 1 from gba.provider_receipt_connections c
    where c.tenant_id = new.tenant_id and c.id = receipt.connection_id for share;
    resource := receipt.facts->'resource';
    select l.intent into held_intent from gba.rental_security_provider_links l
    where l.tenant_id = new.tenant_id and l.security_id = new.security_id and l.sequence = 1;
    select coalesce(sum(e.amount), 0) into captured_so_far from gba.rental_security_events e
    where e.tenant_id = new.tenant_id and e.security_id = new.security_id and e.kind = 'captured'
      and e.sequence <= new.sequence;
    shows := security.method = 'card_hold'
        and exists (select 1 from gba.provider_receipt_connections c
            where c.tenant_id = new.tenant_id and c.id = receipt.connection_id and not c.revoked)
        and exists (select 1 from gba.provider_event_attestations a
            where a.tenant_id = new.tenant_id and a.event_id = new.receipt_id)
        and (receipt.facts->>'livemode') = 'false'
        and resource->>'currency' = security.currency
        and not exists (select 1 from gba.rental_security_provider_links l
            where l.tenant_id = new.tenant_id and l.intent = new.intent and l.security_id <> new.security_id);
    if shows and happened.kind = 'held' then
        shows := receipt.facts->>'event_type' = 'charge.succeeded'
            and resource->>'object' = 'charge'
            and resource->>'status' = 'succeeded'
            and resource->'paid' = 'true'::jsonb
            and resource->'captured' = 'false'::jsonb
            and (resource->>'amount_minor')::bigint = 0
            and resource->>'payment_intent_id' = new.intent;
    elsif shows and happened.kind = 'captured' then
        shows := held_intent = new.intent
            and receipt.facts->>'event_type' = 'payment_intent.succeeded'
            and resource->>'id' = new.intent
            and (resource->>'amount_minor')::bigint = security.amount
            and (resource->>'amount_received_minor')::bigint = captured_so_far;
    elsif shows and happened.kind in ('released', 'expired') then
        shows := held_intent = new.intent
            and resource->>'id' = new.intent
            and (resource->>'amount_minor')::bigint = security.amount
            and ((receipt.facts->>'event_type' = 'payment_intent.canceled' and captured_so_far = 0)
                or (receipt.facts->>'event_type' = 'payment_intent.succeeded'
                    and (resource->>'amount_received_minor')::bigint = captured_so_far));
    end if;
    if shows is not true then
        raise exception using errcode = 'check_violation',
            constraint = 'rental_security_provider_links_evidence_check',
            message = 'a provider receipt shows the security event it is linked to';
    end if;
    return new;
end;
$$;
revoke all on function gba.guard_rental_security_provider_link() from public;
create trigger rental_security_provider_links_guard
    before insert on gba.rental_security_provider_links
    for each row execute function gba.guard_rental_security_provider_link();

-- Writes need the rental module (ADR-0019 gate).
create trigger rental_security_provider_links_module_gate
    before insert on gba.rental_security_provider_links
    for each row execute function gba.require_enabled_module('rental');

alter table gba.rental_security_provider_links enable row level security;
alter table gba.rental_security_provider_links force row level security;
create policy rental_security_provider_links_tenant_isolation on gba.rental_security_provider_links
    using (tenant_id = gba.current_tenant_id())
    with check (tenant_id = gba.current_tenant_id());
grant select, insert on gba.rental_security_provider_links to gba_runtime;

-- Rental branch scope:
create policy rental_security_provider_links_location_scope on gba.rental_security_provider_links
    as restrictive to gba_runtime
    using (gba.current_location_id() is null or exists (
        select 1 from gba.rental_securities s
        where s.tenant_id = rental_security_provider_links.tenant_id
          and s.id = rental_security_provider_links.security_id))
    with check (gba.current_location_id() is null or exists (
        select 1 from gba.rental_securities s
        where s.tenant_id = rental_security_provider_links.tenant_id
          and s.id = rental_security_provider_links.security_id));
