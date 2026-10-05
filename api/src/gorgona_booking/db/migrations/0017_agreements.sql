-- Contracts with counterparties ("agreements" in code; ADR-0020 E3).
-- An agreement belongs to one counterparty and optionally to one of the company's
-- legal entities. Its versions are inserted only: draft -> draft | agreed,
-- agreed -> draft (an amendment) | terminated; terminated is final. An agreed
-- version is never rewritten. A termination ends the latest agreed version, also
-- while an unsigned amendment draft is open (that draft stays in the history,
-- abandoned); its date may lie in the future. Signing happens outside the platform
-- and is only attested; there is no electronic signature. Inserts need the
-- counterparties module enabled by a published configuration.

create table gba.agreements (
    tenant_id uuid not null references gba.tenants (id),
    id uuid not null,
    counterparty_id uuid not null,
    legal_entity_id uuid,
    created_by uuid not null references gba.users (id),
    created_at timestamptz not null default now(),
    primary key (tenant_id, id),
    constraint agreements_counterparty_fk foreign key (tenant_id, counterparty_id)
        references gba.counterparties (tenant_id, id),
    constraint agreements_legal_entity_fk foreign key (tenant_id, legal_entity_id)
        references gba.legal_entities (tenant_id, id)
);
create index agreements_counterparty on gba.agreements (tenant_id, counterparty_id, id);

create table gba.agreement_versions (
    tenant_id uuid not null,
    agreement_id uuid not null,
    revision integer not null check (revision > 0),
    state text not null check (state in ('draft', 'agreed', 'terminated')),
    title text not null check (
        length(btrim(title, E' \t\r\n')) between 1 and 200 and title !~ '[[:cntrl:]]'
    ),
    number text check (
        number is null or (length(btrim(number, E' \t\r\n')) between 1 and 64
                           and number !~ '[[:cntrl:]]')
    ),
    summary text check (summary is null or length(summary) between 1 and 2000),
    effective_from date,
    effective_until date,
    signed_on date,
    attestation text check (attestation is null or attestation = 'signed_outside_platform'),
    document_id uuid,
    document_revision integer,
    terminated_on date,
    -- The agreed revision a termination ends.
    terminates_revision integer,
    created_by uuid not null references gba.users (id),
    created_at timestamptz not null default now(),
    primary key (tenant_id, agreement_id, revision),
    foreign key (tenant_id, agreement_id) references gba.agreements (tenant_id, id),
    constraint agreement_versions_document_fk
        foreign key (tenant_id, document_id, document_revision)
        references gba.document_versions (tenant_id, document_id, revision),
    constraint agreement_versions_terminates_fk
        foreign key (tenant_id, agreement_id, terminates_revision)
        references gba.agreement_versions (tenant_id, agreement_id, revision),
    constraint agreement_versions_document_pair
        check ((document_id is null) = (document_revision is null)),
    constraint agreement_versions_effective
        check (effective_from is null or effective_until is null
               or effective_until >= effective_from),
    -- A draft carries no signature; agreed and terminated versions are attested.
    constraint agreement_versions_state_fields check (
        case state
            when 'draft' then signed_on is null and attestation is null
                and terminated_on is null and terminates_revision is null
            when 'agreed' then signed_on is not null and attestation is not null
                and terminated_on is null and terminates_revision is null
            else signed_on is not null and attestation is not null
                and terminated_on is not null and terminated_on >= signed_on
                and terminates_revision is not null and terminates_revision < revision
        end
    )
);

alter table gba.agreements enable row level security;
alter table gba.agreements force row level security;
alter table gba.agreement_versions enable row level security;
alter table gba.agreement_versions force row level security;

create policy agreements_tenant_isolation on gba.agreements
    using (tenant_id = gba.current_tenant_id())
    with check (tenant_id = gba.current_tenant_id());
grant select on gba.agreements to gba_runtime;
grant insert (tenant_id, id, counterparty_id, legal_entity_id, created_by)
    on gba.agreements to gba_runtime;

create policy agreement_versions_tenant_isolation on gba.agreement_versions
    using (tenant_id = gba.current_tenant_id())
    with check (tenant_id = gba.current_tenant_id());
grant select on gba.agreement_versions to gba_runtime;
grant insert (tenant_id, agreement_id, revision, state, title, number, summary,
              effective_from, effective_until, signed_on, attestation, document_id,
              document_revision, terminated_on, terminates_revision, created_by)
    on gba.agreement_versions to gba_runtime;

create function gba.reject_agreement_mutation() returns trigger language plpgsql as $$
begin
    raise exception using errcode = 'check_violation',
        message = 'agreements and their versions are kept unchanged';
end;
$$;
revoke all on function gba.reject_agreement_mutation() from public;
create trigger agreements_immutable before update or delete on gba.agreements
    for each row execute function gba.reject_agreement_mutation();
create trigger agreement_versions_immutable before update or delete on gba.agreement_versions
    for each row execute function gba.reject_agreement_mutation();

-- A new agreement needs an active counterparty card.
create function gba.enforce_agreement() returns trigger
    language plpgsql as $$
