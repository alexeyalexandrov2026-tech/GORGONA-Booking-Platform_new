-- K6b / ADR-0027, owner decisions of 2026-10-21 (K6 design defaults and the K6b detailed
-- decisions). Forward only; no existing row is changed.
--
-- A reconciler lists the events of an admitted connection from the Stripe API and records them
-- through the same inbox as webhooks. Their facts are the same; how they arrived is recorded on
-- the attestation: `stripe_api_v1` for a retrieved event, `stripe_snapshot_v1` (unchanged) for a
-- signed webhook. Each run of the reconciler leaves one permanent record with its counts and
-- outcome, so a failed run is visible and nothing is reported as received that was not.

alter table gba.provider_event_attestations
    drop constraint provider_event_attestations_verifier_check,
    add constraint provider_event_attestations_verifier_check
        check (verifier in ('stripe_snapshot_v1','stripe_api_v1'));
grant insert (verifier) on gba.provider_event_attestations to gba_receipt_writer;

create table gba.provider_reconciliation_runs (
    tenant_id uuid not null,
    id uuid not null default gen_random_uuid(),
    connection_id uuid not null,
    window_start timestamptz not null,
    window_end timestamptz not null,
    started_at timestamptz not null,
    pages integer not null check (pages >= 0),
    seen integer not null check (seen >= 0),
    recorded integer not null check (recorded >= 0),
    duplicates integer not null check (duplicates >= 0),
    conflicts integer not null check (conflicts >= 0),
    refused integer not null check (refused >= 0),
    outcome text not null check (outcome in ('completed','failed')),
    error_class text check (error_class ~ '^[A-Za-z][A-Za-z0-9_]{0,63}$'),
    finished_at timestamptz not null default now(),
    recorded_by text not null default session_user,
    primary key (tenant_id,id),
    check (window_start < window_end),
    check (seen = recorded + duplicates + conflicts + refused),
    check ((outcome = 'failed') = (error_class is not null)),
    foreign key (tenant_id,connection_id) references gba.provider_receipt_connections (tenant_id,id)
);

-- Only the receipt writer records a run, in its company, after it started; the database sets
-- when it finished and who recorded it.
create function gba.check_provider_reconciliation_run() returns trigger
language plpgsql set search_path=pg_catalog as $$
begin
    if not pg_catalog.pg_has_role(current_user,'gba_receipt_writer','USAGE')
       or pg_catalog.pg_has_role(current_user,'gba_runtime','MEMBER')
       or pg_catalog.pg_has_role(session_user,'gba_runtime','MEMBER')
       or new.tenant_id is distinct from gba.current_tenant_id()
       or gba.current_location_id() is not null
       or new.started_at>now() then
        raise exception using errcode='check_violation', message='provider reconciliation run refused';
    end if;
    new.finished_at := now();
    new.recorded_by := session_user;
    return new;
end;
$$;
revoke all on function gba.check_provider_reconciliation_run() from public;

alter table gba.provider_reconciliation_runs enable row level security;
alter table gba.provider_reconciliation_runs force row level security;
create policy provider_reconciliation_runs_tenant on gba.provider_reconciliation_runs
    using (tenant_id=gba.current_tenant_id()) with check (tenant_id=gba.current_tenant_id());
create policy provider_reconciliation_runs_company on gba.provider_reconciliation_runs as restrictive
    using (gba.current_location_id() is null) with check (gba.current_location_id() is null);

revoke all on gba.provider_reconciliation_runs from public;
grant select on gba.provider_reconciliation_runs to gba_receipt_writer,gba_runtime;
grant insert (tenant_id,connection_id,window_start,window_end,started_at,pages,seen,recorded,
    duplicates,conflicts,refused,outcome,error_class)
    on gba.provider_reconciliation_runs to gba_receipt_writer;

create trigger provider_reconciliation_runs_check before insert on gba.provider_reconciliation_runs
    for each row execute function gba.check_provider_reconciliation_run();
create trigger provider_reconciliation_runs_immutable before update or delete on gba.provider_reconciliation_runs
    for each row execute function gba.reject_ledger_mutation();
create trigger provider_reconciliation_runs_no_truncate before truncate on gba.provider_reconciliation_runs
    for each statement execute function gba.reject_provider_receipt_truncate();
