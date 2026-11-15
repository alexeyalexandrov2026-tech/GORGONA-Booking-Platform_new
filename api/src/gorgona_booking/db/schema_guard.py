"""Fail closed on missing or altered PostgreSQL 18 access definitions.

Covers the branch boundary (location policies and company-only scope policies) and
the booking-module trigger of ADR-0019, which refuses new bookings when a published
configuration disables booking.
"""

from gorgona_booking.db.financial_guard import (
    FINANCIAL_BOUNDARY,
    FINANCIAL_PARAMETERS,
    FINANCIAL_TABLES,
)
from gorgona_booking.db.ledger_guard import LEDGER_BOUNDARY, LEDGER_PARAMETERS
from gorgona_booking.db.pool import RuntimeConnection
from gorgona_booking.errors import DatabaseUnavailableError

_NO_LOCATION = "(gba.current_location_id() IS NULL)"
_FUNCTION_SOURCE = "select nullif(pg_catalog.current_setting('gba.location_id', true), '')::uuid"
# Approved body of gba.enforce_booking_module(), compared without whitespace.
_BOOKING_MODULE_SOURCE = """
begin
    perform pg_catalog.pg_advisory_xact_lock_shared(
        pg_catalog.hashtextextended('gba:business-configuration:' || new.tenant_id::text, 0));
    if exists (
        select 1 from gba.business_module_states s
        where s.tenant_id = new.tenant_id and s.module_id = 'booking_resources'
          and not s.enabled
    ) then
        raise exception using errcode = 'GBM01',
            message = 'the booking module is disabled for this business';
    end if;
    return new;
end;
"""

