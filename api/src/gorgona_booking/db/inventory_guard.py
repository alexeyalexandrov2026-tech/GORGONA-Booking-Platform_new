"""Packaged schema approvals of the inventory tables: J1 materials and places, J2 receipts.

Never learn approvals from the target database.
"""

import re
from collections import defaultdict
from importlib import resources
from typing import Any

from gorgona_booking.db.pool import RuntimeConnection
from gorgona_booking.errors import DatabaseUnavailableError

_MIGRATIONS = resources.files("gorgona_booking.db") / "migrations"
_SQL = "\n".join(
    (_MIGRATIONS / name).read_text(encoding="utf-8")
    for name in ("0036_inventory.sql", "0037_stock_receipts.sql")
)
_BLOCKS = dict(re.findall(r"create table gba\.(\w+)\s*\((.*?)\n\);", _SQL, re.DOTALL))
INVENTORY_TABLES = tuple(_BLOCKS)
# Shared guard functions come from 0015; the stock functions from this package.
_FUNCTIONS = dict(
    re.findall(
        r"create (?:or replace )?function gba\.(\w+)\([^;]*?as \$\$(.*?)\$\$;",
        (_MIGRATIONS / "0015_counterparties.sql").read_text(encoding="utf-8") + _SQL,
        re.DOTALL,
    )
)
_TRIGGERS = tuple(
    re.findall(
        "create (constraint )?trigger (\\w+) (before|after) "
        "(update or delete|insert or update|insert|delete) "
        "on gba\\.(\\w+)\\s*(deferrable initially deferred )?"
        r"for each row execute function gba\.(\w+)\(([^)]*)\);",
        _SQL,
        re.DOTALL,
    )
)
if {trigger[1] for trigger in _TRIGGERS} != set(
    re.findall(r"create (?:constraint )?trigger (\w+)", _SQL)
):
    raise RuntimeError("Every inventory trigger must have an explicit packaged approval")
_INSERTS = {
    table: set(columns.split(","))
    for columns, table in re.findall(r"grant insert \(([^)]+)\) on gba\.(\w+)", _SQL)
}
_COLUMNS = {
    table: tuple(
        re.findall(
            r"^    (\w+) (uuid|text|integer|boolean|timestamptz|bigint|smallint|date|xid8)"
            r"(?=[\s,])([^\n]*)",
            block,
            re.MULTILINE,
        )
    )
    for table, block in _BLOCKS.items()
}
_KEYS = {
    table: {
        (kind, tuple(x.strip() for x in columns.split(",")))
        for kind, columns in re.findall(r"(primary key|unique) \(([^)]+)\)", block)
    }
    for table, block in _BLOCKS.items()
}
# A key that a later migration adds to an earlier table.
for _table, _key in re.findall(
    r"alter table gba\.(\w+) add constraint \w+ unique \(([^)]+)\);", _SQL
):
    _KEYS[_table].add(("unique", tuple(x.strip() for x in _key.split(","))))
_FKS = {
    table: {
        (
            tuple(x.strip() for x in columns.split(",")),
            parent,
            tuple(x.strip() for x in targets.split(",")),
        )
        for columns, parent, targets in re.findall(
            r"foreign key \(([^)]+)\)\s*references gba\.(\w+)\(([^)]+)\)", block
        )
    }
    | {
        ((name,), parent, (target,))
        for name, parent, target in re.findall(
            r"^    (\w+) uuid not null references gba\.(\w+)\((\w+)\)", block, re.MULTILINE
        )
    }
    for table, block in _BLOCKS.items()
}
# Head rows carry the row lock of their versions; balances and costs are running totals.
# Hence a column UPDATE right on these columns, and nothing else is ever updated.
_UPDATE_COLUMNS = {
    (table, column.strip())
    for columns, tables in re.findall(r"grant update \(([^)]+)\) on ([^;]+?) to gba_runtime", _SQL)
    for table in re.findall(r"gba\.(\w+)", tables)
    for column in columns.split(",")
}
_APPROVED_UPDATES = {
    ("stock_items", "id"),
    ("stock_places", "id"),
    ("stock_balances", "quantity"),
    ("stock_costs", "quantity"),
    ("stock_costs", "value_minor"),
}
if _UPDATE_COLUMNS != _APPROVED_UPDATES:
    raise RuntimeError("Every inventory column UPDATE right needs an explicit approval")
