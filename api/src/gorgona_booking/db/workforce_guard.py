"""I1-I4 packaged schema approvals. Never learn approvals from the target database."""

import re
from collections import defaultdict
from importlib import resources
from typing import Any

from gorgona_booking.db.pool import RuntimeConnection
from gorgona_booking.errors import DatabaseUnavailableError

_MIGRATIONS = resources.files("gorgona_booking.db") / "migrations"
_SQL = "\n".join(
    (_MIGRATIONS / filename).read_text(encoding="utf-8")
    for filename in (
        "0032_workforce.sql",
        "0033_shift_changes.sql",
        "0034_timesheets.sql",
        "0035_work_location_settings.sql",
    )
)
_BLOCKS = dict(re.findall(r"create table gba\.(\w+)\s*\((.*?)\n\);", _SQL, re.DOTALL))
WORKFORCE_TABLES = tuple(_BLOCKS)
_FUNCTIONS = dict(
    re.findall(
        r"create (?:or replace )?function gba\.(\w+)\([^;]*?as \$\$(.*?)\$\$;",
        (_MIGRATIONS / "0015_counterparties.sql").read_text(encoding="utf-8") + _SQL,
        re.DOTALL,
    )
)
_TRIGGERS = tuple(
    re.findall(
        "create (constraint )?trigger (\\w+) (before|after) (update or "
        "delete|insert or update or delete|insert|update) on gba\\.(\\w+)\\s*"
        r"(deferrable initially deferred )?for each row execute function gba\.(\w+)\(([^)]*)\);",
        _SQL,
        re.DOTALL,
    )
)
_DECLARED_TRIGGERS = set(re.findall(r"create (?:constraint )?trigger (\w+)", _SQL))
if {trigger[1] for trigger in _TRIGGERS} != _DECLARED_TRIGGERS:
    raise RuntimeError("Every workforce trigger must have an explicit packaged approval")
# 0032 replaces this existing shared function. I1 also verifies its literal
# semantics, rather than inheriting whitespace normalization from older guards.
_TRIGGERS += (
    (
        "",
        "resource_allocations_guard",
        "before",
        "insert or update or delete",
        "resource_allocations",
        "",
        "guard_resource_allocation",
        "",
    ),
)
_INSERTS = {
    table: set(columns.split(","))
    for columns, table in re.findall(r"grant insert \(([^)]+)\) on gba\.(\w+)", _SQL)
}
_COLUMN_PATTERN = (
    r"^    (\w+) (uuid\[\]|uuid|text|integer|boolean|timestamptz\[\]|"
    r"timestamptz|xid8)(?=[\s,])([^\n]*)"
)
_COLUMNS = {
    table: tuple(re.findall(_COLUMN_PATTERN, block, re.MULTILINE))
    for table, block in _BLOCKS.items()
}
_KEYS = {
    table: tuple(
        (kind, tuple(x.strip() for x in columns.split(",")))
        for kind, columns in re.findall(r"(primary key|unique) \(([^)]+)\)", block)
    )
    for table, block in _BLOCKS.items()
}
_FKS = {
    table: tuple(
        (
            tuple(x.strip() for x in columns.split(",")),
            parent,
            tuple(x.strip() for x in targets.split(",")),
        )
        for columns, parent, targets in re.findall(
            r"foreign key \(([^)]+)\)\s*references gba\.(\w+)\(([^)]+)\)", block
        )
    )
    for table, block in _BLOCKS.items()
}


# Explicit PostgreSQL 18 deparse approvals of the reviewed packaged migration.
# Compared with whitespace only: quoted identifiers, literals and parentheses stay.
def _expression(value: str) -> str:
    # Strip formatting only outside SQL string literals and quoted identifiers.
    # Spaces inside a regex, advisory-lock namespace or name are significant.
    return "".join(
        part if part.startswith(("'", '"')) else re.sub(r"\s", "", part)
        for part in re.split(r"""('(?:''|[^'])*'|"(?: "" | [^"] )*")""".replace(" ", ""), value)
    )


