# Next agent handoff — H3 credit voids (H3 complete in code), 2026-10-08

Evidence: [validation](evidence/2026-10-08-h3-credit-voids/VALIDATION.md). Parents:
[corrections handoff](NEXT_AGENT_H3_CORRECTIONS_2026-10-08.md),
[credits handoff](NEXT_AGENT_H3_CREDITS_2026-10-07.md),
[guards handoff](NEXT_AGENT_H3_GUARDS_2026-10-07.md) (runbook and environment).

## 1. State

| Item | Value |
|---|---|
| Repository | `alexeyalexandrov2026-tech/GORGONA-Booking-Platform_new` |
| Branch / checkout | `codex/package-h3-credit-voids`, `C:\Users\alexa\Documents\ChatGPT\gorgona-h3-credit-voids` (git worktree; never bare `git stash`) |
| Parent | `1d96a64` (payment corrections) |
| Code commit | `5ca216560dc016e8a3a5fbe02e0258d28742ba4d` (forward 0029); a docs-only successor holds this file. Read the actual HEAD |
| Stack | PR15 (H1) ← PR16 (H2) ← PR17 (guards 0025–0026) ← credits (0027) ← corrections (0028) ← voids (0029). **No PR exists for credits, corrections or voids** (the app's browser pane is signed out of GitHub; `gh` absent; GitKraken needs `gk auth login`). Open exactly one draft PR per branch, in stack order, each with base = its parent branch |
| Cluster | private PostgreSQL 18.6 `127.0.0.1:51470`, stopped; helpers in `%LOCALAPPDATA%\GorgonaBookingTests\h3-guards-20261007\tools` (`voidtest.ps1`, `void_upgrade_check.py`, `mutate_void_sql.py`) |

Authority, prohibitions and secrets: unchanged from the corrections handoff
(merge, deployment, readiness promotion, provider/funds actions, CodeRabbit
triggers stay unauthorized; never print a DSN or password).

## 2. What the slice does

`0029_credit_voids.sql` plus `credit_notes.void_credit` and
`POST …/credits/{document}/void`: an issued credit is voided by a new immutable
version (state `voided`) that mirrors its journal (`credit_void`), undoes its C
and cancels its untouched refund (C = A, so the cap refuses it). A paid or
unknown-outcome refund, or a credit another refunded credit relied on, gives
`FINANCIAL_RECONCILIATION_REQUIRED`; a plain refund reserve must be released
first. Voided credits stop counting for C, line capacity and payment-correction
dependencies. SQL rechecks the void at commit.

## 3. Next, in order

1. Verify HEAD/origin/CI of the three new branches; open the three draft PRs.
2. Independent review of `0025`–`0029` by someone other than the author.
3. Owner decisions in the four H3 validation records.
4. H4 from the plan: H UI (invoices, settlements, credits, corrections, voids) on
   desktop/mobile with Axe and truthful states, and provider admission records
   without capabilities; then the twelve COMPLETE H cases and exact-SHA CI.
5. HawkScan and Docker gates when available.

## 4. Pitfalls

- GateGuard asks for facts before first edits and destructive commands; its
  destructive-path filter misreads robocopy switches such as `/E` in the same
  command as `Remove-Item`: run them separately.
- New H tables must be added to the scope-restore list in
  `tests/integration/test_location_access.py`; the full suite needs
  `npm run build` in `web` first.
- psycopg async on Windows needs a selector event loop
  (`asyncio.run(..., loop_factory=asyncio.SelectorEventLoop)`).

## Copyable prompt

~~~text
Continue GORGONA Package H after the H3 credit-voids slice (code 5ca2165, forward
0029) in C:\Users\alexa\Documents\ChatGPT\gorgona-h3-credit-voids, branch
codex/package-h3-credit-voids. Stack: PR15 <- PR16 <- PR17 (guards) <- credits
(0027) <- corrections (0028) <- voids (0029); nothing merged; no PR yet for the
three newest branches: check, then open exactly one draft PR per branch in stack
order (base = parent branch). Read docs/plan/NEXT_AGENT_H3_VOIDS_2026-10-08.md and
the four H3 VALIDATION.md records first; verify HEAD, origin and current-head CI
before changing anything. Next: independent review of 0025-0029, owner decisions,
then H4 (UI and admission records). Not authorized: merge/auto-merge,
force-push, rebase/amend of published commits, reset/clean, deployment,
production migration, Azure/provider/funds/credentials actions, FIN-03/FIN-02
promotion. Keep secrets out of Git and output. Private PG 51470 and helpers under
%LOCALAPPDATA%\GorgonaBookingTests\h3-guards-20261007; one executor per cluster;
do not touch clusters 51454, 51455, 51456, 51458, 51460, 51462; published
migrations are frozen (fix forward with 0030).
~~~
