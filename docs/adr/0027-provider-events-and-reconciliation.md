# ADR-0027 — Provider events and reconciliation

Local K1k source `a5f21e41f550d5d07e428c644e9f718082b3f619` implements the K1k decision below;
[validation](../plan/evidence/2026-10-17-k1k-truncate-guard/VALIDATION.md).
Local K1j source `201847856aa768bbeb25751d5b219e154383c293` implements the K1j decision below;
[validation](../plan/evidence/2026-10-17-k1j-revocation-record/VALIDATION.md).
Local K1g source `4401a2e7bcdc716eaa5664285c0ca383ddf77163` implements the K1g decision below;
[validation](../plan/evidence/2026-10-17-k1g-guard-additions/VALIDATION.md).
Local K1f source `3e18c938a505bbb4583778cdf40df0e7bed2aceb` implements the K1f decision below;
[validation](../plan/evidence/2026-10-17-k1f-bootstrap-hardening/VALIDATION.md).
Local K1e source `eb46748fa7446754e96e9290ce5261607ae45ce0` implements the K1e decision below;
[validation](../plan/evidence/2026-10-16-k1e-http-ingress/VALIDATION.md).
Local K1d source `e9c86bfbd1d22e00ea66a96637cd98e9a58f27b4` implements the K1d decision below;
[validation](../plan/evidence/2026-10-16-k1d-receipt-routing/VALIDATION.md).
Local K1c source `0c72a719cb9743a1f3cd7d60ea26bc46e9e2638c` implements the proposed isolated verifier foundation;
[validation](../plan/evidence/2026-10-16-k1c-receipt-attestations/VALIDATION.md).
Status remains Proposed. Operational admission/payment authority and readiness unchanged.

## K2a proposal — 2026-10-17, not started

Receipt decisions without money (operation identity, leased claims with fencing, append-only
decisions) are proposed in [the K2a design](../plan/PACKAGE_K2A_DESIGN_2026-10-17.md). It awaits
the owner's answers on the worker role, ambiguity policy, scope and unattested rows.

## K1k local design decision — 2026-10-17, Proposed; locally implemented in `a5f21e4`

Close review findings IR-09 and IR-08 with migration 0049: a statement-level `BEFORE TRUNCATE`
trigger refuses TRUNCATE (including cascades) on all six K tables for the owner and superusers,
and `provider_receipt_routes.ingress_id` defaults to `gen_random_uuid()`. The receipt schema guard
checks both. A superuser can still switch off triggers; other tables are unchanged. Criteria
T-01–T-04 are in the [K plan](../plan/PACKAGE_K_PLAN_2026-10-15.md).

## K1j local design decision — 2026-10-17, Proposed; locally implemented in `2018478`

Close review finding IR-07 with migration 0048: a revocation of a receipt connection or a
verification config must name its reason (configs `rotation`/`compromise`/`retired`, connections
`compromise`/`retired`); the trigger records when and by which login (`session_user`). The three
fields are permanent and all-or-nothing; rows revoked before 0048 keep them empty (record unknown)
rather than receive invented values. Attestations and configs record the session login.
The receipt schema guard checks the new columns, grants and bodies. No effect of `compromise` on
earlier attestations yet (K2), no API, no re-provisioning. Criteria J-01–J-07 are in the
[K plan](../plan/PACKAGE_K_PLAN_2026-10-15.md).

## K1g local design decision — 2026-10-17, Proposed; locally implemented in `4401a2e`

Close review finding IR-05 inside the existing receipt schema guard: role topology of the two
groups (no mixed or privileged members, no parent roles), K tables ordinary, logged and without
rewrite rules, table/column/function ACLs limited to the owner and the two groups with grant
options only for the owner, and exact source and shape of `current_tenant_id()` and
`current_location_id()`. Drift refuses writer receipts and runtime archives alike. No migration.
Criteria G-01–G-05 are in the [K plan](../plan/PACKAGE_K_PLAN_2026-10-15.md).

## K1f local design decision — 2026-10-17, Proposed; locally implemented in `3e18c93`

Close review finding IR-06 around the K1c writer login without changing receipt code or schema.
Bootstrap refuses equal owner, runtime and writer passwords. `gba-db bootstrap` may create the
writer login from `GBA_RECEIPT_WRITER_ROLE`/`GBA_RECEIPT_WRITER_PASSWORD` (both or neither).
Migrations refuse to start, applying nothing, until bootstrap has created `gba_runtime` and
`gba_receipt_writer`. The Azure bootstrap job is unchanged (owner decision). Criteria F-01–F-04
are in the [K plan](../plan/PACKAGE_K_PLAN_2026-10-15.md).

