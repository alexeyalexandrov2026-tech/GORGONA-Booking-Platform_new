-- PROPERTY-01 5a: maintenance requests, lifecycle approvals and separate FIN-03 obligations.
-- docs/plan/PACKAGE_PROPERTY01_MAINTENANCE_DESIGN_2026-11-20.md.
-- Invoker rights only. All writes on an object serialize via gba.lock_property_object.
create table gba.property_maintenance_requests (
    tenant_id uuid not null,
    id uuid not null,
    object_id uuid not null,
    location_id uuid not null,
    object_kind text not null,
    lease_id uuid,
    category text not null check (
        category in ('plumbing', 'electrical', 'hvac', 'structural', 'appliance', 'general')
    ),
    priority text not null check (priority in ('emergency', 'urgent', 'routine')),
    title text not null check (length(btrim(title)) between 1 and 200 and title !~ '[[:cntrl:]]'),
    description text not null check (
        length(btrim(description)) between 1 and 4000
        and description !~ E'[\\x01-\\x08\\x0b-\\x1f\\x7f]'
    ),
    revision integer not null default 1 check (revision > 0),
    state text not null default 'open' check (
        state in ('open', 'approved', 'assigned', 'completed', 'cancelled')
    ),
    approved_limit_minor bigint check (
        approved_limit_minor is null
        or (approved_limit_minor > 0 and approved_limit_minor < 1000000000000)
    ),
    currency text references gba.currencies (code),
    contractor_id uuid,
    recorded_by uuid not null references gba.users (id),
    recorded_at timestamptz not null default clock_timestamp(),
    primary key (tenant_id, id),
    foreign key (tenant_id, object_id, location_id, object_kind)
        references gba.property_objects (tenant_id, id, location_id, kind),
    constraint property_maintenance_requests_lease_fk
        foreign key (tenant_id, lease_id) references gba.property_leases (tenant_id, id),
    constraint property_maintenance_requests_contractor_fk
        foreign key (tenant_id, contractor_id) references gba.counterparties (tenant_id, id),
    constraint property_maintenance_requests_state_fields check (
        (state = 'open' and revision = 1 and approved_limit_minor is null
            and currency is null and contractor_id is null)
        or (state = 'approved' and revision > 1 and approved_limit_minor is not null
            and currency is not null and contractor_id is null)
        or (state in ('assigned', 'completed') and revision > 1 and approved_limit_minor is not null
            and currency is not null and contractor_id is not null)
        or (state = 'cancelled' and revision > 1
            and (approved_limit_minor is null) = (currency is null)
            and (contractor_id is null or approved_limit_minor is not null))
    )
);
create index property_maintenance_requests_location_id_index
    on gba.property_maintenance_requests (tenant_id, location_id, id);
create index property_maintenance_requests_object_id_index
    on gba.property_maintenance_requests (tenant_id, object_id, id);

create table gba.property_maintenance_events (
    tenant_id uuid not null,
    request_id uuid not null,
    revision integer not null check (revision > 1),
    action text not null check (action in ('approve', 'assign', 'complete', 'cancel')),
    approved_limit_minor bigint check (
        approved_limit_minor is null
        or (approved_limit_minor > 0 and approved_limit_minor < 1000000000000)
    ),
    currency text references gba.currencies (code),
    contractor_id uuid,
    note text check (
        note is null
        or (length(btrim(note)) between 1 and 2000 and note !~ E'[\\x01-\\x08\\x0b-\\x1f\\x7f]')
    ),
    recorded_by uuid not null references gba.users (id),
    recorded_at timestamptz not null default clock_timestamp(),
    creation_xid xid8 not null default pg_current_xact_id(),
    primary key (tenant_id, request_id, revision),
    foreign key (tenant_id, request_id)
        references gba.property_maintenance_requests (tenant_id, id),
    constraint property_maintenance_events_contractor_fk
        foreign key (tenant_id, contractor_id) references gba.counterparties (tenant_id, id),
    constraint property_maintenance_events_action_fields check (
        (action = 'approve' and approved_limit_minor is not null and currency is not null
            and contractor_id is null)
        or (action = 'assign' and contractor_id is not null
            and approved_limit_minor is null and currency is null)
        or (action in ('complete', 'cancel')
            and approved_limit_minor is null and currency is null and contractor_id is null)
    )
);

