"""Approved ledger definitions, using the packaged migration as their single source.

As with migrate.load_migrations, only repository-owned package resources are read.
Database definitions never supply expected values. No import-time database access.
"""

import re
from importlib import resources

_SQL = (resources.files("gorgona_booking.db") / "migrations" / "0020_ledger.sql").read_text(
    encoding="utf-8"
)
_SOURCES = dict(re.findall(r"create function gba\.(\w+)\([^;]*?as \$\$(.*?)\$\$;", _SQL, re.DOTALL))
_TABLES = (
    "ledger_books",
    "ledger_book_versions",
    "ledger_accounts",
    "ledger_account_versions",
    "journal_entries",
    "journal_lines",
    "ledger_period_events",
    "ledger_command_cancellations",
)
_TRIGGERS = (
    *((table, f"{table}_immutable", 27, "reject_ledger_mutation", False) for table in _TABLES),
    (
        "ledger_book_versions",
        "ledger_book_versions_next_revision",
        7,
        "enforce_ledger_book_version",
        False,
    ),
    (
        "ledger_account_versions",
        "ledger_account_versions_next_revision",
        7,
        "enforce_ledger_account_version",
        False,
    ),
    ("journal_entries", "journal_entries_check", 7, "enforce_journal_entry", False),
    ("journal_lines", "journal_lines_check", 7, "enforce_journal_line", False),
    ("journal_entries", "journal_entries_balanced", 5, "check_journal_balance", True),
    ("journal_lines", "journal_lines_balanced", 5, "check_journal_balance", True),
    ("ledger_period_events", "ledger_period_events_next", 7, "enforce_ledger_period_event", False),
)
LEDGER_PARAMETERS: tuple[object, ...] = tuple(
    value
    for table, trigger, kind, function, deferred in _TRIGGERS
    for value in (table, trigger, kind, "gba." + function + "()", deferred, _SOURCES[function])
)
LEDGER_PARAMETERS += (_SOURCES["lock_ledger"], _SOURCES["ledger_period_closed"])
LEDGER_PARAMETERS += (list(_TABLES), "(tenant_id=gba.current_tenant_id())")
LEDGER_PARAMETERS += (list(_TABLES),)
LEDGER_BOUNDARY = """
and not exists (
    select 1 from (values __TRIGGERS__)
        expected(table_name, trigger_name, kind, function_name, deferred, source)
    left join pg_catalog.pg_trigger t
      on t.tgrelid = pg_catalog.to_regclass('gba.' || expected.table_name)
     and t.tgname = expected.trigger_name
    left join pg_catalog.pg_proc f on f.oid = t.tgfoid
    where t.oid is null or t.tgtype <> expected.kind or t.tgenabled <> 'O'
       or t.tgisinternal or t.tgqual is not null or t.tgnargs <> 0 or t.tgattr <> ''::int2vector
       or t.tgdeferrable <> expected.deferred or t.tginitdeferred <> expected.deferred
       or (t.tgconstraint <> 0) <> expected.deferred
       or f.oid is distinct from pg_catalog.to_regprocedure(expected.function_name)
       or f.prosecdef or f.proconfig is not null or f.provolatile <> 'v'
       or f.prolang <> (select oid from pg_catalog.pg_language where lanname = 'plpgsql')
       or f.prosrc is distinct from expected.source
) and exists (
    select 1 from pg_catalog.pg_proc f
    where f.oid = pg_catalog.to_regprocedure('gba.lock_ledger(uuid)')
      and not f.prosecdef and f.proconfig is null and f.provolatile = 'v'
      and f.prosrc = %s
) and exists (
    select 1 from pg_catalog.pg_proc f
    where f.oid = pg_catalog.to_regprocedure('gba.ledger_period_closed(uuid,uuid,date)')
      and not f.prosecdef and f.proconfig is null and f.provolatile = 's'
      and f.prosrc = %s
) and not exists (
    select 1 from unnest(%s::text[]) expected(table_name)
    left join pg_catalog.pg_policy p
      on p.polrelid = pg_catalog.to_regclass('gba.' || expected.table_name)
     and p.polname = expected.table_name || '_tenant_isolation'
    where p.oid is null or not p.polpermissive or p.polcmd <> '*'
       or p.polroles <> array[0::oid]
       or regexp_replace(pg_catalog.pg_get_expr(p.polqual, p.polrelid), '[[:space:]]', '', 'g')
          is distinct from %s
       or p.polwithcheck is distinct from p.polqual
)
-- Permissive policies combine with OR. An extra grant must not bypass tenant isolation
-- while leaving the approved named policy untouched.
and not exists (
    select 1 from unnest(%s::text[]) expected(table_name)
    join pg_catalog.pg_policy p
      on p.polrelid = pg_catalog.to_regclass('gba.' || expected.table_name)
    where p.polpermissive
      and p.polname <> expected.table_name || '_tenant_isolation'
)
""".replace("__TRIGGERS__", ",".join("(%s,%s,%s::int,%s,%s::boolean,%s::text)" for _ in _TRIGGERS))
