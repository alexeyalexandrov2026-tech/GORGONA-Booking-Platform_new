"""Packaged K1b integrity approvals, checked before each internal receipt write."""

import re
from importlib import resources

from gorgona_booking.db.ledger_guard import LEDGER_IMMUTABLE_SOURCE
from gorgona_booking.db.pool import RuntimeConnection
from gorgona_booking.errors import DatabaseUnavailableError

_SQL = (
    resources.files("gorgona_booking.db") / "migrations" / "0044_provider_receipt_inbox.sql"
).read_text(encoding="utf-8")
_FUNCTIONS = re.findall(r"create function gba\.(\w+)\([^;]*?as \$\$(.*?)\$\$;", _SQL, re.DOTALL)
_FUNCTIONS.append(("reject_ledger_mutation", LEDGER_IMMUTABLE_SOURCE))
_TABLES = ("provider_receipt_connections", "provider_event_inbox", "provider_event_deliveries")
_COLUMNS = [
    [
        table,
        name,
        "timestamp with time zone" if kind == "timestamptz" else kind,
        "not null" in tail or name in ("tenant_id", "id", "event_id", "delivery_sha256"),
        "s" if "generated always" in tail else "",
        f"(facts ->> '{name if name != 'provider_event_id' else 'event_id'}'::text)"
        if "generated always" in tail
        else "'not_admitted'::text"
        if "default 'not_admitted'" in tail
        else "false"
        if "default false" in tail
        else "now()"
        if "default now()" in tail
        else None,
        False,  # No PUBLIC column grants, even when the table ACL stays unchanged.
    ]
    for table, block in re.findall(r"create table gba\.(\w+) \((.*?)\n\);", _SQL, re.DOTALL)
    for name, kind, tail in re.findall(
        r"^    (\w+) (uuid|text|boolean|jsonb|timestamptz)\b([^\n]*)", block, re.MULTILINE
    )
]
_TRIGGERS = (
    (
        "provider_receipt_connections",
        "provider_receipt_connections_identity",
        27,
        "guard_provider_receipt_connection",
        False,
    ),
    ("provider_event_inbox", "provider_event_inbox_immutable", 27, "reject_ledger_mutation", False),
    (
        "provider_event_deliveries",
        "provider_event_deliveries_immutable",
        27,
        "reject_ledger_mutation",
        False,
    ),
    ("provider_event_inbox", "provider_event_inbox_check", 7, "check_provider_receipt", False),
    (
        "provider_event_deliveries",
        "provider_event_deliveries_check",
        7,
        "check_provider_receipt",
        False,
    ),
    (
        "provider_event_inbox",
        "provider_event_inbox_complete",
        5,
        "provider_receipt_has_delivery",
        True,
    ),
)
_CHECKS = (
    ("provider_receipt_connections", "(namespace ~ '^[A-Za-z0-9][A-Za-z0-9._:-]{0,99}$'::text)"),
    ("provider_receipt_connections", "(account_id ~ '^acct_[A-Za-z0-9]{1,100}$'::text)"),
    (
        "provider_receipt_connections",
        "(api_version ~ '^[0-9]{4}-[0-9]{2}-[0-9]{2}\\.[a-z][a-z0-9-]{0,39}$'::text)",
    ),
    ("provider_receipt_connections", "(admission = 'not_admitted'::text)"),
    ("provider_receipt_connections", "(NOT livemode)"),
    ("provider_event_inbox", "gba.provider_receipt_facts_valid(facts)"),
    ("provider_event_deliveries", "(delivery_sha256 ~ '^[0-9a-f]{64}$'::text)"),
    ("provider_event_deliveries", "gba.provider_receipt_facts_valid(facts)"),
)
_KEYS = (
    ("provider_receipt_connections", "p", ["tenant_id", "id"], None, None),
    ("provider_receipt_connections", "u", ["namespace", "account_id"], None, None),
    (
        "provider_receipt_connections",
        "f",
        ["tenant_id", "book_id"],
        "ledger_books",
        ["tenant_id", "id"],
    ),
    ("provider_event_inbox", "p", ["tenant_id", "id"], None, None),
    ("provider_event_inbox", "u", ["namespace", "account_id", "provider_event_id"], None, None),
    (
        "provider_event_inbox",
        "f",
        ["tenant_id", "connection_id"],
        "provider_receipt_connections",
        ["tenant_id", "id"],
    ),
    ("provider_event_deliveries", "p", ["tenant_id", "event_id", "delivery_sha256"], None, None),
    (
        "provider_event_deliveries",
        "f",
        ["tenant_id", "event_id"],
        "provider_event_inbox",
        ["tenant_id", "id"],
    ),
)