_CHECKS = {
    "staff_skill_events_effective_check": "((isfinite(effective_at) AND (EXTRACT(epoch FROM "
    "effective_at) >= ('-62104060800'::bigint)::numeric) "
    "AND (EXTRACT(epoch FROM effective_at) < "
    "('253370764800'::bigint)::numeric)))",
    "staff_skill_events_revision_check": "((revision > 0))",
    "work_shift_versions_assignment_check": "(((status = 'published'::text) OR (profile_id IS "
    "NULL)))",
    "work_shift_versions_interval_check": "((isfinite(starts_at) AND isfinite(ends_at) AND "
    "(ends_at > starts_at) AND (EXTRACT(epoch FROM "
    "starts_at) >= ('-62104060800'::bigint)::numeric) AND "
    "(EXTRACT(epoch FROM ends_at) < "
    "('253370764800'::bigint)::numeric) AND (ends_at <= "
    "(starts_at + '31 days'::interval))))",
    "work_shift_versions_position_check": '((((length(btrim("position")) >= 1) AND '
    '(length(btrim("position")) <= 200)) AND ("position" '
    "!~ '[[:cntrl:]]'::text)))",
    "work_shift_versions_revision_check": "((revision > 0))",
    "work_shift_versions_skills_check": "(((cardinality(required_skill_ids) <= 20) AND "
    "(COALESCE(array_ndims(required_skill_ids), 1) = 1) AND "
    "(array_position(required_skill_ids, NULL::uuid) IS "
    "NULL)))",
    "work_shift_versions_status_check": "((status = ANY (ARRAY['draft'::text, 'published'::text, "
    "'cancelled'::text])))",
    "work_skill_versions_name_check": "((((length(btrim(name)) >= 1) AND (length(btrim(name)) <= "
    "200)) AND (name !~ '[[:cntrl:]]'::text)))",
    "work_skill_versions_revision_check": "((revision > 0))",
    "work_skills_code_check": "((code ~ '^[A-Z][A-Z0-9_]{0,63}$'::text))",
    "shift_change_events_action_check": (
        "((action = ANY (ARRAY['propose'::text, 'accept'::text, 'approve'::text, "
        "'decline'::text, 'withdraw'::text])))"
    ),
    "shift_change_events_revision_check": ("((revision > 0))"),
    "shift_change_events_status_check": (
        "((status = ANY (ARRAY['proposed'::text, 'accepted'::text, 'approved'::te"
        "xt, 'declined'::text, 'withdrawn'::text])))"
    ),
    "shift_change_requests_kind_check": (
        "((kind = ANY (ARRAY['handover'::text, 'swap'::text, 'pickup'::text])))"
    ),
    "shift_change_requests_revision_check": (
        "(((shift_revision >= 1) AND (shift_revision <= 2147483646)))"
    ),
    "shift_change_requests_shape_check": (
        "((((kind = 'swap'::text) AND (other_shift_id IS NOT NULL) AND (other_shi"
        "ft_id <> shift_id) AND ((other_shift_revision >= 1) AND (other_shift_rev"
        "ision <= 2147483646)) AND (other_location_id IS NOT NULL) AND (from_prof"
        "ile_id IS NOT NULL) AND (from_assignment_id IS NOT NULL) AND (other_assi"
        "gnment_id IS NOT NULL)) OR ((kind = 'handover'::text) AND (other_shift_i"
        "d IS NULL) AND (other_shift_revision IS NULL) AND (other_location_id IS "
        "NULL) AND (other_assignment_id IS NULL) AND (from_profile_id IS NOT NULL"
        ") AND (from_assignment_id IS NOT NULL)) OR ((kind = 'pickup'::text) AND "
        "(other_shift_id IS NULL) AND (other_shift_revision IS NULL) AND (other_l"
        "ocation_id IS NULL) AND (other_assignment_id IS NULL) AND (from_profile_"
        "id IS NULL) AND (from_assignment_id IS NULL))))"
    ),
    "shift_change_skill_snapshots_catalogue_check": ("((catalogue_revision > 0))"),
    "shift_change_skill_snapshots_staff_check": ("((staff_revision >= 0))"),
    "time_entries_date_check": (
        "((isfinite(starts_at) AND (EXTRACT(epoch FROM starts_at) >= ('-621040608"
        "00'::bigint)::numeric) AND (EXTRACT(epoch FROM starts_at) < ('2533707648"
        "00'::bigint)::numeric)))"
    ),
    "time_entries_shift_check": (
        "((((shift_id IS NULL) AND (shift_revision IS NULL) AND (shift_starts_at "
        "IS NULL) AND (shift_ends_at IS NULL)) OR ((shift_id IS NOT NULL) AND (sh"
        "ift_revision IS NOT NULL) AND ((shift_revision >= 1) AND (shift_revision"
        " <= 2147483646)) AND (shift_starts_at IS NOT NULL) AND (shift_ends_at IS"
        " NOT NULL) AND (shift_ends_at > shift_starts_at))))"
    ),
    "time_entry_revisions_action_check": (
        "((action = ANY (ARRAY['clock_in'::text, 'break_start'::text, 'break_end'"
        "::text, 'clock_out'::text, 'correct'::text, 'approve'::text, 'decline'::"
        "text])))"
    ),
    "time_entry_revisions_arrays_check": (
        "(((cardinality(break_starts) = cardinality(break_ends)) AND (cardinality"
        "(break_starts) <= 100) AND (COALESCE(array_ndims(break_starts), 1) = 1) "
        "AND (COALESCE(array_ndims(break_ends), 1) = 1) AND (COALESCE(array_lower"
        "(break_starts, 1), 1) = 1) AND (COALESCE(array_lower(break_ends, 1), 1) "
        "= 1)))"
    ),
    "time_entry_revisions_dates_check": (
        "((isfinite(occurred_at) AND (EXTRACT(epoch FROM occurred_at) >= ('-62104"
        "060800'::bigint)::numeric) AND (EXTRACT(epoch FROM occurred_at) < ('2533"
        "70764800'::bigint)::numeric) AND isfinite(starts_at) AND (EXTRACT(epoch "
        "FROM starts_at) >= ('-62104060800'::bigint)::numeric) AND (EXTRACT(epoch"
        " FROM starts_at) < ('253370764800'::bigint)::numeric) AND ((ends_at IS N"
        "ULL) OR (isfinite(ends_at) AND (ends_at > starts_at) AND (EXTRACT(epoch "
        "FROM ends_at) < ('253370764800'::bigint)::numeric))) AND ((break_started"
        "_at IS NULL) OR (isfinite(break_started_at) AND (break_started_at >= sta"
        "rts_at) AND (EXTRACT(epoch FROM break_started_at) < ('253370764800'::big"
        "int)::numeric)))))"
    ),
    "time_entry_revisions_reason_check": (
        "((((length(btrim(reason)) >= 1) AND (length(btrim(reason)) <= 1000)) AND"
        " (reason !~ '[[:cntrl:]]'::text)))"
    ),
    "time_entry_revisions_revision_check": ("((revision > 0))"),
    "time_entry_revisions_shape_check": (
        "((((status = 'open'::text) AND (ends_at IS NULL)) OR ((status <> 'open':"
        ":text) AND (ends_at IS NOT NULL) AND (break_started_at IS NULL))))"
    ),
    "time_entry_revisions_status_check": (
        "((status = ANY (ARRAY['open'::text, 'proposed'::text, 'approved'::text, "
        "'declined'::text])))"
    ),
    "time_entry_state_revision_check": ("((last_revision > 0))"),
    "work_location_setting_versions_revision_check": ("((revision > 0))"),
    "time_entry_state_shape_check": (
        "((((approved_revision IS NULL) AND (starts_at IS NULL) AND (ends_at IS N"
        "ULL)) OR ((approved_revision IS NOT NULL) AND (starts_at IS NOT NULL) AN"
        "D (ends_at IS NOT NULL) AND (approved_revision <= last_revision) AND (en"
        "ds_at > starts_at))))"
    ),
}

