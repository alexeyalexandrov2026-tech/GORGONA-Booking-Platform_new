"""H4-only, repository-owned schema approvals; existing readiness is unchanged."""

import re
from importlib import resources

from gorgona_booking.db.pool import RuntimeConnection
from gorgona_booking.errors import DatabaseUnavailableError

_MIGRATIONS = resources.files("gorgona_booking.db") / "migrations"
_SQL = (_MIGRATIONS / "0031_provider_admission.sql").read_text(encoding="utf-8")
_SOURCES = dict(
    re.findall(
        r"create (?:or replace )?function gba\.(\w+)\([^;]*?as \$\$(.*?)\$\$;",
        "\n".join(
            (_MIGRATIONS / name).read_text(encoding="utf-8")
            for name in (
                "0015_counterparties.sql",
                "0020_ledger.sql",
                "0031_provider_admission.sql",
            )
        ),
        re.DOTALL,
    )
)
_BLOCKS = dict(re.findall(r"create table gba\.(\w+)\s*\((.*?)\n\);", _SQL, re.DOTALL))
ADMISSION_TABLES = tuple(_BLOCKS)
_TYPES = r"(uuid|text|integer|smallint|boolean|timestamptz|xid8)"
_INSERTS = {
    table: {name.strip() for name in columns.split(",")}
    for columns, table in re.findall(r"grant insert \(([^)]+)\) on gba\.(\w+)", _SQL)
}
_COLUMNS = tuple(
    (table, name, kind, "not null" in tail, name in _INSERTS[table])
    for table, block in _BLOCKS.items()
    for name, kind, tail in re.findall(rf"^    (\w+)\s+{_TYPES}\b([^\n]*)", block, re.MULTILINE)
)
_DEFAULTS = tuple(
    (
        table,
        name,
        "pg_current_xact_id()"
        if "pg_current_xact_id" in tail
        else "'manually_provided_unverified'::text"
        if "manually_provided_unverified" in tail
        else "false"
        if "default false" in tail
        else "now()",
    )
    for table, block in _BLOCKS.items()
    for name, _, tail in re.findall(rf"^    (\w+)\s+{_TYPES}\b([^\n]*)", block, re.MULTILINE)
    if " default " in tail
)
_KEYS = tuple(
    (table, "p" if kind == "primary key" else "u", [x.strip() for x in columns.split(",")])
    for table, block in _BLOCKS.items()
    for kind, columns in re.findall(r"(primary key|unique)\s*\(([^)]+)\)", block)
)
_FKS = tuple(
    (table, [x.strip() for x in columns.split(",")], parent, [x.strip() for x in other.split(",")])
    for table, block in _BLOCKS.items()
    for columns, parent, other in re.findall(
        r"foreign key\s*\(([^)]+)\)\s*references gba\.(\w+)\(([^)]+)\)", block
    )
) + tuple(
    (table, [column], parent, [other])
    for table, block in _BLOCKS.items()
    for column, _, parent, other in re.findall(
        rf"^    (\w+)\s+{_TYPES}\b[^\n]*?references gba\.(\w+)\(([^)]+)\)", block, re.MULTILINE
    )
)
_TRIGGERS = tuple(
    (
        table,
        trigger,
        27 if event == "update or delete" else 7 if before == "before" else 5,
        function,
        bool(deferred),
        argument.strip("'").encode() + b"\x00" if argument else b"",
        _SOURCES[function],
    )
    for _, trigger, before, event, table, deferred, function, argument in re.findall(
        r"create (constraint )?trigger (\w+) (before|after) (insert|update or delete) "
        r"on gba\.(\w+) (deferrable initially deferred )?for each row execute function "
        r"gba\.(\w+)\(([^)]*)\);",
        _SQL,
    )
)
_HELPERS = (
    (
        "gba.admission_safe_text(text,integer)",
        "boolean",
        "i",
        "s",
        "sql",
        _SOURCES["admission_safe_text"],
    ),
    (
        "gba.assert_admission_consistent(uuid,uuid,uuid)",
        "void",
        "v",
        "u",
        "plpgsql",
        _SOURCES["assert_admission_consistent"],
    ),
)

