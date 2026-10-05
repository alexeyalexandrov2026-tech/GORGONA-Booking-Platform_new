-- Counterparties, contacts, match decisions and confirmed booking links (ADR-0020, E1).
-- Identities never change, content is append-only and links are event logs: nothing is
-- updated or deleted, so history keeps its meaning. Matching only suggests; a person
-- records every merge, "not a duplicate" and separation. Booking customer rows are
-- referenced, never changed. Every insert needs the counterparties module enabled by a
-- published configuration; nothing is enabled on a business's behalf.

-- One gate for every optional module (argument: module id). The shared advisory lock
-- pairs with the exclusive lock a publication takes, so a write is ordered entirely
-- before or after it. No module state means the module was never enabled.
create function gba.require_enabled_module() returns trigger
    language plpgsql as $$
begin
    perform pg_catalog.pg_advisory_xact_lock_shared(
        pg_catalog.hashtextextended('gba:business-configuration:' || new.tenant_id::text, 0));
    if not exists (
        select 1 from gba.business_module_states s
        where s.tenant_id = new.tenant_id and s.module_id = tg_argv[0] and s.enabled
    ) then
        raise exception using errcode = 'GBM01',
            message = 'the ' || tg_argv[0] || ' module is disabled for this business';
    end if;
    return new;
end;
$$;
revoke all on function gba.require_enabled_module() from public;

create table gba.counterparties (
    tenant_id uuid not null references gba.tenants (id),
    id uuid not null,
    kind text not null check (kind in ('person', 'organization')),
    created_by uuid not null references gba.users (id),
    created_at timestamptz not null default now(),
    primary key (tenant_id, id)
);

create table gba.counterparty_versions (
    tenant_id uuid not null,
    counterparty_id uuid not null,
    revision integer not null check (revision > 0),
    display_name text not null check (
        length(btrim(display_name, E' \t\r\n')) between 1 and 200
        and display_name !~ '[[:cntrl:]]'
    ),
    legal_name text check (
        legal_name is null or (
            length(btrim(legal_name, E' \t\r\n')) between 1 and 300
            and legal_name !~ '[[:cntrl:]]'
        )
    ),
    tax_id text check (tax_id is null or tax_id ~ '^[A-Za-z0-9][A-Za-z0-9 ./-]{0,63}$'),
    registration_number text check (
        registration_number is null
        or registration_number ~ '^[A-Za-z0-9][A-Za-z0-9 ./-]{0,63}$'
    ),
    email text check (
        email is null or (
            length(email) between 3 and 254 and email = lower(btrim(email))
            and email ~ '^[^@[:space:][:cntrl:]]+@[^@[:space:][:cntrl:]]+$'
        )
    ),
    phone text check (phone is null or phone ~ '^[+]?[0-9 ().-]{7,32}$'),
    phone_digits text generated always as (
        nullif(regexp_replace(phone, '[^0-9]', '', 'g'), '')
    ) stored,
    name_key text generated always as (
        lower(regexp_replace(btrim(display_name), '[[:space:]]+', ' ', 'g'))
    ) stored,
    roles text[] not null check (
        roles <@ array['customer', 'supplier', 'contractor', 'partner']::text[]
        and cardinality(roles) <= 4
    ),
    state text not null check (state in ('active', 'archived', 'merged')),
    merged_into uuid,
    created_by uuid not null references gba.users (id),
    created_at timestamptz not null default now(),
    created_transaction xid8 not null default pg_catalog.pg_current_xact_id(),
    primary key (tenant_id, counterparty_id, revision),
    foreign key (tenant_id, counterparty_id) references gba.counterparties (tenant_id, id),
    constraint counterparty_versions_merged_into_fk foreign key (tenant_id, merged_into)
        references gba.counterparties (tenant_id, id),
    constraint counterparty_versions_merge_target check (
        (state = 'merged') = (merged_into is not null)
        and merged_into is distinct from counterparty_id
    )
);
create index counterparty_versions_email on gba.counterparty_versions (tenant_id, email)
    where email is not null;
create index counterparty_versions_phone on gba.counterparty_versions (tenant_id, phone_digits)
    where phone_digits is not null;
create index counterparty_versions_tax_id on gba.counterparty_versions (tenant_id, tax_id)
    where tax_id is not null;
