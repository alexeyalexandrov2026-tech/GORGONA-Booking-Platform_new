# K0b — connection admission and receipt processes: local validation

**PASS for this bounded local, synthetic slice.** Branch `codex/package-k0b-entry-points`, parent
`4e0665c` (the K0a design and the owner's answers), source commit `1eacc1d73c4d13a759be95084d994ef1be6cf4fe`.
[CHECKS.json](CHECKS.json) was written before the source commit; it binds every source blob, the
exact commands, exit codes and log digests of every phase, including the failures below. Nothing is
published; no real provider event, key, account or readiness change is involved.

## Owner decisions

The owner answered «i trust you» (2026-10-20) to the seven [K0a](../../PACKAGE_K0A_DESIGN_2026-10-20.md)
questions, so every default applies: the owner records the admission with `gba-db`; the H4 link
is optional (not built); the worker loops every 5 s and also runs `--once`; `127.0.0.1:8787`; no new
dependency; the agent reads the database after the owner's run; a suspended connection may get a
new test-access revision.

## What changed

| Area | Change |
|---|---|
| 0057 (K) | `gba.provider_connection_admissions`: append-only revisions, `test_access` or `suspended`, environment `test`, USD, charge and refund flags, the connection's own account, evidence; revision, login and time set by the trigger; update, delete and truncate refused; only the owner inserts, in company scope. One advisory lock per connection: exclusive when recording, shared in every gate. Gates on attestations and decisions. Worker discover policy. |
| 0058 (H) | `require_provider_money_admission` on provider payments (provenance) and links: test access with charge for a payment, refund for a refund. |
| Services | The writer serves only an admitted connection (one refusal body otherwise); the worker skips connections without test access, so their events wait; applying money answers `PROVIDER_OPERATION_NOT_READY` with reason `not_admitted` (screen text added). |
| Processes | `providers/receipt_processes.py`, `python -m gorgona_booking.providers.ingress_main` (127.0.0.1 only, keys from named variables, writer login checked first) and `python -m gorgona_booking.providers.worker_main [--once] [--interval N]` (worker login checked first, clean stop). |
| Owner command | `gba-db admit-receipt-connection --tenant … --connection … --account acct_… --state test_access|suspended [--operations charge,refund] --evidence "…"` |
| Guards | The receipt guard covers the new table, triggers, checks, keys and policy; the financial guard reads 0058. |

## Criteria (K5 plan)

| id | Result in K0b |
|---|---|
| E-02 | PASS locally: ingress and worker run as processes; a signed synthetic payment is received twice and decided once; no key, ingress ID or payload in the process logs |
| E-03 | PASS locally: only an owner-recorded test-access admission admits a connection; roles cannot record or change one; suspension waits for a receipt in flight (observed `pg_locks` wait) and refuses the next; money needs the operation's permission |
| E-05 | PASS locally for synthetic retries (duplicate delivery, no second decision); real Stripe retries are K0c |
| E-04, E-06–E-08 | NOT TESTED here (K0c with the owner, then K5b) |

## Gates

| Gate | Exact observed outcome |
|---|---|
| New cases | 58 (anchor 1, admissions 29, processes 4, upgrade 1, unit settings 23) |
| Final focused | PASS: 623 passed in 703.66s (0:11:43) |
| Full disposable PostgreSQL 18.6 and browser suite | PASS: 2308 passed, 4 skipped in 2316.92s (0:38:36) |
| Ruff, format, strict mypy | PASS: 340 source files |
| Web typecheck, lint, format, unit, build | PASS |
| Runtime npm audit | PASS: 0 |
| Development npm audit | FAIL: 5 high, existing, not required |

## Failures kept in the record

1. **red-1, product RED (E-03).** On `4e0665c` a connection without an admission attested a signed receipt.
2. **red-2.** Four collection ImportErrors (expected).
3. **dev-1.** Test defects: two configs on one connection, a past signature time against the real
   clock, other companies' events counted in the shared database.
4. **dev-2, a product finding.** uvicorn writes its raw-path access log, with the ingress ID, whenever
   the `uvicorn.access` logger has a handler, whatever `access_log` says. The ingress process now
   disables that logger. **red-3** proved it by removing the guard for one run.
5. **dev-6.** A helper made a second connection without an admission; the new gate refused it, as it
   should; the helper now records test access.

## Limits and what is next

- K0c — the owner's real Stripe test run — is NOT TESTED; it needs the owner (see the runbook).
- Only `test_access` and `suspended` exist; approved or live needs a later decision. The H4 link is not built.
- The operations list shows no separate "not admitted" state; applying explains it.
- Not published: the new branch needs the owner's word. FIN-02 and STOCK-01 stay `planned`.
