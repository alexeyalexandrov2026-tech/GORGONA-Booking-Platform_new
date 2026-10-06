"""Approved H1 controls from packaged SQL; never learn expectations from a DB."""

import re
from importlib import resources

_SQL = (
    resources.files("gorgona_booking.db") / "migrations" / "0021_invoice_accrual.sql"
).read_text(encoding="utf-8")
_G = (resources.files("gorgona_booking.db") / "migrations" / "0020_ledger.sql").read_text(
    encoding="utf-8"
)
_SOURCES = dict(
    re.findall(r"create function gba\.(\w+)\([^;]*?as \$\$(.*?)\$\$;", _G + _SQL, re.DOTALL)
)
_BLOCKS = dict(re.findall(r"create table gba\.(\w+)\s*\((.*?)\n\);", _SQL, re.DOTALL))
FINANCIAL_TABLES = tuple(_BLOCKS)
_MONEY = tuple(t for t in FINANCIAL_TABLES if not t.startswith("financial_command_"))
_TRIGGERS = (
    *((t, f"{t}_immutable", 27, "reject_ledger_mutation", False) for t in FINANCIAL_TABLES),
    *((t, f"{t}_lock", 7, "lock_financial_record", False) for t in FINANCIAL_TABLES),
    *((t, f"{t}_require_workflow", 7, "require_financial_workflow", False) for t in _MONEY),
    *(
        (t, f"{t}_consistent", 5, "check_invoice_integrity", True)
        for t in FINANCIAL_TABLES
        if t != "financial_command_cancellations"
    ),
    (
        "financial_document_versions",
        "financial_versions_next",
        7,
        "enforce_financial_version",
        False,
    ),
    ("financial_document_lines", "financial_lines_check", 7, "enforce_financial_line", False),
    ("journal_entries", "journal_entries_invoice_origin", 7, "enforce_invoice_origin", False),
    *(
        (t, f"{t}_invoice_consistent", 5, "check_invoice_integrity", True)
        for t in ("journal_entries", "journal_lines")
    ),
)


def _columns(value: str) -> list[str]:
    return [x.strip() for x in value.split(",")]


