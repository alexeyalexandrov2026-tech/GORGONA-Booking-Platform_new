-- I3: immutable actual-work history and a checked, derivable current projection.
-- This accounts for worked time; it never reserves a shared resource or posts money.
create table gba.time_entries (
    tenant_id uuid not null references gba.tenants(id),
    id uuid not null,
    profile_id uuid not null,
    user_id uuid not null references gba.users(id),
    resource_id uuid not null,
    location_id uuid not null,
    shift_id uuid,
    shift_revision integer,
    shift_starts_at timestamptz,
    shift_ends_at timestamptz,
    starts_at timestamptz not null,
    created_by uuid not null references gba.users(id),
    created_at timestamptz not null default now(),
    creation_xid xid8 not null default pg_current_xact_id(),
    primary key (tenant_id,id),
    foreign key (tenant_id,profile_id) references gba.staff_profiles(tenant_id,id),
    foreign key (tenant_id,resource_id) references gba.resources(tenant_id,id),
    foreign key (tenant_id,location_id) references gba.locations(tenant_id,id),
    foreign key (tenant_id,shift_id,shift_revision) references gba.work_shift_versions(tenant_id,shift_id,revision),
    constraint time_entries_shift_check check ((shift_id is null and shift_revision is null
        and shift_starts_at is null and shift_ends_at is null)
        or (shift_id is not null and shift_revision is not null and shift_revision between 1 and 2147483646
            and shift_starts_at is not null and shift_ends_at is not null and shift_ends_at>shift_starts_at)),
    constraint time_entries_date_check check (isfinite(starts_at)
        and extract(epoch from starts_at)>=-62104060800 and extract(epoch from starts_at)<253370764800)
);
create table gba.time_entry_revisions (
    tenant_id uuid not null,
    entry_id uuid not null,
    revision integer not null constraint time_entry_revisions_revision_check check (revision>0),
    action text not null constraint time_entry_revisions_action_check check (action in
        ('clock_in','break_start','break_end','clock_out','correct','approve','decline')),
    status text not null constraint time_entry_revisions_status_check check (status in
        ('open','proposed','approved','declined')),
    occurred_at timestamptz not null,
    starts_at timestamptz not null,
    ends_at timestamptz,
    break_starts timestamptz[] not null,
    break_ends timestamptz[] not null,
    break_started_at timestamptz,
    reason text not null constraint time_entry_revisions_reason_check check (
        length(btrim(reason)) between 1 and 1000 and reason !~ '[[:cntrl:]]'),
    self_approved boolean not null,
    created_by uuid not null references gba.users(id),
    created_at timestamptz not null default now(),
    creation_xid xid8 not null default pg_current_xact_id(),
    primary key (tenant_id,entry_id,revision),
    foreign key (tenant_id,entry_id) references gba.time_entries(tenant_id,id),
    constraint time_entry_revisions_dates_check check (
        isfinite(occurred_at) and extract(epoch from occurred_at)>=-62104060800
        and extract(epoch from occurred_at)<253370764800
        and isfinite(starts_at) and extract(epoch from starts_at)>=-62104060800
        and extract(epoch from starts_at)<253370764800
        and (ends_at is null or (isfinite(ends_at) and ends_at>starts_at
            and extract(epoch from ends_at)<253370764800))
        and (break_started_at is null or (isfinite(break_started_at) and break_started_at>=starts_at
            and extract(epoch from break_started_at)<253370764800))),
    constraint time_entry_revisions_shape_check check (
        (status='open' and ends_at is null) or
        (status<>'open' and ends_at is not null and break_started_at is null)),
    constraint time_entry_revisions_arrays_check check (
        cardinality(break_starts)=cardinality(break_ends) and cardinality(break_starts)<=100
        and coalesce(array_ndims(break_starts),1)=1 and coalesce(array_ndims(break_ends),1)=1
        and coalesce(array_lower(break_starts,1),1)=1 and coalesce(array_lower(break_ends,1),1)=1)
);
create table gba.time_entry_state (
    tenant_id uuid not null,
    entry_id uuid not null,
    user_id uuid not null references gba.users(id),
    location_id uuid not null,
    last_revision integer not null constraint time_entry_state_revision_check check (last_revision>0),
    is_open boolean not null,
    approved_revision integer,
    starts_at timestamptz,
    ends_at timestamptz,
    primary key (tenant_id,entry_id),
    foreign key (tenant_id,entry_id) references gba.time_entries(tenant_id,id),
    foreign key (tenant_id,location_id) references gba.locations(tenant_id,id),
    foreign key (tenant_id,entry_id,last_revision) references gba.time_entry_revisions(tenant_id,entry_id,revision),
    foreign key (tenant_id,entry_id,approved_revision) references gba.time_entry_revisions(tenant_id,entry_id,revision),
    constraint time_entry_state_shape_check check (
        (approved_revision is null and starts_at is null and ends_at is null) or
        (approved_revision is not null and starts_at is not null and ends_at is not null
            and approved_revision<=last_revision and ends_at>starts_at)),
    constraint time_entry_state_one_open exclude using gist (tenant_id with =,user_id with =) where (is_open),
    constraint time_entry_state_no_overlap exclude using gist
        (tenant_id with =,user_id with =,tstzrange(starts_at,ends_at,'[)') with &&)
        where (approved_revision is not null)
);
create index time_entries_user_history on gba.time_entries(tenant_id,user_id,id);