def _compact(source: str) -> str:
    return re.sub(r"\s+", "", source)


async def assert_provider_receipt_ready(conn: RuntimeConnection) -> None:
    tables = list(_TABLES)
    # One catalog round trip. Expected source is packaged, never learned from the target DB.
    row = await (
        await conn.execute(
            """
select
 (select jsonb_agg(jsonb_build_array(c.relname,c.relrowsecurity,c.relforcerowsecurity,
     has_table_privilege(current_user,c.oid,'SELECT'),
     has_table_privilege(current_user,c.oid,'UPDATE,DELETE,TRUNCATE,REFERENCES,TRIGGER'),
     exists(select 1 from aclexplode(c.relacl) a where a.grantee=0)))
  from pg_class c join pg_namespace n on n.oid=c.relnamespace
  where n.nspname='gba' and c.relname=any(%s)),
 (select jsonb_agg(jsonb_build_array(c.relname,p.polname,p.polpermissive,p.polcmd,
     p.polroles::bigint[],pg_get_expr(p.polqual,p.polrelid),pg_get_expr(p.polwithcheck,p.polrelid)))
  from pg_policy p join pg_class c on c.oid=p.polrelid
  join pg_namespace n on n.oid=c.relnamespace where n.nspname='gba' and c.relname=any(%s)),
 (select jsonb_agg(jsonb_build_array(c.relname,t.tgname,t.tgtype,p.proname,t.tgdeferrable,
     t.tginitdeferred,t.tgenabled,
     t.tgfoid=to_regprocedure('gba.'||p.proname||'()') and t.tgqual is null
       and t.tgnargs=0 and t.tgattr=''::int2vector and octet_length(t.tgargs)=0
       and (t.tgconstraint<>0)=t.tgdeferrable and t.tgparentid=0
       and t.tgoldtable is null and t.tgnewtable is null))
  from pg_trigger t join pg_class c on c.oid=t.tgrelid
  join pg_namespace n on n.oid=c.relnamespace join pg_proc p on p.oid=t.tgfoid
  where n.nspname='gba' and c.relname=any(%s) and not t.tgisinternal),
 (select jsonb_agg(jsonb_build_array(p.proname,p.prosrc,p.prosecdef,p.proconfig,p.provolatile,
     p.proparallel,exists(select 1 from aclexplode(p.proacl) a where a.grantee=0),
     l.lanname,p.oid=to_regprocedure('gba.'||p.proname||case p.proname
       when 'provider_receipt_integer' then '(jsonb,numeric)'
       when 'provider_receipt_facts_valid' then '(jsonb)' else '()' end)))
  from pg_proc p join pg_namespace n on n.oid=p.pronamespace
  join pg_language l on l.oid=p.prolang
  where n.nspname='gba' and p.proname=any(%s)),
 (select jsonb_agg(jsonb_build_array(c.relname,pg_get_expr(k.conbin,k.conrelid),k.convalidated))
  from pg_constraint k join pg_class c on c.oid=k.conrelid
  join pg_namespace n on n.oid=c.relnamespace
  where n.nspname='gba' and c.relname=any(%s) and k.contype='c'),
 (select jsonb_agg(jsonb_build_array(c.relname,k.contype,
     array(select a.attname from unnest(k.conkey) with ordinality x(num,ord)
       join pg_attribute a on a.attrelid=c.oid and a.attnum=x.num order by x.ord),
     parent_ns.nspname||'.'||parent.relname,case when k.contype='f' then
       array(select a.attname from unnest(k.confkey) with ordinality x(num,ord)
       join pg_attribute a on a.attrelid=parent.oid and a.attnum=x.num order by x.ord) end,
     k.convalidated,k.condeferrable,k.confdeltype))
  from pg_constraint k join pg_class c on c.oid=k.conrelid
  join pg_namespace n on n.oid=c.relnamespace left join pg_class parent on parent.oid=k.confrelid
  left join pg_namespace parent_ns on parent_ns.oid=parent.relnamespace
  where n.nspname='gba' and c.relname=any(%s) and k.contype in ('p','u','f')),
 (select jsonb_agg(jsonb_build_array(c.relname,a.attname,
     has_column_privilege(current_user,c.oid,a.attnum,'INSERT'),
     has_column_privilege(current_user,c.oid,a.attnum,'UPDATE')))
  from pg_attribute a join pg_class c on c.oid=a.attrelid
  join pg_namespace n on n.oid=c.relnamespace
  where n.nspname='gba' and c.relname=any(%s) and a.attnum>0 and not a.attisdropped),
 (select jsonb_agg(jsonb_build_array(c.relname,a.attname,format_type(a.atttypid,a.atttypmod),
     a.attnotnull,a.attgenerated,pg_get_expr(d.adbin,d.adrelid),
     exists(select 1 from aclexplode(a.attacl) acl where acl.grantee=0)))
  from pg_attribute a join pg_class c on c.oid=a.attrelid
  join pg_namespace n on n.oid=c.relnamespace
  left join pg_attrdef d on d.adrelid=c.oid and d.adnum=a.attnum
  where n.nspname='gba' and c.relname=any(%s) and a.attnum>0 and not a.attisdropped)
""",
            (
                tables,
                tables,
                tables,
                [name for name, _ in _FUNCTIONS],
                tables,
                tables,
                tables,
                tables,
            ),
        )
    ).fetchone()
    valid = row is not None
    if row is not None:
        boundary, policies, triggers, functions, checks, keys, privileges, columns = row
        valid = sorted(boundary or []) == sorted(
            [[t, True, True, True, False, False] for t in tables]
        )
        expected_policies = [
            [t, t + suffix, permissive, "*", [0], _compact(predicate), _compact(predicate)]
            for t in tables
            for suffix, permissive, predicate in (
                ("_tenant", True, "(tenant_id = gba.current_tenant_id())"),
                ("_company", False, "(gba.current_location_id() IS NULL)"),
            )
        ]
        actual_policies = [
            [*p[:5], _compact(p[5] or ""), _compact(p[6] or "")] for p in policies or []
        ]
        valid &= sorted(actual_policies) == sorted(expected_policies)
        valid &= sorted(triggers or []) == sorted([[*list(t), t[4], "O", True] for t in _TRIGGERS])
        expected_functions = [
            [
                name,
                _compact(body),
                False,
                None if name == "reject_ledger_mutation" else ["search_path=pg_catalog"],
                "i"
                if name in ("provider_receipt_integer", "provider_receipt_facts_valid")
                else "v",
                "s"
                if name in ("provider_receipt_integer", "provider_receipt_facts_valid")
                else "u",
                False,
                "sql" if name == "provider_receipt_integer" else "plpgsql",
                True,
            ]
            for name, body in _FUNCTIONS
        ]
        actual_functions = [[*f[:1], _compact(f[1]), *f[2:]] for f in functions or []]
        valid &= sorted(actual_functions) == sorted(expected_functions)
        valid &= sorted([c[0], _compact(c[1]), c[2]] for c in checks or []) == sorted(
            [t, _compact(predicate), True] for t, predicate in _CHECKS
        )
        valid &= sorted(keys or []) == sorted(
            [
                *k[:3],
                "gba." + k[3] if k[3] else None,
                k[4],
                True,
                False,
                "a" if k[1] == "f" else " ",
            ]
            for k in _KEYS
        )
        inserts = {
            "provider_receipt_connections": set(),
            "provider_event_inbox": {"tenant_id", "id", "connection_id", "facts"},
            "provider_event_deliveries": {"tenant_id", "event_id", "delivery_sha256", "facts"},
        }
        valid &= all(
            insert == (column in inserts[table])
            and update == (table == "provider_receipt_connections" and column == "revoked")
            for table, column, insert, update in privileges or []
        )
        valid &= sorted(columns or []) == sorted(_COLUMNS)
    if not valid:
        raise DatabaseUnavailableError("Provider receipt schema is unavailable")
