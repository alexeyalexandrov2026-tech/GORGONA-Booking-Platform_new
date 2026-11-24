"""Unit contract tests for OPS-01 recovery reconciliation snapshots."""

from uuid import uuid7

from tools.ops_recovery_drill import (
    LedgerCurrencyBalance,
    ReconciliationSnapshot,
    _parse_pg_major_version,
    reconcile_snapshots,
)

from gorgona_booking.db.financial_guard import _pg_dump_check_expr


def test_reconcile_snapshots_passes_on_exact_balanced_match() -> None:
    tid, bid = uuid7(), uuid7()
    bal = LedgerCurrencyBalance(
        tenant_id=tid,
        book_id=bid,
        currency="USD",
        total_debit_minor=25000,
        total_credit_minor=25000,
        entry_count=3,
    )
    snap = ReconciliationSnapshot(
        migration_count=2,
        migration_checksums={1: "aaa", 2: "bbb"},
        table_counts={"tenants": 2, "journal_entries": 3},
        ledger_balances=(bal,),
    )
    report = reconcile_snapshots(snap, snap)
    assert report.matched is True
    assert report.mismatched_migrations == ()
    assert report.mismatched_tables == ()
    assert report.mismatched_ledgers == ()
    assert report.unbalanced_ledgers == ()


def test_reconcile_snapshots_detects_checksum_row_and_ledger_drift() -> None:
    tid, bid = uuid7(), uuid7()
    before = ReconciliationSnapshot(
        migration_count=2,
        migration_checksums={1: "aaa", 2: "bbb"},
        table_counts={"tenants": 2, "journal_entries": 3},
        ledger_balances=(
            LedgerCurrencyBalance(
                tenant_id=tid,
                book_id=bid,
                currency="USD",
                total_debit_minor=1000,
                total_credit_minor=1000,
                entry_count=1,
            ),
        ),
    )
    after = ReconciliationSnapshot(
        migration_count=2,
        migration_checksums={1: "aaa", 2: "ccc"},
        table_counts={"tenants": 2, "journal_entries": 2},
        ledger_balances=(
            LedgerCurrencyBalance(
                tenant_id=tid,
                book_id=bid,
                currency="USD",
                total_debit_minor=1000,
                total_credit_minor=900,
                entry_count=1,
            ),
        ),
    )
    report = reconcile_snapshots(before, after)
    assert report.matched is False
    assert report.mismatched_migrations == (2,)
    assert report.mismatched_tables == ("journal_entries",)
    assert len(report.mismatched_ledgers) == 1
    assert len(report.unbalanced_ledgers) == 1


def test_pg_dump_check_expr_flattens_nested_and_without_weakening_or() -> None:
    nested = (
        "(((length(btrim(reason)) >= 1) AND (length(btrim(reason)) <= 500))"
        " AND (reason !~ '[[:cntrl:]]'::text))"
    )
    expected = (
        "((length(btrim(reason)) >= 1) AND (length(btrim(reason)) <= 500)"
        " AND (reason !~ '[[:cntrl:]]'::text))"
    )
    assert _pg_dump_check_expr(nested) == expected

    nullable = f"((reason IS NULL) OR {nested})"
    assert _pg_dump_check_expr(nullable) == f"((reason IS NULL) OR {expected})"

    middle = (
        "((alias = btrim(alias)) AND ((length(alias) >= 1) AND (length(alias) <= 100))"
        " AND (alias !~ '[[:cntrl:]]'::text))"
    )
    assert _pg_dump_check_expr(middle) == (
        "((alias = btrim(alias)) AND (length(alias) >= 1) AND (length(alias) <= 100)"
        " AND (alias !~ '[[:cntrl:]]'::text))"
    )

    with_or = "((kind = 'a'::text) AND ((status = 'x'::text) OR (status = 'y'::text)))"
    assert _pg_dump_check_expr(with_or) == with_or
    or_top = "((kind = 'a'::text) OR ((amount >= 1) AND (amount <= 100)))"
    assert _pg_dump_check_expr(or_top) == or_top


def test_parse_pg_major_version_extracts_major() -> None:
    assert _parse_pg_major_version("pg_dump (PostgreSQL) 18.7 (Ubuntu 18.7-1)") == 18
    assert _parse_pg_major_version("pg_dump (PostgreSQL) 16.16 (Ubuntu 16.16-1)") == 16
    assert _parse_pg_major_version("unknown") is None