create function gba.guard_time_entry() returns trigger language plpgsql as $$
declare profile gba.staff_profiles; selected_shift gba.work_shift_versions; branch_scope text; module_on boolean;
begin
    -- Configuration lock precedes the stable resource and entry locks everywhere.
    perform pg_catalog.pg_advisory_xact_lock_shared(pg_catalog.hashtextextended('gba:business-configuration:'||new.tenant_id::text,0));
    -- Row locking detects a configuration replaced after a REPEATABLE READ snapshot.
    -- Config is already tenant-readable in every branch; only this lock-read widens
    -- branch scope, because its UPDATE RLS applies to FOR SHARE. Restore before staff access.
    branch_scope := pg_catalog.current_setting('gba.location_id',true);
    perform pg_catalog.set_config('gba.location_id','',true);
    select enabled into module_on from gba.business_module_states where tenant_id=new.tenant_id
        and module_id='workforce' for share;
    perform pg_catalog.set_config('gba.location_id',coalesce(branch_scope,''),true);
    if not coalesce(module_on,false) then
        raise exception using errcode='GBM01', message='the workforce module is disabled for this business';
    end if;
    select p.* into profile from gba.staff_profiles p join gba.memberships m
      on m.tenant_id=p.tenant_id and m.id=p.membership_id join gba.users u on u.id=p.user_id
      join gba.resources r on r.tenant_id=p.tenant_id and r.id=p.resource_id
     where p.tenant_id=new.tenant_id and p.id=new.profile_id and p.user_id=gba.current_user_id()
       and m.status='active' and u.status='active' and r.is_active and r.kind='staff' for share of m,r;
    if profile.id is null or new.created_by is distinct from gba.current_user_id() then
        raise exception using errcode='42501', message='clock-in needs the authenticated employee active profile';
    end if;
    perform pg_catalog.pg_advisory_xact_lock(pg_catalog.hashtextextended('gba:resource:'||new.tenant_id::text||':'||profile.resource_id::text,0));
    new.user_id := profile.user_id; new.resource_id := profile.resource_id; new.location_id := profile.location_id;
    if new.shift_id is not null then
        perform 1 from gba.work_shifts where tenant_id=new.tenant_id and id=new.shift_id for update;
        select v.* into selected_shift from gba.work_shift_versions v join gba.staff_profiles p
          on p.tenant_id=v.tenant_id and p.id=v.profile_id
         where v.tenant_id=new.tenant_id and v.shift_id=new.shift_id and v.revision=new.shift_revision
           and p.user_id=new.user_id and v.status='published';
        if selected_shift.shift_id is null or new.shift_revision is distinct from (
            select max(revision) from gba.work_shift_versions where tenant_id=new.tenant_id and shift_id=new.shift_id
        ) then
            raise exception using errcode='42501', message='a clock-in shift link needs the employee current published assignment';
        end if;
        -- Version history is immutable, but replacing an assignment physically
        -- releases this row. Lock it to reject a stale RR snapshot with 40001.
        perform 1 from gba.resource_allocations r join gba.shift_assignments a
          on a.tenant_id=r.tenant_id and a.id=r.source_id
         where r.tenant_id=new.tenant_id and r.resource_id=new.resource_id
           and r.source_kind='shift' and r.state='confirmed'
           and a.shift_id=new.shift_id and a.shift_revision=new.shift_revision
           and a.profile_id=selected_shift.profile_id for share of r;
        if not found then
            raise exception using errcode='42501', message='a clock-in shift link needs its current confirmed assignment';
        end if;
        new.shift_starts_at := selected_shift.starts_at; new.shift_ends_at := selected_shift.ends_at;
    elsif new.shift_revision is not null then
        raise exception using errcode='23514', message='a clock-in shift reference needs both identifiers';
    end if;
    return new;