create table gba.property_maintenance_obligations (
    tenant_id uuid not null,
    request_id uuid not null,
    number integer not null check (number > 0),
    book_id uuid not null,
    invoice_document_id uuid not null,
    obligation_id uuid not null,
    amount_minor bigint not null check (amount_minor > 0 and amount_minor < 1000000000000),
    currency text not null references gba.currencies (code),
    note text check (
        note is null
        or (length(btrim(note)) between 1 and 500 and note !~ E'[\\x01-\\x08\\x0b-\\x1f\\x7f]')
    ),
    recorded_by uuid not null references gba.users (id),
    recorded_at timestamptz not null default clock_timestamp(),
    primary key (tenant_id, request_id, number),
    constraint property_maintenance_obligations_unique_invoice
        unique (tenant_id, book_id, invoice_document_id),
    constraint property_maintenance_obligations_unique_obligation
        unique (tenant_id, book_id, obligation_id),
    foreign key (tenant_id, request_id)
        references gba.property_maintenance_requests (tenant_id, id),
    constraint property_maintenance_obligations_document_fk
        foreign key (tenant_id, book_id, invoice_document_id)
        references gba.financial_documents (tenant_id, book_id, id),
    foreign key (tenant_id, book_id, obligation_id)
        references gba.financial_obligations (tenant_id, book_id, id)
);

create function gba.validate_property_maintenance_request() returns trigger language plpgsql as $$
begin
    if pg_catalog.current_setting('transaction_isolation') <> 'read committed' then
        raise exception using errcode = 'serialization_failure',
            message = 'maintenance requests require a read committed transaction';
    end if;
    perform gba.lock_property_object(new.tenant_id, new.object_id);
    select o.location_id, o.kind into new.location_id, new.object_kind
    from gba.property_objects o
    where o.tenant_id = new.tenant_id and o.id = new.object_id;
    if not found then
        raise exception using errcode = 'check_violation',
            constraint = 'property_maintenance_request_object',
            message = 'a maintenance request belongs to an existing property object';
    end if;
    if new.lease_id is not null and not exists (
        select 1 from gba.property_leases l
        where l.tenant_id = new.tenant_id and l.id = new.lease_id
          and l.object_id = new.object_id
    ) then
        raise exception using errcode = 'check_violation',
            constraint = 'property_maintenance_request_lease',
            message = 'a linked lease must belong to the same property object';
    end if;
    return new;
end;
$$;
revoke all on function gba.validate_property_maintenance_request() from public;

create function gba.guard_property_maintenance_request() returns trigger language plpgsql as $$
declare
    ev gba.property_maintenance_events%rowtype;
begin
    if tg_op = 'INSERT' then
        if new.revision <> 1 or new.state <> 'open'
           or new.approved_limit_minor is not null
           or new.currency is not null
           or new.contractor_id is not null then
            raise exception using errcode = 'check_violation',
                message = 'a maintenance request starts open at revision 1';
        end if;
        return new;
    end if;
    if tg_op = 'DELETE' or
       (new.tenant_id, new.id, new.object_id, new.location_id, new.object_kind,
        new.lease_id, new.category, new.priority, new.title, new.description,
        new.recorded_by, new.recorded_at)
        is distinct from
       (old.tenant_id, old.id, old.object_id, old.location_id, old.object_kind,
        old.lease_id, old.category, old.priority, old.title, old.description,
        old.recorded_by, old.recorded_at) then
        raise exception using errcode = 'check_violation',
            message = 'maintenance request identity and description are immutable';
    end if;
    if new.revision::bigint <> old.revision::bigint + 1 then
        raise exception using errcode = 'check_violation',
            message = 'maintenance request revision follows its next event';
    end if;
    select e.* into ev from gba.property_maintenance_events e
    where e.tenant_id = new.tenant_id and e.request_id = new.id
      and e.revision = new.revision and e.creation_xid = pg_current_xact_id();
    if not found then
        raise exception using errcode = 'check_violation',
            message = 'maintenance request state changes only through a recorded event';
    end if;
    if (ev.action = 'approve' and (
            new.state <> 'approved'
            or new.approved_limit_minor is distinct from ev.approved_limit_minor
            or new.currency is distinct from ev.currency
            or new.contractor_id is not null))
       or (ev.action = 'assign' and (
            new.state <> 'assigned'
            or new.approved_limit_minor is distinct from old.approved_limit_minor
            or new.currency is distinct from old.currency
            or new.contractor_id is distinct from ev.contractor_id))
       or (ev.action = 'complete' and (
            new.state <> 'completed'
            or new.approved_limit_minor is distinct from old.approved_limit_minor
            or new.currency is distinct from old.currency
            or new.contractor_id is distinct from old.contractor_id))
       or (ev.action = 'cancel' and (
            new.state <> 'cancelled'
            or new.approved_limit_minor is distinct from old.approved_limit_minor
            or new.currency is distinct from old.currency
            or new.contractor_id is distinct from old.contractor_id)) then
        raise exception using errcode = 'check_violation',
            message = 'maintenance request state must match its recorded event';
    end if;
    return new;
