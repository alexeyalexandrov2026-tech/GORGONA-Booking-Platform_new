-- I2: immutable proposals, explicit recipient consent, manager approval.
-- Reuse I1 versions, assignments and the immediate shared exclusion constraint.
create table gba.shift_change_requests (
    tenant_id uuid not null references gba.tenants(id),
    id uuid not null default uuidv7(),
    location_id uuid not null,
    other_location_id uuid,
    kind text not null constraint shift_change_requests_kind_check check (kind in ('handover','swap','pickup')),
    shift_id uuid not null,
    shift_revision integer not null constraint shift_change_requests_revision_check check (shift_revision between 1 and 2147483646),
    other_shift_id uuid,
    other_shift_revision integer,
    from_profile_id uuid,
    from_assignment_id uuid,
    other_assignment_id uuid,
    target_profile_id uuid not null,
    proposed_by uuid not null references gba.users(id),
    recipient_user_id uuid not null references gba.users(id),
    created_at timestamptz not null default now(),
    creation_xid xid8 not null default pg_current_xact_id(),
    primary key (tenant_id,id),
    foreign key (tenant_id,location_id) references gba.locations(tenant_id,id),
    foreign key (tenant_id,other_location_id) references gba.locations(tenant_id,id),
    foreign key (tenant_id,shift_id,shift_revision) references gba.work_shift_versions(tenant_id,shift_id,revision),
    foreign key (tenant_id,other_shift_id,other_shift_revision) references gba.work_shift_versions(tenant_id,shift_id,revision),
    foreign key (tenant_id,from_profile_id) references gba.staff_profiles(tenant_id,id),
    foreign key (tenant_id,target_profile_id) references gba.staff_profiles(tenant_id,id),
    foreign key (tenant_id,from_assignment_id) references gba.shift_assignments(tenant_id,id),
    foreign key (tenant_id,other_assignment_id) references gba.shift_assignments(tenant_id,id),
    constraint shift_change_requests_shape_check check (
        (kind='swap' and other_shift_id is not null and other_shift_id<>shift_id
            and other_shift_revision between 1 and 2147483646 and other_location_id is not null
            and from_profile_id is not null and from_assignment_id is not null and other_assignment_id is not null)
        or (kind='handover' and other_shift_id is null and other_shift_revision is null
            and other_location_id is null and other_assignment_id is null
            and from_profile_id is not null and from_assignment_id is not null)
        or (kind='pickup' and other_shift_id is null and other_shift_revision is null
            and other_location_id is null and other_assignment_id is null
            and from_profile_id is null and from_assignment_id is null)
    )
);
create table gba.shift_change_skill_snapshots (
    tenant_id uuid not null,
    request_id uuid not null,
    profile_id uuid not null,
    skill_id uuid not null,
    catalogue_revision integer not null constraint shift_change_skill_snapshots_catalogue_check check (catalogue_revision>0),
    staff_revision integer not null constraint shift_change_skill_snapshots_staff_check check (staff_revision>=0),
    creation_xid xid8 not null default pg_current_xact_id(),
    primary key (tenant_id,request_id,profile_id,skill_id),
    foreign key (tenant_id,request_id) references gba.shift_change_requests(tenant_id,id),
    foreign key (tenant_id,profile_id) references gba.staff_profiles(tenant_id,id),
    foreign key (tenant_id,skill_id,catalogue_revision) references gba.work_skill_versions(tenant_id,skill_id,revision)
);
create table gba.shift_change_events (
    tenant_id uuid not null,
    request_id uuid not null,
    revision integer not null constraint shift_change_events_revision_check check (revision>0),
    action text not null constraint shift_change_events_action_check check (action in ('propose','accept','approve','decline','withdraw')),
    status text not null constraint shift_change_events_status_check check (status in ('proposed','accepted','approved','declined','withdrawn')),
    created_by uuid not null references gba.users(id),
    created_at timestamptz not null default now(),
    creation_xid xid8 not null default pg_current_xact_id(),
    primary key (tenant_id,request_id,revision),
    foreign key (tenant_id,request_id) references gba.shift_change_requests(tenant_id,id)
);

