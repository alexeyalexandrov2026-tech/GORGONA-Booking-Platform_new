-- PRO-01 Slice 2 (ADR-0038): stages, tasks, DAG dependencies, restricted matter files.
-- Invoker rights only.

create table gba.project_stages (
    tenant_id uuid not null,
    id uuid not null,
    location_id uuid not null,
    matter_id uuid not null,
    stage_no integer not null check (stage_no between 1 and 1000),
    title text not null check (char_length(btrim(title)) between 1 and 200),
    description text check (description is null or char_length(btrim(description)) between 1 and 4000),
    due_on date,
    fixed_fee_minor bigint check (fixed_fee_minor is null or fixed_fee_minor >= 0),
    deliverable_summary text check (deliverable_summary is null or char_length(btrim(deliverable_summary)) between 1 and 4000),
    deliverable_revision integer not null default 0 check (deliverable_revision >= 0),
    status text not null check (status in ('open', 'submitted', 'accepted', 'rejected')),
    decided_by uuid references gba.users (id),
    decided_at timestamptz,
    revision integer not null check (revision >= 1),
    recorded_by uuid not null references gba.users (id),
    recorded_at timestamptz not null default clock_timestamp(),
    primary key (tenant_id, id),
    unique (tenant_id, id, matter_id, location_id),
    unique (tenant_id, matter_id, stage_no),
    foreign key (tenant_id, matter_id, location_id)
        references gba.project_matters (tenant_id, id, location_id),
    check (
        (status in ('accepted', 'rejected') and decided_by is not null and decided_at is not null)
        or (status in ('open', 'submitted') and decided_by is null and decided_at is null)
    )
);
create index project_stages_matter_idx
    on gba.project_stages (tenant_id, matter_id, stage_no, id);

create table gba.project_tasks (
    tenant_id uuid not null,
    id uuid not null,
    location_id uuid not null,
    matter_id uuid not null,
    stage_id uuid,
    title text not null check (char_length(btrim(title)) between 1 and 200),
    description text check (description is null or char_length(btrim(description)) between 1 and 4000),
    assignee_user_id uuid references gba.users (id),
    priority text not null check (priority in ('low', 'normal', 'high', 'urgent')),
    status text not null check (status in ('todo', 'in_progress', 'blocked', 'done', 'cancelled')),
    due_on date,
    revision integer not null check (revision >= 1),
    recorded_by uuid not null references gba.users (id),
    recorded_at timestamptz not null default clock_timestamp(),
    primary key (tenant_id, id),
    unique (tenant_id, id, matter_id, location_id),
    foreign key (tenant_id, matter_id, location_id)
        references gba.project_matters (tenant_id, id, location_id),
    foreign key (tenant_id, stage_id, matter_id, location_id)
        references gba.project_stages (tenant_id, id, matter_id, location_id)
);
create index project_tasks_matter_idx
    on gba.project_tasks (tenant_id, matter_id, status, id);
create index project_tasks_assignee_idx
    on gba.project_tasks (tenant_id, assignee_user_id, status, id)
    where assignee_user_id is not null;

create table gba.project_task_dependencies (
    tenant_id uuid not null,
    location_id uuid not null,
    matter_id uuid not null,
    task_id uuid not null,
    depends_on_task_id uuid not null,
    recorded_by uuid not null references gba.users (id),
    recorded_at timestamptz not null default clock_timestamp(),
    primary key (tenant_id, task_id, depends_on_task_id),
    check (task_id <> depends_on_task_id),
    foreign key (tenant_id, task_id, matter_id, location_id)
        references gba.project_tasks (tenant_id, id, matter_id, location_id),
    foreign key (tenant_id, depends_on_task_id, matter_id, location_id)
        references gba.project_tasks (tenant_id, id, matter_id, location_id)
);
create index project_task_dependencies_matter_idx
    on gba.project_task_dependencies (tenant_id, matter_id, task_id);