# Explicit PostgreSQL 18 deparse approvals. Never adopt predicates from a target DB.
_CHECKS = (
    ("provider_admission_versions", "revision", "(revision > 0)"),
    (
        "provider_admission_versions",
        "state",
        "(state = ANY (ARRAY['draft'::text, 'submitted'::text, 'withdrawn'::text]))",
    ),
    ("provider_admission_versions", "provider", "(provider = 'stripe_connect'::text)"),
    ("provider_admission_versions", "country", "(country ~ '^[A-Z]{2}$'::text)"),
    ("provider_admission_versions", "activity", "gba.admission_safe_text(business_activity, 500)"),
    (
        "provider_admission_versions",
        "operation",
        "(requested_operation = ANY (ARRAY['charge'::text, "
        "'refund'::text, 'transfer'::text, 'payout'::text]))",
    ),
    (
        "provider_admission_versions",
        "assessment",
        "(assessment = ANY (ARRAY['not_checked'::text, 'suspended'::text, 'unsupported'::text]))",
    ),
    ("provider_admission_versions", "account", "gba.admission_safe_text(account_reference, 160)"),
    (
        "provider_admission_versions",
        "account_format",
        "(account_reference ~ '^[A-Za-z0-9][A-Za-z0-9._:-]{0,159}$'::text)",
    ),
    ("provider_admission_versions", "notes", "gba.admission_safe_text(notes, 2000)"),
    (
        "provider_admission_versions",
        "evidence_count",
        "((evidence_count >= 0) AND (evidence_count <= 8))",
    ),
    (
        "provider_admission_versions",
        "evidence_status",
        "(evidence_status = 'manually_provided_unverified'::text)",
    ),
    *(
        ("provider_admission_versions", kind, f"(NOT {kind}_enabled)")
        for kind in ("charge", "refund", "transfer", "payout")
    ),
    ("provider_admission_evidence", "number", "((reference_no >= 1) AND (reference_no <= 8))"),
    ("provider_admission_evidence", "reference", "gba.admission_safe_text(reference, 256)"),
    *(
        (
            table,
            "operation",
            "(operation = ANY (ARRAY['admission_draft'::text, "
            "'admission_submit'::text, 'admission_withdraw'::text]))",
        )
        for table in ("provider_admission_receipts", "provider_admission_cancellations")
    ),
    *(
        (table, "key", "(idempotency_key ~ '^[A-Za-z0-9._:-]{8,255}$'::text)")
        for table in ("provider_admission_receipts", "provider_admission_cancellations")
    ),
    ("provider_admission_receipts", "hash", "(request_hash ~ '^[0-9a-f]{64}$'::text)"),
    ("provider_admission_receipts", "actor", "(actor_key = ('user:'::text || (created_by)::text))"),
    (
        "provider_admission_cancellations",
        "actor",
        "(actor_key = ('user:'::text || (cancelled_by)::text))",
    ),
    (
        "provider_admission_cancellations",
        "revision",
        "((revision >= 1) AND ((operation = 'admission_draft'::text) OR (revision >= 2)))",
    ),
)
_DECLARED_CHECKS = set(re.findall(r"constraint (\w+) check", _SQL))
if {f"{table}_{suffix}_check" for table, suffix, _ in _CHECKS} != _DECLARED_CHECKS:
    raise RuntimeError("Every H4 CHECK needs an explicit packaged approval")


def _values(rows: tuple[tuple[object, ...], ...], casts: str) -> tuple[str, list[object]]:
    return ",".join(casts for _ in rows), [value for row in rows for value in row]


