-- Migration 0148: SPECIAL-04 Staffing, advisory, organizations and public admin (ADR-0045)
-- Profiles 30, 31, 36, 39 (completing 39/39 industry profile coverage).

create table gba.civic_programs (
  id uuid primary key,
  tenant_id uuid not null references gba.tenants(id) on delete cascade,
  location_id uuid not null,
  program_domain text not null check (
    program_domain in (
      'advisory_engagement',
      'staffing_requisition',
      'membership_program',
      'public_service_program'
    )
  ),
  code text not null check (length(btrim(code)) between 1 and 64),
  title text not null check (length(btrim(title)) between 1 and 200),
  status text not null default 'active' check (status in ('active', 'paused', 'closed')),
  requires_dual_review boolean not null default false,
  revision int not null default 1 check (revision >= 1),
  recorded_by uuid not null references gba.users(id),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (tenant_id, id),
  unique (tenant_id, location_id, id),
  unique (tenant_id, location_id, code),
  foreign key (tenant_id, location_id)
    references gba.locations(tenant_id, id) on delete cascade
);

create index civic_programs_tenant_location_idx
  on gba.civic_programs(tenant_id, location_id, status, code);

create table gba.civic_cases (
  id uuid primary key,
  tenant_id uuid not null references gba.tenants(id) on delete cascade,
  location_id uuid not null,
  program_id uuid not null,
  subject_counterparty_id uuid not null,
  case_number text not null check (length(btrim(case_number)) between 1 and 64),
  status text not null default 'submitted' check (
    status in ('submitted', 'in_review', 'approved', 'rejected', 'closed')
  ),
  summary text not null check (length(btrim(summary)) between 1 and 300),
  decision_notes text not null default '' check (length(decision_notes) <= 2000),
  submitted_by uuid not null references gba.users(id),
  decided_by uuid null references gba.users(id),
  decided_at timestamptz null,
  revision int not null default 1 check (revision >= 1),
  recorded_by uuid not null references gba.users(id),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (tenant_id, id),
  unique (tenant_id, location_id, id),
  unique (tenant_id, location_id, case_number),
  foreign key (tenant_id, location_id)
    references gba.locations(tenant_id, id) on delete cascade,
  foreign key (tenant_id, location_id, program_id)
    references gba.civic_programs(tenant_id, location_id, id) on delete cascade,
  foreign key (tenant_id, subject_counterparty_id)
    references gba.counterparties(tenant_id, id),
  check (
    (status not in ('approved', 'rejected'))
    or (decided_by is not null and decided_at is not null)
  )
);

create index civic_cases_program_idx
  on gba.civic_cases(tenant_id, location_id, program_id, status, created_at desc);

create table gba.civic_allocations (
  id uuid primary key,
  tenant_id uuid not null references gba.tenants(id) on delete cascade,
  location_id uuid not null,
  case_id uuid not null,
  allocation_kind text not null check (
    allocation_kind in (
      'staffing_placement',
      'advisory_mandate',
      'membership_award',
      'grant_award',
      'public_permit'
    )
  ),
  reference_code text not null check (length(btrim(reference_code)) between 1 and 64),
  status text not null default 'active' check (
    status in ('active', 'suspended', 'revoked', 'expired')
  ),
  effective_from date not null,
  effective_until date null,
  revision int not null default 1 check (revision >= 1),
  recorded_by uuid not null references gba.users(id),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (tenant_id, id),
  unique (tenant_id, location_id, reference_code),
  foreign key (tenant_id, location_id)
    references gba.locations(tenant_id, id) on delete cascade,
  foreign key (tenant_id, location_id, case_id)
    references gba.civic_cases(tenant_id, location_id, id) on delete cascade,
  check (effective_until is null or effective_until >= effective_from)
);

create index civic_allocations_case_idx
  on gba.civic_allocations(tenant_id, location_id, case_id, status);

