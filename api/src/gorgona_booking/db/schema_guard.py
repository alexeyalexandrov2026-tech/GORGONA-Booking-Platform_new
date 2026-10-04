"""Fail closed on missing or altered PostgreSQL 18 branch access definitions."""

from gorgona_booking.db.pool import RuntimeConnection
from gorgona_booking.errors import DatabaseUnavailableError

_NO_LOCATION = "(gba.current_location_id() IS NULL)"
_FUNCTION_SOURCE = "select nullif(pg_catalog.current_setting('gba.location_id', true), '')::uuid"


def _parent(table: str, parent: str, alias: str, reference: str) -> str:
    return (
        f"(EXISTS ( SELECT 1 FROM gba.{parent} {alias} "  # noqa: S608 - bound as comparison data
        f"WHERE (({alias}.tenant_id = {table}.tenant_id) "
        f"AND ({alias}.id = {table}.{reference}))))"
    )


def _definition(table: str, expression: str, *, command: str = "*") -> tuple[str, str, str, str]:
    suffix = "location_scope" if command == "*" else "unrestricted_read"
    # PostgreSQL deparses the approved expression. Ignore formatting whitespace,
    # retain parentheses, predicates and SQL case; do not reduce this to names.
    return table, f"{table}_{suffix}", command, "".join(expression.split())


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
    _definition("audit_events", _NO_LOCATION, command="r"),
    *[
        (table, f"{table}_unrestricted_scope", "*", "".join(_NO_LOCATION.split()))
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
        )
    ],
]

_LOCATION_BOUNDARY = """
with required(table_name, policy_name, command, expression) as (values __VALUES__)
select exists (
    select 1 from pg_catalog.pg_proc
    where oid = pg_catalog.to_regprocedure('gba.current_location_id()')
      and not prosecdef and proconfig is null and pronargs = 0
      and prokind = 'f' and provolatile = 's' and proparallel = 's'
      and prorettype = 'pg_catalog.uuid'::regtype
      and prolang = (select oid from pg_catalog.pg_language where lanname = 'sql')
      and btrim(prosrc, E' \t\r\n') = %s
) and not exists (
    select 1 from required r
    left join pg_catalog.pg_class c on c.oid = pg_catalog.to_regclass('gba.' || r.table_name)
    left join pg_catalog.pg_policy p on p.polrelid = c.oid and p.polname = r.policy_name
    where c.oid is null or not c.relrowsecurity or not c.relforcerowsecurity
       or p.oid is null or p.polpermissive or p.polcmd::text <> r.command
       or coalesce(regexp_replace(pg_catalog.pg_get_expr(p.polqual, c.oid),
                                  '[[:space:]]', '', 'g'), '') <> r.expression
       or (r.command = '*' and coalesce(regexp_replace(
               pg_catalog.pg_get_expr(p.polwithcheck, c.oid),
               '[[:space:]]', '', 'g'), '') <> r.expression)
       or not coalesce(p.polroles @> array[(select oid from pg_catalog.pg_roles
                                           where rolname = 'gba_runtime')], false)
)
""".replace("__VALUES__", ", ".join("(%s, %s, %s, %s)" for _ in _DEFINITIONS))


async def assert_location_scope_ready(conn: RuntimeConnection) -> None:
    parameters = [field for definition in _DEFINITIONS for field in definition]
    parameters.append(_FUNCTION_SOURCE)
    row = await (await conn.execute(_LOCATION_BOUNDARY, parameters)).fetchone()
    if row is None or row[0] is not True:
        raise DatabaseUnavailableError("Required database access controls are not ready")
