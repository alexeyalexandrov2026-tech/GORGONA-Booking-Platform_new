-- 0146_special_clinical_vet_social_care.sql
-- ADR-0043 / SPECIAL-02: consent-gated healthcare, veterinary, and social care workflows.
-- Invoker rights only.

create table gba.care_subjects (
    id uuid not null,
    tenant_id uuid not null,
    location_id uuid not null,
    guardian_counterparty_id uuid not null,
    subject_kind text not null,
    code text not null,
    display_name text not null,
    species_or_profile text null,
    allergies_summary text null,
    revision integer not null default 1,
    recorded_by uuid not null references gba.users(id),
    recorded_at timestamptz not null default now(),
    primary key (tenant_id, id),
    constraint care_subjects_location_fk
        foreign key (tenant_id, location_id)
        references gba.locations(tenant_id, id) on delete restrict,
    constraint care_subjects_guardian_fk
        foreign key (tenant_id, guardian_counterparty_id)
        references gba.counterparties(tenant_id, id) on delete restrict,
    constraint care_subjects_loc_id_unique
        unique (tenant_id, location_id, id),
    constraint care_subjects_code_unique
        unique (tenant_id, location_id, code),
    constraint care_subjects_checks
        check (
            subject_kind in ('human_patient', 'animal_patient', 'social_care_recipient')
            and btrim(code) = code and char_length(code) between 2 and 64
            and code ~ '^[A-Z0-9][A-Z0-9_-]*$'
            and btrim(display_name) = display_name and char_length(display_name) between 1 and 200
            and revision >= 1
        )
);

create table gba.care_consents (
    id uuid not null,
    tenant_id uuid not null,
    location_id uuid not null,
    subject_id uuid not null,
    scope text not null,
    status text not null default 'active',
    granted_by_name text not null,
    revoked_at timestamptz null,
    revision integer not null default 1,
    recorded_by uuid not null references gba.users(id),
    recorded_at timestamptz not null default now(),
    primary key (tenant_id, id),
    constraint care_consents_subject_fk
        foreign key (tenant_id, location_id, subject_id)
        references gba.care_subjects(tenant_id, location_id, id) on delete restrict,
    constraint care_consents_anchor_unique
        unique (tenant_id, location_id, id, subject_id),
    constraint care_consents_checks
        check (
            scope in ('care_records', 'procedures', 'medication', 'sharing')
            and status in ('active', 'revoked')
            and ((status = 'revoked') = (revoked_at is not null))
            and btrim(granted_by_name) = granted_by_name
            and char_length(granted_by_name) between 1 and 200
            and revision >= 1
        )
);

create table gba.care_plans (
    id uuid not null,
    tenant_id uuid not null,
    location_id uuid not null,
    subject_id uuid not null,
    consent_id uuid not null,
    title text not null,
    status text not null default 'active',
    revision integer not null default 1,
    recorded_by uuid not null references gba.users(id),
    recorded_at timestamptz not null default now(),
    primary key (tenant_id, id),
    constraint care_plans_consent_fk
        foreign key (tenant_id, location_id, consent_id, subject_id)
        references gba.care_consents(tenant_id, location_id, id, subject_id) on delete restrict,
    constraint care_plans_checks
        check (
            btrim(title) = title and char_length(title) between 1 and 200
            and status in ('active', 'completed', 'cancelled')
            and revision >= 1
        )
);

create table gba.care_encounters (
    id uuid not null,
    tenant_id uuid not null,
    location_id uuid not null,
    subject_id uuid not null,
    consent_id uuid not null,
    plan_id uuid null,
    encounter_date date not null,
    summary text not null,
    clinical_notes text not null,
    recorded_by uuid not null references gba.users(id),
    recorded_at timestamptz not null default now(),
    primary key (tenant_id, id),
    constraint care_encounters_consent_fk
        foreign key (tenant_id, location_id, consent_id, subject_id)
        references gba.care_consents(tenant_id, location_id, id, subject_id) on delete restrict,
    constraint care_encounters_plan_fk
        foreign key (tenant_id, plan_id)
        references gba.care_plans(tenant_id, id) on delete restrict,
    constraint care_encounters_checks
        check (
            btrim(summary) = summary and char_length(summary) between 1 and 300
            and btrim(clinical_notes) = clinical_notes
            and char_length(clinical_notes) between 1 and 2000
        )
);

-- RLS, grants and module write gates
alter table gba.care_subjects enable row level security;
alter table gba.care_subjects force row level security;
create policy care_subjects_tenant_isolation on gba.care_subjects
    using (tenant_id = gba.current_tenant_id()) with check (tenant_id = gba.current_tenant_id());
grant select, insert, update on gba.care_subjects to gba_runtime;
create trigger care_subjects_require_module before insert on gba.care_subjects
    for each row execute function gba.require_enabled_module('clinical_care');

alter table gba.care_consents enable row level security;
alter table gba.care_consents force row level security;
create policy care_consents_tenant_isolation on gba.care_consents
    using (tenant_id = gba.current_tenant_id()) with check (tenant_id = gba.current_tenant_id());
grant select, insert, update on gba.care_consents to gba_runtime;
create trigger care_consents_require_module before insert on gba.care_consents
    for each row execute function gba.require_enabled_module('clinical_care');

alter table gba.care_plans enable row level security;
alter table gba.care_plans force row level security;
create policy care_plans_tenant_isolation on gba.care_plans
    using (tenant_id = gba.current_tenant_id()) with check (tenant_id = gba.current_tenant_id());
grant select, insert, update on gba.care_plans to gba_runtime;
create trigger care_plans_require_module before insert on gba.care_plans
    for each row execute function gba.require_enabled_module('clinical_care');

alter table gba.care_encounters enable row level security;
alter table gba.care_encounters force row level security;
create policy care_encounters_tenant_isolation on gba.care_encounters
    using (tenant_id = gba.current_tenant_id()) with check (tenant_id = gba.current_tenant_id());
grant select, insert on gba.care_encounters to gba_runtime;
create trigger care_encounters_require_module before insert on gba.care_encounters
    for each row execute function gba.require_enabled_module('clinical_care');

-- Clinical care branch scope:
create policy care_subjects_location_scope on gba.care_subjects
    as restrictive to gba_runtime
    using (gba.current_location_id() is null or location_id = gba.current_location_id())
    with check (gba.current_location_id() is null or location_id = gba.current_location_id());

create policy care_consents_location_scope on gba.care_consents
    as restrictive to gba_runtime
    using (gba.current_location_id() is null or location_id = gba.current_location_id())
    with check (gba.current_location_id() is null or location_id = gba.current_location_id());

create policy care_plans_location_scope on gba.care_plans
    as restrictive to gba_runtime
    using (gba.current_location_id() is null or location_id = gba.current_location_id())
    with check (gba.current_location_id() is null or location_id = gba.current_location_id());

create policy care_encounters_location_scope on gba.care_encounters
    as restrictive to gba_runtime
    using (gba.current_location_id() is null or location_id = gba.current_location_id())
    with check (gba.current_location_id() is null or location_id = gba.current_location_id());