_OPTIONAL_MODULE_SOURCE = """
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
"""
# Approved bodies of the shared-occupancy triggers (ADR-0022), compared without
# whitespace: a disabled or rewritten mirror would let two modules double-book.
_OCCUPANCY_GUARD_SOURCE = """
begin
    if tg_op = 'DELETE' then
        raise exception using errcode = 'check_violation',
            message = 'resource allocations are kept';
    end if;
    if tg_op = 'UPDATE' then
        if (new.tenant_id, new.id, new.resource_id, new.source_kind, new.source_id,
            new.during, new.created_at)
           is distinct from (old.tenant_id, old.id, old.resource_id, old.source_kind,
                             old.source_id, old.during, old.created_at) then
            raise exception using errcode = 'check_violation',
                message = 'an allocation keeps its resource, source and interval';
        end if;
        if new.state is distinct from old.state and not (
            (old.state = 'held' and new.state in ('confirmed', 'released'))
            or (old.state = 'confirmed' and new.state = 'released')
        ) then
            raise exception using errcode = 'check_violation',
                message = 'this allocation state change is not allowed';
        end if;
        new.updated_at := pg_catalog.now();
    end if;
    if new.source_kind = 'booking' and not exists (
        select 1 from gba.booking_allocations a
        where a.tenant_id = new.tenant_id and a.booking_id = new.source_id
          and a.resource_id = new.resource_id and a.during = new.during
          and gba.booking_occupancy_state(a.booking_status) = new.state
    ) then
        raise exception using errcode = 'check_violation',
            message = 'a booking allocation follows its booking';
    end if;
    if new.source_kind = 'reservation' then
        if tg_op = 'INSERT' and not exists (
            select 1 from gba.resource_reservations v
            join gba.resources r
              on r.tenant_id = v.tenant_id and r.location_id = v.location_id
            where v.tenant_id = new.tenant_id and v.id = new.source_id
              and v.status = 'active' and new.state = 'confirmed'
              -- Only in the transaction that created the reservation.
              and v.created_at = pg_catalog.now()
              and new.during = tstzrange(v.starts_at, v.ends_at, '[)')
              and r.id = new.resource_id and r.is_active
        ) then
            raise exception using errcode = 'check_violation',
                message = 'a reservation allocation follows its active reservation';
        end if;
        if tg_op = 'UPDATE' and new.state = 'released' and not exists (
            select 1 from gba.resource_reservations v
            where v.tenant_id = new.tenant_id and v.id = new.source_id
              and v.status = 'cancelled'
        ) then
            raise exception using errcode = 'check_violation',
                message = 'a reservation allocation is released by its cancellation';
        end if;
        -- Mirrored bookings are decided by the exclusion constraint; this only
        -- covers booking allocations a company has not copied yet.
        if tg_op = 'INSERT' and exists (
            select 1 from gba.booking_allocations a
            where a.tenant_id = new.tenant_id and a.resource_id = new.resource_id
              and a.booking_status in ('HOLD', 'CONFIRMED') and a.during && new.during
              and not exists (
                  select 1 from gba.resource_allocations c
                  where c.tenant_id = a.tenant_id and c.source_kind = 'booking'
                    and c.source_id = a.booking_id and c.resource_id = a.resource_id)
        ) then
            raise exception using errcode = 'exclusion_violation',
                constraint = 'resource_allocations_no_overlap',
                message = 'the resource is booked in this interval';
        end if;
    end if;

    if exists (select 1 from gba.resources r where r.tenant_id=new.tenant_id
        and r.id=new.resource_id and (r.kind='staff') <> (new.source_kind='shift')) then
        raise exception using errcode='23514', message='staff occupancy is only for shifts';
    end if;
    if new.source_kind='shift' then
        if tg_op='INSERT' and not exists (
            select 1 from gba.shift_assignments a join gba.work_shift_versions v
              on v.tenant_id=a.tenant_id and v.shift_id=a.shift_id and v.revision=a.shift_revision
              join gba.staff_profiles p on p.tenant_id=a.tenant_id and p.id=a.profile_id
             where a.tenant_id=new.tenant_id and a.id=new.source_id
               and p.resource_id=new.resource_id and v.profile_id=p.id and v.status='published'
               and a.creation_xid=pg_current_xact_id() and v.creation_xid=a.creation_xid
               and new.during=tstzrange(v.starts_at,v.ends_at,'[)') and new.state='confirmed'
        ) then
            raise exception using errcode='23514',
                message='a shift allocation follows its exact assignment';
        end if;
        if tg_op='UPDATE' and new.state='released' and not exists (
            select 1 from gba.shift_assignments a join gba.work_shift_versions v
              on v.tenant_id=a.tenant_id and v.shift_id=a.shift_id and v.revision>a.shift_revision
             where a.tenant_id=new.tenant_id and a.id=new.source_id
        ) then
            raise exception using errcode='23514',
                message='a shift allocation is released by a new version';
        end if;
    end if;
    if exists (select 1 from gba.resources r where r.tenant_id = new.tenant_id
        and r.id = new.resource_id
        and (r.kind in ('driver', 'truck', 'trailer'))
            <> (new.source_kind = 'trip_assignment')) then
        raise exception using errcode = '23514',
            message = 'transport occupancy is only for trip assignments';
    end if;
    if new.source_kind = 'trip_assignment' then
        if tg_op = 'INSERT' and not exists (
            select 1 from gba.transport_assignments a
             where a.tenant_id = new.tenant_id and a.id = new.source_id
               and a.resource_id = new.resource_id and new.state = 'confirmed'
               and (
                   (a.creation_xid = pg_current_xact_id()
                    and new.during = tstzrange(
                        a.starts_at, upper(gba.transport_trip_span(a.tenant_id, a.trip_id)), '[)'))
                   or exists (
                       select 1 from gba.transport_assignment_ends e
                        where e.tenant_id = a.tenant_id and e.assignment_id = a.id
                          and e.creation_xid = pg_current_xact_id()
                          and new.during = tstzrange(a.starts_at, e.ends_at, '[)'))
               )
        ) then
            raise exception using errcode = '23514',
                message = 'a trip allocation follows its exact assignment';
        end if;
        if tg_op = 'UPDATE' and new.state = 'released' and not exists (
            select 1 from gba.transport_assignment_ends e
             where e.tenant_id = new.tenant_id and e.assignment_id = new.source_id
               and e.creation_xid = pg_current_xact_id()
        ) then
            raise exception using errcode = '23514',
                message = 'a trip allocation is released by its end';
        end if;
    end if;
    if exists (select 1 from gba.resources r where r.tenant_id = new.tenant_id
        and r.id = new.resource_id
        and (r.kind = 'rental_unit')
            <> (new.source_kind in ('rental_assignment', 'rental_block'))) then
        raise exception using errcode = '23514',
            message = 'rental occupancy is only for rental assignments and blocks';
    end if;
    if new.source_kind = 'rental_assignment' then
        if tg_op = 'INSERT' and not exists (
            select 1 from gba.rental_assignments a
              join gba.rental_units u on u.tenant_id = a.tenant_id and u.id = a.unit_id
             where a.tenant_id = new.tenant_id and a.id = new.source_id
               and u.resource_id = new.resource_id and new.state = 'confirmed'
               and a.creation_xid = pg_current_xact_id()
               and new.during = tstzrange(a.starts_at, a.ends_at, '[)')
        ) then
            raise exception using errcode = '23514',
                message = 'a rental allocation follows its exact assignment';
        end if;
        if tg_op = 'UPDATE' and new.state = 'released' and not exists (
            select 1 from gba.rental_assignment_releases l
             where l.tenant_id = new.tenant_id and l.assignment_id = new.source_id
               and l.creation_xid = pg_current_xact_id()
        ) then
            raise exception using errcode = '23514',
                message = 'a rental allocation is released by its release';
        end if;
    end if;
    if new.source_kind = 'rental_block' then
        if tg_op = 'INSERT' and not exists (
            select 1 from gba.rental_unit_blocks b
              join gba.rental_units u on u.tenant_id = b.tenant_id and u.id = b.unit_id
             where b.tenant_id = new.tenant_id and b.id = new.source_id
               and u.resource_id = new.resource_id and new.state = 'confirmed'
               and b.creation_xid = pg_current_xact_id()
               and new.during = tstzrange(b.starts_at, b.ends_at, '[)')
        ) then
            raise exception using errcode = '23514',
                message = 'a rental block hold follows its exact block';
        end if;
        if tg_op = 'UPDATE' and new.state = 'released' and not exists (
            select 1 from gba.rental_unit_block_releases l
             where l.tenant_id = new.tenant_id and l.block_id = new.source_id
               and l.creation_xid = pg_current_xact_id()
        ) then
            raise exception using errcode = '23514',
                message = 'a rental block hold is released by its release';
        end if;
    end if;
    if exists (
        select 1 from gba.resources r where r.tenant_id = new.tenant_id
          and r.id = new.resource_id and r.kind = 'property_object'
          and new.source_kind <> 'property_showing'
    ) then
        raise exception using errcode = '23514',
            message = 'a property object resource is reserved only for showings';
    end if;
    if new.source_kind = 'property_showing' then
        if tg_op = 'INSERT' and not exists (
            select 1 from gba.property_showings s join gba.resources r on r.tenant_id = s.tenant_id
             where s.tenant_id = new.tenant_id and s.id = new.source_id
               and r.id = new.resource_id and r.location_id = s.location_id and r.is_active
               and ((s.object_resource_id = r.id and r.kind = 'property_object')
                    or (s.host_resource_id = r.id and r.kind = 'artist'))
               and s.creation_xid = pg_current_xact_id()
               and new.during = tstzrange(s.starts_at, s.ends_at, '[)') and new.state = 'confirmed'
        ) then
            raise exception using errcode = '23514', message = 'an allocation follows its showing';
        end if;
        if tg_op = 'UPDATE' and new.state = 'released' and not exists (
            select 1 from gba.property_showing_cancellations c
             where c.tenant_id = new.tenant_id and c.showing_id = new.source_id
               and c.creation_xid = pg_current_xact_id()
        ) then
            raise exception using errcode = '23514',
                message = 'a showing release requires cancellation';
        end if;
        if tg_op = 'INSERT' and exists (
            select 1 from gba.booking_allocations a
             where a.tenant_id = new.tenant_id and a.resource_id = new.resource_id
               and a.booking_status in ('HOLD', 'CONFIRMED') and a.during && new.during
        ) then
            raise exception using errcode = 'exclusion_violation',
                constraint = 'resource_allocations_no_overlap',
                message = 'the resource is booked in this interval';
        end if;
    end if;
    return new;
end;
"""
_RESERVATION_GUARD_SOURCE = """
begin
    if tg_op = 'DELETE' then
        raise exception using errcode = 'check_violation',
            message = 'resource reservations are kept';
    end if;
    if tg_op = 'INSERT' then
        if new.status <> 'active' then
            raise exception using errcode = 'check_violation',
                message = 'a reservation is created active';
        end if;
        return new;
    end if;
    if (new.tenant_id, new.id, new.location_id, new.starts_at, new.ends_at, new.purpose,
        new.resource_count, new.created_by, new.created_at)
       is distinct from (old.tenant_id, old.id, old.location_id, old.starts_at, old.ends_at,
                         old.purpose, old.resource_count, old.created_by, old.created_at)
       or not (old.status = 'active' and new.status = 'cancelled') then
        raise exception using errcode = 'check_violation',
            message = 'an active reservation can only be cancelled';
    end if;
    new.cancelled_at := pg_catalog.now();
    return new;
end;
"""
_RESERVATION_RELEASE_SOURCE = """
declare
    released integer;
begin
    if new.status = 'cancelled' then
        update gba.resource_allocations r set state = 'released'
         where r.tenant_id = new.tenant_id and r.source_kind = 'reservation'
           and r.source_id = new.id and r.state <> 'released';
        get diagnostics released = row_count;
        -- Row security hides a resource moved to another branch: never leave it
        -- reserved silently; a company-wide session can cancel.
        if released <> new.resource_count then
            raise exception using errcode = 'check_violation',
                message = 'a reserved resource is outside the current branch';
        end if;
    end if;
    return null;
end;
"""
_RESERVATION_ALLOCATED_SOURCE = """
begin
    if (
        select count(*) from gba.resource_allocations r
        where r.tenant_id = new.tenant_id and r.source_kind = 'reservation'
          and r.source_id = new.id
    ) <> new.resource_count then
        raise exception using errcode = 'check_violation',
            message = 'a reservation requires its resources before commit';
    end if;
    return null;
end;
"""
# L2a (0067): the mirror matches the interval too.
_OCCUPANCY_MIRROR_SOURCE = """
begin
    if tg_op = 'INSERT' then
        insert into gba.resource_allocations (tenant_id, resource_id, source_kind, source_id,
                                              during, state)
        values (new.tenant_id, new.resource_id, 'booking', new.booking_id, new.during,
                gba.booking_occupancy_state(new.booking_status));
    elsif new.booking_status is distinct from old.booking_status then
        update gba.resource_allocations r
           set state = gba.booking_occupancy_state(new.booking_status)
         where r.tenant_id = new.tenant_id and r.source_kind = 'booking'
           and r.source_id = new.booking_id and r.resource_id = new.resource_id
           and r.during = new.during
           and r.state <> gba.booking_occupancy_state(new.booking_status);
        -- Nothing to update means an allocation from before 0018; the backfill copies
        -- it later with the booking's state. The status cascade runs this trigger in
        -- the foreign-key context, so branch row security never hides the row.
    end if;
    return null;
end;
"""
_OCCUPANCY_STATE_SOURCE = """
    select case status when 'HOLD' then 'held' when 'CONFIRMED' then 'confirmed'
                       else 'released' end
"""
_OCCUPANCY_CONSTRAINT = (
    "EXCLUDE USING gist (tenant_id WITH =, resource_id WITH =, during WITH &&) "
    "WHERE ((state = ANY (ARRAY['held'::text, 'confirmed'::text])))"
)
# (table, trigger, tgtype, function, UPDATE OF columns, approved body) of the shared
# occupancy triggers: row guards (BEFORE INSERT OR UPDATE OR DELETE, 31), the booking
# mirror (AFTER INSERT OR UPDATE OF booking_status, 21), the reservation release
# (AFTER UPDATE OF status, 17) and the booking-module gate on reservations (7).
GUARD_PROPERTY_SHOWING_RESOURCE_SOURCE = """
begin
    if not exists (
        select 1 from gba.resources r
        where r.tenant_id = new.tenant_id and r.id = new.resource_id
          and r.location_id = new.location_id and r.kind = 'property_object' and r.is_active
    ) then
        raise exception using errcode = '23514',
            message = 'a showing object has its branch resource';
    end if;
    return new;
end;
"""

