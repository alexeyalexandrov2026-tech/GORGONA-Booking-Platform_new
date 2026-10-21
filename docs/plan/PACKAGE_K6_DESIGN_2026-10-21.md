# K6 — FIN-02 gaps K-05 and K-12: bounded retries, parked events and provider reconciliation (design and questions, 2026-10-21)

**Status: owner decisions received 2026-10-21 — all six defaults** («Да, все умолчания»). Local
branch `codex/package-k6-design` from `fba651e` (STOCK-01 record). The owner chose this work on
2026-10-21 («1» = close the FIN-02 gaps K-05 and K-12). Next: K6a on its own local branch.

FIN-02 is `technically_verified` with two partial criteria
([acceptance](evidence/2026-10-20-fin-02-acceptance/ACCEPTANCE.md)):

- **K-05** — permutations converge; stale, equal-time and *missing* objects reconcile safely. Missing:
  provider retrieval of objects whose events never arrived; permutations are tested by representative
  orders only.
- **K-12** — bounded retries, no fabricated success, no secrets in logs. Missing: a dead-letter queue
  and provider reconciliation.

## What exists today (inspected 2026-10-21)

- The receipt worker (`providers/receipt_worker.py`) claims an attested event with a lease, then
  records a permanent decision; the database trigger classifies the facts. Money moves only when a
  finance user applies an operation (K3a); the worker never posts.
- **Gap found while reading the code (K-12).** When the decision statement fails for one event
  (for example a trigger refusal on unexpected facts), `process_batch` stops the whole batch; the
  worker logs the error class and starts again. The failed event keeps its lease (60 s), is skipped
  until the lease expires, then is claimed again and fails again — **forever**, every minute, and each
  time it stops the rest of that batch. Nothing in the database records the failure, so the finance
  screen cannot show it. This is the unbounded retry the K-12 criterion forbids.
