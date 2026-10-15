# ADR-0027 — Provider events and reconciliation

- Status: **Proposed, 2026-10-15; local design only.**
- Scope: [Package K / FIN-02](../plan/PACKAGE_K_PLAN_2026-10-15.md) in the agreed stage 2.
- Baseline: `df88c20687333668d39fe76a26eabca691e62cb0`; no runtime/schema changes.
- Decision owner: the product owner. This ADR grants no provider or publication permission.

## Context and actual reuse

FIN-02 needs durable event and financial-operation deduplication, safe reordering
and traceable payment/refund effects. G is the accounting authority; H implements
manual external-payment attestations, caps and refund obligations. H4 admission is
owner-supplied metadata with every operational capability false.

Inspection found no Booking provider inbox/outbox, Stripe adapter or event worker.
AI jobs and a future Azure Service Bus topology do not supply that implementation.
The live customer-host resolver is not a provider connection authority. These gaps
must be implemented and tested, not described as existing reuse.

Inspected candidates, exact source references and current official provider evidence:
[ARCHITECTURE_REUSE](../plan/evidence/2026-10-15-package-k-plan/ARCHITECTURE_REUSE.md).

## Proposed decision

Keep K in the existing Python/FastAPI/Pydantic/psycopg/PostgreSQL modular backend.
Use a bounded PostgreSQL inbox and worker first. The financial result and its
operation identity commit in one database transaction. An eventual external wakeup
or notification requires an atomic outbox at its actual caller; do not introduce a
broker, new cloud service or speculative generic event framework in K1.

Keep provider event identity, provider operation identity, internal financial source
and command idempotency as distinct typed concepts. The envelope records its schema
version, verified provider API/format, account, environment, event ID and object ID.
Permanent effect uniqueness is scoped by provider namespace/mode/account and the
canonical operation, independent of ordinary receipt expiry.

Use a verified connection binding to select tenant/book, with minimal routing
metadata and a scoped worker principal. Never give a payment worker an owner or
BYPASSRLS connection, impersonate a finance user, or use event metadata as authority.
Every new role, routing function or grant requires direct-SQL denial evidence.
Admission revocation is rechecked in the same transaction as a new effect.

Verify the bounded raw HTTP body before interpreting business fields. Prefer the
official Stripe Python library, with an exact version/API format selected only
after compatibility, license and fixture checks. No dependency is installed by this
ADR. Snapshot versus thin event handling is resolved and pinned in K1 against the
actual admitted test environment; an unknown version cannot silently share a decoder.

Receipt durability precedes acknowledgement. Worker leases are fenced; crashes
produce a recoverable pending outcome. Fetch remote facts outside financial locks,
then validate the expected internal revision under `gba.lock_ledger(tenant)`.
Out-of-order events use an explicit transition/reconciliation policy; timestamps
are not a financial ordering guarantee. Unsupported events have a visible disposition.

Extend H through a narrow shared posting primitive and provider provenance, preserving
the manual-attestation API. A provider event cannot satisfy a human attestation by
inventing an actor or label. New SQL lineage, cap and source constraints must prevent
orphan/foreign effects under direct SQL. Reuse G balance/date/currency controls,
H reserves/refund obligations, shared audit and transaction-scoped RLS.

Approved merchant/book/currency/object bindings select the intended reserve and
explicit clearing/control accounts. Unbound or conflicting facts are review items.
Successful refunds append distinct effects against their H refund obligations;
they do not roll payment state backwards or manufacture an H attestation correction.
Bank payouts, provider fees and gross collections are not interchangeable balances.
Existing manual facts retain their provenance when later linked to verified evidence.

K observes admitted payment/refund events. Charge/refund initiation, transfers,
payouts, booking checkout, commissions, taxes, FX, dispute accounting and automatic
revenue recognition are outside this proposal. Unsupported real facts remain visible
for reconciliation; they cannot be silently declared applied or ignored as harmless.

## Consequences and acceptance

This introduces a real new trust boundary and durable worker lifecycle. Its small
initial footprint does not remove the need for workload limits, retries, payload
retention, redaction, monitoring, key rotation behavior and least-privilege tests.
No measured throughput, latency, compliance, account eligibility or provider
availability is claimed by this planning record.

K-01–K-14 are **NOT TESTED**. Local fixtures can prove deterministic contract and
transaction behavior, but do not establish actual provider admission. Full FIN-02
acceptance also needs authorized real test-environment evidence, independent review,
the full gates and exact-commit CI. FIN-02/ STOCK-01 readiness is unchanged.

The next available migration at this baseline is 0044. Published migrations 0001–0043
stay immutable. Forward migration and API/client compatibility must advance together.
Before deployment, a reverting code commit can restore the earlier API; any created
financial history must be preserved, with forward corrections rather than destructive
schema rollback. No rollout/rollback action is authorized here.