KEEP_PROPERTY_RESOURCE_IDENTITY_SOURCE = """
begin
    if (old.kind = 'property_object' or new.kind = 'property_object') and
       (old.tenant_id, old.id, old.location_id, old.kind, old.is_active) is distinct from
       (new.tenant_id, new.id, new.location_id, new.kind, new.is_active) then
        raise exception using errcode = '23514', message = 'a property resource keeps its identity';
    end if;
    return new;
end;
"""

RELEASE_PROPERTY_SHOWING_SOURCE = """
declare
    released integer;
    expected integer;
begin
    select case when s.host_resource_id is null then 1 else 2 end into strict expected
    from gba.property_showings s where s.tenant_id = new.tenant_id and s.id = new.showing_id;
    update gba.resource_allocations set state = 'released'
    where tenant_id = new.tenant_id and source_kind = 'property_showing'
      and source_id = new.showing_id and state = 'confirmed';
    get diagnostics released = row_count;
    if released <> expected then
        raise exception using errcode = '23514', message = 'cancellation releases all allocations';
    end if;
    return null;
end;
"""

CHECK_PROPERTY_SHOWING_ALLOCATED_SOURCE = """
begin
    if (
        select count(*) from gba.resource_allocations a
        where a.tenant_id = new.tenant_id and a.source_kind = 'property_showing'
          and a.source_id = new.id
    ) <> (case when new.host_resource_id is null then 1 else 2 end) then
        raise exception using errcode = '23514', message = 'a showing requires all its allocations';
    end if;
    return null;
end;
"""