end;
$$;
create function gba.initialize_time_entry() returns trigger language plpgsql as $$
begin
    insert into gba.time_entry_revisions (tenant_id,entry_id,revision,action,occurred_at,created_by)
    values (new.tenant_id,new.id,1,'clock_in',new.starts_at,new.created_by);
    return null;
end;
$$;

create function gba.guard_time_entry_revision() returns trigger language plpgsql as $$
declare entry gba.time_entries; previous gba.time_entry_revisions; role text; home uuid; latest integer; pos integer;
    branch_scope text; module_on boolean;
begin
    perform pg_catalog.pg_advisory_xact_lock_shared(pg_catalog.hashtextextended('gba:business-configuration:'||new.tenant_id::text,0));
    if new.action<>'clock_out' then
        branch_scope := pg_catalog.current_setting('gba.location_id',true);
        perform pg_catalog.set_config('gba.location_id','',true);
        select enabled into module_on from gba.business_module_states where tenant_id=new.tenant_id
            and module_id='workforce' for share;
        perform pg_catalog.set_config('gba.location_id',coalesce(branch_scope,''),true);
        if not coalesce(module_on,false) then
            raise exception using errcode='GBM01', message='the workforce module is disabled for this business';
        end if;
    end if;
    select * into entry from gba.time_entries where tenant_id=new.tenant_id and id=new.entry_id;
    if entry.id is null then raise exception using errcode='42501', message='time entry is outside scope'; end if;
    select m.role,m.location_id into role,home from gba.memberships m join gba.users u on u.id=m.user_id
     where m.tenant_id=new.tenant_id and m.user_id=new.created_by and m.status='active' and u.status='active' for share of m;
    if new.created_by is distinct from gba.current_user_id() or role is null then
        raise exception using errcode='42501', message='a time revision needs its authenticated active member';
    end if;
    if new.action in ('approve','decline') then
        if home is not null and home<>entry.location_id then
            raise exception using errcode='42501', message='a manager decision stays inside their membership home';
        end if;
        if role not in ('owner','manager') or (new.action='approve' and new.created_by=entry.user_id and role<>'owner') then
            raise exception using errcode='42501', message='a manager cannot approve their own time entry';
        end if;
    elsif new.created_by<>entry.user_id then
        raise exception using errcode='42501', message='only the employee clocks or corrects their own time';
    end if;
    perform pg_catalog.pg_advisory_xact_lock(pg_catalog.hashtextextended('gba:resource:'||new.tenant_id::text||':'||entry.resource_id::text,0));
    perform 1 from gba.time_entries where tenant_id=new.tenant_id and id=new.entry_id for update;
    select * into previous from gba.time_entry_revisions where tenant_id=new.tenant_id
        and entry_id=new.entry_id order by revision desc limit 1;
    latest := coalesce(previous.revision,0);
    if new.revision<>latest+1 then raise exception using errcode='GBW01', message='stale time entry revision'; end if;
    if new.action<>'correct' and (new.starts_at is not null or new.ends_at is not null
        or new.break_starts is not null or new.break_ends is not null
        or (new.reason is not null and new.action<>'decline')) then
        raise exception using errcode='23514', message='clock and approval commands cannot replace the snapshot';
    end if;
    new.self_approved := false;
    if new.action='clock_in' then
        if latest<>0 or entry.creation_xid<>pg_current_xact_id()
            or new.created_by<>entry.created_by or new.occurred_at is distinct from entry.starts_at then
            raise exception using errcode='GBW01', message='clock-in is part of entry construction';
        end if;
        new.starts_at := entry.starts_at; new.ends_at := null;
        new.break_starts := '{}'::timestamptz[]; new.break_ends := '{}'::timestamptz[];
        new.break_started_at := null; new.status := 'open'; new.reason := 'Clock-in';
    elsif new.action in ('break_start','break_end','clock_out') then
        if previous.status is distinct from 'open' or new.occurred_at is null or new.occurred_at<previous.occurred_at then
            raise exception using errcode='GBW01', message='a clock command needs an open entry and nondecreasing time';
        end if;
        new.starts_at := previous.starts_at; new.ends_at := null;
        new.break_starts := previous.break_starts; new.break_ends := previous.break_ends;
        new.break_started_at := previous.break_started_at; new.status := 'open';
        if new.action='break_start' then
            if previous.break_started_at is not null then raise exception using errcode='GBW01', message='a break is already open'; end if;
            if cardinality(previous.break_starts)>=100 then
                raise exception using errcode='GBW01', message='the break limit preserves the ability to close the time entry';
            end if;
            new.break_started_at := new.occurred_at; new.reason := 'Break start';
        elsif new.action='break_end' then
            if previous.break_started_at is null then raise exception using errcode='GBW01', message='no break is open'; end if;
            new.break_starts := array_append(new.break_starts,previous.break_started_at);
            new.break_ends := array_append(new.break_ends,new.occurred_at);
            new.break_started_at := null; new.reason := 'Break end';
        else
            new.ends_at := new.occurred_at; new.status := 'proposed'; new.reason := 'Recorded clock-out';
            if previous.break_started_at is not null then
                new.break_starts := array_append(new.break_starts,previous.break_started_at);
                new.break_ends := array_append(new.break_ends,new.occurred_at);
                new.break_started_at := null;
            end if;
        end if;
    elsif new.action='correct' then
        if previous.status is null or previous.status='open' then
            raise exception using errcode='GBW01', message='a correction needs a closed time entry';
        end if;
        if new.occurred_at is not null then raise exception using errcode='23514', message='a correction has a server event time'; end if;
        new.occurred_at := now(); new.status := 'proposed'; new.break_started_at := null;
    elsif new.action in ('approve','decline') then
        if previous.status is distinct from 'proposed' then
            raise exception using errcode='GBW01', message='a decision needs the latest proposed time revision';
        end if;
        if new.occurred_at is not null then raise exception using errcode='23514', message='a decision has a server event time'; end if;
        new.occurred_at := now(); new.starts_at := previous.starts_at; new.ends_at := previous.ends_at;
        new.break_starts := previous.break_starts; new.break_ends := previous.break_ends; new.break_started_at := null;
        if new.action='approve' then
            new.status := 'approved'; new.reason := previous.reason;
            new.self_approved := new.created_by=entry.user_id;
        else new.status := 'declined'; end if;
    else raise exception using errcode='23514', message='unknown time action';
    end if;
    -- Validate exact closed breaks, including NULLs/dimensions and supported dates.
    if new.break_starts is null or new.break_ends is null then
        raise exception using errcode='23514', message='time breaks must be explicit arrays';
    end if;
    for pos in select generate_subscripts(new.break_starts,1) loop
        if new.break_starts[pos] is null or new.break_ends[pos] is null
            or not isfinite(new.break_starts[pos]) or not isfinite(new.break_ends[pos])
            or new.break_starts[pos]<new.starts_at or new.break_ends[pos]<=new.break_starts[pos]
            or extract(epoch from new.break_ends[pos])>=253370764800
            or (new.ends_at is not null and new.break_ends[pos]>new.ends_at)
            or (pos>1 and new.break_starts[pos]<new.break_ends[pos-1]) then
            raise exception using errcode='23514', message='breaks must be ordered nonoverlapping intervals inside worked time';
        end if;
    end loop;
    if new.break_started_at is not null and cardinality(new.break_ends)>0
        and new.break_started_at<new.break_ends[cardinality(new.break_ends)] then
        raise exception using errcode='23514', message='an open break follows every completed break';
    end if;
    return new;
