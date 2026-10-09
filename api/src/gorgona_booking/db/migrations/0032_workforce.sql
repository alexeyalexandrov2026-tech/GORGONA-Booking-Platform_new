-- I1 / ADR-0025: staff work time uses the existing shared occupancy constraint.
-- Forward only. No payroll, booking availability derivation or readiness promotion.
alter table gba.resources drop constraint resources_kind_valid;
alter table gba.resources add constraint resources_kind_valid
    check (kind in ('artist', 'chair', 'room', 'staff'));
alter table gba.resource_allocations drop constraint resource_allocations_source_kind;
alter table gba.resource_allocations add constraint resource_allocations_source_kind
    check (source_kind in ('booking', 'reservation', 'shift'));

-- Memberships can be revoked and re-issued. The person's resource is stable
-- across those immutable membership-specific profiles, preventing a second lane.
create table gba.staff_resource_owners (
    tenant_id uuid not null references gba.tenants(id),
    user_id uuid not null references gba.users(id),
    resource_id uuid not null,
    location_id uuid not null,
    created_by uuid not null references gba.users(id),
    created_at timestamptz not null default now(),
    primary key (tenant_id, user_id),
    unique (tenant_id, resource_id),
    unique (tenant_id, user_id, resource_id),
    foreign key (tenant_id, resource_id) references gba.resources(tenant_id, id),
    foreign key (tenant_id, location_id) references gba.locations(tenant_id, id)
);
create table gba.staff_profiles (
    tenant_id uuid not null references gba.tenants(id),
    id uuid not null,
    membership_id uuid not null,
    user_id uuid not null,
    resource_id uuid not null,
    location_id uuid not null,
    created_by uuid not null references gba.users(id),
    created_at timestamptz not null default now(),
    primary key (tenant_id, id),
    unique (tenant_id, membership_id),
    foreign key (tenant_id, user_id, resource_id)
        references gba.staff_resource_owners(tenant_id, user_id, resource_id),
    foreign key (tenant_id, membership_id) references gba.memberships(tenant_id, id),
    foreign key (tenant_id, resource_id) references gba.resources(tenant_id, id),
    foreign key (tenant_id, location_id) references gba.locations(tenant_id, id)
);
create table gba.work_skills (
    tenant_id uuid not null references gba.tenants(id),
    id uuid not null,
    code text not null constraint work_skills_code_check check (code ~ '^[A-Z][A-Z0-9_]{0,63}$'),
    created_at timestamptz not null default now(),
    primary key (tenant_id, id),
    unique (tenant_id, code)
);
create table gba.work_skill_versions (
    tenant_id uuid not null references gba.tenants(id),
    skill_id uuid not null,
    revision integer not null constraint work_skill_versions_revision_check check (revision > 0),
    name text not null constraint work_skill_versions_name_check
        check (length(btrim(name)) between 1 and 200 and name !~ '[[:cntrl:]]'),
    archived boolean not null,
    created_by uuid not null references gba.users(id),
    created_at timestamptz not null default now(),
    primary key (tenant_id, skill_id, revision),
    foreign key (tenant_id, skill_id) references gba.work_skills(tenant_id, id)
);
create table gba.staff_skill_events (
    tenant_id uuid not null references gba.tenants(id),
    profile_id uuid not null,
    skill_id uuid not null,
    revision integer not null constraint staff_skill_events_revision_check check (revision > 0),
    effective_at timestamptz not null constraint staff_skill_events_effective_check
        check (isfinite(effective_at) and extract(epoch from effective_at)>=-62104060800
               and extract(epoch from effective_at)<253370764800),
    granted boolean not null,
    created_by uuid not null references gba.users(id),
    created_at timestamptz not null default now(),
    primary key (tenant_id, profile_id, skill_id, revision),
    foreign key (tenant_id, profile_id) references gba.staff_profiles(tenant_id, id),
    foreign key (tenant_id, skill_id) references gba.work_skills(tenant_id, id)
);
create index staff_skill_events_effective on gba.staff_skill_events
    (tenant_id, profile_id, skill_id, effective_at desc, revision desc);