_POLICIES = {
    "shift_assignments": (
        "((gba.current_location_id() IS NULL) OR (EXISTS ( SELECT 1\n"
        "   FROM gba.work_shifts s\n"
        "  WHERE ((s.tenant_id = shift_assignments.tenant_id) AND (s.id = "
        "shift_assignments.shift_id) AND (s.location_id = "
        "gba.current_location_id())))))",
        "((gba.current_location_id() IS NULL) OR (EXISTS ( SELECT 1\n"
        "   FROM gba.work_shifts s\n"
        "  WHERE ((s.tenant_id = shift_assignments.tenant_id) AND (s.id = "
        "shift_assignments.shift_id) AND (s.location_id = "
        "gba.current_location_id())))))",
    ),
    "staff_profiles": (
        "((gba.current_location_id() IS NULL) OR (location_id = gba.current_location_id()))",
        "((gba.current_location_id() IS NULL) OR (location_id = gba.current_location_id()))",
    ),
    "staff_resource_owners": (
        "((gba.current_location_id() IS NULL) OR (location_id = gba.current_location_id()))",
        "((gba.current_location_id() IS NULL) OR (location_id = gba.current_location_id()))",
    ),
    "staff_skill_events": (
        "((gba.current_location_id() IS NULL) OR (EXISTS ( SELECT 1\n"
        "   FROM gba.staff_profiles p\n"
        "  WHERE ((p.tenant_id = staff_skill_events.tenant_id) AND (p.id = "
        "staff_skill_events.profile_id) AND (p.location_id = "
        "gba.current_location_id())))))",
        "((gba.current_location_id() IS NULL) OR (EXISTS ( SELECT 1\n"
        "   FROM gba.staff_profiles p\n"
        "  WHERE ((p.tenant_id = staff_skill_events.tenant_id) AND (p.id = "
        "staff_skill_events.profile_id) AND (p.location_id = "
        "gba.current_location_id())))))",
    ),
    "work_shift_versions": (
        "((gba.current_location_id() IS NULL) OR (EXISTS ( SELECT 1\n"
        "   FROM gba.work_shifts s\n"
        "  WHERE ((s.tenant_id = work_shift_versions.tenant_id) AND (s.id = "
        "work_shift_versions.shift_id) AND (s.location_id = "
        "gba.current_location_id())))))",
        "((gba.current_location_id() IS NULL) OR (EXISTS ( SELECT 1\n"
        "   FROM gba.work_shifts s\n"
        "  WHERE ((s.tenant_id = work_shift_versions.tenant_id) AND (s.id = "
        "work_shift_versions.shift_id) AND (s.location_id = "
        "gba.current_location_id())))))",
    ),
    "work_shifts": (
        "((gba.current_location_id() IS NULL) OR (location_id = gba.current_location_id()))",
        "((gba.current_location_id() IS NULL) OR (location_id = gba.current_location_id()))",
    ),
    "work_skill_versions": ("true", "(gba.current_location_id() IS NULL)"),
    "work_skills": ("true", "(gba.current_location_id() IS NULL)"),
    "shift_change_events": (
        (
            "(EXISTS ( SELECT 1\n   FROM gba.shift_change_requests r\n  WHERE ((r.tenan"
            "t_id = shift_change_events.tenant_id) AND (r.id = shift_change_events.re"
            "quest_id))))"
        ),
        (
            "(EXISTS ( SELECT 1\n   FROM gba.shift_change_requests r\n  WHERE ((r.tenan"
            "t_id = shift_change_events.tenant_id) AND (r.id = shift_change_events.re"
            "quest_id))))"
        ),
    ),
    "shift_change_requests": (
        (
            "((gba.current_location_id() IS NULL) OR ((location_id = gba.current_loca"
            "tion_id()) AND ((other_location_id IS NULL) OR (other_location_id = gba."
            "current_location_id()))))"
        ),
        (
            "((gba.current_location_id() IS NULL) OR ((location_id = gba.current_loca"
            "tion_id()) AND ((other_location_id IS NULL) OR (other_location_id = gba."
            "current_location_id()))))"
        ),
    ),
    "shift_change_skill_snapshots": (
        (
            "(EXISTS ( SELECT 1\n   FROM gba.shift_change_requests r\n  WHERE ((r.tenan"
            "t_id = shift_change_skill_snapshots.tenant_id) AND (r.id = shift_change_"
            "skill_snapshots.request_id))))"
        ),
        (
            "(EXISTS ( SELECT 1\n   FROM gba.shift_change_requests r\n  WHERE ((r.tenan"
            "t_id = shift_change_skill_snapshots.tenant_id) AND (r.id = shift_change_"
            "skill_snapshots.request_id))))"
        ),
    ),
    "time_entries": (
        ("((gba.current_location_id() IS NULL) OR (location_id = gba.current_location_id()))"),
        ("((gba.current_location_id() IS NULL) OR (location_id = gba.current_location_id()))"),
    ),
    "time_entry_revisions": (
        (
            "(EXISTS ( SELECT 1\n   FROM gba.time_entries e\n  WHERE ((e.tenant_id = ti"
            "me_entry_revisions.tenant_id) AND (e.id = time_entry_revisions.entry_id)"
            ")))"
        ),
        (
            "(EXISTS ( SELECT 1\n   FROM gba.time_entries e\n  WHERE ((e.tenant_id = ti"
            "me_entry_revisions.tenant_id) AND (e.id = time_entry_revisions.entry_id)"
            ")))"
        ),
    ),
    "time_entry_state": (
        ("((gba.current_location_id() IS NULL) OR (location_id = gba.current_location_id()))"),
        ("((gba.current_location_id() IS NULL) OR (location_id = gba.current_location_id()))"),
    ),
    "work_location_setting_versions": (
        ("((gba.current_location_id() IS NULL) OR (location_id = gba.current_location_id()))"),
        ("((gba.current_location_id() IS NULL) OR (location_id = gba.current_location_id()))"),
    ),
}

