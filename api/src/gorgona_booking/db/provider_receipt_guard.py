"""Packaged K1b-K1j integrity approvals, checked before each internal receipt write."""

import re
from importlib import resources

from gorgona_booking.db.ledger_guard import LEDGER_IMMUTABLE_SOURCE
from gorgona_booking.db.pool import RuntimeConnection
from gorgona_booking.errors import DatabaseUnavailableError

_SQL = "".join(
    (resources.files("gorgona_booking.db") / "migrations" / name).read_text(encoding="utf-8")
    for name in (
        "0044_provider_receipt_inbox.sql",
        "0045_provider_receipt_attestations.sql",
        "0046_provider_receipt_routing.sql",
        "0048_provider_revocation_record.sql",
        "0049_provider_receipt_truncate_guard.sql",
    )
)
# A later `create or replace` (0048) supersedes the earlier body of the same function.
_FUNCTIONS = list(
    dict(
        re.findall(
            r"create (?:or replace )?function gba\.(\w+)\([^;]*?as \$\$(.*?)\$\$;", _SQL, re.DOTALL
        )
    ).items()
)
_FUNCTIONS.append(("reject_ledger_mutation", LEDGER_IMMUTABLE_SOURCE))
_ROUTES = "provider_receipt_routes"
# Company-scoped tables: tenant and company policies, readable by the runtime and the writer.
_SCOPED = (
    "provider_receipt_connections",
    "provider_event_inbox",
    "provider_event_deliveries",
    "provider_event_attestations",
    "provider_verification_configs",
)
_TABLES = (*_SCOPED, _ROUTES)
# Every K policy depends on these context functions (migrations 0001 and 0009).
_TENANT_SOURCE = "select nullif(pg_catalog.current_setting('gba.tenant_id', true), '')::uuid"
_LOCATION_SOURCE = "select nullif(pg_catalog.current_setting('gba.location_id', true), '')::uuid"


def _column(table: str, name: str, kind: str, tail: str) -> list[object]:
    return [
        table,
        name,
        "timestamp with time zone" if kind == "timestamptz" else kind,
        "not null" in tail
        or "primary key" in tail
        or name in ("tenant_id", "id", "event_id", "delivery_sha256"),
        "s" if "generated always" in tail else "",
        f"(facts ->> '{name if name != 'provider_event_id' else 'event_id'}'::text)"
        if "generated always" in tail
        else "'" + re.findall(r"default '([^']+)'", tail)[0] + "'::text"
        if re.search(r"default '[^']+'", tail)
        else "CURRENT_USER"
        if "default current_user" in tail
        else "false"
        if "default false" in tail
        else "now()"
        if "default now()" in tail
        else None,
        False,  # No PUBLIC column grants, even when the table ACL stays unchanged.
    ]


