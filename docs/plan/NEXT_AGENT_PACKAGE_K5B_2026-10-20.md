# Next agent — Package K after K5b, 2026-10-20

Read this whole file before any command. It replaces the
[K0b handoff](NEXT_AGENT_PACKAGE_K0B_2026-10-20.md); that file's sections 2 (what K0b added), 5
(how a slice is run) and 6 (traps) and the [K5a-fix handoff](NEXT_AGENT_PACKAGE_K5A_FIX_2026-10-19.md)
sections 2 and 6 still apply. The ready-to-paste prompt is
[NEXT_AGENT_PACKAGE_K5B_PROMPT_2026-10-20.md](NEXT_AGENT_PACKAGE_K5B_PROMPT_2026-10-20.md).

## 0. Owner decision that frames everything (2026-10-20)

Production is **all 39 directions of the master plan at once**, one launch; a business of any
direction can sign up and work. Never plan, estimate or describe a salon-only (or one-industry)
launch. See the block at the top of the [master plan](GORGONA_MASTER_PLAN.md) and §1 point 13.

## 1. State (verified 2026-10-20)

- Checkout `C:/Users/alexa/.codex/worktrees/package-j-review2-fixes/Gorgona Booking`, local branch
  `codex/package-k5b-open-findings`: docs `1b89958` (K0c postponed, later resumed), K5b source
  `58cf561d0f2d065ad44dac850182fdd61d3fae20`, then the docs commit. Run `git status` and
  `git log -5 --oneline` first; the tree must be clean.