end;
$$;

create function gba.guard_time_entry_state() returns trigger language plpgsql as $$
declare entry gba.time_entries; latest gba.time_entry_revisions; approved gba.time_entry_revisions;
begin
    if tg_op='DELETE' then raise exception using errcode='23514', message='time state is derived and kept'; end if;
    select * into entry from gba.time_entries where tenant_id=new.tenant_id and id=new.entry_id;
    select * into latest from gba.time_entry_revisions where tenant_id=new.tenant_id and entry_id=new.entry_id order by revision desc limit 1;
    select * into approved from gba.time_entry_revisions where tenant_id=new.tenant_id and entry_id=new.entry_id and action='approve' order by revision desc limit 1;
    if entry.id is null or latest.creation_xid is distinct from pg_current_xact_id()
        or (new.user_id,new.location_id,new.last_revision,new.is_open,new.approved_revision,new.starts_at,new.ends_at)
           is distinct from (entry.user_id,entry.location_id,latest.revision,latest.status='open',approved.revision,approved.starts_at,approved.ends_at) then
        raise exception using errcode='23514', message='time state requires its exact immutable source';
    end if;
    if tg_op='INSERT' and latest.revision<>1 then
        raise exception using errcode='23514', message='time state is initialized with the first revision';
    elsif tg_op='UPDATE' and (
        (new.tenant_id,new.entry_id,new.user_id,new.location_id) is distinct from (old.tenant_id,old.entry_id,old.user_id,old.location_id)
        or new.last_revision<>old.last_revision+1) then
        raise exception using errcode='23514', message='time state advances exactly one immutable revision';
    end if;
    return new;