_EXCLUSIONS: dict[str, str] = {
    "time_entry_state_no_overlap": (
        "EXCLUDE USING gist (tenant_id WITH =, user_id WITH =, tstzrange(starts_a"
        "t, ends_at, '[)'::text) WITH &&) WHERE ((approved_revision IS NOT NULL))"
    ),
    "time_entry_state_one_open": (
        "EXCLUDE USING gist (tenant_id WITH =, user_id WITH =) WHERE (is_open)"
    ),
}

_SHARED_CHECKS = {
    (
        "resources",
        "resources_kind_valid",
    ): "((kind = ANY (ARRAY['artist'::text, 'chair'::text, 'room'::text, 'staff'::text])))",
    (
        "resource_allocations",
        "resource_allocations_source_kind",
    ): "((source_kind = ANY (ARRAY['booking'::text, 'reservation'::text, 'shift'::text])))",
}


async def assert_workforce_ready(conn: RuntimeConnection) -> None:
    try:
        await _check(conn)
    except (ValueError, KeyError) as exc:
        raise DatabaseUnavailableError("Workforce schema protection is unavailable") from exc


def _require(value: bool) -> None:
    if not value:
        raise ValueError("Workforce schema differs from packaged approvals")


async def _catalog(
    conn: RuntimeConnection, query: str, names: list[str]
) -> dict[str, list[tuple[Any, ...]]]:
    grouped: dict[str, list[tuple[Any, ...]]] = defaultdict(list)
    for row in await (await conn.execute(query, (names,))).fetchall():
        grouped[str(row[0])].append(tuple(row[1:]))
    return grouped


