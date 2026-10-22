# Runbook — provider operations (FIN-02, K4)

For finance users and operators of a company that has a payment provider connection. It
explains what the **Provider operations** tab in **Financial documents** shows and what to do in
each case. Design: [K4a](../plan/PACKAGE_K4A_DESIGN_2026-10-18.md),
[K4b](../plan/PACKAGE_K4B_DESIGN_2026-10-18.md); decisions: [ADR-0027](../adr/0027-provider-events-and-reconciliation.md).

Current limits: test mode only, USD only, one clearing account per connection, synthetic events
in local verification. Provider fees, payouts and bank reconciliation stay manual. A connection
works only after the owner admits it for test access (K0, below); the receipt worker runs as a
local process, so events wait as "not decided yet" while it is stopped.

## Ground rules

- An operation is a provider payment (`pi_…`) or refund (`re_…`). Its amount, currency and date
  always come from the provider's signed events; nobody types them.
- Money moves only when a finance user applies an **observed** operation to a reserved
  settlement. Nothing on this tab is a bank payout.
- Never edit, delete or insert rows in the database to "fix" a case. The database refuses it, and
  the history is the evidence.
- After an unknown outcome ("Resolve the earlier request"), retry the **same** request or resolve
  it. Never start a new request for the same money.

## Operation states

| State | Screen text | What to do |
|---|---|---|
| `observed` | Observed by the provider, not applied yet | Open the reserved settlement it belongs to and use **Apply provider operation**. |
| `pending` | Provider events still being decided | Wait for the receipt worker. Nothing to apply yet. |
| `not_final` | No final provider success yet | Wait. A processing or failed payment moves no money. |
| `needs_review` | Provider events disagree; manual review needed | Open **Details**, read **What disagrees**, compare with the provider's dashboard. A refund that both succeeded and failed (or was canceled), in either order, is here. It cannot be applied; contact the platform owner if the provider confirms a different amount. |
| `needs_link` | Already recorded by hand; link it to the manual payment | A manual payment of the book that is not voided names this provider ID (letter case and invisible characters do not matter), so applying it would count the money twice. Open **Details**, compare the manual payment and **Link** it (no money moves). A voided manual payment no longer blocks it. |
| `revoked` | Connection or verification revoked; cannot move money | The connection was revoked, or a key that attested its events was revoked as compromised. New money is refused; history stays. A key revoked for routine `rotation` or as `retired` blocks nothing it attested before. Ask the platform owner for a new connection. |
| `applied` | Applied to a settlement | Done. The payment shows "Observed provider payment". |
| `linked` | Linked to the manual payment that recorded it | Done; the money is the manual payment's. If that payment is voided or corrected to another amount, the operation returns to `needs_review`; the link stays in the history and the operation is never applied. |
| `applied_with_conflict` | Applied; later provider data disagrees — manual review needed | Money already moved and later data never changes it. Open **Details**, compare with the provider. If the payment is wrong, **Correct** or **Void** it from its settlement. The provider record stays in the history; the operation is never applied again. |

## Refusals