create table gba.project_matter_files (
    tenant_id uuid not null,
    id uuid not null,
    location_id uuid not null,
    matter_id uuid not null,
    stage_id uuid,
    task_id uuid,
    linked_document_id uuid,
    category text not null check (category in ('pleading', 'contract', 'evidence', 'deliverable', 'correspondence', 'other')),
    title text not null check (char_length(btrim(title)) between 1 and 200),
    file_name text not null check (char_length(btrim(file_name)) between 1 and 255),
    media_type text not null check (media_type in ('application/pdf', 'image/png', 'image/jpeg')),
    byte_size integer not null check (byte_size between 1 and 10485760),
    sha256 text not null check (sha256 ~ '^[0-9a-f]{64}$'),
    content bytea not null check (octet_length(content) = byte_size),
    uploaded_by uuid not null references gba.users (id),
    uploaded_at timestamptz not null default clock_timestamp(),
    primary key (tenant_id, id),
    foreign key (tenant_id, matter_id, location_id)
        references gba.project_matters (tenant_id, id, location_id),
    foreign key (tenant_id, stage_id, matter_id, location_id)
        references gba.project_stages (tenant_id, id, matter_id, location_id),
    foreign key (tenant_id, task_id, matter_id, location_id)
        references gba.project_tasks (tenant_id, id, matter_id, location_id),
    constraint project_matter_files_document_fk
        foreign key (tenant_id, linked_document_id) references gba.documents (tenant_id, id)
);
create index project_matter_files_matter_idx
    on gba.project_matter_files (tenant_id, matter_id, uploaded_at desc, id);

create function gba.guard_project_stage() returns trigger language plpgsql as $$
begin
    if tg_op = 'DELETE' then
        raise exception using errcode = '23514', message = 'project stages are kept';
    end if;
    if tg_op = 'INSERT' then
        if new.revision <> 1 then
            raise exception using errcode = '23514', message = 'project stage starts at revision 1';
        end if;
        return new;
    end if;
    if (new.tenant_id, new.id, new.location_id, new.matter_id, new.stage_no)
       is distinct from
       (old.tenant_id, old.id, old.location_id, old.matter_id, old.stage_no) then
        raise exception using errcode = '23514', message = 'project stage identity is immutable';
    end if;
    if new.revision <> old.revision + 1 then
        raise exception using errcode = '23514', message = 'project stage revision advances by one';
    end if;
    if old.status = 'accepted' and new.status <> 'accepted' then
        raise exception using errcode = '23514', message = 'accepted project stage cannot revert';
    end if;
    return new;
end;
$$;
revoke all on function gba.guard_project_stage() from public;
grant execute on function gba.guard_project_stage() to gba_runtime;
create trigger project_stages_guard before insert or update or delete on gba.project_stages
    for each row execute function gba.guard_project_stage();

create function gba.guard_project_task() returns trigger language plpgsql as $$
begin
    if tg_op = 'DELETE' then
        raise exception using errcode = '23514', message = 'project tasks are kept';
    end if;
    if tg_op = 'INSERT' then
        if new.revision <> 1 then
            raise exception using errcode = '23514', message = 'project task starts at revision 1';
        end if;
        return new;
    end if;
    if (new.tenant_id, new.id, new.location_id, new.matter_id)
       is distinct from
       (old.tenant_id, old.id, old.location_id, old.matter_id) then
        raise exception using errcode = '23514', message = 'project task identity is immutable';
    end if;
    if new.revision <> old.revision + 1 then
        raise exception using errcode = '23514', message = 'project task revision advances by one';
    end if;
    return new;
end;
$$;
revoke all on function gba.guard_project_task() from public;
grant execute on function gba.guard_project_task() to gba_runtime;
create trigger project_tasks_guard before insert or update or delete on gba.project_tasks
    for each row execute function gba.guard_project_task();

create function gba.guard_project_task_dependency() returns trigger language plpgsql as $$
begin
    if tg_op = 'UPDATE' then
        raise exception using errcode = '23514', message = 'task dependencies are immutable';
    end if;
    if tg_op = 'INSERT' then
        if exists (
            with recursive chain(node) as (
                select new.depends_on_task_id
                union
                select d.depends_on_task_id
                from gba.project_task_dependencies d
                join chain c on d.task_id = c.node
                where d.tenant_id = new.tenant_id
                  and d.matter_id = new.matter_id
            )
            select 1 from chain where node = new.task_id
        ) then
            raise exception using errcode = '23514',
                message = 'task dependency cycle is not allowed';
        end if;
    end if;
    return new;
end;
$$;
revoke all on function gba.guard_project_task_dependency() from public;
grant execute on function gba.guard_project_task_dependency() to gba_runtime;
create trigger project_task_dependencies_guard before insert or update on gba.project_task_dependencies
    for each row execute function gba.guard_project_task_dependency();

create trigger project_matter_files_append_only
    before update or delete on gba.project_matter_files
    for each row execute function gba.guard_project_append_only();

-- RLS, module write gates and minimal runtime privileges
alter table gba.project_stages enable row level security;
alter table gba.project_stages force row level security;
create policy project_stages_tenant_isolation on gba.project_stages
    using (tenant_id = gba.current_tenant_id()) with check (tenant_id = gba.current_tenant_id());
