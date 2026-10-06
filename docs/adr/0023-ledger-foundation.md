# ADR-0023 — Ledger foundation: books, chart of accounts, double entry and periods (FIN-01)

- Status: **Proposed (2026-10-06)** — waiting for the owner's four decisions in the
  [stage 2 plan](../plan/STAGE2_PLAN_2026-10-06.md). No code before acceptance.
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

## Decision (proposed, defaults marked; owner choices in the plan)

1. **Module and rights.** Implement module `finance` (readiness `implemented` with the
   code, `technically_verified` only after exact-SHA CI). New permissions
   `finance.read`, `finance.manage` (owner and manager) and `finance.close` (owner
   only by default, decision 4); not delegable, not platform support, company-wide
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

Later packages (invoices and payments H, materials J, provider events K) post through
this ledger instead of keeping their own money records. Currency conversion, group
consolidation, year-end closing and imports are separate decisions. Production
migration and Azure deployment need the owner's explicit authorization.