end;
$$;
create function gba.apply_time_entry_revision() returns trigger language plpgsql as $$
declare entry gba.time_entries; approved gba.time_entry_revisions; affected bigint;
begin
    select * into entry from gba.time_entries where tenant_id=new.tenant_id and id=new.entry_id;
    select * into approved from gba.time_entry_revisions where tenant_id=new.tenant_id
        and entry_id=new.entry_id and action='approve' order by revision desc limit 1;
    update gba.time_entry_state set last_revision=new.revision,is_open=new.status='open',
        approved_revision=approved.revision,starts_at=approved.starts_at,ends_at=approved.ends_at
     where tenant_id=new.tenant_id and entry_id=new.entry_id;
    get diagnostics affected=row_count;
    if affected=0 then
        insert into gba.time_entry_state (tenant_id,entry_id,user_id,location_id,last_revision,is_open,approved_revision,starts_at,ends_at)
        values (new.tenant_id,new.entry_id,entry.user_id,entry.location_id,new.revision,new.status='open',approved.revision,approved.starts_at,approved.ends_at);
    end if;
    return null;
end;
$$;
create function gba.check_time_entry_complete() returns trigger language plpgsql as $$
declare identifier uuid; entry gba.time_entries; latest gba.time_entry_revisions; approved gba.time_entry_revisions;
begin
    if tg_table_name='time_entries' then identifier := new.id; else identifier := new.entry_id; end if;
    select * into entry from gba.time_entries where tenant_id=new.tenant_id and id=identifier;
    select * into latest from gba.time_entry_revisions where tenant_id=new.tenant_id and entry_id=identifier order by revision desc limit 1;
    select * into approved from gba.time_entry_revisions where tenant_id=new.tenant_id and entry_id=identifier and action='approve' order by revision desc limit 1;
    if not exists (select 1 from gba.time_entry_revisions where tenant_id=new.tenant_id and entry_id=identifier
            and revision=1 and action='clock_in' and starts_at=entry.starts_at and creation_xid=entry.creation_xid)
        or not exists (select 1 from gba.time_entry_state s where s.tenant_id=new.tenant_id and s.entry_id=identifier
            and (s.user_id,s.location_id,s.last_revision,s.is_open,s.approved_revision,s.starts_at,s.ends_at)
             is not distinct from (entry.user_id,entry.location_id,latest.revision,latest.status='open',approved.revision,approved.starts_at,approved.ends_at)) then
        raise exception using errcode='23514', message='a time entry requires its complete immutable history and exact derived state';
    end if;
    return null;