create table gba.civic_audit_events (
  id uuid primary key,
  tenant_id uuid not null references gba.tenants(id) on delete cascade,
  location_id uuid not null,
  case_id uuid not null,
  event_kind text not null check (
    event_kind in (
      'compliance_check',
      'conflict_disclosure',
      'review_note',
      'public_notice',
      'appeal_logged'
    )
  ),
  details text not null check (length(btrim(details)) between 1 and 2000),
  recorded_by uuid not null references gba.users(id),
  created_at timestamptz not null default now(),
  unique (tenant_id, id),
  foreign key (tenant_id, location_id)
    references gba.locations(tenant_id, id) on delete cascade,
  foreign key (tenant_id, location_id, case_id)
    references gba.civic_cases(tenant_id, location_id, id) on delete cascade
);

create index civic_audit_events_case_idx
  on gba.civic_audit_events(tenant_id, location_id, case_id, created_at desc);

create or replace function gba.reject_civic_audit_event_mutation()
returns trigger
language plpgsql
as $$
begin
  raise exception 'civic audit events are insert-only'
    using errcode = '22023';
end;
$$;

create trigger civic_audit_events_insert_only
  before update or delete on gba.civic_audit_events
  for each row execute function gba.reject_civic_audit_event_mutation();

-- Tenant isolation, RLS, grants and module gates (all before branch-scope marker)
alter table gba.civic_programs enable row level security;
alter table gba.civic_programs force row level security;
create policy civic_programs_tenant_isolation on gba.civic_programs
  using (tenant_id = gba.current_tenant_id())
  with check (tenant_id = gba.current_tenant_id());

alter table gba.civic_cases enable row level security;
alter table gba.civic_cases force row level security;
create policy civic_cases_tenant_isolation on gba.civic_cases
  using (tenant_id = gba.current_tenant_id())
  with check (tenant_id = gba.current_tenant_id());

alter table gba.civic_allocations enable row level security;
alter table gba.civic_allocations force row level security;
create policy civic_allocations_tenant_isolation on gba.civic_allocations
  using (tenant_id = gba.current_tenant_id())
  with check (tenant_id = gba.current_tenant_id());

alter table gba.civic_audit_events enable row level security;
alter table gba.civic_audit_events force row level security;
create policy civic_audit_events_tenant_isolation on gba.civic_audit_events
  using (tenant_id = gba.current_tenant_id())
  with check (tenant_id = gba.current_tenant_id());

grant select, insert, update on gba.civic_programs to gba_runtime;
grant select, insert, update on gba.civic_cases to gba_runtime;
grant select, insert, update on gba.civic_allocations to gba_runtime;
grant select, insert on gba.civic_audit_events to gba_runtime;

create trigger civic_programs_require_module
  before insert on gba.civic_programs
  for each row execute function gba.require_enabled_module('public_civic');

create trigger civic_cases_require_module
  before insert on gba.civic_cases
  for each row execute function gba.require_enabled_module('public_civic');

create trigger civic_allocations_require_module
  before insert on gba.civic_allocations
  for each row execute function gba.require_enabled_module('public_civic');

create trigger civic_audit_events_require_module
  before insert on gba.civic_audit_events
  for each row execute function gba.require_enabled_module('public_civic');

-- Public civic branch scope:
create policy civic_programs_location_scope on gba.civic_programs
  as restrictive to gba_runtime
  using (gba.current_location_id() is null or location_id = gba.current_location_id())
  with check (gba.current_location_id() is null or location_id = gba.current_location_id());

create policy civic_cases_location_scope on gba.civic_cases
  as restrictive to gba_runtime
  using (gba.current_location_id() is null or location_id = gba.current_location_id())
  with check (gba.current_location_id() is null or location_id = gba.current_location_id());

create policy civic_allocations_location_scope on gba.civic_allocations
  as restrictive to gba_runtime
  using (gba.current_location_id() is null or location_id = gba.current_location_id())
  with check (gba.current_location_id() is null or location_id = gba.current_location_id());

create policy civic_audit_events_location_scope on gba.civic_audit_events
  as restrictive to gba_runtime
  using (gba.current_location_id() is null or location_id = gba.current_location_id())
  with check (gba.current_location_id() is null or location_id = gba.current_location_id());