end;
$$;
revoke all on function gba.guard_property_maintenance_request() from public;

-- Alphabetical order: guard -> lock_validate -> require_module (object lock precedes config lock).
create trigger property_maintenance_requests_guard
    before insert or update or delete on gba.property_maintenance_requests
    for each row execute function gba.guard_property_maintenance_request();
create trigger property_maintenance_requests_lock_validate
    before insert on gba.property_maintenance_requests
    for each row execute function gba.validate_property_maintenance_request();
create trigger property_maintenance_requests_require_module
    before insert on gba.property_maintenance_requests
    for each row execute function gba.require_enabled_module('property');

create function gba.validate_property_maintenance_event() returns trigger language plpgsql as $$
declare
    req gba.property_maintenance_requests%rowtype;
begin
    if pg_catalog.current_setting('transaction_isolation') <> 'read committed' then
        raise exception using errcode = 'serialization_failure',
            message = 'maintenance events require a read committed transaction';
    end if;
    select r.* into req from gba.property_maintenance_requests r
    where r.tenant_id = new.tenant_id and r.id = new.request_id;
    if not found then
        raise exception using errcode = 'check_violation',
            constraint = 'property_maintenance_event_request',
            message = 'a maintenance event requires an existing request';
    end if;
    perform gba.lock_property_object(new.tenant_id, req.object_id);
    select r.* into req from gba.property_maintenance_requests r
    where r.tenant_id = new.tenant_id and r.id = new.request_id;

    if new.action in ('approve', 'assign') then
        perform pg_catalog.pg_advisory_xact_lock_shared(
            pg_catalog.hashtextextended('gba:business-configuration:' || new.tenant_id::text, 0));
        if not exists (
            select 1 from gba.business_module_states s
            where s.tenant_id = new.tenant_id and s.module_id = 'property' and s.enabled
        ) then
            raise exception using errcode = 'GBM01',
                message = 'the property module is disabled for this business';
        end if;
    end if;

    if new.revision::bigint <> req.revision::bigint + 1 then
        raise exception using errcode = 'check_violation',
            constraint = 'property_maintenance_event_sequence',
            message = 'a maintenance event follows the current revision';
    end if;

    if new.action = 'approve' then
        if req.state <> 'open' then
            raise exception using errcode = 'check_violation',
                constraint = 'property_maintenance_event_state',
                message = 'only an open maintenance request can be approved';
        end if;
    elsif new.action = 'assign' then
        if req.state not in ('approved', 'assigned') then
            raise exception using errcode = 'check_violation',
                constraint = 'property_maintenance_event_state',
                message = 'a maintenance request must be approved before contractor assignment';
        end if;
        if req.contractor_id is not null
           and new.contractor_id is distinct from req.contractor_id
           and exists (
               select 1 from gba.property_maintenance_obligations o
               where o.tenant_id = req.tenant_id and o.request_id = req.id
           ) then
            raise exception using errcode = 'check_violation',
                constraint = 'property_maintenance_assign_has_obligations',
                message = 'cannot change contractor after work obligations are linked';
        end if;
    elsif new.action = 'complete' then
        if req.state <> 'assigned' then
            raise exception using errcode = 'check_violation',
                constraint = 'property_maintenance_event_state',
                message = 'only an assigned maintenance request can be completed';
        end if;
    elsif new.action = 'cancel' then
        if req.state not in ('open', 'approved', 'assigned') then
            raise exception using errcode = 'check_violation',
                constraint = 'property_maintenance_event_state',
                message = 'a completed or already cancelled maintenance request cannot be cancelled';
        end if;
        if exists (
            select 1 from gba.property_maintenance_obligations o
            where o.tenant_id = req.tenant_id and o.request_id = req.id
        ) then
            raise exception using errcode = 'check_violation',
                constraint = 'property_maintenance_cancel_has_obligations',
                message = 'cannot cancel a maintenance request that has linked work obligations';
        end if;
    end if;
    return new;
