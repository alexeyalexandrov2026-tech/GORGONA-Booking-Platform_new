-- PRO-01 Slice 3 (ADR-0038): billable time tracking (versioned) and recurring service schedules/runs.
-- Invoker rights only.

create table gba.project_time_entries (
    tenant_id uuid not null,
    id uuid not null,
    location_id uuid not null,
    matter_id uuid not null,
    stage_id uuid,
    task_id uuid,
    staff_user_id uuid not null references gba.users (id),
    work_date date not null,
    duration_minutes integer not null check (duration_minutes between 1 and 1440),
    hourly_rate_minor bigint not null check (hourly_rate_minor >= 0),
    currency char(3) not null check (currency ~ '^[A-Z]{3}$'),
    billable boolean not null default true,
    amount_minor bigint not null check (amount_minor >= 0),
    description text not null check (char_length(btrim(description)) between 1 and 2000),
    status text not null check (status in ('draft', 'submitted', 'approved', 'billed', 'rejected')),
    decided_by uuid references gba.users (id),
    decided_at timestamptz,
    revision integer not null check (revision >= 1),
    recorded_by uuid not null references gba.users (id),
    recorded_at timestamptz not null default clock_timestamp(),
    primary key (tenant_id, id),
    unique (tenant_id, id, matter_id, location_id),
    foreign key (tenant_id, matter_id, location_id, currency)
        references gba.project_matters (tenant_id, id, location_id, currency),
    foreign key (tenant_id, stage_id, matter_id, location_id)
        references gba.project_stages (tenant_id, id, matter_id, location_id),
    foreign key (tenant_id, task_id, matter_id, location_id)
        references gba.project_tasks (tenant_id, id, matter_id, location_id),
    check (billable or amount_minor = 0),
    check (
        (status in ('approved', 'billed', 'rejected') and decided_by is not null and decided_at is not null)
        or (status in ('draft', 'submitted') and decided_by is null and decided_at is null)
    )
);
create index project_time_entries_matter_status_idx
    on gba.project_time_entries (tenant_id, matter_id, status, work_date, id);

create table gba.project_time_entry_revisions (
    tenant_id uuid not null,
    time_entry_id uuid not null,
    revision integer not null check (revision >= 1),
    location_id uuid not null,
    matter_id uuid not null,
    stage_id uuid,
    task_id uuid,
    staff_user_id uuid not null references gba.users (id),
    work_date date not null,
    duration_minutes integer not null check (duration_minutes between 1 and 1440),
    hourly_rate_minor bigint not null check (hourly_rate_minor >= 0),
    currency char(3) not null check (currency ~ '^[A-Z]{3}$'),
    billable boolean not null,
    amount_minor bigint not null check (amount_minor >= 0),
    description text not null check (char_length(btrim(description)) between 1 and 2000),
    status text not null check (status in ('draft', 'submitted', 'approved', 'billed', 'rejected')),
    decided_by uuid references gba.users (id),
    decided_at timestamptz,
    recorded_by uuid not null references gba.users (id),
    recorded_at timestamptz not null default clock_timestamp(),
    primary key (tenant_id, time_entry_id, revision),
    foreign key (tenant_id, time_entry_id, matter_id, location_id)
        references gba.project_time_entries (tenant_id, id, matter_id, location_id)
);

create table gba.project_recurring_schedules (
    tenant_id uuid not null,
    id uuid not null,
    location_id uuid not null,
    matter_id uuid not null,
    title text not null check (char_length(btrim(title)) between 1 and 200),
    task_template_title text not null check (char_length(btrim(task_template_title)) between 1 and 200),
    task_template_description text check (
        task_template_description is null
        or char_length(btrim(task_template_description)) between 1 and 4000
    ),
    default_assignee_user_id uuid references gba.users (id),
    cadence text not null check (cadence in ('weekly', 'biweekly', 'monthly', 'quarterly')),
    next_run_date date not null,
    fixed_fee_minor bigint not null check (fixed_fee_minor >= 0),
    currency char(3) not null check (currency ~ '^[A-Z]{3}$'),
    status text not null check (status in ('active', 'paused', 'ended')),
    revision integer not null check (revision >= 1),
    recorded_by uuid not null references gba.users (id),
    recorded_at timestamptz not null default clock_timestamp(),
    primary key (tenant_id, id),
    unique (tenant_id, id, matter_id, location_id, currency),
    foreign key (tenant_id, matter_id, location_id, currency)
        references gba.project_matters (tenant_id, id, location_id, currency)
);
create index project_recurring_schedules_matter_idx
    on gba.project_recurring_schedules (tenant_id, matter_id, status, next_run_date, id);

