-- R6a (package R, RENT-01): handover and return inspections of a rental booking.
-- docs/plan/PACKAGE_R6A_DESIGN_2026-11-07.md. One handover and one return per booking, of its current unit assignment;
-- the class meter reading, a level, a note and damage marks written with the inspection, each mark optionally citing a
-- PNG or JPEG document version. Insert-only; nothing here changes an assignment, agreement, security or payment.
create table gba.rental_inspections (
    tenant_id uuid not null references gba.tenants(id),
    id uuid not null,
    booking_id uuid not null,
    assignment_id uuid not null,
    kind text not null constraint rental_inspections_kind_check check (kind in ('handover', 'return')),
    meter bigint constraint rental_inspections_meter_range_check
        check (meter is null or meter between 0 and 10000000),
    level smallint constraint rental_inspections_level_check check (level is null or level between 0 and 100),
    note text constraint rental_inspections_note_check
        check (note is null or (length(btrim(note)) between 1 and 1000)),
    inspected_by uuid not null references gba.users(id),
    inspected_at timestamptz not null default now(),
    creation_xid xid8 not null default pg_current_xact_id(),
    primary key (tenant_id, id),
    unique (tenant_id, booking_id, kind),
    foreign key (tenant_id, booking_id) references gba.rental_bookings (tenant_id, id),
    foreign key (tenant_id, assignment_id) references gba.rental_assignments (tenant_id, id)
);
create table gba.rental_inspection_marks (
    tenant_id uuid not null references gba.tenants(id),
    inspection_id uuid not null,
    position smallint not null constraint rental_inspection_marks_position_range_check
        check (position between 1 and 50),
    area text not null constraint rental_inspection_marks_area_check
        check (length(btrim(area)) between 1 and 100 and area !~ '[[:cntrl:]]'),
    severity text not null constraint rental_inspection_marks_severity_check
        check (severity in ('minor', 'major')),
    note text constraint rental_inspection_marks_note_check
        check (note is null or (length(btrim(note)) between 1 and 500)),
    new boolean not null,
    document_id uuid,
    document_revision integer,
    primary key (tenant_id, inspection_id, position),
    foreign key (tenant_id, inspection_id) references gba.rental_inspections (tenant_id, id),
    foreign key (tenant_id, document_id, document_revision)
        references gba.document_versions (tenant_id, document_id, revision),
    constraint rental_inspection_marks_photo_fields_check
        check ((document_id is null) = (document_revision is null))
);

-- An inspection names the current assignment of a booking with an agreement that is not cancelled; a return follows
-- the handover of the same assignment; the meter follows the class and never goes back.
create function gba.guard_rental_inspection() returns trigger language plpgsql as $$
declare
    booking record;
    handover record;
    handover_meter bigint;
begin
    select b.class_id, c.meter_kind into booking from gba.rental_bookings b
      join gba.rental_classes c on c.tenant_id = b.tenant_id and c.id = b.class_id
    where b.tenant_id = new.tenant_id and b.id = new.booking_id;
    perform 1 from gba.rental_classes c
    where c.tenant_id = new.tenant_id and c.id = booking.class_id for update;
    if exists (
        select 1 from gba.rental_booking_cancellations c
        where c.tenant_id = new.tenant_id and c.booking_id = new.booking_id
    ) or not exists (
        select 1 from gba.rental_agreements a
        where a.tenant_id = new.tenant_id and a.booking_id = new.booking_id
    ) then
        raise exception using errcode = 'check_violation',
            constraint = 'rental_inspections_booking_check',
            message = 'an inspection belongs to a booking with an agreement that is not cancelled';
    end if;
    if not exists (
        select 1 from gba.rental_assignments a
        where a.tenant_id = new.tenant_id and a.id = new.assignment_id and a.booking_id = new.booking_id
          and not exists (select 1 from gba.rental_assignment_releases r
              where r.tenant_id = a.tenant_id and r.assignment_id = a.id)
    ) then
        raise exception using errcode = 'check_violation',
            constraint = 'rental_inspections_assignment_check',
            message = 'an inspection names the current assignment of its booking';
    end if;
    if new.kind = 'return' then
        select i.assignment_id, i.meter into handover from gba.rental_inspections i
        where i.tenant_id = new.tenant_id and i.booking_id = new.booking_id and i.kind = 'handover';
        if not found or handover.assignment_id <> new.assignment_id then
            raise exception using errcode = 'check_violation',
                constraint = 'rental_inspections_order_check',
                message = 'a return follows the handover of the same assignment';
        end if;
        handover_meter := handover.meter;
    end if;
    if (booking.meter_kind = 'none') <> (new.meter is null)
        or new.meter < handover_meter then
        raise exception using errcode = 'check_violation',
            constraint = 'rental_inspections_meter_check',
            message = 'a class with a meter records a reading that never goes back, a class without one none';
    end if;
    return new;