- **Gap K-05.** Stripe keeps events for 30 days. A webhook that never reached us (endpoint down
  longer than Stripe's retry window, a wrong secret during rotation, a suspended connection) is lost:
  the operation stays `not_final` or a refund waits for a payment operation that never appears.
  Nothing asks Stripe what really happened.
- The `stripe==16.0.0` SDK is already a runtime dependency (signature checks), so its API client
  needs no new package. `httpx` is a test dependency only.
- The worker and ingress are local processes (K0b); the ingress writes receipts with the writer login
  (`gba_receipt_writer`), the worker decides with the worker login (`gba_receipt_worker`).
- Migrations 0001–0062 are immutable; the next is **0063**.

## Proposed design (defaults; alternatives in the questions)

### K6a — bounded retries and parked events (local, no network) — migration 0063

1. **Failure record.** New append-only table `gba.provider_event_failures`: `tenant_id`, `event_id`,
   `generation` and `holder` of the lease that failed, `error_class` (a short class name such as
   `CheckViolation`, pattern `^[A-Za-z][A-Za-z0-9_]{0,63}$`; never a message or payload),
   `failed_at`. Only the worker group inserts it, under the same lease fencing as a decision (a
   stale holder cannot record a failure). No update, delete or truncate.
2. **Only event-level errors count.** A failure is recorded when the decision statement raises a
   database error *about this event* (integrity, check, data, raise-exception errors). Lost
   connections, timeouts, an unavailable database and a damaged schema stop the batch **without**
   counting, so an outage never parks healthy events.
3. **The batch goes on.** After recording a failure the worker continues with the next event, so one
   bad event never delays the others.
4. **Backoff.** Discovery skips an event whose latest failure is younger than `2^(n−1)` minutes
   (n = failures since the last release): 1, 2, 4, 8 minutes.
5. **Parking (dead letter).** After **5** failures since the last release the event is *parked*:
   discovery never returns it; nothing is decided or booked. It appears in the finance attention list
   as a new kind `failed` with the error class, the attempt count and the time — no payload.
6. **Release.** A finance user with workflow rights (the same rights as acknowledging attention) may
   press **«Повторить»**: an append-only row in `gba.provider_event_releases` (`event_id`,
   `released_by`, `released_at`, a required note) resets the count, so the worker tries again with the
   same limits. Release never decides, posts or edits facts; a decided event cannot be released.
7. **Metrics and logs.** Counts of failures, parked events and releases by error class; never a
   payload, key, account, ingress ID or message text.
8. **Exhaustive permutations (K-05).** A test generates **every order** of a representative set of
   events of one payment and its refund (PaymentIntent processing, PaymentIntent succeeded, Charge
   succeeded, refund pending, refund succeeded, a stale duplicate) — 720 orders, each in its own
   company — and checks one operation per object, the same final decisions and no regression. A
   second set covers equal timestamps.

### K6b — provider reconciliation by event backfill (read-only network) — migration 0064

1. **Method.** A reconciler asks Stripe for the **events** of each admitted connection
   (`GET /v1/events` with the connected account) for a time window and feeds each one into the
   **same inbox** as a webhook delivery. Event identity is Stripe's event ID, so an event that already
   came by webhook converges as a duplicate and a lost one fills the gap. No new money path, no new
   decision rules: the worker and the finance flow treat it like any other receipt.
2. **Provenance.** A retrieved event is attested with a new verifier `stripe_api_v1` (fetched over TLS
   from the Stripe API with the connection's read-only key) next to today's `stripe_snapshot_v1`
   (signed webhook). The finance screen shows the source. Facts must match the inbox exactly as for
   webhooks; a difference is a visible conflict, never an overwrite.
3. **Scope and limits.** Only admitted connections (`test_access`), only the event types FIN-02
   already supports, test mode only. Window: the last **3 days** every **15 minutes**, plus a manual
   run for up to **30 days** (Stripe's retention). At most 10 pages of 100 events per connection per
   run; 10-second timeout; 429 and 5xx are retried with backoff three times, then the run stops and
   records nothing for that page. **A timeout or refusal never creates a receipt** (no fabricated
   success); the next run tries again.
4. **Process and roles.** A third local process `gorgona_booking.providers.reconcile_main` (`--once`
   or a loop) with the writer login, because it writes receipts. The network call is never made inside
   a database transaction. The key comes from a secret reference (`env:NAME`) as the webhook secrets
   do; it lives only in memory and never reaches a log, a row or an error.
5. **Stuck operations.** The finance screen marks an operation `not_final` for more than 24 hours as
   «давно без итога» so a person sees it even if Stripe has no newer event.
6. **Tests.** A local fake Stripe API (an HTTP server in the test) covers paging, the window,
   duplicates, a lost event that fills the gap, a different fact that becomes a conflict, timeouts,
   429/5xx, a wrong account in the answer (refused), a suspended connection (not asked) and logs
   without secrets.

### K6c — real sandbox run, review and readiness update

1. In the owner's Stripe sandbox (test mode): make a payment and a refund while the ingress is
   **stopped**, so their webhooks are lost; run the reconciler; the events arrive through the inbox,
   the worker decides them, and a finance user can apply them. A second run adds nothing.
2. Full gates, CI for the branch (with the owner's word), one independent review, then update the
   FIN-02 acceptance: K-05 and K-12 from PARTIAL to PASS if the evidence holds. FIN-02 stays
   `technically_verified`; still no live mode and no production approval.

## Questions for the owner (each has a default)

1. **Who may retry a parked event?** Default: a finance user with workflow rights, with the
   «Повторить» button and a required note. Alternative: only an operator command (`gba-db`).
2. **Retry limits?** Default: 5 attempts, waits of 1, 2, 4, 8 minutes. Alternative: other numbers.
3. **How to reconcile?** Default: event backfill from `GET /v1/events` into the same inbox.
   Alternative: also retrieve each stuck object (`GET /v1/payment_intents/…`) — more code, a new kind
   of fact without a Stripe event ID.
4. **Window and schedule?** Default: the last 3 days every 15 minutes, plus a manual run for up to 30
   days.
5. **Which key in the sandbox run?** Default: the Stripe CLI already signed in on this computer serves
   the run (the run's transport calls `stripe get /v1/events --stripe-account …`), so no key enters our
   code or files; the product's own client uses a read-only restricted key from `env:NAME`, tested
   against the fake API. Alternative: you create a read-only restricted key in the Stripe Dashboard
   (Events, PaymentIntents, Charges, Refunds: read) and put it into an environment variable yourself;
   I never see its value.
6. **Order of work?** Default: K6a first (no network, closes the dead-letter part), then K6b, then the
   sandbox run K6c. Each slice: failing tests first, gates, record, code and docs commits, as before.

## Out of scope

Live mode and real money; creating payments, refunds, transfers or payouts; fees, payouts and
disputes; other currencies or providers; Azure, deployment and production migrations; automatic
posting of anything; merging into `main` or publishing a new branch without the owner's word.