async def _check(conn: RuntimeConnection) -> None:
    names = list(WORKFORCE_TABLES)
    tables = await _catalog(
        conn,
        """
        select c.relname,c.relrowsecurity,c.relforcerowsecurity,c.relkind,
               has_table_privilege(current_user,c.oid,'SELECT'),
               has_table_privilege(current_user,c.oid,'UPDATE,DELETE,TRUNCATE,REFERENCES,TRIGGER'),
               exists(select 1 from aclexplode(c.relacl) a where a.grantee=0)
          from pg_class c where c.relnamespace='gba'::regnamespace and c.relname=any(%s)
    """,
        names,
    )
    policies = await _catalog(
        conn,
        """
        select c.relname,p.polname,p.polpermissive,p.polcmd,
               pg_get_expr(p.polqual,p.polrelid),pg_get_expr(p.polwithcheck,p.polrelid),
               p.polroles=array[0::oid],
               p.polroles=array[(select oid from pg_roles where rolname='gba_runtime')]
          from pg_policy p join pg_class c on c.oid=p.polrelid
         where c.relnamespace='gba'::regnamespace and c.relname=any(%s)
    """,
        names,
    )
    columns = await _catalog(
        conn,
        """
        select c.relname,a.attname,format_type(a.atttypid,a.atttypmod),a.attnotnull,
               pg_get_expr(d.adbin,d.adrelid),
               has_column_privilege(current_user,a.attrelid,a.attnum,'INSERT'),
               has_column_privilege(current_user,a.attrelid,a.attnum,'UPDATE'),
               has_column_privilege(current_user,a.attrelid,a.attnum,'REFERENCES'),
               exists(select 1 from aclexplode(a.attacl) acl where acl.grantee=0)
          from pg_attribute a join pg_class c on c.oid=a.attrelid
          left join pg_attrdef d on d.adrelid=a.attrelid and d.adnum=a.attnum
         where c.relnamespace='gba'::regnamespace and c.relname=any(%s)
           and a.attnum>0 and not a.attisdropped order by c.relname,a.attnum
    """,
        names,
    )
    constraints = await _catalog(
        conn,
        """
        select cl.relname,c.conname,c.contype,c.convalidated,c.conenforced,
               pg_get_constraintdef(c.oid),
               array(select attname from pg_attribute where attrelid=c.conrelid
                     and attnum=any(c.conkey) order by array_position(c.conkey,attnum)),
               c.confrelid::regclass::text,
               array(select attname from pg_attribute where attrelid=c.confrelid
                     and attnum=any(c.confkey) order by array_position(c.confkey,attnum)),
               c.condeferrable,c.condeferred,c.confupdtype,c.confdeltype,c.confmatchtype,c.connoinherit,
               i.indisvalid,i.indisready,i.indislive,i.indisexclusion,am.amname,
               array(select op.opcname from unnest(i.indclass) with ordinality x(id,n)
                     join pg_opclass op on op.oid=x.id order by x.n)
          from pg_constraint c join pg_class cl on cl.oid=c.conrelid
          left join pg_index i on i.indexrelid=c.conindid
          left join pg_class ix on ix.oid=i.indexrelid left join pg_am am on am.oid=ix.relam
         where cl.relnamespace='gba'::regnamespace and cl.relname=any(%s)
    """,
        [*names, "resources", "resource_allocations"],
    )
    trigger_tables = sorted({t[4] for t in _TRIGGERS})
    triggers = await _catalog(
        conn,
        """
        select cl.relname,t.tgname,t.tgtype,t.tgenabled,t.tgdeferrable,t.tginitdeferred,t.tgargs,
               p.prosrc,p.prosecdef,p.proconfig,p.prorettype::regtype::text,t.tgqual,t.tgattr::text,
               t.tgisinternal,(t.tgconstraint<>0),p.oid=to_regprocedure('gba.'||p.proname||'()'),
               l.lanname,p.provolatile,p.proparallel,p.pronargs,p.prokind,p.proleakproof,p.proname,
               t.tgoldtable,t.tgnewtable
          from pg_trigger t join pg_class cl on cl.oid=t.tgrelid join pg_proc p on p.oid=t.tgfoid
          join pg_language l on l.oid=p.prolang
         where cl.relnamespace='gba'::regnamespace and cl.relname=any(%s) and not t.tgisinternal
    """,
        trigger_tables,
    )
    for (table, name), definition in _SHARED_CHECKS.items():
        actual_shared = next((row for row in constraints[table] if row[0] == name), None)
        _require(actual_shared is not None)
        if actual_shared is not None:
            _require(actual_shared[1:4] == ("c", True, True))
            _require(
                _expression(actual_shared[4].removeprefix("CHECK ")) == _expression(definition)
            )
    for table in WORKFORCE_TABLES:
        _require(tables[table] == [(True, True, "r", True, False, False)])
        _require(len(policies[table]) == 2)
        for name, permissive, cmd, using, check, public, runtime in policies[table]:
            tenant = name == table + "_tenant_isolation"
            _require(tenant or name == table + "_location_scope")
            expected = (
                ("(tenant_id = gba.current_tenant_id())",) * 2 if tenant else _POLICIES[table]
            )
            _require(permissive == tenant and cmd == "*" and public == tenant and runtime != tenant)
            _require(
                _expression(using) == _expression(expected[0])
                and _expression(check) == _expression(expected[1])
            )
        _require(len(columns[table]) == len(_COLUMNS[table]))
        for actual, (name, kind, tail) in zip(columns[table], _COLUMNS[table], strict=True):
            default = (
                "pg_current_xact_id()"
                if name == "creation_xid"
                else "now()"
                if "default now()" in tail
                else "uuidv7()"
                if "default uuidv7()" in tail
                else None
            )
            lock_column = (
                table in ("work_skills", "work_shifts", "shift_change_requests", "time_entries")
                and name == "id"
            ) or (
                table == "time_entry_state"
                and name
                in ("last_revision", "is_open", "approved_revision", "starts_at", "ends_at")
            )
            _require(
                actual
                == (
                    name,
                    "timestamp with time zone"
                    if kind == "timestamptz"
                    else "timestamp with time zone[]"
                    if kind == "timestamptz[]"
                    else kind,
                    "not null" in tail,
                    default,
                    name in _INSERTS[table],
                    lock_column,
                    False,
                    False,
                )
            )
        actual_keys: set[tuple[str, tuple[str, ...]]] = set()
        actual_fks: set[tuple[tuple[str, ...], str, tuple[str, ...]]] = set()
        check_names = set()
        exclusion_names = set()
        for (
            name,
            kind,
            valid,
            enforced,
            definition,
            keys,
            parent,
            targets,
            defer,
            deferred,
            up,
            delete,
            match,
            noinherit,
            index_valid,
            index_ready,
            index_live,
            index_exclusion,
            index_method,
            index_classes,
        ) in constraints[table]:
            if not valid or not enforced or (kind == "c" and noinherit):
                raise ValueError(
                    f"Invalid constraint flags: {name} {kind} {valid} {enforced} {noinherit}"
                )
            if kind in ("p", "u"):
                _require(not defer and not deferred)
                actual_keys.add(("primary key" if kind == "p" else "unique", tuple(keys)))
            elif kind == "f":
                _require(not defer and not deferred and (up, delete, match) == ("a", "a", "s"))
                actual_fks.add((tuple(keys), str(parent).removeprefix("gba."), tuple(targets)))
            elif kind == "c":
                check_names.add(name)
                _require(
                    name in _CHECKS
                    and _expression(definition.removeprefix("CHECK ")) == _expression(_CHECKS[name])
                )
            elif kind == "t":
                _require(name in {t[1] for t in _TRIGGERS if t[0] and t[4] == table})
            elif kind == "x":
                exclusion_names.add(name)
                _require(not defer and not deferred and name in _EXCLUSIONS)
                _require(_expression(definition) == _expression(_EXCLUSIONS[name]))
                expected_classes = ["gist_uuid_ops", "gist_uuid_ops"]
                if name == "time_entry_state_no_overlap":
                    expected_classes.append("range_ops")
                _require(
                    (
                        index_valid,
                        index_ready,
                        index_live,
                        index_exclusion,
                        index_method,
                        index_classes,
                    )
                    == (True, True, True, True, "gist", expected_classes)
                )
            else:
                _require(kind == "n")
        _require(actual_keys == set(_KEYS[table]))
        inline = {
            ((name,), parent, (target,))
            for name, parent, target in re.findall(
                r"^    (\w+) uuid not null references gba\.(\w+)\((\w+)\)",
                _BLOCKS[table],
                re.MULTILINE,
            )
        }
        if actual_fks != set(_FKS[table]) | inline:
            raise ValueError(
                f"Unapproved FK for {table}: {actual_fks} expected {set(_FKS[table]) | inline}"
            )
        _require(check_names == {name for name in _CHECKS if name.startswith(table + "_")})
        _require(exclusion_names == {name for name in _EXCLUSIONS if name.startswith(table + "_")})
        _require({t[0] for t in triggers[table]} == {t[1] for t in _TRIGGERS if t[4] == table})
    for constraint, name, when, event, table, deferred, function, argument in _TRIGGERS:
        actual_trigger = next((t[1:] for t in triggers[table] if t[0] == name), None)
        _require(actual_trigger is not None)
        if actual_trigger is None:
            return
        expected_type = (
            4
            if name == "work_shift_versions_apply"
            else 31
            if event == "insert or update or delete"
            else 27
            if event == "update or delete"
            else 19
            if event == "update"
            else 7
            if when == "before"
            else 5
        )
        _require(
            actual_trigger[:5]
            == (
                expected_type,
                "O",
                bool(deferred),
                bool(deferred),
                argument.strip("'").encode() + bytes([0]) if argument else b"",
            )
        )
        _require(actual_trigger[5] == _FUNCTIONS[function])
        _require(
            actual_trigger[6:]
            == (
                False,
                None,
                "trigger",
                None,
                "",
                False,
                bool(constraint),
                True,
                "plpgsql",
                "v",
                "u",
                0,
                "f",
                False,
                function,
                None,
                "inserted_versions" if name == "work_shift_versions_apply" else None,
            )
        )