create table gba.work_shifts (
    tenant_id uuid not null references gba.tenants(id),
    id uuid not null,
    location_id uuid not null,
    created_at timestamptz not null default now(),
    primary key (tenant_id, id),
    foreign key (tenant_id, location_id) references gba.locations(tenant_id, id)
);
create table gba.work_shift_versions (
    tenant_id uuid not null references gba.tenants(id),
    shift_id uuid not null,
    revision integer not null constraint work_shift_versions_revision_check check (revision > 0),
    position text not null constraint work_shift_versions_position_check
        check (length(btrim(position)) between 1 and 200 and position !~ '[[:cntrl:]]'),
    starts_at timestamptz not null,
    ends_at timestamptz not null,
    required_skill_ids uuid[] not null,
    status text not null constraint work_shift_versions_status_check
        check (status in ('draft', 'published', 'cancelled')),
    profile_id uuid,
    created_by uuid not null references gba.users(id),
    created_at timestamptz not null default now(),
    creation_xid xid8 not null default pg_current_xact_id(),
    primary key (tenant_id, shift_id, revision),
    foreign key (tenant_id, shift_id) references gba.work_shifts(tenant_id, id),
    foreign key (tenant_id, profile_id) references gba.staff_profiles(tenant_id, id),
    constraint work_shift_versions_interval_check
        check (isfinite(starts_at) and isfinite(ends_at) and ends_at > starts_at
               and extract(epoch from starts_at)>=-62104060800
               and extract(epoch from ends_at)<253370764800
               and ends_at <= starts_at + interval '31 days'),
    constraint work_shift_versions_skills_check
        check (cardinality(required_skill_ids) <= 20
               and coalesce(array_ndims(required_skill_ids),1)=1
               and array_position(required_skill_ids, null) is null),
    constraint work_shift_versions_assignment_check check (status = 'published' or profile_id is null)
);
create index work_shift_versions_window on gba.work_shift_versions (tenant_id, starts_at, shift_id);
create table gba.shift_assignments (
    tenant_id uuid not null references gba.tenants(id),
    id uuid not null default uuidv7(),
    shift_id uuid not null,
    shift_revision integer not null,
    profile_id uuid not null,
    created_at timestamptz not null default now(),
    creation_xid xid8 not null default pg_current_xact_id(),
    primary key (tenant_id, id),
    unique (tenant_id, shift_id, shift_revision),
    foreign key (tenant_id, shift_id, shift_revision)
        references gba.work_shift_versions(tenant_id, shift_id, revision),
    foreign key (tenant_id, profile_id) references gba.staff_profiles(tenant_id, id)
);

create function gba.guard_staff_profile() returns trigger language plpgsql as $$
begin
    if not exists (
        select 1 from gba.memberships m join gba.resources r on r.tenant_id=m.tenant_id
        where m.tenant_id=new.tenant_id and m.id=new.membership_id and m.status='active'
          and m.user_id=new.user_id
          and (m.location_id is null or m.location_id=new.location_id)
          and r.id=new.resource_id and r.kind='staff' and r.is_active
          and r.location_id=new.location_id
          and exists (select 1 from gba.staff_resource_owners o where o.tenant_id=new.tenant_id
              and o.user_id=new.user_id and o.resource_id=new.resource_id and o.location_id=new.location_id)
        for share of m,r
    ) then
        raise exception using errcode='23514', message='a staff profile needs an active membership and home resource';
    end if;
    return new;
end;
$$;
create function gba.check_staff_resource() returns trigger language plpgsql as $$
begin
    if new.kind='staff' and not exists (
        select 1 from gba.staff_profiles p where p.tenant_id=new.tenant_id and p.resource_id=new.id
    ) then
        raise exception using errcode='23514', message='a staff resource requires its profile';
    end if;
    return null;
end;
$$;
create constraint trigger resources_staff_profile after insert on gba.resources
    deferrable initially deferred for each row execute function gba.check_staff_resource();
