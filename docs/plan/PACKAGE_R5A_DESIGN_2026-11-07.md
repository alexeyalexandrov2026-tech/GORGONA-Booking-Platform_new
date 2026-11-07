# Package R, slice R5a — recorded security of payment for a rental booking (2026-11-07)

Plan: [PACKAGE_RENT_PLAN_2026-11-03.md](PACKAGE_RENT_PLAN_2026-11-03.md), decision 5, acceptance R-05.
Previous slice: [R4c](PACKAGE_R4C_DESIGN_2026-11-06.md); handoff [NEXT_AGENT_PACKAGE_R5_2026-11-07.md](NEXT_AGENT_PACKAGE_R5_2026-11-07.md).
Branch `codex/package-r5a-rental-security` from the R4c docs commit `63b2318`. Same process: failing tests first,
gates on the VM `gorgona-dev`, a source-bound record, code and docs commits, push for CI without a PR. The owner
asked to go on to the next stage right after R4c.

## Split

R5 is split: **R5a** (this) records security held outside the platform (a card hold at a terminal, cash, a bank
transfer) with its own states; **R5b** adds provider holds in sandbox through the existing provider inbox. No live
provider and no live card hold in either without the owner's word.

## Scope

- Migration **0103**: `rental_securities` (one per booking, the amount and the currency of the agreement's frozen
  card) and `rental_security_events` (insert-only, numbered 1, 2, 3 per security); guards under the security row lock;
  module gate; tenant isolation; branch scope last.
- Service `business/rental_security.py`; routes `POST bookings/{id}/security`, `POST bookings/{id}/security/events`,
  `GET bookings/{id}/security`.

## Decisions (R5a, agent)

1. **A security request** belongs to a booking with an agreement that is not cancelled: an amount above zero, the
   currency of the latest agreement version's rate card, a method (`card_hold`, `cash`, `bank_transfer`, `other`), who
   requested it and when. One per booking in R5a; the row never changes.
2. **Its states are derived from insert-only events**, never stored: requested (no event), `held` (once, first, the
   full amount, an external reference, an optional hold expiry), `captured` (after held, part or all of what is still
   held, with a basis), `released` (the rest, once, closes) and `expired` (the rest, once, closes; also from requested
   with nothing held). Nothing follows a closing event. The database checks the order and the amounts, so captured
   plus released or expired equals what was held.
3. **Separate from charges**: no reference to charges, invoices or payments; capturing records only the security.
   The damage charge (R6) and the invoice (R7) cite it later.
4. **Permissions**: requesting, holding, releasing and expiring need `rental.manage`; capturing needs
   `rental.approve`. Idempotency scopes `rental.security` and `rental.security_event`.
5. **Rules as before**: module off writes nothing; branch scope by the booking's pickup branch; another company sees
   nothing; direct SQL updates and deletes refused.

## Acceptance of R5a — NOT TESTED

| id | Requirement | Result |
|---|---|---|
| R5a-01 | A request records the amount in the agreement currency; held, captured in parts and released record the rest once; the view derives the state and every figure | NOT TESTED |
| R5a-02 | Capture above what is held, an event after closing, a second hold, a release before hold and a capture without basis are refused; expiry closes requested or held | NOT TESTED |
| R5a-03 | No agreement, a cancelled booking, a second request, a bad amount or method are refused; capture needs `rental.approve` | NOT TESTED |
| R5a-04 | The database refuses updates, deletes, forged sequences, amounts and currency; module off writes nothing; scope holds | NOT TESTED |
| R5a-05 | 0102 -> 0103 keeps every row; the full suite stays green | NOT TESTED |

## Not in R5a

Provider holds in sandbox (R5b); handover, return, damage charges and refunds (R6); invoices and the reconciliation per
agreement (R7); screens (R8); more than one security per booking; live providers.
