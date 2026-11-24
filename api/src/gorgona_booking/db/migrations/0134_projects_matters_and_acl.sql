-- PRO-01 Slice 1 (ADR-0038): legal matters, projects, conflict checks, and ethical-wall ACL.
-- Invoker rights only.

create table gba.project_matters (
    tenant_id uuid not null,
    id uuid not null,
    location_id uuid not null,
    code text not null check (char_length(btrim(code)) between 1 and 40),
    title text not null check (char_length(btrim(title)) between 1 and 200),
    description text check (description is null or char_length(btrim(description)) between 1 and 4000),
    kind text not null check (kind in ('legal_case', 'project', 'recurring_engagement')),
    status text not null check (status in ('intake', 'conflict_check', 'active', 'on_hold', 'closed', 'cancelled')),
    access_mode text not null check (access_mode in ('branch', 'restricted')),
    client_counterparty_id uuid not null,
    currency char(3) not null check (currency ~ '^[A-Z]{3}$'),
    budget_minor bigint check (budget_minor is null or budget_minor >= 0),
    opened_on date not null,
    due_on date check (due_on is null or due_on >= opened_on),
    closed_at timestamptz,
    revision integer not null check (revision >= 1),
    created_by uuid not null references gba.users (id),
    recorded_by uuid not null references gba.users (id),
    recorded_at timestamptz not null default clock_timestamp(),
    creation_xid xid8 not null default pg_current_xact_id(),
    primary key (tenant_id, id),
    unique (tenant_id, id, location_id),
    unique (tenant_id, id, location_id, currency),
    unique (tenant_id, location_id, code),
    foreign key (tenant_id, location_id) references gba.locations (tenant_id, id),
    constraint project_matters_client_fk
        foreign key (tenant_id, client_counterparty_id) references gba.counterparties (tenant_id, id),
    check (
        (status in ('closed', 'cancelled') and closed_at is not null)
        or (status not in ('closed', 'cancelled') and closed_at is null)
    )
);
create index project_matters_loc_status_idx
    on gba.project_matters (tenant_id, location_id, status, id);
create index project_matters_client_idx
    on gba.project_matters (tenant_id, client_counterparty_id, id);

create table gba.project_matter_members (
    tenant_id uuid not null,
    id uuid not null,
    location_id uuid not null,
    matter_id uuid not null,
    user_id uuid not null references gba.users (id),
    matter_role text not null check (matter_role in ('lead', 'contributor', 'viewer', 'billing')),
    granted_by uuid not null references gba.users (id),
    granted_at timestamptz not null default clock_timestamp(),
    revoked_by uuid references gba.users (id),
    revoked_at timestamptz,
    primary key (tenant_id, id),
    foreign key (tenant_id, matter_id, location_id)
        references gba.project_matters (tenant_id, id, location_id),
    check (
        (revoked_at is null and revoked_by is null)
        or (revoked_at is not null and revoked_by is not null and revoked_at >= granted_at)
    )
);
create unique index project_matter_members_active_uidx
    on gba.project_matter_members (tenant_id, matter_id, user_id)
    where revoked_at is null;
create index project_matter_members_user_active_idx
    on gba.project_matter_members (tenant_id, user_id, matter_id)
    where revoked_at is null;

create table gba.project_matter_revisions (
    tenant_id uuid not null,
    matter_id uuid not null,
    revision integer not null check (revision >= 1),
    location_id uuid not null,
    code text not null check (char_length(btrim(code)) between 1 and 40),
    title text not null check (char_length(btrim(title)) between 1 and 200),
    description text check (description is null or char_length(btrim(description)) between 1 and 4000),
    kind text not null check (kind in ('legal_case', 'project', 'recurring_engagement')),
    status text not null check (status in ('intake', 'conflict_check', 'active', 'on_hold', 'closed', 'cancelled')),
    access_mode text not null check (access_mode in ('branch', 'restricted')),
    client_counterparty_id uuid not null,
    currency char(3) not null check (currency ~ '^[A-Z]{3}$'),
    budget_minor bigint check (budget_minor is null or budget_minor >= 0),
    opened_on date not null,
    due_on date check (due_on is null or due_on >= opened_on),
    closed_at timestamptz,
    recorded_by uuid not null references gba.users (id),
    recorded_at timestamptz not null default clock_timestamp(),
    primary key (tenant_id, matter_id, revision),
    foreign key (tenant_id, matter_id, location_id)
        references gba.project_matters (tenant_id, id, location_id)
);

create table gba.project_conflict_checks (
    tenant_id uuid not null,
    id uuid not null,
    location_id uuid not null,
    matter_id uuid not null,
    checked_parties text not null check (char_length(btrim(checked_parties)) between 1 and 2000),
    decision text not null check (decision in ('clear', 'waived', 'blocked')),
    rationale text not null check (char_length(btrim(rationale)) between 1 and 2000),
    decided_by uuid not null references gba.users (id),
    decided_at timestamptz not null default clock_timestamp(),
    primary key (tenant_id, id),
    foreign key (tenant_id, matter_id, location_id)
        references gba.project_matters (tenant_id, id, location_id)
);
create index project_conflict_checks_matter_idx
    on gba.project_conflict_checks (tenant_id, matter_id, decided_at desc, id);

