-- K1j, review finding IR-07 / ADR-0027. Forward only; no row is changed.
--
-- A revocation of a receipt connection or a verification config was a bare boolean: nothing
-- said who revoked, when, or whether a key was rotated or compromised. A revocation now names
-- its reason; the trigger records the time and the session login (session_user, the login
-- behind any SET ROLE). The record is permanent and all-or-nothing. Rows revoked before this
-- migration keep an empty record, meaning "revoked, record unknown"; no value is invented, and
-- a new revocation without a reason is refused, so no new row reaches that state.
-- Attestations and configs record the session login as well.

alter table gba.provider_receipt_connections
    add column revoked_reason text,
    add column revoked_at timestamptz,
    add column revoked_by text;
alter table gba.provider_receipt_connections add constraint provider_receipt_connections_revocation
    check ((revoked_reason is null) = (revoked_at is null) and (revoked_at is null) = (revoked_by is null)
        and (revoked or revoked_at is null)
        and (revoked_reason is null or revoked_reason in ('compromise','retired')));
alter table gba.provider_verification_configs
    add column revoked_reason text,
    add column revoked_at timestamptz,
    add column revoked_by text;
alter table gba.provider_verification_configs add constraint provider_verification_configs_revocation
    check ((revoked_reason is null) = (revoked_at is null) and (revoked_at is null) = (revoked_by is null)
        and (revoked or revoked_at is null)
        and (revoked_reason is null or revoked_reason in ('rotation','compromise','retired')));

create or replace function gba.guard_provider_receipt_connection() returns trigger
language plpgsql set search_path=pg_catalog as $$
begin
    if tg_op='DELETE'
       or (to_jsonb(new)-array['revoked','revoked_reason','revoked_at','revoked_by'])
          is distinct from (to_jsonb(old)-array['revoked','revoked_reason','revoked_at','revoked_by'])
       or (old.revoked and to_jsonb(new) is distinct from to_jsonb(old)) then
        raise exception using errcode='check_violation', message='receipt connection identity and revocation are permanent';
    end if;
    if new.revoked and not old.revoked then
        if new.revoked_reason is null then
            raise exception using errcode='check_violation', message='receipt connection revocation needs a reason';
        end if;
        new.revoked_at := now();
        new.revoked_by := session_user;
    elsif (new.revoked_reason,new.revoked_at,new.revoked_by)
          is distinct from (old.revoked_reason,old.revoked_at,old.revoked_by) then
        raise exception using errcode='check_violation', message='receipt connection revocation fields need a revocation';
    end if;
    return new;
end;
$$;

create or replace function gba.guard_provider_verification_config() returns trigger
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
        new.created_by := session_user;
        new.created_at := now();
        return new;
    end if;
    if tg_op='DELETE'
       or (to_jsonb(new)-array['revoked','revoked_reason','revoked_at','revoked_by'])
          is distinct from (to_jsonb(old)-array['revoked','revoked_reason','revoked_at','revoked_by'])
       or (old.revoked and to_jsonb(new) is distinct from to_jsonb(old)) then
        raise exception using errcode='check_violation', message='verification config is permanent; revoke it instead';
    end if;
    if new.revoked and not old.revoked then
        if new.revoked_reason is null then
            raise exception using errcode='check_violation', message='verification config revocation needs a reason';
        end if;
        new.revoked_at := now();
        new.revoked_by := session_user;
    elsif (new.revoked_reason,new.revoked_at,new.revoked_by)
          is distinct from (old.revoked_reason,old.revoked_at,old.revoked_by) then
        raise exception using errcode='check_violation', message='verification config revocation fields need a revocation';
    end if;
    return new;
end;
$$;

create or replace function gba.check_provider_receipt_attestation() returns trigger
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
    new.verified_by := session_user;
    return new;
end;
$$;

-- A revocation names its reason; its time and login are written by the trigger only.
grant update (revoked_reason) on gba.provider_receipt_connections to gba_runtime,gba_receipt_writer;
grant update (revoked_reason) on gba.provider_verification_configs to gba_runtime,gba_receipt_writer;
