"""Fail closed on missing or altered PostgreSQL 18 access definitions.

Covers the branch boundary (location policies and company-only scope policies) and
the booking-module trigger of ADR-0019, which refuses new bookings when a published
configuration disables booking.
"""

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
    return new;
end;
"""
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
_MODULE_TABLES = (*_COUNTERPARTY_TABLES, *_DOCUMENT_TABLES)
# (table, trigger, module argument) for every optional-module write gate.
_MODULE_TRIGGERS = (
    *[(table, f"{table}_require_module", "counterparties") for table in _COUNTERPARTY_TABLES],
    *[(table, f"{table}_require_module", "documents") for table in _DOCUMENT_TABLES],
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
        for table in ("resources", "bookings", "business_hours")
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
    where c.oid is null or not c.relrowsecurity or not c.relforcerowsecurity
       or p.oid is null or p.polpermissive or p.polcmd::text <> r.command
       or coalesce(regexp_replace(pg_catalog.pg_get_expr(p.polqual, c.oid),
                                  '[[:space:]]', '', 'g'), '') <> r.using_expression
       or coalesce(regexp_replace(pg_catalog.pg_get_expr(p.polwithcheck, c.oid),
                                  '[[:space:]]', '', 'g'), '') <> r.check_expression
       or not coalesce(p.polroles @> array[(select oid from pg_catalog.pg_roles
                                           where rolname = 'gba_runtime')], false)
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
      and regexp_replace(f.prosrc, '[[:space:]]', '', 'g') = %s
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
    select 1 from pg_catalog.pg_proc f
    where f.oid = pg_catalog.to_regprocedure('gba.booking_occupancy_state(text)')
      and not f.prosecdef and f.proconfig is null and f.provolatile = 'i'
      and f.prolang = (select oid from pg_catalog.pg_language where lanname = 'sql')
      and regexp_replace(f.prosrc, '[[:space:]]', '', 'g') = %s
) and not exists (
    select 1 from (values
        ('resource_allocations', 'resource_allocations_guard', 31,
         'gba.guard_resource_allocation()', '', %s::text),
        ('booking_allocations', 'booking_allocations_mirror_occupancy', 21,
         'gba.mirror_booking_allocation()', 'booking_status', %s::text)
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
"""


async def assert_location_scope_ready(conn: RuntimeConnection) -> None:
    parameters: list[object] = [field for definition in _DEFINITIONS for field in definition]
    parameters += [_FUNCTION_SOURCE, _compact(_BOOKING_MODULE_SOURCE)]
    parameters += [
        _compact(_OPTIONAL_MODULE_SOURCE),
        [table for table, _, _ in _MODULE_TRIGGERS],
        [trigger for _, trigger, _ in _MODULE_TRIGGERS],
        [module.encode() + b"\x00" for _, _, module in _MODULE_TRIGGERS],
        _compact(_OCCUPANCY_CONSTRAINT),
        _compact(_OCCUPANCY_STATE_SOURCE),
        _compact(_OCCUPANCY_GUARD_SOURCE),
        _compact(_OCCUPANCY_MIRROR_SOURCE),
    ]
    row = await (await conn.execute(_ACCESS_BOUNDARY, parameters)).fetchone()
    if row is None or row[0] is not True:
        raise DatabaseUnavailableError("Required database access controls are not ready")