create index counterparty_versions_registration
    on gba.counterparty_versions (tenant_id, registration_number)
    where registration_number is not null;
create index counterparty_versions_name on gba.counterparty_versions (tenant_id, name_key);
create index counterparty_versions_merged_into
    on gba.counterparty_versions (tenant_id, merged_into) where merged_into is not null;

-- Contacts belong to one saved card version: one card, one revision, one history.
create table gba.counterparty_version_contacts (
    tenant_id uuid not null,
    counterparty_id uuid not null,
    revision integer not null,
    position smallint not null check (position between 1 and 20),
    name text not null check (
        length(btrim(name, E' \t\r\n')) between 1 and 200 and name !~ '[[:cntrl:]]'
    ),
    job_title text check (
        job_title is null or (
            length(btrim(job_title, E' \t\r\n')) between 1 and 200
            and job_title !~ '[[:cntrl:]]'
        )
    ),
    email text check (
        email is null or (
            length(email) between 3 and 254 and email = lower(btrim(email))
            and email ~ '^[^@[:space:][:cntrl:]]+@[^@[:space:][:cntrl:]]+$'
        )
    ),
    phone text check (phone is null or phone ~ '^[+]?[0-9 ().-]{7,32}$'),
    phone_digits text generated always as (
        nullif(regexp_replace(phone, '[^0-9]', '', 'g'), '')
    ) stored,
    primary key (tenant_id, counterparty_id, revision, position),
    foreign key (tenant_id, counterparty_id, revision)
        references gba.counterparty_versions (tenant_id, counterparty_id, revision)
);
create index counterparty_version_contacts_email
    on gba.counterparty_version_contacts (tenant_id, email) where email is not null;
create index counterparty_version_contacts_phone
    on gba.counterparty_version_contacts (tenant_id, phone_digits)
    where phone_digits is not null;

-- A person's decision about two records: merged (the first into the second), distinct
-- (not duplicates) or separated (the reversal of a merge). Nothing is moved by a merge.
create table gba.counterparty_match_decisions (
    tenant_id uuid not null references gba.tenants (id),
    id uuid not null default uuidv7(),
    kind text not null check (kind in ('merged', 'distinct', 'separated')),
    counterparty_id uuid not null,
    other_counterparty_id uuid not null,
    reverses_decision_id uuid,
    counterparty_revision integer,
    decided_by uuid not null references gba.users (id),
    decided_at timestamptz not null default now(),
    created_transaction xid8 not null default pg_catalog.pg_current_xact_id(),
    primary key (tenant_id, id),
    constraint counterparty_match_decisions_one_version
        unique (tenant_id, counterparty_id, counterparty_revision),
    constraint counterparty_match_decisions_counterparty_fk foreign key
        (tenant_id, counterparty_id) references gba.counterparties (tenant_id, id),
    constraint counterparty_match_decisions_other_fk foreign key
        (tenant_id, other_counterparty_id) references gba.counterparties (tenant_id, id),
    constraint counterparty_match_decisions_reverses_fk foreign key
        (tenant_id, reverses_decision_id)
        references gba.counterparty_match_decisions (tenant_id, id),
    constraint counterparty_match_decisions_two_records
        check (counterparty_id <> other_counterparty_id),
    constraint counterparty_match_decisions_reversal
        check ((kind = 'separated') = (reverses_decision_id is not null)),
    constraint counterparty_match_decisions_version
        check ((kind = 'distinct') = (counterparty_revision is null)),
    foreign key (tenant_id, counterparty_id, counterparty_revision)
        references gba.counterparty_versions (tenant_id, counterparty_id, revision)
        deferrable initially deferred
);
create unique index counterparty_match_decisions_one_distinct_pair
    on gba.counterparty_match_decisions (
        tenant_id, least(counterparty_id, other_counterparty_id),
        greatest(counterparty_id, other_counterparty_id)
    ) where kind = 'distinct';
create unique index counterparty_match_decisions_one_reversal
    on gba.counterparty_match_decisions (tenant_id, reverses_decision_id)
    where reverses_decision_id is not null;