# The journal tables carry three stock triggers; the ledger guards own their other ones.
_FOREIGN_TABLES = ("journal_entries", "journal_lines")
_DEFAULTS = ("now()", "pg_current_xact_id()")
_TYPES = {"timestamptz": "timestamp with time zone"}


# Explicit PostgreSQL 18 deparse approvals of the reviewed packaged migration.
# Compared with whitespace only: quoted identifiers, literals and parentheses stay.
def _expression(value: str | None) -> str:
    return "".join(
        part if part.startswith(("'", '"')) else re.sub(r"\s", "", part)
        for part in re.split(r"""('(?:''|[^'])*'|"(?:""|[^"])*")""", value or "")
    )


_CODE = "((code ~ '^[A-Z0-9][A-Z0-9_-]{0,63}$'::text))"
_NAME = (
    "((((length(btrim(name)) >= 1) AND (length(btrim(name)) <= 200)) AND "
    "(name !~ '[[:cntrl:]]'::text)))"
)
_CHECKS = {
    "stock_items_code_check": _CODE,
    "stock_items_unit_check": (
        "((((length(unit) >= 1) AND (length(unit) <= 16)) AND (unit = btrim(unit)) AND "
        "(unit !~ '[[:cntrl:]]'::text)))"
    ),
    "stock_items_scale_check": "(((quantity_scale >= 0) AND (quantity_scale <= 3)))",
    "stock_item_versions_revision_check": "((revision > 0))",
    "stock_item_versions_name_check": _NAME,
    "stock_places_code_check": _CODE,
    "stock_place_versions_revision_check": "((revision > 0))",
    "stock_place_versions_name_check": _NAME,
}
_QUANTITY = "(((quantity >= 1) AND (quantity <= '999999999999'::bigint)))"
_HELD = "(((quantity >= 0) AND (quantity <= '999999999999999'::bigint)))"
_DIRECTION = "((direction = ANY (ARRAY['in'::text, 'out'::text])))"
_CHECKS |= {
    "stock_posting_rules_revision_check": "((revision > 0))",
    "stock_posting_rules_distinct_check": (
        "(((inventory_account_id <> receipt_account_id) AND "
        "(inventory_account_id <> opening_account_id) AND "
        "(inventory_account_id <> surplus_account_id) AND "
        "(inventory_account_id <> consumption_account_id) AND "
        "(inventory_account_id <> loss_account_id) AND "
        "(inventory_account_id <> difference_account_id)))"
    ),
    "stock_documents_kind_check": "((kind = 'receipt'::text))",
    "stock_documents_reason_check": (
        "((reason = ANY (ARRAY['purchase'::text, 'opening_balance'::text, 'surplus'::text])))"
    ),
    "stock_documents_number_check": (
        "((((length(supplier_document) >= 1) AND (length(supplier_document) <= 64)) AND "
        "(supplier_document = btrim(supplier_document)) AND "
        "(supplier_document !~ '[[:cntrl:]]'::text)))"
    ),
    "stock_documents_lines_check": "(((line_count >= 1) AND (line_count <= 100)))",
    "stock_documents_supplier_check": (
        "((((supplier_id IS NULL) AND (supplier_document IS NULL)) OR (reason = 'purchase'::text)))"
    ),
    "stock_document_lines_number_check": "(((line_no >= 1) AND (line_no <= 100)))",
    "stock_document_lines_quantity_check": _QUANTITY,
    "stock_movements_direction_check": _DIRECTION,
    "stock_movements_quantity_check": _QUANTITY,
    "stock_balances_quantity_check": _HELD,
    "stock_document_postings_total_check": (
        "(((total_minor >= 0) AND (total_minor <= '999999999999999999'::bigint)))"
    ),
    "stock_document_postings_entry_check": "(((entry_id IS NULL) = (total_minor = 0)))",
    "stock_valuations_direction_check": _DIRECTION,
    "stock_valuations_quantity_check": _QUANTITY,
    "stock_valuations_amount_check": (
        "(((amount_minor >= 0) AND (amount_minor <= '999999999999999'::bigint)))"
    ),
    "stock_costs_quantity_check": _HELD,
    "stock_costs_value_check": (
        "(((value_minor >= 0) AND (value_minor <= '999999999999999999'::bigint)))"
    ),
    "stock_costs_empty_check": "(((quantity > 0) OR (value_minor = 0)))",
}
_BRANCH = "((gba.current_location_id() IS NULL) OR (location_id = gba.current_location_id()))"
# Amounts, cost and the link to a book: company-wide members only, like the ledger.
_COMPANY = "(gba.current_location_id() IS NULL)"
_PLACE_BRANCH = (
    "((gba.current_location_id() IS NULL) OR (EXISTS ( SELECT 1\n"
    "   FROM gba.stock_places p\n"
    "  WHERE ((p.tenant_id = stock_place_versions.tenant_id) AND (p.id = "
    "stock_place_versions.place_id) AND (p.location_id = gba.current_location_id())))))"
)
# table: (USING, WITH CHECK) of its restrictive location policy.
_POLICIES = {
    "stock_items": ("true", "(gba.current_location_id() IS NULL)"),
    "stock_item_versions": ("true", "(gba.current_location_id() IS NULL)"),
    "stock_places": (_BRANCH, _BRANCH),
    "stock_place_versions": (_PLACE_BRANCH, _PLACE_BRANCH),
    "stock_posting_rules": (_COMPANY, _COMPANY),
    "stock_documents": (_BRANCH, _BRANCH),
    "stock_document_lines": (_BRANCH, _BRANCH),
    "stock_movements": (_BRANCH, _BRANCH),
    "stock_balances": (_BRANCH, _BRANCH),
    "stock_document_postings": (_COMPANY, _COMPANY),
    "stock_valuations": (_COMPANY, _COMPANY),
    "stock_costs": (_COMPANY, _COMPANY),
}
if set(_POLICIES) != set(INVENTORY_TABLES):
    raise RuntimeError("Every inventory table needs an explicit location policy approval")