begin
    perform pg_catalog.pg_advisory_xact_lock(
        pg_catalog.hashtextextended('gba:counterparties:' || new.tenant_id::text, 0));
    if not exists (
        select 1 from gba.counterparty_versions v
        where v.tenant_id = new.tenant_id and v.counterparty_id = new.counterparty_id
          and v.state = 'active'
          and v.revision = (select max(x.revision) from gba.counterparty_versions x
              where x.tenant_id = v.tenant_id and x.counterparty_id = v.counterparty_id)
    ) then
        raise exception using errcode = 'check_violation',
            message = 'a new agreement requires an active counterparty';
    end if;
    return new;
end;
$$;
revoke all on function gba.enforce_agreement() from public;
create trigger agreements_require_active_counterparty before insert on gba.agreements
    for each row execute function gba.enforce_agreement();

-- A contract is created together with its first version: no invisible empty contract.
create function gba.check_agreement_first_version() returns trigger
    language plpgsql as $$
begin
    if not exists (
        select 1 from gba.agreement_versions v
        where v.tenant_id = new.tenant_id and v.agreement_id = new.id and v.revision = 1
    ) then
        raise exception using errcode = 'check_violation',
            message = 'a contract requires its first version before commit';
    end if;
    return null;
end;
$$;
revoke all on function gba.check_agreement_first_version() from public;
create constraint trigger agreements_first_version_committed
    after insert on gba.agreements deferrable initially deferred
    for each row execute function gba.check_agreement_first_version();

-- Revisions are contiguous and follow the allowed transitions. Drafting and
-- agreeing need an active counterparty; termination is allowed for any card.
-- A termination names the latest agreed revision and repeats its content
-- unchanged, also when an amendment draft (then abandoned) follows it. Signing
-- dates cannot be in the future; termination dates can.
create function gba.enforce_agreement_version() returns trigger
    language plpgsql as $$
declare
    previous gba.agreement_versions%rowtype;
    agreed gba.agreement_versions%rowtype;
    card_active boolean;
    latest_day date := ((pg_catalog.now() at time zone 'UTC') + interval '14 hours')::date;
begin
    perform pg_catalog.pg_advisory_xact_lock(
        pg_catalog.hashtextextended('gba:counterparties:' || new.tenant_id::text, 0));
    select * into previous from gba.agreement_versions v
     where v.tenant_id = new.tenant_id and v.agreement_id = new.agreement_id
     order by v.revision desc limit 1;
    select * into agreed from gba.agreement_versions v
     where v.tenant_id = new.tenant_id and v.agreement_id = new.agreement_id
       and v.state = 'agreed'
     order by v.revision desc limit 1;
    if new.revision <> coalesce(previous.revision, 0) + 1 then
        raise exception using errcode = 'check_violation',
            message = 'an agreement version follows the latest revision';
    end if;
    if not (
        (previous.revision is null and new.state = 'draft')
        or (previous.state = 'draft' and new.state in ('draft', 'agreed'))
        or (previous.state = 'agreed' and new.state in ('draft', 'terminated'))
        or (previous.state = 'draft' and new.state = 'terminated'
            and agreed.revision is not null)
    ) then
        raise exception using errcode = 'check_violation',
            message = 'this agreement state change is not allowed';
    end if;
    if new.signed_on > latest_day then
        raise exception using errcode = 'check_violation',
            message = 'a signing date cannot be in the future';
    end if;
    if new.state = 'agreed' and (
        new.title, new.number, new.summary, new.effective_from, new.effective_until
    ) is distinct from (
        previous.title, previous.number, previous.summary, previous.effective_from,
        previous.effective_until
    ) then
        raise exception using errcode = 'check_violation',
            message = 'an agreement is agreed exactly as drafted';
    end if;
    if new.state = 'terminated' and (
        new.terminates_revision, new.title, new.number, new.summary, new.effective_from,
        new.effective_until, new.signed_on, new.attestation, new.document_id,
        new.document_revision
    ) is distinct from (
        agreed.revision, agreed.title, agreed.number, agreed.summary, agreed.effective_from,
        agreed.effective_until, agreed.signed_on, agreed.attestation, agreed.document_id,
        agreed.document_revision
    ) then
        raise exception using errcode = 'check_violation',
            message = 'a termination repeats the latest agreed version unchanged';
    end if;
    if new.state <> 'terminated' then
        select v.state = 'active' into card_active
          from gba.agreements a
          join gba.counterparty_versions v
            on v.tenant_id = a.tenant_id and v.counterparty_id = a.counterparty_id
         where a.tenant_id = new.tenant_id and a.id = new.agreement_id
         order by v.revision desc limit 1;
        if not coalesce(card_active, false) then
            raise exception using errcode = 'check_violation',
                message = 'drafting or agreeing requires an active counterparty';
        end if;
    end if;
    return new;
end;
$$;
revoke all on function gba.enforce_agreement_version() from public;
create trigger agreement_versions_next_revision before insert on gba.agreement_versions
    for each row execute function gba.enforce_agreement_version();

create trigger agreements_require_module before insert on gba.agreements
    for each row execute function gba.require_enabled_module('counterparties');
create trigger agreement_versions_require_module before insert on gba.agreement_versions
    for each row execute function gba.require_enabled_module('counterparties');

-- Agreement branch scope: reusable separately when restoring a damaged boundary in tests.
create policy agreements_unrestricted_scope on gba.agreements
    as restrictive to gba_runtime
    using (gba.current_location_id() is null) with check (gba.current_location_id() is null);
create policy agreement_versions_unrestricted_scope on gba.agreement_versions
    as restrictive to gba_runtime
    using (gba.current_location_id() is null) with check (gba.current_location_id() is null);