_PROPERTY_LEASE_EXCLUSION = (
    "EXCLUDE USING gist (tenant_id WITH =, object_id WITH =, "
    "daterange(starts_on, ends_on, '[]'::text) WITH &&)"
)
_PROPERTY_LEASE_VALIDATION_SOURCE = """
begin
    -- Advisory locks do not refresh an older REPEATABLE READ/SERIALIZABLE snapshot.
    if pg_catalog.current_setting('transaction_isolation') <> 'read committed' then
        raise exception using errcode = 'serialization_failure',
            message = 'lease registration requires a read committed transaction';
    end if;
    perform pg_catalog.pg_advisory_xact_lock(
        pg_catalog.hashtextextended('gba:counterparties:' || new.tenant_id::text, 0));
    if not exists (
        select 1 from gba.property_objects o
        where o.tenant_id = new.tenant_id and o.id = new.object_id and o.kind = 'unit'
    ) then
        raise exception using errcode = 'check_violation', constraint = 'property_leases_unit',
            message = 'an exclusive lease requires a property unit';
    end if;

    select v.effective_from, v.effective_until into new.starts_on, new.ends_on
    from gba.agreement_versions v
    join gba.document_versions d
      on d.tenant_id = v.tenant_id and d.document_id = v.document_id
     and d.revision = v.document_revision
    where v.tenant_id = new.tenant_id and v.agreement_id = new.agreement_id
      and v.revision = new.agreement_revision and v.state = 'agreed'
      and v.attestation = 'signed_outside_platform'
      and v.signed_on between date '0001-01-01' and date '9999-12-31'
      and v.effective_from >= date '0001-01-01'
      and v.effective_until <= date '9999-12-31'
      and d.category = 'agreement' and not d.archived and d.file_id is not null
      and not exists (
          select 1 from gba.agreement_versions later
          where later.tenant_id = v.tenant_id and later.agreement_id = v.agreement_id
            and later.revision > v.revision and later.state <> 'draft'
      );
    if not found then
        raise exception using errcode = 'check_violation',
            constraint = 'property_leases_signed_source',
            message = 'an exclusive lease requires the current agreed term and its signed file';
    end if;
    return new;
end;
"""
_AGREEMENT_IMMUTABILITY_SOURCE = """
begin
    raise exception using errcode = 'check_violation',
        message = 'agreements and their versions are kept unchanged';
end;
"""

