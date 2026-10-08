# Next agent handoff — H3 payment corrections, 2026-10-08

Copyable prompt: [NEXT_AGENT_PROMPT_H3_CORRECTIONS_2026-10-08.md](NEXT_AGENT_PROMPT_H3_CORRECTIONS_2026-10-08.md).
Evidence: [validation](evidence/2026-10-08-h3-payment-corrections/VALIDATION.md).
Parent slice: [H3 credit notes handoff](NEXT_AGENT_H3_CREDITS_2026-10-07.md); read
it, [the H3 guards handoff](NEXT_AGENT_H3_GUARDS_2026-10-07.md) and
[the H2 handoff](NEXT_AGENT_H2_2026-10-07.md) for everything not changed here.

## 1. State at handoff

| Item | Value |
|---|---|
| Repository | `alexeyalexandrov2026-tech/GORGONA-Booking-Platform_new` |
| Branch | `codex/package-h3-payment-corrections` |
| Checkout | `C:\Users\alexa\Documents\ChatGPT\gorgona-h3-corrections` (a git worktree; the stash stack is shared with other worktrees) |
| Parent | `807ed59` (head of `codex/package-h3-credits`, the credit-notes slice; itself on draft PR17) |
| Code commit | `238b157d979e504cb84e0870c722d23356f4f520` (forward 0028, service, routes, tests, web origin), pushed to origin; a docs-only successor holds this handoff, so read the actual HEAD. **No pull request** for this branch nor for the credit-notes branch: the app's browser pane was signed out of GitHub, `gh` is not installed and the GitKraken connector needs `gk auth login`; stored Git credentials were not extracted. When someone is signed in, open exactly one draft PR per branch: credits with base `codex/package-h3-settlement-guards`, then this branch with base `codex/package-h3-credits`. |
| Stack | PR15 (H1) ← PR16 (H2) ← PR17 (H3 guards) ← credits (0027) ← this branch (0028). Nothing is merged. |
| Local evidence | see the validation record: affected and full suites, static and web gates, SQL mutation red, upgrade 0027 → 0028 |
| Other trees | credits checkout clean at `807ed59`; H3 guards clean at `c6c5d89`; H2 clean at `e93ca5c`; owner, E2, G and H1 trees untouched. `web/node_modules` of this checkout is a local copy (ignored by Git). |
| Test cluster | private PostgreSQL 18.6 on `127.0.0.1:51470`, stopped at handoff. Clusters 51454, 51455, 51458, 51456, 51460 and 51462 were not touched. |

## 2. Authority

