-- K6a / ADR-0027, owner decisions of 2026-10-21 (K6 design, all defaults). Forward only; no
-- existing row is changed.
--
-- A decision that fails for one attested event is recorded under the lease that failed. After
-- five failures in a round the event is parked: no lease may claim it until a finance user
-- releases it with a note, which starts the next round. Nothing here decides, books or edits facts.

create table gba.provider_event_failures (
    tenant_id uuid not null,
    event_id uuid not null,
    generation bigint not null,
    holder uuid not null,
    round integer not null,
    error_class text not null check (error_class ~ '^[A-Za-z][A-Za-z0-9_]{0,63}$'),
    failed_at timestamptz not null default now(),
    primary key (tenant_id,event_id,generation),
    foreign key (tenant_id,event_id) references gba.provider_event_leases (tenant_id,event_id)
);

create table gba.provider_event_releases (
    tenant_id uuid not null,
    event_id uuid not null,
    round integer not null,
    note text not null check (length(btrim(note)) between 1 and 500 and note !~ '[[:cntrl:]]'),
    released_by uuid not null,
    released_at timestamptz not null default now(),
    primary key (tenant_id,event_id,round),
    foreign key (tenant_id,event_id) references gba.provider_event_leases (tenant_id,event_id),
    foreign key (released_by) references gba.users (id)
);

-- Only the holder of the event's unexpired lease records its failure, at most five per round.
create function gba.record_provider_event_failure() returns trigger
language plpgsql set search_path=pg_catalog as $$
declare
    lease gba.provider_event_leases;
begin
    if new.tenant_id is distinct from gba.current_tenant_id() or gba.current_location_id() is not null then
        raise exception using errcode='check_violation', message='provider event failure requires company scope';
    end if;
    select l.* into lease from gba.provider_event_leases l
        where l.tenant_id=new.tenant_id and l.event_id=new.event_id for update;
    if lease.event_id is null or lease.holder is distinct from new.holder
       or lease.generation is distinct from new.generation or lease.expires_at<=now()
       or exists (select 1 from gba.provider_event_decisions d
           where d.tenant_id=new.tenant_id and d.event_id=new.event_id) then
        raise exception using errcode='check_violation', message='provider event lease refused';
    end if;
    new.round := (select count(*) from gba.provider_event_releases r
        where r.tenant_id=new.tenant_id and r.event_id=new.event_id);
    if (select count(*) from gba.provider_event_failures f
        where f.tenant_id=new.tenant_id and f.event_id=new.event_id and f.round=new.round)>=5 then
        raise exception using errcode='check_violation', message='provider event is parked';
    end if;
    new.failed_at := now();
    return new;
end;
$$;
revoke all on function gba.record_provider_event_failure() from public;

-- A release starts the next round of a parked, undecided event; it decides and books nothing.
create function gba.check_provider_event_release() returns trigger
language plpgsql set search_path=pg_catalog as $$
begin
    if new.tenant_id is distinct from gba.current_tenant_id() or gba.current_location_id() is not null then
        raise exception using errcode='check_violation', message='provider event release requires company scope';
    end if;
    new.round := 1+(select count(*) from gba.provider_event_releases r
        where r.tenant_id=new.tenant_id and r.event_id=new.event_id);
    if exists (select 1 from gba.provider_event_decisions d
           where d.tenant_id=new.tenant_id and d.event_id=new.event_id)
       or (select count(*) from gba.provider_event_failures f where f.tenant_id=new.tenant_id
           and f.event_id=new.event_id and f.round=new.round-1)<5 then
        raise exception using errcode='check_violation', message='only a parked provider event takes a release';
    end if;
    new.released_at := now();
    return new;
end;
$$;
revoke all on function gba.check_provider_event_release() from public;

-- 0050's lease guard, now also refusing any claim of a parked event.
create or replace function gba.guard_provider_event_lease() returns trigger
language plpgsql set search_path=pg_catalog as $$
begin
    if tg_op='DELETE' then
        raise exception using errcode='check_violation', message='provider event leases are kept';
    end if;
    if new.tenant_id is distinct from gba.current_tenant_id() or gba.current_location_id() is not null then
        raise exception using errcode='check_violation', message='provider event lease requires company scope';
    end if;
    if new.expires_at<=now() or new.expires_at>now()+interval '10 minutes'
       or not exists (select 1 from gba.provider_event_attestations a
           where a.tenant_id=new.tenant_id and a.event_id=new.event_id)
       or exists (select 1 from gba.provider_event_decisions d
           where d.tenant_id=new.tenant_id and d.event_id=new.event_id)
       or (tg_op='INSERT' and new.generation<>1)
       or (tg_op='UPDATE' and ((new.tenant_id,new.event_id) is distinct from (old.tenant_id,old.event_id)
           or old.expires_at>=now() or new.generation<>old.generation+1)) then
        raise exception using errcode='check_violation', message='provider event lease refused';
    end if;
    if (select count(*) from gba.provider_event_failures f
        where f.tenant_id=new.tenant_id and f.event_id=new.event_id
          and f.round=(select count(*) from gba.provider_event_releases r
              where r.tenant_id=new.tenant_id and r.event_id=new.event_id))>=5 then
        raise exception using errcode='check_violation', message='provider event is parked';
    end if;
    new.claimed_at := now();
    return new;
end;
$$;

alter table gba.provider_event_failures enable row level security;
alter table gba.provider_event_failures force row level security;
alter table gba.provider_event_releases enable row level security;
alter table gba.provider_event_releases force row level security;
create policy provider_event_failures_tenant on gba.provider_event_failures
    using (tenant_id=gba.current_tenant_id()) with check (tenant_id=gba.current_tenant_id());
create policy provider_event_failures_company on gba.provider_event_failures as restrictive
    using (gba.current_location_id() is null) with check (gba.current_location_id() is null);
create policy provider_event_releases_tenant on gba.provider_event_releases
    using (tenant_id=gba.current_tenant_id()) with check (tenant_id=gba.current_tenant_id());
create policy provider_event_releases_company on gba.provider_event_releases as restrictive
    using (gba.current_location_id() is null) with check (gba.current_location_id() is null);
-- Discovery without a company context skips waiting and parked events (worker group only).
create policy provider_event_failures_discover on gba.provider_event_failures
    for select to gba_receipt_worker using (true);
create policy provider_event_releases_discover on gba.provider_event_releases
    for select to gba_receipt_worker using (true);

revoke all on gba.provider_event_failures,gba.provider_event_releases from public;
grant select on gba.provider_event_failures,gba.provider_event_releases
    to gba_receipt_worker,gba_runtime;
grant insert (tenant_id,event_id,generation,holder,error_class) on gba.provider_event_failures
    to gba_receipt_worker;
grant insert (tenant_id,event_id,note,released_by) on gba.provider_event_releases to gba_runtime;

create trigger provider_event_failures_check before insert on gba.provider_event_failures
    for each row execute function gba.record_provider_event_failure();
create trigger provider_event_failures_immutable before update or delete on gba.provider_event_failures
    for each row execute function gba.reject_ledger_mutation();
create trigger provider_event_releases_check before insert on gba.provider_event_releases
    for each row execute function gba.check_provider_event_release();
create trigger provider_event_releases_immutable before update or delete on gba.provider_event_releases
    for each row execute function gba.reject_ledger_mutation();
create trigger provider_event_failures_no_truncate before truncate on gba.provider_event_failures
    for each statement execute function gba.reject_provider_receipt_truncate();
create trigger provider_event_releases_no_truncate before truncate on gba.provider_event_releases
    for each statement execute function gba.reject_provider_receipt_truncate();
