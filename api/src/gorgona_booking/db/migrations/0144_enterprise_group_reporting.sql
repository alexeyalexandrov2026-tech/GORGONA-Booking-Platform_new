-- 0144_enterprise_group_reporting.sql
-- ADR-0041 / ENTERPRISE-01 Slice 2: consent-based group reporting grants and legal-entity /
-- currency-separated aggregate report snapshots. Preserves Stage 1 ownership boundaries
-- (ADR-0018): organizer receives ONLY explicitly consented report sets without ownership
-- transfer or raw tenant access. Invoker rights only.

create table gba.enterprise_group_report_grants (
    id uuid not null,
    tenant_id uuid not null references gba.tenants(id),
    organizer_tenant_id uuid not null,
    group_id uuid not null,
    allowed_report_sets text[] not null,
    status text not null default 'active',
    revoked_at timestamptz null,
    revision integer not null default 1,
    recorded_by uuid not null references gba.users(id),
    recorded_at timestamptz not null default now(),
    primary key (tenant_id, id),
    constraint enterprise_group_report_grants_group_fk
        foreign key (organizer_tenant_id, group_id)
        references gba.business_groups(organizer_tenant_id, id) on delete restrict,
    constraint enterprise_group_report_grants_unique
        unique (tenant_id, organizer_tenant_id, group_id),
    constraint enterprise_group_report_grants_not_self
        check (tenant_id <> organizer_tenant_id),
    constraint enterprise_group_report_grants_sets_check
        check (
            cardinality(allowed_report_sets) >= 1
            and allowed_report_sets <@ array[
                'ledger_summary',
                'revenue_by_currency',
                'order_volume',
                'headcount'
            ]::text[]
        ),
    constraint enterprise_group_report_grants_status_check
        check (
            status in ('active', 'revoked')
            and ((status = 'revoked') = (revoked_at is not null))
            and revision >= 1
        )
);

create index enterprise_group_report_grants_org_idx
    on gba.enterprise_group_report_grants (organizer_tenant_id, group_id, status);

create table gba.enterprise_group_report_snapshots (
    id uuid not null,
    tenant_id uuid not null references gba.tenants(id),
    organizer_tenant_id uuid not null,
    group_id uuid not null,
    legal_entity_id uuid not null,
    period_key text not null,
    currency text not null references gba.currencies(code),
    report_set text not null,
    metric_count bigint not null default 0,
    metric_amount_minor bigint not null default 0,
    notes text null,
    recorded_by uuid not null references gba.users(id),
    recorded_at timestamptz not null default now(),
    primary key (tenant_id, id),
    constraint enterprise_group_report_snapshots_group_fk
        foreign key (organizer_tenant_id, group_id)
        references gba.business_groups(organizer_tenant_id, id) on delete restrict,
    constraint enterprise_group_report_snapshots_le_fk
        foreign key (tenant_id, legal_entity_id)
        references gba.legal_entities(tenant_id, id) on delete restrict,
    constraint enterprise_group_report_snapshots_unique
        unique (tenant_id, group_id, legal_entity_id, period_key, currency, report_set),
    constraint enterprise_group_report_snapshots_checks
        check (
            tenant_id <> organizer_tenant_id
            and period_key ~ '^[0-9]{4}-[0-9]{2}$'
            and report_set in (
                'ledger_summary',
                'revenue_by_currency',
                'order_volume',
                'headcount'
            )
            and metric_count >= 0
        )
);

create index enterprise_group_report_snapshots_org_idx
    on gba.enterprise_group_report_snapshots (organizer_tenant_id, group_id, period_key, report_set);

-- RLS, grants and module write gates
alter table gba.enterprise_group_report_grants enable row level security;
alter table gba.enterprise_group_report_grants force row level security;
create policy enterprise_group_report_grants_access on gba.enterprise_group_report_grants
    using (
        tenant_id = gba.current_tenant_id()
        or organizer_tenant_id = gba.current_tenant_id()
    )
    with check (tenant_id = gba.current_tenant_id());
grant select, insert, update on gba.enterprise_group_report_grants to gba_runtime;
create trigger enterprise_group_report_grants_require_module
    before insert on gba.enterprise_group_report_grants
    for each row execute function gba.require_enabled_module('analytics');

alter table gba.enterprise_group_report_snapshots enable row level security;
alter table gba.enterprise_group_report_snapshots force row level security;
create policy enterprise_group_report_snapshots_access on gba.enterprise_group_report_snapshots
    using (
        tenant_id = gba.current_tenant_id()
        or (
            organizer_tenant_id = gba.current_tenant_id()
            and exists (
                select 1
                from gba.business_group_members m
                join gba.enterprise_group_report_grants g
                    on g.tenant_id = m.member_tenant_id
                    and g.organizer_tenant_id = m.organizer_tenant_id
                    and g.group_id = m.group_id
                where m.organizer_tenant_id = enterprise_group_report_snapshots.organizer_tenant_id
                  and m.group_id = enterprise_group_report_snapshots.group_id
                  and m.member_tenant_id = enterprise_group_report_snapshots.tenant_id
                  and m.status = 'active'
                  and g.status = 'active'
                  and enterprise_group_report_snapshots.report_set = any(g.allowed_report_sets)
            )
        )
    )
    with check (tenant_id = gba.current_tenant_id());
grant select, insert, update on gba.enterprise_group_report_snapshots to gba_runtime;
create trigger enterprise_group_report_snapshots_require_module
    before insert on gba.enterprise_group_report_snapshots
    for each row execute function gba.require_enabled_module('analytics');

-- Enterprise group reporting branch scope:
create policy enterprise_group_report_grants_unrestricted_scope
    on gba.enterprise_group_report_grants
    as restrictive to gba_runtime
    using (gba.current_location_id() is null)
    with check (gba.current_location_id() is null);

create policy enterprise_group_report_snapshots_unrestricted_scope
    on gba.enterprise_group_report_snapshots
    as restrictive to gba_runtime
    using (gba.current_location_id() is null)
    with check (gba.current_location_id() is null);
