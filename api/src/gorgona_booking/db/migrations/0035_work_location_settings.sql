-- I4 owner decision (2026-10-11) / ADR-0025: whether employees of a branch may see
-- the published shifts of home-branch colleagues is a versioned branch setting.
-- No row means the default: visible. Forward only. No readiness promotion.
create table gba.work_location_setting_versions (
    tenant_id uuid not null references gba.tenants(id),
    location_id uuid not null,
    revision integer not null constraint work_location_setting_versions_revision_check check (revision > 0),
    colleague_shifts_visible boolean not null,
    created_by uuid not null references gba.users(id),
    created_at timestamptz not null default now(),
    primary key (tenant_id, location_id, revision),
    foreign key (tenant_id, location_id) references gba.locations(tenant_id, id)
);

-- The author is the authenticated owner or manager whose membership covers the
-- branch. Versions of one branch are ordered by one lock; the next is latest plus one.
create function gba.guard_work_location_setting_version() returns trigger language plpgsql as $$
declare latest integer;
begin
    perform 1 from gba.memberships m join gba.users u on u.id=m.user_id
     where m.tenant_id=new.tenant_id and m.user_id=new.created_by and m.status='active' and u.status='active'
       and m.role in ('owner','manager') and (m.location_id is null or m.location_id=new.location_id)
     for share of m;
    if not found or new.created_by is distinct from gba.current_user_id() then
        raise exception using errcode='42501', message='a branch setting needs its authenticated owner or manager';
    end if;
    perform pg_catalog.pg_advisory_xact_lock(pg_catalog.hashtextextended(
        'gba:work-location-setting:'||new.tenant_id::text||':'||new.location_id::text,0));
    select coalesce(max(revision),0) into latest from gba.work_location_setting_versions
     where tenant_id=new.tenant_id and location_id=new.location_id;
    if new.revision <> latest+1 then
        raise exception using errcode='GBW01', message='stale location setting revision';
    end if;
    return new;
end;
$$;
revoke all on function gba.guard_work_location_setting_version() from public;
create trigger work_location_setting_versions_guard before insert on gba.work_location_setting_versions
    for each row execute function gba.guard_work_location_setting_version();

alter table gba.work_location_setting_versions enable row level security;
alter table gba.work_location_setting_versions force row level security;
create policy work_location_setting_versions_tenant_isolation on gba.work_location_setting_versions
    using (tenant_id=gba.current_tenant_id()) with check (tenant_id=gba.current_tenant_id());
create policy work_location_setting_versions_location_scope on gba.work_location_setting_versions as restrictive to gba_runtime
    using (gba.current_location_id() is null or location_id=gba.current_location_id())
    with check (gba.current_location_id() is null or location_id=gba.current_location_id());
grant select on gba.work_location_setting_versions to gba_runtime;
grant insert (tenant_id,location_id,revision,colleague_shifts_visible,created_by) on gba.work_location_setting_versions to gba_runtime;
create trigger work_location_setting_versions_immutable before update or delete on gba.work_location_setting_versions
    for each row execute function gba.reject_counterparty_mutation();
create trigger work_location_setting_versions_require_workforce before insert on gba.work_location_setting_versions
    for each row execute function gba.require_enabled_module('workforce');
