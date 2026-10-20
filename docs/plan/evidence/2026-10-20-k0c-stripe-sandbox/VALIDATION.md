# K0c — real Stripe sandbox events: validation

**PASS for the bounded test-mode run.** Base commit `dd013fd` (K5b source `58cf561` plus docs), branch
`codex/package-k5b-open-findings`; no source changed during the run. Stripe **sandbox (test mode)**
`acct_1UJtGO0mkpVWlKYX` (Alexey AAA logistics LLC) as the Connect platform and the connected test account
`acct_1USjOo0mkpWSHVnd`. No live mode, no real money; FIN-02 readiness unchanged.

## Who did what (owner decision 2026-10-20)

The owner said «ты сам все делай, сам все настраивай» and «Да» (download the CLI; pass the signing
secret by script, in memory only). The agent installed the Stripe CLI 1.54.1 (zip SHA-256 matched
Stripe's checksum file), ran the device login, created the connected test account (Accounts v2,
dashboard none, fees and losses on the platform), filled Stripe's documented test values (FAKE name,
date of birth 1901-01-01, test address `address_full_match`, test bank token `btok_us_verified`, last
four 0000, terms accepted for this fictitious test account), started the stack and drove the run. The
owner alone approved the CLI login, enabled Connect in the sandbox (platform model) and entered the
full test SSN, which the agent may not enter.

## The run

[`test_k0c_run.py.txt`](test_k0c_run.py.txt) (sha256 `271e7316…d1ac`) ran with the repository's test
helpers on a fresh own PostgreSQL 18.6 cluster on 127.0.0.1 (removed afterwards): a FAKE company with
finance enabled and a USD book; the connection with the real connected account and API version
`2026-08-26.dahlia`; a verification config `env:GBA_STRIPE_TEST_WEBHOOK_SECRET`; a route; the
admission `test_access` (charge and refund) recorded with `record_receipt_admission`, the function
behind `gba-db admit-receipt-connection`. The ingress (`serve_ingress`, product code) listened on a free
127.0.0.1 port with the secret held in memory; `stripe listen --forward-connect-to` delivered
connected-account events; the worker (`process_batch`) decided; money was applied through the finance
API the screen uses. Result: `1 passed in 55.42s`. Record: [`K0C_RECORD.json`](K0C_RECORD.json);
delivery log (secret and ingress ID redacted): [`listen.log`](listen.log).

| Step | Observed |
|---|---|
| `stripe trigger payment_intent.succeeded` | `payment_intent.succeeded` and `charge.succeeded` (2000) delivered 200, attested, decided `observed/success` |
| `stripe trigger payment_intent.payment_failed` | `payment_intent.payment_failed` and `charge.failed` delivered, decided `observed/not_final`; applying it answered 409 `PROVIDER_OPERATION_NOT_READY` |
| `stripe trigger charge.refunded` | its payment (100) succeeded; `refund.created` and `refund.updated` (100) decided `observed/success`; `charge.refunded` decided `needs_review/unkeyed_operation` (by design: a charge.refunded has no key) |
| Apply payment | 20.00 USD receivable, attestation `provider_observed`, journal debit clearing / credit control 20.00 |
| Apply refund | the parent 1.00 applied on an invoice; the refund 1.00 payable on a credit note: journal credit clearing / debit refund control 1.00 |
| Operations list | two payments `applied`, the refund `applied`, the failed payment `not_final` |
| `stripe events resend` of the first event | delivered again (200); stored events stayed 9, no second effect (E-05) |
| Suspension, then a new trigger | both deliveries answered 400; nothing stored |

## Criteria (K5 plan)

| id | Result |
|---|---|
| E-02 | PASS: the ingress ran from product code with the key from a named reference; no key, ingress ID or payload in any log (checked: 0 `whsec_` values in every file) |
| E-03 | PASS: only the recorded admission let events in; the suspension refused the next real deliveries |
| E-04 | PASS: real signed sandbox events (success, failure, refund) were attested, decided and listed; one payment and one refund applied with provenance |
| E-05 | PASS: a Stripe resend produced no second receipt or effect |
| E-06–E-08 | Not this step: K5-CI (exact-head CI; publication needs the owner's word) and K5c (the owner's readiness decision) |

## Limits

- The money was applied through the finance API, not by clicking the screen; the screen path itself is
  covered by the K4a browser tests on synthetic events.
- Only test mode, USD, one connected account; the ISK/UGX and currency limits of finding 15 remain.
- `charge.refunded` always lands in "needs attention" (no key); the refund itself is decided from the
  refund events. Operators may acknowledge it.