end;
$$;

create trigger time_entries_guard before insert on gba.time_entries
    for each row execute function gba.guard_time_entry();
create trigger time_entries_initialize after insert on gba.time_entries
    for each row execute function gba.initialize_time_entry();
create constraint trigger time_entries_complete after insert on gba.time_entries
    deferrable initially deferred for each row execute function gba.check_time_entry_complete();
create trigger time_entry_revisions_guard before insert on gba.time_entry_revisions
    for each row execute function gba.guard_time_entry_revision();
create trigger time_entry_revisions_apply after insert on gba.time_entry_revisions
    for each row execute function gba.apply_time_entry_revision();
create constraint trigger time_entry_revisions_complete after insert on gba.time_entry_revisions
    deferrable initially deferred for each row execute function gba.check_time_entry_complete();
create trigger time_entry_state_guard before insert or update or delete on gba.time_entry_state
    for each row execute function gba.guard_time_entry_state();

alter table gba.time_entries enable row level security;
alter table gba.time_entries force row level security;
create policy time_entries_tenant_isolation on gba.time_entries
    using (tenant_id=gba.current_tenant_id()) with check (tenant_id=gba.current_tenant_id());
create policy time_entries_location_scope on gba.time_entries as restrictive to gba_runtime
    using (gba.current_location_id() is null or location_id=gba.current_location_id())
    with check (gba.current_location_id() is null or location_id=gba.current_location_id());
grant select on gba.time_entries to gba_runtime;
grant insert (tenant_id,id,profile_id,shift_id,shift_revision,starts_at,created_by) on gba.time_entries to gba_runtime;
grant update (id) on gba.time_entries to gba_runtime;
create trigger time_entries_immutable before update or delete on gba.time_entries
    for each row execute function gba.reject_counterparty_mutation();
alter table gba.time_entry_revisions enable row level security;
alter table gba.time_entry_revisions force row level security;
create policy time_entry_revisions_tenant_isolation on gba.time_entry_revisions
    using (tenant_id=gba.current_tenant_id()) with check (tenant_id=gba.current_tenant_id());
create policy time_entry_revisions_location_scope on gba.time_entry_revisions as restrictive to gba_runtime
    using (exists (select 1 from gba.time_entries e where e.tenant_id=time_entry_revisions.tenant_id and e.id=time_entry_revisions.entry_id))
    with check (exists (select 1 from gba.time_entries e where e.tenant_id=time_entry_revisions.tenant_id and e.id=time_entry_revisions.entry_id));
grant select on gba.time_entry_revisions to gba_runtime;
grant insert (tenant_id,entry_id,revision,action,occurred_at,starts_at,ends_at,break_starts,break_ends,reason,created_by) on gba.time_entry_revisions to gba_runtime;
create trigger time_entry_revisions_immutable before update or delete on gba.time_entry_revisions
    for each row execute function gba.reject_counterparty_mutation();
alter table gba.time_entry_state enable row level security;
alter table gba.time_entry_state force row level security;
create policy time_entry_state_tenant_isolation on gba.time_entry_state
    using (tenant_id=gba.current_tenant_id()) with check (tenant_id=gba.current_tenant_id());
create policy time_entry_state_location_scope on gba.time_entry_state as restrictive to gba_runtime
    using (gba.current_location_id() is null or location_id=gba.current_location_id())
    with check (gba.current_location_id() is null or location_id=gba.current_location_id());
grant select on gba.time_entry_state to gba_runtime;
grant insert (tenant_id,entry_id,user_id,location_id,last_revision,is_open,approved_revision,starts_at,ends_at) on gba.time_entry_state to gba_runtime;
grant update (last_revision,is_open,approved_revision,starts_at,ends_at) on gba.time_entry_state to gba_runtime;
revoke all on function gba.guard_time_entry() from public;
revoke all on function gba.initialize_time_entry() from public;
revoke all on function gba.guard_time_entry_revision() from public;
revoke all on function gba.guard_time_entry_state() from public;
revoke all on function gba.apply_time_entry_revision() from public;
revoke all on function gba.check_time_entry_complete() from public;