_PARAMETERS: list[object] = [list(ADMISSION_TABLES), list(ADMISSION_TABLES)]
_BOUNDARY = """
select not exists (
    select 1 from unnest(%s::text[]) expected(table_name)
    left join pg_catalog.pg_class c on c.oid=pg_catalog.to_regclass('gba.'||expected.table_name)
    where c.oid is null or c.relkind<>'r' or not c.relrowsecurity or not c.relforcerowsecurity
       or not pg_catalog.has_table_privilege(current_user,c.oid,'SELECT')
       or
pg_catalog.has_table_privilege(current_user,c.oid,'UPDATE,DELETE,TRUNCATE,REFERENCES,TRIGGER')
       or exists(select 1 from pg_catalog.aclexplode(c.relacl) a where a.grantee=0)
) and not exists (
    select 1 from unnest(%s::text[]) expected(table_name)
    left join pg_catalog.pg_policy tenant_policy
      on tenant_policy.polrelid=pg_catalog.to_regclass('gba.'||expected.table_name)
     and tenant_policy.polname=expected.table_name||'_tenant_isolation'
    left join pg_catalog.pg_policy scope_policy
      on scope_policy.polrelid=tenant_policy.polrelid
     and scope_policy.polname=expected.table_name||'_unrestricted_scope'
    where tenant_policy.oid is null or not tenant_policy.polpermissive
       or tenant_policy.polcmd<>'*' or tenant_policy.polroles<>array[0::oid]
       or
regexp_replace(pg_catalog.pg_get_expr(tenant_policy.polqual,tenant_policy.polrelid),'[[:space:]]','','g')
            is distinct from '(tenant_id=gba.current_tenant_id())'
       or tenant_policy.polwithcheck is distinct from tenant_policy.polqual
       or scope_policy.oid is null or scope_policy.polpermissive or scope_policy.polcmd<>'*'
       or scope_policy.polroles<>array[(select oid from pg_catalog.pg_roles where
rolname='gba_runtime')]
       or
regexp_replace(pg_catalog.pg_get_expr(scope_policy.polqual,scope_policy.polrelid),'[[:space:]]','','g')
            is distinct from '(gba.current_location_id()ISNULL)'
       or scope_policy.polwithcheck is distinct from scope_policy.polqual
       or exists(select 1 from pg_catalog.pg_policy extra where
extra.polrelid=tenant_policy.polrelid
            and extra.polname not in (tenant_policy.polname,scope_policy.polname))
)
"""
_FRAGMENTS = (
    (
        _TRIGGERS,
        "(%s,%s,%s::int,%s,%s::boolean,%s::bytea,%s::text)",
        """
and not exists (select 1 from (values __VALUES__)
expected(table_name,trigger_name,kind,function_name,deferred,arguments,source)
    left join pg_catalog.pg_trigger t on
t.tgrelid=pg_catalog.to_regclass('gba.'||expected.table_name) and
t.tgname=expected.trigger_name
    left join pg_catalog.pg_proc f on f.oid=t.tgfoid
    where t.oid is null or t.tgtype<>expected.kind or t.tgenabled<>'O' or t.tgisinternal
      or t.tgqual is not null or t.tgattr<>''::int2vector or t.tgargs<>expected.arguments
      or t.tgnargs<>case when octet_length(expected.arguments)=0 then 0 else 1 end
      or t.tgdeferrable<>expected.deferred or t.tginitdeferred<>expected.deferred
      or (t.tgconstraint<>0)<>expected.deferred
      or f.oid is distinct from pg_catalog.to_regprocedure('gba.'||expected.function_name||'()')
      or f.prosecdef or f.proconfig is not null or f.provolatile<>'v' or f.proparallel<>'u'
      or f.prokind<>'f' or f.pronargs<>0 or f.prorettype<>'pg_catalog.trigger'::regtype
      or f.prolang<>(select oid from pg_catalog.pg_language where lanname='plpgsql')
      or f.prosrc is distinct from expected.source)
""",
    ),
    (
        _HELPERS,
        "(%s,%s,%s,%s,%s,%s::text)",
        """
and not exists (select 1 from (values __VALUES__)
expected(signature,result,volatility,parallel,language,source)
    left join pg_catalog.pg_proc f on f.oid=pg_catalog.to_regprocedure(expected.signature)
    where f.oid is null or f.prosecdef or f.proconfig is not null or f.prokind<>'f'
      or f.provolatile::text<>expected.volatility or f.proparallel::text<>expected.parallel
      or f.prorettype is distinct from pg_catalog.to_regtype(expected.result)
      or f.prolang<>(select oid from pg_catalog.pg_language where lanname=expected.language)
      or f.prosrc is distinct from expected.source
      or not pg_catalog.has_function_privilege(current_user,f.oid,'EXECUTE')
      or exists(select 1 from pg_catalog.aclexplode(f.proacl) a where a.grantee=0))
""",
    ),
    (
        _COLUMNS,
        "(%s,%s,%s,%s::boolean,%s::boolean)",
        """
and not exists (select 1 from (values __VALUES__)
expected(table_name,column_name,kind,required,insertable)
    left join pg_catalog.pg_attribute a on
a.attrelid=pg_catalog.to_regclass('gba.'||expected.table_name)
      and a.attname=expected.column_name and not a.attisdropped
    where a.attnum is null or a.atttypid is distinct from pg_catalog.to_regtype(expected.kind)
      or a.attnotnull<>expected.required or a.attgenerated<>'' or a.attidentity<>''
      or
pg_catalog.has_column_privilege(current_user,a.attrelid,a.attnum,'INSERT')<>expected.insertable
      or pg_catalog.has_column_privilege(current_user,a.attrelid,a.attnum,'UPDATE'))
""",
    ),
    (
        _DEFAULTS,
        "(%s,%s,%s::text)",
        """
and not exists (select 1 from (values __VALUES__) expected(table_name,column_name,expression)
    left join pg_catalog.pg_attribute a on
a.attrelid=pg_catalog.to_regclass('gba.'||expected.table_name) and
a.attname=expected.column_name and not a.attisdropped
    left join pg_catalog.pg_attrdef d on d.adrelid=a.attrelid and d.adnum=a.attnum
    where d.oid is null or pg_catalog.pg_get_expr(d.adbin,d.adrelid) is distinct from
expected.expression)
""",
    ),
    (
        _KEYS,
        "(%s,%s,%s::text[])",
        """
and not exists (select 1 from (values __VALUES__) expected(table_name,kind,columns) where not
exists (
    select 1 from pg_catalog.pg_constraint c where
c.conrelid=pg_catalog.to_regclass('gba.'||expected.table_name)
      and c.contype::text=expected.kind and c.convalidated and not c.condeferrable
      and array(select a.attname::text from unnest(c.conkey) with ordinality k(n,p)
        join pg_catalog.pg_attribute a on a.attrelid=c.conrelid and a.attnum=k.n order by
k.p)=expected.columns))
""",
    ),
    (
        _FKS,
        "(%s,%s::text[],%s,%s::text[])",
        """
and not exists (select 1 from (values __VALUES__)
expected(table_name,columns,parent_name,parent_columns) where not exists (
    select 1 from pg_catalog.pg_constraint c where
c.conrelid=pg_catalog.to_regclass('gba.'||expected.table_name)
      and c.contype='f' and c.confrelid=pg_catalog.to_regclass('gba.'||expected.parent_name)
      and c.convalidated and not c.condeferrable and c.confupdtype='a' and c.confdeltype='a'
and c.confmatchtype='s'
      and array(select a.attname::text from unnest(c.conkey) with ordinality k(n,p)
        join pg_catalog.pg_attribute a on a.attrelid=c.conrelid and a.attnum=k.n order by
k.p)=expected.columns
      and array(select a.attname::text from unnest(c.confkey) with ordinality k(n,p)
        join pg_catalog.pg_attribute a on a.attrelid=c.confrelid and a.attnum=k.n order by
k.p)=expected.parent_columns))
""",
    ),
    (
        tuple(
            (table, f"{table}_{suffix}_check", expression) for table, suffix, expression in _CHECKS
        ),
        "(%s,%s,%s::text)",
        """
and not exists (select 1 from (values __VALUES__) expected(table_name,constraint_name,expression)
    left join pg_catalog.pg_constraint c on
c.conrelid=pg_catalog.to_regclass('gba.'||expected.table_name) and
c.conname=expected.constraint_name
    where c.oid is null or c.contype<>'c' or not c.convalidated or c.connoinherit or not
c.conislocal
      or pg_catalog.pg_get_expr(c.conbin,c.conrelid) is distinct from expected.expression)
""",
    ),
)
for _rows, _casts, _fragment in _FRAGMENTS:
    _placeholders, _arguments = _values(_rows, _casts)
    _BOUNDARY += _fragment.replace("__VALUES__", _placeholders)
    _PARAMETERS.extend(_arguments)


async def assert_admission_ready(conn: RuntimeConnection) -> None:
    """Only admission endpoints demand H4; existing financial readiness stays intact."""
    result = await (await conn.execute(_BOUNDARY, _PARAMETERS)).fetchone()
    if result is None or result[0] is not True:
        raise DatabaseUnavailableError("Required provider-admission controls are not ready")
