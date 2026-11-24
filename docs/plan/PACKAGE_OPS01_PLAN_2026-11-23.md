# Package OPS-01 Plan — Recovery, Replay, Reconciliation & Reverse Switchback (2026-11-23)

- Branch: `codex/package-ops-01-recovery-migration-reconciliation`
- ADR: `docs/adr/0046-ops-recovery-reconciliation-and-load-verification.md`
- Migration: none (verifies full `0001`–`0148` schema)
- Scope:
  1. `api/src/gorgona_booking/ops/recovery.py` + `api/tools/ops_recovery_drill.py`:
     snapshot & reconcile all `gba.*` table counts, `public.gba_schema_migrations` SHA-256
     checksums, and currency-separated double-entry ledger balances (`debit == credit`).
  2. Real PG18 `pg_dump` + `pg_restore` into a clean target database with measured
     `dump_seconds` and `restore_seconds` (RTO), full `assert_location_scope_ready`
     under `gba_runtime`, and idempotent `apply_migrations` no-op check.
  3. Idempotent command/queue replay on the restored DB proving zero double-posting.
  4. Reverse-switchback check proving freeze -> reconcile -> switchback -> resume writes
     with zero data loss or divergence.