_KIND = r"(uuid|text|boolean|jsonb|timestamptz|integer)\b([^\n]*)"
_COLUMNS = [
    _column(table, name, kind, tail)
    for table, block in re.findall(r"create table gba\.(\w+) \((.*?)\n\);", _SQL, re.DOTALL)
    for name, kind, tail in re.findall(r"^    (\w+) " + _KIND, block, re.MULTILINE)
] + [
    # Columns that a later migration adds (0048).
    _column(table, name, kind, tail)
    for table, block in re.findall(r"alter table gba\.(\w+)\n((?:    add column [^\n]*\n)+)", _SQL)
    for name, kind, tail in re.findall(r"^    add column (\w+) " + _KIND, block, re.MULTILINE)
]
# Defaults that a later migration sets (0049).
for _table, _name, _default in re.findall(
    r"alter table gba\.(\w+) alter column (\w+) set default ([^;]+);", _SQL
):
    for _approved in _COLUMNS:
        if _approved[:2] == [_table, _name]:
            _approved[5] = _default
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
    (
        "provider_event_attestations",
        "provider_event_attestations_check",
        7,
        "check_provider_receipt_attestation",
        False,
    ),
    (
        "provider_event_attestations",
        "provider_event_attestations_immutable",
        27,
        "reject_ledger_mutation",
        False,
    ),
    (
        "provider_event_attestations",
        "provider_event_attestations_config",
        7,
        "check_provider_attestation_config",
        False,
    ),
    (
        "provider_verification_configs",
        "provider_verification_configs_guard",
        31,
        "guard_provider_verification_config",
        False,
    ),
    (_ROUTES, "provider_receipt_routes_immutable", 27, "reject_ledger_mutation", False),
    # 0049: BEFORE TRUNCATE FOR EACH STATEMENT on every receipt table.
    *(
        (table, f"{table}_no_truncate", 34, "reject_provider_receipt_truncate", False)
        for table in _TABLES
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
    ("provider_event_attestations", "(delivery_sha256 ~ '^[0-9a-f]{64}$'::text)"),
    ("provider_event_attestations", "(verifier = 'stripe_snapshot_v1'::text)"),
    ("provider_verification_configs", "(version > 0)"),
    (
        "provider_verification_configs",
        "((secret_ref ~ '^[a-z][a-z0-9-]{0,30}:[A-Za-z0-9][A-Za-z0-9._/-]{0,199}$'::text) "
        "AND (secret_ref !~* '(^|[^A-Za-z0-9])(whsec|sk|rk|pk)_'::text))",
    ),
    *(
        (
            table,
            "(((revoked_reason IS NULL) = (revoked_at IS NULL)) "
            "AND ((revoked_at IS NULL) = (revoked_by IS NULL)) "
            "AND (revoked OR (revoked_at IS NULL)) "
            f"AND ((revoked_reason IS NULL) OR (revoked_reason = ANY (ARRAY[{reasons}]))))",
        )
        for table, reasons in (
            ("provider_receipt_connections", "'compromise'::text, 'retired'::text"),
            (
                "provider_verification_configs",
                "'rotation'::text, 'compromise'::text, 'retired'::text",
            ),
        )
    ),
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
    ("provider_event_attestations", "p", ["tenant_id", "event_id", "delivery_sha256"], None, None),
    (
        "provider_event_attestations",
        "f",
        ["tenant_id", "event_id", "delivery_sha256"],
        "provider_event_deliveries",
        ["tenant_id", "event_id", "delivery_sha256"],
    ),
    (
        "provider_event_attestations",
        "f",
        ["tenant_id", "connection_id"],
        "provider_receipt_connections",
        ["tenant_id", "id"],
    ),
    (
        "provider_event_attestations",
        "f",
        ["tenant_id", "book_id"],
        "ledger_books",
        ["tenant_id", "id"],
    ),
    (
        "provider_event_attestations",
        "f",
        ["tenant_id", "connection_id", "verification_config_id"],
        "provider_verification_configs",
        ["tenant_id", "connection_id", "id"],
    ),
    ("provider_verification_configs", "p", ["tenant_id", "id"], None, None),
    ("provider_verification_configs", "u", ["tenant_id", "connection_id", "version"], None, None),
    ("provider_verification_configs", "u", ["tenant_id", "connection_id", "id"], None, None),
    (
        "provider_verification_configs",
        "f",
        ["tenant_id", "connection_id"],
        "provider_receipt_connections",
        ["tenant_id", "id"],
    ),
    (_ROUTES, "p", ["ingress_id"], None, None),
    (_ROUTES, "u", ["tenant_id", "connection_id"], None, None),
    (
        _ROUTES,
        "f",
        ["tenant_id", "connection_id"],
        "provider_receipt_connections",
        ["tenant_id", "id"],
    ),
)
_INDEXES = (
    (
        "provider_verification_configs",
        "provider_verification_configs_active",
        "CREATE UNIQUE INDEX provider_verification_configs_active "
        "ON gba.provider_verification_configs USING btree (tenant_id, connection_id) "
        "WHERE (NOT revoked)",
    ),
)
_TENANT = "(tenant_id = gba.current_tenant_id())"
_COMPANY = "(gba.current_location_id() IS NULL)"
_POLICIES: list[tuple[str, str, bool, str, list[str], str, str]] = [
    *(
        (table, table + suffix, permissive, "*", ["public"], predicate, predicate)
        for table in _SCOPED
        for suffix, permissive, predicate in (
            ("_tenant", True, _TENANT),
            ("_company", False, _COMPANY),
        )
    ),
    (_ROUTES, _ROUTES + "_resolve", True, "r", ["gba_receipt_writer"], "true", ""),
    (_ROUTES, _ROUTES + "_provision", True, "a", ["public"], "", _TENANT),
    (_ROUTES, _ROUTES + "_company", False, "a", ["public"], "", _COMPANY),
]
# Column privileges per group; any role running the guard is checked against its own group.
_RUNTIME_INSERTS = {
    ("provider_event_inbox", column) for column in ("tenant_id", "id", "connection_id", "facts")
} | {
    ("provider_event_deliveries", column)
    for column in ("tenant_id", "event_id", "delivery_sha256", "facts")
}
_WRITER_INSERTS = _RUNTIME_INSERTS | {
    ("provider_event_attestations", column)
    for column in ("tenant_id", "event_id", "delivery_sha256", "verification_config_id")
}
_UPDATES = {
    (table, column)
    for table in ("provider_receipt_connections", "provider_verification_configs")
    for column in ("revoked", "revoked_reason")
}


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
     exists(select 1 from aclexplode(c.relacl) a where a.grantee=0),
     has_table_privilege('gba_runtime',c.oid,'SELECT'),
     has_table_privilege('gba_runtime',c.oid,'UPDATE,DELETE,TRUNCATE,REFERENCES,TRIGGER'),
     has_table_privilege('gba_receipt_writer',c.oid,'SELECT'),
     has_table_privilege('gba_receipt_writer',c.oid,'UPDATE,DELETE,TRUNCATE,REFERENCES,TRIGGER')))
  from pg_class c join pg_namespace n on n.oid=c.relnamespace
  where n.nspname='gba' and c.relname=any(%s)),
 (select jsonb_agg(jsonb_build_array(c.relname,p.polname,p.polpermissive,p.polcmd,
     array(select case when r=0 then 'public' else pg_get_userbyid(r)::text end
       from unnest(p.polroles) r order by 1),
     pg_get_expr(p.polqual,p.polrelid),pg_get_expr(p.polwithcheck,p.polrelid)))
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
     has_column_privilege(current_user,c.oid,a.attnum,'UPDATE'),
     has_column_privilege('gba_runtime',c.oid,a.attnum,'INSERT'),
     has_column_privilege('gba_runtime',c.oid,a.attnum,'UPDATE'),
     has_column_privilege('gba_receipt_writer',c.oid,a.attnum,'INSERT'),
     has_column_privilege('gba_receipt_writer',c.oid,a.attnum,'UPDATE')))
  from pg_attribute a join pg_class c on c.oid=a.attrelid
  join pg_namespace n on n.oid=c.relnamespace
  where n.nspname='gba' and c.relname=any(%s) and a.attnum>0 and not a.attisdropped),
 (select jsonb_agg(jsonb_build_array(c.relname,a.attname,format_type(a.atttypid,a.atttypmod),
     a.attnotnull,a.attgenerated,pg_get_expr(d.adbin,d.adrelid),
     exists(select 1 from aclexplode(a.attacl) acl where acl.grantee=0)))
  from pg_attribute a join pg_class c on c.oid=a.attrelid
  join pg_namespace n on n.oid=c.relnamespace
  left join pg_attrdef d on d.adrelid=c.oid and d.adnum=a.attnum
  where n.nspname='gba' and c.relname=any(%s) and a.attnum>0 and not a.attisdropped),
 (select jsonb_agg(jsonb_build_array(c.relname,i.relname,pg_get_indexdef(x.indexrelid),
     x.indisvalid and x.indisready))
  from pg_index x join pg_class i on i.oid=x.indexrelid join pg_class c on c.oid=x.indrelid
  join pg_namespace n on n.oid=c.relnamespace
  where n.nspname='gba' and c.relname=any(%s) and not exists (
     select 1 from pg_constraint k where k.conindid=x.indexrelid and k.conrelid=x.indrelid
       and k.contype in ('p','u','x'))),
 pg_catalog.pg_has_role(current_user,'gba_receipt_writer','USAGE'),
 (with recursive members(grp,member) as (
     select g.rolname,m.member from pg_auth_members m join pg_roles g on g.oid=m.roleid
     where g.rolname in ('gba_runtime','gba_receipt_writer')
     union select s.grp,m.member from members s join pg_auth_members m on m.roleid=s.member)
  select (select count(*)=2 and bool_and(not (rolcanlogin or rolsuper or rolbypassrls
          or rolcreaterole or rolcreatedb or rolreplication))
        from pg_roles where rolname in ('gba_runtime','gba_receipt_writer'))
    and not exists (select 1 from pg_auth_members m join pg_roles g on g.oid=m.member
        where g.rolname in ('gba_runtime','gba_receipt_writer'))
    and not exists (select member from members where grp='gba_runtime'
        intersect select member from members where grp='gba_receipt_writer')
    and not exists (select 1 from members s join pg_roles r on r.oid=s.member
        where r.rolsuper or r.rolbypassrls)),
 (select count(*)=cardinality(%s::text[]) and bool_and(c.relkind='r' and c.relpersistence='p'
     and not exists (select 1 from pg_rewrite w where w.ev_class=c.oid)
     and not exists (select 1 from aclexplode(c.relacl) a where a.grantee<>c.relowner
       and (a.is_grantable or a.grantee not in
         (to_regrole('gba_runtime')::oid,to_regrole('gba_receipt_writer')::oid)))
     and not exists (select 1 from pg_attribute t cross join lateral aclexplode(t.attacl) a
       where t.attrelid=c.oid and t.attnum>0 and (a.is_grantable or a.grantee not in
         (to_regrole('gba_runtime')::oid,to_regrole('gba_receipt_writer')::oid))))
  from pg_class c join pg_namespace n on n.oid=c.relnamespace
  where n.nspname='gba' and c.relname=any(%s)),
 (select bool_and(not exists (select 1 from aclexplode(p.proacl) a where a.grantee<>p.proowner
     and (a.is_grantable or a.grantee not in
       (to_regrole('gba_runtime')::oid,to_regrole('gba_receipt_writer')::oid))))
  from pg_proc p join pg_namespace n on n.oid=p.pronamespace
  where n.nspname='gba' and p.proname=any(%s)),
 (select count(*)=2 and bool_and(l.lanname='sql' and p.provolatile='s' and p.proparallel='s'
     and not p.prosecdef and p.proconfig is null and p.pronargs=0 and p.prokind='f'
     and p.prorettype='uuid'::regtype and p.proacl is not null
     and btrim(p.prosrc,E' \\t\\r\\n')=case p.proname when 'current_tenant_id' then %s else %s end
     and not exists (select 1 from aclexplode(p.proacl) a where a.grantee<>p.proowner
       and (a.is_grantable or a.grantee not in
         (to_regrole('gba_runtime')::oid,to_regrole('gba_receipt_writer')::oid))))
  from pg_proc p join pg_namespace n on n.oid=p.pronamespace
  join pg_language l on l.oid=p.prolang
  where n.nspname='gba' and p.proname in ('current_tenant_id','current_location_id'))
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
                tables,
                tables,
                tables,
                [name for name, _ in _FUNCTIONS],
                _TENANT_SOURCE,
                _LOCATION_SOURCE,
            ),
        )
    ).fetchone()
    valid = row is not None
    if row is not None:
        (
            boundary,
            policies,
            triggers,
            functions,
            checks,
            keys,
            privileges,
            columns,
            indexes,
            is_writer,
            roles_safe,
            tables_safe,
            function_acls_safe,
            context_safe,
        ) = row
        # K1g (IR-05): group membership, table shape and ACLs, and the RLS context functions.
        valid = all(
            check is True for check in (roles_safe, tables_safe, function_acls_safe, context_safe)
        )
        valid &= sorted(boundary or []) == sorted(
            [
                t,
                True,
                True,
                is_writer or t != _ROUTES,
                False,
                False,
                t != _ROUTES,
                False,
                True,
                False,
            ]
            for t in tables
        )
        actual_policies = [
            [*p[:5], _compact(p[5] or ""), _compact(p[6] or "")] for p in policies or []
        ]
        valid &= sorted(actual_policies) == sorted(
            [*p[:5], _compact(p[5]), _compact(p[6])] for p in _POLICIES
        )
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
        inserts = _WRITER_INSERTS if is_writer else _RUNTIME_INSERTS
        valid &= all(
            [own_insert, own_update, runtime_insert, runtime_update, writer_insert, writer_update]
            == [
                (table, column) in inserts,
                (table, column) in _UPDATES,
                (table, column) in _RUNTIME_INSERTS,
                (table, column) in _UPDATES,
                (table, column) in _WRITER_INSERTS,
                (table, column) in _UPDATES,
            ]
            for (
                table,
                column,
                own_insert,
                own_update,
                runtime_insert,
                runtime_update,
                writer_insert,
                writer_update,
            ) in privileges or []
        )
        valid &= sorted(columns or []) == sorted(_COLUMNS)
        valid &= sorted([i[0], i[1], _compact(i[2]), i[3]] for i in indexes or []) == sorted(
            [table, name, _compact(definition), True] for table, name, definition in _INDEXES
        )
    if not valid:
        raise DatabaseUnavailableError("Provider receipt schema is unavailable")