_OCCUPANCY_TRIGGERS = (
    (
        "property_leases",
        "property_leases_validate_input",
        7,
        "gba.validate_property_lease()",
        "",
        _PROPERTY_LEASE_VALIDATION_SOURCE,
    ),
    (
        "property_leases",
        "property_leases_immutable",
        27,
        "gba.reject_agreement_mutation()",
        "",
        _AGREEMENT_IMMUTABILITY_SOURCE,
    ),
    (
        "resource_allocations",
        "resource_allocations_guard",
        31,
        "gba.guard_resource_allocation()",
        "",
        _OCCUPANCY_GUARD_SOURCE,
    ),
    (
        "booking_allocations",
        "booking_allocations_mirror_occupancy",
        21,
        "gba.mirror_booking_allocation()",
        "booking_status",
        _OCCUPANCY_MIRROR_SOURCE,
    ),
    (
        "resource_reservations",
        "resource_reservations_guard",
        31,
        "gba.guard_resource_reservation()",
        "",
        _RESERVATION_GUARD_SOURCE,
    ),
    (
        "resource_reservations",
        "resource_reservations_release",
        17,
        "gba.release_reservation_allocations()",
        "status",
        _RESERVATION_RELEASE_SOURCE,
    ),
    (
        "resource_reservations",
        "resource_reservations_require_booking_module",
        7,
        "gba.enforce_booking_module()",
        "",
        _BOOKING_MODULE_SOURCE,
    ),
    (
        "property_showing_resources",
        "property_showing_resources_guard",
        7,
        "gba.guard_property_showing_resource()",
        "",
        GUARD_PROPERTY_SHOWING_RESOURCE_SOURCE,
    ),
    (
        "resources",
        "resources_keep_property_identity",
        19,
        "gba.keep_property_resource_identity()",
        "",
        KEEP_PROPERTY_RESOURCE_IDENTITY_SOURCE,
    ),
    (
        "property_showing_cancellations",
        "property_showing_cancellations_release",
        5,
        "gba.release_property_showing()",
        "",
        RELEASE_PROPERTY_SHOWING_SOURCE,
    ),
)
_COUNTERPARTY_TABLES = (
    "counterparties",
    "counterparty_versions",
    "counterparty_version_contacts",
    "counterparty_match_decisions",
    "counterparty_booking_links",
    "agreements",
    "agreement_versions",
)
_DOCUMENT_TABLES = (
    "document_files",
    "documents",
    "document_versions",
    "document_counterparty_links",
)
_LEDGER_TABLES = (
    "ledger_books",
    "ledger_book_versions",
    "ledger_accounts",
    "ledger_account_versions",
    "journal_entries",
    "journal_lines",
    "ledger_period_events",
)
_PROPERTY_CATALOG_TABLES = ("property_objects", "property_revisions")
_PROPERTY_LISTING_TABLES = ("property_listings", "property_listing_revisions")
_PROPERTY_SHOWING_TABLES = ("property_showing_resources", "property_showings")
_PROPERTY_BRANCH_TABLES = (
    *_PROPERTY_CATALOG_TABLES,
    *_PROPERTY_LISTING_TABLES,
    *_PROPERTY_SHOWING_TABLES,
)
_PROPERTY_TABLES = (
    *_PROPERTY_BRANCH_TABLES,
    "property_parties",
    "property_showing_cancellations",
    "property_leases",
)
_MODULE_TABLES = (*_COUNTERPARTY_TABLES, *_DOCUMENT_TABLES, *_LEDGER_TABLES)
# (table, trigger, module argument) for every optional-module write gate.
_MODULE_TRIGGERS = (
    *[
        (table, f"{table}_require_module", "property")
        for table in _PROPERTY_TABLES
        if table != "property_showing_cancellations"
    ],
    *[(table, f"{table}_require_module", "counterparties") for table in _COUNTERPARTY_TABLES],
    *[(table, f"{table}_require_module", "documents") for table in _DOCUMENT_TABLES],
    *[(table, f"{table}_require_module", "finance") for table in _LEDGER_TABLES],
    (
        "document_counterparty_links",
        "document_counterparty_links_require_counterparties",
        "counterparties",
    ),
)


def _compact(text: str) -> str:
    return "".join(text.split())


