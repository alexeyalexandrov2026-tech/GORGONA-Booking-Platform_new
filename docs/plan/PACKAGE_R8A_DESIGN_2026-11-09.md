# Package R, slice R8a — rental screens: catalogue, availability and bookings (2026-11-09)

Plan: [PACKAGE_RENT_PLAN_2026-11-03.md](PACKAGE_RENT_PLAN_2026-11-03.md), slice R8, acceptance R-09.
Previous slice: [R7c](PACKAGE_R7C_DESIGN_2026-11-08.md); handoff [NEXT_AGENT_PACKAGE_R8_2026-11-09.md](NEXT_AGENT_PACKAGE_R8_2026-11-09.md).
Branch `codex/package-r8a-rental-screens` from the R7c docs commit `a2bfc54`. Same process: failing tests first, gates
on the VM `gorgona-dev`, a source-bound record, code and docs commits, push for CI without a PR. The parent session
relayed on 2026-11-09 to go straight on to R8 under the same rules.

R8 is split like the construction screens (O7a, O7b): **R8a** the rental page, its strict contracts, the catalogue,
availability and bookings with their unit; **R8b** rate cards, the agreement, the security, handover and return, and
the settlement with charges, refunds and the reconciliation.

## Scope of R8a

- Web only; **no API change and no migration** (next migration stays 0108). If a test shows that a read the screen
  needs is missing, the slice stops and records it instead of adding a route quietly.
- `web/app/rental/page.tsx`, `web/components/rental.tsx` (classes, units, availability, bookings),
  `web/lib/rental-contracts.ts` (strict zod contracts of every R1-R3a response used, registered in
  `managementResponseSchema`), `web/lib/rental-api.ts` (reads and commands), a navigation entry "Rental".
- Tests: `web/tests/rental-contracts.spec.ts` (contracts, in `test:unit`), `web/tests/rental.spec.ts` (real browser,
  desktop and mobile, `test:management:rental`) and `api/tests/integration/test_r8a_rental_browser.py` (seeds through
  the routes, runs the browser, reads the database back).

## Decisions (R8a, agent)

1. **Who sees it**: owners and managers who are active members and not delegates (rental rights are theirs, R1);
   others see a short note. The server decides every read and command.
2. **Catalogue**: classes with code, name, meter and attributes; a new class or a revision with the revision the
   screen read. Units of a class with identifier, branch, state and attribute values; a new unit or a revision.
3. **Availability**: a class, a branch and a period give the server's units, booked and available, never computed
   on the screen.
4. **Bookings**: the list with number, class, period, branches and state (cancelled or not); a new booking names a
   class, a customer (an active counterparty with the customer role), pickup and return branches, a period and an
   optional note; a booking is cancelled with a reason; a unit of the class is assigned and the assignment history
   shows replaced and released ones. A command keeps its Idempotency-Key until it succeeds.
5. **Accessibility and times** as in O7a: named forms, tables in focusable regions, the business zone for times,
   axe without violations, no horizontal scroll at 375 px.

## Acceptance of R8a — PASS 2026-11-11 (code `06b3c25`, [evidence](evidence/2026-11-09-r8a-rental-screens/CHECKS.json))

| id | Requirement | Result |
|---|---|---|
| R8a-01 | Strict contracts accept every R1-R3a response the screens read and refuse unknown fields and bad values | PASS |
| R8a-02 | In a real browser (desktop and mobile) an owner creates a class and a unit, reads availability, books, assigns the unit and cancels another booking; the database holds them | PASS |
| R8a-03 | Axe finds no violation; no horizontal scroll on mobile; a member without rental rights sees the note | PASS |
| R8a-04 | Web static checks and the full suite stay green | PASS |

## Not in R8a

Rate cards, agreements, security, inspections, settlement, charges, refunds and the reconciliation (R8b); blocks and
moves of units; acceptance (R9).