-- Both new versions exist before this runs. Release ALL prior allocations first.
-- Preserve immediate exclusion and the existing release-by-new-version guard.
create or replace function gba.apply_work_shift_version() returns trigger language plpgsql as $$
declare expected_releases bigint; actual_releases bigint;
begin
    if (select count(*) from inserted_versions) <> (
        select count(distinct (tenant_id,shift_id)) from inserted_versions
    ) then
        raise exception using errcode='23514', message='one version per shift per statement';
    end if;
    -- An assigned shift may be located outside its employee's home branch.
    -- A narrow SQL scope must refuse the whole change rather than silently
    -- skipping the invisible prior resource and leaving its occupancy active.
    if exists (
        select 1 from inserted_versions v join gba.work_shift_versions previous
          on previous.tenant_id=v.tenant_id and previous.shift_id=v.shift_id
            and previous.revision=v.revision-1
        where previous.profile_id is not null and not exists (
            select 1 from gba.staff_profiles p join gba.resources r
              on r.tenant_id=p.tenant_id and r.id=p.resource_id
            where p.tenant_id=previous.tenant_id and p.id=previous.profile_id
        )
    ) then
        raise exception using errcode='42501', message='the prior assignment resource is outside scope';
    end if;
    select count(*) into expected_releases
      from inserted_versions v join gba.work_shift_versions previous
        on previous.tenant_id=v.tenant_id and previous.shift_id=v.shift_id
          and previous.revision=v.revision-1
     where previous.profile_id is not null;
    update gba.resource_allocations r set state='released'
     where r.source_kind='shift' and r.state='confirmed' and exists (
        select 1 from gba.shift_assignments a join inserted_versions v
          on v.tenant_id=a.tenant_id and v.shift_id=a.shift_id and a.shift_revision<v.revision
         where a.tenant_id=r.tenant_id and a.id=r.source_id
    );
    get diagnostics actual_releases = row_count;
    if actual_releases<>expected_releases then
        raise exception using errcode='23514', message='every prior assignment must release exactly one allocation';
    end if;
    insert into gba.shift_assignments (tenant_id,shift_id,shift_revision,profile_id)
    select tenant_id,shift_id,revision,profile_id from inserted_versions
     where profile_id is not null order by tenant_id,shift_id;
    insert into gba.resource_allocations (tenant_id,resource_id,source_kind,source_id,during,state)
    select v.tenant_id,p.resource_id,'shift',a.id,tstzrange(v.starts_at,v.ends_at,'[)'),'confirmed'
      from inserted_versions v join gba.shift_assignments a
        on a.tenant_id=v.tenant_id and a.shift_id=v.shift_id and a.shift_revision=v.revision
      join gba.staff_profiles p on p.tenant_id=v.tenant_id and p.id=v.profile_id
     order by p.resource_id,v.shift_id;
    return null;
end;
$$;
drop trigger work_shift_versions_apply on gba.work_shift_versions;
create trigger work_shift_versions_apply after insert on gba.work_shift_versions
    referencing new table as inserted_versions for each statement execute function gba.apply_work_shift_version();

create function gba.guard_shift_change_request() returns trigger language plpgsql as $$
declare first gba.work_shift_versions; second gba.work_shift_versions; resource uuid; shift uuid; skill uuid;
    recipient uuid; recipient_home uuid; origin uuid; latest integer;
