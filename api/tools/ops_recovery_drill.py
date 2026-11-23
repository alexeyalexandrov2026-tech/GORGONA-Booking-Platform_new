"""OPS-01: Backup/restore recovery drill, migration reconciliation and ledger balance checks."""

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Literal
from uuid import UUID

import psycopg
from psycopg import sql
from psycopg.conninfo import conninfo_to_dict, make_conninfo
from pydantic import BaseModel, ConfigDict


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class LedgerCurrencyBalance(_Strict):
    tenant_id: UUID
    book_id: UUID
    currency: str
    total_debit_minor: int
    total_credit_minor: int
    entry_count: int

    @property
    def balanced(self) -> bool:
        return self.total_debit_minor == self.total_credit_minor


class ReconciliationSnapshot(_Strict):
    schema_version: Literal[1] = 1
    migration_count: int
    migration_checksums: dict[int, str]
    table_counts: dict[str, int]
    ledger_balances: tuple[LedgerCurrencyBalance, ...]


class ReconciliationReport(_Strict):
    schema_version: Literal[1] = 1
    matched: bool
    mismatched_migrations: tuple[int, ...]
    mismatched_tables: tuple[str, ...]
    mismatched_ledgers: tuple[str, ...]
    unbalanced_ledgers: tuple[str, ...]


class RestoreDrillResult(_Strict):
    schema_version: Literal[1] = 1
    source_database: str
    target_database: str
    dump_seconds: float
    restore_seconds: float
    dump_bytes: int
    reconciliation: ReconciliationReport


def _find_pg_tool(name: str, pg_bin: str | None = None) -> str:
    candidates: list[str] = []
    if pg_bin:
        candidates.append(str(Path(pg_bin) / name))
    candidates.append(f"/usr/lib/postgresql/18/bin/{name}")
    found = shutil.which(name)
    if found:
        candidates.append(found)
    for path in candidates:
        if os.path.isfile(path) and os.access(path, os.X_OK):
            return path
    raise FileNotFoundError(f"PostgreSQL utility {name!r} not found")


def capture_reconciliation_snapshot(admin_db_dsn: str) -> ReconciliationSnapshot:
    """Capture migration checksums, all gba.* row counts, and double-entry ledger balances.

    Must connect with a BYPASSRLS backup/audit role (same privilege level as pg_dump)
    because gba.* tables enforce FORCE ROW LEVEL SECURITY even against the table owner.
    """
    with psycopg.connect(admin_db_dsn) as conn:
        mig_rows = conn.execute(
            "select version, checksum from public.gba_schema_migrations order by version"
        ).fetchall()
        checksums = {int(v): str(c) for v, c in mig_rows}

        tables = [
            str(r[0])
            for r in conn.execute(
                "select tablename from pg_catalog.pg_tables "
                "where schemaname = 'gba' order by tablename"
            ).fetchall()
        ]
        table_counts: dict[str, int] = {}
        for tbl in tables:
            row = conn.execute(
                sql.SQL("select count(*) from gba.{}").format(sql.Identifier(tbl))
            ).fetchone()
            assert row is not None  # noqa: S101
            table_counts[tbl] = int(row[0])

        bal_rows = conn.execute(
            """
            select
                je.tenant_id,
                je.book_id,
                je.currency,
                coalesce(sum(case when jl.side = 'debit' then jl.amount_minor else 0 end), 0),
                coalesce(sum(case when jl.side = 'credit' then jl.amount_minor else 0 end), 0),
                count(distinct je.id)
            from gba.journal_entries je
            join gba.journal_lines jl
              on jl.tenant_id = je.tenant_id
             and jl.book_id = je.book_id
             and jl.entry_id = je.id
            group by je.tenant_id, je.book_id, je.currency
            order by je.tenant_id, je.book_id, je.currency
            """
        ).fetchall()
        balances = tuple(
            LedgerCurrencyBalance(
                tenant_id=r[0],
                book_id=r[1],
                currency=str(r[2]),
                total_debit_minor=int(r[3]),
                total_credit_minor=int(r[4]),
                entry_count=int(r[5]),
            )
            for r in bal_rows
        )
    return ReconciliationSnapshot(
        migration_count=len(checksums),
        migration_checksums=checksums,
        table_counts=table_counts,
        ledger_balances=balances,
    )