## K1e local design decision — 2026-10-16, Proposed; locally implemented in `eb46748`

Attach the K1d entry point to raw HTTP without moving trust into the ordinary application.
A separate ASGI application, run by the receipt writer process with the writer pool and the
server-held key store, serves only `POST /v1/provider-events/stripe/{ingress_id}`. The ordinary
application gets no receipt route and never holds the writer credential or keys.

The handler reads the raw body as bytes under a byte cap (K1a's 256 KiB, checked by
`Content-Length` and while streaming) and a read-time budget, takes exactly one
`Stripe-Signature` header and passes both unchanged to `receive_routed_receipt`. A bounded
number of receipts run at once; a full quota answers 503 before the body is read. The receipt
transaction sets local lock and statement timeouts before its first query.

After the [independent review](../plan/evidence/2026-10-16-k1e-http-ingress/INDEPENDENT_REVIEW_K1A_K1D.md)
(IR-01) the unauthenticated path is made cheap: before the signature check only unlocked reads
of the route, the active config and the binding run. The writer-role and schema guards, and a
FOR SHARE re-read that must return the same active config and binding, follow a valid signature
and precede every write. Revocation still serializes with in-flight receipts.

It answers 200 with one fixed body only after the commit (recorded, known duplicate or retained
conflicting variant), so a lost acknowledgement is replayed safely as a duplicate. Every
authentication, routing and decoding refusal is one 400 with a byte-identical body: no K1a
reason, IDs or references. Unavailable storage, timeouts and guard refusals are 503 with
`Retry-After`; anything else, including a failed commit, is 500. Never 2xx before the commit.

Stored rows keep only the existing minimal typed facts; raw bodies, signature headers, keys,
client addresses and ingress IDs are neither stored nor logged. Event identities, deliveries and
attestations are kept permanently as duplicate identity and audit trail; a legal retention
period is an owner decision before production. No migration, process entry point, deployment,
provider account or key, worker, financial effect or readiness change. Edge rate limits, durable
volume quotas and a production key store remain open. Criteria E-01–E-13 are in the
[K plan](../plan/PACKAGE_K_PLAN_2026-10-15.md).

## K1d local design decision — 2026-10-16, Proposed; locally implemented in `e9c86bf`

Close the two K1c gaps found by the K1d executor's
[non-independent review](../plan/evidence/2026-10-16-k1d-receipt-routing/K1C_AUTHOR_REVIEW.md):
an unanchored verification-config ID and caller-supplied scope.

Add migration 0046 with a versioned, company-scoped verification-config authority per
connection: one active version, an opaque `store:name` secret reference (never a key;
secret-like values refused), immutable except one-way revocation. Add a writer-only
routing record from a server-generated ingress ID to company and connection IDs.
Only the database owner provisions both, inside an explicit company context. The runtime
and the writer may only revoke. No new role, security-definer function or runtime
routing grant. Every new grant, policy and trigger gets direct-SQL denial tests.

Replace the caller-supplied `ReceiptVerifierBinding` with one internal entry point keyed by
the ingress ID. The server-held key store resolves the reference; the database never holds
key material. Before the K1a signature check only authority rows are read (route, active
config, connection binding); no inbox, ledger or business rows. Attestations reference the
exact config (composite key, same connection) under FOR SHARE, so revocation serializes with
in-flight receipts and applies from the next transaction. 0046 refuses to upgrade a database
that already holds K1c attestations rather than invent authority for them; the refusal is an
explicit check under a temporary owner policy, because key validation by the owner does not
see rows hidden by forced row security.

A config is verification authority, not operational admission: connections stay
`not_admitted` and test-mode only, H4 stays a declaration, and no HTTP route, provider
account/key, worker, financial effect or readiness change is added. Criteria D-01–D-09 are in
the [K plan](../plan/PACKAGE_K_PLAN_2026-10-15.md).

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

- Status: **Proposed, 2026-10-15; integration not accepted. K1a verification, K1b storage, K1c isolated writer attestations, K1d verification authority and routing and K1e raw HTTP ingress for the writer process are locally implemented.**
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
