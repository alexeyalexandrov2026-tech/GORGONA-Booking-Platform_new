# ADR-0023 — Ledger foundation: books, chart of accounts, double entry and periods (FIN-01)

- Status: **Accepted (2026-10-06)** — owner decisions: ledger foundation only
  (invoices and payments in package H), neutral starter chart of accounts, no
  currency conversion, and both owner and manager may close and reopen periods
  ([stage 2 plan](../plan/STAGE2_PLAN_2026-10-06.md)).
- Scope: master plan §11.1 and criterion FIN-01; first package (G) of stage 2.
  Builds on ADR-0015 (tenant-owned legal entities), ADR-0019 (configuration and
  module gates), ADR-0002/0014 (tenancy, RLS and location scope).

## Context

Stage 1 is technically closed ([evidence](../plan/evidence/2026-10-06-stage1/ACCEPTANCE.md)).
No financial records exist: bookings carry `total_cents` and `currency` as a price
snapshot, which the interface shows as booking value per currency and never as paid
money or revenue (BASE-03). Legal entities are owner-entered drafts with a legal
name only. The registry lists `finance` as a planned optional module depending on
`organization`.

§11.1 requires double entry with a chart of accounts; every entry has a legal entity,
period, currency, source and a unique business-operation identifier; debit equals
credit; posted entries are never edited or deleted; closed periods are enforced in
the same transaction; corrections are separate operations; different currencies are
not summed without an explicit rate, date and source; currency scale is not assumed
to be two decimals. FIN-01: "double entry is balanced; different legal entities and
currencies are not mixed; a closed period forbids posting".

## Decision

1. **Module and rights.** Implement module `finance` (readiness `implemented` with the
   code, `technically_verified` only after exact-SHA CI). New permissions
   `finance.read`, `finance.manage` and `finance.close` (owner and manager, owner
   decision 4); not delegable, not platform support, company-wide
   members only. Permission map version increments.
2. **Books.** `gba.ledger_books`: one per legal entity, insert-only versions with base
   currency (ISO 4217 alpha code from a built-in table with its minor-unit scale),
   fiscal-year start month and accounting start date. A book is required before any
   entry; its base currency cannot change once entries exist.
3. **Money.** Amounts are `bigint` minor units with the currency; the scale comes from
   the built-in table (0, 2 or 3). API amounts are decimal strings validated against
   the scale (no floats). Booking `*_cents` keep their meaning.
4. **Accounts.** `gba.ledger_accounts` per book: stable code, name, type (asset,
   liability, equity, revenue, expense), archived flag; insert-only versions; an
   account with lines cannot change type or disappear. Starter template by default
   (decision 2), never country tax accounts.
5. **Entries.** `gba.journal_entries` (book, entry date, period, currency, source
   kind, source id, memo, reverses-entry reference) and `gba.journal_lines` (account,
   side, positive minor-unit amount). `(book, source kind, source id)` is unique, so a
   repeated business operation cannot post twice; commands also use idempotency keys.
   A deferred constraint trigger checks at commit that each entry has at least two
   lines and that debits equal credits; all lines share the entry's currency and book
   (decision 3: no conversion in this package). Entries and lines are never updated
   or deleted; a reversal is a new entry with mirrored lines referencing the original,
   allowed once.
6. **Periods.** Calendar months of the book (fiscal year by start month). Close and
   reopen are insert-only events with actor, time and reason; the latest event
   decides. Posting and closing take `gba:ledger:{tenant}` exclusively; a trigger
   refuses lines in a closed period, so a close racing a posting has exactly one order.
7. **Reports.** Trial balance per book, period range and currency from posted lines;
   no cross-entity or cross-currency totals.
8. **Boundary.** FORCE RLS, tenant isolation and restrictive company-only policies on
   every table; schema guard definitions and module gates as in ADR-0019/0020;
   reference-only idempotency receipts; audit details without memos or counterparty
   names; reads, history and reports continue when the module is disabled.

## Acceptance (FIN-01 technical)

- An unbalanced or single-line entry is refused by SQL, also when inserted directly.
- One entry cannot mix legal entities or currencies; reports never sum currencies.
- A closed period refuses posting; close and post racing give one consistent order;
  reopening is recorded; posted history is unchanged byte for byte.
- A repeated command or business operation creates one entry; a reversal is allowed
  once and nets the original to zero.
- Access refused for artists, front desk, branch-limited members, delegates, platform
  support and other companies; damaged policies or gates fail readiness (503).
- Real browser: book, accounts, entry, reversal, period close; mobile and axe.

## Consequences

### Local implementation — 2026-10-06

Package G is implemented in codex/package-g-ledger-review (migration 0020,
permission map v5, real ledger API and /ledger UI). The original uncommitted work
is preserved separately. A reproduced early-SET-CONSTRAINTS balance bypass is
closed by deferred triggers on both entries and lines. Readiness inspects the
approved integrity and access definitions from the packaged migration.
Mutations require READ COMMITTED to prevent stale month/account/module snapshots
after lock waits. Extra original lines after reversal are rejected. Function source
checks are exact, including SQL literals. A minimal session-scoped recovery reference
and serialized resolve/cancel API preserve unknown outcomes across reload/navigation;
permanent cancellation records reject delayed originals. Recovery has no financial
effect and remains available when finance is disabled. No financial payload or token
is persisted in browser storage; cross-browser intent deduplication still needs an
explicit business operation ID. Trial balances validate each row equation as well
as column totals. These decisions close all five initial independent review findings.
Follow-up review found and closed entity reselection state loss. A further
fault-injection check found that an extra permissive policy could OR away tenant
isolation while preserving the approved policy name. Readiness now rejects any
unapproved permissive policy on the eight ledger tables; SELECT/INSERT/ALL and
public/runtime/member-role variants are covered. No production policy repair is
automatic. Final evidence must correspond to the SHA containing this guard.
[Current evidence and acceptance gates](../plan/evidence/2026-10-06-ledger/ACCEPTANCE.md).
Finance and FIN-01 are technically verified in a separate acceptance commit,
based on 95a0de4: full local 858 passed/4 skipped, exact-SHA CI 861 passed/1 skipped,
earlier independent runtime/browser review and final independent guard-delta
review. Positive API/browser readiness overrides are removed; publication uses the
normal registry. The acceptance HEAD must also pass fresh CI. This is not
authorization for production migration or deployment.

Later packages (invoices and payments H, materials J, provider events K) post through
this ledger instead of keeping their own money records. Currency conversion, group
consolidation, year-end closing and imports are separate decisions. Production
migration and Azure deployment need the owner's explicit authorization.