| Code | Meaning | What to do |
|---|---|---|
| `PROVIDER_OPERATION_NOT_READY` | The operation is pending, not final, needs review, has a differing delivery or is revoked (the message names which) | Follow the state's row above. |
| `PROVIDER_OPERATION_APPLIED` | This operation already moved money, or a manual payment's reference names an operation that did | Nothing; it is applied at most once. Find its payment in the operation list. A manual payment for the same money is refused; if the provider payment was wrong, void it first. |
| `PROVIDER_PAYMENT_MISMATCH` | Currency, direction, refund obligation, the refund's original payment, counterparty or the refund cap does not match | Choose the right settlement. A refund applies only to the refund obligation of a credit note, after its original payment was applied. |
| `PROVIDER_CLEARING_ACCOUNT_REQUIRED` | The connection has no clearing account | Register it under **Provider operations → Connections**. |
| `PROVIDER_CLEARING_ACCOUNT_REGISTERED` | The connection already has another clearing account | It cannot be changed. Contact the platform owner if it is wrong. |
| `PROVIDER_PAYMENT_LINK_REQUIRED` | A manual payment in this book already names this provider ID | Nothing was applied. Link the operation to that manual payment instead (state `needs_link`). |
| `PROVIDER_OPERATION_LINKED` | The operation is linked to a manual payment, or a new manual payment names a linked operation | It never moves money itself. A second link, another note or a second manual payment for it is refused; read the existing link. |
| `PROVIDER_LINK_MISMATCH` | The manual payment does not match: amount, currency, direction, a date more than 3 days apart, voided, already linked, not a manual payment, its reference does not name the ID, or the facts changed while linking (`facts`; the message names which) | Choose the manual payment that recorded this provider operation, or correct it first through its settlement. |
| `PROVIDER_ATTENTION_ACKNOWLEDGED` | The item was already acknowledged with another note | Read the existing note; an acknowledgement is permanent. |
| `PROVIDER_ATTENTION_NOT_NEEDED` | The event belongs to an operation or is not decided yet (`facts`: the database decided so while it was being acknowledged); for **Try again**, the event is not stopped after failed attempts (`not_failed`) | Use the operation's state instead; undecided events need no acknowledgement, and only a stopped event takes **Try again**. |
| `PROVIDER_EVENT_RELEASED` | The stopped event was already released with another note (K6a) | Read the existing note; the worker is already trying it again. |

## Linking a manual payment (K3b)

When money from the provider was recorded by hand before (for example from the bank payout), the
operation shows `needs_link`. **Details** lists the manual payments whose reference names the
provider ID, with their amount, date and state. Link one only when the amount, currency and
direction are equal and the dates are at most 3 days apart; write a note of what you compared.
Linking writes no journal and changes no payment. A linked payment can still be voided or
corrected through its settlement; the link stays.

## Clearing account

Each connection needs one open asset account (never a control account) for the provider's gross
amounts. Register it once: choose the account, tick the confirmation and press **Register
clearing account**. It cannot be changed later. Repeating the same account is safe.

## Needs attention

- **Waiting for the receipt worker**: an event is attested but not decided. It is decided
  automatically; there is nothing to do on this screen. If it stays for long, the worker is not
  running — tell the operator. When earlier attempts failed, the item shows how many and the
  error class; the worker tries again after 1, 2, 4 and 8 minutes by itself.
- **Stopped after 5 failed attempts** (K6a): the worker could not decide the event five times in a
  row and stopped trying, so it does not hold up other events. Nothing was decided or booked. Tell
  the operator the error class; once the cause is fixed, press **Try again** with a note of what was
  fixed. The note is permanent; the worker then tries again with the same limits. Repeating the
  same note is safe; another note is refused (`PROVIDER_EVENT_RELEASED`).
- **No payment to attach it to** (`unkeyed_operation`) or **a refund without its payment**
  (`refund_without_payment`): the provider reported something that does not belong to a payment
  this platform can see. Check it in the provider's dashboard by its ID (`ch_…`, `re_…`), then
  **Acknowledge** it with a note of what you checked. The note is permanent and changes no money
  and no decision.

## Details and what disagrees

**Details** on an operation lists every provider event, its decision and every delivery. A later
delivery that differs names each field with both values (for example *Amount received (minor
units) 3100 → 3099*; minor units are cents for USD). An event decided as "its facts disagree"
contradicts earlier events of the same operation. Raw bodies, signatures and keys are never shown.
Each delivery names how it arrived: *signed webhook* or *fetched by reconciliation* (K6b). An
operation that is still waiting or has no final provider event, and whose latest event is more than
24 hours old, shows **No final event for over 24 hours**: check it in the provider's dashboard by its
ID; the reconciler fetches lost events by itself.

## Admission and the receipt processes (K0, owner and operators)

A connection receives events, decides them and moves money only while the owner's latest
admission of it is **test access** (for money: test access for that operation, charge or refund).
Design: [K0a](../plan/PACKAGE_K0A_DESIGN_2026-10-20.md).

