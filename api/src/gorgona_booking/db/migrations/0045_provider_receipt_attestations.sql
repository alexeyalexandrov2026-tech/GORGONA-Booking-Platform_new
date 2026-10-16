-- K1c: a separately permissioned verifier may attest a minimal archived delivery.
-- Bootstrap creates the NOLOGIN group before owner migrations. No operational
-- admission, public routing, worker or financial effect is granted by these rows.

grant usage on schema gba to gba_receipt_writer;
grant execute on function gba.current_tenant_id(),gba.current_location_id(),
    gba.provider_receipt_integer(jsonb,numeric),gba.provider_receipt_facts_valid(jsonb)
    to gba_receipt_writer;
grant select on gba.provider_receipt_connections,gba.provider_event_inbox,
    gba.provider_event_deliveries to gba_receipt_writer;
-- FOR SHARE needs UPDATE on a column; the existing trigger permits only revocation.
grant update (revoked) on gba.provider_receipt_connections to gba_receipt_writer;
grant insert (tenant_id,id,connection_id,facts) on gba.provider_event_inbox to gba_receipt_writer;
grant insert (tenant_id,event_id,delivery_sha256,facts) on gba.provider_event_deliveries
    to gba_receipt_writer;

create table gba.provider_event_attestations (
    tenant_id uuid not null,
    event_id uuid not null,
    delivery_sha256 text not null check (delivery_sha256 ~ '^[0-9a-f]{64}$'),
    verification_config_id uuid not null,
    connection_id uuid not null,
    book_id uuid not null,
    verifier text not null default 'stripe_snapshot_v1' check (verifier='stripe_snapshot_v1'),
    verified_by text not null default current_user,
    verified_at timestamptz not null default now(),
    primary key (tenant_id,event_id,delivery_sha256),
    foreign key (tenant_id,event_id,delivery_sha256)
        references gba.provider_event_deliveries (tenant_id,event_id,delivery_sha256),
    foreign key (tenant_id,connection_id) references gba.provider_receipt_connections (tenant_id,id),
    foreign key (tenant_id,book_id) references gba.ledger_books (tenant_id,id)
);

create function gba.check_provider_receipt_attestation() returns trigger
language plpgsql set search_path=pg_catalog as $$
declare
    binding gba.provider_receipt_connections;
    facts jsonb;
begin
    if not pg_catalog.pg_has_role(current_user,'gba_receipt_writer','USAGE')
       or pg_catalog.pg_has_role(current_user,'gba_runtime','MEMBER')
       or pg_catalog.pg_has_role(session_user,'gba_runtime','MEMBER')
       or new.tenant_id is distinct from gba.current_tenant_id()
       or gba.current_location_id() is not null then
        raise exception using errcode='check_violation', message='receipt attestation writer refused';
    end if;
    select c.* into binding from gba.provider_receipt_connections c
        join gba.provider_event_inbox e on e.tenant_id=c.tenant_id and e.connection_id=c.id
        where e.tenant_id=new.tenant_id and e.id=new.event_id for share of c;
    select d.facts into facts from gba.provider_event_deliveries d
        where d.tenant_id=new.tenant_id and d.event_id=new.event_id
          and d.delivery_sha256=new.delivery_sha256;
    if binding.id is null or binding.revoked or facts is null
       or binding.namespace<>facts->>'namespace' or binding.account_id<>facts->>'account_id'
       or binding.api_version<>facts->>'api_version' then
        raise exception using errcode='check_violation', message='receipt attestation binding refused';
    end if;
    new.connection_id := binding.id;
    new.book_id := binding.book_id;
    new.verified_by := current_user;
    return new;
end;
$$;
revoke all on function gba.check_provider_receipt_attestation() from public;
alter table gba.provider_event_attestations enable row level security;
alter table gba.provider_event_attestations force row level security;
create policy provider_event_attestations_tenant on gba.provider_event_attestations
    using (tenant_id=gba.current_tenant_id()) with check (tenant_id=gba.current_tenant_id());
create policy provider_event_attestations_company on gba.provider_event_attestations as restrictive
    using (gba.current_location_id() is null) with check (gba.current_location_id() is null);
revoke all on gba.provider_event_attestations from public;
grant select on gba.provider_event_attestations to gba_runtime,gba_receipt_writer;
grant insert (tenant_id,event_id,delivery_sha256,verification_config_id)
    on gba.provider_event_attestations to gba_receipt_writer;
create trigger provider_event_attestations_check before insert on gba.provider_event_attestations
    for each row execute function gba.check_provider_receipt_attestation();
create trigger provider_event_attestations_immutable before update or delete
    on gba.provider_event_attestations for each row execute function gba.reject_ledger_mutation();
