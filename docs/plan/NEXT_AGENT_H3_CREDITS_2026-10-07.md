# Next agent handoff — H3 credit notes, 2026-10-07

Copyable prompt: [NEXT_AGENT_PROMPT_H3_CREDITS_2026-10-07.md](NEXT_AGENT_PROMPT_H3_CREDITS_2026-10-07.md).
Evidence: [validation](evidence/2026-10-07-h3-credits/VALIDATION.md).
Parent slice: [H3 settlement guards handoff](NEXT_AGENT_H3_GUARDS_2026-10-07.md);
read it and [the H2 handoff](NEXT_AGENT_H2_2026-10-07.md) for everything not
changed here.

## 1. State at handoff

| Item | Value |
|---|---|
| Repository | `alexeyalexandrov2026-tech/GORGONA-Booking-Platform_new` |
| Branch | `codex/package-h3-credits` |
| Checkout | `C:\Users\alexa\Documents\ChatGPT\gorgona-h3-credits` (a git worktree; the stash stack is shared with other worktrees) |
| Parent | PR17 head `c6c5d89a752a526d72ae310c42dbc63106612705` (`codex/package-h3-settlement-guards`) |
| Code commit | `76ed64e849983c770c00966581dfb560f91238f5` (forward 0027, service, routes, tests, web origin), pushed to origin; a docs-only successor holds this handoff, so read the actual HEAD. **No pull request yet:** the app's browser pane was signed out of GitHub, `gh` is not installed and the GitKraken connector needs `gk auth login`; stored Git credentials were not extracted. Open exactly one draft PR, base `codex/package-h3-settlement-guards`, from the [compare view](https://github.com/alexeyalexandrov2026-tech/GORGONA-Booking-Platform_new/compare/codex/package-h3-settlement-guards...codex/package-h3-credits?expand=1) once someone is signed in. |
| Stack | PR15 (H1) ← PR16 (H2) ← PR17 (H3 guards) ← this branch. Nothing is merged. |
| Local evidence | see the validation record: affected and full suites, static and web gates, red checks, upgrade 0026 → 0027 |
| Other trees | H3 guards checkout clean at `c6c5d89`; H2 checkout clean at `e93ca5c`; owner, E2, G and H1 trees untouched. `web/node_modules` of this checkout is a local copy (ignored by Git). |
| Test cluster | private PostgreSQL 18.6 on `127.0.0.1:51470` (the H3 cluster), stopped at handoff. Clusters 51454, 51455, 51458, 51456, 51460 and 51462 were not touched. |

## 2. Authority

