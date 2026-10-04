"""Fail closed on missing or altered PostgreSQL 18 access-boundary definitions.

Branch-scoped work (ADR-0014) and delegated work between businesses (ADR-0016) rely on
these scope functions, restrictive policies and cross-tenant delegation policies.
"""

from dataclasses import dataclass

from gorgona_booking.db.pool import RuntimeConnection
from gorgona_booking.errors import DatabaseUnavailableError

_NO_LOCATION = "(gba.current_location_id() IS NULL)"
_NO_DELEGATION = "(gba.current_delegation_grant_id() IS NULL)"
_LOCATION_SOURCE = "select nullif(pg_catalog.current_setting('gba.location_id', true), '')::uuid"
_DELEGATION_SOURCE = (
    "select nullif(pg_catalog.current_setting('gba.delegation_grant_id', true), '')::uuid"
)

# Tables whose complete policy set is fixed: no other policy may widen them.
DELEGATION_TABLES = ("delegation_grants", "delegation_grant_versions", "delegation_designations")


@dataclass(frozen=True, slots=True)
class PolicyDefinition:
    """Restrictive policies apply to gba_runtime; permissive ones to PUBLIC."""

    table: str
    name: str
    using: str
    check: str | None
    command: str = "*"
    permissive: bool = False

    def parameters(self) -> tuple[str, str, bool, str, str, str | None]:
        # PostgreSQL deparses the approved expression. Ignore formatting whitespace,
        # retain parentheses, predicates and SQL case; do not reduce this to names.
        check = None if self.check is None else _compact(self.check)
        return self.table, self.name, self.permissive, self.command, _compact(self.using), check


def _compact(expression: str) -> str:
    return "".join(expression.split())


def _scope(table: str, name: str, expression: str) -> PolicyDefinition:
    return PolicyDefinition(table, name, expression, expression)


def _parent(table: str, parent: str, alias: str, reference: str) -> str:
    return (
        f"(EXISTS ( SELECT 1 FROM gba.{parent} {alias} "  # noqa: S608 - bound as comparison data
        f"WHERE (({alias}.tenant_id = {table}.tenant_id) "
        f"AND ({alias}.id = {table}.{reference}))))"
    )


def _location(table: str, expression: str) -> PolicyDefinition:
    return _scope(table, f"{table}_location_scope", f"({_NO_LOCATION} OR {expression})")


def _delegate_read(table: str, grant_column: str) -> PolicyDefinition:
    return PolicyDefinition(
        table,
        f"{table}_delegate_read",
        "(EXISTS ( SELECT 1 FROM gba.delegation_designations d "  # noqa: S608 - comparison data
        f"WHERE ((d.grantor_business_id = {table}.tenant_id) "
        f"AND (d.grant_id = {table}.{grant_column}) "
        "AND (d.user_id = gba.current_user_id()) AND (d.status = 'active'::text))))",
        None,
        command="r",
        permissive=True,
    )


def _isolation(table: str) -> PolicyDefinition:
    expression = "(tenant_id = gba.current_tenant_id())"
    return PolicyDefinition(
        table, f"{table}_tenant_isolation", expression, expression, permissive=True
    )


def _read(table: str, name: str, expression: str) -> PolicyDefinition:
    return PolicyDefinition(table, name, expression, None, command="r", permissive=True)


_COMPANY_RECORDS = (
    "business_profile_versions",
    "business_profile_industries",
    "business_profile_formats",
    "salon_fact_confirmations",
    "tenant_embed_origins",
    "invitations",
    "legal_entities",
    "legal_entity_versions",
)