create table gba.project_recurring_runs (
    tenant_id uuid not null,
    id uuid not null,
    location_id uuid not null,
    matter_id uuid not null,
    schedule_id uuid not null,
    period_start date not null,
    period_end date not null,
    task_id uuid not null,
    fee_minor bigint not null check (fee_minor >= 0),
    currency char(3) not null check (currency ~ '^[A-Z]{3}$'),
    billing_status text not null check (billing_status in ('unbilled', 'billed')),
    recorded_by uuid not null references gba.users (id),
    recorded_at timestamptz not null default clock_timestamp(),
    primary key (tenant_id, id),
    unique (tenant_id, id, matter_id, location_id),
    unique (tenant_id, schedule_id, period_start, period_end),
    check (period_end >= period_start),
    foreign key (tenant_id, schedule_id, matter_id, location_id, currency)
        references gba.project_recurring_schedules (tenant_id, id, matter_id, location_id, currency),
    foreign key (tenant_id, task_id, matter_id, location_id)
        references gba.project_tasks (tenant_id, id, matter_id, location_id)
);
create index project_recurring_runs_matter_idx
    on gba.project_recurring_runs (tenant_id, matter_id, billing_status, period_start, id);

create function gba.guard_project_time_entry() returns trigger language plpgsql as $$
begin
    if tg_op = 'DELETE' then
        raise exception using errcode = '23514', message = 'project time entries are kept';
    end if;
    if tg_op = 'INSERT' then
        if new.revision <> 1 then
            raise exception using errcode = '23514', message = 'time entry starts at revision 1';
        end if;
        if new.status not in ('draft', 'submitted') then
            raise exception using errcode = '23514', message = 'time entry starts as draft or submitted';
        end if;
        return new;
    end if;
    if (new.tenant_id, new.id, new.location_id, new.matter_id, new.currency, new.staff_user_id)
       is distinct from
       (old.tenant_id, old.id, old.location_id, old.matter_id, old.currency, old.staff_user_id) then
        raise exception using errcode = '23514', message = 'time entry identity and staff are immutable';
    end if;
    if new.revision <> old.revision + 1 then
        raise exception using errcode = '23514', message = 'time entry revision advances by one';
    end if;
    if old.status = 'billed' then
        raise exception using errcode = '23514', message = 'billed time entry is immutable';
    end if;
    if old.status = 'approved' and new.status <> 'billed' then
        raise exception using errcode = '23514', message = 'approved time entry may only transition to billed';
    end if;
    return new;
end;
$$;
revoke all on function gba.guard_project_time_entry() from public;
grant execute on function gba.guard_project_time_entry() to gba_runtime;
create trigger project_time_entries_guard before insert or update or delete on gba.project_time_entries
    for each row execute function gba.guard_project_time_entry();

create trigger project_time_entry_revisions_append_only
    before update or delete on gba.project_time_entry_revisions
    for each row execute function gba.guard_project_append_only();

create function gba.guard_project_recurring_schedule() returns trigger language plpgsql as $$
begin
    if tg_op = 'DELETE' then
        raise exception using errcode = '23514', message = 'recurring schedules are kept';
    end if;
    if tg_op = 'INSERT' then
        if new.revision <> 1 then
            raise exception using errcode = '23514', message = 'recurring schedule starts at revision 1';
        end if;
        return new;
    end if;
    if (new.tenant_id, new.id, new.location_id, new.matter_id, new.currency)
       is distinct from
       (old.tenant_id, old.id, old.location_id, old.matter_id, old.currency) then
        raise exception using errcode = '23514', message = 'recurring schedule identity is immutable';
    end if;
    if new.revision <> old.revision + 1 then
        raise exception using errcode = '23514', message = 'recurring schedule revision advances by one';
    end if;
    if old.status = 'ended' and new.status <> 'ended' then
        raise exception using errcode = '23514', message = 'ended recurring schedule cannot resume';
    end if;
    return new;
end;
$$;
revoke all on function gba.guard_project_recurring_schedule() from public;
grant execute on function gba.guard_project_recurring_schedule() to gba_runtime;
create trigger project_recurring_schedules_guard before insert or update or delete on gba.project_recurring_schedules
    for each row execute function gba.guard_project_recurring_schedule();

create function gba.guard_project_recurring_run() returns trigger language plpgsql as $$
begin
    if tg_op = 'DELETE' then
        raise exception using errcode = '23514', message = 'recurring runs are kept';
    end if;
    if tg_op = 'UPDATE' then
        if (new.tenant_id, new.id, new.location_id, new.matter_id, new.schedule_id,
            new.period_start, new.period_end, new.task_id, new.fee_minor, new.currency,
            new.recorded_by, new.recorded_at)
           is distinct from
           (old.tenant_id, old.id, old.location_id, old.matter_id, old.schedule_id,
            old.period_start, old.period_end, old.task_id, old.fee_minor, old.currency,
            old.recorded_by, old.recorded_at) then
            raise exception using errcode = '23514', message = 'recurring run facts are immutable';
        end if;
        if old.billing_status = 'billed' or new.billing_status <> 'billed' then
            raise exception using errcode = '23514', message = 'recurring run may only transition once from unbilled to billed';
        end if;
    end if;
    return new;
end;
$$;
revoke all on function gba.guard_project_recurring_run() from public;
grant execute on function gba.guard_project_recurring_run() to gba_runtime;
create trigger project_recurring_runs_guard before insert or update or delete on gba.project_recurring_runs
    for each row execute function gba.guard_project_recurring_run();

