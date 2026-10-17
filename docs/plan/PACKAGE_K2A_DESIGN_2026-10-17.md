# Package K2a — receipt decisions without money (design, 2026-10-17)

**Status: owner decisions received 2026-10-17; locally implemented in `6e9bbfc`**
([validation](evidence/2026-10-17-k2a-receipt-decisions/VALIDATION.md)). Local branch
`codex/package-k2a-receipt-decisions` from `b6c8040` (the proposal); migration 0050. Nothing here
is published or deployed. Section 7: no CLI was added (no process entry point at all).

## Owner decisions (2026-10-17)

The owner answered the four proposal questions: «отдельная группа gba_receipt_worker, все
конфликты на ручную сверку, только прямые платежи и возвраты, события без аттестации не
обрабатывать».

1. The worker uses a new NOLOGIN group `gba_receipt_worker`, separate from `gba_runtime` and
   `gba_receipt_writer`.
2. Every conflict or ambiguous fact becomes `needs_review`; nothing is booked automatically.
3. Scope: observation of direct payments and refunds only; no initiation, transfers, payouts,
   disputes or fees.
4. Events without an attestation are never processed.

## Goal

Plan slice K2 is "bounded worker, fencing, operation identity and reconciliation decisions"
([K plan](PACKAGE_K_PLAN_2026-10-15.md), proposed flow items 5–6). K2a is its local part with no
provider network call and no money: turn each **attested** receipt into one durable decision and
link it to one canonical provider operation. K2b (provider retrieval for ambiguous facts) needs
K0 and stays BLOCKED; K3 (G/H financial effects) comes later.

Observable result: replaying, duplicating or reordering events never yields a second operation or
a second decision; two workers never both decide one event; a worker whose lease expired cannot
commit; two events of one operation are decided one after the other, so a conflict is always
seen; every unresolved case is visible as `needs_review`.

## Model (migration 0050 and bootstrap)

1. **Worker group.** `gba-db bootstrap` creates NOLOGIN `gba_receipt_worker` like the writer
   group and, from `GBA_RECEIPT_WORKER_ROLE`/`GBA_RECEIPT_WORKER_PASSWORD` (both or neither), an
   optional worker login that belongs to it only. All role names and passwords differ; no role
   belongs to two of the three groups. `gba-db migrate` refuses while the group is missing.
2. **Eligible input.** An inbox event is eligible only when it has an attestation. Discovery runs
   without a company context through select policies for the worker group only on
   `provider_event_attestations` and `provider_event_decisions` (IDs only are used); every read of
   facts and every write happens inside the event's company context.