DEFINITIONS: tuple[PolicyDefinition, ...] = (
    # ADR-0014: branch-scoped operational work.
    _location("locations", "(id = gba.current_location_id())"),
    *[
        _location(table, "(location_id = gba.current_location_id())")
        for table in ("resources", "bookings", "business_hours")
    ],
    *[
        _location(table, _parent(table, "resources", "r", "resource_id"))
        for table in ("resource_services", "resource_hours", "resource_blocks")
    ],
    *[
        _location(table, _parent(table, "bookings", "b", "booking_id"))
        for table in ("booking_customers", "booking_events")
    ],
    _location(
        "booking_allocations",
        f"({_parent('booking_allocations', 'bookings', 'b', 'booking_id')} AND "
        f"{_parent('booking_allocations', 'resources', 'r', 'resource_id')})",
    ),
    PolicyDefinition(
        "audit_events", "audit_events_unrestricted_read", _NO_LOCATION, None, command="r"
    ),
    *[
        _scope(table, f"{table}_unrestricted_scope", _NO_LOCATION)
        for table in (*_COMPANY_RECORDS, *DELEGATION_TABLES)
    ],
    # ADR-0016: delegated transactions keep to operational data.
    *[
        _scope(table, f"{table}_delegation_scope", _NO_DELEGATION)
        for table in ("memberships", *_COMPANY_RECORDS, *DELEGATION_TABLES)
    ],
    PolicyDefinition(
        "users",
        "users_delegation_scope",
        f"({_NO_DELEGATION} OR (id = gba.current_user_id()))",
        _NO_DELEGATION,
    ),
    PolicyDefinition(
        "audit_events", "audit_events_delegation_read", _NO_DELEGATION, None, command="r"
    ),
    # ADR-0016: the only cross-tenant views of delegation records.
    *[_isolation(table) for table in DELEGATION_TABLES],
    _read(
        "delegation_grants",
        "delegation_grants_grantee_read",
        "(grantee_business_id = gba.current_tenant_id())",
    ),
    _read(
        "delegation_grant_versions",
        "delegation_grant_versions_grantee_read",
        "(grantee_business_id = gba.current_tenant_id())",
    ),
    _delegate_read("delegation_grants", "id"),
    _delegate_read("delegation_grant_versions", "grant_id"),
    _read(
        "delegation_designations",
        "delegation_designations_grantor_read",
        "(grantor_business_id = gba.current_tenant_id())",
    ),
    _read(
        "delegation_designations",
        "delegation_designations_self_read",
        "(user_id = gba.current_user_id())",
    ),
)

_ACCESS_BOUNDARY = """
with required(table_name, policy_name, permissive, command, using_expr, check_expr) as (
    values __VALUES__
), runtime(oid) as (
    select oid from pg_catalog.pg_roles where rolname = 'gba_runtime'
)
select (
    select count(*) from pg_catalog.pg_proc
    where oid in (pg_catalog.to_regprocedure('gba.current_location_id()'),
                  pg_catalog.to_regprocedure('gba.current_delegation_grant_id()'))
      and not prosecdef and proconfig is null and pronargs = 0
      and prokind = 'f' and provolatile = 's' and proparallel = 's'
      and prorettype = 'pg_catalog.uuid'::regtype
      and prolang = (select oid from pg_catalog.pg_language where lanname = 'sql')
      and btrim(prosrc, E' \t\r\n') = case proname::text
          when 'current_location_id' then %s::text else %s::text end
) = 2 and not exists (
    select 1 from required r
    left join pg_catalog.pg_class c on c.oid = pg_catalog.to_regclass('gba.' || r.table_name)
    left join pg_catalog.pg_policy p on p.polrelid = c.oid and p.polname = r.policy_name
    where c.oid is null or not c.relrowsecurity or not c.relforcerowsecurity
       or p.oid is null or p.polpermissive <> r.permissive or p.polcmd::text <> r.command
       or coalesce(regexp_replace(pg_catalog.pg_get_expr(p.polqual, c.oid),
                                  '[[:space:]]', '', 'g'), '') <> r.using_expr
       or coalesce(regexp_replace(pg_catalog.pg_get_expr(p.polwithcheck, c.oid),
                                  '[[:space:]]', '', 'g'), '') <> coalesce(r.check_expr, '')
       or case when r.permissive then p.polroles <> array[0]::oid[]
               else not coalesce(p.polroles @> array[(select oid from runtime)], false) end
) and not exists (
    select 1 from pg_catalog.pg_policy p
    join pg_catalog.pg_class c on c.oid = p.polrelid
    join pg_catalog.pg_namespace n on n.oid = c.relnamespace
    where n.nspname = 'gba' and c.relname = any(%s::text[])
      and not exists (select 1 from required r
                      where r.table_name = c.relname and r.policy_name = p.polname)
)
""".replace(
    "__VALUES__",
    ", ".join(
        "(%s::text, %s::text, %s::boolean, %s::text, %s::text, %s::text)" for _ in DEFINITIONS
    ),
)


async def assert_access_boundaries_ready(conn: RuntimeConnection) -> None:
    parameters: list[object] = [
        value for definition in DEFINITIONS for value in definition.parameters()
    ]
    parameters.extend([_LOCATION_SOURCE, _DELEGATION_SOURCE, list(DELEGATION_TABLES)])
    row = await (await conn.execute(_ACCESS_BOUNDARY, parameters)).fetchone()
    if row is None or row[0] is not True:
        raise DatabaseUnavailableError("Required database access controls are not ready")
