# K6c — webhooks lost on purpose, fetched back from the real Stripe sandbox: validation

**PASS for the bounded test-mode run.** Base commit `9b741a7` (K6b2 docs on top of K6a `2f577bc`, K6b1
`73f5c45`, K6b2 `0af2a46`), branch `codex/package-k6c-sandbox`; no source changed during the run.
Stripe **sandbox (test mode)** `acct_1UJtGO0mkpVWlKYX` as the Connect platform, connected test account
`acct_1USjOo0mkpWSHVnd`, API version `2026-08-26.dahlia`. No live mode, no real money. FIN-02 readiness
unchanged until the review and CI below.

## Who did what

Owner 2026-10-21: «1» (close the FIN-02 gaps) and «Да, все умолчания» (the Stripe CLI as the sandbox
transport); the standing 2026-10-20 word «ты сам все делай, сам все настраивай». The agent ran
everything: the CLI session signed in on 2026-10-20 was still valid; no key entered our code (the
reconciler's transport was `stripe get /v1/events`), and the webhook signing secret of the last phase
lived in memory only (0 `whsec_` values in every file here).

## The run

[`test_k6c_run.py.txt`](test_k6c_run.py.txt) ran with the repository's test helpers on a fresh own
PostgreSQL 18.6 cluster on 127.0.0.1 (removed afterwards): a FAKE company with finance and a USD book,
the connection with the real connected account, an admission `test_access`, and the product's
`reconcile` with a CLI transport (`CliSource`), the worker, the finance API and, in the last phase, the
product ingress behind `stripe listen --forward-connect-to`. Result `1 passed in 33.93s` (k6c-4).
Record: [`K6C_RECORD.json`](K6C_RECORD.json); commands and calls: [`stripe-commands.log`](stripe-commands.log),
[`stripe-get.log`](stripe-get.log); deliveries: [`listen.log`](listen.log) (secret and ingress ID
redacted); every attempt: [`RUNS.md`](RUNS.md).

| Phase | Observed |
|---|---|
| A. Webhooks lost | `stripe trigger payment_intent.succeeded` and `charge.refunded` while nothing listened; the inbox stayed empty |
| B. First reconciliation (1 day) | 1 page, **28 events seen, 28 recorded**, 0 duplicates, 0 conflicts, 0 refused (every event of the window, including earlier attempts', had the connection's API version); each attested `stripe_api_v1`; the worker decided them (`observed/success`; `charge.refunded` `needs_review/unkeyed_operation` by design) |
| Money | The lost payment applied: **20.00 USD receivable**, attestation `provider_observed`, journal debit/credit 20.00; the refunded charge's payment 1.00 applied on an invoice and the **refund 1.00 payable** on a credit note |
| C. Second reconciliation | **28 seen, 0 recorded, 28 duplicates** — nothing new, nothing twice |
| D. Webhook first, then reconciliation | a new payment's webhook arrived (`200`) and was attested `stripe_snapshot_v1`; the third run saw 30, recorded 0, 30 duplicates; that event now has **2 deliveries, verifiers stripe_api_v1, stripe_snapshot_v1, same facts**, and no new decision |
| Screen | the operation's deliveries name both sources: provider_api, provider_api, webhook, webhook |

## Attempts that failed (kept)

- **k6c-1**: the driver's "new event" filter used this computer's start time, which runs a few seconds
  ahead of Stripe's clock, so the payment events fell before it (Stripe had them all). Fix: start minus
  120 s. Lesson for operators: the reconciler's window ends at the local time; a late clock could miss
  the newest seconds, which the next run (every 15 minutes) reads.
- **k6c-2**: phases A–C passed; phase D tried `stripe events resend` of the lost event, which Stripe
  refuses for an event created while no CLI listened (the CLI still exits 0). Phase D changed to the
  other order, and the driver now fails on an error body.
- **k6c-3**: my mistake — the driver edit failed but the run was not chained to it, so it repeated
  k6c-2 unchanged (one more test-mode payment and refund).
- **k6c-4**: PASS.

## Criteria (K6 design)

| Gap | Result in the sandbox |
|---|---|
| K-05 missing objects reconcile safely | PASS: lost payment and refund events were fetched, decided and applied; a repeat and the other order converged without a second fact or effect |
| K-12 reconciliation, no fabricated success | PASS: every run recorded with its counts; no event recorded twice; failures stay visible (K6b1 tests cover timeouts, 429/5xx, refusals) |

## Limits

Test mode, USD, one connected account. The webhook-after-retrieval order could not be produced with a
Stripe resend in the sandbox; the webhook-then-retrieval order and the K6b1 tests show the same
convergence. Next: exact-head CI for the K6 branches and one independent review (both need the owner's
word), then the FIN-02 acceptance update.