end;
$$;
revoke all on function gba.validate_property_maintenance_event() from public;

create function gba.apply_property_maintenance_event() returns trigger language plpgsql as $$
begin
    update gba.property_maintenance_requests
    set revision = new.revision,
        state = case new.action
            when 'approve' then 'approved'
            when 'assign' then 'assigned'
            when 'complete' then 'completed'
            when 'cancel' then 'cancelled'
        end,
        approved_limit_minor = case when new.action = 'approve'
            then new.approved_limit_minor else approved_limit_minor end,
        currency = case when new.action = 'approve'
            then new.currency else currency end,
        contractor_id = case when new.action = 'assign'
            then new.contractor_id else contractor_id end
    where tenant_id = new.tenant_id and id = new.request_id;
    if not found then
        raise exception using errcode = 'check_violation',
            message = 'a recorded maintenance event must advance its request';
    end if;
    return null;
end;
$$;
revoke all on function gba.apply_property_maintenance_event() from public;

create trigger property_maintenance_events_validate
    before insert on gba.property_maintenance_events
    for each row execute function gba.validate_property_maintenance_event();
create trigger property_maintenance_events_apply
    after insert on gba.property_maintenance_events
    for each row execute function gba.apply_property_maintenance_event();
create trigger property_maintenance_events_immutable
    before update or delete on gba.property_maintenance_events
    for each row execute function gba.reject_agreement_mutation();

create function gba.validate_property_maintenance_obligation() returns trigger language plpgsql as $$
declare
    req gba.property_maintenance_requests%rowtype;
    inv record;
    linked_total bigint;
begin
    if pg_catalog.current_setting('transaction_isolation') <> 'read committed' then
        raise exception using errcode = 'serialization_failure',
            message = 'maintenance obligations require a read committed transaction';
    end if;
    select r.* into req from gba.property_maintenance_requests r
    where r.tenant_id = new.tenant_id and r.id = new.request_id;
    if not found then
        raise exception using errcode = 'check_violation',
            constraint = 'property_maintenance_obligation_request',
            message = 'a maintenance obligation belongs to an existing request';
    end if;
    perform gba.lock_property_object(new.tenant_id, req.object_id);
    select r.* into req from gba.property_maintenance_requests r
    where r.tenant_id = new.tenant_id and r.id = new.request_id;

    if req.state not in ('assigned', 'completed')
       or req.contractor_id is null
       or req.approved_limit_minor is null
       or req.currency is null then
        raise exception using errcode = 'check_violation',
            constraint = 'property_maintenance_obligation_state',
            message = 'a work obligation requires an approved and assigned maintenance request';
    end if;

    if new.number <> 1 + coalesce((
        select max(o.number) from gba.property_maintenance_obligations o
        where o.tenant_id = new.tenant_id and o.request_id = new.request_id
    ), 0) then
        raise exception using errcode = 'check_violation',
            constraint = 'property_maintenance_obligation_sequence',
            message = 'maintenance obligations are numbered 1, 2, 3 per request';
    end if;

    select v.obligation_id, v.principal_minor, v.currency into inv
    from gba.financial_documents d
    join gba.financial_document_versions v
      on v.tenant_id = d.tenant_id and v.book_id = d.book_id and v.document_id = d.id
    where d.tenant_id = new.tenant_id and d.book_id = new.book_id
      and d.id = new.invoice_document_id and d.kind = 'invoice'
      and v.revision = (
          select max(x.revision) from gba.financial_document_versions x
          where x.tenant_id = d.tenant_id and x.book_id = d.book_id and x.document_id = d.id
      )
      and v.state = 'issued' and v.obligation_id is not null
      and v.direction = 'payable'
      and v.counterparty_id = req.contractor_id
      and v.currency = req.currency;
    if not found then
        raise exception using errcode = 'check_violation',
            constraint = 'property_maintenance_obligation_document',
            message = 'a maintenance obligation names an issued payable invoice for the assigned contractor in the approved currency';
    end if;

    new.obligation_id := inv.obligation_id;
    new.amount_minor := inv.principal_minor;
    new.currency := inv.currency;

    select coalesce(sum(o.amount_minor), 0) into linked_total
    from gba.property_maintenance_obligations o
    where o.tenant_id = new.tenant_id and o.request_id = new.request_id;
    if linked_total + new.amount_minor > req.approved_limit_minor then
        raise exception using errcode = 'check_violation',
            constraint = 'property_maintenance_obligation_limit',
            message = 'linked maintenance obligations cannot exceed the approved limit';
    end if;
    return new;