grant select, insert, update on gba.project_stages to gba_runtime;
create trigger project_stages_require_module before insert on gba.project_stages
    for each row execute function gba.require_enabled_module('projects');

alter table gba.project_tasks enable row level security;
alter table gba.project_tasks force row level security;
create policy project_tasks_tenant_isolation on gba.project_tasks
    using (tenant_id = gba.current_tenant_id()) with check (tenant_id = gba.current_tenant_id());
grant select, insert, update on gba.project_tasks to gba_runtime;
create trigger project_tasks_require_module before insert on gba.project_tasks
    for each row execute function gba.require_enabled_module('projects');

alter table gba.project_task_dependencies enable row level security;
alter table gba.project_task_dependencies force row level security;
create policy project_task_dependencies_tenant_isolation on gba.project_task_dependencies
    using (tenant_id = gba.current_tenant_id()) with check (tenant_id = gba.current_tenant_id());
grant select, insert, delete on gba.project_task_dependencies to gba_runtime;
create trigger project_task_dependencies_require_module before insert on gba.project_task_dependencies
    for each row execute function gba.require_enabled_module('projects');

alter table gba.project_matter_files enable row level security;
alter table gba.project_matter_files force row level security;
create policy project_matter_files_tenant_isolation on gba.project_matter_files
    using (tenant_id = gba.current_tenant_id()) with check (tenant_id = gba.current_tenant_id());
grant select, insert on gba.project_matter_files to gba_runtime;
create trigger project_matter_files_require_module before insert on gba.project_matter_files
    for each row execute function gba.require_enabled_module('projects');

-- Projects work ethical-wall matter access scope (PostgreSQL 18 FORCE RLS, invoker rights):
create policy project_stages_matter_access on gba.project_stages as restrictive to gba_runtime
    using (
        exists (
            select 1 from gba.project_matters pm
            where pm.tenant_id = project_stages.tenant_id
              and pm.id = project_stages.matter_id
        )
    )
    with check (
        exists (
            select 1 from gba.project_matters pm
            where pm.tenant_id = project_stages.tenant_id
              and pm.id = project_stages.matter_id
        )
    );

create policy project_tasks_matter_access on gba.project_tasks as restrictive to gba_runtime
    using (
        exists (
            select 1 from gba.project_matters pm
            where pm.tenant_id = project_tasks.tenant_id
              and pm.id = project_tasks.matter_id
        )
    )
    with check (
        exists (
            select 1 from gba.project_matters pm
            where pm.tenant_id = project_tasks.tenant_id
              and pm.id = project_tasks.matter_id
        )
    );

create policy project_task_dependencies_matter_access on gba.project_task_dependencies as restrictive to gba_runtime
    using (
        exists (
            select 1 from gba.project_matters pm
            where pm.tenant_id = project_task_dependencies.tenant_id
              and pm.id = project_task_dependencies.matter_id
        )
    )
    with check (
        exists (
            select 1 from gba.project_matters pm
            where pm.tenant_id = project_task_dependencies.tenant_id
              and pm.id = project_task_dependencies.matter_id
        )
    );

create policy project_matter_files_matter_access on gba.project_matter_files as restrictive to gba_runtime
    using (
        exists (
            select 1 from gba.project_matters pm
            where pm.tenant_id = project_matter_files.tenant_id
              and pm.id = project_matter_files.matter_id
        )
    )
    with check (
        exists (
            select 1 from gba.project_matters pm
            where pm.tenant_id = project_matter_files.tenant_id
              and pm.id = project_matter_files.matter_id
        )
    );

-- Projects work branch scope:
create policy project_stages_location_scope on gba.project_stages as restrictive to gba_runtime
    using (gba.current_location_id() is null or location_id = gba.current_location_id())
    with check (gba.current_location_id() is null or location_id = gba.current_location_id());

create policy project_tasks_location_scope on gba.project_tasks as restrictive to gba_runtime
    using (gba.current_location_id() is null or location_id = gba.current_location_id())
    with check (gba.current_location_id() is null or location_id = gba.current_location_id());

create policy project_task_dependencies_location_scope on gba.project_task_dependencies as restrictive to gba_runtime
    using (gba.current_location_id() is null or location_id = gba.current_location_id())
    with check (gba.current_location_id() is null or location_id = gba.current_location_id());

create policy project_matter_files_location_scope on gba.project_matter_files as restrictive to gba_runtime
    using (gba.current_location_id() is null or location_id = gba.current_location_id())
    with check (gba.current_location_id() is null or location_id = gba.current_location_id());
