# Package R, slice R8c — rental screens: inspections, usage, settlement, charges, refunds, reconciliation (2026-11-11)

Plan: [PACKAGE_RENT_PLAN_2026-11-03.md](PACKAGE_RENT_PLAN_2026-11-03.md), slice R8, acceptance R-09.
Previous slice: [R8b](PACKAGE_R8B_DESIGN_2026-11-11.md); handoff
[NEXT_AGENT_PACKAGE_R8C_2026-11-11.md](NEXT_AGENT_PACKAGE_R8C_2026-11-11.md). Branch
`codex/package-r8c-rental-settlement-screens` from the R8b docs commit `977a96f`.

Same process: failing tests first, gates on the VM `gorgona-dev`, a source-bound record, code and docs commits, and a
push for CI without a PR. The owner said "continue" on 2026-11-11 and gave the word to start the VM.

R8 is split three ways:

- R8a (done): the catalogue, availability and bookings.
- R8b (done): rate cards, the agreement and the security.
- **R8c**: what happens after the agreement — handover and return inspections, usage, the settlement, damage charges,
  refunds and the reconciliation.

## Scope of R8c

- Web only; **no API change and no migration** (the next migration stays 0108).
- A new `web/components/rental-settlement.tsx` on the booking page of `web/components/rental.tsx`, after the agreement
  and the security of R8b.
- Strict contracts of the R6a-R7c responses in `web/lib/rental-contracts.ts`, and their calls in
  `web/lib/rental-api.ts`.
- Tests:
  - `web/tests/rental-contracts.spec.ts` (new cases);
  - `web/tests/rental-settlement.spec.ts` (real browser, desktop and mobile, `test:management:rental-settlement`);
  - `api/tests/integration/test_r8c_rental_settlement_browser.py`.

## Decisions (R8c, agent)

1. **Inspections** (R6a):
   - The list shows kind, unit, meter, level, note, who and when, and each inspection's marks (position, area,
     severity, note, new).
   - The "Inspection" form records the handover until there is one, then the return.
   - It has a meter (only when the class counts one), a level from 0 to 100, a note, and marks added one row at a
     time (area, severity, note).
   - Only a return mark can be marked new.
   - The server decides the order, the agreement and the assignment, and refuses what it does not accept.
   - Photos on marks stay with the API for now.
2. **Usage** (R6b), shown as the server reads it: state, period end, overdue hours, distance, allowance, excess and
   its amount, with the time it used.
3. **The settlement** (R7a):
   - It appears after the return.
   - The form names a book, a receivable account and a revenue account (the book and account pickers of the money
     screens), an invoice date, an optional due date and a number.
   - The view shows the rental, excess, late and total amounts and the FIN-03 invoice's state.
   - Issuing, posting and paying the invoice stay in FIN-03's own screens.
4. **Damage charges** (R7b):
   - The form chooses one or more new return marks not charged before, and gives an amount, a reason, the book and
     accounts, a date and a number.
   - The list shows each charge.
   - The server requires `rental.approve`.
5. **Refunds** (R7b):
   - An external refund has a reference and the time it was made.
   - A credit refund names an issued invoice of the booking. It is offered only when the reconciliation shows one,
     and needs a credit date and a number.
   - The list shows each refund. The server requires `rental.approve` and keeps refunds within the ceiling.
6. **The reconciliation** (R7c) shows:
   - the documents, with kind, number, amount, state, principal, paid, credited and open;
   - the refunds and their state;
   - the security figures;
   - the totals.

   A booking without a settlement shows none.
7. **As before:**
   - every figure is the server's;
   - money is entered in major units and sent in minor units;
   - a command keeps its Idempotency-Key until it succeeds;
   - accessibility and times are handled as in R8a.

## Acceptance of R8c — NOT TESTED

| id | Requirement | Result |
|---|---|---|
| R8c-01 | Strict contracts accept every R6a-R7c response the screens read and refuse unknown fields and bad values; the management client knows every route | NOT TESTED |
| R8c-02 | In a real browser (desktop and mobile) an owner assigns a unit, records the handover (meter 1000) and the return (meter 1300, one new major mark), reads the usage (distance 300 over 200 allowed: excess 100 at 25.00), settles (rental 100.00 and excess 25.00: 125.00), charges the new mark 80.00, records an external refund of 10.00 and reads the reconciliation (charged 205.00, refunded externally 10.00); the database holds them | NOT TESTED |
| R8c-03 | Axe finds no violation; no horizontal scroll on mobile | NOT TESTED |
| R8c-04 | Web static checks and the full suite stay green | NOT TESTED |

## Not in R8c

- Photos on marks.
- Agreement extensions and extras on screen.
- Provider evidence (R5b).
- Issuing FIN-03 documents. They stay in FIN-03's screens, so a credit refund is tested through the API (R7b) and
  only offered here.
- Acceptance of RENT-01 (R9).
