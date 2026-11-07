# Package R, slice R5b — provider evidence for a rental card hold, sandbox only (2026-11-07)

Plan: [PACKAGE_RENT_PLAN_2026-11-03.md](PACKAGE_RENT_PLAN_2026-11-03.md), decision 5, acceptance R-05.
Previous slice: [R5a](PACKAGE_R5A_DESIGN_2026-11-07.md); handoff [NEXT_AGENT_PACKAGE_R5B_2026-11-07.md](NEXT_AGENT_PACKAGE_R5B_2026-11-07.md).
Branch `codex/package-r5b-rental-provider-holds` from the R5a docs commit `7129d83`. Same process: failing tests first,
gates on the VM `gorgona-dev`, a source-bound record, code and docs commits, push for CI without a PR. The owner
asked to go on to the next stage right after R5a.

## Scope

- Migration **0104**: `rental_security_provider_links` (insert-only): a recorded security event (R5a) of a
  `card_hold` security names the verified provider receipt that shows it; guards under the connection row lock and
  the class row lock; module gate; tenant isolation; branch scope last.
- Service `business/rental_security_provider.py`; route `POST bookings/{id}/security/events/{sequence}/provider`;
  the security view shows each event's provider evidence.

## Decisions (R5b, agent)

1. **No new provider contract and no live provider.** The provider inbox already accepts only signature-checked
   test-mode (`livemode` false) events of an admitted, not revoked connection of the company; R5b only reads them.
   The platform never calls the provider; a person records the event (R5a) and names the receipt that shows it.
2. **What a receipt shows**, checked by the database against the stored facts: `held` by an observed charge of the
   intent that is paid and not captured, for the security amount; `captured` by the intent's success with the amount
   received equal to everything captured so far; `released` or `expired` by the intent's cancellation, or by its
   success when the rest was never captured. The currency is the security currency; one intent per security.
3. **A link is permanent history**: one per security event, one security per intent, never an operation, payment or
   journal entry; the security figures stay those of R5a; nothing changes a charge.
4. **Permissions and rules as before**: `rental.manage` (a capture's evidence needs `rental.approve`); idempotency
   scope `rental.security_provider`; module off writes nothing; branch scope by the booking's pickup branch; another
   company, another connection or a revoked connection is refused; direct SQL updates and deletes refused.

## Acceptance of R5b — NOT TESTED

| id | Requirement | Result |
|---|---|---|
| R5b-01 | A held, a partial capture and the release of a card hold link to the sandbox receipts of one intent; the view shows them | NOT TESTED |
| R5b-02 | A receipt of another intent, amount, currency, kind or state, a second link, a non-card security and an unrecorded event are refused | NOT TESTED |
| R5b-03 | Another company's or a revoked connection's receipt is refused; capture evidence needs `rental.approve` | NOT TESTED |
| R5b-04 | The database refuses updates, deletes and forged links; module off writes nothing; scope holds | NOT TESTED |
| R5b-05 | 0103 -> 0104 keeps every row; the provider suites and the full suite stay green | NOT TESTED |

## Not in R5b

Creating or capturing a hold at the provider; live mode; refunds and damage charges (R6); invoices (R7); screens (R8).