- Admit or suspend (owner database login in `GBA_MIGRATION_DATABASE_URL`):
  `gba-db admit-receipt-connection --tenant <company> --connection <connection> --account acct_…
  --state test_access --evidence "<short note>"`; use `--state suspended` to stop a connection and
  `--operations charge` or `refund` to allow one kind only. **A suspension is final** (K5r): the
  connection cannot be admitted again, because deliveries refused while suspended are lost to it;
  provision a new connection to resume. Every revision is kept; a suspension
  waits for work in flight and refuses the next delivery. Applying money for a connection that is
  not admitted answers `PROVIDER_OPERATION_NOT_READY` with reason `not_admitted`.
- Ingress: `python -m gorgona_booking.providers.ingress_main` with
  `GBA_RECEIPT_WRITER_DATABASE_URL` (receipt writer login), `GBA_RECEIPT_SECRET_REFS` (for example
  `env:GBA_STRIPE_TEST_WEBHOOK_SECRET`) and that variable set in the same terminal; it listens on
  127.0.0.1 port `GBA_RECEIPT_PORT` (default 8787) and refuses to start without its key or with a
  wrong login. Never paste a key into a document, chat or command line of another person.
- Worker: `python -m gorgona_booking.providers.worker_main` (every 5 s; `--once` for one batch;
  `--interval 1-300`) with `GBA_RECEIPT_WORKER_DATABASE_URL` (receipt worker login); Ctrl+C stops
  it after the current batch. Events of a suspended or unadmitted connection wait undecided.
  K6a: when deciding one event fails with a database error about that event (a check, data or
  integrity error), the worker records the error class, goes on with the other events and tries
  that one again after 1, 2, 4 and 8 minutes; after 5 failures it stops trying until a finance user
  presses **Try again**. A lost connection, a timeout or damaged privileges stop the whole batch
  without counting, so an outage never stops healthy events; the next batch tries again.
- Reconciler (K6b): `python -m gorgona_booking.providers.reconcile_main` (every 15 minutes over the
  last 3 days; `--once`, `--interval 60-3600`, `--days 1-30`, Stripe keeps events for 30 days) with
  `GBA_RECEIPT_WRITER_DATABASE_URL` (receipt writer login), `GBA_STRIPE_NAMESPACE` (the platform
  namespace of the key) and `GBA_STRIPE_API_KEY_REF` (for example `env:GBA_STRIPE_TEST_API_KEY`, a
  read-only test key set in the same terminal). For each admitted connection of that namespace it
  lists the connected account's events from the Stripe API and records them through the same inbox
  as webhooks: an event that already arrived is a duplicate, a lost one fills the gap, a different
  fact under the same ID is a visible conflict. Retrieved deliveries are attested as
  `stripe_api_v1`, webhooks as `stripe_snapshot_v1`. An event of another API version, account or
  live mode is refused and counted, never recorded. Timeouts, rate limits and server errors are
  retried three times (1, 2, 4 s); then the run fails. Each run is recorded in
  `gba.provider_reconciliation_runs` with its counts and outcome (`failed` names the error class); a
  failed run reports nothing as received that was not. Suspended connections are never asked.
- Logs carry counts and outcomes only: no payload, key, account or ingress ID.
- A `charge.refunded` event has no operation key and always appears under "needs attention"
  (`unkeyed_operation`); the refund itself is decided from its `refund.*` events. Acknowledge it.
  Confirmed on real sandbox events (K0c, 2026-10-20).
- Only the receipt writer (the ingress) records events and deliveries; the application's runtime
  login reads them but cannot insert them (K5b). A Stripe charge counts what was captured: a partial
  capture is that captured amount, not the authorized one.

## Metrics (operators)

With telemetry configured, the API and worker export four counters, each with the company
identifier and no payload values:

- `gorgona.provider_receipt_decisions` — by `outcome` and `reason`;
- `gorgona.provider_applications` — by `result` (`applied` or the refusal code); only requests that passed authorization for a real company are counted;
- `gorgona.provider_receipt_failures` — failed decisions by `error_class` and `parked` (K6a);
- `gorgona.provider_receipt_releases` — **Try again** releases of stopped events (K6a).

Refusals also appear in `gorgona.domain_errors` by code and route. A rising `needs_review` count
or `PROVIDER_OPERATION_NOT_READY` results for one company points to a provider-side difference;
no decisions at all while events arrive points to a stopped worker.
