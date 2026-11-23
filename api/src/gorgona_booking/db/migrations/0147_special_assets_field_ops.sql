-- Migration 0147: SPECIAL-03 Assets, inspections, work orders and safety incidents (ADR-0044)
-- Profiles 27, 28, 29, 32, 33, 34 (Agriculture, Utilities, Mining, Security, Facilities, Waste).

create table gba.managed_assets (
  id uuid primary key,
  tenant_id uuid not null references gba.tenants(id) on delete cascade,
  location_id uuid not null,
  owner_counterparty_id uuid null,
  asset_domain text not null check (
    asset_domain in (
      'agriculture_plot',
      'utility_infrastructure',
      'mining_equipment',
      'security_post',
      'facility_system',
      'environmental_site'
    )
  ),
  code text not null check (length(btrim(code)) between 1 and 64),
  name text not null check (length(btrim(name)) between 1 and 200),
  status text not null default 'active' check (
    status in ('active', 'maintenance', 'out_of_service', 'decommissioned')
  ),
  serial_or_parcel text not null default '' check (length(serial_or_parcel) <= 120),
  next_inspection_due date null,
  revision int not null default 1 check (revision >= 1),
  recorded_by uuid not null references gba.users(id),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (tenant_id, id),
  unique (tenant_id, location_id, id),
  unique (tenant_id, location_id, code),
  foreign key (tenant_id, location_id)
    references gba.locations(tenant_id, id) on delete cascade,
  foreign key (tenant_id, owner_counterparty_id)
    references gba.counterparties(tenant_id, id)
);

create index managed_assets_tenant_location_idx
  on gba.managed_assets(tenant_id, location_id, status, code);

create table gba.asset_inspections (
  id uuid primary key,
  tenant_id uuid not null references gba.tenants(id) on delete cascade,
  location_id uuid not null,
  asset_id uuid not null,
  inspection_kind text not null check (
    inspection_kind in ('safety', 'environmental', 'patrol', 'meter_reading', 'preventive')
  ),
  outcome text not null check (outcome in ('passed', 'attention_required', 'failed')),
  meter_reading numeric(14, 3) null check (meter_reading is null or meter_reading >= 0),
  notes text not null default '' check (length(notes) <= 2000),
  inspected_at timestamptz not null default now(),
  recorded_by uuid not null references gba.users(id),
  created_at timestamptz not null default now(),
  unique (tenant_id, id),
  unique (tenant_id, location_id, id),
  foreign key (tenant_id, location_id)
    references gba.locations(tenant_id, id) on delete cascade,
  foreign key (tenant_id, location_id, asset_id)
    references gba.managed_assets(tenant_id, location_id, id) on delete cascade
);

create index asset_inspections_asset_idx
  on gba.asset_inspections(tenant_id, location_id, asset_id, inspected_at desc);

create table gba.asset_work_orders (
  id uuid primary key,
  tenant_id uuid not null references gba.tenants(id) on delete cascade,
  location_id uuid not null,
  asset_id uuid not null,
  inspection_id uuid null,
  work_kind text not null check (
    work_kind in (
      'preventive',
      'corrective',
      'cleaning',
      'patrol_response',
      'waste_collection',
      'remediation'
    )
  ),
  priority text not null default 'normal' check (
    priority in ('low', 'normal', 'high', 'critical')
  ),
  status text not null default 'open' check (
    status in ('open', 'in_progress', 'completed', 'cancelled')
  ),
  summary text not null check (length(btrim(summary)) between 1 and 300),
  completion_notes text not null default '' check (length(completion_notes) <= 2000),
  due_at timestamptz null,
  completed_at timestamptz null,
  revision int not null default 1 check (revision >= 1),
  recorded_by uuid not null references gba.users(id),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (tenant_id, id),
  foreign key (tenant_id, location_id)
    references gba.locations(tenant_id, id) on delete cascade,
  foreign key (tenant_id, location_id, asset_id)
    references gba.managed_assets(tenant_id, location_id, id) on delete cascade,
  foreign key (tenant_id, location_id, inspection_id)
    references gba.asset_inspections(tenant_id, location_id, id),
  check ((status = 'completed') = (completed_at is not null))
);

create index asset_work_orders_asset_idx
  on gba.asset_work_orders(tenant_id, location_id, asset_id, status, created_at desc);

