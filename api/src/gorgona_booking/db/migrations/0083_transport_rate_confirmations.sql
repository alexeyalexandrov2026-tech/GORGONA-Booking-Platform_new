-- N3 (package N): rate confirmations of accepted tenders. docs/plan/PACKAGE_N3_DESIGN_2026-10-27.md.
-- Insert-only versions per tender; version 1 carries the tender's rate and terms and is agreed by the
-- acceptance. A later version is a proposal, in force only once the carrier's agreement is recorded.
create table gba.transport_rate_confirmations (
    tenant_id uuid not null references gba.tenants(id),
    tender_id uuid not null,
    revision integer not null constraint transport_rate_confirmations_revision_check
        check (revision > 0),
    basis text not null constraint transport_rate_confirmations_basis_check
        check (basis in ('fixed', 'per_mile')),
    amount numeric(20, 3) not null constraint transport_rate_confirmations_amount_check
        check (amount > 0),
    terms text not null constraint transport_rate_confirmations_terms_check
        check (length(btrim(terms)) between 1 and 2000),
    document_id uuid,
    proposed_at timestamptz not null,
    created_by uuid not null references gba.users(id),
    created_at timestamptz not null default now(),
    primary key (tenant_id, tender_id, revision),
    foreign key (tenant_id, tender_id) references gba.transport_tenders (tenant_id, id),
    foreign key (tenant_id, document_id) references gba.documents (tenant_id, id)
);
create table gba.transport_rate_confirmation_answers (
    tenant_id uuid not null references gba.tenants(id),
    tender_id uuid not null,
    revision integer not null,
    kind text not null constraint transport_rate_confirmation_answers_kind_check
        check (kind in ('agreed', 'declined')),
    source text not null constraint transport_rate_confirmation_answers_source_check
        check (source in ('email', 'phone', 'load_board', 'other')),
    occurred_at timestamptz not null,
    created_by uuid not null references gba.users(id),
    created_at timestamptz not null default now(),
    primary key (tenant_id, tender_id, revision),
    foreign key (tenant_id, tender_id, revision)
        references gba.transport_rate_confirmations (tenant_id, tender_id, revision)
);

-- Tenders accepted before 0083 get version 1, agreed by their acceptance.
insert into gba.transport_rate_confirmations (tenant_id, tender_id, revision, basis, amount, terms,
                                              proposed_at, created_by)
select t.tenant_id, t.id, 1, t.basis, t.amount, t.terms, a.occurred_at, a.created_by
  from gba.transport_tenders t
  join gba.transport_tender_answers a
    on a.tenant_id = t.tenant_id and a.tender_id = t.id and a.kind = 'accepted';
insert into gba.transport_rate_confirmation_answers (tenant_id, tender_id, revision, kind, source,
                                                     occurred_at, created_by)
select a.tenant_id, a.tender_id, 1, 'agreed', a.source, a.occurred_at, a.created_by
  from gba.transport_tender_answers a
 where a.kind = 'accepted';

-- A version follows the answered previous one on an accepted, not withdrawn tender, never earlier than
-- the last answer; an answer answers the latest version once, never before its proposal.
create function gba.guard_transport_rate_confirmation() returns trigger language plpgsql as $$
declare
    latest integer;
    open boolean;
    answered timestamptz;
begin
    perform pg_catalog.pg_advisory_xact_lock(
        pg_catalog.hashtextextended('gba:rate-confirmation:' || new.tender_id::text, 0));
    if not exists (
        select 1 from gba.transport_tender_answers a
         where a.tenant_id = new.tenant_id and a.tender_id = new.tender_id and a.kind = 'accepted')
       or exists (
        select 1 from gba.transport_tender_answers a
         where a.tenant_id = new.tenant_id and a.tender_id = new.tender_id and a.kind = 'withdrawn') then
        raise exception using errcode = 'check_violation',
            constraint = 'transport_rate_confirmations_state_check',
            message = 'only an accepted tender has rate confirmations';
    end if;
    select max(c.revision), bool_or(x.revision is null), max(x.occurred_at)
      into latest, open, answered
      from gba.transport_rate_confirmations c
      left join gba.transport_rate_confirmation_answers x
        on x.tenant_id = c.tenant_id and x.tender_id = c.tender_id and x.revision = c.revision
     where c.tenant_id = new.tenant_id and c.tender_id = new.tender_id;
    if new.revision <> coalesce(latest, 0) + 1 or coalesce(open, false) then
        raise exception using errcode = 'check_violation',
            constraint = 'transport_rate_confirmations_revision_check',
            message = 'a version follows the answered previous one';
    end if;
    if answered is not null and new.proposed_at < answered then
        raise exception using errcode = 'check_violation',
            constraint = 'transport_rate_confirmations_time_check',
            message = 'a proposal follows the previous answer';
    end if;
    return new;
