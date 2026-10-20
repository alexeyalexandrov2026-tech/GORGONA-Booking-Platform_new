> **Superseded 2026-10-20** by the [K5b handoff](NEXT_AGENT_PACKAGE_K5B_2026-10-20.md).

# Next agent — Package K after K0b, 2026-10-20

Read this whole file before any command. It replaces the
[K5a-fix handoff](NEXT_AGENT_PACKAGE_K5A_FIX_2026-10-19.md); that file's section 2 (master plan
frame) and section 6 (traps) still apply and are not repeated in full. The ready-to-paste prompt is
[NEXT_AGENT_PACKAGE_K0B_PROMPT_2026-10-20.md](NEXT_AGENT_PACKAGE_K0B_PROMPT_2026-10-20.md).

## 1. State (verified 2026-10-20)

- Checkout `C:/Users/alexa/.codex/worktrees/package-j-review2-fixes/Gorgona Booking`, local branch
  `codex/package-k0b-entry-points`: K0a design `7d6ef1e` and the owner's answers `4e0665c` (both on
  local branch `codex/package-k0a-design`), K0b source `1eacc1d73c4d13a759be95084d994ef1be6cf4fe`, then the docs commit. Run
  `git status` and `git log -5 --oneline` first; the tree must be clean.
- **Not published.** `codex/package-k5a-review-fixes` is on GitHub at `d03ae53` (pushed 2026-10-20 on
  the owner's «i trust you»); the K0a and K0b branches are local and need the owner's word to push.
- `main` is `fedd0f1`; published J is `df88c20`. Migrations 0001–0058 are immutable; the next is
  **0059**. FIN-02 and STOCK-01 stay `planned`; ADR-0026 and ADR-0027 stay Proposed.
- K0b gates: focused PASS: 623 passed in 703.66s (0:11:43); full PASS: 2308 passed, 4 skipped in 2316.92s (0:38:36); ruff, strict mypy (340 files), web
  typecheck, lint, format, unit, build PASS; runtime npm audit 0, development audit 5 high (existing).
  [Validation](evidence/2026-10-20-k0b-entry-points/VALIDATION.md),
  [CHECKS.json](evidence/2026-10-20-k0b-entry-points/CHECKS.json),
  [K0a design and answers](PACKAGE_K0A_DESIGN_2026-10-20.md).

## 2. What K0b added

- **Admission (0057, K).** `gba.provider_connection_admissions`: owner-only, append-only revisions
  (`test_access` or `suspended`, test mode, USD, charge and refund flags, the connection's own
  account, evidence). The writer serves, the worker decides and money applies only while the latest
  revision is `test_access` (for money: with the operation's flag). One advisory lock per
  connection (`gba:provider-admission:<tenant>:<connection>`): exclusive when recording, shared in
  every gate, so a suspension waits for work in flight.
- **Money gate (0058, H)** on provider payments and links; reason `not_admitted` in the service and
  on the screen.
- **Processes.** `python -m gorgona_booking.providers.ingress_main` (needs
  `GBA_RECEIPT_WRITER_DATABASE_URL`, `GBA_RECEIPT_SECRET_REFS=env:GBA_STRIPE_TEST_WEBHOOK_SECRET` and
  that variable; 127.0.0.1 only; port `GBA_RECEIPT_PORT`, default 8787) and
  `python -m gorgona_booking.providers.worker_main [--once] [--interval 5]` (needs
  `GBA_RECEIPT_WORKER_DATABASE_URL`). Each refuses a login of the wrong group before serving.
- **Owner command.** `gba-db admit-receipt-connection --tenant <uuid> --connection <uuid>
  --account acct_… --state test_access|suspended [--operations charge,refund] --evidence "<short note>"`
  over `GBA_MIGRATION_DATABASE_URL`.

## 3. Rules (unchanged; restated)

- Without the owner's separate, direct word: no push, PR, merge, `main` change; no rebase, amend,
  reset, clean, force-push; no readiness change, CodeRabbit; no Azure or other cloud action,
  production migration or deployment; no provider, account, key, credential or money action. Each
  Azure action needs consent for that action. Never repeat the Azure sign-in address.
- Do not touch `C:/Users/alexa/Documents/ChatGPT/Gorgona Booking`.
- **Stripe:** the owner performs `stripe login`, `stripe listen` and every trigger. Agents never
  enter credentials and never see the signing secret; the owner sets it in their own terminal.
- One executor per checkout and per disposable PostgreSQL cluster: explicit port, `127.0.0.1`,
  `max_connections=400`; never ports 51454, 51458, 51474, 51511, 49981 or other executors' clusters;
  compare the data directory and port in `postmaster.pid` before stopping; never start `pg_ctl` with
  captured output.
- Secrets only in memory, never printed; synthetic data in tests. A race counts only with an
  observed `pg_locks` wait. Tests must not rely on an empty shared database. Never hide a failure or
  commit as green while a required suite fails. Report PASS/FAIL/BLOCKED/NOT TESTED with exact
  commands and numbers. Work inline. Write to the owner in Russian, simply; the owner is they/them.

## 4. Next step: K0c — the owner's real Stripe test run

**Owner decision 2026-10-20: K0c is postponed** — no Stripe registration for now («без страйп обойтись»). FIN-02 stays `planned`; manual payments (H) remain the way money is recorded. Do not start K0c until the owner says so. Meanwhile the open K5a review findings 6, 8, 9, 12, 15 and the UTC default of the manual editors are fixed locally, without a provider.


Only with the owner, step by step; stop at any surprise. Before the owner's steps, the agent:

1. Starts a local, owner-run stack on this computer only: its own PostgreSQL cluster (kept for the
   run, explicit port), `gba-db bootstrap` and `gba-db migrate` with fresh in-memory passwords,
   separate writer and worker logins, a FAKE-named test company with finance enabled and a USD book,
   a clearing account, and the API (`python -m gorgona_booking`) for the finance screen. Nothing is
   exposed beyond `127.0.0.1`.
2. Asks the owner for two non-secret values: the **connected test account ID** (`acct_…`) and its
   **API version** (Stripe Dashboard). Provisions the connection with them, a verification config
   with `secret_ref = env:GBA_STRIPE_TEST_WEBHOOK_SECRET`, and a route; tells the owner the path
   `/v1/provider-events/stripe/<ingress_id>`.

Then the owner, in their own terminal:

3. `stripe login` (their test sandbox, the Connect platform).
4. `stripe listen --forward-connect-to localhost:8787/v1/provider-events/stripe/<ingress_id> --events payment_intent.succeeded,payment_intent.payment_failed,charge.refunded,refund.created,refund.updated`
   — it prints a signing secret; the owner sets `GBA_STRIPE_TEST_WEBHOOK_SECRET` in a second terminal
   and starts the ingress and the worker there (the agent gives the exact two commands without any
   secret).
5. `gba-db admit-receipt-connection … --state test_access --evidence "owner test run <date>"`.
6. `stripe trigger payment_intent.succeeded --stripe-account acct_…`, then
   `payment_intent.payment_failed`, then `charge.refunded`, for the same account.
7. On the finance screen: apply one payment and one refund.

After the run the agent reads the database in the company's context and writes a redacted record
(event IDs, decisions, payment and journal IDs, amounts; no payload, secret or customer data), shows
that a suspension refuses a further event, stops every process and its own cluster, and then
prepares K5b (exact-head CI, VALIDATION K-01–K-14) and K5c (the owner's readiness decision).

If the owner prefers to wait, the open review findings (section 6) are the alternative work.

## 5. How a slice is run here

As in the K5a-fix handoff section 5, with the K0b run folder
`C:\Users\alexa\AppData\Local\GorgonaBookingTests\package-k0b-20261020-4e0665c` as the source of
`runner.py`, `run_gates.py`, `write_record.py`. The runner hashes `api`, `web` and `docs/runbooks`:
edit none of them while a gate runs. Build `web` before a focused run that includes a browser test.

## 6. Traps (new in K0b; the K5a-fix list still applies)

- Every receipt, decision and money test needs an admission: `attested.provision(..., admit=True)`
  records one; a hand-made connection must call `record_receipt_admission`.
- uvicorn writes its raw-path access log (with the ingress ID) whenever `uvicorn.access` has any
  handler, whatever `access_log` says; `serve_ingress` disables that logger. Keep it so.
- The running ingress checks the signature time against the real clock: sign test events with the
  current time, not the fixture's fixed instant.
- The worker runs across companies: count decisions of your own company, not the batch total.
- A Python edit through a shell heredoc can turn `\b` or `\n` into control characters: check bytes.

## 7. Open items

1. K0c (above), then K5b and K5c.
2. Review findings 6, 8, 9, 12 and 15; the manual editors still default to the UTC date.
3. Not built (owner defaults): an approved/live admission state, a link to the H4 declaration, a
   separate "not admitted" state in the operations list, worker schedule, alerts and dashboards.