begin
    if new.proposed_by is distinct from gba.current_user_id() or not exists (
        select 1 from gba.memberships m join gba.users u on u.id=m.user_id
         where m.tenant_id=new.tenant_id and m.user_id=new.proposed_by and m.status='active' and u.status='active'
    ) then
        raise exception using errcode='42501', message='a change is proposed by its authenticated member';
    end if;
    select * into first from gba.work_shift_versions where tenant_id=new.tenant_id
        and shift_id=new.shift_id and revision=new.shift_revision;
    select * into second from gba.work_shift_versions where tenant_id=new.tenant_id
        and shift_id=new.other_shift_id and revision=new.other_shift_revision;
    if first.shift_id is null or first.status<>'published' or
        (new.kind='swap' and (second.shift_id is null or second.status<>'published')) then
        raise exception using errcode='23514', message='a change needs published shift versions';
    end if;
    for resource in select distinct p.resource_id from gba.staff_profiles p
        where p.tenant_id=new.tenant_id and p.id in (first.profile_id,second.profile_id,new.target_profile_id)
        order by p.resource_id
    loop
        perform pg_catalog.pg_advisory_xact_lock(pg_catalog.hashtextextended(
            'gba:resource:'||new.tenant_id::text||':'||resource::text,0));
    end loop;
    for shift in select s.id from gba.work_shifts s where s.tenant_id=new.tenant_id
        and s.id in (new.shift_id,new.other_shift_id) order by s.id for update
    loop
        select max(v.revision) into latest from gba.work_shift_versions v
         where v.tenant_id=new.tenant_id and v.shift_id=shift;
        if latest <> (case when shift=new.shift_id then new.shift_revision else new.other_shift_revision end) then
            raise exception using errcode='GBW01', message='a proposal needs the current shift versions';
        end if;
    end loop;
    if not exists (select 1 from gba.work_shifts where tenant_id=new.tenant_id and id=new.shift_id)
        or (new.kind='swap' and not exists (select 1 from gba.work_shifts where tenant_id=new.tenant_id and id=new.other_shift_id)) then
        raise exception using errcode='23514', message='a shift is outside the change scope';
    end if;
    select p.user_id,p.location_id into recipient,recipient_home from gba.staff_profiles p join gba.memberships m
      on m.tenant_id=p.tenant_id and m.id=p.membership_id join gba.users u on u.id=m.user_id
     where p.tenant_id=new.tenant_id and p.id=new.target_profile_id and m.status='active' and u.status='active'
     for share of m;
    select user_id into origin from gba.staff_profiles where tenant_id=new.tenant_id and id=first.profile_id;
    if recipient is null or (new.kind='pickup' and (first.profile_id is not null or recipient<>new.proposed_by))
        or (new.kind in ('handover','swap') and (origin is distinct from new.proposed_by or recipient=origin))
        or (new.kind='swap' and second.profile_id is distinct from new.target_profile_id) then
        raise exception using errcode='42501', message='only the outgoing employee or open-shift recipient may propose';
    end if;
    new.from_profile_id := first.profile_id;
    new.recipient_user_id := recipient;
    select location_id into new.location_id from gba.work_shifts where tenant_id=new.tenant_id and id=new.shift_id;
    if new.kind='pickup' and new.location_id<>recipient_home then
        raise exception using errcode='42501', message='an employee may pick up open shifts only in their home branch';
    end if;
    select location_id into new.other_location_id from gba.work_shifts where tenant_id=new.tenant_id and id=new.other_shift_id;
    select id into new.from_assignment_id from gba.shift_assignments where tenant_id=new.tenant_id
        and shift_id=new.shift_id and shift_revision=new.shift_revision;
    select id into new.other_assignment_id from gba.shift_assignments where tenant_id=new.tenant_id
        and shift_id=new.other_shift_id and shift_revision=new.other_shift_revision;
    for skill in select s.id from gba.work_skills s where s.tenant_id=new.tenant_id
        and s.id=any(first.required_skill_ids||coalesce(second.required_skill_ids,'{}'::uuid[]))
        order by s.id for share
    loop
        null;
    end loop;
    return new;
end;
$$;