def _parent(table: str, parent: str, alias: str, reference: str) -> str:
    return (
        f"(EXISTS ( SELECT 1 FROM gba.{parent} {alias} "  # noqa: S608 - bound as comparison data
        f"WHERE (({alias}.tenant_id = {table}.tenant_id) "
        f"AND ({alias}.id = {table}.{reference}))))"
    )


def _definition(
    table: str, expression: str, *, command: str = "*"
) -> tuple[str, str, str, str, str]:
    suffix = "location_scope" if command == "*" else "unrestricted_read"
    # PostgreSQL deparses the approved expression. Ignore formatting whitespace,
    # retain parentheses, predicates and SQL case; do not reduce this to names.
    using = _compact(expression)
    return table, f"{table}_{suffix}", command, using, using if command == "*" else ""


def _company_only(table: str, policy: str, command: str) -> tuple[str, str, str, str, str]:
    """Restrictive company-wide scope; an INSERT policy has only a WITH CHECK clause."""
    expression = _compact(_NO_LOCATION)
    return table, policy, command, "" if command == "a" else expression, expression


# (table, policy, command, approved USING, approved WITH CHECK); "" means absent.
_DEFINITIONS = [
    _definition("locations", f"({_NO_LOCATION} OR (id = gba.current_location_id()))"),
    *[
        _definition(table, f"({_NO_LOCATION} OR (location_id = gba.current_location_id()))")
        for table in ("resources", "bookings", "business_hours", "resource_reservations")
    ],
    *[
        _definition(table, f"({_NO_LOCATION} OR {_parent(table, 'resources', 'r', 'resource_id')})")
        for table in ("resource_services", "resource_hours", "resource_blocks")
    ],
    *[
        _definition(table, f"({_NO_LOCATION} OR {_parent(table, 'bookings', 'b', 'booking_id')})")
        for table in ("booking_customers", "booking_events")
    ],
    _definition(
        "booking_allocations",
        f"({_NO_LOCATION} OR ("
        f"{_parent('booking_allocations', 'bookings', 'b', 'booking_id')} AND "
        f"{_parent('booking_allocations', 'resources', 'r', 'resource_id')}))",
    ),
    _definition(
        "resource_allocations",
        f"({_NO_LOCATION} OR {_parent('resource_allocations', 'resources', 'r', 'resource_id')})",
    ),
    _definition("audit_events", _NO_LOCATION, command="r"),
    *[
        _definition(table, f"({_NO_LOCATION} OR (location_id = gba.current_location_id()))")
        for table in _PROPERTY_BRANCH_TABLES
    ],
    *[
        _company_only(table, f"{table}_unrestricted_insert", "a")
        for table in _PROPERTY_BRANCH_TABLES
    ],
    _company_only("property_parties", "property_parties_unrestricted_scope", "*"),
    _company_only("property_leases", "property_leases_unrestricted_scope", "*"),
    _definition(
        "property_showing_cancellations",
        f"({_NO_LOCATION} OR "
        f"{_parent('property_showing_cancellations', 'property_showings', 's', 'showing_id')})",
    ),
    _company_only(
        "property_showing_cancellations", "property_showing_cancellations_unrestricted_insert", "a"
    ),
    *[
        (
            table,
            f"{table}_tenant_isolation",
            "*",
            "(tenant_id=gba.current_tenant_id())",
            "(tenant_id=gba.current_tenant_id())",
        )
        for table in _PROPERTY_TABLES
    ],
    *[
        _company_only(table, f"{table}_unrestricted_scope", "*")
        for table in (
            "business_profile_versions",
            "business_profile_industries",
            "business_profile_formats",
            "salon_fact_confirmations",
            "tenant_embed_origins",
            "invitations",
            "legal_entities",
            "legal_entity_versions",
            "departments",
            "department_versions",
            "delegation_grants",
            "delegation_grant_members",
            "business_groups",
            "business_group_members",
            "business_configuration_versions",
            "business_configuration_modules",
            *_MODULE_TABLES,
            "ledger_command_cancellations",
            *FINANCIAL_TABLES,
        )
    ],
    # Branch sessions read effective module states; only company-wide sessions write them.
    _company_only("business_module_states", "business_module_states_unrestricted_insert", "a"),
    _company_only("business_module_states", "business_module_states_unrestricted_update", "w"),
]