def reconcile_snapshots(
    before: ReconciliationSnapshot,
    after: ReconciliationSnapshot,
) -> ReconciliationReport:
    """Compare two snapshots and verify double-entry ledger balance on both sides."""
    all_migs = sorted(set(before.migration_checksums) | set(after.migration_checksums))
    bad_migs = tuple(
        v for v in all_migs if before.migration_checksums.get(v) != after.migration_checksums.get(v)
    )

    all_tables = sorted(set(before.table_counts) | set(after.table_counts))
    bad_tables = tuple(
        t for t in all_tables if before.table_counts.get(t) != after.table_counts.get(t)
    )

    before_map = {(b.tenant_id, b.book_id, b.currency): b for b in before.ledger_balances}
    after_map = {(b.tenant_id, b.book_id, b.currency): b for b in after.ledger_balances}
    all_keys = sorted(
        set(before_map) | set(after_map),
        key=lambda k: (str(k[0]), str(k[1]), k[2]),
    )
    bad_ledgers: list[str] = []
    unbalanced: list[str] = []
    for key in all_keys:
        label = f"{key[0]}:{key[1]}:{key[2]}"
        lb, la = before_map.get(key), after_map.get(key)
        if lb != la:
            bad_ledgers.append(label)
        if (lb is not None and not lb.balanced) or (la is not None and not la.balanced):
            unbalanced.append(label)

    matched = not bad_migs and not bad_tables and not bad_ledgers and not unbalanced
    return ReconciliationReport(
        matched=matched,
        mismatched_migrations=bad_migs,
        mismatched_tables=bad_tables,
        mismatched_ledgers=tuple(bad_ledgers),
        unbalanced_ledgers=tuple(unbalanced),
    )


def verify_pg_dump_restore(
    *,
    admin_dsn: str,
    source_database: str,
    source_owner_dsn: str,
    target_database: str,
    pg_bin: str | None = None,
) -> RestoreDrillResult:
    """Run real pg_dump -> pg_restore into a clean target DB, measuring RTO and reconciling."""
    pg_dump = _find_pg_tool("pg_dump", pg_bin)
    pg_restore = _find_pg_tool("pg_restore", pg_bin)

    source_admin_dsn = make_conninfo(admin_dsn, dbname=source_database)
    target_admin_dsn = make_conninfo(admin_dsn, dbname=target_database)
    before = capture_reconciliation_snapshot(source_admin_dsn)
    owner_user = str(conninfo_to_dict(source_owner_dsn).get("user") or "")

    with psycopg.connect(admin_dsn, autocommit=True) as conn:
        conn.execute(
            sql.SQL("drop database if exists {} with (force)").format(
                sql.Identifier(target_database)
            )
        )
        if owner_user:
            conn.execute(
                sql.SQL("create database {} owner {}").format(
                    sql.Identifier(target_database),
                    sql.Identifier(owner_user),
                )
            )
        else:
            conn.execute(sql.SQL("create database {}").format(sql.Identifier(target_database)))
        conn.execute(
            sql.SQL("revoke all on database {} from public").format(sql.Identifier(target_database))
        )
        has_runtime = conn.execute(
            "select 1 from pg_catalog.pg_roles where rolname = 'gba_runtime'"
        ).fetchone()
        if has_runtime is not None:
            conn.execute(
                sql.SQL("grant connect on database {} to gba_runtime").format(
                    sql.Identifier(target_database)
                )
            )

    with tempfile.TemporaryDirectory(prefix="gorgona-ops01-") as tmp:
        dump_file = Path(tmp) / f"{source_database}.dump"
        t0 = time.perf_counter()
        dump_proc = subprocess.run(  # noqa: S603
            [pg_dump, "--format=custom", "--file", str(dump_file), source_admin_dsn],
            capture_output=True,
            text=True,
            check=False,
        )
        dump_seconds = round(time.perf_counter() - t0, 3)
        if dump_proc.returncode != 0:
            raise RuntimeError(f"pg_dump failed: {dump_proc.stderr.strip()}")
        dump_bytes = dump_file.stat().st_size

        t1 = time.perf_counter()
        restore_proc = subprocess.run(  # noqa: S603
            [pg_restore, "--exit-on-error", "--dbname", target_admin_dsn, str(dump_file)],
            capture_output=True,
            text=True,
            check=False,
        )
        restore_seconds = round(time.perf_counter() - t1, 3)
        if restore_proc.returncode != 0:
            raise RuntimeError(f"pg_restore failed: {restore_proc.stderr.strip()}")

    after = capture_reconciliation_snapshot(target_admin_dsn)
    report = reconcile_snapshots(before, after)
    return RestoreDrillResult(
        source_database=source_database,
        target_database=target_database,
        dump_seconds=dump_seconds,
        restore_seconds=restore_seconds,
        dump_bytes=dump_bytes,
        reconciliation=report,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Run OPS-01 pg_dump/pg_restore drill.")
    parser.add_argument("--admin-dsn", required=True)
    parser.add_argument("--source-db", required=True)
    parser.add_argument("--source-owner-dsn", required=True)
    parser.add_argument("--target-db", required=True)
    parser.add_argument("--pg-bin", default=None)
    args = parser.parse_args()

    result = verify_pg_dump_restore(
        admin_dsn=args.admin_dsn,
        source_database=args.source_db,
        source_owner_dsn=args.source_owner_dsn,
        target_database=args.target_db,
        pg_bin=args.pg_bin,
    )
    sys.stdout.write(json.dumps(result.model_dump(mode="json"), indent=2) + "\n")
    return 0 if result.reconciliation.matched else 1


if __name__ == "__main__":
    sys.exit(main())
