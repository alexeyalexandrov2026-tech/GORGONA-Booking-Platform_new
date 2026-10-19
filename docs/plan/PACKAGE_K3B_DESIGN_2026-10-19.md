# Package K3b — linking earlier manual payments to provider operations (design, 2026-10-19)

**Status: owner decisions received 2026-10-19; locally implemented in `8bb2eb4`**
([validation](evidence/2026-10-19-k3b-provider-links/VALIDATION.md)). Local branch
`codex/package-k3b-provider-links` from `199eada` (the decisions). Expected
migration **0054** (H). Nothing here is published or deployed; no provider call, account,
credential or real money.

## Owner decisions (2026-10-19)

The owner took the four defaults below:

1. **Link only**: the link records that the manual payment is this provider operation; money stays
   as recorded, no new journal; a linked operation is never applied.
2. Amount, currency and direction must be **exactly equal**; the manual date may differ from the
   provider's date by **up to 3 days**, both shown.
3. **One to one**: one manual payment links to one operation.
4. A linked manual payment can still be **voided or corrected** through H; the link stays in the
   history, and a voided link puts the operation under manual review again.

## Refinements found during implementation

- The table is named `provider_payment_links` (not `external_payment_…`): it moves no money, so it
  takes the H immutable, lock and check triggers without the payment consistency trigger.
- No separate truncate trigger: the runtime has no TRUNCATE privilege, as for every H table.
- The state of a link whose payment is voided or no longer states the amount is `needs_review`.

## Goal

Plan slice K3 says "explicit prior-payment verification adds no duplicate journal; unresolved
cross-path identity needs review" ([K plan](PACKAGE_K_PLAN_2026-10-15.md), acceptance K-10). K3a
refuses to apply a provider operation when a manual payment of the book already names its
provider ID (`PROVIDER_PAYMENT_LINK_REQUIRED`), because applying it would count the same money
twice ([K3a design](PACKAGE_K3A_DESIGN_2026-10-17.md), owner decision 4). K3b gives a finance user
a way out of that dead end.

Observable result: an operation blocked by an earlier manual payment shows as "needs linking"; a
finance user links it to that manual payment after the facts are compared; the money stays as it
was recorded (no new journal), the operation becomes "linked" and can never be applied; every
link is permanent history.

## What exists (inspected)

- `external_payments`: immutable rows with revisions; a manual payment has
  `attestation='manual_attestation'`, its own cash account, alias, reference, amount and actual
  date; void and correction are human H paths with reasons and evidence.
- K3a: `external_payment_provenance` (one row per provider-observed payment, operation unique per
  company); `gba.assert_provider_payment` and `settlements.confirm_provider` refuse an
  application when any manual payment of the book names the provider ID in its reference
  (word-boundary match), voided or not.
- K4a/K4b: the operation list, detail and runbook; the blocked operation is listed as `observed`
  and only the refusal says it needs linking.

## Proposed model

1. **State.** A new operation state `needs_link` (not applied; a manual payment of the book names
   its ID) shown before the user tries to apply, and `linked` (permanently linked to a manual
   payment). The SQL state of K4a gains both; the filter and runbook follow.
2. **Link record** (migration 0054, H, guarded like 0052): `external_payment_links` —
   `(tenant_id, book_id, payment_id)` primary key, `operation_id` unique per company, the matching
   success event, `created_by` (user), `created_at`, a required note. Append-only, FORCE RLS,
   company scope. A payment is either provider-observed (provenance) or manual-and-linked, never
   both; an operation is either applied or linked, never both.
3. **What must match** (checked in SQL when the link is inserted, under the ledger and operation
   locks): the operation is observed (success decided, no review, no differing delivery, not
   revoked) and not applied; the manual payment is in the book, not voided, names the provider ID;
   same direction (payment ↔ receivable, refund ↔ payable), same currency; the amount and date
   rule by Question 2; one manual payment per operation by Question 3.
4. **Money.** Linking writes no journal and changes no payment, allocation or settlement. The
   manual payment keeps its cash account (often the bank, where a payout arrived); moving amounts
   between the bank and the clearing account stays a manual ledger entry.
5. **After linking.** By Question 4: the linked manual payment can still be voided or corrected
   through H, and the link stays in the history (default), or a linked payment is frozen.
6. **API and screen.** `PUT …/provider-operations/{id}/link` with `payment_id` and `note`
   (finance manage; the same payment and note again returns the link); the operation detail
   shows the candidate manual payment(s) and the comparison; a "Link to this manual payment"
   form with a confirmation. Applying a linked operation is refused (`PROVIDER_OPERATION_LINKED`).

## Acceptance criteria (failing tests first)

| id | Requirement |
|---|---|
| L-01 | An operation blocked by a manual payment is listed as `needs_link` (server filter complete across pages) |
| L-02 | Linking an observed operation to the matching manual payment writes one link, no journal, no payment or settlement change; the operation becomes `linked` |
| L-03 | Mismatches refuse with a reason: direction, currency, amount or date (by Question 2), voided payment, payment of another book, payment that does not name the ID, operation not observed, already applied, already linked |
| L-04 | One operation links once; concurrent links wait (observed `pg_locks` wait) and one wins; a link and an application of the same operation serialise and only one succeeds |
| L-05 | A linked operation can never be applied (`PROVIDER_OPERATION_LINKED`); provenance and link exclude each other in SQL |
| L-06 | Direct SQL cannot forge, change or delete a link; company scope; worker and writer cannot reach it; guard drift refuses with 503 |
| L-07 | Void and correction of a linked manual payment behave by Question 4; the link stays in the history |
| L-08 | Finance rights; branch, front desk, artist and foreign company refused |
| L-09 | Real desktop and mobile browser with axe: needs-link state, comparison, link form, refusal |
| L-10 | Runbook updated (new states and code); K3a, K4a, K4b, H and the full suite stay green |

## Questions for the owner

1. **What linking does.** Default: *link only* — record that the manual payment is this provider
   operation; money stays as recorded, no new journal. Alternative: *replace* — void the manual
   payment and apply the provider operation to the clearing account (two journals and a reversal;
   the reserve must be restored first).
2. **How strict the comparison is.** Default: amount, currency and direction must be exactly
   equal; the manual date may differ from the provider's date by up to 3 days (shown side by side).
   Alternatives: dates must be equal; or any date, shown only.
3. **Several manual payments for one operation.** Default: refused — one manual payment links to
   one operation, amounts equal. Alternative: several manual payments whose amounts add up to the
   operation's amount.
4. **Changing a linked manual payment.** Default: still allowed through H void and correction; the
   link stays in the history and a voided link makes the operation `needs_review` again.
   Alternative: a linked payment can no longer be voided or corrected.

## Out of scope

Automatic linking, linking by anything other than the provider ID in the reference, fees and
payouts, moving money between the bank and the clearing account, other currencies, provider
retrieval (K2b, needs K0), publishing beyond CI and deployment.