_KEYS = tuple(
    (t, "p" if kind == "primary key" else "u", _columns(cols))
    for t, body in _BLOCKS.items()
    for kind, cols in re.findall(r"(primary key|unique)\s*\(([^)]+)\)", body)
)
_FK_PATTERN = (
    r"foreign key\s*\(([^)]+)\)\s*references\s+gba\.(\w+)\s*\(([^)]+)\)"
    r"(\s+deferrable\s+initially\s+deferred)?"
)
_FKS = tuple(
    (t, _columns(cols), parent, _columns(other), bool(deferred))
    for t, body in (
        *_BLOCKS.items(),
        *re.findall(r"alter table gba\.(\w+) add constraint ([^;]+);", _SQL, re.DOTALL),
    )
    for cols, parent, other, deferred in re.findall(_FK_PATTERN, body)
)
_COLUMNS = tuple(
    (t, name, kind, "not null" in rest)
    for t, body in _BLOCKS.items()
    for name, kind, rest in re.findall(
        r"^    (\w+)\s+(uuid|text|integer|smallint|bigint|date|timestamptz|xid8)\b([^\n]*)",
        body,
        re.MULTILINE,
    )
)
_PRIVATE = tuple(
    (t, name)
    for t, name, _, _ in _COLUMNS
    if name in ("created_at", "created_transaction", "cancelled_at")
)
FINANCIAL_PARAMETERS: tuple[object, ...] = tuple(
    x
    for t, trigger, kind, function, deferred in _TRIGGERS
    for x in (t, trigger, kind, "gba." + function + "()", deferred, _SOURCES[function])
)
FINANCIAL_PARAMETERS += (
    _SOURCES["assert_invoice_consistent"],
    list(FINANCIAL_TABLES),
    "(tenant_id=gba.current_tenant_id())",
    list(FINANCIAL_TABLES),
)
FINANCIAL_PARAMETERS += tuple(x for row in _KEYS for x in row)
FINANCIAL_PARAMETERS += tuple(x for row in _FKS for x in row)
FINANCIAL_PARAMETERS += tuple(x for row in _COLUMNS for x in row)
FINANCIAL_PARAMETERS += tuple(x for row in _PRIVATE for x in row)
FINANCIAL_PARAMETERS += (list(FINANCIAL_TABLES),)
FINANCIAL_PARAMETERS += (
    "(source_kind=ANY(ARRAY['manual'::text,'opening'::text,'reversal'::text,'invoice'::text]))",
)
FINANCIAL_BOUNDARY = (
    """
and not exists (
    select 1 from (values __TRIGGERS__)
        expected(table_name,trigger_name,kind,function_name,deferred,source)
    left join pg_catalog.pg_trigger t
        on t.tgrelid=pg_catalog.to_regclass('gba.'||expected.table_name)
        and t.tgname=expected.trigger_name
    left join pg_catalog.pg_proc f on f.oid=t.tgfoid
    where t.oid is null or t.tgtype<>expected.kind or t.tgenabled<>'O' or t.tgisinternal
        or t.tgqual is not null or t.tgnargs<>0 or t.tgattr<>''::int2vector
        or pg_catalog.octet_length(t.tgargs)<>0
        or t.tgdeferrable<>expected.deferred or t.tginitdeferred<>expected.deferred
        or (t.tgconstraint<>0)<>expected.deferred
        or f.oid is distinct from pg_catalog.to_regprocedure(expected.function_name)
        or f.prosecdef or f.proconfig is not null or f.provolatile<>'v' or f.proparallel<>'u'
        or f.pronargs<>0 or f.prokind<>'f' or f.prorettype<>'pg_catalog.trigger'::regtype
        or f.prolang<>(select oid from pg_catalog.pg_language where lanname='plpgsql')
        or f.prosrc is distinct from expected.source
)
and exists (
    select 1 from pg_catalog.pg_proc f
    where f.oid=pg_catalog.to_regprocedure('gba.assert_invoice_consistent(uuid,uuid,uuid)')
        and not f.prosecdef and f.proconfig is null and f.provolatile='v' and f.proparallel='u'
        and f.pronargs=3 and f.prorettype='pg_catalog.void'::regtype
        and f.prolang=(select oid from pg_catalog.pg_language where lanname='plpgsql')
        and f.prosrc=%s
)
and not exists (
    select 1 from unnest(%s::text[]) expected(table_name)
    left join pg_catalog.pg_policy p
        on p.polrelid=pg_catalog.to_regclass('gba.'||expected.table_name)
        and p.polname=expected.table_name||'_tenant_isolation'
    where p.oid is null or not p.polpermissive or p.polcmd<>'*' or p.polroles<>array[0::oid]
        or regexp_replace(pg_catalog.pg_get_expr(p.polqual,p.polrelid),'[[:space:]]','','g')
            is distinct from %s
        or p.polwithcheck is distinct from p.polqual
)
and not exists (
    select 1 from unnest(%s::text[]) expected(table_name)
    join pg_catalog.pg_policy p on p.polrelid=pg_catalog.to_regclass('gba.'||expected.table_name)
    where p.polpermissive and p.polname<>expected.table_name||'_tenant_isolation'
)
and not exists (
    select 1 from (values __KEYS__) expected(table_name,kind,columns)
    where not exists (
        select 1 from pg_catalog.pg_constraint c
        where c.conrelid=pg_catalog.to_regclass('gba.'||expected.table_name)
            and c.contype::text=expected.kind and c.convalidated and not c.condeferrable
            and array(select a.attname::text from unnest(c.conkey) with ordinality k(n,position)
                join pg_catalog.pg_attribute a on a.attrelid=c.conrelid and a.attnum=k.n
                order by k.position)=expected.columns
    )
)
and not exists (
    select 1 from (values __FKS__) expected(table_name,columns,parent_name,parent_columns,deferred)
    where not exists (
        select 1 from pg_catalog.pg_constraint c
        where c.conrelid=pg_catalog.to_regclass('gba.'||expected.table_name) and c.contype='f'
            and c.confrelid=pg_catalog.to_regclass('gba.'||expected.parent_name) and c.convalidated
            and c.condeferrable=expected.deferred and c.condeferred=expected.deferred
            and c.confupdtype='a' and c.confdeltype='a' and c.confmatchtype='s'
            and array(select a.attname::text from unnest(c.conkey) with ordinality k(n,position)
                join pg_catalog.pg_attribute a on a.attrelid=c.conrelid and a.attnum=k.n
                order by k.position)=expected.columns
            and array(select a.attname::text from unnest(c.confkey) with ordinality k(n,position)
                join pg_catalog.pg_attribute a on a.attrelid=c.confrelid and a.attnum=k.n
                order by k.position)=expected.parent_columns
    )
)
and not exists (
    select 1 from (values __COLUMNS__) expected(table_name,column_name,kind,required)
    left join pg_catalog.pg_attribute a
        on a.attrelid=pg_catalog.to_regclass('gba.'||expected.table_name)
        and a.attname=expected.column_name and not a.attisdropped
    where a.attnum is null or a.atttypid is distinct from pg_catalog.to_regtype(expected.kind)
        or a.attnotnull is distinct from expected.required
)
and not exists (
    select 1 from (values __PRIVATE__) expected(table_name,column_name)
    where pg_catalog.has_column_privilege(
        'gba_runtime','gba.'||expected.table_name,expected.column_name,'INSERT')
)
and not exists (
    select 1 from unnest(%s::text[]) expected(table_name)
    where pg_catalog.has_table_privilege(
        'gba_runtime','gba.'||expected.table_name,'UPDATE,DELETE,TRUNCATE')
)
and exists (
    select 1 from pg_catalog.pg_constraint c
    where c.conrelid='gba.journal_entries'::regclass
        and c.conname='journal_entries_source_kind_check'
        and c.contype='c' and c.convalidated
        and regexp_replace(pg_catalog.pg_get_expr(c.conbin,c.conrelid),'[[:space:]]','','g')
            = %s
)
""".replace("__TRIGGERS__", ",".join("(%s,%s,%s::int,%s,%s::boolean,%s::text)" for _ in _TRIGGERS))
    .replace("__KEYS__", ",".join("(%s,%s,%s::text[])" for _ in _KEYS))
    .replace("__FKS__", ",".join("(%s,%s::text[],%s,%s::text[],%s::boolean)" for _ in _FKS))
    .replace("__COLUMNS__", ",".join("(%s,%s,%s,%s::boolean)" for _ in _COLUMNS))
    .replace("__PRIVATE__", ",".join("(%s,%s)" for _ in _PRIVATE))
)
