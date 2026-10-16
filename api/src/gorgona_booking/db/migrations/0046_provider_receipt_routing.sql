-- K1d: owner-provisioned verification authority and writer-only receipt routing.
-- A config names which server-held key may verify deliveries for one connection; it is
-- not operational admission. Rows hold opaque references and IDs only, never key material.
-- The owner provisions inside an explicit company context; the runtime and the receipt
-- writer may only revoke a config. No HTTP route, worker or financial effect is granted.

create table gba.provider_verification_configs (
    tenant_id uuid not null,
    id uuid not null,
    connection_id uuid not null,
    version integer not null check (version > 0),
    secret_ref text not null check (secret_ref ~ '^[a-z][a-z0-9-]{0,30}:[A-Za-z0-9][A-Za-z0-9._/-]{0,199}$' and secret_ref !~* '(^|[^A-Za-z0-9])(whsec|sk|rk|pk)_'),
    revoked boolean not null default false,
    created_by text not null default current_user,
    created_at timestamptz not null default now(),
    primary key (tenant_id,id),
    unique (tenant_id,connection_id,version),
    unique (tenant_id,connection_id,id),
    foreign key (tenant_id,connection_id) references gba.provider_receipt_connections (tenant_id,id)
);
-- At most one active version per connection; rotation revokes, then provisions the next.
create unique index provider_verification_configs_active
    on gba.provider_verification_configs (tenant_id,connection_id) where not revoked;

-- Resolves a server-generated ingress ID before any company context exists, like
-- tenant_hosts, but only for the receipt writer group and only to opaque IDs.
create table gba.provider_receipt_routes (
    ingress_id uuid primary key,
    tenant_id uuid not null,
    connection_id uuid not null,
    created_at timestamptz not null default now(),
    unique (tenant_id,connection_id),
    foreign key (tenant_id,connection_id) references gba.provider_receipt_connections (tenant_id,id)
);

create function gba.guard_provider_verification_config() returns trigger
language plpgsql set search_path=pg_catalog as $$
declare
    binding gba.provider_receipt_connections;
begin
    if tg_op='INSERT' then
        if new.tenant_id is distinct from gba.current_tenant_id() or gba.current_location_id() is not null then
            raise exception using errcode='check_violation', message='verification config requires company scope';
        end if;
        select c.* into binding from gba.provider_receipt_connections c
            where c.tenant_id=new.tenant_id and c.id=new.connection_id for share;
        if binding.id is null or binding.revoked or new.revoked then
            raise exception using errcode='check_violation', message='verification config connection refused';
        end if;
        new.version := coalesce((select max(v.version) from gba.provider_verification_configs v
            where v.tenant_id=new.tenant_id and v.connection_id=new.connection_id),0)+1;
        new.created_by := current_user;
        new.created_at := now();
        return new;
    end if;
    if tg_op='DELETE' or (to_jsonb(new)-'revoked') is distinct from (to_jsonb(old)-'revoked')
       or (old.revoked and not new.revoked) then
        raise exception using errcode='check_violation', message='verification config is permanent; revoke it instead';
    end if;
    return new;
end;
$$;
revoke all on function gba.guard_provider_verification_config() from public;

-- Runs after provider_event_attestations_check (trigger name order), which sets connection_id.
create function gba.check_provider_attestation_config() returns trigger
language plpgsql set search_path=pg_catalog as $$
declare
    authority gba.provider_verification_configs;
begin
    select v.* into authority from gba.provider_verification_configs v
        where v.tenant_id=new.tenant_id and v.id=new.verification_config_id for share;
    if authority.id is null or authority.revoked
       or authority.connection_id is distinct from new.connection_id then
        raise exception using errcode='check_violation', message='receipt attestation config refused';
    end if;
    return new;
end;
$$;
revoke all on function gba.check_provider_attestation_config() from public;

alter table gba.provider_verification_configs enable row level security;
alter table gba.provider_verification_configs force row level security;
alter table gba.provider_receipt_routes enable row level security;
alter table gba.provider_receipt_routes force row level security;
create policy provider_verification_configs_tenant on gba.provider_verification_configs
    using (tenant_id=gba.current_tenant_id()) with check (tenant_id=gba.current_tenant_id());
create policy provider_verification_configs_company on gba.provider_verification_configs as restrictive
    using (gba.current_location_id() is null) with check (gba.current_location_id() is null);
create policy provider_receipt_routes_resolve on gba.provider_receipt_routes
    for select to gba_receipt_writer using (true);
create policy provider_receipt_routes_provision on gba.provider_receipt_routes
    for insert with check (tenant_id=gba.current_tenant_id());
create policy provider_receipt_routes_company on gba.provider_receipt_routes as restrictive
    for insert with check (gba.current_location_id() is null);
revoke all on gba.provider_verification_configs,gba.provider_receipt_routes from public;
grant select on gba.provider_verification_configs to gba_runtime,gba_receipt_writer;
-- UPDATE on one column also permits SELECT FOR SHARE. The trigger only permits revocation.
grant update (revoked) on gba.provider_verification_configs to gba_runtime,gba_receipt_writer;
grant select on gba.provider_receipt_routes to gba_receipt_writer;
create trigger provider_verification_configs_guard before insert or update or delete
    on gba.provider_verification_configs for each row execute function gba.guard_provider_verification_config();
create trigger provider_receipt_routes_immutable before update or delete on gba.provider_receipt_routes
    for each row execute function gba.reject_ledger_mutation();

-- Every attestation names a config of its own connection. A K1c attestation has no such
-- authority, so this migration is refused rather than back-filled. Row security hides
-- every company's rows from the owner here, and the key validation below would not see
-- them either: a temporary policy of the migration owner makes the check complete. It is
-- dropped in the same transaction.
create policy k1d_upgrade_owner_check on gba.provider_event_attestations
    for select to current_user using (true);
do $$
begin
    if exists (select 1 from gba.provider_event_attestations) then
        raise exception using errcode='check_violation',
            message='K1c attestations have no verification authority; upgrade refused';
    end if;
end;
$$;
drop policy k1d_upgrade_owner_check on gba.provider_event_attestations;
alter table gba.provider_event_attestations add constraint provider_event_attestations_config_fkey
    foreign key (tenant_id,connection_id,verification_config_id)
    references gba.provider_verification_configs (tenant_id,connection_id,id);
create trigger provider_event_attestations_config before insert on gba.provider_event_attestations
    for each row execute function gba.check_provider_attestation_config();