create function gba.protect_staff_resource() returns trigger language plpgsql as $$
begin
    if old.kind='staff' or new.kind='staff' then
        raise exception using errcode='23514', message='staff resources are owned by workforce';
    end if;
    if tg_op='DELETE' then
        return old;
    end if;
    return new;
end;
$$;
create trigger resources_staff_protected before update or delete on gba.resources
    for each row execute function gba.protect_staff_resource();

create function gba.guard_work_skill_version() returns trigger language plpgsql as $$
declare latest integer;
begin
    perform 1 from gba.work_skills where tenant_id=new.tenant_id and id=new.skill_id for update;
    select coalesce(max(revision),0) into latest from gba.work_skill_versions
     where tenant_id=new.tenant_id and skill_id=new.skill_id;
    if new.revision <> latest+1 then
        raise exception using errcode='GBW01', message='stale skill revision';
    end if;
    return new;
end;
$$;
create function gba.guard_staff_skill_event() returns trigger language plpgsql as $$
declare resource uuid; latest integer;
begin
    select resource_id into resource from gba.staff_profiles
     where tenant_id=new.tenant_id and id=new.profile_id;
    perform pg_catalog.pg_advisory_xact_lock(pg_catalog.hashtextextended(
        'gba:resource:'||new.tenant_id::text||':'||resource::text,0));
    select coalesce(max(revision),0) into latest from gba.staff_skill_events
     where tenant_id=new.tenant_id and profile_id=new.profile_id and skill_id=new.skill_id;
    if new.revision <> latest+1 then
        raise exception using errcode='GBW01', message='stale staff skill revision';
    end if;
    return new;
end;
$$;

-- Lock order for API and SQL: resources sorted by id, then the shift head.
-- Reading old version again after the lock also detects a changed lock set.
create function gba.guard_work_shift_version() returns trigger language plpgsql as $$
declare previous gba.work_shift_versions; latest integer; resource uuid; selected_profile uuid;
begin
    select * into previous from gba.work_shift_versions
     where tenant_id=new.tenant_id and shift_id=new.shift_id order by revision desc limit 1;
    for resource in select p.resource_id from gba.staff_profiles p
        where p.tenant_id=new.tenant_id and p.id in (new.profile_id,previous.profile_id)
        order by p.resource_id
    loop
        perform pg_catalog.pg_advisory_xact_lock(pg_catalog.hashtextextended(
            'gba:resource:'||new.tenant_id::text||':'||resource::text,0));
    end loop;
    perform 1 from gba.work_shifts where tenant_id=new.tenant_id and id=new.shift_id for update;
    select coalesce(max(revision),0) into latest from gba.work_shift_versions
     where tenant_id=new.tenant_id and shift_id=new.shift_id;
    if new.revision <> latest+1 or coalesce(previous.revision,0) <> latest then
        raise exception using errcode='GBW01', message='stale shift revision';
    end if;
    if previous.status='cancelled' or (new.status='cancelled' and latest=0)
       or (previous.status='published' and new.status='draft') then
        raise exception using errcode='23514', message='invalid shift transition';
    end if;
    if cardinality(new.required_skill_ids) <> (
        select count(distinct x) from unnest(new.required_skill_ids) x
    ) or exists (
        select 1 from unnest(new.required_skill_ids) x where not exists (
            select 1 from gba.work_skills s where s.tenant_id=new.tenant_id and s.id=x
        )
    ) then
        raise exception using errcode='23514', message='unknown or duplicate required skill';
    end if;
    if new.profile_id is not null then
        select p.id into selected_profile from gba.staff_profiles p join gba.memberships m
          on m.tenant_id=p.tenant_id and m.id=p.membership_id
          join gba.resources r on r.tenant_id=p.tenant_id and r.id=p.resource_id
          join gba.users u on u.id=m.user_id
         where p.tenant_id=new.tenant_id and p.id=new.profile_id and m.status='active'
           and u.status='active' and r.is_active and r.kind='staff'
           and r.location_id=p.location_id and (m.location_id is null or m.location_id=p.location_id)
         for share of m,r;
        if selected_profile is null then
            raise exception using errcode='23514', message='unknown or inactive staff profile';
        end if;
        perform 1 from gba.work_skills s where s.tenant_id=new.tenant_id
            and s.id=any(new.required_skill_ids) order by s.id for share;
        if exists (
            select 1 from unnest(new.required_skill_ids) x where not coalesce((
                select e.granted from gba.staff_skill_events e where e.tenant_id=new.tenant_id
                  and e.profile_id=new.profile_id and e.skill_id=x and e.effective_at<=new.starts_at
                 order by e.effective_at desc,e.revision desc limit 1
            ),false) or coalesce((select v.archived from gba.work_skill_versions v
                where v.tenant_id=new.tenant_id and v.skill_id=x order by v.revision desc limit 1),true)
        ) then
            raise exception using errcode='GBW02', message='required skill is not effective';
        end if;
    end if;
    return new;
