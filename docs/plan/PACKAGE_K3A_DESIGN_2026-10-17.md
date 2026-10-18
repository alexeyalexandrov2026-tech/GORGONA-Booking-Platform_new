# Package K3a — observed provider money into H (design, 2026-10-17)

**Status: owner decisions received 2026-10-17; locally implemented in `2f91368`**
([validation](evidence/2026-10-17-k3a-provider-money/VALIDATION.md)). Local branch
`codex/package-k3a-provider-money` from `6ba065c` (the proposal). Migrations 0051 (K access)
and 0052 (H provenance). Nothing here is published or deployed; no provider call, account,
credential or real money.

## Owner decisions (2026-10-17)

The owner answered the four questions below: a finance user applies each operation; one
registered clearing account; **USD** only; manual voids and corrections are allowed as for manual
payments.

1. A finance user applies each observed operation; the worker never posts.
2. One registered provider clearing asset account per connection (a connection belongs to one
   book); gross amounts go there; fees and payouts stay manual.
3. USD only. Stripe states amounts in the smallest unit and USD is not a zero-decimal currency
   (docs.stripe.com/currencies, checked 2026-10-17), matching `gba.currencies` (USD, 2).
4. A provider payment is voided or corrected through the existing H paths, like a manual one; the
   revision is a human attestation and the provider provenance stays in the history. Because the
   H identity of a payment is permanent, an operation is applied at most once, also after a void.
   An earlier manual payment that names the same provider ID still refuses the application
   ("needs linking"); linking is K3b.

## Refinements found during implementation design

- Two migrations, because each guard reads its own package: **0051** grants the runtime
  company-scoped select on `provider_operations` and `provider_event_decisions`, the lock column
  (`update (currency)`, refused by the immutability trigger) and execute on
  `gba.provider_receipt_operation`; **0052** (H) widens `external_payments.attestation`, adds
  `provider_clearing_accounts` and `external_payment_provenance` with the H trigger set
  (immutable, ledger lock, workflow, deferred consistency, check) and `gba.assert_provider_payment`,
  called from `gba.assert_payment_consistent` in the transaction that applies the payment.
- The command receipt stays `settlement_confirm`: the H rule pairs a `confirmed` event with that
  receipt operation, and the attestation and provenance already tell the paths apart (found in
  dev-3; a separate command kind was dropped).
- `provider_receipt_connections` already has one `book_id`: the payment, every attestation and the
  clearing account must name that book.
- A refund applies only to `credit_refund` obligations (from a credit note), and its parent
  payment must be applied in the book and not voided.
- The actual external date is the earliest `created` of the operation's success events in the
  business time zone; that event is stored as `success_event_id`.

## Goal

Plan slice K3 is "provider provenance and atomic G/H payment/refund application"
([K plan](PACKAGE_K_PLAN_2026-10-15.md), proposed flow items 7–10). K3a is its first local part:
a finance user applies one **observed** provider payment or refund (K2a decision `success`) to an
existing **reserved** H settlement. The database takes the amount, currency and date from the
attested facts, rechecks every delivery of the operation, and records one external payment with
provider provenance, its allocations and one balanced G journal in one transaction, or nothing.

Observable result: one provider operation moves money at most once, in one book; the amount is
the provider's, never a typed one; a conflict, a pending event, a revoked connection, a closed
period or a missing reserve gives a refusal and no partial row; manual H payments stay as they are.

## What exists (inspected)

- H: `settlements.confirm` (`business/settlements.py`) moves a reserved line to confirmed money,
  writes `external_payments` (attestation only `manual_attestation`, identity
  `(book, direction, source_account_alias, external_reference)`), allocations and a `payment`
  journal under `gba.lock_ledger`; caps, accrual date, period close and cash-not-control checks
  are in Python and SQL triggers (0023–0026). A refund is a payable settlement of the refund
  obligation that a credit note creates (0027).
- G: a journal needs `created_by` = a real user (`gba.users`); `ledger_period_closed` refuses a
  closed month in the same transaction.
- K: attestations carry `book_id` and `connection_id`; K2a gives `provider_operations` and
  append-only `provider_event_decisions`; the runtime already reads the inbox, deliveries and
  attestations of its company, but not operations or decisions.

So a person is needed for every journal, and the existing H confirmation is the posting path to
reuse, not to imitate.

## Proposed model (migration 0051)

1. **Who applies.** A finance user of the company (same rights as a manual confirmation), through
   the runtime, with an idempotency key. The worker gets no money authority. (Question 1.)
2. **Read access.** The runtime gets company-scoped select on `provider_operations` and
   `provider_event_decisions` (RLS as today); no insert or update except the lock column below.
3. **Provenance row** `gba.external_payment_provenance`, append-only: primary key
   `(tenant_id, book_id, payment_id)`, `operation_id` unique per company, `success_event_id`
   (derived by the trigger), `created_by` (user), `created_at`, `created_transaction`. The runtime
   inserts only IDs; the trigger derives and checks the rest.