-- Confirmed links between a booking's customer and a counterparty, per booking:
-- linked -> unlinked -> linked ... with the basis a person confirmed.
create table gba.counterparty_booking_links (
    tenant_id uuid not null,
    id uuid not null default uuidv7(),
    booking_id uuid not null,
    sequence integer not null check (sequence > 0),
    action text not null check (action in ('linked', 'unlinked')),
    counterparty_id uuid not null,
    basis text[] not null check (
        basis <@ array['email', 'phone']::text[]
        and (action = 'linked') = (cardinality(basis) > 0)
    ),
    decided_by uuid not null references gba.users (id),
    decided_at timestamptz not null default now(),
    primary key (tenant_id, booking_id, sequence),
    unique (tenant_id, id),
    constraint counterparty_booking_links_booking_fk foreign key (tenant_id, booking_id)
        references gba.booking_customers (tenant_id, booking_id),
    constraint counterparty_booking_links_counterparty_fk foreign key
        (tenant_id, counterparty_id) references gba.counterparties (tenant_id, id)
);
create index counterparty_booking_links_counterparty
    on gba.counterparty_booking_links (tenant_id, counterparty_id, id);

alter table gba.counterparties enable row level security;
alter table gba.counterparties force row level security;
alter table gba.counterparty_versions enable row level security;
alter table gba.counterparty_versions force row level security;
alter table gba.counterparty_version_contacts enable row level security;
alter table gba.counterparty_version_contacts force row level security;
alter table gba.counterparty_match_decisions enable row level security;
alter table gba.counterparty_match_decisions force row level security;
alter table gba.counterparty_booking_links enable row level security;
alter table gba.counterparty_booking_links force row level security;

create policy counterparties_tenant_isolation on gba.counterparties
    using (tenant_id = gba.current_tenant_id())
    with check (tenant_id = gba.current_tenant_id());
grant select on gba.counterparties to gba_runtime;
grant insert (tenant_id, id, kind, created_by) on gba.counterparties to gba_runtime;

create policy counterparty_versions_tenant_isolation on gba.counterparty_versions
    using (tenant_id = gba.current_tenant_id())
    with check (tenant_id = gba.current_tenant_id());
grant select on gba.counterparty_versions to gba_runtime;
grant insert (tenant_id, counterparty_id, revision, display_name, legal_name, tax_id,
              registration_number, email, phone, roles, state, merged_into, created_by)
    on gba.counterparty_versions to gba_runtime;

create policy counterparty_version_contacts_tenant_isolation
    on gba.counterparty_version_contacts
    using (tenant_id = gba.current_tenant_id())
    with check (tenant_id = gba.current_tenant_id());
grant select on gba.counterparty_version_contacts to gba_runtime;
grant insert (tenant_id, counterparty_id, revision, position, name, job_title, email, phone)
    on gba.counterparty_version_contacts to gba_runtime;

create policy counterparty_match_decisions_tenant_isolation
    on gba.counterparty_match_decisions
    using (tenant_id = gba.current_tenant_id())
    with check (tenant_id = gba.current_tenant_id());
grant select on gba.counterparty_match_decisions to gba_runtime;
grant insert (tenant_id, kind, counterparty_id, other_counterparty_id, reverses_decision_id,
              counterparty_revision, decided_by)
    on gba.counterparty_match_decisions to gba_runtime;

create policy counterparty_booking_links_tenant_isolation on gba.counterparty_booking_links
    using (tenant_id = gba.current_tenant_id())
    with check (tenant_id = gba.current_tenant_id());
grant select on gba.counterparty_booking_links to gba_runtime;
grant insert (tenant_id, booking_id, sequence, action, counterparty_id, basis, decided_by)
    on gba.counterparty_booking_links to gba_runtime;

create function gba.reject_counterparty_mutation() returns trigger language plpgsql as $$
begin
    raise exception using errcode = 'check_violation',
        message = 'counterparty records and decisions are kept unchanged';
end;
$$;
revoke all on function gba.reject_counterparty_mutation() from public;
create trigger counterparties_immutable before update or delete on gba.counterparties
    for each row execute function gba.reject_counterparty_mutation();
create trigger counterparty_versions_immutable before update or delete
    on gba.counterparty_versions
    for each row execute function gba.reject_counterparty_mutation();
create trigger counterparty_match_decisions_immutable before update or delete
    on gba.counterparty_match_decisions
    for each row execute function gba.reject_counterparty_mutation();