create function gba.guard_project_matter() returns trigger language plpgsql as $$
begin
    if tg_op = 'DELETE' then
        raise exception using errcode = '23514', message = 'project matters are kept';
    end if;
    if tg_op = 'INSERT' then
        if new.revision <> 1 then
            raise exception using errcode = '23514', message = 'project matter starts at revision 1';
        end if;
        if new.kind = 'legal_case' and new.status not in ('intake', 'conflict_check') then
            raise exception using errcode = '23514',
                message = 'legal cases must start in intake or conflict_check before conflict clearance';
        end if;
        new.creation_xid := pg_current_xact_id();
        return new;
    end if;
    if (new.tenant_id, new.id, new.location_id, new.kind, new.currency, new.created_by, new.creation_xid)
       is distinct from
       (old.tenant_id, old.id, old.location_id, old.kind, old.currency, old.created_by, old.creation_xid) then
        raise exception using errcode = '23514',
            message = 'project matter identity, branch, kind and currency are immutable';
    end if;
    if new.revision <> old.revision + 1 then
        raise exception using errcode = '23514',
            message = 'project matter revision advances by one';
    end if;
    if old.status in ('closed', 'cancelled') and new.status <> old.status then
        raise exception using errcode = '23514',
            message = 'closed or cancelled project matters cannot reopen';
    end if;
    if new.kind = 'legal_case' and new.status = 'active' and old.status <> 'active' then
        if not exists (
            select 1 from gba.project_conflict_checks c
            where c.tenant_id = new.tenant_id and c.matter_id = new.id
              and c.decision in ('clear', 'waived')
        ) then
            raise exception using errcode = '23514',
                message = 'legal case cannot activate without a clear or waived conflict check';
        end if;
        if exists (
            select 1 from (
                select decision from gba.project_conflict_checks c
                where c.tenant_id = new.tenant_id and c.matter_id = new.id
                order by c.decided_at desc, c.id desc
                limit 1
            ) latest
            where latest.decision = 'blocked'
        ) then
            raise exception using errcode = '23514',
                message = 'legal case has a blocked conflict check';
        end if;
    end if;
    return new;
end;
$$;
revoke all on function gba.guard_project_matter() from public;
grant execute on function gba.guard_project_matter() to gba_runtime;
create trigger project_matters_guard before insert or update or delete on gba.project_matters
    for each row execute function gba.guard_project_matter();

create function gba.guard_project_matter_member() returns trigger language plpgsql as $$
begin
    if tg_op = 'DELETE' then
        raise exception using errcode = '23514', message = 'project matter memberships are kept';
    end if;
    if tg_op = 'UPDATE' then
        if (new.tenant_id, new.id, new.location_id, new.matter_id, new.user_id, new.granted_by, new.granted_at)
           is distinct from
           (old.tenant_id, old.id, old.location_id, old.matter_id, old.user_id, old.granted_by, old.granted_at) then
            raise exception using errcode = '23514',
                message = 'project matter membership identity is immutable';
        end if;
        if old.revoked_at is not null then
            raise exception using errcode = '23514',
                message = 'revoked project matter membership cannot be modified';
        end if;
    end if;
    return new;
end;
$$;
revoke all on function gba.guard_project_matter_member() from public;
grant execute on function gba.guard_project_matter_member() to gba_runtime;
create trigger project_matter_members_guard before insert or update or delete on gba.project_matter_members
    for each row execute function gba.guard_project_matter_member();

create function gba.check_restricted_matter_has_lead() returns trigger language plpgsql as $$
declare
    v_tenant uuid;
    v_matter uuid;
    v_mode text;
begin
    if tg_table_name = 'project_matters' then
        v_tenant := new.tenant_id;
        v_matter := new.id;
    else
        v_tenant := new.tenant_id;
        v_matter := new.matter_id;
    end if;
    select access_mode into v_mode
      from gba.project_matters
     where tenant_id = v_tenant and id = v_matter;
    if v_mode = 'restricted' then
        if not exists (
            select 1 from gba.project_matter_members m
            where m.tenant_id = v_tenant
              and m.matter_id = v_matter
              and m.matter_role = 'lead'
              and m.revoked_at is null
        ) then
            raise exception using errcode = '23514',
                message = 'restricted project matter must retain at least one active lead member';
        end if;
    end if;
    return null;
end;
$$;
revoke all on function gba.check_restricted_matter_has_lead() from public;
grant execute on function gba.check_restricted_matter_has_lead() to gba_runtime;

create constraint trigger project_matters_restricted_has_lead
    after insert or update of access_mode on gba.project_matters
    deferrable initially deferred
    for each row execute function gba.check_restricted_matter_has_lead();

create constraint trigger project_matter_members_restricted_has_lead
    after update of matter_role, revoked_at on gba.project_matter_members
    deferrable initially deferred
    for each row execute function gba.check_restricted_matter_has_lead();

create function gba.guard_project_append_only() returns trigger language plpgsql as $$
begin
    raise exception using errcode = '23514', message = 'project audit records are immutable';