end;
$$;

create function gba.apply_work_shift_version() returns trigger language plpgsql as $$
declare assignment uuid;
begin
    update gba.resource_allocations r set state='released'
     where r.tenant_id=new.tenant_id and r.source_kind='shift' and r.state='confirmed'
       and r.source_id in (select a.id from gba.shift_assignments a
           where a.tenant_id=new.tenant_id and a.shift_id=new.shift_id and a.shift_revision<new.revision);
    if new.profile_id is not null then
        insert into gba.shift_assignments (tenant_id,shift_id,shift_revision,profile_id)
        values (new.tenant_id,new.shift_id,new.revision,new.profile_id) returning id into assignment;
        insert into gba.resource_allocations (tenant_id,resource_id,source_kind,source_id,during,state)
        select new.tenant_id,p.resource_id,'shift',assignment,tstzrange(new.starts_at,new.ends_at,'[)'), 'confirmed'
          from gba.staff_profiles p where p.tenant_id=new.tenant_id and p.id=new.profile_id;
    end if;
    return null;
end;
$$;
create function gba.check_shift_assignment() returns trigger language plpgsql as $$
begin
    if not exists (
        select 1 from gba.work_shift_versions v join gba.staff_profiles p
          on p.tenant_id=v.tenant_id and p.id=new.profile_id
          join gba.resource_allocations r on r.tenant_id=p.tenant_id and r.resource_id=p.resource_id
         where v.tenant_id=new.tenant_id and v.shift_id=new.shift_id and v.revision=new.shift_revision
           and v.profile_id=new.profile_id and v.status='published'
           and v.creation_xid=new.creation_xid and new.creation_xid=pg_current_xact_id()
           and r.source_kind='shift' and r.source_id=new.id
           and r.during=tstzrange(v.starts_at,v.ends_at,'[)')
    ) then
        raise exception using errcode='23514', message='an assignment requires its exact shift and allocation';
    end if;
    return null;
end;
$$;
create constraint trigger shift_assignments_consistent after insert on gba.shift_assignments
    deferrable initially deferred for each row execute function gba.check_shift_assignment();
create trigger staff_profiles_guard before insert on gba.staff_profiles
    for each row execute function gba.guard_staff_profile();
create trigger work_skill_versions_guard before insert on gba.work_skill_versions
    for each row execute function gba.guard_work_skill_version();
create trigger staff_skill_events_guard before insert on gba.staff_skill_events
    for each row execute function gba.guard_staff_skill_event();
create trigger work_shift_versions_guard before insert on gba.work_shift_versions
    for each row execute function gba.guard_work_shift_version();
create trigger work_shift_versions_apply after insert on gba.work_shift_versions
    for each row execute function gba.apply_work_shift_version();

create function gba.check_workforce_head() returns trigger language plpgsql as $$
begin
    if (tg_table_name='work_shifts' and not exists (
        select 1 from gba.work_shift_versions where tenant_id=new.tenant_id and shift_id=new.id
    )) or (tg_table_name='work_skills' and not exists (
        select 1 from gba.work_skill_versions where tenant_id=new.tenant_id and skill_id=new.id
    )) then
        raise exception using errcode='23514', message='a workforce head requires its first version';
    end if;
    return null;
