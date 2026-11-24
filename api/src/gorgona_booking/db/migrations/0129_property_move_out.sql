-- PROPERTY-01 6a: one condition report and its photos on the recorded move-out.
-- docs/plan/PACKAGE_PROPERTY01_MOVE_OUT_DESIGN_2026-11-20.md. Invoker rights only.
create table gba.property_move_outs (
    tenant_id uuid not null,
    lease_id uuid not null,
    term_revision integer not null check (term_revision > 0),
    moved_out_on date not null,
    condition_summary text not null check (condition_summary in ('normal_wear', 'damage_noted')),
    note text check (
        note is null
        or (length(btrim(note)) between 1 and 2000 and note !~ E'[\\x01-\\x08\\x0b-\\x1f\\x7f]')
    ),
    report_id uuid not null,
    report_revision integer not null,
    photo_count smallint not null check (photo_count between 1 and 50),
    recorded_by uuid not null references gba.users (id),
    recorded_at timestamptz not null default clock_timestamp(),
    creation_xid xid8 not null default pg_current_xact_id(),
    primary key (tenant_id, lease_id),
    foreign key (tenant_id, lease_id) references gba.property_move_ins (tenant_id, lease_id),
    foreign key (tenant_id, report_id, report_revision)
        references gba.document_versions (tenant_id, document_id, revision)
);

create table gba.property_move_out_photos (
    tenant_id uuid not null,
    lease_id uuid not null,
    position smallint not null check (position between 1 and 50),
    document_id uuid not null,
    document_revision integer not null,
    primary key (tenant_id, lease_id, position),
    constraint property_move_out_photos_unique
        unique (tenant_id, lease_id, document_id, document_revision),
    foreign key (tenant_id, lease_id) references gba.property_move_outs (tenant_id, lease_id),
    foreign key (tenant_id, document_id, document_revision)
        references gba.document_versions (tenant_id, document_id, revision)
);

create function gba.validate_property_move_out() returns trigger language plpgsql as $$
declare
    lease_term record;
begin
    if pg_catalog.current_setting('transaction_isolation') <> 'read committed' then
        raise exception using errcode = 'serialization_failure',
            message = 'move-out requires a read committed transaction';
    end if;
    perform pg_catalog.pg_advisory_xact_lock(
        pg_catalog.hashtextextended('gba:counterparties:' || new.tenant_id::text, 0));
    select l.term_revision, l.starts_on, coalesce(l.occupied_through, l.ends_on) as ends_on,
           (pg_catalog.now() at time zone branch.timezone)::date as local_day,
           m.moved_in_on, m.report_id as mi_report_id, m.report_revision as mi_report_revision
    into lease_term
    from gba.property_leases l
    join gba.property_objects o on o.tenant_id = l.tenant_id and o.id = l.object_id
    join gba.locations branch on branch.tenant_id = o.tenant_id and branch.id = o.location_id
    left join gba.property_move_ins m on m.tenant_id = l.tenant_id and m.lease_id = l.id
    where l.tenant_id = new.tenant_id and l.id = new.lease_id;
    if not found then
        raise exception using errcode = 'check_violation', constraint = 'property_move_out_lease',
            message = 'a move-out belongs to a recorded lease';
    end if;
    if lease_term.moved_in_on is null then
        raise exception using errcode = 'check_violation',
            constraint = 'property_move_out_requires_move_in',
            message = 'a move-out requires a recorded move-in first';
    end if;
    if new.term_revision <> lease_term.term_revision then
        raise exception using errcode = 'check_violation', constraint = 'property_move_out_revision',
            message = 'a move-out uses the current term revision';
    end if;
    if new.moved_out_on < lease_term.moved_in_on
       or new.moved_out_on > lease_term.ends_on
       or new.moved_out_on > lease_term.local_day then
        raise exception using errcode = 'check_violation', constraint = 'property_move_out_day',
            message = 'a move-out records a day from move-in through the current term and today';
    end if;
    if (new.report_id, new.report_revision) = (lease_term.mi_report_id, lease_term.mi_report_revision) then
        raise exception using errcode = 'check_violation',
            constraint = 'property_move_out_report_distinct',
            message = 'a move-out report must be distinct from the move-in condition report';
    end if;
    if not exists (
        select 1 from gba.document_versions d
        where d.tenant_id = new.tenant_id and d.document_id = new.report_id
          and d.revision = new.report_revision and d.category = 'report'
          and not d.archived and d.file_id is not null
    ) then
        raise exception using errcode = 'check_violation', constraint = 'property_move_out_report',
            message = 'a move-out requires a stored condition report';
    end if;
    return new;
end;
$$;
revoke all on function gba.validate_property_move_out() from public;

-- Agreement lock precedes configuration lock, matching 0115-0117.
create trigger property_move_outs_agreement_period before insert on gba.property_move_outs
    for each row execute function gba.validate_property_move_out();
create trigger property_move_outs_require_module before insert on gba.property_move_outs
    for each row execute function gba.require_enabled_module('property');