create function gba.guard_shift_change_snapshot() returns trigger language plpgsql as $$
declare request gba.shift_change_requests; catalogue integer; staff integer;
begin
    select * into request from gba.shift_change_requests where tenant_id=new.tenant_id and id=new.request_id;
    if request.id is null or request.creation_xid<>pg_current_xact_id()
        or new.creation_xid<>request.creation_xid
        or new.profile_id not in (request.target_profile_id,coalesce(request.from_profile_id,request.target_profile_id))
        or not exists (select 1 from gba.work_shift_versions v where v.tenant_id=new.tenant_id
            and ((v.shift_id=request.shift_id and v.revision=request.shift_revision)
              or (v.shift_id=request.other_shift_id and v.revision=request.other_shift_revision))
            and new.skill_id=any(v.required_skill_ids)) then
        raise exception using errcode='23514', message='a snapshot belongs to the proposal construction';
    end if;
    select max(revision) into catalogue from gba.work_skill_versions where tenant_id=new.tenant_id and skill_id=new.skill_id;
    select coalesce(max(revision),0) into staff from gba.staff_skill_events where tenant_id=new.tenant_id
        and profile_id=new.profile_id and skill_id=new.skill_id;
    if new.catalogue_revision is distinct from catalogue or new.staff_revision<>staff then
        raise exception using errcode='23514', message='a snapshot captures the exact current skill versions';
    end if;
    return new;
end;
$$;
create function gba.initialize_shift_change() returns trigger language plpgsql as $$
begin
    insert into gba.shift_change_skill_snapshots (tenant_id,request_id,profile_id,skill_id,catalogue_revision,staff_revision)
    select new.tenant_id,new.id,p.id,s.id,
        (select max(revision) from gba.work_skill_versions where tenant_id=new.tenant_id and skill_id=s.id),
        (select coalesce(max(revision),0) from gba.staff_skill_events where tenant_id=new.tenant_id and profile_id=p.id and skill_id=s.id)
      from gba.staff_profiles p cross join gba.work_skills s
     where p.tenant_id=new.tenant_id and p.id in (new.from_profile_id,new.target_profile_id)
       and s.tenant_id=new.tenant_id and exists (
        select 1 from gba.work_shift_versions v where v.tenant_id=new.tenant_id
            and ((v.shift_id=new.shift_id and v.revision=new.shift_revision)
              or (v.shift_id=new.other_shift_id and v.revision=new.other_shift_revision))
            and s.id=any(v.required_skill_ids)) order by p.resource_id,s.id;
    insert into gba.shift_change_events (tenant_id,request_id,revision,action,created_by)
    values (new.tenant_id,new.id,1,'propose',new.proposed_by);
    return null;
end;
$$;

create function gba.guard_shift_change_event() returns trigger language plpgsql as $$
declare request gba.shift_change_requests; resource uuid; shift uuid; skill uuid; latest integer; previous text;
    role text; home uuid; visible integer;