4. **Provenance on the payment.** `external_payments.attestation` also allows
   `provider_observed`, only together with its application row in the same transaction (deferred
   check, like the existing `created_transaction` pattern). For such a payment
   `source_account_alias` = `stripe_connect`, `external_reference` = the `pi_…`/`re_…` ID, so the
   existing identity key also stops a manual payment typed with the same text.
5. **Checks in the trigger**, under `gba.lock_ledger` and a lock of the operation row (the K1d
   pattern: one-column update grant, immutability trigger), so a worker deciding another event of
   the same operation waits:
   - every committed attested event whose facts map to the operation is decided; none is
     `needs_review`; no delivery of those events has `matches_original = false`; at least one
     decision is `success` (all successes agree, as K2a already enforces);
   - the connection and its verification config are not revoked; every attestation of those
     events names this book;
   - currency: `upper(provider currency)` = the settlement's currency and is in the verified list
     (Question 3); amount = the success amount (`amount_received_minor` for payments, refund
     `amount_minor`), equal to the sum of allocations, each within its reserved line;
   - direction: a payment confirms a `receivable` settlement; a refund confirms a `payable` one,
     only when its parent PaymentIntent was applied in this book, to the same counterparty, and the
     refunds applied to that parent stay within the parent's amount;
   - actual external date = the success event's `created` in the business time zone; the entry
     date is the user's, not before the accrual and not in a closed period (existing G check);
   - the cash account is the registered clearing account of this connection and book
     (Question 2), an open asset account that is no control account;
   - no manual external payment of this book names the same provider ID in its reference
     (normalised by `gba.external_identity_key`); then the answer is "needs linking", not a post.
6. **Posting.** Python reuses the confirm path (`settlements.confirm` split into a shared posting
   primitive), with the provider amount and date; no forged manual attestation. One command
   receipt `settlement_confirm` (see refinements).
7. **After application.** Facts that arrive later never change money. A late conflicting event or
   delivery of an applied operation is listed by a read function as "applied, later conflict" for
   manual review (K4 shows it). Manual void and correction work for `provider_observed` payments
   as for manual ones (owner decision 4); the provenance row stays.
8. **Guards.** The receipt schema guard and the financial schema guard cover the new table,
   columns, checks, triggers and grants; drift refuses the application path.
9. **API.** Finance routes: list observed operations with their decision state (cursor), and
   apply one operation to a settlement. No UI (K4).

## Acceptance criteria (failing tests first)

| id | Requirement |
|---|---|
| M-01 | An observed payment applied to a reserved receivable settlement posts one external payment, its allocations and one balanced journal with provider provenance; repeat with the same key returns the same result |
| M-02 | The same operation under another key, another settlement or another book is refused; two concurrent applications: the second waits (observed `pg_locks` wait) and is refused |
| M-03 | Amount, currency, direction, counterparty, cap and accrual date come from facts and H; a typed amount is not accepted; any mismatch is refused with no partial row |
| M-04 | A pending, `not_final`-only or `needs_review` event, a mismatching delivery, a revoked connection or config, or an attestation of another book refuses the application |
| M-05 | A worker deciding another event of the operation and an application serialise on the operation row (observed wait); whichever commits first is seen by the other |
| M-06 | A refund applies only to a payable settlement after its parent payment was applied in the book, within the parent's amount; partial and repeated refunds keep the cap |
| M-07 | A closed period or a period closing concurrently (observed wait on the ledger lock) gives one legal outcome and no partial journal |
| M-08 | Direct SQL: runtime cannot insert a `provider_observed` payment without its application, alter or delete applications, or read another company's operations; the worker and writer cannot reach H tables |
| M-09 | A manual payment that names the same provider ID refuses the application ("needs linking"); a provider payment can be voided and corrected like a manual one and is never applied again; existing manual paths behave as before |
| M-10 | Facts arriving after application change no money and appear as "applied, later conflict" |
| M-11 | Guard drift refuses the application; repaired schema passes; existing H, K and full suite stay green |

## Questions for the owner

1. **Who triggers money.** Default: a finance user applies each observed operation (the database
   takes amount and date from the facts); the worker never posts. Alternative: automatic posting
   when a binding registered in advance matches.
2. **Account.** Default: one registered provider clearing asset account per connection and book;
   gross amounts go there; provider fees and bank payouts stay manual (out of K3a). Alternative:
   the user chooses the account at each application.
3. **Currencies.** Default: start with one currency you name; its minor-unit rule is checked
   against current Stripe documentation during implementation; every other currency is refused.
4. **Mistakes and old manual records.** Default: a provider payment cannot be voided or corrected
   through the manual H paths, and linking an earlier manual payment to a provider operation is a
   later slice (K3b); until then such a case is refused as "needs linking".

## Out of scope

Provider retrieval and admission (K0, K2b), automatic posting (unless Question 1 says otherwise),
fees, payouts, disputes, FX, revenue recognition, linking earlier manual payments (K3b), UI and
runbook (K4), worker entry point, publishing and deployment.