end;
$$;
create function gba.guard_staff_resource_owner() returns trigger language plpgsql as $$
begin
    if not exists (select 1 from gba.resources r where r.tenant_id=new.tenant_id
        and r.id=new.resource_id and r.kind='staff' and r.is_active and r.location_id=new.location_id) then
        raise exception using errcode='23514', message='a staff resource ownership needs its home resource';
    end if;
    return new;
end;
$$;
revoke all on function gba.guard_staff_resource_owner() from public;
create trigger staff_resource_owners_guard before insert on gba.staff_resource_owners
    for each row execute function gba.guard_staff_resource_owner();

-- A home transfer requires a separate audited lifecycle, not a membership edit
-- that silently invalidates the immutable profile and shared occupancy history.
create function gba.guard_staff_membership_home() returns trigger language plpgsql as $$
begin
    if new.location_id is distinct from old.location_id and gba.current_location_id() is not null then
        raise exception using errcode='23514', message='membership home changes need company-wide scope';
    end if;
    if new.location_id is distinct from old.location_id and new.location_id is not null
        and exists (select 1 from gba.staff_profiles p where p.tenant_id=new.tenant_id
            and p.membership_id=new.id and p.location_id<>new.location_id) then
        raise exception using errcode='23514', message='a workforce membership keeps its home branch';
    end if;
    return new;
end;
$$;
revoke all on function gba.guard_staff_membership_home() from public;
create trigger memberships_staff_home before update on gba.memberships
    for each row execute function gba.guard_staff_membership_home();
revoke all on function gba.check_workforce_head() from public;
create constraint trigger work_shifts_version_required after insert on gba.work_shifts
    deferrable initially deferred for each row execute function gba.check_workforce_head();
create constraint trigger work_skills_version_required after insert on gba.work_skills
    deferrable initially deferred for each row execute function gba.check_workforce_head();

-- Grants, tenant/location policies and immutable/module guards are declared below.
alter table gba.staff_resource_owners enable row level security;
alter table gba.staff_resource_owners force row level security;
create policy staff_resource_owners_tenant_isolation on gba.staff_resource_owners
    using (tenant_id=gba.current_tenant_id()) with check (tenant_id=gba.current_tenant_id());
create policy staff_resource_owners_location_scope on gba.staff_resource_owners as restrictive to gba_runtime
    using (gba.current_location_id() is null or location_id=gba.current_location_id())
    with check (gba.current_location_id() is null or location_id=gba.current_location_id());
grant select on gba.staff_resource_owners to gba_runtime;
grant insert (tenant_id,user_id,resource_id,location_id,created_by) on gba.staff_resource_owners to gba_runtime;
create trigger staff_resource_owners_immutable before update or delete on gba.staff_resource_owners
    for each row execute function gba.reject_counterparty_mutation();
create trigger staff_resource_owners_require_workforce before insert on gba.staff_resource_owners
    for each row execute function gba.require_enabled_module('workforce');
-- PostgreSQL row-lock commands need column UPDATE rights. Immutability triggers
-- still reject every actual mutation, including an UPDATE that keeps the same id.
grant update (id) on gba.work_skills, gba.work_shifts to gba_runtime;

