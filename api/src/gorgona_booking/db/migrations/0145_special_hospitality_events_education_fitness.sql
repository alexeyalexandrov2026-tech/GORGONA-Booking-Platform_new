-- 0145_special_hospitality_events_education_fitness.sql
-- ADR-0042 / SPECIAL-01: typed domain workflows for education cohorts & fitness memberships,
-- hospitality room inventory & stays with housekeeping states, and events & ticket capacity.
-- Invoker rights only.

create table gba.special_programs (
    id uuid not null,
    tenant_id uuid not null,
    location_id uuid not null,
    code text not null,
    title text not null,
    program_kind text not null,
    capacity integer not null,
    enrolled_count integer not null default 0,
    included_sessions integer not null default 1,
    price_minor bigint not null default 0,
    currency text not null references gba.currencies(code),
    is_active boolean not null default true,
    revision integer not null default 1,
    recorded_by uuid not null references gba.users(id),
    recorded_at timestamptz not null default now(),
    primary key (tenant_id, id),
    constraint special_programs_location_fk
        foreign key (tenant_id, location_id)
        references gba.locations(tenant_id, id) on delete restrict,
    constraint special_programs_loc_id_unique
        unique (tenant_id, location_id, id),
    constraint special_programs_code_unique
        unique (tenant_id, location_id, code),
    constraint special_programs_checks
        check (
            btrim(code) = code and char_length(code) between 2 and 64
            and code ~ '^[A-Z0-9][A-Z0-9_-]*$'
            and btrim(title) = title and char_length(title) between 1 and 200
            and program_kind in ('education_cohort', 'fitness_membership', 'club_pass')
            and capacity between 1 and 100000
            and enrolled_count between 0 and capacity
            and included_sessions between 1 and 10000
            and price_minor between 0 and 999999999999999
            and revision >= 1
        )
);

create table gba.special_enrollments (
    id uuid not null,
    tenant_id uuid not null,
    location_id uuid not null,
    program_id uuid not null,
    participant_counterparty_id uuid not null,
    status text not null default 'active',
    sessions_used integer not null default 0,
    sessions_total integer not null,
    result_grade text null,
    revision integer not null default 1,
    recorded_by uuid not null references gba.users(id),
    recorded_at timestamptz not null default now(),
    primary key (tenant_id, id),
    constraint special_enrollments_program_fk
        foreign key (tenant_id, location_id, program_id)
        references gba.special_programs(tenant_id, location_id, id) on delete restrict,
    constraint special_enrollments_cp_fk
        foreign key (tenant_id, participant_counterparty_id)
        references gba.counterparties(tenant_id, id) on delete restrict,
    constraint special_enrollments_checks
        check (
            status in ('active', 'completed', 'cancelled')
            and sessions_total >= 1
            and sessions_used between 0 and sessions_total
            and revision >= 1
        )
);

create table gba.special_rooms (
    id uuid not null,
    tenant_id uuid not null,
    location_id uuid not null,
    room_number text not null,
    room_type text not null,
    max_guests integer not null default 2,
    nightly_rate_minor bigint not null default 0,
    currency text not null references gba.currencies(code),
    housekeeping_status text not null default 'clean',
    revision integer not null default 1,
    recorded_by uuid not null references gba.users(id),
    recorded_at timestamptz not null default now(),
    primary key (tenant_id, id),
    constraint special_rooms_location_fk
        foreign key (tenant_id, location_id)
        references gba.locations(tenant_id, id) on delete restrict,
    constraint special_rooms_loc_id_unique
        unique (tenant_id, location_id, id),
    constraint special_rooms_num_unique
        unique (tenant_id, location_id, room_number),
    constraint special_rooms_checks
        check (
            btrim(room_number) = room_number and char_length(room_number) between 1 and 32
            and btrim(room_type) = room_type and char_length(room_type) between 1 and 80
            and max_guests between 1 and 50
            and nightly_rate_minor between 0 and 999999999999999
            and housekeeping_status in ('clean', 'occupied', 'dirty', 'maintenance')
            and revision >= 1
        )
);

