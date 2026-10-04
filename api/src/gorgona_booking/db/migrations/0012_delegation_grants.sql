-- Cross-company delegation (ADR-0017): an owner business grants a servicing
-- business limited, expiring access; the servicer accepts and names its own
-- delegates. Both companies keep their own data; no shared account, no RLS bypass.
create table gba.delegation_grants (
    owner_tenant_id uuid not null references gba.tenants (id),
    id uuid not null,
    servicer_tenant_id uuid not null references gba.tenants (id),
    owner_display_name text not null check (length(btrim(owner_display_name)) between 1 and 200),
    servicer_display_name text check (length(btrim(servicer_display_name)) between 1 and 200),
    permissions text[] not null check (
        cardinality(permissions) between 1 and 4
        and permissions <@ array['booking.read', 'booking.write', 'catalog.read', 'staff.read']
    ),
    location_id uuid,
    expires_at timestamptz not null,
    status text not null default 'pending'
        check (status in ('pending', 'active', 'declined', 'revoked')),
    revision integer not null default 1 check (revision > 0),
    created_by uuid not null references gba.users (id),
    created_at timestamptz not null default now(),
    decided_by uuid references gba.users (id),
    decided_at timestamptz,
    revoked_by uuid references gba.users (id),
    revoked_at timestamptz,
    revoked_by_side text check (revoked_by_side in ('owner', 'servicer')),
    primary key (owner_tenant_id, id),
    constraint delegation_grants_id_unique unique (id),
    constraint delegation_grants_parties unique (owner_tenant_id, id, servicer_tenant_id),
    constraint delegation_grants_distinct_parties check (owner_tenant_id <> servicer_tenant_id),
    constraint delegation_grants_location_fk foreign key (owner_tenant_id, location_id)
        references gba.locations (tenant_id, id),
    constraint delegation_grants_expiry_after_issue check (expires_at > created_at),
    constraint delegation_grants_decision_complete
        check ((decided_at is null) = (decided_by is null)),
    constraint delegation_grants_revocation_complete check (
        (status = 'revoked') = (revoked_at is not null)
        and (revoked_at is null) = (revoked_by is null)
        and (revoked_at is null) = (revoked_by_side is null)
    )
);
-- One open relationship per pair: changing terms means revoking and issuing anew.
create unique index delegation_grants_one_open
    on gba.delegation_grants (owner_tenant_id, servicer_tenant_id)
    where status in ('pending', 'active');
create index delegation_grants_servicer_idx on gba.delegation_grants (servicer_tenant_id);

create table gba.delegation_grant_members (
    owner_tenant_id uuid not null,
    id uuid not null default uuidv7(),
    grant_id uuid not null,
    servicer_tenant_id uuid not null,
    user_id uuid not null references gba.users (id),
    display_name text not null check (length(btrim(display_name)) between 1 and 200),
    added_by uuid not null references gba.users (id),
    added_at timestamptz not null default now(),
    removed_by uuid references gba.users (id),
    removed_at timestamptz,
    primary key (owner_tenant_id, id),
    foreign key (owner_tenant_id, grant_id, servicer_tenant_id)
        references gba.delegation_grants (owner_tenant_id, id, servicer_tenant_id),
    constraint delegation_grant_members_removal_complete
        check ((removed_at is null) = (removed_by is null))
);
create unique index delegation_grant_members_one_live
    on gba.delegation_grant_members (owner_tenant_id, grant_id, user_id)
    where removed_at is null;
create index delegation_grant_members_user_idx on gba.delegation_grant_members (user_id);

alter table gba.delegation_grants enable row level security;
alter table gba.delegation_grants force row level security;
alter table gba.delegation_grant_members enable row level security;
alter table gba.delegation_grant_members force row level security;

-- Either party sees the relationship; a named delegate sees the grants it works under.
create policy delegation_grants_parties_read on gba.delegation_grants for select
    using (owner_tenant_id = gba.current_tenant_id()
           or servicer_tenant_id = gba.current_tenant_id()
           or exists (select 1 from gba.delegation_grant_members m
                      where m.owner_tenant_id = delegation_grants.owner_tenant_id
                        and m.grant_id = delegation_grants.id
                        and m.user_id = gba.current_user_id()
                        and m.removed_at is null));
create policy delegation_grants_owner_issue on gba.delegation_grants for insert
    with check (owner_tenant_id = gba.current_tenant_id());
create policy delegation_grants_parties_decide on gba.delegation_grants for update
    using (owner_tenant_id = gba.current_tenant_id()
           or servicer_tenant_id = gba.current_tenant_id())
    with check (owner_tenant_id = gba.current_tenant_id()
                or servicer_tenant_id = gba.current_tenant_id());
grant select on gba.delegation_grants to gba_runtime;
grant insert (owner_tenant_id, id, servicer_tenant_id, owner_display_name, permissions,
              location_id, expires_at, created_by)
    on gba.delegation_grants to gba_runtime;
grant update (status, revision, servicer_display_name, decided_by, decided_at, revoked_by,
              revoked_at, revoked_by_side)
    on gba.delegation_grants to gba_runtime;

-- The owner may lock delegate rows while authorizing; only the servicer changes them.
create policy delegation_grant_members_read on gba.delegation_grant_members for select
    using (owner_tenant_id = gba.current_tenant_id()
           or servicer_tenant_id = gba.current_tenant_id()
           or user_id = gba.current_user_id());