-- Revisions are contiguous: the next version is the latest plus one.
create function gba.enforce_counterparty_version() returns trigger
    language plpgsql as $$
declare
    previous gba.counterparty_versions%rowtype;
    decision gba.counterparty_match_decisions%rowtype;
    restored text;
begin
    perform pg_catalog.pg_advisory_xact_lock(
        pg_catalog.hashtextextended('gba:counterparties:' || new.tenant_id::text, 0));
    select v.* into previous from gba.counterparty_versions v
    where v.tenant_id = new.tenant_id and v.counterparty_id = new.counterparty_id
    order by v.revision desc limit 1;
    if new.revision <> coalesce(previous.revision, 0) + 1 then
        raise exception using errcode = 'check_violation',
            message = 'a counterparty version follows the latest revision';
    end if;
    if (select count(distinct r) from unnest(new.roles) r) <> cardinality(new.roles)
       or (new.phone is not null and length(regexp_replace(new.phone, '[^0-9]', '', 'g'))
           not between 7 and 15) then
        raise exception using errcode = 'check_violation',
            message = 'counterparty roles and phone digits must be valid';
    end if;
    if new.state = 'merged' or previous.state = 'merged' then
        select d.* into decision from gba.counterparty_match_decisions d
        where d.tenant_id = new.tenant_id and d.counterparty_id = new.counterparty_id
          and d.counterparty_revision = new.revision
          and d.created_transaction = pg_catalog.pg_current_xact_id();
        if previous.revision is null or decision.id is null
           or (new.state = 'merged' and
               (previous.state = 'merged' or decision.kind <> 'merged'
                or decision.other_counterparty_id is distinct from new.merged_into))
           or (previous.state = 'merged' and decision.kind <> 'separated') then
            raise exception using errcode = 'check_violation',
                message = 'merge state requires its matching decision in this transaction';
        end if;
        -- Decisions can be staged before their versions in one transaction.
        -- Recheck the graph at version insertion so staged pairs cannot form a
        -- cycle or chain after the initial decision check.
        if new.state = 'merged' and (
            exists (select 1 from gba.counterparty_versions v
                where v.tenant_id = new.tenant_id and v.counterparty_id = new.merged_into
                  and v.state = 'merged'
                  and v.revision = (select max(x.revision) from gba.counterparty_versions x
                      where x.tenant_id = v.tenant_id and x.counterparty_id = v.counterparty_id))
            or exists (select 1 from gba.counterparty_versions v
                where v.tenant_id = new.tenant_id and v.merged_into = new.counterparty_id
                  and v.revision = (select max(x.revision) from gba.counterparty_versions x
                      where x.tenant_id = v.tenant_id and x.counterparty_id = v.counterparty_id))
        ) then
            raise exception using errcode = 'check_violation',
                message = 'merge versions cannot create a cycle or chain';
        end if;
        if previous.state = 'merged' then
            select v.state into restored from gba.counterparty_versions v
            where v.tenant_id = new.tenant_id and v.counterparty_id = new.counterparty_id
              and v.revision = previous.revision - 1;
            if new.state is distinct from restored then
                raise exception using errcode = 'check_violation',
                    message = 'separation restores the state preceding the merge';
            end if;
        end if;
    end if;
    return new;
end;
$$;
revoke all on function gba.enforce_counterparty_version() from public;
create trigger counterparty_versions_next_revision before insert on gba.counterparty_versions
    for each row execute function gba.enforce_counterparty_version();

-- A decision validates the current pair; a deferred constraint also requires the
-- promised version to exist at commit. SQL cannot consume another pair's reversal.
create function gba.enforce_counterparty_decision() returns trigger
    language plpgsql as $$
declare
    source gba.counterparty_versions%rowtype;
    target gba.counterparty_versions%rowtype;
    merge gba.counterparty_match_decisions%rowtype;