_TENANT = "(tenant_id = gba.current_tenant_id())"


async def assert_inventory_ready(conn: RuntimeConnection) -> None:
    try:
        await _check(conn)
    except (ValueError, KeyError) as exc:
        raise DatabaseUnavailableError("Inventory schema protection is unavailable") from exc


def _require(value: bool, what: str) -> None:
    if not value:
        raise ValueError(f"Inventory schema differs from packaged approvals: {what}")


async def _catalog(
    conn: RuntimeConnection, query: str, names: list[str]
) -> dict[str, list[tuple[Any, ...]]]:
    grouped: dict[str, list[tuple[Any, ...]]] = defaultdict(list)
    for row in await (await conn.execute(query, (names,))).fetchall():
        grouped[str(row[0])].append(tuple(row[1:]))
    return grouped


async def _check(conn: RuntimeConnection) -> None:
    names = list(INVENTORY_TABLES)
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
               c.condeferrable,c.condeferred,c.confupdtype,c.confdeltype,c.confmatchtype,
               c.connoinherit
          from pg_constraint c join pg_class cl on cl.oid=c.conrelid
         where cl.relnamespace='gba'::regnamespace and cl.relname=any(%s)
    """,
        names,
    )
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
        [*names, *_FOREIGN_TABLES],
    )
    for table in INVENTORY_TABLES:
        _require(tables[table] == [(True, True, "r", True, False, False)], f"{table} access")
        _require(len(policies[table]) == 2, f"{table} policy count")
        for name, permissive, cmd, using, check, public, runtime in policies[table]:
            tenant = name == table + "_tenant_isolation"
            _require(tenant or name == table + "_location_scope", f"policy {name}")
            expected = (_TENANT, _TENANT) if tenant else _POLICIES[table]
            _require(
                permissive == tenant and cmd == "*" and public == tenant and runtime != tenant,
                f"policy {name} kind",
            )
            _require(
                _expression(using) == _expression(expected[0])
                and _expression(check) == _expression(expected[1]),
                f"policy {name} expression",
            )
        _require(len(columns[table]) == len(_COLUMNS[table]), f"{table} columns")
        for actual, (name, kind, tail) in zip(columns[table], _COLUMNS[table], strict=True):
            _require(
                actual
                == (
                    name,
                    _TYPES.get(kind, kind),
                    "not null" in tail,
                    next((d for d in _DEFAULTS if f"default {d}" in tail), None),
                    name in _INSERTS[table],
                    (table, name) in _UPDATE_COLUMNS,
                    False,
                    False,
                ),
                f"{table}.{name}",
            )
        keys: set[tuple[str, tuple[str, ...]]] = set()
        fks: set[tuple[tuple[str, ...], str, tuple[str, ...]]] = set()
        checks: set[str] = set()
        for (
            name,
            kind,
            valid,
            enforced,
            definition,
            own,
            parent,
            targets,
            defer,
            deferred,
            up,
            delete,
            match,
            noinherit,
        ) in constraints[table]:
            _require(valid and enforced and not (kind == "c" and noinherit), f"{name} flags")
            if kind in ("p", "u"):
                _require(not defer and not deferred, f"{name} deferral")
                keys.add(("primary key" if kind == "p" else "unique", tuple(own)))
            elif kind == "f":
                _require(
                    not defer and not deferred and (up, delete, match) == ("a", "a", "s"),
                    f"{name} actions",
                )
                fks.add((tuple(own), str(parent).removeprefix("gba."), tuple(targets)))
            elif kind == "c":
                checks.add(name)
                _require(
                    name in _CHECKS
                    and _expression(definition.removeprefix("CHECK "))
                    == _expression(_CHECKS[name]),
                    f"check {name}",
                )
            elif kind == "t":
                _require(
                    name in {t[1] for t in _TRIGGERS if t[0] and t[4] == table},
                    f"constraint trigger {name}",
                )
            else:
                _require(kind == "n", f"{name} kind")
        _require(keys == _KEYS[table], f"{table} keys")
        _require(fks == _FKS[table], f"{table} foreign keys")
        _require(
            checks == {name for name in _CHECKS if name.rsplit("_", 2)[0] == table},
            f"{table} checks",
        )
        _require(
            {t[0] for t in triggers[table]} == {t[1] for t in _TRIGGERS if t[4] == table},
            f"{table} triggers",
        )
    for constraint, name, when, event, table, deferred, function, argument in _TRIGGERS:
        found = next((t[1:] for t in triggers[table] if t[0] == name), None)
        _require(found is not None, f"trigger {name}")
        if found is None:
            return
        # Row trigger bits: row 1, before 2, insert 4, delete 8, update 16.
        kind = (
            1
            + (2 if when == "before" else 0)
            + sum(b for word, b in (("insert", 4), ("delete", 8), ("update", 16)) if word in event)
        )
        _require(
            found[:5]
            == (
                kind,
                "O",
                bool(deferred),
                bool(deferred),
                argument.strip("'").encode() + bytes([0]) if argument else b"",
            ),
            f"trigger {name} shape",
        )
        _require(found[5] == _FUNCTIONS[function], f"function {function}")
        _require(
            found[6:]
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
                None,
            ),
            f"trigger {name} function",
        )