create table gba.special_stays (
    id uuid not null,
    tenant_id uuid not null,
    location_id uuid not null,
    room_id uuid not null,
    guest_counterparty_id uuid not null,
    check_in_date date not null,
    check_out_date date not null,
    guest_count integer not null default 1,
    status text not null default 'reserved',
    checked_in_at timestamptz null,
    checked_out_at timestamptz null,
    revision integer not null default 1,
    recorded_by uuid not null references gba.users(id),
    recorded_at timestamptz not null default now(),
    primary key (tenant_id, id),
    constraint special_stays_room_fk
        foreign key (tenant_id, location_id, room_id)
        references gba.special_rooms(tenant_id, location_id, id) on delete restrict,
    constraint special_stays_guest_fk
        foreign key (tenant_id, guest_counterparty_id)
        references gba.counterparties(tenant_id, id) on delete restrict,
    constraint special_stays_checks
        check (
            check_out_date > check_in_date
            and guest_count between 1 and 50
            and status in ('reserved', 'checked_in', 'checked_out', 'cancelled')
            and revision >= 1
        )
);

create table gba.special_events (
    id uuid not null,
    tenant_id uuid not null,
    location_id uuid not null,
    code text not null,
    title text not null,
    event_date date not null,
    capacity integer not null,
    tickets_sold integer not null default 0,
    ticket_price_minor bigint not null default 0,
    currency text not null references gba.currencies(code),
    status text not null default 'scheduled',
    revision integer not null default 1,
    recorded_by uuid not null references gba.users(id),
    recorded_at timestamptz not null default now(),
    primary key (tenant_id, id),
    constraint special_events_location_fk
        foreign key (tenant_id, location_id)
        references gba.locations(tenant_id, id) on delete restrict,
    constraint special_events_loc_id_unique
        unique (tenant_id, location_id, id),
    constraint special_events_code_unique
        unique (tenant_id, location_id, code),
    constraint special_events_checks
        check (
            btrim(code) = code and char_length(code) between 2 and 64
            and code ~ '^[A-Z0-9][A-Z0-9_-]*$'
            and btrim(title) = title and char_length(title) between 1 and 200
            and capacity between 1 and 1000000
            and tickets_sold between 0 and capacity
            and ticket_price_minor between 0 and 999999999999999
            and status in ('scheduled', 'completed', 'cancelled')
            and revision >= 1
        )
);

create table gba.special_tickets (
    id uuid not null,
    tenant_id uuid not null,
    location_id uuid not null,
    event_id uuid not null,
    attendee_counterparty_id uuid not null,
    ticket_code text not null,
    quantity integer not null default 1,
    status text not null default 'issued',
    checked_in_at timestamptz null,
    revision integer not null default 1,
    recorded_by uuid not null references gba.users(id),
    recorded_at timestamptz not null default now(),
    primary key (tenant_id, id),
    constraint special_tickets_event_fk
        foreign key (tenant_id, location_id, event_id)
        references gba.special_events(tenant_id, location_id, id) on delete restrict,
    constraint special_tickets_attendee_fk
        foreign key (tenant_id, attendee_counterparty_id)
        references gba.counterparties(tenant_id, id) on delete restrict,
    constraint special_tickets_code_unique
        unique (tenant_id, event_id, ticket_code),
    constraint special_tickets_checks
        check (
            btrim(ticket_code) = ticket_code and char_length(ticket_code) between 2 and 64
            and quantity between 1 and 100
            and status in ('issued', 'checked_in', 'cancelled')
            and revision >= 1
        )
);

-- RLS, grants and module write gates
alter table gba.special_programs enable row level security;
alter table gba.special_programs force row level security;
create policy special_programs_tenant_isolation on gba.special_programs
    using (tenant_id = gba.current_tenant_id()) with check (tenant_id = gba.current_tenant_id());
