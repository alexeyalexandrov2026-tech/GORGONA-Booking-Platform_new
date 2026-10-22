# K6r — fixes of the independent K6 review: local validation

**PASS for this bounded local, synthetic slice.** Branch `codex/package-k6r-review-fixes`, parent
`a41307e` (the [review record](../2026-10-22-k6-review/REVIEW.md)), source commit `2eb6cf723f719bde3753ba6bd800c44bc082602d`.
[CHECKS.json](CHECKS.json) was written before the source commit and binds every source blob, command,
exit code and log digest. No network; readiness unchanged in this slice.

## What changed (by finding)

| id | Change |
|---|---|
| R1 | An event counts as `seen` only together with its outcome. Any error that stops a connection's run (a suspension or revocation mid-run, the provider, a page, the database) records that run as `failed` by class with balanced counts; the other connections of the cycle go on |
| R2 | The JSON log keeps `error`, `attempts`, `parked`, `outcome`, `pages`, `seen`, `recorded`, `duplicates`, `conflicts`, `refused`, `runs`, `decided` (this also fixes the K5r "provider receipt batch failed" line, whose class was dropped); counter `gorgona.provider_reconciliation_runs` by outcome and error class; **Provider connections** shows each connection's latest run (completed with how many events were new, or failed with its class) in the API and on the screen |
| R3 | Migration 0065: the worker reads only `tenant_id`, `event_id`, `round` of a release, never the note or who released; the schema guard checks the worker's column reads |
| R4 | The reconciler refuses any key that is not `sk_test_` or `rk_test_` |
| R5 | At most 10 pages of 100 events per connection and run, as the owner approved |
| R6 | The fake Stripe API records and the test asserts the exact request (`types[0..10]`, `created[gte]`, `created[lt]`, `limit=100`, `Authorization`, `Stripe-Account`) |
| R7 | A same-note release that loses a race repeats the answer instead of 409 |
| R8 | A retrieved receipt reports `retrieved_not_admitted`; a webhook keeps `signature_checked_not_admitted` |
| Test gaps | Two concurrent releases with an observed `pg_locks` wait (one wins, the same note repeats); SQL refusal of a release of a waiting or decided event; the run trigger's foreign-company and future-start refusals; the processes test asserts the worker decided events |

## Failures kept

- **red-1**: 8 failed, 4 passed — R1 reproduced exactly (`provider_reconciliation_runs_check1` after a
  mid-run suspension), the other failures name each missing fix. The 4 that passed confirm behaviour
  the reviewer verified as correct and stay as regression tests.
- **dev-1**: 2 failed, 698 passed — a K6a test read a release note as the worker, which R3 now forbids
  (it reads the note as the owner); the K4a connection key list lacked `last_reconciliation`.

## Gates (final, suffix 1)

Run folder `GorgonaBookingTests/package-k6r-20261022-a41307e`: **static-1** PASS (npm audit 0);
**focused-1** PASS, **700 passed** (51 files); **full-1** PASS, **2415 passed, 4 skipped**.

## Remaining (recorded, not fixed here)

R6: the product's `StripeApiSource` was not run against Stripe; that needs a restricted test key,
which only the owner may create. R8: the platform key has no own revocation record (rotate it in the
environment). R9: run records are permanent; limits repeated across SQL, Python and TypeScript.
Migrations 0001–0065 immutable; the next is **0066**.
