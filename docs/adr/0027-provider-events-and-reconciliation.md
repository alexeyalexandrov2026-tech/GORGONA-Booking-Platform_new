# ADR-0027 — Provider events and reconciliation

Local K1c source `0c72a719cb9743a1f3cd7d60ea26bc46e9e2638c` implements the proposed isolated verifier foundation;
[validation](../plan/evidence/2026-10-16-k1c-receipt-attestations/VALIDATION.md).
Status remains Proposed. Operational admission/payment authority and readiness unchanged.

## K1c local implementation decision — 2026-10-16, Proposed

Use a separate NOLOGIN `gba_receipt_writer` group and an explicitly configured,
non-owner writer login. Reuse K1a raw signature verification and K1b archive writes.
Add migration0045 with an immutable, company-scoped attestation per archived delivery,
an opaque verification configuration ID, decoder version and database writer attribution.
The ordinary runtime can read attestations but cannot insert, mutate or assume the writer
role. The writer must have no unrelated business/financial table privileges. Refuse mixed
roles, including an unsafe session login hidden by SET ROLE. Owner bootstrap may create
an optional writer login; current ordinary bootstrap callers keep their existing behavior.

Only an internal raw-body entry point may attest after verification against trusted
server-supplied tenant/connection/book/account policy. Commit archive and attestation
together before returning. Test refusals, rollback/commit, duplicates/conflicts, RLS,
revocation, role/schema drift and nonempty0044 upgrade on disposable PostgreSQL; races
require observed pg_locks waits. Preserve0001–0044. No new dependency or security-definer.

The trusted writer can assert a false receipt if its own credential/code is compromised;
PostgreSQL does not independently verify a Stripe MAC. This is a protected verifier
attestation, not operational admission or payment authority. Production process/credential
separation and independent review remain gates before exposure. No public HTTP, global
routing, actual provider account/key/action, worker, financial effect or readiness change
is authorized by this local slice. H4 declarations and manual attestation stay unchanged.

Local K1b guard review source `db96f005442201428700995c09f028e1b6da08c0` adds schema conformance checks and six
regressions; [validation](../plan/evidence/2026-10-15-k1b-guard-review/VALIDATION.md).
Receipt archive remains unauthenticated for financial authority. No status/readiness,
operational admission, HTTP, worker or financial effects are added by this slice.

- Status: **Proposed, 2026-10-15; integration not accepted. K1a verification, K1b storage and K1c isolated writer attestations are locally implemented.**
- Scope: [Package K / FIN-02](../plan/PACKAGE_K_PLAN_2026-10-15.md) in the agreed stage 2.
- Planning baseline: `df88c20687333668d39fe76a26eabca691e62cb0`; K1a source `7d25aa2d72874271a62e363817e0624fb502497c`, no schema/route changes.
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

## K1a execution note — 2026-10-15

The later local continuation implements only the signature/decoder boundary and pins
stripe16.0.0 after MIT/source/Python3.14 checks. [Evidence](../plan/evidence/2026-10-15-k1a-event-boundary/VALIDATION.md).
Original no-adapter/no-installed-SDK statements above describe the proposal baseline.
No admitted connection, HTTP receipt, inbox, worker or financial effect exists.
All complete K acceptance rows remain NOT TESTED; readiness stays planned and
real provider execution remains separately gated. This is not acceptance of the overall ADR.

## K1b execution note — 2026-10-15

Local source `543b73221ac1dd0aa738bd8cf33dd468366ef27a` adds migration0044 and internal receipt storage only.
Connections are immutable, owner-provisioned, always `not_admitted`, with no stored
secret/configuration reference. Runtime may revoke permanently, but cannot provision
or reactivate. No global routing grant, new role or security-definer function is added.
Future verified operational admission remains a separate authority; neither H4 nor
archived signed facts grants it. The only supplied provisioning is a synthetic test fixture.

The caller supplies a company-scoped READ COMMITTED transaction and signature-checked
K1a model. PostgreSQL verifies shape/scope/integrity, not the MAC. No public caller is
wired. Equal facts keep one event; distinct digest variants persist conflicts without
overwriting. Exact retries add no rows. The result is provisional until commit, not an
HTTP acknowledgement. Connection-row SHARE locks serialize revocation. Retention,
global routing, worker/fencing/operation identity and financial provenance remain ahead.

[Evidence](../plan/evidence/2026-10-15-k1b-receipt-inbox/VALIDATION.md):40 new tests,
1884 passed, 4 skipped in 1502.59s (0:25:02). All complete K acceptance rows and readiness unchanged. Next0045.
Independent review and actual admitted provider execution remain ahead.