create or replace function gba.guard_resource_allocation() returns trigger language plpgsql as $$
begin
    if tg_op = 'DELETE' then
        raise exception using errcode = 'check_violation',
            message = 'resource allocations are kept';
    end if;
    if tg_op = 'UPDATE' then
        if (new.tenant_id, new.id, new.resource_id, new.source_kind, new.source_id,
            new.during, new.created_at)
           is distinct from (old.tenant_id, old.id, old.resource_id, old.source_kind,
                             old.source_id, old.during, old.created_at) then
            raise exception using errcode = 'check_violation',
                message = 'an allocation keeps its resource, source and interval';
        end if;
        if new.state is distinct from old.state and not (
            (old.state = 'held' and new.state in ('confirmed', 'released'))
            or (old.state = 'confirmed' and new.state = 'released')
        ) then
            raise exception using errcode = 'check_violation',
                message = 'this allocation state change is not allowed';
        end if;
        new.updated_at := pg_catalog.now();
    end if;
    if new.source_kind = 'booking' and not exists (
        select 1 from gba.booking_allocations a
        where a.tenant_id = new.tenant_id and a.booking_id = new.source_id
          and a.resource_id = new.resource_id and a.during = new.during
          and gba.booking_occupancy_state(a.booking_status) = new.state
    ) then
        raise exception using errcode = 'check_violation',
            message = 'a booking allocation follows its booking';
    end if;
    if new.source_kind = 'reservation' then
        if tg_op = 'INSERT' and not exists (
            select 1 from gba.resource_reservations v
            join gba.resources r
              on r.tenant_id = v.tenant_id and r.location_id = v.location_id
            where v.tenant_id = new.tenant_id and v.id = new.source_id
              and v.status = 'active' and new.state = 'confirmed'
              -- Only in the transaction that created the reservation.
              and v.created_at = pg_catalog.now()
              and new.during = tstzrange(v.starts_at, v.ends_at, '[)')
              and r.id = new.resource_id and r.is_active
        ) then
            raise exception using errcode = 'check_violation',
                message = 'a reservation allocation follows its active reservation';
        end if;
        if tg_op = 'UPDATE' and new.state = 'released' and not exists (
            select 1 from gba.resource_reservations v
            where v.tenant_id = new.tenant_id and v.id = new.source_id
              and v.status = 'cancelled'
        ) then
            raise exception using errcode = 'check_violation',
                message = 'a reservation allocation is released by its cancellation';
        end if;
        -- Mirrored bookings are decided by the exclusion constraint; this only
        -- covers booking allocations a company has not copied yet.
        if tg_op = 'INSERT' and exists (
            select 1 from gba.booking_allocations a
            where a.tenant_id = new.tenant_id and a.resource_id = new.resource_id
              and a.booking_status in ('HOLD', 'CONFIRMED') and a.during && new.during
              and not exists (
                  select 1 from gba.resource_allocations c
                  where c.tenant_id = a.tenant_id and c.source_kind = 'booking'
                    and c.source_id = a.booking_id and c.resource_id = a.resource_id)
        ) then
            raise exception using errcode = 'exclusion_violation',
                constraint = 'resource_allocations_no_overlap',
                message = 'the resource is booked in this interval';
        end if;
    end if;

    if exists (select 1 from gba.resources r where r.tenant_id=new.tenant_id
        and r.id=new.resource_id and (r.kind='staff') <> (new.source_kind='shift')) then
        raise exception using errcode='23514', message='staff occupancy is only for shifts';
    end if;
    if new.source_kind='shift' then
        if tg_op='INSERT' and not exists (
            select 1 from gba.shift_assignments a join gba.work_shift_versions v
              on v.tenant_id=a.tenant_id and v.shift_id=a.shift_id and v.revision=a.shift_revision
              join gba.staff_profiles p on p.tenant_id=a.tenant_id and p.id=a.profile_id
             where a.tenant_id=new.tenant_id and a.id=new.source_id
               and p.resource_id=new.resource_id and v.profile_id=p.id and v.status='published'
               and a.creation_xid=pg_current_xact_id() and v.creation_xid=a.creation_xid
               and new.during=tstzrange(v.starts_at,v.ends_at,'[)') and new.state='confirmed'
        ) then
            raise exception using errcode='23514', message='a shift allocation follows its exact assignment';
        end if;
        if tg_op='UPDATE' and new.state='released' and not exists (
            select 1 from gba.shift_assignments a join gba.work_shift_versions v
              on v.tenant_id=a.tenant_id and v.shift_id=a.shift_id and v.revision>a.shift_revision
             where a.tenant_id=new.tenant_id and a.id=new.source_id
        ) then
            raise exception using errcode='23514', message='a shift allocation is released by a new version';
        end if;
    end if;
    return new;