end;
$$;
revoke all on function gba.validate_property_maintenance_obligation() from public;

-- Alphabetical order: immutable / lock_validate precede require_module.
create trigger property_maintenance_obligations_immutable
    before update or delete on gba.property_maintenance_obligations
    for each row execute function gba.reject_agreement_mutation();
create trigger property_maintenance_obligations_lock_validate
    before insert on gba.property_maintenance_obligations
    for each row execute function gba.validate_property_maintenance_obligation();
create trigger property_maintenance_obligations_require_module
    before insert on gba.property_maintenance_obligations
    for each row execute function gba.require_enabled_module('property');

alter table gba.property_maintenance_requests enable row level security;
alter table gba.property_maintenance_requests force row level security;
alter table gba.property_maintenance_events enable row level security;
alter table gba.property_maintenance_events force row level security;
alter table gba.property_maintenance_obligations enable row level security;
alter table gba.property_maintenance_obligations force row level security;

create policy property_maintenance_requests_tenant_isolation on gba.property_maintenance_requests
    using (tenant_id = gba.current_tenant_id()) with check (tenant_id = gba.current_tenant_id());
create policy property_maintenance_events_tenant_isolation on gba.property_maintenance_events
    using (tenant_id = gba.current_tenant_id()) with check (tenant_id = gba.current_tenant_id());
create policy property_maintenance_obligations_tenant_isolation
    on gba.property_maintenance_obligations
    using (tenant_id = gba.current_tenant_id()) with check (tenant_id = gba.current_tenant_id());

grant select on gba.property_maintenance_requests,
                gba.property_maintenance_events,
                gba.property_maintenance_obligations
    to gba_runtime;
grant insert (tenant_id, id, object_id, lease_id, category, priority, title, description, recorded_by)
    on gba.property_maintenance_requests to gba_runtime;
grant update (revision, state, approved_limit_minor, currency, contractor_id)
    on gba.property_maintenance_requests to gba_runtime;
grant insert (tenant_id, request_id, revision, action, approved_limit_minor, currency,
              contractor_id, note, recorded_by)
    on gba.property_maintenance_events to gba_runtime;
grant insert (tenant_id, request_id, number, book_id, invoice_document_id, note, recorded_by)
    on gba.property_maintenance_obligations to gba_runtime;

-- Property maintenance branch scope:
create policy property_maintenance_requests_location_scope on gba.property_maintenance_requests
    as restrictive to gba_runtime
    using (gba.current_location_id() is null or location_id = gba.current_location_id())
    with check (gba.current_location_id() is null or location_id = gba.current_location_id());
create policy property_maintenance_requests_unrestricted_insert on gba.property_maintenance_requests
    as restrictive for insert to gba_runtime with check (gba.current_location_id() is null);
create policy property_maintenance_requests_unrestricted_update on gba.property_maintenance_requests
    as restrictive for update to gba_runtime
    using (gba.current_location_id() is null) with check (gba.current_location_id() is null);
create policy property_maintenance_events_unrestricted_scope on gba.property_maintenance_events
    as restrictive to gba_runtime
    using (gba.current_location_id() is null) with check (gba.current_location_id() is null);
create policy property_maintenance_obligations_unrestricted_scope
    on gba.property_maintenance_obligations
    as restrictive to gba_runtime
    using (gba.current_location_id() is null) with check (gba.current_location_id() is null);