begin
    perform pg_catalog.pg_advisory_xact_lock(
        pg_catalog.hashtextextended('gba:counterparties:' || new.tenant_id::text, 0));
    select v.* into source from gba.counterparty_versions v
    where v.tenant_id = new.tenant_id and v.counterparty_id = new.counterparty_id
    order by v.revision desc limit 1;
    select v.* into target from gba.counterparty_versions v
    where v.tenant_id = new.tenant_id and v.counterparty_id = new.other_counterparty_id
    order by v.revision desc limit 1;
    if source.revision is null or target.revision is null then
        raise exception using errcode = 'check_violation',
            message = 'a decision requires two saved cards';
    end if;
    if new.kind = 'merged' then
        if source.state = 'merged' or target.state = 'merged'
           or new.counterparty_revision <> source.revision + 1
           or exists (
               select 1 from gba.counterparty_versions v
               where v.tenant_id = new.tenant_id and v.merged_into = new.counterparty_id
                 and v.revision = (select max(x.revision) from gba.counterparty_versions x
                     where x.tenant_id = v.tenant_id and x.counterparty_id = v.counterparty_id)
           ) then
            raise exception using errcode = 'check_violation',
                message = 'merged cards and cards with merged children cannot be merged';
        end if;
    elsif new.kind = 'separated' then
        select d.* into merge from gba.counterparty_match_decisions d
        where d.tenant_id = new.tenant_id and d.id = new.reverses_decision_id;
        if merge.kind is distinct from 'merged'
           or (merge.counterparty_id, merge.other_counterparty_id)
              is distinct from (new.counterparty_id, new.other_counterparty_id)
           or source.state <> 'merged' or source.merged_into <> new.other_counterparty_id
           or source.revision <> merge.counterparty_revision
           or new.counterparty_revision <> source.revision + 1 then
            raise exception using errcode = 'check_violation',
                message = 'separation reverses the current merge of this exact pair';
        end if;
    end if;
    return new;
end;
$$;
revoke all on function gba.enforce_counterparty_decision() from public;
create trigger counterparty_match_decisions_check before insert on gba.counterparty_match_decisions
    for each row execute function gba.enforce_counterparty_decision();

create function gba.check_counterparty_decision_version() returns trigger
    language plpgsql as $$
begin
    if new.kind <> 'distinct' and not exists (
        select 1 from gba.counterparty_versions v
        where v.tenant_id = new.tenant_id and v.counterparty_id = new.counterparty_id
          and v.revision = new.counterparty_revision
          and v.created_transaction = new.created_transaction
          and ((new.kind = 'merged' and v.state = 'merged'
                and v.merged_into = new.other_counterparty_id)
               or (new.kind = 'separated' and v.state <> 'merged' and v.merged_into is null))
    ) then
        raise exception using errcode = 'check_violation',
            message = 'a match decision requires its immutable version before commit';
    end if;
    return null;
end;
$$;
revoke all on function gba.check_counterparty_decision_version() from public;
create constraint trigger counterparty_match_decisions_version_committed
    after insert on gba.counterparty_match_decisions deferrable initially deferred
    for each row execute function gba.check_counterparty_decision_version();

-- Contacts belong to the transaction that created their card version.
create function gba.guard_counterparty_version_contacts() returns trigger
    language plpgsql as $$
begin
    if tg_op <> 'INSERT' then
        raise exception using errcode = 'check_violation',
            message = 'saved contacts are kept unchanged';
    end if;
    perform pg_catalog.pg_advisory_xact_lock(
        pg_catalog.hashtextextended('gba:counterparties:' || new.tenant_id::text, 0));
    if not exists (
        select 1 from gba.counterparty_versions v
        where v.tenant_id = new.tenant_id and v.counterparty_id = new.counterparty_id
          and v.revision = new.revision
          and v.created_transaction = pg_catalog.pg_current_xact_id()
    ) then
        raise exception using errcode = 'check_violation',
            message = 'cannot change the contacts of a saved version';
    end if;
    return new;
end;
$$;
revoke all on function gba.guard_counterparty_version_contacts() from public;
create trigger counterparty_version_contacts_guard
    before insert or update or delete on gba.counterparty_version_contacts
    for each row execute function gba.guard_counterparty_version_contacts();

-- Per booking: links alternate linked/unlinked, an unlink names the linked record,
-- and the sequence advances by one. Nothing is rewritten.
create function gba.enforce_counterparty_booking_link() returns trigger
    language plpgsql as $$
declare
    last_sequence integer;
    last_action text;
    last_counterparty uuid;