end;
$$;
revoke all on function gba.guard_transport_rate_confirmation() from public;
create trigger transport_rate_confirmations_guard before insert on gba.transport_rate_confirmations
    for each row execute function gba.guard_transport_rate_confirmation();
create function gba.guard_transport_rate_confirmation_answer() returns trigger language plpgsql as $$
declare
    version gba.transport_rate_confirmations%rowtype;
begin
    perform pg_catalog.pg_advisory_xact_lock(
        pg_catalog.hashtextextended('gba:rate-confirmation:' || new.tender_id::text, 0));
    select * into version from gba.transport_rate_confirmations c
     where c.tenant_id = new.tenant_id and c.tender_id = new.tender_id and c.revision = new.revision;
    if exists (
        select 1 from gba.transport_rate_confirmations c
         where c.tenant_id = new.tenant_id and c.tender_id = new.tender_id
           and c.revision > new.revision)
       or exists (
        select 1 from gba.transport_rate_confirmation_answers x
         where x.tenant_id = new.tenant_id and x.tender_id = new.tender_id
           and x.revision = new.revision) then
        raise exception using errcode = 'check_violation',
            constraint = 'transport_rate_confirmation_answers_revision_check',
            message = 'an answer answers the latest version once';
    end if;
    if new.occurred_at < version.proposed_at then
        raise exception using errcode = 'check_violation',
            constraint = 'transport_rate_confirmation_answers_time_check',
            message = 'an answer follows the proposal';
    end if;
    return new;
end;
$$;
revoke all on function gba.guard_transport_rate_confirmation_answer() from public;
create trigger transport_rate_confirmation_answers_guard
    before insert on gba.transport_rate_confirmation_answers
    for each row execute function gba.guard_transport_rate_confirmation_answer();

-- Writes need the transport module (ADR-0019 gate).
create trigger transport_rate_confirmations_module_gate
    before insert on gba.transport_rate_confirmations
    for each row execute function gba.require_enabled_module('transport');
create trigger transport_rate_confirmation_answers_module_gate
    before insert on gba.transport_rate_confirmation_answers
    for each row execute function gba.require_enabled_module('transport');

alter table gba.transport_rate_confirmations enable row level security;
alter table gba.transport_rate_confirmations force row level security;
alter table gba.transport_rate_confirmation_answers enable row level security;
alter table gba.transport_rate_confirmation_answers force row level security;
create policy transport_rate_confirmations_tenant_isolation on gba.transport_rate_confirmations
    using (tenant_id = gba.current_tenant_id())
    with check (tenant_id = gba.current_tenant_id());
create policy transport_rate_confirmation_answers_tenant_isolation
    on gba.transport_rate_confirmation_answers
    using (tenant_id = gba.current_tenant_id())
    with check (tenant_id = gba.current_tenant_id());
grant select on gba.transport_rate_confirmations, gba.transport_rate_confirmation_answers
    to gba_runtime;
grant insert (tenant_id, tender_id, revision, basis, amount, terms, document_id, proposed_at, created_by)
    on gba.transport_rate_confirmations to gba_runtime;
grant insert (tenant_id, tender_id, revision, kind, source, occurred_at, created_by)
    on gba.transport_rate_confirmation_answers to gba_runtime;

-- Rate confirmation branch scope: brokerage is company-wide; a branch-limited session sees none of it.
create policy transport_rate_confirmations_company on gba.transport_rate_confirmations
    as restrictive to gba_runtime
    using (gba.current_location_id() is null)
    with check (gba.current_location_id() is null);
create policy transport_rate_confirmation_answers_company on gba.transport_rate_confirmation_answers
    as restrictive to gba_runtime
    using (gba.current_location_id() is null)
    with check (gba.current_location_id() is null);