- **Not published.** On GitHub: `codex/package-k0a-design` `4e0665c` and
  `codex/package-k0b-entry-points` `90b236e` (CI SUCCESS, pushed on the owner's «Да»). The K5b branch
  is local and needs the owner's word to push.
- `main` is `fedd0f1`. Migrations 0001–0060 are immutable; the next is **0061**. FIN-02 and STOCK-01
  stay `planned`; ADR-0026 and ADR-0027 stay Proposed.
- K5b gates: focused 775 passed in 841.46s (0:14:01); full 2315 passed, 4 skipped in 2410.31s
  (0:40:10); static, web and build PASS; runtime audit 0.
  [Validation](evidence/2026-10-20-k5b-open-findings/VALIDATION.md),
  [CHECKS.json](evidence/2026-10-20-k5b-open-findings/CHECKS.json). Run folder
  `C:\Users\alexa\AppData\Local\GorgonaBookingTests\package-k5b-20261020-1b89958`.

## 2. What K5b changed

- 0059 (K): inbox index by connection; the runtime cannot insert events or deliveries — only the
  receipt writer can. Tests that archive a receipt use `writer_pool` (its fixture now lives in
  `test_provider_event_inbox`); a writer cannot read journals, so count them through the runtime.
- 0060 (H): a link needs the enabled finance workflow (GBM01); the link check calls `pg_catalog.abs`.
- Decoder: a Stripe charge fact is `amount_captured`; test fixtures carry it (`decided.stripe()` sets
  it for a charge).
- Web: manual financial editors default to today in the business time zone (`timezone` in `Common`).

## 3. Rules (unchanged except Stripe)

- Without the owner's separate, direct word: no push, PR, merge, `main` change; no rebase, amend,
  reset, clean, force-push; no readiness change, CodeRabbit; no Azure or other cloud action,
  production migration or deployment; no live-mode provider action or real money. Each Azure action
  needs consent for that action. Never repeat the Azure sign-in address.
- **Stripe (owner, 2026-10-20: «ты сам все делай, сам все настраивай» and «Да»):** the agent runs the
  Stripe CLI itself, in the owner's **sandbox (test mode) only**. The owner alone signs in and accepts
  Stripe's terms in the dashboard; the agent never enters a password, never reads or prints a key or
  the signing secret, and passes the `stripe listen` signing secret from one process to the ingress
  only in memory. No live mode.
- Do not touch `C:/Users/alexa/Documents/ChatGPT/Gorgona Booking`. One executor per checkout and per
  disposable cluster (explicit port, `127.0.0.1`, `max_connections=400`; never 51454, 51458, 51474,
  51511, 49981; check `postmaster.pid` before stopping; never `pg_ctl` with captured output). Secrets
  only in memory; races only with an observed `pg_locks` wait; never hide a failure. Work inline;
  write to the owner in Russian, simply; the owner is they/them.

## 4. K0c — the real Stripe test run: DONE, PASS (2026-10-20)

The owner enabled Connect (platform) and entered the test SSN; the agent created the connected test
account `acct_1USjOo0mkpWSHVnd` and ran the steps below with
[`test_k0c_run.py.txt`](evidence/2026-10-20-k0c-stripe-sandbox/test_k0c_run.py.txt):
[validation](evidence/2026-10-20-k0c-stripe-sandbox/VALIDATION.md). **Next: K5-CI** (publish the final
branch for CI only on the owner's word, read the result once, VALIDATION K-01–K-14) **and K5c** (the
owner's readiness decision for FIN-02). The original plan of the run follows.


Done on 2026-10-20:
- Stripe CLI 1.54.1 at `C:\Users\alexa\AppData\Local\GorgonaBookingTests\stripe-cli-1.54.1\bin\stripe.exe`
  (zip SHA-256 `afc82ef5…5441` matched Stripe's checksum file; the Windows binary is unsigned).
- `stripe login` (device flow) approved by the owner: the CLI is authorized for
  **Alexey AAA logistics LLC · sandbox `acct_1UJtGO0mkpVWlKYX`** (platform; country US; USD).
- In Git Bash set `MSYS_NO_PATHCONV=1`, otherwise `/v1/...` paths are mangled.

Blocked on the owner: creating a connected account answers "You can only create new accounts if
you've signed up for Connect". The owner must enable Connect **in that sandbox** (dashboard account
switcher on the sandbox → Connect → Get started → platform → accept terms). Then the agent:

1. Creates one connected test account (controller: no Stripe dashboard, fees and losses on the
   application, requirement collection by the application; card_payments and transfers), fills
   Stripe's documented **test** onboarding values only, and tells the owner which values were used.
2. Starts its own local stack on 127.0.0.1 (own cluster, `gba-db bootstrap`/`migrate`, writer and
   worker logins, a FAKE company with finance enabled, USD book, clearing account, the API), provisions
   the connection with the connected account ID and the API version seen on its events, a
   verification config with `secret_ref = env:GBA_STRIPE_TEST_WEBHOOK_SECRET`, a route, and records
   the admission (`gba-db admit-receipt-connection … --state test_access`).
3. Runs `stripe listen --forward-connect-to localhost:8787/v1/provider-events/stripe/<ingress_id>`
   with the event list of the K0b handoff, captures the signing secret in memory only and starts the
   ingress and the worker with it; then `stripe trigger payment_intent.succeeded`,
   `payment_intent.payment_failed` and `charge.refunded` with `--stripe-account acct_…`.
4. Applies one payment and one refund on the finance screen, shows a suspension refusing a further
   event, writes a redacted record (IDs, decisions, amounts; no payload, key or customer data), stops
   every process and its cluster. Then K5-CI (exact-head CI, VALIDATION K-01–K-14; publication needs
   the owner's word) and K5c (the owner's readiness decision).

## 5. Open items

1. K0c (above), then K5-CI and K5c.
2. Finding 15 limits (ISK/UGX scale, missing currencies) while USD only; finding 6 has no
   production-volume timing.
3. Not built (owner defaults): approved/live admission state, the H4 link, a separate "not admitted"
   list state, worker schedule, alerts and dashboards.
4. Beyond K: everything the master plan needs for one launch of all 39 directions (industry modules,
   stage 9 operations in Azure, acceptance).