begin
    select * into request from gba.shift_change_requests where tenant_id=new.tenant_id and id=new.request_id;
    if request.id is null then
        raise exception using errcode='23514', message='change request is outside scope';
    end if;
    select m.role,m.location_id into role,home from gba.memberships m join gba.users u on u.id=m.user_id
     where m.tenant_id=new.tenant_id and m.user_id=new.created_by and m.status='active' and u.status='active' for share of m;
    if new.created_by is distinct from gba.current_user_id() or role is null then
        raise exception using errcode='42501', message='a change event needs its authenticated active member';
    end if;
    for resource in select distinct p.resource_id from gba.staff_profiles p
        where p.tenant_id=new.tenant_id and p.id in (request.from_profile_id,request.target_profile_id)
        order by p.resource_id
    loop
        perform pg_catalog.pg_advisory_xact_lock(pg_catalog.hashtextextended(
            'gba:resource:'||new.tenant_id::text||':'||resource::text,0));
    end loop;
    select count(*) into visible from gba.staff_profiles where tenant_id=new.tenant_id
        and id in (request.from_profile_id,request.target_profile_id);
    if visible<>(case when request.from_profile_id is null then 1 else 2 end) then
        raise exception using errcode='42501', message='change participants are outside the branch scope';
    end if;
    for shift in select s.id from gba.work_shifts s where s.tenant_id=new.tenant_id
        and s.id in (request.shift_id,request.other_shift_id) order by s.id for update
    loop
        null;
    end loop;
    select count(*) into visible from gba.work_shifts where tenant_id=new.tenant_id
        and id in (request.shift_id,request.other_shift_id);
    if visible<>(case when request.kind='swap' then 2 else 1 end) then
        raise exception using errcode='42501', message='change shifts are outside the branch scope';
    end if;
    -- Lock catalog heads before reading revisions: staff events use resource locks,
    -- but a catalog rename/archive serializes only on this head.
    for skill in select s.id from gba.work_skills s where s.tenant_id=new.tenant_id
        and s.id in (select skill_id from gba.shift_change_skill_snapshots where tenant_id=new.tenant_id and request_id=new.request_id)
        order by s.id for share
    loop
        null;
    end loop;
    perform 1 from gba.shift_change_requests where tenant_id=new.tenant_id and id=new.request_id for update;
    select revision,status into latest,previous from gba.shift_change_events where tenant_id=new.tenant_id
        and request_id=new.request_id order by revision desc limit 1;
    latest := coalesce(latest,0);
    if new.revision<>latest+1 then
        raise exception using errcode='GBW01', message='stale change event revision';
    end if;
    if previous in ('approved','declined','withdrawn') then
        raise exception using errcode='GBW01', message='a finished change cannot transition';
    end if;
    if new.action='propose' then
        if latest<>0 or request.creation_xid<>pg_current_xact_id() or new.created_by<>request.proposed_by then
            raise exception using errcode='GBW01', message='a proposal event is part of request construction';
        end if;
        new.status := 'proposed';
    elsif new.action='accept' then
        if new.created_by<>request.recipient_user_id then
            raise exception using errcode='42501', message='only the recipient gives this consent';
        end if;
        if previous<>'proposed' then
            raise exception using errcode='GBW01', message='the recipient must explicitly accept a proposed change';
        end if;
        new.status := 'accepted';
    elsif new.action='withdraw' then
        if previous not in ('proposed','accepted') or new.created_by<>request.proposed_by then
            raise exception using errcode='42501', message='only the proposer withdraws a pending change';
        end if;
        new.status := 'withdrawn';
    elsif new.action='decline' then
        if new.created_by<>request.recipient_user_id and role not in ('owner','manager') then
            raise exception using errcode='42501', message='only recipient or manager declines a change';
        end if;
        if new.created_by<>request.recipient_user_id and home is not null
            and (home<>request.location_id or (request.other_location_id is not null and home<>request.other_location_id)) then
            raise exception using errcode='42501', message='a manager cannot decline another branch change';
        end if;
        new.status := 'declined';
    elsif new.action='approve' then
        if role not in ('owner','manager') or (request.kind='pickup' and new.created_by=request.recipient_user_id) then
            raise exception using errcode='42501', message='a pickup needs a second manager decision';
        end if;
        if previous<>'accepted' then
            raise exception using errcode='GBW01', message='recipient consent precedes approval';
        end if;
        if home is not null and (home<>request.location_id
            or (request.other_location_id is not null and home<>request.other_location_id)
            or exists (select 1 from gba.staff_profiles p where p.tenant_id=new.tenant_id
                and p.id in (request.from_profile_id,request.target_profile_id) and p.location_id<>home)) then
            raise exception using errcode='42501', message='cross-home changes need company-wide management';
        end if;
        if exists (select 1 from gba.work_shift_versions v where v.tenant_id=new.tenant_id
            and ((v.shift_id=request.shift_id and v.revision>request.shift_revision)
              or (v.shift_id=request.other_shift_id and v.revision>request.other_shift_revision))) then
            raise exception using errcode='GBW01', message='a proposed shift or assignment has changed';
        end if;
        if exists (select 1 from gba.shift_change_skill_snapshots s where s.tenant_id=new.tenant_id and s.request_id=new.request_id
            and (s.catalogue_revision is distinct from (select max(revision) from gba.work_skill_versions
                    where tenant_id=s.tenant_id and skill_id=s.skill_id)
                or s.staff_revision<>(select coalesce(max(revision),0) from gba.staff_skill_events
                    where tenant_id=s.tenant_id and profile_id=s.profile_id and skill_id=s.skill_id))) then
            raise exception using errcode='GBW01', message='a proposed skill snapshot has changed';
        end if;
        new.status := 'approved';
    else
        raise exception using errcode='23514', message='unknown change event';
    end if;
    return new;