end;
$$;

alter table gba.staff_profiles enable row level security;
alter table gba.staff_profiles force row level security;
create policy staff_profiles_tenant_isolation on gba.staff_profiles
    using (tenant_id=gba.current_tenant_id()) with check (tenant_id=gba.current_tenant_id());
create policy staff_profiles_location_scope on gba.staff_profiles as restrictive to gba_runtime
    using ((gba.current_location_id() is null or location_id=gba.current_location_id())) with check ((gba.current_location_id() is null or location_id=gba.current_location_id()));
grant select on gba.staff_profiles to gba_runtime;
grant insert (tenant_id,id,membership_id,user_id,resource_id,location_id,created_by) on gba.staff_profiles to gba_runtime;
create trigger staff_profiles_immutable before update or delete on gba.staff_profiles
    for each row execute function gba.reject_counterparty_mutation();
create trigger staff_profiles_require_workforce before insert on gba.staff_profiles
    for each row execute function gba.require_enabled_module('workforce');

alter table gba.work_skills enable row level security;
alter table gba.work_skills force row level security;
create policy work_skills_tenant_isolation on gba.work_skills
    using (tenant_id=gba.current_tenant_id()) with check (tenant_id=gba.current_tenant_id());
create policy work_skills_location_scope on gba.work_skills as restrictive to gba_runtime
    using (true) with check (gba.current_location_id() is null);
grant select on gba.work_skills to gba_runtime;
grant insert (tenant_id,id,code) on gba.work_skills to gba_runtime;
create trigger work_skills_immutable before update or delete on gba.work_skills
    for each row execute function gba.reject_counterparty_mutation();
create trigger work_skills_require_workforce before insert on gba.work_skills
    for each row execute function gba.require_enabled_module('workforce');

alter table gba.work_skill_versions enable row level security;
alter table gba.work_skill_versions force row level security;
create policy work_skill_versions_tenant_isolation on gba.work_skill_versions
    using (tenant_id=gba.current_tenant_id()) with check (tenant_id=gba.current_tenant_id());
create policy work_skill_versions_location_scope on gba.work_skill_versions as restrictive to gba_runtime
    using (true) with check (gba.current_location_id() is null);
grant select on gba.work_skill_versions to gba_runtime;
grant insert (tenant_id,skill_id,revision,name,archived,created_by) on gba.work_skill_versions to gba_runtime;
create trigger work_skill_versions_immutable before update or delete on gba.work_skill_versions
    for each row execute function gba.reject_counterparty_mutation();
create trigger work_skill_versions_require_workforce before insert on gba.work_skill_versions
    for each row execute function gba.require_enabled_module('workforce');

alter table gba.staff_skill_events enable row level security;
alter table gba.staff_skill_events force row level security;
create policy staff_skill_events_tenant_isolation on gba.staff_skill_events
    using (tenant_id=gba.current_tenant_id()) with check (tenant_id=gba.current_tenant_id());
create policy staff_skill_events_location_scope on gba.staff_skill_events as restrictive to gba_runtime
    using ((gba.current_location_id() is null or exists (select 1 from gba.staff_profiles p where p.tenant_id=staff_skill_events.tenant_id and p.id=staff_skill_events.profile_id and p.location_id=gba.current_location_id()))) with check ((gba.current_location_id() is null or exists (select 1 from gba.staff_profiles p where p.tenant_id=staff_skill_events.tenant_id and p.id=staff_skill_events.profile_id and p.location_id=gba.current_location_id())));
grant select on gba.staff_skill_events to gba_runtime;
grant insert (tenant_id,profile_id,skill_id,revision,effective_at,granted,created_by) on gba.staff_skill_events to gba_runtime;
create trigger staff_skill_events_immutable before update or delete on gba.staff_skill_events
    for each row execute function gba.reject_counterparty_mutation();
create trigger staff_skill_events_require_workforce before insert on gba.staff_skill_events
    for each row execute function gba.require_enabled_module('workforce');

