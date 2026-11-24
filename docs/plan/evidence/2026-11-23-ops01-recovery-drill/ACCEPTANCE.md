# OPS-01 Technical Acceptance Evidence (2026-11-23)

- **Branch**: `codex/package-ops-01-recovery-migration-reconciliation`
- **Verified code SHA**: `ce581a224641a6812a72aec675c6f419bd39ca86`
- **Full parallel suite**: `3110 passed / 0 failed / 4 skipped` out of `3114` (`count_ok=true`, `duplicates=0`, `wall=1474.06s`, `browser=53/53`, `serial=217/217`).
- **Real PG18 recovery bug caught & fixed**: `financial_guard.py` now strictly accepts both pre-dump nested `AND` ASTs and PostgreSQL `pg_dump` flattened pure-`AND` chains via `_pg_dump_check_expr`, without weakening `OR` precedence or any CHECK predicate.
- **Recovery drill verified**: real PG18 `pg_dump --format=custom` -> `pg_restore --exit-on-error` into clean DB, 148/148 migration checksums, all `gba.*` row counts, balanced multi-currency double-entry ledgers (USD + EUR), `assert_location_scope_ready` under `gba_runtime` RLS, idempotent replay with zero double-posting, and reverse switchback.