begin
    if tg_op <> 'INSERT' then
        raise exception using errcode = 'check_violation',
            message = 'booking link history is kept';
    end if;
    perform pg_catalog.pg_advisory_xact_lock(
        pg_catalog.hashtextextended('gba:counterparties:' || new.tenant_id::text, 0));
    select l.sequence, l.action, l.counterparty_id
      into last_sequence, last_action, last_counterparty
      from gba.counterparty_booking_links l
     where l.tenant_id = new.tenant_id and l.booking_id = new.booking_id
     order by l.sequence desc limit 1;
    if new.sequence <> coalesce(last_sequence, 0) + 1
       or (new.action = 'linked' and last_action = 'linked')
       or (new.action = 'unlinked' and (last_action is distinct from 'linked'
                                        or last_counterparty <> new.counterparty_id)) then
        raise exception using errcode = 'check_violation',
            message = 'invalid booking link change';
    end if;
    if new.action = 'linked' and not exists (
        select 1 from gba.counterparty_versions v
        join gba.booking_customers bc on bc.tenant_id = v.tenant_id
            and bc.booking_id = new.booking_id
        where v.tenant_id = new.tenant_id and v.counterparty_id = new.counterparty_id
          and v.state = 'active'
          and v.revision = (select max(x.revision) from gba.counterparty_versions x
              where x.tenant_id = v.tenant_id and x.counterparty_id = v.counterparty_id)
          and cardinality(new.basis) =
              (select count(distinct b) from unnest(new.basis) b)
          and (not ('email' = any(new.basis)) or
               lower(btrim(bc.email)) = v.email or exists (
                   select 1 from gba.counterparty_version_contacts c
                   where c.tenant_id = v.tenant_id and c.counterparty_id = v.counterparty_id
                     and c.revision = v.revision and c.email = lower(btrim(bc.email))))
          and (not ('phone' = any(new.basis)) or
               nullif(regexp_replace(bc.phone, '[^0-9]', '', 'g'), '') = v.phone_digits
               or exists (
                   select 1 from gba.counterparty_version_contacts c
                   where c.tenant_id = v.tenant_id and c.counterparty_id = v.counterparty_id
                     and c.revision = v.revision and c.phone_digits =
                         nullif(regexp_replace(bc.phone, '[^0-9]', '', 'g'), '')))
    ) then
        raise exception using errcode = 'check_violation',
            message = 'a booking link requires the active card and matching customer details';
    end if;
    return new;
end;
$$;
revoke all on function gba.enforce_counterparty_booking_link() from public;
create trigger counterparty_booking_links_enforce_change
    before insert or update or delete on gba.counterparty_booking_links
    for each row execute function gba.enforce_counterparty_booking_link();

create trigger counterparties_require_module before insert on gba.counterparties
    for each row execute function gba.require_enabled_module('counterparties');
create trigger counterparty_versions_require_module before insert
    on gba.counterparty_versions
    for each row execute function gba.require_enabled_module('counterparties');
create trigger counterparty_version_contacts_require_module before insert
    on gba.counterparty_version_contacts
    for each row execute function gba.require_enabled_module('counterparties');
create trigger counterparty_match_decisions_require_module before insert
    on gba.counterparty_match_decisions
    for each row execute function gba.require_enabled_module('counterparties');
create trigger counterparty_booking_links_require_module before insert
    on gba.counterparty_booking_links
    for each row execute function gba.require_enabled_module('counterparties');

-- Counterparty branch scope: reusable separately when restoring a damaged boundary in tests.
create policy counterparties_unrestricted_scope on gba.counterparties
    as restrictive to gba_runtime
    using (gba.current_location_id() is null) with check (gba.current_location_id() is null);
create policy counterparty_versions_unrestricted_scope on gba.counterparty_versions
    as restrictive to gba_runtime
    using (gba.current_location_id() is null) with check (gba.current_location_id() is null);
create policy counterparty_version_contacts_unrestricted_scope
    on gba.counterparty_version_contacts as restrictive to gba_runtime
    using (gba.current_location_id() is null) with check (gba.current_location_id() is null);
create policy counterparty_match_decisions_unrestricted_scope
    on gba.counterparty_match_decisions as restrictive to gba_runtime
    using (gba.current_location_id() is null) with check (gba.current_location_id() is null);
create policy counterparty_booking_links_unrestricted_scope
    on gba.counterparty_booking_links as restrictive to gba_runtime
    using (gba.current_location_id() is null) with check (gba.current_location_id() is null);