end;
$$;
revoke all on function gba.guard_project_append_only() from public;
grant execute on function gba.guard_project_append_only() to gba_runtime;

create trigger project_matter_revisions_append_only
    before update or delete on gba.project_matter_revisions
    for each row execute function gba.guard_project_append_only();
create trigger project_conflict_checks_append_only
    before update or delete on gba.project_conflict_checks
    for each row execute function gba.guard_project_append_only();

-- RLS, module write gates and minimal runtime privileges
alter table gba.project_matters enable row level security;
alter table gba.project_matters force row level security;
create policy project_matters_tenant_isolation on gba.project_matters
    using (tenant_id = gba.current_tenant_id()) with check (tenant_id = gba.current_tenant_id());
grant select, insert, update on gba.project_matters to gba_runtime;
create trigger project_matters_require_module before insert on gba.project_matters
    for each row execute function gba.require_enabled_module('projects');

alter table gba.project_matter_members enable row level security;
alter table gba.project_matter_members force row level security;
create policy project_matter_members_tenant_isolation on gba.project_matter_members
    using (tenant_id = gba.current_tenant_id()) with check (tenant_id = gba.current_tenant_id());
grant select, insert, update on gba.project_matter_members to gba_runtime;
create trigger project_matter_members_require_module before insert on gba.project_matter_members
    for each row execute function gba.require_enabled_module('projects');

alter table gba.project_matter_revisions enable row level security;
alter table gba.project_matter_revisions force row level security;
create policy project_matter_revisions_tenant_isolation on gba.project_matter_revisions
    using (tenant_id = gba.current_tenant_id()) with check (tenant_id = gba.current_tenant_id());
grant select, insert on gba.project_matter_revisions to gba_runtime;

alter table gba.project_conflict_checks enable row level security;
alter table gba.project_conflict_checks force row level security;
create policy project_conflict_checks_tenant_isolation on gba.project_conflict_checks
    using (tenant_id = gba.current_tenant_id()) with check (tenant_id = gba.current_tenant_id());
grant select, insert on gba.project_conflict_checks to gba_runtime;
create trigger project_conflict_checks_require_module before insert on gba.project_conflict_checks
    for each row execute function gba.require_enabled_module('projects');

-- Projects ethical-wall matter access scope (PostgreSQL 18 FORCE RLS, invoker rights):
create policy project_matters_matter_access on gba.project_matters as restrictive to gba_runtime
    using (
        access_mode = 'branch'
        or creation_xid = pg_current_xact_id()
        or exists (
            select 1 from gba.project_matter_members m
            where m.tenant_id = project_matters.tenant_id
              and m.matter_id = project_matters.id
              and m.user_id = gba.current_user_id()
              and m.revoked_at is null
        )
    )
    with check (
        access_mode = 'branch'
        or creation_xid = pg_current_xact_id()
        or exists (
            select 1 from gba.project_matter_members m
            where m.tenant_id = project_matters.tenant_id
              and m.matter_id = project_matters.id
              and m.user_id = gba.current_user_id()
              and m.revoked_at is null
        )
    );

create policy project_matter_revisions_matter_access on gba.project_matter_revisions as restrictive to gba_runtime
    using (
        exists (
            select 1 from gba.project_matters pm
            where pm.tenant_id = project_matter_revisions.tenant_id
              and pm.id = project_matter_revisions.matter_id
        )
    )
    with check (
        exists (
            select 1 from gba.project_matters pm
            where pm.tenant_id = project_matter_revisions.tenant_id
              and pm.id = project_matter_revisions.matter_id
        )
    );

create policy project_conflict_checks_matter_access on gba.project_conflict_checks as restrictive to gba_runtime
    using (
        exists (
            select 1 from gba.project_matters pm
            where pm.tenant_id = project_conflict_checks.tenant_id
              and pm.id = project_conflict_checks.matter_id
        )
    )
    with check (
        exists (
            select 1 from gba.project_matters pm
            where pm.tenant_id = project_conflict_checks.tenant_id
              and pm.id = project_conflict_checks.matter_id
        )
    );

-- Projects matters branch scope:
create policy project_matters_location_scope on gba.project_matters as restrictive to gba_runtime
    using (gba.current_location_id() is null or location_id = gba.current_location_id())
    with check (gba.current_location_id() is null or location_id = gba.current_location_id());

create policy project_matter_members_location_scope on gba.project_matter_members as restrictive to gba_runtime
    using (gba.current_location_id() is null or location_id = gba.current_location_id())
    with check (gba.current_location_id() is null or location_id = gba.current_location_id());

create policy project_matter_revisions_location_scope on gba.project_matter_revisions as restrictive to gba_runtime
    using (gba.current_location_id() is null or location_id = gba.current_location_id())
    with check (gba.current_location_id() is null or location_id = gba.current_location_id());

create policy project_conflict_checks_location_scope on gba.project_conflict_checks as restrictive to gba_runtime
    using (gba.current_location_id() is null or location_id = gba.current_location_id())
    with check (gba.current_location_id() is null or location_id = gba.current_location_id());