-- RLS, module write gates and minimal runtime privileges
alter table gba.project_time_entries enable row level security;
alter table gba.project_time_entries force row level security;
create policy project_time_entries_tenant_isolation on gba.project_time_entries
    using (tenant_id = gba.current_tenant_id()) with check (tenant_id = gba.current_tenant_id());
grant select, insert, update on gba.project_time_entries to gba_runtime;
create trigger project_time_entries_require_module before insert on gba.project_time_entries
    for each row execute function gba.require_enabled_module('projects');

alter table gba.project_time_entry_revisions enable row level security;
alter table gba.project_time_entry_revisions force row level security;
create policy project_time_entry_revisions_tenant_isolation on gba.project_time_entry_revisions
    using (tenant_id = gba.current_tenant_id()) with check (tenant_id = gba.current_tenant_id());
grant select, insert on gba.project_time_entry_revisions to gba_runtime;

alter table gba.project_recurring_schedules enable row level security;
alter table gba.project_recurring_schedules force row level security;
create policy project_recurring_schedules_tenant_isolation on gba.project_recurring_schedules
    using (tenant_id = gba.current_tenant_id()) with check (tenant_id = gba.current_tenant_id());
grant select, insert, update on gba.project_recurring_schedules to gba_runtime;
create trigger project_recurring_schedules_require_module before insert on gba.project_recurring_schedules
    for each row execute function gba.require_enabled_module('projects');

alter table gba.project_recurring_runs enable row level security;
alter table gba.project_recurring_runs force row level security;
create policy project_recurring_runs_tenant_isolation on gba.project_recurring_runs
    using (tenant_id = gba.current_tenant_id()) with check (tenant_id = gba.current_tenant_id());
grant select, insert, update on gba.project_recurring_runs to gba_runtime;
create trigger project_recurring_runs_require_module before insert on gba.project_recurring_runs
    for each row execute function gba.require_enabled_module('projects');

-- Projects time & recurring ethical-wall matter access scope (PostgreSQL 18 FORCE RLS, invoker rights):
create policy project_time_entries_matter_access on gba.project_time_entries as restrictive to gba_runtime
    using (
        exists (
            select 1 from gba.project_matters pm
            where pm.tenant_id = project_time_entries.tenant_id
              and pm.id = project_time_entries.matter_id
        )
    )
    with check (
        exists (
            select 1 from gba.project_matters pm
            where pm.tenant_id = project_time_entries.tenant_id
              and pm.id = project_time_entries.matter_id
        )
    );

create policy project_time_entry_revisions_matter_access on gba.project_time_entry_revisions as restrictive to gba_runtime
    using (
        exists (
            select 1 from gba.project_matters pm
            where pm.tenant_id = project_time_entry_revisions.tenant_id
              and pm.id = project_time_entry_revisions.matter_id
        )
    )
    with check (
        exists (
            select 1 from gba.project_matters pm
            where pm.tenant_id = project_time_entry_revisions.tenant_id
              and pm.id = project_time_entry_revisions.matter_id
        )
    );

create policy project_recurring_schedules_matter_access on gba.project_recurring_schedules as restrictive to gba_runtime
    using (
        exists (
            select 1 from gba.project_matters pm
            where pm.tenant_id = project_recurring_schedules.tenant_id
              and pm.id = project_recurring_schedules.matter_id
        )
    )
    with check (
        exists (
            select 1 from gba.project_matters pm
            where pm.tenant_id = project_recurring_schedules.tenant_id
              and pm.id = project_recurring_schedules.matter_id
        )
    );

create policy project_recurring_runs_matter_access on gba.project_recurring_runs as restrictive to gba_runtime
    using (
        exists (
            select 1 from gba.project_matters pm
            where pm.tenant_id = project_recurring_runs.tenant_id
              and pm.id = project_recurring_runs.matter_id
        )
    )
    with check (
        exists (
            select 1 from gba.project_matters pm
            where pm.tenant_id = project_recurring_runs.tenant_id
              and pm.id = project_recurring_runs.matter_id
        )
    );

-- Projects time & recurring branch scope:
create policy project_time_entries_location_scope on gba.project_time_entries as restrictive to gba_runtime
    using (gba.current_location_id() is null or location_id = gba.current_location_id())
    with check (gba.current_location_id() is null or location_id = gba.current_location_id());

create policy project_time_entry_revisions_location_scope on gba.project_time_entry_revisions as restrictive to gba_runtime
    using (gba.current_location_id() is null or location_id = gba.current_location_id())
    with check (gba.current_location_id() is null or location_id = gba.current_location_id());

create policy project_recurring_schedules_location_scope on gba.project_recurring_schedules as restrictive to gba_runtime
    using (gba.current_location_id() is null or location_id = gba.current_location_id())
    with check (gba.current_location_id() is null or location_id = gba.current_location_id());

create policy project_recurring_runs_location_scope on gba.project_recurring_runs as restrictive to gba_runtime
    using (gba.current_location_id() is null or location_id = gba.current_location_id())
    with check (gba.current_location_id() is null or location_id = gba.current_location_id());
