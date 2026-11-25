-- 0150_self_service_onboarding: controlled self-service business registration for
-- authenticated OIDC callers without elevated database privileges.
--
-- Security invariants:
--   * gba.self_service_signups is scoped to the verified caller (gba.current_auth_issuer(),
--     gba.current_auth_subject()) and idempotency key; FORCE ROW LEVEL SECURITY applies.
--   * gba_runtime receives INSERT on gba.tenants guarded by a RESTRICTIVE RLS policy
--     requiring: id = gba.current_tenant_id(), status = 'active', booking_state = 'not_live',
--     gba.current_user_id() IS NOT NULL, and a matching row in gba.self_service_signups
--     owned by the current verified caller. Any unguarded direct INSERT still fails with
--     SQLSTATE 42501 (insufficient_privilege).
--   * gba.tenant_hosts remains SELECT-only for gba_runtime (host routing stays governed).

create table gba.self_service_signups (
    id              uuid primary key default uuidv7(),
    issuer          text not null
                    constraint self_service_signups_issuer_format
                    check (issuer ~ '^https?://\S+$' and length(issuer) <= 500),
    subject         text not null
                    constraint self_service_signups_subject_length
                    check (length(subject) between 1 and 255),
    idempotency_key text not null
                    constraint self_service_signups_key_length
                    check (length(btrim(idempotency_key)) between 8 and 128),
    request_hash    text not null
                    constraint self_service_signups_hash_format
                    check (request_hash ~ '^[0-9a-f]{64}$'),
    user_id         uuid not null references gba.users (id),
    tenant_id       uuid not null,
    location_id     uuid not null,
    response_body   jsonb,
    created_at      timestamptz not null default now(),
    unique (issuer, subject, idempotency_key)
);

create index self_service_signups_tenant_idx
    on gba.self_service_signups (tenant_id, user_id);

alter table gba.self_service_signups enable row level security;
alter table gba.self_service_signups force row level security;

create policy self_service_signups_caller on gba.self_service_signups
    using (
        issuer = gba.current_auth_issuer()
        and subject = gba.current_auth_subject()
    )
    with check (
        issuer = gba.current_auth_issuer()
        and subject = gba.current_auth_subject()
        and user_id = gba.current_user_id()
    );

grant select, insert, update (response_body) on gba.self_service_signups to gba_runtime;

create policy tenants_runtime_self_service_insert on gba.tenants
    as restrictive
    for insert
    to gba_runtime
    with check (
        id = gba.current_tenant_id()
        and status = 'active'
        and booking_state = 'not_live'
        and gba.current_user_id() is not null
        and exists (
            select 1
            from gba.self_service_signups s
            where s.tenant_id = tenants.id
              and s.user_id = gba.current_user_id()
              and s.issuer = gba.current_auth_issuer()
              and s.subject = gba.current_auth_subject()
        )
    );

grant insert on gba.tenants to gba_runtime;