3. **Provider operation** `gba.provider_operations`: `(tenant_id, id)`, `connection_id`, `kind`
   (`payment` | `refund`), `provider_object_id` (`pi_…` | `re_…`), `parent_object_id` (the
   refund's `pi_…`; null for payments), `currency`, `first_event_id`, `created_by`
   (`session_user`), `created_at`; unique `(tenant_id, connection_id, kind, provider_object_id)`.
   - payment: the PaymentIntent ID, from a `payment_intent` resource or a charge's
     `payment_intent_id`; a PaymentIntent and its Charge are one operation;
   - refund: the refund ID, with the PaymentIntent it refunds as parent (stored as an ID, so the
     order of arrival does not matter);
   - not keyed, so `needs_review`: a charge without a PaymentIntent (`unkeyed_operation`), a
     `charge.refunded` event (`unkeyed_operation`: no refund ID), a refund without a
     PaymentIntent (`refund_without_payment`).
4. **Leases** `gba.provider_event_leases`: `(tenant_id, event_id)` with `generation` (fencing
   token), `holder` (random UUID per worker run), `expires_at`, `claimed_at`. A claim is one
   `INSERT … ON CONFLICT … DO UPDATE … WHERE expires_at < now()`: a held lease makes a second
   claimer wait for the holder's transaction and then skip. A trigger allows only a first claim
   (`generation` 1) or a re-claim of an expired lease (`generation`+1), only for an attested,
   undecided event, with a lease of at most ten minutes; leases are never deleted.
5. **Decisions** `gba.provider_event_decisions`, append-only: `(tenant_id, event_id)` primary
   key, `generation`, `holder`, `rules_version` (1), `outcome` (`observed` | `needs_review`),
   `reason` (`success`, `not_final`, `conflicting_facts`, `unkeyed_operation`,
   `refund_without_payment`), `operation_id`, `decided_by` (`session_user`), `decided_at`.
   `observed` exactly for `success`/`not_final`; an operation exactly when the event is keyed.
   A trigger locks the lease row and refuses the decision unless it holds the same `holder` and
   `generation` and has not expired (fencing); it also refuses an unattested event, a foreign
   company, and an operation whose kind, key or connection does not match the event's facts.
6. **Rules** (pure Python over the typed facts, `rules_version=1`):
   - succeeded PaymentIntent, succeeded paid and captured Charge, succeeded refund → `success`;
   - any other state → `not_final` (states are a set of observations: nothing is replaced, so a
     stale state never hides a success);
   - a currency different from the operation's, or a success amount (PaymentIntent
     `amount_received_minor`, Charge or refund `amount_minor`) different from an earlier success
     of the same operation → `conflicting_facts`;
   - nothing is applied: no ledger, settlement or obligation row is read or written.
   The worker takes the operation row `FOR UPDATE` before reading earlier decisions, so two
   events of one operation are decided in turn and a conflict cannot be missed.
7. **Process.** `gorgona_booking.providers.receipt_worker.process_batch(pool, *, limit,
   lease_seconds)`: worker role and schema checks first, then discovery, then one claim and one
   decision transaction per event. No provider call, CLI, daemon, schedule or deployment.
8. **Permissions.** The worker group: usage on `gba`, the context functions, select on the inbox
   and attestations, select and column inserts on operations and decisions, select, column
   inserts and updates (`generation`, `holder`, `expires_at`) on leases. No access for the runtime
   or the writer to the new tables; the worker gets nothing else. Operations and decisions refuse
   UPDATE, DELETE and TRUNCATE; leases refuse DELETE and TRUNCATE.
9. **Guard.** The receipt schema guard covers the three groups and the three new tables; the
   worker runs it with its own role check before each batch.

## Acceptance criteria (failing tests first)

| id | Requirement |
|---|---|
| W-01 | A PaymentIntent event and its Charge event yield one payment operation; a refund yields its own operation with the PaymentIntent as parent, also when it arrives first |
| W-02 | Duplicate deliveries and repeated runs yield one decision per event; a stale non-final state after a success is `not_final` and the success stays |
| W-03 | Conflicting currency or success amount, unkeyed charges, `charge.refunded` and refunds without a PaymentIntent are `needs_review` with their reason, never `observed` |
| W-04 | Two concurrent claimers of one event: the second waits for the first (observed `pg_locks` wait) and skips; one decision |
| W-05 | Two events of one operation decided concurrently: the second waits on the operation row (observed `pg_locks` wait) and sees the first, so a conflicting amount is `needs_review` |
| W-06 | A worker whose lease expired and was re-claimed cannot commit (fencing refusal); the new holder can; a forged holder or generation is refused |
| W-07 | Unattested archive rows are never claimed or decided; no journal, settlement or obligation row changes |
| W-08 | Operations and decisions are permanent (UPDATE, DELETE, TRUNCATE refused, also for the owner); runtime and writer cannot read or write the new tables; the worker cannot write receipts or business tables |
| W-09 | Bootstrap: worker group always, worker login only with both variables, all passwords differ; migrate refuses without the worker group; role topology guard refuses a login in two groups |
| W-10 | Guard drift in a new table refuses the worker, the writer and the runtime archive; repaired schema passes |
| W-11 | Existing K and full suite stay green |

## Out of scope

Provider retrieval and admission (K0, K2b), financial effects (K3), UI, runtime read access and
runbook (K4), a process entry point or schedule, disputes, fees, payouts, retention period,
publishing and deployment.