end;
$$;
revoke all on function gba.guard_rental_inspection() from public;
create trigger rental_inspections_guard
    before insert on gba.rental_inspections
    for each row execute function gba.guard_rental_inspection();

-- Marks are written with their inspection, numbered 1, 2, 3; a handover mark is never new; a photo is a PNG or JPEG.
create function gba.guard_rental_inspection_mark() returns trigger language plpgsql as $$
declare
    inspection record;
begin
    select i.kind, i.creation_xid into inspection from gba.rental_inspections i
    where i.tenant_id = new.tenant_id and i.id = new.inspection_id;
    if inspection.creation_xid <> pg_current_xact_id() or new.position <> 1 + (
        select count(*) from gba.rental_inspection_marks m
        where m.tenant_id = new.tenant_id and m.inspection_id = new.inspection_id
    ) then
        raise exception using errcode = 'check_violation',
            constraint = 'rental_inspection_marks_written_check',
            message = 'marks are written with their inspection, numbered in order';
    end if;
    if inspection.kind = 'handover' and new.new then
        raise exception using errcode = 'check_violation',
            constraint = 'rental_inspection_marks_new_check',
            message = 'a handover mark is never new';
    end if;
    if new.document_id is not null and not exists (
        select 1 from gba.document_versions v
          join gba.document_files f on f.tenant_id = v.tenant_id and f.id = v.file_id
        where v.tenant_id = new.tenant_id and v.document_id = new.document_id
          and v.revision = new.document_revision and f.media_type in ('image/png', 'image/jpeg')
    ) then
        raise exception using errcode = 'check_violation',
            constraint = 'rental_inspection_marks_photo_check',
            message = 'a photo is a document version with a PNG or JPEG file';
    end if;
    return new;
end;
$$;
revoke all on function gba.guard_rental_inspection_mark() from public;
create trigger rental_inspection_marks_guard
    before insert on gba.rental_inspection_marks
    for each row execute function gba.guard_rental_inspection_mark();

-- Writes need the rental module (ADR-0019 gate).
create trigger rental_inspections_module_gate
    before insert on gba.rental_inspections
    for each row execute function gba.require_enabled_module('rental');
create trigger rental_inspection_marks_module_gate
    before insert on gba.rental_inspection_marks
    for each row execute function gba.require_enabled_module('rental');

alter table gba.rental_inspections enable row level security;
alter table gba.rental_inspections force row level security;
create policy rental_inspections_tenant_isolation on gba.rental_inspections
    using (tenant_id = gba.current_tenant_id())
    with check (tenant_id = gba.current_tenant_id());
alter table gba.rental_inspection_marks enable row level security;
alter table gba.rental_inspection_marks force row level security;
create policy rental_inspection_marks_tenant_isolation on gba.rental_inspection_marks
    using (tenant_id = gba.current_tenant_id())
    with check (tenant_id = gba.current_tenant_id());
grant select, insert on gba.rental_inspections, gba.rental_inspection_marks to gba_runtime;

-- Rental branch scope:
create policy rental_inspections_location_scope on gba.rental_inspections
    as restrictive to gba_runtime
    using (gba.current_location_id() is null or exists (
        select 1 from gba.rental_bookings b
        where b.tenant_id = rental_inspections.tenant_id and b.id = rental_inspections.booking_id))
    with check (gba.current_location_id() is null or exists (
        select 1 from gba.rental_bookings b
        where b.tenant_id = rental_inspections.tenant_id and b.id = rental_inspections.booking_id));
create policy rental_inspection_marks_location_scope on gba.rental_inspection_marks
    as restrictive to gba_runtime
    using (gba.current_location_id() is null or exists (
        select 1 from gba.rental_inspections i
        where i.tenant_id = rental_inspection_marks.tenant_id and i.id = rental_inspection_marks.inspection_id))
    with check (gba.current_location_id() is null or exists (
        select 1 from gba.rental_inspections i
        where i.tenant_id = rental_inspection_marks.tenant_id and i.id = rental_inspection_marks.inspection_id));
