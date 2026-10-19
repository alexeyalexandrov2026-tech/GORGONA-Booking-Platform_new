# Package K4b — provider conflict detail, recovery views, metrics and runbook (design, 2026-10-18)

**Status: owner decisions received 2026-10-18; locally implemented in `60a12e1`**
([validation](evidence/2026-10-18-k4b-provider-review/VALIDATION.md)). Local branch
`codex/package-k4b-provider-review` from `45f15df` (the decisions). Migration **0053** (acknowledgements,
decision 2). Nothing here is deployed;
no provider call, account, credential or real money.

## Owner decisions (2026-10-18)

1. Conflict detail names the differing fields **and shows both values**.
2. The "Needs attention" view gets an **acknowledgement with a required note** (the owner answered
   "make sure is done"; recorded as: an item can be marked as handled, with a note, in an
   append-only record; migration 0053). An acknowledgement never changes money or a decision.
3. Counters carry the **company identifier** as well as outcome, reason and code (no other
   company data, no payload values).
4. The runbook is in **English**.

## Refinements found during implementation

- Only a decision **without** an operation is acknowledged; an undecided event waits for its
  decision (the worker decides it), and the database refuses an acknowledgement of an event of an
  operation.
- Attention items carry the provider's object ID (`pi_`, `ch_`, `re_`) so two items of the same
  type can be told apart and found at the provider.
- The "oldest undecided age" gauge was dropped: undecided events and their dates are listed in the
  attention view; the two counters cover decisions and applications.

## Goal

K4 is "finance review UI and recovery, redacted metrics and operational runbook"
([K plan](PACKAGE_K_PLAN_2026-10-15.md), K-12, K-13). K4a gave the screen to apply observed
operations ([K4a design](PACKAGE_K4A_DESIGN_2026-10-18.md)). K4b completes K4: a finance user can
see **why** an operation needs review, finds every event that is stuck or has no operation, and an
operator has redacted metrics and a written procedure.

Observable result: from an operation row the user opens its detail and sees each provider event,
its decision and every delivery, with the facts that disagree named; a "Needs attention" view lists
events still waiting for a decision and decisions without an operation; counters show decisions
and applications without company data or payloads; a runbook says what each state means and what
to do.

## What exists (inspected)

- `provider_event_deliveries`: every delivery of an event, its `facts`, `matches_original` and
  `received_at`. `provider_event_decisions`: outcome `observed`/`needs_review`, reason `success`,
  `not_final`, `conflicting_facts`, `unkeyed_operation`, `refund_without_payment`; decisions of the
  last two reasons have **no operation**, so the K4a list never shows them.
- An attested event with no decision is "pending" for its operation; with no operation it is not
  visible at all. The worker has no entry point yet, so in practice pending events wait.
- `observability.py`: structured logs, OpenTelemetry meter `gorgona_booking`, a domain error
  counter, span attribute sanitising, Azure Monitor export only when configured.
- The receipt worker (`providers/receipt_worker.py`) has no counters.

## Proposed model

1. **Operation detail read** `GET …/provider-operations/{operation}`: the operation, its applied
   payment if any, and per event: provider event type, `created`, decision (outcome, reason,
   decided at) and deliveries (received at, matches original, the first 12 hex digits of the
   delivery digest). For a delivery that differs: the names of the fact fields that differ and,
   by Question 1, their two values. Only fields of the allowlisted fact schema; never the raw
   body, signature, secret reference, verification config or customer data.
2. **Screen.** "Details" on each operation row opens the detail: a timeline and, for
   `needs_review` and `applied_with_conflict`, a panel "What disagrees" in plain words.
3. **Needs attention view.** A read `GET …/provider-attention` (cursor) and a screen section:
   attested events of the book without a decision, with their age; decisions without an
   operation (`unkeyed_operation`, `refund_without_payment`) with their event type and date. By
   Question 2, read-only, or with an "Acknowledge with a note" action.
4. **Metrics.** Counters in the existing meter: receipt decisions by outcome and reason (worker),
   provider applications by result code (API), and a gauge of the oldest undecided event's age
   per run. By Question 3, attributes have no company identifier. Exported only where telemetry
   is already configured; tests read them with an in-memory reader.
5. **Runbook** `docs/runbooks/PROVIDER_OPERATIONS.md` (language by Question 4): each state and
   what to do; conflict after applying (compare, then correct or void in H); revoked connection;
   stuck pending events (worker not running); events without an operation; what never to do
   (edit rows in the database, apply a typed amount, retry with a new key after an unknown
   outcome).

## Acceptance criteria (failing tests first)

| id | Requirement |
|---|---|
| R-01 | The detail lists every event, decision and delivery of the operation in order; another company's or book's operation is not found |
| R-02 | A differing delivery names exactly the differing fact fields (and values if chosen); identical deliveries name none |
| R-03 | No raw body, signature, secret reference, verification config, customer data or key appears in any new response or log |
| R-04 | The attention view lists undecided events and decisions without an operation, complete across pages, and nothing else |
| R-05 | If acknowledgements are chosen: finance rights only, note required, append-only, company scoped, guarded; nothing about money changes |
| R-06 | Counters record decisions by outcome and reason and applications by code, without company identifiers or payload values |
| R-07 | Finance rights for the new reads; branch, delegate, support and foreign company refused |
| R-08 | Real desktop and mobile browser with axe: detail, conflict panel, attention view; no side scroll |
| R-09 | The runbook covers every state and refusal code shown by the screen; links resolve |
| R-10 | Existing K4a/K3a/H browser and API tests and the full suite stay green |

## Questions for the owner

1. **How much conflict detail.** Default: name the differing fields and show both values (for
   example amount 10.00 vs 9.00); these are provider facts already stored, not customer data.
   Alternative: only name the fields.
2. **Needs attention.** Default: read-only in K4b (no migration); acknowledging an event comes
   later. Alternative: an "Acknowledge with a note" action now (migration 0053, append-only record).
3. **Metrics.** Default: counters without any company identifier (outcome, reason, code only).
   Alternative: also per company (more useful per customer, more data in telemetry).
4. **Runbook language.** Default: English, as the repository documents. Alternative: Russian.

## Out of scope

Provider retrieval (K2b, needs K0), linking earlier manual payments (K3b), automatic resolution,
alerts and dashboards in Azure, a worker entry point and schedule, publishing beyond CI and
deployment.
