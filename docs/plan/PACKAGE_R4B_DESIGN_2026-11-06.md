# Package R, slice R4b — the rental agreement as the frozen accepted quote, and its change versions (2026-11-06)

Plan: [PACKAGE_RENT_PLAN_2026-11-03.md](PACKAGE_RENT_PLAN_2026-11-03.md), decision 4, acceptance R-04.
Previous slice: [R4a](PACKAGE_R4A_DESIGN_2026-11-04.md); handoff [NEXT_AGENT_PACKAGE_R4B_2026-11-04.md](NEXT_AGENT_PACKAGE_R4B_2026-11-04.md).
Branch `codex/package-r4b-rental-agreements` from the R4a docs commit `4902f23`. Same process: failing tests first,
gates on the VM `gorgona-dev`, a source-bound record, code and docs commits, push for CI without a PR.

R4 is split again: **R4b** the agreement (version 1 freezes the accepted quote) and its change versions over the same
period (this); **R4c** extensions and shortened periods, which move the booking period and its holds on the shared
occupancy.

## Scope

- Migration **0101**: `rental_agreements` (one per booking), `rental_agreement_versions` and
  `rental_agreement_version_extras` (insert-only); module gate; tenant isolation; branch scope last. No change to the
  shared occupancy and to the availability peak.
- Service `business/rental_agreements.py`; routes `POST bookings/{id}/agreement` (accept: version 1),
  `POST bookings/{id}/agreement/versions` (a change) and `GET bookings/{id}/agreement`.

## Decisions (R4b, agent)

1. **The agreement is the accepted quote, frozen.** Accepting a booking's quote records version 1: the rate card in
   force when the booking was made (R4a decision 4), the booking period, the chosen extras with their name, price and
   unit copied from that card, the counts of hours, days, weeks and months, the rental amount, the extras amounts and
   the total, in the card's currency. A later rate card version never changes it. A cancelled booking takes no
   agreement and no new version (`RENTAL_BOOKING_CANCELLED`); a booking has at most one agreement
   (`RENTAL_AGREEMENT_EXISTS`, 409).
2. **Who accepted it and how**: the source (`platform`, `paper`, `email`), the name of the person who accepted, the
   time they accepted (not in the future) and who recorded it. Customers answering on the platform themselves need a
   grant (plan decision 9) and come with the screens; until then the business records the answer with its source. A
   signed copy as a document version comes with handover documents (R6).
3. **A change is a new insert-only version** with a reason: the same period and the same frozen rate card, a new set
   of extras priced from that card, numbered 2, 3 with no gap. The current agreement is the latest version; earlier
   versions stay. Changing the period is R4c.
4. **The database** keeps agreements whole: insert-only (updates and deletes refused by grants); version 1 names the
   card in force for the booking's class at its pickup branch when the booking was made, and its period is the
   booking's; a later version keeps the card and the period; versions follow 1, 2, 3; an extra line copies its card
   extra (code, name, price, unit) and its amount is the price times the quantity, per rental day for `per_day`; at
   commit the total is the rental plus the extras of the version. The rental amount (the cheapest cover) is computed by
   the service from the frozen card; the database checks it is positive.
5. **Rules as before**: `rental.manage` to accept and change, `rental.read` to read; idempotency scopes
   `rental.agreement` and `rental.agreement_version`; module off writes nothing; branch scope by the booking's pickup
   branch; another company sees nothing.

## Acceptance of R4b — NOT TESTED

| id | Requirement | Result |
|---|---|---|
| R4b-01 | Accepting records version 1 frozen from the card in force at the booking with the chosen extras, the source, who accepted and when; a later card version does not change it | NOT TESTED |
| R4b-02 | A change is version 2, 3 with a reason, the same card and period and new extras; earlier versions stay | NOT TESTED |
| R4b-03 | A second agreement, a cancelled booking, an unknown extra, a future acceptance time and a missing reason are refused | NOT TESTED |
| R4b-04 | The database refuses updates, deletes, a forged card, period, version, extra price or total; module off writes nothing; scope holds | NOT TESTED |
| R4b-05 | 0100 -> 0101 keeps every row; the full suite stays green | NOT TESTED |

## Not in R4b

Extensions and shortened periods (R4c); security of payment (R5); signed copies and inspections (R6); invoices (R7);
screens and customers answering on the platform (R8); taxes and discounts.