create policy delegation_grant_members_servicer_add on gba.delegation_grant_members for insert
    with check (servicer_tenant_id = gba.current_tenant_id());
create policy delegation_grant_members_servicer_remove on gba.delegation_grant_members
    for update
    using (owner_tenant_id = gba.current_tenant_id()
           or servicer_tenant_id = gba.current_tenant_id())
    with check (servicer_tenant_id = gba.current_tenant_id());
grant select on gba.delegation_grant_members to gba_runtime;
grant insert (owner_tenant_id, grant_id, servicer_tenant_id, user_id, display_name, added_by)
    on gba.delegation_grant_members to gba_runtime;
grant update (removed_by, removed_at) on gba.delegation_grant_members to gba_runtime;

create function gba.enforce_delegation_grant_change() returns trigger language plpgsql as $$
declare
    side text := case gba.current_tenant_id()
        when old.owner_tenant_id then 'owner'
        when old.servicer_tenant_id then 'servicer'
    end;
begin
    if tg_op = 'DELETE' then
        raise exception using errcode = 'check_violation',
            message = 'delegation grants are kept for audit';
    end if;
    if (new.owner_tenant_id, new.id, new.servicer_tenant_id, new.owner_display_name,
        new.permissions, new.location_id, new.expires_at, new.created_by, new.created_at)
       is distinct from
       (old.owner_tenant_id, old.id, old.servicer_tenant_id, old.owner_display_name,
        old.permissions, old.location_id, old.expires_at, old.created_by, old.created_at) then
        raise exception using errcode = 'check_violation',
            message = 'delegation grant terms are immutable';
    end if;
    if new.revision <> old.revision + 1 then
        raise exception using errcode = 'check_violation',
            message = 'delegation grant revision must advance by one';
    end if;
    if not (
        (side = 'servicer' and old.status = 'pending' and new.status in ('active', 'declined'))
        or (side = 'servicer' and old.status = 'active' and new.status = 'active')
        or (new.status = 'revoked' and new.revoked_by_side = side
            and (old.status = 'active' or (old.status = 'pending' and side = 'owner')))
    ) then
        raise exception using errcode = 'check_violation',
            message = 'invalid delegation grant transition';
    end if;
    if new.servicer_display_name is distinct from old.servicer_display_name
       and not (old.status = 'pending' and new.status = 'active') then
        raise exception using errcode = 'check_violation',
            message = 'servicer name is recorded only on acceptance';
    end if;
    -- Who decided or revoked, and when, is written once by that transition.
    if (new.decided_by, new.decided_at) is distinct from (old.decided_by, old.decided_at)
       and not (old.status = 'pending' and new.status in ('active', 'declined')) then
        raise exception using errcode = 'check_violation',
            message = 'delegation decisions are recorded only once';
    end if;
    if (new.revoked_by, new.revoked_at, new.revoked_by_side)
       is distinct from (old.revoked_by, old.revoked_at, old.revoked_by_side)
       and new.status <> 'revoked' then
        raise exception using errcode = 'check_violation',
            message = 'revocation details are recorded only by revocation';
    end if;
    return new;
end;
$$;
revoke all on function gba.enforce_delegation_grant_change() from public;
create trigger delegation_grants_enforce_change before update or delete on gba.delegation_grants
    for each row execute function gba.enforce_delegation_grant_change();

-- A delegate is an active company-wide member of the servicer, added to an active grant.
create function gba.enforce_delegation_member_change() returns trigger language plpgsql as $$
begin
    if tg_op = 'DELETE' then
        raise exception using errcode = 'check_violation',
            message = 'delegate history is kept for audit';
    end if;
    if tg_op = 'UPDATE' then
        if old.removed_at is not null
           or (new.owner_tenant_id, new.id, new.grant_id, new.servicer_tenant_id, new.user_id,
               new.display_name, new.added_by, new.added_at)
              is distinct from
              (old.owner_tenant_id, old.id, old.grant_id, old.servicer_tenant_id, old.user_id,
               old.display_name, old.added_by, old.added_at) then
            raise exception using errcode = 'check_violation',
                message = 'a delegate can only be removed once';
        end if;
        return new;
    end if;
    if not exists (select 1 from gba.delegation_grants g
                   where g.owner_tenant_id = new.owner_tenant_id and g.id = new.grant_id
                     and g.status = 'active')
       or not exists (select 1 from gba.memberships m
                      where m.tenant_id = new.servicer_tenant_id and m.user_id = new.user_id
                        and m.status = 'active' and m.location_id is null) then
        raise exception using errcode = 'check_violation',
            message = 'delegates must be active company-wide servicer members of an active grant';
    end if;
    return new;
end;
$$;
revoke all on function gba.enforce_delegation_member_change() from public;
create trigger delegation_grant_members_enforce_change
    before insert or update or delete on gba.delegation_grant_members
    for each row execute function gba.enforce_delegation_member_change();

-- Delegation branch scope: reusable separately when restoring a damaged boundary in tests.
create policy delegation_grants_unrestricted_scope on gba.delegation_grants
    as restrictive to gba_runtime
    using (gba.current_location_id() is null) with check (gba.current_location_id() is null);
create policy delegation_grant_members_unrestricted_scope on gba.delegation_grant_members
    as restrictive to gba_runtime
    using (gba.current_location_id() is null) with check (gba.current_location_id() is null);
