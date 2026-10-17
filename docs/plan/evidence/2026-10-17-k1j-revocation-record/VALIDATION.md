# K1j revocation record — local validation

**PASS for this bounded local slice.** Branch `codex/package-k1j-revocation-record`, parent
`84bc4d7`, source commit `201847856aa768bbeb25751d5b219e154383c293`. [CHECKS.json](CHECKS.json) was
generated before the source commit and binds source blobs, commands, exit codes and log digests.
Not published. Closes [independent review](../2026-10-16-k1e-http-ingress/INDEPENDENT_REVIEW_K1A_K1D.md)
finding IR-07 (except the namespace limit below). Executor: Claude, inline; the owner, away,
asked to keep working and decide alone.

## What changed

- `api/src/gorgona_booking/db/migrations/0048_provider_revocation_record.sql` (new):
  `revoked_reason`, `revoked_at`, `revoked_by` on `provider_receipt_connections` and
  `provider_verification_configs`; one check per table (all-or-nothing, empty while not
  revoked, reasons: configs `rotation`/`compromise`/`retired`, connections `compromise`/`retired`);
  the two guard triggers require a reason and write `now()` and `session_user`; the record is
  permanent; `verified_by` and `created_by` record `session_user`; `UPDATE (revoked_reason)` for
  the runtime and the writer group only
- `api/src/gorgona_booking/db/provider_receipt_guard.py`: reads 0048 (added columns, checks,
  column grants; a later `create or replace` supersedes the earlier body)
- `api/tests/integration/test_provider_receipt_revocation.py` (new, 20 cases),
  `test_provider_revocation_upgrade.py` (new, 1 case); existing revocations in
  `test_provider_event_inbox.py`, `test_provider_receipt_attestations.py` and
  `test_provider_receipt_routing.py` name a reason

Migrations 0001–0047 unchanged (next 0049). Rows revoked before 0048 are not changed: their empty
record means "revoked, record unknown". No dependency, API, receipt flow, readiness or Azure change.

## Criteria and evidence

| id | Requirement | Tests | Result |
|---|---|---|---|
| J-01 | No reason, or a reason outside the table's set, is refused for the runtime and the writer; nothing changes | `test_revocation_without_a_valid_reason_is_refused` ×8 | PASS |
| J-02 | Reason, a time within the transaction and the session login are recorded, also after `SET ROLE gba_receipt_writer` | `test_revocation_records_reason_time_and_session_login` ×5 | PASS |
| J-03 | Record permanent; not set before revocation; `revoked_at`/`revoked_by` not writable (runtime: no grant; owner: trigger) | `test_revocation_record_is_permanent_and_written_only_by_the_trigger` ×2 | PASS |
| J-04 | Attestations and configs record the session login after `SET ROLE` | `test_attestation_records_the_login_behind_the_group`, `test_config_records_the_login_behind_the_owner_role` | PASS |
| J-05 | 0047 → 0048 with revoked rows keeps every row and prior checksums; earlier revocations keep an empty record | `test_earlier_revocations_upgrade_with_an_empty_record` | PASS |
| J-06 | Drift refuses receipts and archives; repaired schema passes | `test_revocation_drift_stops_routed_and_runtime_receipts` ×3 (grant on `revoked_by`, dropped check, 0046 config trigger body) | PASS |
| J-07 | Existing K and guard tests and the full suite | focused-1, full-1 | PASS |

## Gates

| Gate | Exact observed outcome |
|---|---|
| Final focused, PostgreSQL 18.6, own cluster | PASS: 494 passed in 358.27s (0:05:58) |
| Full disposable PostgreSQL 18.6 and browser suite | PASS: 2077 passed, 4 skipped in 1598.78s (0:26:38); skips: 3 container, 1 tenant-site (NOT TESTED) |
| Ruff check and format, strict mypy | PASS: 319 source files |
| Web typecheck, lint, format, unit, build | PASS (web unchanged) |
| Runtime / development npm audit | PASS 0 / FAIL 5 high (existing, not required) |
| Run harness | each phase's stopped cluster deleted after stop (`data_removed: true`); no `postmaster.pid` left |
| K CI | NOT TESTED (not published) |

New cases 21, regression cases 191 (K receipt modules, see CHECKS.json).

## Failures kept in the record

**red-1, product RED** on `84bc4d7`: 21 failed in 17.92s. No reason columns; a revocation without
a reason was accepted (`DID NOT RAISE CheckViolation`); an attestation made after
`SET ROLE gba_receipt_writer` recorded `gba_receipt_writer` instead of the login; the 0046 config
trigger body was not refused by the guard.

**dev-1**: 222 passed in 127.19s; two warnings (an empty `match`) led to exact refusal messages in
J-03 before the gates.

## Limits

A revoked connection still cannot be re-provisioned in the same namespace (unique
`namespace, account_id`; K2 constraint). A `compromise` reason does not yet affect earlier
attestations (K2 reconciliation). There is no API or CLI for revocation; the runtime or the writer
revokes by direct SQL. `revoked_by` is the database login: it tells processes apart, not people
behind one login. The column defaults of `verified_by`/`created_by` stay `current_user`; the
triggers always overwrite them. FIN-02 planned; ADR-0027 Proposed.