_ACCESS_BOUNDARY = """
with required(table_name, policy_name, command, using_expression, check_expression)
    as (values __VALUES__)
select exists (
    select 1 from pg_catalog.pg_proc
    where oid = pg_catalog.to_regprocedure('gba.current_location_id()')
      and not prosecdef and proconfig is null and pronargs = 0
      and prokind = 'f' and provolatile = 's' and proparallel = 's'
      and prorettype = 'pg_catalog.uuid'::regtype
      and prolang = (select oid from pg_catalog.pg_language where lanname = 'sql')
      and btrim(prosrc, E' \t\r\n') = %s
) and exists (
    -- BEFORE INSERT FOR EACH ROW (tgtype 7), enabled, calling the approved function.
    select 1 from pg_catalog.pg_trigger t
    join pg_catalog.pg_proc f on f.oid = t.tgfoid
    where t.tgrelid = pg_catalog.to_regclass('gba.bookings')
      and t.tgname = 'bookings_require_booking_module'
      and t.tgtype = 7 and t.tgenabled = 'O' and not t.tgisinternal
      and t.tgqual is null and t.tgconstraint = 0
      and t.tgnargs = 0 and pg_catalog.octet_length(t.tgargs) = 0
      and f.oid = pg_catalog.to_regprocedure('gba.enforce_booking_module()')
      and not f.prosecdef and f.proconfig is null
      and f.pronargs = 0 and f.prokind = 'f' and f.provolatile = 'v' and f.proparallel = 'u'
      and f.prorettype = 'pg_catalog.trigger'::regtype
      and f.prolang = (select oid from pg_catalog.pg_language where lanname = 'plpgsql')
      and regexp_replace(f.prosrc, '[[:space:]]', '', 'g') = %s
) and not exists (
    select 1 from required r
    left join pg_catalog.pg_class c on c.oid = pg_catalog.to_regclass('gba.' || r.table_name)
    left join pg_catalog.pg_policy p on p.polrelid = c.oid and p.polname = r.policy_name
    cross join lateral (select r.policy_name = r.table_name || '_tenant_isolation') a(permissive)
    where c.oid is null or not c.relrowsecurity or not c.relforcerowsecurity
       or p.oid is null or p.polpermissive <> a.permissive or p.polcmd::text <> r.command
       or (a.permissive and exists (
           select 1 from pg_catalog.pg_policy other
           where other.polrelid = c.oid and other.polpermissive and other.oid <> p.oid
       ))
       or coalesce(regexp_replace(pg_catalog.pg_get_expr(p.polqual, c.oid),
                                  '[[:space:]]', '', 'g'), '') <> r.using_expression
       or coalesce(regexp_replace(pg_catalog.pg_get_expr(p.polwithcheck, c.oid),
                                  '[[:space:]]', '', 'g'), '') <> r.check_expression
       or not coalesce(case when a.permissive then p.polroles = array[0::oid]
           else p.polroles @> array[(select oid from pg_catalog.pg_roles
                                     where rolname = 'gba_runtime')] end, false)
)
""".replace("__VALUES__", ", ".join("(%s, %s, %s, %s, %s)" for _ in _DEFINITIONS))

# Inspect the body and every trigger argument, not just a familiar object name.
_ACCESS_BOUNDARY += """
and exists (
    select 1 from pg_catalog.pg_proc f
    where f.oid = pg_catalog.to_regprocedure('gba.require_enabled_module()')
      and not f.prosecdef and f.proconfig is null and f.pronargs = 0
      and f.prorettype = 'pg_catalog.trigger'::regtype and f.prokind = 'f'
      and f.provolatile = 'v' and f.proparallel = 'u'
      and f.prolang = (select oid from pg_catalog.pg_language where lanname = 'plpgsql')
      and f.prosrc = %s
) and not exists (
    select 1 from unnest(%s::text[], %s::text[], %s::bytea[])
        required(table_name, trigger_name, arguments)
    left join pg_catalog.pg_trigger t
      on t.tgrelid = pg_catalog.to_regclass('gba.' || required.table_name)
     and t.tgname = required.trigger_name
    where t.oid is null or t.tgtype <> 7 or t.tgenabled <> 'O' or t.tgisinternal
       -- A WHEN clause or constraint trigger could silently skip the gate.
       or t.tgqual is not null or t.tgconstraint <> 0
       or t.tgfoid is distinct from pg_catalog.to_regprocedure('gba.require_enabled_module()')
       or t.tgnargs <> 1 or t.tgargs <> required.arguments
)
"""