create function gba.validate_property_move_out_photo() returns trigger language plpgsql as $$
begin
    if not exists (
        select 1 from gba.property_move_outs m
        where m.tenant_id = new.tenant_id and m.lease_id = new.lease_id
          and m.creation_xid = pg_current_xact_id() and new.position <= m.photo_count
    ) then
        raise exception using errcode = 'check_violation',
            constraint = 'property_move_out_photo_parent',
            message = 'photos are written with their move-out report';
    end if;
    if not exists (
        select 1 from gba.document_versions d
        join gba.document_files f on f.tenant_id = d.tenant_id and f.id = d.file_id
        where d.tenant_id = new.tenant_id and d.document_id = new.document_id
          and d.revision = new.document_revision and not d.archived
          and f.media_type in ('image/png', 'image/jpeg')
    ) then
        raise exception using errcode = 'check_violation', constraint = 'property_move_out_photo',
            message = 'a move-out photo refers to a stored PNG or JPEG document';
    end if;
    return new;
end;
$$;
revoke all on function gba.validate_property_move_out_photo() from public;
create trigger property_move_out_photos_validate before insert on gba.property_move_out_photos
    for each row execute function gba.validate_property_move_out_photo();

create function gba.complete_property_move_out_photos() returns trigger language plpgsql as $$
begin
    if (
        select count(*) from gba.property_move_out_photos p
        where p.tenant_id = new.tenant_id and p.lease_id = new.lease_id
    ) <> new.photo_count then
        raise exception using errcode = 'check_violation',
            constraint = 'property_move_out_photos_complete',
            message = 'a move-out keeps all of its photos';
    end if;
    return null;
end;
$$;
revoke all on function gba.complete_property_move_out_photos() from public;
create constraint trigger property_move_outs_photos_complete after insert on gba.property_move_outs
    deferrable initially deferred for each row execute function gba.complete_property_move_out_photos();

create trigger property_move_outs_immutable before update or delete on gba.property_move_outs
    for each row execute function gba.reject_agreement_mutation();
create trigger property_move_out_photos_immutable before update or delete on gba.property_move_out_photos
    for each row execute function gba.reject_agreement_mutation();

-- Keep lease term guard synchronized with move-out records.
create or replace function gba.guard_property_lease_term() returns trigger language plpgsql as $$
begin
    if tg_op = 'INSERT' then
        if new.term_revision <> 1 or new.occupied_through is not null then
            raise exception using errcode = 'check_violation',
                message = 'a lease starts with the registered term';
        end if;
        return new;
    end if;
    if tg_op = 'DELETE' or
       (new.tenant_id, new.id, new.object_id, new.agreement_id, new.agreement_revision,
        new.starts_on, new.ends_on, new.recorded_by, new.recorded_at)
        is distinct from
       (old.tenant_id, old.id, old.object_id, old.agreement_id, old.agreement_revision,
        old.starts_on, old.ends_on, old.recorded_by, old.recorded_at) then
        raise exception using errcode = 'check_violation',
            message = 'original lease registrations are kept unchanged';
    end if;
    if new.term_revision::bigint <> old.term_revision::bigint + 1 or not exists (
        select 1 from gba.property_lease_term_events e
        where e.tenant_id = new.tenant_id and e.lease_id = new.id
          and e.revision = new.term_revision and e.occupied_through = new.occupied_through
          and e.creation_xid = pg_current_xact_id()
    ) then
        raise exception using errcode = 'check_violation',
            message = 'the current term follows its next recorded event';
    end if;
    if exists (
        select 1 from gba.property_move_ins m
        where m.tenant_id = new.tenant_id and m.lease_id = new.id
          and m.moved_in_on > new.occupied_through
    ) then
        raise exception using errcode = 'check_violation',
            constraint = 'property_lease_term_move_in',
            message = 'the last day cannot precede a recorded move-in';
    end if;
    if exists (
        select 1 from gba.property_move_outs mo
        where mo.tenant_id = new.tenant_id and mo.lease_id = new.id
          and (mo.moved_out_on > new.occupied_through
               or exists (
                   select 1 from gba.property_lease_term_events ev
                   where ev.tenant_id = new.tenant_id and ev.lease_id = new.id
                     and ev.revision = new.term_revision and ev.action = 'extend'
               ))
    ) then
        raise exception using errcode = 'check_violation',
            constraint = 'property_lease_term_move_out',
            message = 'a recorded move-out cannot be extended or preceded by release';
    end if;
    return new;
end;
$$;

alter table gba.property_move_outs enable row level security;
alter table gba.property_move_outs force row level security;
alter table gba.property_move_out_photos enable row level security;
alter table gba.property_move_out_photos force row level security;
create policy property_move_outs_tenant_isolation on gba.property_move_outs
    using (tenant_id = gba.current_tenant_id()) with check (tenant_id = gba.current_tenant_id());
create policy property_move_out_photos_tenant_isolation on gba.property_move_out_photos
    using (tenant_id = gba.current_tenant_id()) with check (tenant_id = gba.current_tenant_id());
grant select on gba.property_move_outs, gba.property_move_out_photos to gba_runtime;
grant insert (tenant_id, lease_id, term_revision, moved_out_on, condition_summary, note,
              report_id, report_revision, photo_count, recorded_by)
    on gba.property_move_outs to gba_runtime;
grant insert on gba.property_move_out_photos to gba_runtime;

-- Property move-out company scope:
create policy property_move_outs_unrestricted_scope on gba.property_move_outs
    as restrictive to gba_runtime
    using (gba.current_location_id() is null) with check (gba.current_location_id() is null);
create policy property_move_out_photos_unrestricted_scope on gba.property_move_out_photos
    as restrictive to gba_runtime
    using (gba.current_location_id() is null) with check (gba.current_location_id() is null);
