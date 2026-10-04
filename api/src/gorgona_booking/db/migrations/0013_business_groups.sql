-- Company groups (ADR-0018): an organizer business names a group and invites
-- independent businesses; each member accepts or declines. Membership records the
-- relationship only. It grants no access to any party's rows; consolidated reports
-- later read only sets that each owner explicitly grants.
create table gba.business_groups (
    organizer_tenant_id uuid not null references gba.tenants (id),
    id uuid not null,
    code text not null check (length(code) between 1 and 64 and code ~ '^[A-Z0-9][A-Z0-9_-]*$'),
    name text not null check (
        length(btrim(name, E' \t\r\n')) between 1 and 200 and name !~ '[[:cntrl:]]'
    ),
    organizer_display_name text not null
        check (length(btrim(organizer_display_name)) between 1 and 200),
    created_by uuid not null references gba.users (id),
    created_at timestamptz not null default now(),
    primary key (organizer_tenant_id, id),
    constraint business_groups_id_unique unique (id),
    constraint business_groups_code_unique unique (organizer_tenant_id, code)
);

create table gba.business_group_members (
    organizer_tenant_id uuid not null,
    id uuid not null default uuidv7(),
    group_id uuid not null,
    member_tenant_id uuid not null references gba.tenants (id),
    member_display_name text check (length(btrim(member_display_name)) between 1 and 200),
    status text not null default 'invited'
        check (status in ('invited', 'active', 'declined', 'left', 'removed')),
    revision integer not null default 1 check (revision > 0),
    invited_by uuid not null references gba.users (id),
    invited_at timestamptz not null default now(),
    decided_by uuid references gba.users (id),
    decided_at timestamptz,
    ended_by uuid references gba.users (id),
    ended_at timestamptz,
    primary key (organizer_tenant_id, id),
    foreign key (organizer_tenant_id, group_id)
        references gba.business_groups (organizer_tenant_id, id),
    constraint business_group_members_not_organizer
        check (member_tenant_id <> organizer_tenant_id),
    constraint business_group_members_decision_complete
        check ((decided_at is null) = (decided_by is null)),
    constraint business_group_members_end_complete check (
        (status in ('left', 'removed')) = (ended_at is not null)
        and (ended_at is null) = (ended_by is null)
    )
);
create unique index business_group_members_one_open
    on gba.business_group_members (organizer_tenant_id, group_id, member_tenant_id)
    where status in ('invited', 'active');
create index business_group_members_member_idx on gba.business_group_members (member_tenant_id);

alter table gba.business_groups enable row level security;
alter table gba.business_groups force row level security;
alter table gba.business_group_members enable row level security;
alter table gba.business_group_members force row level security;

-- An invited or member business sees the group, and only its own membership row.
create policy business_groups_parties_read on gba.business_groups for select
    using (organizer_tenant_id = gba.current_tenant_id()
           or exists (select 1 from gba.business_group_members m
                      where m.organizer_tenant_id = business_groups.organizer_tenant_id
                        and m.group_id = business_groups.id
                        and m.member_tenant_id = gba.current_tenant_id()));
create policy business_groups_organizer_create on gba.business_groups for insert
    with check (organizer_tenant_id = gba.current_tenant_id());
grant select on gba.business_groups to gba_runtime;
grant insert (organizer_tenant_id, id, code, name, organizer_display_name, created_by)
    on gba.business_groups to gba_runtime;

create policy business_group_members_parties_read on gba.business_group_members for select
    using (organizer_tenant_id = gba.current_tenant_id()
           or member_tenant_id = gba.current_tenant_id());
create policy business_group_members_organizer_invite on gba.business_group_members
    for insert with check (organizer_tenant_id = gba.current_tenant_id());
create policy business_group_members_parties_decide on gba.business_group_members for update
    using (organizer_tenant_id = gba.current_tenant_id()
           or member_tenant_id = gba.current_tenant_id())
    with check (organizer_tenant_id = gba.current_tenant_id()
                or member_tenant_id = gba.current_tenant_id());
grant select on gba.business_group_members to gba_runtime;
grant insert (organizer_tenant_id, group_id, member_tenant_id, invited_by)
    on gba.business_group_members to gba_runtime;
grant update (status, revision, member_display_name, decided_by, decided_at, ended_by, ended_at)
    on gba.business_group_members to gba_runtime;

create function gba.reject_business_group_mutation() returns trigger language plpgsql as $$
begin
    raise exception using errcode = 'check_violation',
        message = 'business group identities are immutable';
end;
$$;
revoke all on function gba.reject_business_group_mutation() from public;
create trigger business_groups_immutable before update or delete on gba.business_groups
    for each row execute function gba.reject_business_group_mutation();

create function gba.enforce_business_group_member_change() returns trigger
    language plpgsql as $$
declare
    side text := case gba.current_tenant_id()
        when old.organizer_tenant_id then 'organizer'
        when old.member_tenant_id then 'member'
    end;
begin
    if tg_op = 'DELETE' then
        raise exception using errcode = 'check_violation',
            message = 'group membership history is kept';
    end if;
    if (new.organizer_tenant_id, new.id, new.group_id, new.member_tenant_id, new.invited_by,
        new.invited_at)
       is distinct from
       (old.organizer_tenant_id, old.id, old.group_id, old.member_tenant_id, old.invited_by,
        old.invited_at)
       or new.revision <> old.revision + 1 then
        raise exception using errcode = 'check_violation',
            message = 'group membership identity is immutable and revisions advance by one';
    end if;
    if not (
        (side = 'member' and old.status = 'invited' and new.status in ('active', 'declined'))
        or (side = 'member' and old.status = 'active' and new.status = 'left')
        or (side = 'organizer' and old.status in ('invited', 'active')
            and new.status = 'removed')
    ) then
        raise exception using errcode = 'check_violation',
            message = 'invalid group membership transition';
    end if;
    if (new.member_display_name is distinct from old.member_display_name
        or (new.decided_by, new.decided_at) is distinct from (old.decided_by, old.decided_at))
       and old.status <> 'invited' then
        raise exception using errcode = 'check_violation',
            message = 'a membership decision is recorded once';
    end if;
    return new;
end;
$$;
revoke all on function gba.enforce_business_group_member_change() from public;
create trigger business_group_members_enforce_change
    before update or delete on gba.business_group_members
    for each row execute function gba.enforce_business_group_member_change();

-- Group branch scope: reusable separately when restoring a damaged boundary in tests.
create policy business_groups_unrestricted_scope on gba.business_groups
    as restrictive to gba_runtime
    using (gba.current_location_id() is null) with check (gba.current_location_id() is null);
create policy business_group_members_unrestricted_scope on gba.business_group_members
    as restrictive to gba_runtime
    using (gba.current_location_id() is null) with check (gba.current_location_id() is null);