# Shared occupancy: the exclusion constraint, the row guard (BEFORE INSERT OR UPDATE
# OR DELETE, tgtype 31) and the booking mirror (AFTER INSERT OR UPDATE OF
# booking_status, tgtype 21), each enabled and calling its approved function.
_ACCESS_BOUNDARY += """
and exists (
    select 1 from pg_catalog.pg_constraint k
    where k.conrelid = pg_catalog.to_regclass('gba.resource_allocations')
      and k.conname = 'resource_allocations_no_overlap' and k.contype = 'x' and k.convalidated
      and regexp_replace(pg_catalog.pg_get_constraintdef(k.oid), '[[:space:]]', '', 'g') = %s
) and exists (
    select 1 from pg_catalog.pg_constraint k
    where k.conrelid = pg_catalog.to_regclass('gba.property_leases')
      and k.conname = 'property_leases_no_overlap' and k.contype = 'x' and k.convalidated
      and regexp_replace(pg_catalog.pg_get_constraintdef(k.oid), '[[:space:]]', '', 'g') = %s
) and exists (
    select 1 from pg_catalog.pg_proc f
    where f.oid = pg_catalog.to_regprocedure('gba.booking_occupancy_state(text)')
      and not f.prosecdef and f.proconfig is null and f.provolatile = 'i'
      and f.prolang = (select oid from pg_catalog.pg_language where lanname = 'sql')
      and regexp_replace(f.prosrc, '[[:space:]]', '', 'g') = %s
) and not exists (
    select 1 from (values __OCCUPANCY_TRIGGERS__
    ) required(table_name, trigger_name, trigger_type, function_name, columns, source)
    left join pg_catalog.pg_trigger t
      on t.tgrelid = pg_catalog.to_regclass('gba.' || required.table_name)
     and t.tgname = required.trigger_name
    left join pg_catalog.pg_proc f on f.oid = t.tgfoid
    where t.oid is null or t.tgtype <> required.trigger_type or t.tgenabled <> 'O'
       or t.tgisinternal or t.tgqual is not null or t.tgconstraint <> 0 or t.tgnargs <> 0
       or f.oid is distinct from pg_catalog.to_regprocedure(required.function_name)
       or f.prosecdef or f.proconfig is not null
       or f.prolang <> (select oid from pg_catalog.pg_language where lanname = 'plpgsql')
       or regexp_replace(f.prosrc, '[[:space:]]', '', 'g') <> required.source
       -- An UPDATE OF list on other columns would skip the status changes.
       or coalesce((
           select string_agg(a.attname, ',' order by a.attnum)
           from unnest(t.tgattr::int2[]) k(attnum)
           join pg_catalog.pg_attribute a on a.attrelid = t.tgrelid and a.attnum = k.attnum
       ), '') <> required.columns
)
""".replace(
    "__OCCUPANCY_TRIGGERS__",
    ", ".join("(%s, %s, %s::int, %s, %s, %s::text)" for _ in _OCCUPANCY_TRIGGERS),
)


# A reservation's resources before commit: the deferred constraint trigger,
# enabled and calling its approved function.
_ACCESS_BOUNDARY += """
and exists (
    select 1 from pg_catalog.pg_trigger t
    join pg_catalog.pg_proc f on f.oid = t.tgfoid
    where t.tgrelid = pg_catalog.to_regclass('gba.resource_reservations')
      and t.tgname = 'resource_reservations_allocated'
      and t.tgtype = 5 and t.tgenabled = 'O' and not t.tgisinternal
      and t.tgconstraint <> 0 and t.tgdeferrable and t.tginitdeferred
      and t.tgqual is null and t.tgnargs = 0
      and f.oid = pg_catalog.to_regprocedure('gba.check_reservation_allocated()')
      and not f.prosecdef and f.proconfig is null
      and f.prolang = (select oid from pg_catalog.pg_language where lanname = 'plpgsql')
      and regexp_replace(f.prosrc, '[[:space:]]', '', 'g') = %s
)
and exists (
    select 1 from pg_catalog.pg_trigger t
    join pg_catalog.pg_proc f on f.oid = t.tgfoid
    where t.tgrelid = pg_catalog.to_regclass('gba.property_showings')
      and t.tgname = 'property_showings_allocated'
      and t.tgtype = 5 and t.tgenabled = 'O' and not t.tgisinternal
      and t.tgconstraint <> 0 and t.tgdeferrable and t.tginitdeferred
      and t.tgqual is null and t.tgnargs = 0
      and f.oid = pg_catalog.to_regprocedure('gba.check_property_showing_allocated()')
      and not f.prosecdef and f.proconfig is null
      and f.prolang = (select oid from pg_catalog.pg_language where lanname = 'plpgsql')
      and regexp_replace(f.prosrc, '[[:space:]]', '', 'g') = %s
)
"""


async def assert_location_scope_ready(conn: RuntimeConnection) -> None:
    parameters: list[object] = [field for definition in _DEFINITIONS for field in definition]
    parameters += [_FUNCTION_SOURCE, _compact(_BOOKING_MODULE_SOURCE)]
    parameters += [
        _OPTIONAL_MODULE_SOURCE,
        [table for table, _, _ in _MODULE_TRIGGERS],
        [trigger for _, trigger, _ in _MODULE_TRIGGERS],
        [module.encode() + b"\x00" for _, _, module in _MODULE_TRIGGERS],
        _compact(_OCCUPANCY_CONSTRAINT),
        _compact(_PROPERTY_LEASE_EXCLUSION),
        _compact(_OCCUPANCY_STATE_SOURCE),
    ]
    for table, trigger, kind, function, columns, source in _OCCUPANCY_TRIGGERS:
        parameters += [table, trigger, kind, function, columns, _compact(source)]
    parameters.append(_compact(_RESERVATION_ALLOCATED_SOURCE))
    parameters.append(_compact(CHECK_PROPERTY_SHOWING_ALLOCATED_SOURCE))
    parameters.extend(LEDGER_PARAMETERS)
    parameters.extend(FINANCIAL_PARAMETERS)
    row = await (
        await conn.execute(_ACCESS_BOUNDARY + LEDGER_BOUNDARY + FINANCIAL_BOUNDARY, parameters)
    ).fetchone()
    if row is None or row[0] is not True:
        raise DatabaseUnavailableError("Required database access controls are not ready")