alter table gba.work_shifts enable row level security;
alter table gba.work_shifts force row level security;
create policy work_shifts_tenant_isolation on gba.work_shifts
    using (tenant_id=gba.current_tenant_id()) with check (tenant_id=gba.current_tenant_id());
create policy work_shifts_location_scope on gba.work_shifts as restrictive to gba_runtime
    using ((gba.current_location_id() is null or location_id=gba.current_location_id())) with check ((gba.current_location_id() is null or location_id=gba.current_location_id()));
grant select on gba.work_shifts to gba_runtime;
grant insert (tenant_id,id,location_id) on gba.work_shifts to gba_runtime;
create trigger work_shifts_immutable before update or delete on gba.work_shifts
    for each row execute function gba.reject_counterparty_mutation();
create trigger work_shifts_require_workforce before insert on gba.work_shifts
    for each row execute function gba.require_enabled_module('workforce');

alter table gba.work_shift_versions enable row level security;
alter table gba.work_shift_versions force row level security;
create policy work_shift_versions_tenant_isolation on gba.work_shift_versions
    using (tenant_id=gba.current_tenant_id()) with check (tenant_id=gba.current_tenant_id());
create policy work_shift_versions_location_scope on gba.work_shift_versions as restrictive to gba_runtime
    using ((gba.current_location_id() is null or exists (select 1 from gba.work_shifts s where s.tenant_id=work_shift_versions.tenant_id and s.id=work_shift_versions.shift_id and s.location_id=gba.current_location_id()))) with check ((gba.current_location_id() is null or exists (select 1 from gba.work_shifts s where s.tenant_id=work_shift_versions.tenant_id and s.id=work_shift_versions.shift_id and s.location_id=gba.current_location_id())));
grant select on gba.work_shift_versions to gba_runtime;
grant insert (tenant_id,shift_id,revision,position,starts_at,ends_at,required_skill_ids,status,profile_id,created_by) on gba.work_shift_versions to gba_runtime;
create trigger work_shift_versions_immutable before update or delete on gba.work_shift_versions
    for each row execute function gba.reject_counterparty_mutation();
create trigger work_shift_versions_require_workforce before insert on gba.work_shift_versions
    for each row execute function gba.require_enabled_module('workforce');

alter table gba.shift_assignments enable row level security;
alter table gba.shift_assignments force row level security;
create policy shift_assignments_tenant_isolation on gba.shift_assignments
    using (tenant_id=gba.current_tenant_id()) with check (tenant_id=gba.current_tenant_id());
create policy shift_assignments_location_scope on gba.shift_assignments as restrictive to gba_runtime
    using ((gba.current_location_id() is null or exists (select 1 from gba.work_shifts s where s.tenant_id=shift_assignments.tenant_id and s.id=shift_assignments.shift_id and s.location_id=gba.current_location_id()))) with check ((gba.current_location_id() is null or exists (select 1 from gba.work_shifts s where s.tenant_id=shift_assignments.tenant_id and s.id=shift_assignments.shift_id and s.location_id=gba.current_location_id())));
grant select on gba.shift_assignments to gba_runtime;
grant insert (tenant_id,id,shift_id,shift_revision,profile_id) on gba.shift_assignments to gba_runtime;
create trigger shift_assignments_immutable before update or delete on gba.shift_assignments
    for each row execute function gba.reject_counterparty_mutation();
create trigger shift_assignments_require_workforce before insert on gba.shift_assignments
    for each row execute function gba.require_enabled_module('workforce');
revoke all on function gba.guard_staff_profile() from public;
revoke all on function gba.check_staff_resource() from public;
revoke all on function gba.protect_staff_resource() from public;
revoke all on function gba.guard_work_skill_version() from public;
revoke all on function gba.guard_staff_skill_event() from public;
revoke all on function gba.guard_work_shift_version() from public;
revoke all on function gba.apply_work_shift_version() from public;
revoke all on function gba.check_shift_assignment() from public;
