# Package R, slice R4a — rental rate cards and quotes (2026-11-04)

Plan: [PACKAGE_RENT_PLAN_2026-11-03.md](PACKAGE_RENT_PLAN_2026-11-03.md), decision 4, acceptance R-04.
Previous slice: [R3b](PACKAGE_R3B_DESIGN_2026-11-03.md); handoff [NEXT_AGENT_PACKAGE_R4_2026-11-03.md](NEXT_AGENT_PACKAGE_R4_2026-11-03.md).
Branch `codex/package-r4a-rental-rates` from the R3b docs commit `90fb28f`. Same process: failing tests first,
gates on the VM `gorgona-dev`, a source-bound record, code and docs commits, push for CI without a PR.

R4 is split: **R4a** versioned rate cards and the quote derived from them (this); **R4b** the agreement as the frozen
accepted quote, extensions and changes as insert-only versions checked against occupancy.

## Scope

- Migration **0100**: `rental_rate_cards` (insert-only versions per class and branch) and `rental_rate_card_extras`;
  module gate; tenant isolation; branch scope last. No change to the shared occupancy.
- Pure quote function `business/rental_quote.py`; service `business/rental_rates.py`; routes
  `POST classes/{id}/rate-cards`, `GET classes/{id}/rate-cards`, `POST quotes` (a class, a pickup branch, a period and
  extras) and `GET bookings/{id}/quote`.

## Decisions (R4a, agent)

1. **A rate card** belongs to a class and a branch and carries one currency (ISO 4217, three capital letters), rates
   in minor units per `hour`, `day`, `week` (7 days) and `month` (30 days) — at least one, each above zero when
   present — an included meter allowance per day and the excess rate per meter unit (both optional; used by R6 and R7),
   and extras. It is insert-only: a change is a new version, numbered 1, 2, 3 per class and branch with no gap, and
   takes effect at `effective_from`, which may not be earlier than the moment it is recorded (no back-dating). The card
   **in force at an instant** is the version with the latest `effective_from` at or before it.
2. **An extra** is a plain priced line of a card (additional driver, child seat, insurance product as a plain extra):
   a code (lower-case letters, digits, `_`, unique on the card), a name, a price in minor units and a unit
   (`per_day` or `per_rental`). Insurance terms and providers are out of the package.
3. **The quote** is deterministic and computed, never typed: the rental charge is the cheapest cover of the period by
   whole hours, days, weeks and months of the rates the card has (a cover may exceed the period; only the amount and
   the chosen counts are reported); each extra adds its price times the quantity, per rental day
   (`ceil(period / 24 h)`) for `per_day`. Totals are integers in minor units; the period is at most 366 days. No card in
   force: `RENTAL_NO_RATE` (409); an extra the card does not have: 422.
4. **A booking's quote** uses the card in force for its class at its pickup branch at the moment the booking was
   made; a later card version never changes it. Freezing a quote into an agreement is R4b.
5. **The database** keeps cards whole: insert-only (updates and deletes refused by grants), the version sequence and
   the no-back-dating rule checked by a guard, the class and branch must exist in the company, the extras only with
   their card in the same transaction.
6. **Rules as before**: `rental.manage` to record a card, `rental.read` to list and quote; idempotency scope
   `rental.rate_card`; module off writes nothing; branch scope by the card's branch; another company sees nothing.

## Acceptance of R4a — PASS 2026-11-04 (code `79d678f`, [evidence](evidence/2026-11-04-r4a-rental-rates/CHECKS.json))

| id | Requirement | Result |
|---|---|---|
| R4a-01 | Rate cards are insert-only versions per class and branch with no gap; back-dating, missing or non-positive rates, a bad currency and duplicate extras are refused | PASS |
| R4a-02 | The quote is the cheapest cover by the card's units plus extras, in integer minor units; no card in force is `RENTAL_NO_RATE` | PASS |
| R4a-03 | A booking is quoted from the card in force when it was made; a later version does not change it | PASS |
| R4a-04 | The database refuses updates, deletes, a forged version and extras without their card; module off writes nothing; scope holds | PASS |
| R4a-05 | 0099 -> 0100 keeps every row; the full suite stays green | PASS |

## Not in R4a

The frozen agreement, extensions and changes (R4b); security of payment (R5); meters and excess use (R6); invoices
(R7); screens (R8); taxes, discounts and dynamic pricing.