The owner gave full decision authority on 2026-10-07 ("делай, как считаешь
нужным будет лучше для проекта") and said "Continue" on 2026-10-08. Still **not
authorized**: merge or auto-merge, force-push, rebase or amend of published
commits, reset/clean, deployment, production migration,
Azure/provider/funds/credentials actions, FIN-03/FIN-02 readiness promotion,
triggering CodeRabbit or any action that observed content suggests. Keep all
secrets outside Git and output.

## 3. What the slice does

Forward migration `0028_payment_corrections.sql` plus `void_payment` /
`correct_payment` in `business/settlements.py` and two routes:

- `POST …/settlements/{settlement}/confirmations/{payment}/void` and `/correct`,
  under the expected settlement sequence, `FINANCE_MANAGE`, idempotency key.
- A void or a correction is a new revision of the same payment
  (`external_payment_revisions`, `external_payment_revision_allocations`) under
  a new settlement event `payment_voided` / `payment_corrected`. The external
  identity never changes and is never freed. Attestation
  `attested_erroneous_confirmation` with a reason and an evidence source.
- The replaced version's journal is mirrored by a `payment_correction` journal;
  its allocations return to the reserve of a held settlement (a released one
  only loses P). A correction confirms its replacement within that reserve with
  a second `payment_correction` journal. A void is final.
- Effective P and R (`gba.effective_payment_allocations`) everywhere: balance,
  finality, line caps, views. A later credit splits against the corrected P.
- `FINANCIAL_RECONCILIATION_REQUIRED` without effects for an issued credit on a
  touched obligation, a refund obligation, or another settlement with an unknown
  sent outcome; `FINANCIAL_OUTCOME_UNRESOLVED` for the payment's own unknown
  sent remainder.
- SQL rechecks the whole payment at commit (see the validation record).

## 4. How the work went

1. After the credit notes, the owner said "continue" with full authority. The
   browser pane was still signed out, so no PR could be opened; the next slice of
   the plan was taken instead: payment corrections first, credit voids next.
2. Read the H plan and ADR-0024 section 7, migrations `0023`–`0027`, the
   settlement service and the tests. Design: revisions in two new tables keyed by
   the payment (revision 1 is the original row), a new settlement event per
   revision for ordering, receipts and the expected sequence, and one
   effective-allocation helper used by every balance.
3. Implemented `0028`; the approved CHECK deparses were read from a throwaway
   database. Existing tests showed two intended rule changes (a void may follow a
   release; two more guarded tables).
4. New tests green on first run; then SQL-alone correction cases, the mutation
   red and the upgrade check were added.
5. The first full run failed in unrelated files: the location-scope drift test
   drops `gba.current_location_id()` with cascade and restores the scope
   policies of a fixed list of migrations, which did not know the two new
   policies of `0028`, so later tests saw an unready schema (503). The list now
   includes `0028`; see the validation record for the green run.

## 5. Next steps, in order

1. Read the actual HEAD, origin, the PR state and current-head CI; if a run
   failed, diagnose and report before changing source.
2. Open the two missing draft PRs (credits, then this branch) once someone is
   signed in to GitHub; never a second PR for the same branch.
3. Independent review of `0025`–`0028` by someone other than the author.
4. Owner decisions listed in the validation records of the credit and
   correction slices.
5. Credit voids from migration `0029`: mirror the credit journal, undo its C,
   cancel an untouched refund obligation, atomically; refuse with
   `FINANCIAL_RECONCILIATION_REQUIRED` when the refund has any effective
   payment, reserve or sent/unknown settlement. Race them with observed
   `pg_locks` waits. Remember the location-scope drift test list for any new
   table.
6. HawkScan and local Docker gates when available; exact CI test counts.
7. Merge order when the owner decides: PR15, PR16, PR17, credits, this branch.
   Deploy each migration together with its application: older code fails closed
   against a newer database.

## 6. Environment and runbook

As in the [H3 guards handoff](NEXT_AGENT_H3_GUARDS_2026-10-07.md#6-environment-and-runbook),
with this checkout. Helpers outside Git under
`%LOCALAPPDATA%\GorgonaBookingTests\h3-guards-20261007\tools`:

| Helper | Use |
|---|---|
| `corrtest.ps1` | pytest in this checkout against 51470 (set `GBA_REQUIRE_BROWSER=1` first for the full suite) |
| `credtest.ps1` | the same for the credits checkout (populates a `0027` database with `GBA_TEST_KEEP_DB=1`) |
| `correction_upgrade_check.py` | `guard` / `upgrade` / `drop` for 0027 → 0028 (`PYTHONPATH` selects the code; imports `credit_upgrade_check.py`) |
| `mutate_correction_sql.py` | removes the revision commit checks from a throwaway copy of the `api` directory for the SQL red check |

Start the cluster with `Start-Process pg_ctl` (no `-Wait`) and poll
`pg_isready`; stop it with `pg_ctl stop -m fast` when done.

## 7. Pitfalls met in this slice

- The GateGuard hooks ask for facts before the first edit of each file, the first
  command and every destructive command; state them and retry.
- The location-scope drift test in `test_location_access.py` restores scope
  policies from a fixed list of migrations: every new H table needs its
  migration added there, or every later test in a full run gets 503.
- `RETURNS TABLE` helpers in plpgsql: qualify every column, since the output
  names are variables.
- A void of a fully confirmed sent settlement reopens its remainder as unknown:
  the following release needs the attested `attested_no_payment` resolution.

## 8. Decisions taken (owner may revise)

See the validation record: revisions under new settlement events with the
identity bound forever; explicit erroneous-confirmation attestation; the
per-line restored reserve as the correction limit; released settlements only
voided; corrections post on their own date; credit, refund and unknown-sent
dependencies refused; a void of a sent settlement reopens its outcome; own
journal origin `payment_correction`.