end;
$$;
create function gba.apply_shift_change_event() returns trigger language plpgsql as $$
declare request gba.shift_change_requests;
begin
    if new.status<>'approved' then return null; end if;
    select * into request from gba.shift_change_requests where tenant_id=new.tenant_id and id=new.request_id;
    insert into gba.work_shift_versions (tenant_id,shift_id,revision,position,starts_at,ends_at,required_skill_ids,status,profile_id,created_by)
    select v.tenant_id,v.shift_id,v.revision+1,v.position,v.starts_at,v.ends_at,v.required_skill_ids,'published',
        case when v.shift_id=request.shift_id then request.target_profile_id else request.from_profile_id end,new.created_by
      from gba.work_shift_versions v where v.tenant_id=new.tenant_id
        and ((v.shift_id=request.shift_id and v.revision=request.shift_revision)
          or (v.shift_id=request.other_shift_id and v.revision=request.other_shift_revision)) order by v.shift_id;
    return null;
end;
$$;
create function gba.check_shift_change_complete() returns trigger language plpgsql as $$
declare profiles integer; skills integer; actual integer;
begin
    profiles := case when new.from_profile_id is null then 1 else 2 end;
    select count(distinct x.skill) into skills from gba.work_shift_versions v
        cross join lateral unnest(v.required_skill_ids) x(skill) where v.tenant_id=new.tenant_id
        and ((v.shift_id=new.shift_id and v.revision=new.shift_revision)
          or (v.shift_id=new.other_shift_id and v.revision=new.other_shift_revision));
    select count(*) into actual from gba.shift_change_skill_snapshots where tenant_id=new.tenant_id and request_id=new.id;
    if actual<>profiles*skills or not exists (select 1 from gba.shift_change_events e
        where e.tenant_id=new.tenant_id and e.request_id=new.id and e.revision=1
          and e.action='propose' and e.status='proposed' and e.created_by=new.proposed_by and e.creation_xid=new.creation_xid) then
        raise exception using errcode='23514', message='a change requires its complete snapshot and proposal event';
    end if;
    return null;
end;
$$;

create trigger shift_change_requests_guard before insert on gba.shift_change_requests
    for each row execute function gba.guard_shift_change_request();
create trigger shift_change_requests_initialize after insert on gba.shift_change_requests
    for each row execute function gba.initialize_shift_change();
create constraint trigger shift_change_requests_complete after insert on gba.shift_change_requests
    deferrable initially deferred for each row execute function gba.check_shift_change_complete();
create trigger shift_change_skill_snapshots_guard before insert on gba.shift_change_skill_snapshots
    for each row execute function gba.guard_shift_change_snapshot();
create trigger shift_change_events_guard before insert on gba.shift_change_events
    for each row execute function gba.guard_shift_change_event();
create trigger shift_change_events_apply after insert on gba.shift_change_events
    for each row execute function gba.apply_shift_change_event();

alter table gba.shift_change_requests enable row level security;
alter table gba.shift_change_requests force row level security;
create policy shift_change_requests_tenant_isolation on gba.shift_change_requests
    using (tenant_id=gba.current_tenant_id()) with check (tenant_id=gba.current_tenant_id());