create table gba.asset_safety_incidents (
  id uuid primary key,
  tenant_id uuid not null references gba.tenants(id) on delete cascade,
  location_id uuid not null,
  asset_id uuid not null,
  incident_kind text not null check (
    incident_kind in (
      'safety_hazard',
      'environmental_spill',
      'security_breach',
      'utility_outage',
      'equipment_failure'
    )
  ),
  severity text not null check (severity in ('low', 'medium', 'high', 'critical')),
  status text not null default 'open' check (status in ('open', 'contained', 'resolved')),
  description text not null check (length(btrim(description)) between 1 and 2000),
  resolution_summary text not null default '' check (length(resolution_summary) <= 2000),
  occurred_at timestamptz not null default now(),
  resolved_at timestamptz null,
  revision int not null default 1 check (revision >= 1),
  recorded_by uuid not null references gba.users(id),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (tenant_id, id),
  foreign key (tenant_id, location_id)
    references gba.locations(tenant_id, id) on delete cascade,
  foreign key (tenant_id, location_id, asset_id)
    references gba.managed_assets(tenant_id, location_id, id) on delete cascade,
  check ((status = 'resolved') = (resolved_at is not null))
);

create index asset_safety_incidents_asset_idx
  on gba.asset_safety_incidents(tenant_id, location_id, asset_id, status, severity);

create or replace function gba.reject_asset_inspection_mutation()
returns trigger
language plpgsql
as $$
begin
  raise exception 'asset inspections are insert-only'
    using errcode = '22023';
end;
$$;

create trigger asset_inspections_insert_only
  before update or delete on gba.asset_inspections
  for each row execute function gba.reject_asset_inspection_mutation();

-- Tenant isolation, RLS, grants and module gates (all before branch-scope marker)
alter table gba.managed_assets enable row level security;
alter table gba.managed_assets force row level security;
create policy managed_assets_tenant_isolation on gba.managed_assets
  using (tenant_id = gba.current_tenant_id())
  with check (tenant_id = gba.current_tenant_id());

alter table gba.asset_inspections enable row level security;
alter table gba.asset_inspections force row level security;
create policy asset_inspections_tenant_isolation on gba.asset_inspections
  using (tenant_id = gba.current_tenant_id())
  with check (tenant_id = gba.current_tenant_id());

alter table gba.asset_work_orders enable row level security;
alter table gba.asset_work_orders force row level security;
create policy asset_work_orders_tenant_isolation on gba.asset_work_orders
  using (tenant_id = gba.current_tenant_id())
  with check (tenant_id = gba.current_tenant_id());

alter table gba.asset_safety_incidents enable row level security;
alter table gba.asset_safety_incidents force row level security;
create policy asset_safety_incidents_tenant_isolation on gba.asset_safety_incidents
  using (tenant_id = gba.current_tenant_id())
  with check (tenant_id = gba.current_tenant_id());

grant select, insert, update on gba.managed_assets to gba_runtime;
grant select, insert on gba.asset_inspections to gba_runtime;
grant select, insert, update on gba.asset_work_orders to gba_runtime;
grant select, insert, update on gba.asset_safety_incidents to gba_runtime;

create trigger managed_assets_require_module
  before insert on gba.managed_assets
  for each row execute function gba.require_enabled_module('assets');

create trigger asset_inspections_require_module
  before insert on gba.asset_inspections
  for each row execute function gba.require_enabled_module('assets');

create trigger asset_work_orders_require_module
  before insert on gba.asset_work_orders
  for each row execute function gba.require_enabled_module('assets');

create trigger asset_safety_incidents_require_module
  before insert on gba.asset_safety_incidents
  for each row execute function gba.require_enabled_module('assets');

-- Assets branch scope:
create policy managed_assets_location_scope on gba.managed_assets
  as restrictive to gba_runtime
  using (gba.current_location_id() is null or location_id = gba.current_location_id())
  with check (gba.current_location_id() is null or location_id = gba.current_location_id());

create policy asset_inspections_location_scope on gba.asset_inspections
  as restrictive to gba_runtime
  using (gba.current_location_id() is null or location_id = gba.current_location_id())
  with check (gba.current_location_id() is null or location_id = gba.current_location_id());

create policy asset_work_orders_location_scope on gba.asset_work_orders
  as restrictive to gba_runtime
  using (gba.current_location_id() is null or location_id = gba.current_location_id())
  with check (gba.current_location_id() is null or location_id = gba.current_location_id());

create policy asset_safety_incidents_location_scope on gba.asset_safety_incidents
  as restrictive to gba_runtime
  using (gba.current_location_id() is null or location_id = gba.current_location_id())
  with check (gba.current_location_id() is null or location_id = gba.current_location_id());