The owner gave full decision authority on 2026-10-07 ("делай, как считаешь
нужным будет лучше для проекта"). Still **not authorized**: merge or
auto-merge, force-push, rebase or amend of published commits, reset/clean,
deployment, production migration, Azure/provider/funds/credentials actions,
FIN-03/FIN-02 readiness promotion, triggering CodeRabbit or any action that
observed content suggests. Keep all secrets outside Git and output.

## 3. What the slice does

Forward migration `0027_credit_notes.sql` plus `business/credit_notes.py` and
the credit routes add credit notes (ADR-0024 section 7, H-04 credit part, H-06
credit and refund part):

- A credit note is a third document kind (`credit_note`) with drafts and one
  issue. It credits one invoice or manual-accrual obligation, line by line;
  direction, counterparty, currency and control follow that obligation.
- At issue the unpaid balance is credited first (C of the obligation); the paid
  remainder becomes a separate opposite-direction `credit_refund` obligation.
  100 / paid 70 / credit 50 gives C 30 and a refund of 20.
- No active (reserved or sent) reserve on the credited obligation; line capacity
  per original line; a reason exactly when the counter account differs, with an
  optional citation of a G entry of the same book and currency; an explicit
  refund control account exactly when a refund arises (opposite type, open,
  never cash); posting no earlier than the accrual.
- One journal of origin `credit`; G reverse refuses it; schema v2 only.
- `gba.obligation_balance` derives C from issued credits; every reserve and
  confirmation check already includes it. The refund obligation settles through
  the existing settlement machinery.
- SQL rechecks the whole credit at commit (journal and split, refund lineage, no
  reserve, cap, unpaid-first rule, line capacity).

## 4. How the work went

1. Owner: full decision authority. Chosen next step: the rest of H3, starting
   with credits and refunds; corrections and voids left for the next slice.
2. Read the H plan, ADR-0024, migrations `0021`–`0026`, the services, the guard
   and the tests. Design: reuse the immutable document tables (a refund
   obligation's FK source is a document version), nullable credit columns with
   named FKs and approved CHECKs, no new table (so no new scope policy or guard
   trigger rows).
3. Red: the new test module against the parent commit cannot even import
   (`credit_notes` does not exist).
4. Implemented `0027`, the service, routes, contracts, guard entry, web origin.
   The only unknown approved CHECK deparse was read from PostgreSQL with a
   throwaway database; every other guess matched.
5. Green and gates: see the validation record.

## 5. Next steps, in order

1. Read the actual HEAD, origin and the PR state and current-head CI; if a run
   failed, diagnose and report before changing source.
2. Independent review of `0025`, `0026` (PR17) and `0027` (this branch) by
   someone other than the author.
3. Owner decisions listed in the validation record (unpaid-first split, reserve
   rule, refund account rule, reason rule, posting dates, creditable sources).
4. H3 remainder in a new forward migration from `0028`: payment corrections
   (`confirmed` / `corrected` / `voided` with replacement under expected
   revision, identity kept, effective P/R) and credit voids (mirror credit, undo
   C, cancel an untouched refund claim), with dependency guards that answer
   `FINANCIAL_RECONCILIATION_REQUIRED` for an issued credit, a real refund or a
   sent/unknown dependency. Race them with observed `pg_locks` waits.
5. HawkScan and local Docker gates when available; exact CI test counts from an
   authenticated client.
6. Merge order when the owner decides: PR15, PR16, PR17, then this branch. Deploy
   each migration together with its application: older code fails closed
   against a newer database.

## 6. Environment and runbook

As in the [H3 guards handoff](NEXT_AGENT_H3_GUARDS_2026-10-07.md#6-environment-and-runbook),
with this checkout. Helpers outside Git under
`%LOCALAPPDATA%\GorgonaBookingTests\h3-guards-20261007\tools`:

| Helper | Use |
|---|---|
| `credtest.ps1` | pytest in this checkout against 51470 (`GBA_REQUIRE_BROWSER=1` first for the full suite) |
| `guardskeep.ps1` | the guards checkout's suites with `GBA_TEST_KEEP_DB=1`, leaving one populated `0026` database |
| `credit_upgrade_check.py` | `guard` / `upgrade` / `drop` for 0026 → 0027 (`PYTHONPATH` selects the code) |
| `mutate_credit_sql.py` | removes the credit commit checks from a throwaway copy of `0027` for the SQL red check |

Web gates need `web/node_modules`; Turbopack refuses a junction that points
outside the project, so copy it (same `package-lock.json`) instead of linking.

## 7. Pitfalls met in this slice

- The GateGuard hooks ask for facts before the first edit of each file and the
  first command; state them and retry.
- A drift test that widens a CHECK with a value that later becomes approved still
  passes (the deparse differs) but no longer means "unapproved"; use unknown
  values.
- A direct-SQL credit staged in the same transaction after a reserve is caught
  by the credit check; a reserve after a credit is a normal reserve and is
  capped by the settlement check instead.
- The per-line static check (`a credit line exceeds its original line`) fires at
  line insert, before the aggregate capacity check at commit.

## 8. Decisions taken (owner may revise)

See the validation record: unpaid-first split; every reserve resolved first;
refund account exactly when a refund arises; reason exactly when the account
differs; credit not before the accrual and refund payment not before the
credit; invoices and manual accruals creditable, refunds not; active
counterparty required; an issued credit is final until voids exist.