create policy shift_change_requests_location_scope on gba.shift_change_requests as restrictive to gba_runtime
    using (gba.current_location_id() is null or (location_id=gba.current_location_id() and (other_location_id is null or other_location_id=gba.current_location_id())))
    with check (gba.current_location_id() is null or (location_id=gba.current_location_id() and (other_location_id is null or other_location_id=gba.current_location_id())));
grant select on gba.shift_change_requests to gba_runtime;
grant insert (tenant_id,id,kind,shift_id,shift_revision,other_shift_id,other_shift_revision,target_profile_id,proposed_by) on gba.shift_change_requests to gba_runtime;
grant update (id) on gba.shift_change_requests to gba_runtime;
create trigger shift_change_requests_immutable before update or delete on gba.shift_change_requests
    for each row execute function gba.reject_counterparty_mutation();
create trigger shift_change_requests_require_workforce before insert on gba.shift_change_requests
    for each row execute function gba.require_enabled_module('workforce');
alter table gba.shift_change_skill_snapshots enable row level security;
alter table gba.shift_change_skill_snapshots force row level security;
create policy shift_change_skill_snapshots_tenant_isolation on gba.shift_change_skill_snapshots
    using (tenant_id=gba.current_tenant_id()) with check (tenant_id=gba.current_tenant_id());
create policy shift_change_skill_snapshots_location_scope on gba.shift_change_skill_snapshots as restrictive to gba_runtime
    using (exists (select 1 from gba.shift_change_requests r where r.tenant_id=shift_change_skill_snapshots.tenant_id and r.id=shift_change_skill_snapshots.request_id))
    with check (exists (select 1 from gba.shift_change_requests r where r.tenant_id=shift_change_skill_snapshots.tenant_id and r.id=shift_change_skill_snapshots.request_id));
grant select on gba.shift_change_skill_snapshots to gba_runtime;
grant insert (tenant_id,request_id,profile_id,skill_id,catalogue_revision,staff_revision) on gba.shift_change_skill_snapshots to gba_runtime;
create trigger shift_change_skill_snapshots_immutable before update or delete on gba.shift_change_skill_snapshots
    for each row execute function gba.reject_counterparty_mutation();
create trigger shift_change_skill_snapshots_require_workforce before insert on gba.shift_change_skill_snapshots
    for each row execute function gba.require_enabled_module('workforce');
alter table gba.shift_change_events enable row level security;
alter table gba.shift_change_events force row level security;
create policy shift_change_events_tenant_isolation on gba.shift_change_events
    using (tenant_id=gba.current_tenant_id()) with check (tenant_id=gba.current_tenant_id());
create policy shift_change_events_location_scope on gba.shift_change_events as restrictive to gba_runtime
    using (exists (select 1 from gba.shift_change_requests r where r.tenant_id=shift_change_events.tenant_id and r.id=shift_change_events.request_id))
    with check (exists (select 1 from gba.shift_change_requests r where r.tenant_id=shift_change_events.tenant_id and r.id=shift_change_events.request_id));
grant select on gba.shift_change_events to gba_runtime;
grant insert (tenant_id,request_id,revision,action,created_by) on gba.shift_change_events to gba_runtime;
create trigger shift_change_events_immutable before update or delete on gba.shift_change_events
    for each row execute function gba.reject_counterparty_mutation();
create trigger shift_change_events_require_workforce before insert on gba.shift_change_events
    for each row execute function gba.require_enabled_module('workforce');
revoke all on function gba.guard_shift_change_request() from public;
revoke all on function gba.guard_shift_change_snapshot() from public;
revoke all on function gba.initialize_shift_change() from public;
revoke all on function gba.guard_shift_change_event() from public;
revoke all on function gba.apply_shift_change_event() from public;
revoke all on function gba.check_shift_change_complete() from public;
