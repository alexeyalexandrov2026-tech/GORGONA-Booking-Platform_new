# K1f writer bootstrap and migration order — local validation

**PASS for this bounded local slice.** Branch `codex/package-k1f-bootstrap-hardening`, parent
`be97fbd`, source commit `3e18c938a505bbb4583778cdf40df0e7bed2aceb`. [CHECKS.json](CHECKS.json) was
generated before the source commit and binds source blobs, commands, exit codes and log digests.
Not published. Closes [independent review](../2026-10-16-k1e-http-ingress/INDEPENDENT_REVIEW_K1A_K1D.md)
finding IR-06. Executor: Claude, inline, after the owner's «continue».

## What changed

- `api/src/gorgona_booking/db/bootstrap.py`: `validate()` refuses equal owner, runtime and writer passwords
- `api/src/gorgona_booking/db/cli.py`: `gba-db bootstrap` reads optional `GBA_RECEIPT_WRITER_ROLE`/`GBA_RECEIPT_WRITER_PASSWORD`; `gba-db migrate` prints `MigrationError`
- `api/src/gorgona_booking/db/migrate.py`: refuses before the lock and before creating anything when `gba_runtime` or `gba_receipt_writer` is missing
- `api/tests/unit/test_receipt_writer_bootstrap.py` (5 new cases), `api/tests/integration/test_bootstrap_order.py` (new, 3 cases)
- `docs/DEVELOPMENT.md`: order, writer variables, credentials row

No migration (next 0047), dependency, receipt code, schema or Azure infrastructure change.

## Criteria and evidence

| id | Requirement | Tests | Result |
|---|---|---|---|
| F-01 | Equal passwords refused before any connection; no value in the message | `test_equal_role_passwords_are_refused_before_any_connection` ×3 (unreachable DSN) | PASS |
| F-02 | CLI writer login: both variables create a writer-group member that is not runtime or owner and can log in; one refuses; none creates no writer | `test_cli_needs_both_writer_variables` ×2, `test_cli_bootstrap_creates_a_separate_writer_login`, `test_cli_bootstrap_without_writer_variables_creates_no_writer` | PASS |
| F-03 | Missing writer group: migrate refuses, no migration table and no `gba` schema; after the group returns all 46 apply | `test_migrate_refuses_before_bootstrap_created_the_writer_group` (group renamed by the superuser and restored in `finally`) | PASS |
| F-04 | Existing tests and the full suite | focused, full | PASS |

## Gates

| Gate | Exact observed outcome |
|---|---|
| Final focused, PostgreSQL 18.6, own cluster | PASS: 458 passed in 408.78s (0:06:48) |
| Full disposable PostgreSQL 18.6 and browser suite | PASS: 2042 passed, 4 skipped in 3100.84s (0:51:40); skips: 3 container, 1 tenant-site (NOT TESTED). Slower than K1e's 0:28:20 on the same suite plus 8 cases; machine load was not measured |
| Ruff check and format, strict mypy | PASS: 315 source files |
| Web typecheck, lint, format, unit, build | PASS (web unchanged) |
| Runtime / development npm audit | PASS 0 / FAIL 5 high (existing, not required) |
| Run harness | each phase's stopped cluster deleted after stop (`data_removed: true`) |
| K CI | NOT TESTED for K1f (not published). K1e branch CI: run 38991120703 FAILED at the production image build after 17 s (log needs a GitHub sign-in; pinned base images were pullable afterwards); an empty re-run commit `e5279cb` (same tree as `be97fbd`) passed: [CI run 38996263458](https://github.com/alexeyalexandrov2026-tech/GORGONA-Booking-Platform_new/actions/runs/38996263458) SUCCESS. The first failure is treated as transient; its cause is not established. Local `uv lock --check` and `uv sync --locked --no-dev --no-install-project` PASS |

## Failures kept in the record

**red-1, product RED.** 7 failed, 9 passed in 17.98s on `be97fbd`: equal passwords reached a
connection attempt; the CLI ignored the writer variables; migrate applied 0001–0044 and failed
inside 0045 with `UndefinedObject` for `gba_receipt_writer`.

## Limits

The Azure bootstrap job does not pass the writer variables (infrastructure and secrets need the
owner's word). The migration check covers role existence only, not their attributes (bootstrap
and the runtime/writer guards check those). FIN-02/STOCK-01 planned; ADR-0026/0027 Proposed.
