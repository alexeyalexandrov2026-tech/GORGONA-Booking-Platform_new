# K6 — one independent read-only review (2026-10-22)

**Verdict: APPROVE with conditions.** No Critical or High finding; no defect that could fabricate or
duplicate a receipt, decision or payment. Two Medium findings (R1, R2) must be fixed before the FIN-02
acceptance moves K-05 and K-12 to PASS.

Scope `8b8f8a3..056ab30` (K6a bounded retries and parked events, K6b1 event backfill, K6b2 screen,
K6c sandbox evidence). The owner allowed one read-only reviewer on 2026-10-22 («Да, и то и другое»:
CI and the review). The reviewer read the code and tests and ran nothing. The author checked R1 and
R2 against the code before deciding: both hold.

## Findings and the author's decisions

| id | Severity | Finding | Decision (K6r) |
|---|---|---|---|
| R1 | Medium | A run interrupted by a suspension or revocation counts the event as `seen` but nothing else; the run insert then breaks `seen = recorded + duplicates + conflicts + refused`, the `CheckViolation` escapes, no `failed` run is recorded and the other connections of that cycle are skipped. Any unlisted error (lock or statement timeout, a writer role refusal, an encoding error of a lone surrogate) escapes the same way | Fix: count an event only with its outcome; a binding refusal or database error ends that connection's run as `failed` with balanced counts and its class; one connection's error never stops the others; test a suspension after the first page |
| R2 | Medium | The JSON log formatter drops every new `extra` field (error class, attempts, parked, outcome, counts), so production logs say only "provider receipt event failed" — the K5r "provider receipt batch failed" line had the same defect. Nothing shows `provider_reconciliation_runs`: no screen, no metric | Fix: allow these fields in the formatter (test the formatted line); a counter of reconciliation runs by outcome and error class; the Provider connections list shows each connection's latest reconciliation (outcome, error class, time) |
| R3 | Low | The worker may read every company's release notes (`provider_event_releases` table-wide SELECT, discovery policy `true`) though discovery needs only `tenant_id`, `event_id`, `round` | Fix: migration 0065 grants the worker only those three columns; the guard learns column reads |
| R4 | Low | The reconciler accepts any key; a live key would query live Stripe (events then refused) | Fix: refuse a key that is not `sk_test_` or `rk_test_` |
| R5 | Low | `MAX_PAGES = 100` is ten times the owner-approved design (10 pages of 100 per connection per run) | Fix: back to 10, as the owner approved; a larger window fails visibly (`PageLimitExceededError`) |
| R6 | Low | The product's HTTP transport was never run against Stripe (K6c used the CLI); the fake API ignores `types` and the exact query shape | Fix: the fake asserts the exact request (`types`, `created[gte]`, `created[lt]`, `limit`, `Authorization`, `Stripe-Account`). A real call of `StripeApiSource` needs a restricted test key that only the owner may create: recorded as a limit, not claimed |
| R7 | Info | A same-note release racing another can answer 409 `not_failed` instead of repeating the answer | Fix: after a refused insert, compare with the latest release like after a duplicate |
| R8 | Info | A retrieved event's result says `signature_checked_not_admitted`; the platform key has no own revocation record | Fix the label (`retrieved_not_admitted`). Key revocation: recorded as a limit (rotate the key in the environment; a compromised connection is revoked as before) |
| R9 | Info | Run records grow without bound; the 5/10 limits are repeated in SQL, Python and TypeScript; one counted failure can follow a suspension in flight | Recorded; no change in K6r (retention is a later operations decision) |

Test gaps named by the reviewer, added in K6r: SQL refusals of a release (not parked, decided); two
concurrent releases with an observed `pg_locks` wait; the run trigger's foreign-company and future
`started_at` refusals; a real assertion in the processes test instead of `>= 0`.

## Checked and found correct (reviewer)

Migrations and upgrade (only 0063 and 0064 added; constraint name matches 0045); failure fencing,
rounds and the five-per-round bound, including a failure racing a lease takeover; the discovery
backoff arithmetic and the round boundary after a release; release concurrency by the primary key;
grants and RLS of all new tables and the guard's lists; which errors count; the retrieval trust model
(the webhook path reused, same facts, version, account and live-mode checks, namespace binding, no
network inside a transaction, key hidden); provenance from the attestation; the screen contract
indexes; no signing secret or key in the evidence.

## Resolution (K6r)

R1–R5, R7 and R8 fixed and R6 partly (exact request asserted) in `2eb6cf7`; see the
[K6r validation](../2026-10-22-k6r-review-fixes/VALIDATION.md). Full suite 2415 passed, 4 skipped.
Left as recorded limits: a real call of `StripeApiSource` (needs the owner's restricted test key), an
own revocation record for the platform key, and R9. The K6c sandbox VALIDATION said "failures stay
visible"; before K6r that held for the run rows only, not for logs or the screen — corrected here.