grant select, insert, update on gba.special_programs to gba_runtime;
create trigger special_programs_require_module before insert on gba.special_programs
    for each row execute function gba.require_enabled_module('hospitality_events');

alter table gba.special_enrollments enable row level security;
alter table gba.special_enrollments force row level security;
create policy special_enrollments_tenant_isolation on gba.special_enrollments
    using (tenant_id = gba.current_tenant_id()) with check (tenant_id = gba.current_tenant_id());
grant select, insert, update on gba.special_enrollments to gba_runtime;
create trigger special_enrollments_require_module before insert on gba.special_enrollments
    for each row execute function gba.require_enabled_module('hospitality_events');

alter table gba.special_rooms enable row level security;
alter table gba.special_rooms force row level security;
create policy special_rooms_tenant_isolation on gba.special_rooms
    using (tenant_id = gba.current_tenant_id()) with check (tenant_id = gba.current_tenant_id());
grant select, insert, update on gba.special_rooms to gba_runtime;
create trigger special_rooms_require_module before insert on gba.special_rooms
    for each row execute function gba.require_enabled_module('hospitality_events');

alter table gba.special_stays enable row level security;
alter table gba.special_stays force row level security;
create policy special_stays_tenant_isolation on gba.special_stays
    using (tenant_id = gba.current_tenant_id()) with check (tenant_id = gba.current_tenant_id());
grant select, insert, update on gba.special_stays to gba_runtime;
create trigger special_stays_require_module before insert on gba.special_stays
    for each row execute function gba.require_enabled_module('hospitality_events');

alter table gba.special_events enable row level security;
alter table gba.special_events force row level security;
create policy special_events_tenant_isolation on gba.special_events
    using (tenant_id = gba.current_tenant_id()) with check (tenant_id = gba.current_tenant_id());
grant select, insert, update on gba.special_events to gba_runtime;
create trigger special_events_require_module before insert on gba.special_events
    for each row execute function gba.require_enabled_module('hospitality_events');

alter table gba.special_tickets enable row level security;
alter table gba.special_tickets force row level security;
create policy special_tickets_tenant_isolation on gba.special_tickets
    using (tenant_id = gba.current_tenant_id()) with check (tenant_id = gba.current_tenant_id());
grant select, insert, update on gba.special_tickets to gba_runtime;
create trigger special_tickets_require_module before insert on gba.special_tickets
    for each row execute function gba.require_enabled_module('hospitality_events');

-- Special venues branch scope:
create policy special_programs_location_scope on gba.special_programs
    as restrictive to gba_runtime
    using (gba.current_location_id() is null or location_id = gba.current_location_id())
    with check (gba.current_location_id() is null or location_id = gba.current_location_id());

create policy special_enrollments_location_scope on gba.special_enrollments
    as restrictive to gba_runtime
    using (gba.current_location_id() is null or location_id = gba.current_location_id())
    with check (gba.current_location_id() is null or location_id = gba.current_location_id());

create policy special_rooms_location_scope on gba.special_rooms
    as restrictive to gba_runtime
    using (gba.current_location_id() is null or location_id = gba.current_location_id())
    with check (gba.current_location_id() is null or location_id = gba.current_location_id());

create policy special_stays_location_scope on gba.special_stays
    as restrictive to gba_runtime
    using (gba.current_location_id() is null or location_id = gba.current_location_id())
    with check (gba.current_location_id() is null or location_id = gba.current_location_id());

create policy special_events_location_scope on gba.special_events
    as restrictive to gba_runtime
    using (gba.current_location_id() is null or location_id = gba.current_location_id())
    with check (gba.current_location_id() is null or location_id = gba.current_location_id());

create policy special_tickets_location_scope on gba.special_tickets
    as restrictive to gba_runtime
    using (gba.current_location_id() is null or location_id = gba.current_location_id())
    with check (gba.current_location_id() is null or location_id = gba.current_location_id());
