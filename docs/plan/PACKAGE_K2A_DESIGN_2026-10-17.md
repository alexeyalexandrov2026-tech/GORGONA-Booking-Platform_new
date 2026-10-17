# Package K2a — receipt decisions without money (design proposal, 2026-10-17)

**Status: Proposed, docs only, not started.** Written by Claude after K1k while the owner was
away (the owner asked to keep working and decide alone). K2 shapes how provider facts will later
drive money, so code waits for the owner's answers to the questions at the end. Base: local
branch `codex/package-k1k-truncate-guard` at `500fa34`; next migration 0050. Nothing here is
implemented, published or deployed.

## Goal

Plan slice K2 is "bounded worker, fencing, operation identity and reconciliation decisions"
([K plan](PACKAGE_K_PLAN_2026-10-15.md), proposed flow items 5–6). K2a is its local part that needs
no provider network call and no money: turn each **attested** receipt into one durable,
repeatable decision and link it to one canonical provider operation. K2b (provider retrieval for
ambiguous facts) needs K0 and stays BLOCKED; K3 (G/H financial effects) comes later.

Observable result: replaying, duplicating or reordering the same events never yields a second
operation or a second decision; two workers can never both commit a decision for one event; a
worker whose lease expired cannot commit; every unresolved case is visible as `needs_review`.

## Proposed model (migration 0050)

1. **Eligible input.** Only inbox events that have an attestation (the writer verified the
   signature, K1c–K1e) are eligible. Runtime-archived events without an attestation (K1b) are
   never claimed and never become a financial input.
2. **Provider operation** `gba.provider_operations`: `(tenant_id, id)`, `connection_id`, `kind`
   (`payment` | `refund`), `provider_object_id`, `currency`, `first_event_id`, `created_at`;
   unique `(tenant_id, connection_id, kind, provider_object_id)`. Identity rules:
   - payment: the PaymentIntent ID (`pi_…`), from a `payment_intent` resource or from a charge's
     `payment_intent_id`; a PaymentIntent and its Charge are one operation;
   - refund: the refund ID (`re_…`), linked to the payment of its `payment_intent_id`;
   - a charge without a PaymentIntent, or `charge.refunded` (no refund ID), is not keyed: the
     decision is `needs_review`.
3. **Leases** `gba.provider_event_leases`: one row per eligible event with `generation`
   (fencing token), `holder` (random token), `expires_at`, `attempts`. A claim is one
   `INSERT … ON CONFLICT … DO UPDATE … WHERE expires_at < now()` that increments `generation`;
   a bounded batch is claimed with `FOR UPDATE SKIP LOCKED` on the lease rows.
4. **Decisions** `gba.provider_event_decisions` (append-only, UPDATE/DELETE/TRUNCATE refused):
   `(tenant_id, event_id)` primary key, `generation`, `outcome` (`observed` | `ignored` |
   `needs_review`), `reason` (closed code list), `operation_id` (null unless `observed`),
   `decided_by` (`session_user`), `decided_at`. A trigger refuses a decision whose lease row is
   not held by the same `holder` and `generation` and unexpired, under `FOR UPDATE` of the lease,
   so an expired or replaced worker cannot commit.
5. **Rules** (pure function over the typed facts, versioned `decision_rules=1`):
   - succeeded payment or refund facts → `observed`, attached to the operation;
   - pending, processing, failed or canceled → `observed` as a non-final state; a later stale
     state never replaces a recorded success (states are a set of observations, not ranked by
     enum or timestamp);
   - same operation with a different currency, or a success amount that differs from an
     earlier success → `needs_review` (`conflicting_facts`);
   - unkeyed facts (item 2) → `needs_review` (`unkeyed_operation`);
   - nothing is `applied`: there is no ledger, settlement or obligation write in K2a.
6. **Process.** `gorgona_booking.providers.receipt_worker.process_batch(pool, *, limit,
   lease_seconds)` and a CLI `gba-receipts work --once`; no daemon, schedule or deployment. No
   provider call happens inside a transaction; decisions are recorded in one transaction each.
7. **Guard and roles.** The receipt schema guard learns the three tables. Privileges follow
   question 1 below. RLS and company scope as for every K table.

## Acceptance criteria (failing tests first, when started)

| id | Requirement |
|---|---|
| W-01 | A PaymentIntent event and its Charge event yield one payment operation; a refund yields its own operation linked to the payment |
| W-02 | Duplicate and reordered deliveries yield the same operation and one decision per event; a stale non-final state never replaces a success |
| W-03 | Conflicting facts and unkeyed facts are `needs_review` with their reason code, never `observed` |
| W-04 | Two concurrent claimers: one wins, the other waits or skips (observed `pg_locks` wait), no double decision |
| W-05 | A worker whose lease expired and was re-claimed cannot commit (fencing refusal); the new holder can |
| W-06 | Unattested archive rows are never claimed; no journal, settlement or obligation row is written by any K2a path |
| W-07 | Decisions and operations are permanent (UPDATE, DELETE, TRUNCATE refused); guard drift refuses processing |
| W-08 | Existing K and full suite stay green |

## Questions for the owner before code

1. **Worker role.** Use the existing `gba_runtime` (simplest; decisions carry no money in K2a)
   or a new NOLOGIN group `gba_receipt_worker` like the K1c writer (stronger separation; bootstrap
   and the Azure job would later need it)? Recommendation: a new group, because K3 will turn
   these decisions into money.
2. **Ambiguity policy** (plan decision 3): confirm that every conflict or unkeyed fact goes to
   human review and nothing is booked automatically.
3. **Scope** (plan decision 1): confirm observation of direct charges and refunds only, no
   initiation, transfers, payouts, disputes or fees in K2.
4. **Unattested archive rows** (K1b runtime path): leave them unprocessed (recommended), or
   also record `ignored` decisions for them?

## Out of scope

Provider retrieval and admission (K0, K2b), financial effects (K3), UI and runbook (K4),
disputes, fees, payouts, retention period, publishing and deployment.
