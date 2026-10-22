-- L1 / package L (BEAUTY-01), the owner's delegation of 2026-10-22. Forward only; no row changes.
--
-- A variant may list ordered stages: active (the specialist works), processing (the client waits;
-- the specialist is free) or finish, each with minutes and the resource kinds it occupies. A
-- variant with stages books exactly the sum of its stages; one without stages keeps its meaning.
-- Equipment becomes a resource kind.

alter table gba.resources drop constraint resources_kind_valid;
alter table gba.resources add constraint resources_kind_valid
    check (kind in ('artist', 'chair', 'room', 'staff', 'equipment'));

-- The resource kinds of one stage: known, distinct, and the specialist exactly where work is done.
create function gba.variant_stage_resources_valid(kind text, resources text[]) returns boolean
language sql immutable parallel safe set search_path=pg_catalog as $$
    select resources <@ array['specialist', 'chair', 'room', 'equipment']::text[]
       and cardinality(resources) = (select count(distinct r) from unnest(resources) r)
       and (('specialist' = any(resources)) = (kind in ('active', 'finish')))
$$;
revoke all on function gba.variant_stage_resources_valid(text, text[]) from public;
grant execute on function gba.variant_stage_resources_valid(text, text[]) to gba_runtime;

create table gba.variant_stages (
    tenant_id uuid not null references gba.tenants (id),
    variant_id uuid not null,
    position smallint not null
        constraint variant_stages_position_range check (position between 1 and 10),
    kind text not null
        constraint variant_stages_kind_valid check (kind in ('active', 'processing', 'finish')),
    minutes integer not null
        constraint variant_stages_minutes_range check (minutes between 1 and 720),
    resources text[] not null
        constraint variant_stages_resources_valid
        check (gba.variant_stage_resources_valid(kind, resources)),
    primary key (tenant_id, variant_id, position),
    constraint variant_stages_variant_fk
        foreign key (tenant_id, variant_id) references gba.service_variants (tenant_id, id)
);
alter table gba.variant_stages enable row level security;
alter table gba.variant_stages force row level security;
create policy variant_stages_tenant_isolation on gba.variant_stages
    using (tenant_id = gba.current_tenant_id())
    with check (tenant_id = gba.current_tenant_id());
grant select, insert, delete on gba.variant_stages to gba_runtime;

-- A staged variant books exactly the sum of its stages and has at least one active stage.
create function gba.check_variant_stage_duration() returns trigger
language plpgsql set search_path=pg_catalog as $$
declare
    variant uuid;
    tenant uuid;
    total bigint;
    active bigint;
    duration integer;
begin
    if tg_table_name = 'service_variants' then
        variant := new.id;
        tenant := new.tenant_id;
    elsif tg_op = 'DELETE' then
        variant := old.variant_id;
        tenant := old.tenant_id;
    else
        variant := new.variant_id;
        tenant := new.tenant_id;
    end if;
    select sum(s.minutes), count(*) filter (where s.kind = 'active') into total, active
        from gba.variant_stages s where s.tenant_id = tenant and s.variant_id = variant;
    if total is null then
        return null;
    end if;
    select v.booking_duration_minutes into duration from gba.service_variants v
        where v.tenant_id = tenant and v.id = variant;
    if duration is distinct from total or active = 0 then
        raise exception using errcode = 'check_violation',
            constraint = 'service_variants_duration_of_stages',
            message = 'a staged variant books exactly the sum of its stages, with an active stage';
    end if;
    return null;
end;
$$;
revoke all on function gba.check_variant_stage_duration() from public;

create constraint trigger variant_stages_duration after insert or update or delete
    on gba.variant_stages deferrable initially deferred
    for each row execute function gba.check_variant_stage_duration();
-- A change of the duration itself is checked at once, so the caller can name the reason.
create trigger service_variants_duration_of_stages after update of booking_duration_minutes
    on gba.service_variants
    for each row execute function gba.check_variant_stage_duration();
