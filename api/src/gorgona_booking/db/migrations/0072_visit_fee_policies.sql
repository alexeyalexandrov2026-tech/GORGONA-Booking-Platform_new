-- L9a (package L, BEAUTY-01): the published fee policy for late cancellations and no-shows, and
-- the no-show fact. Design docs/plan/PACKAGE_L9_DESIGN_2026-10-23.md decisions 76-78. A policy is
-- kept in insert-only versions; a visit uses the version in force when it was booked. A no-show is
-- a permanent fact of a started confirmed visit that was not completed.
create table gba.visit_fee_policies (
    tenant_id uuid not null references gba.tenants(id),
    version integer not null constraint visit_fee_policies_version_check check (version > 0),
    published_at timestamptz not null default now(),
    published_by uuid not null references gba.users(id),
    free_cancellation_minutes integer not null
        constraint visit_fee_policies_free_minutes_check
        check (free_cancellation_minutes between 0 and 525600),
    -- Each fee is a percentage of the visit's priced total (basis points) or a fixed amount in
    -- hundredths of the main currency unit, like catalog prices; or none.
    late_fee_bp integer constraint visit_fee_policies_late_bp_check
        check (late_fee_bp between 0 and 10000),
    late_fee_cents bigint constraint visit_fee_policies_late_cents_check
        check (late_fee_cents between 0 and 999999999999),
    no_show_fee_bp integer constraint visit_fee_policies_no_show_bp_check
        check (no_show_fee_bp between 0 and 10000),
    no_show_fee_cents bigint constraint visit_fee_policies_no_show_cents_check
        check (no_show_fee_cents between 0 and 999999999999),
    primary key (tenant_id, version),
    constraint visit_fee_policies_late_kind_check
        check (late_fee_bp is null or late_fee_cents is null),
    constraint visit_fee_policies_no_show_kind_check
        check (no_show_fee_bp is null or no_show_fee_cents is null)
);
create table gba.visit_no_shows (
    tenant_id uuid not null references gba.tenants(id),
    booking_id uuid not null,
    location_id uuid not null,
    -- The version in force when the visit was booked; none when no policy was published then.
    policy_version integer,
    recorded_at timestamptz not null default now(),
    recorded_by uuid not null references gba.users(id),
    primary key (tenant_id, booking_id),
    foreign key (tenant_id, booking_id) references gba.bookings (tenant_id, id),
    foreign key (tenant_id, location_id) references gba.locations (tenant_id, id),
    foreign key (tenant_id, policy_version) references gba.visit_fee_policies (tenant_id, version)
);

-- A version follows the last one and is published now; it never changes.
create function gba.guard_visit_fee_policy() returns trigger language plpgsql as $$
begin
    if new.version <> coalesce((
           select max(p.version) from gba.visit_fee_policies p
           where p.tenant_id = new.tenant_id), 0) + 1
       or new.published_at <> pg_catalog.now() then
        raise exception using errcode = 'check_violation',
            constraint = 'visit_fee_policies_next_version_check',
            message = 'a fee policy version follows the last one';
    end if;
    return new;
end;
$$;
revoke all on function gba.guard_visit_fee_policy() from public;
create trigger visit_fee_policies_guard
    before insert on gba.visit_fee_policies
    for each row execute function gba.guard_visit_fee_policy();

-- A no-show follows a started confirmed booking of its own branch that was not completed, and
-- names the version in force when it was booked.
create function gba.guard_visit_no_show() returns trigger language plpgsql as $$
begin
    if not exists (
        select 1 from gba.bookings b
        where b.tenant_id = new.tenant_id and b.id = new.booking_id
          and b.status = 'CONFIRMED' and b.starts_at <= pg_catalog.now()
          and b.location_id = new.location_id
          and new.policy_version is not distinct from (
              select max(p.version) from gba.visit_fee_policies p
              where p.tenant_id = b.tenant_id and p.published_at <= b.created_at)
    ) or exists (
        select 1 from gba.visit_completions c
        where c.tenant_id = new.tenant_id and c.booking_id = new.booking_id
    ) or new.recorded_at <> pg_catalog.now() then
        raise exception using errcode = 'check_violation',
            constraint = 'visit_no_shows_started_check',
            message = 'only a started confirmed visit that was not completed is a no-show';
    end if;
    return new;
end;
$$;
revoke all on function gba.guard_visit_no_show() from public;
create trigger visit_no_shows_guard
    before insert on gba.visit_no_shows
    for each row execute function gba.guard_visit_no_show();

-- A no-show visit is never completed.
create function gba.guard_completion_not_no_show() returns trigger language plpgsql as $$
begin
    if exists (
        select 1 from gba.visit_no_shows n
        where n.tenant_id = new.tenant_id and n.booking_id = new.booking_id
    ) then
        raise exception using errcode = 'check_violation',
            constraint = 'visit_completions_not_no_show_check',
            message = 'a no-show visit is not completed';
    end if;
    return new;
end;
$$;
revoke all on function gba.guard_completion_not_no_show() from public;
create trigger visit_completions_not_no_show_guard
    before insert on gba.visit_completions
    for each row execute function gba.guard_completion_not_no_show();

alter table gba.visit_fee_policies enable row level security;
alter table gba.visit_fee_policies force row level security;
alter table gba.visit_no_shows enable row level security;
alter table gba.visit_no_shows force row level security;
create policy visit_fee_policies_tenant_isolation on gba.visit_fee_policies
    using (tenant_id = gba.current_tenant_id())
    with check (tenant_id = gba.current_tenant_id());
create policy visit_no_shows_tenant_isolation on gba.visit_no_shows
    using (tenant_id = gba.current_tenant_id())
    with check (tenant_id = gba.current_tenant_id());
grant select, insert on gba.visit_fee_policies, gba.visit_no_shows to gba_runtime;

-- Visit branch scope:
create policy visit_no_shows_location_scope on gba.visit_no_shows
    as restrictive to gba_runtime
    using (gba.current_location_id() is null or location_id = gba.current_location_id())
    with check (gba.current_location_id() is null or location_id = gba.current_location_id());
