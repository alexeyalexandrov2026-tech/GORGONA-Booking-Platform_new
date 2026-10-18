# Package K4a — finance screen for provider operations (design, 2026-10-18)

**Status: proposed, not started.** Docs only. Waits for the owner's answers to the three questions
below. Planned local branch `codex/package-k4a-provider-screen` from this proposal. No migration is
expected (next free number stays **0053**). Nothing here is published or deployed; no provider
call, account, credential or real money.

## Goal

Plan slice K4 is "finance review UI and recovery, redacted metrics and operational runbook"
([K plan](PACKAGE_K_PLAN_2026-10-15.md), acceptance K-13). K4a is its first part: the screen a
finance user needs to use K3a. Today an observed provider payment or refund can be applied only
through the API ([K3a design](PACKAGE_K3A_DESIGN_2026-10-17.md)).

Observable result: in **Financial documents**, for the selected book, a finance user sees the
book's provider operations and their state, registers the clearing account of a connection, and
applies an observed operation to a reserved settlement. The amount, currency and date are shown
from the facts and cannot be typed. Refusals, an unknown outcome and a later conflict are shown
plainly; no label says "paid", "verified" or "bank payout".

K4b (later) is the conflict detail and recovery views, redacted metrics and the operational
runbook.

## What exists (inspected)

- API (K3a): `GET /books/{book}/provider-operations` (cursor, states `pending`, `needs_review`,
  `not_final`, `observed`, `applied`, `applied_with_conflict`), `PUT
  /books/{book}/provider-connections/{connection}/clearing-account` (once per connection) and
  `POST {settlement}/provider-confirmations/{payment_id}` (idempotency key; allocations and entry
  date only). There is no read of the book's connections or their clearing account, and no state
  filter on the list.
- Web: `components/financial-workspace.tsx` shows settlements with "Record external payment"
  (`PaymentEditor`) and already labels a `provider_observed` payment. Commands use
  `Idempotency-Key`; an unknown outcome blocks new mutations and keeps the request for a safe
  retry or resolve (existing recovery model). Contracts are strict zod objects
  (`lib/financial-contracts.ts`).
- Browser evidence: `api/tests/integration/test_h4_browser.py` starts the real API and web,
  seeds synthetic data and runs `web/tests/finance.spec.ts` on desktop and mobile with axe.
  Synthetic provider events can be produced locally through the signed K1e ingress and
  `receipt_worker.process_batch` (K2a), as the K3a integration tests do.

## Proposed model

1. **Operations region.** A region "Provider operations" in Financial documents for the selected
   book, visible only with finance rights. Rows: kind (payment or refund), provider ID, observed
   amount and currency, observed date, state in plain words, linked payment when applied. "Load
   more" follows the cursor to the end. A state filter is applied by the server (new optional
   `state` query parameter), so a filtered list is complete across pages.
2. **State wording.** `observed`: "Observed by the provider, not applied yet". `pending`,
   `not_final`, `needs_review`: why it cannot be applied, no action. `applied`: link to the
   payment. `applied_with_conflict`: a visible marker "Later provider data disagrees — manual
   review needed" (Question 3).
3. **Clearing account.** A new read `GET /books/{book}/provider-connections` returns the book's
   connections with their revoked flag and registered clearing account (no secrets, no
   verification keys). If a connection has none, the region says so and, by Question 2, offers a
   one-time registration with an explicit confirmation step. A second registration is refused by
   the API and shown.
4. **Applying.** By Question 1, from a reserved settlement: next to "Record external payment" a
   button "Apply provider operation" opens a form that lists only `observed` operations of the
   fitting kind (payment for a receivable, refund for a payable `credit_refund` settlement) and
   the settlement's currency. The amount is read-only from the facts; the user sets the entry
   date and the allocations; the form checks that allocations add up to the amount before it
   sends (the server stays the authority).
5. **Result and refusals.** Success shows the payment with its existing provider label, the
   operation turns `applied`, the settlement history shows the confirmation. Every K3a error
   code (`PROVIDER_OPERATION_NOT_READY` with its reason, `PROVIDER_OPERATION_APPLIED`,
   `PROVIDER_PAYMENT_MISMATCH` with its reason, `PROVIDER_CLEARING_ACCOUNT_REQUIRED`,
   `PROVIDER_PAYMENT_LINK_REQUIRED`, closed period) gets a plain message; the form keeps its
   input; nothing claims success.
6. **Unknown outcome.** The existing recovery model: a lost response blocks new mutations; retry
   sends the same key and shows the same payment; the database holds one payment.
7. **Contracts.** New strict zod schemas for the operation list and the connection list, and
   contract tests for refused extra fields and inconsistent rows (for example `applied` without a
   payment).

## Acceptance criteria (failing tests first)

| id | Requirement |
|---|---|
| U-01 | A finance user sees every operation of the book through the cursor; the state filter is complete across pages (server-side) |
| U-02 | Labels are truthful: no "paid", "verified" or "payout"; non-applicable states explain why and offer no action |
| U-03 | From a fitting reserved settlement only fitting `observed` operations are offered; the amount is read-only; allocations must add up before sending |
| U-04 | Applying shows the provider payment, the operation as `applied` and the settlement confirmation; one payment in the database |
| U-05 | Each K3a refusal and a closed period are shown plainly, input kept, no false success |
| U-06 | A lost response blocks mutations; retry with the same key returns the same payment; no second payment |
| U-07 | Missing clearing account is shown; registration (if allowed) needs confirmation; a second registration is refused and shown |
| U-08 | `applied_with_conflict` is visible with the manual review instruction; no automatic action |
| U-09 | No region and API refusals for a non-finance user, another branch, a delegate and a foreign company; the connection read shows no secret or key |
| U-10 | Real desktop and mobile browser runs and axe with zero violations on the list, the form, a refusal and the recovery state; synthetic events only, through signed local ingress and the worker |
| U-11 | Existing finance browser test, web contract tests, static checks and the full suite stay green |

## Questions for the owner

1. **Where applying starts.** Default: from the reserved settlement ("Apply provider operation"),
   because allocations live there. Alternative: from the operation row, then choose a settlement.
2. **Clearing account in the screen.** Default: a finance user registers it once per connection
   in the screen, after a confirmation step (it cannot be changed later). Alternative: the screen
   only shows it; registration stays an API action.
3. **Conflict after applying.** Default in K4a: a marker and a manual review instruction; the
   detail of which deliveries disagree and the recovery views come in K4b. Alternative: include
   the detail in K4a (larger slice).

## Out of scope

Conflict detail and recovery views, metrics, runbook (K4b); linking earlier manual payments
(K3b); provider retrieval and admission (K0, K2b); fees, payouts, disputes; worker entry point;
publishing and deployment.
