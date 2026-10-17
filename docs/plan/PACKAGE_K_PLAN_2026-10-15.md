# Package K — provider events and reconciliation (FIN-02)

## Current checkpoint — 2026-10-17: K1f bootstrap hardening locally verified

Source `3e18c938a505bbb4583778cdf40df0e7bed2aceb` on local branch `codex/package-k1f-bootstrap-hardening`, parent `be97fbd`. Criteria
F-01–F-04 PASS; 8 new cases; no migration. Focused **458 passed in 408.78s (0:06:48)**; full
**2042 passed, 4 skipped in 3100.84s (0:51:40)**; static, mypy (315 files), web and build PASS;
runtime audit 0; existing development audit 5 high FAIL. Kept failure: product RED (7 failed).
Not published. K1e branch CI: run 38991120703 FAILED at the production image build after 17 s (log needs a GitHub sign-in; pinned base images were pullable afterwards); an empty re-run commit `e5279cb` (same tree as `be97fbd`) passed: [CI run 38996263458](https://github.com/alexeyalexandrov2026-tech/GORGONA-Booking-Platform_new/actions/runs/38996263458) SUCCESS. The first failure is treated as transient; its cause is not established.
[Validation](evidence/2026-10-17-k1f-bootstrap-hardening/VALIDATION.md),
[CHECKS.json](evidence/2026-10-17-k1f-bootstrap-hardening/CHECKS.json),
[handoff](NEXT_AGENT_PACKAGE_K1F_2026-10-17.md), [prompt](NEXT_AGENT_PACKAGE_K1F_PROMPT_2026-10-17.md).

### K1f design, recorded before code

Local branch `codex/package-k1f-bootstrap-hardening` from `be97fbd` (K1e plus the disk-cleanup
note). After the K1e handoff asked which follow-up to take, the owner answered «continue»; the
recommended first follow-up was review finding IR-06. Not published (the push authorization
covered the K1e branch only).

**K1f: writer bootstrap and migration order — local only.** IR-06: `BootstrapSpec.validate()`
accepts equal owner, runtime and writer passwords, so a runtime credential holder could log in as
the writer; `gba-db bootstrap` cannot create the writer login; a database bootstrapped before
K1c lacks `gba_receipt_writer`, and `migrate` then fails inside 0045 after 0044 was applied.

Decisions:

1. **Distinct passwords.** `validate()` refuses any two equal passwords among owner, runtime and
   writer, before any connection; the message names no value.
2. **Writer login from the CLI.** `gba-db bootstrap` reads optional `GBA_RECEIPT_WRITER_ROLE` and
   `GBA_RECEIPT_WRITER_PASSWORD` from the environment, both or neither; neither keeps today's
   behavior. The existing `bootstrap()` creates the login and its group membership. Output names
   roles only.
3. **Bootstrap before migrate.** `apply_migrations` checks, before taking the migration lock or
   creating anything, that the groups `gba_runtime` and `gba_receipt_writer` exist; otherwise it
   refuses with "run gba-db bootstrap before migrate" and applies nothing. `gba-db migrate`
   prints `MigrationError` as an operator message instead of a traceback.
4. **Docs.** `docs/DEVELOPMENT.md` documents the order, the writer variables and a credentials row
   for the writer login. The Azure bootstrap job (`infra/azure/modules/containerapps.bicep`) is
   not changed: infrastructure and secrets need the owner's separate word; recorded as a limit.
5. No migration (0047 stays free), no dependency, no change to receipt code or schema.

Acceptance criteria (failing tests first):

| id | Requirement |
|---|---|
| F-01 | Equal owner/runtime, owner/writer or runtime/writer passwords are refused by `validate()` and by `bootstrap()` before any connection; no password appears in the message |
| F-02 | `gba-db bootstrap` with both writer variables creates a login that is a member of `gba_receipt_writer` and passes the K1c writer-role check shape (not a runtime member, not the owner); with one variable it refuses; with none no writer login is created |
| F-03 | `migrate` on a cluster where `gba_receipt_writer` is missing refuses before applying anything (no `gba_schema_migrations` table, no `gba` schema) and names the bootstrap step; after the group is back the same database migrates fully |
| F-04 | Existing bootstrap and migration tests and the full suite stay green |

## Previous checkpoint — 2026-10-16: K1e raw HTTP ingress locally verified

Source `eb46748fa7446754e96e9290ce5261607ae45ce0` on local branch `codex/package-k1e-http-ingress`,
parent `2d434bf`. A separate writer-process ASGI application and the reordered
`receive_routed_receipt` implement decisions 1–9 below; criteria E-01–E-13 PASS on synthetic
data. 46 new cases; no migration. Final focused **450 passed in 273.91s (0:04:33)**; full
**2034 passed, 4 skipped in 1700.22s (0:28:20)**; static, mypy (314 files), web 114 and build
PASS; runtime audit 0; existing development audit 5 high FAIL; 3 container and 1 tenant-site
skips NOT TESTED. Kept failures: a product RED on the K1d code (unbounded lock wait, share locks
before the signature) and a design gap found in dev-1 (the ordinary runtime lost the K1c
writer-role refusal; fixed with a cheap membership check). The owner-approved independent
read-only review of K1a–K1d found no High, two Medium (both addressed here) and nine Low/Note
findings. Human review, K CI, process entry point and the real provider are NOT TESTED or
BLOCKED. FIN-02/STOCK-01 planned; ADR-0026/0027 Proposed; K not published; next migration 0047.
[Validation](evidence/2026-10-16-k1e-http-ingress/VALIDATION.md),
[CHECKS.json](evidence/2026-10-16-k1e-http-ingress/CHECKS.json),
[review](evidence/2026-10-16-k1e-http-ingress/INDEPENDENT_REVIEW_K1A_K1D.md),
[handoff](NEXT_AGENT_PACKAGE_K1E_2026-10-16.md), [prompt](NEXT_AGENT_PACKAGE_K1E_PROMPT_2026-10-16.md).

### K1e design, recorded before code

Local branch `codex/package-k1e-http-ingress` from `2d434bff8081e03d38765caa0b61f5df006dde27` (K1d docs).
The owner answered with the handoff prompt for K1e and chose an independent read-only review of
K1a–K1d by a separate agent, run in parallel with K1e. The review found no High issue, two
Medium (IR-01, IR-02) and nine Low/Note findings; dispositions are in decision 9 and the
[review record](evidence/2026-10-16-k1e-http-ingress/INDEPENDENT_REVIEW_K1A_K1D.md).
Decision 9 and criteria E-12/E-13 were added after the review, still before code.

**K1e: raw HTTP receipt ingress — local, synthetic only.**

Decisions:

1. **Separate writer process.** A new ASGI application, built by
   `create_receipt_ingress_app(pool, key_store, limits=…)`, serves exactly one route:
   `POST /v1/provider-events/stripe/{ingress_id}`. It runs with the receipt writer pool and the
   server-held key store. The ordinary application (`create_app`) gets no receipt route and never
   holds the writer credential or keys; its runtime role guard already refuses writer membership.
   No settings, process entry point, container or deployment is added: pool and key store are
   injected. No OpenAPI or other routes in the ingress application.
2. **Bounded raw body.** Order: route and method → ingress ID syntax → a free concurrency slot →
   `Content-Length` check → streamed read with a running cap → `receive_routed_receipt`. The body
   cap is K1a's 256 KiB; over it → 413 (before reading by `Content-Length`, otherwise as soon as
   the cap is passed, also when chunked). Reading the body has a time budget; over it → 408.
   Exactly one `Stripe-Signature` header; none or several is a refusal. No framework JSON
   parsing: the exact bytes reach the K1a check.
3. **Acknowledgement.** 200 with one fixed body, only after `receive_routed_receipt` returned,
   that is after the commit: for a recorded event, a known duplicate and a verified conflicting
   variant (it is durably retained for review). No IDs, disposition or digest in the response.
   A lost acknowledgement is safe: the retry finds a duplicate, adds no rows and gets 200.
4. **One refusal.** Unknown or malformed ingress, missing, repeated, bad or stale signature, wrong
   or unusable key, revoked config or connection, wrong account, version, type or shape, an empty
   body and a foreign company's event: 400 with one byte-identical body, without a reason, IDs or
   references. The request ID is only in `X-Request-ID`. The K1a refusal reason is never sent.
5. **Retryable failure.** Storage unavailable — pool timeout, lost connection, lock or statement
   timeout, serialization failure, deadlock, schema or writer-role guard refusal — and a full
   concurrency quota: 503 with `Retry-After` and one fixed body. Any other failure, including a
   failed commit: 500 with one fixed body. Never 2xx before the commit.
6. **Quotas, per process.** Body 256 KiB and signature header 4096 bytes (K1a constants), a body
   read budget, a bounded number of concurrent receipts (a full quota answers 503 without reading
   the body), and transaction-local `lock_timeout` and `statement_timeout` set by
   `receive_routed_receipt` before its first query. Per-source rate limits at the edge and durable
   per-connection volume quotas are recorded limits; they need real traffic data (K0).
7. **Retention.** Stored rows keep only typed minimal facts, the delivery digest, the config ID
   and the writer attribution: no raw body, signature header, key, client address or ingress ID.
   Event identities, deliveries and attestations are kept permanently: they are the duplicate
   identity that must outlive receipts (K-04) and the audit trail; immutability triggers forbid
   deletion. No automatic deletion in K1e; a legal retention period is an owner decision before
   production. Logs keep the existing policy: route template, status, duration, request ID; never
   the body, headers or the ingress ID from the path.
8. **No schema change.** K1e needs no migration; 0047 stays free.
9. **Cheap unauthenticated path** (added after the
   [independent review](evidence/2026-10-16-k1e-http-ingress/INDEPENDENT_REVIEW_K1A_K1D.md), IR-01).
   Before the signature check `receive_routed_receipt` only sets its timeouts, checks cheaply that
   the session belongs to the writer group and not to the runtime (`pg_has_role`; the ordinary
   runtime still gets the K1c writer-role refusal), and reads the route, then the active config
   and binding, without row locks and without the catalog guards. After a
   valid signature it runs the writer-role and schema guards, re-reads the config and binding
   under FOR SHARE and refuses unless they are the same active config and binding; only then it
   archives and attests. An unknown ingress costs one indexed read; a bad signature takes no row
   lock and no catalog scan. This corrects the K1d claim: there, an unknown ingress also paid for
   two catalog queries, and a bad signature took share locks. The review's other findings
   (IR-03–IR-11) are recorded limits; IR-02 is decision 4; for IR-04 a K0 prerequisite is that
   the endpoint subscribes only to the 11 supported event types.

Acceptance criteria (failing tests first):

| id | Requirement |
|---|---|
| E-01 | A signed delivery over HTTP to a routed ingress returns 200 with the fixed body; archive and attestation are already committed when the response arrives; no journal rows. Also over a real loopback HTTP socket |
| E-02 | The same delivery again (acknowledgement lost) returns 200 and adds no rows; a verified conflicting variant returns 200 and is retained as a conflict delivery |
| E-03 | Unknown and malformed ingress, missing, repeated, bad and stale signature, wrong key, revoked config, revoked connection, a foreign company's account, an unsupported type and an empty body return 400 with a byte-identical body; nothing is stored |
| E-04 | A body over the cap returns 413: by `Content-Length` without reading, and chunked as soon as the cap is passed (also over a real socket); nothing is stored |
| E-05 | A body that does not arrive within the read budget returns 408; nothing is stored |
| E-06 | Storage unavailable: an exhausted writer pool returns 503 with `Retry-After`; a receipt connection terminated while it waits on a lock (observed `pg_locks` wait) returns 503; nothing is stored; the retry after recovery returns 200 |
| E-07 | A failure at commit returns 500 with the fixed body; nothing is stored |
| E-08 | Quotas: with every slot busy the next request returns 503 without reading its body; a receipt blocked by a held revocation lock longer than its lock timeout returns 503 (observed `pg_locks` wait) and stores nothing |
| E-09 | Schema or writer-role drift returns 503 and stores nothing |
| E-10 | Only `POST` on the one route; other methods and paths are refused; the ordinary application has no receipt route |
| E-11 | Stored rows and captured logs contain no raw body, signature header, key or ingress ID; full suite green |
| E-12 | While a revocation of the route's config is held uncommitted, a bad signature is refused at once: before the refusal no statement takes a row lock or scans the catalog |
| E-13 | A config revoked, or rotated to a new version, between the unlocked read and the locked re-read is refused; nothing is stored |

Limits: synthetic fixtures only; no provider account or key, process entry point, deployment,
worker or money. Connections stay `not_admitted`. K-01–K-14 stay NOT TESTED: E-01–E-13 are
partial local evidence for K-01 and K-03. FIN-02/STOCK-01 planned; ADR-0026/0027 Proposed;
0001–0046 unchanged; K not published.

## Previous checkpoint — 2026-10-16: K1d verification authority and routing locally verified

Source `e9c86bfbd1d22e00ea66a96637cd98e9a58f27b4` on local branch `codex/package-k1d-receipt-routing`,
parent `46ab31d`. Migration 0046 and the routed entry point implement decisions 1–8 below;
criteria D-01–D-09 PASS on synthetic data. 60 new cases, 28 K1c cases ported. Final focused
**404 passed in 267.91s (0:04:27)**; full **1988 passed, 4 skipped in 1970.01s (0:32:50)**;
static, mypy (312 files), web 114 and build PASS; runtime audit 0; existing development audit
5 high FAIL; 3 container and 1 tenant-site skips NOT TESTED. Kept failures include a genuine
design defect: a validated key added by the migration owner did not see rows hidden by forced
row security, so 0046 checks under a temporary owner policy. Independent review, K CI, HTTP
ingress and the real provider are NOT TESTED or BLOCKED. FIN-02/STOCK-01 planned; ADR-0026/0027
Proposed; K not published; next migration 0047.
[Validation](evidence/2026-10-16-k1d-receipt-routing/VALIDATION.md),
[CHECKS.json](evidence/2026-10-16-k1d-receipt-routing/CHECKS.json),
[handoff](NEXT_AGENT_PACKAGE_K1D_2026-10-16.md), [prompt](NEXT_AGENT_PACKAGE_K1D_PROMPT_2026-10-16.md).

### K1d design, recorded before code

The owner answered «ok» to the offer to take the K1c handoff: review K1c, then design
and build the next small local slice. Branch `codex/package-k1d-receipt-routing` from
`46ab31dd6f41ae820a85a09f19fd5812584fc89d`. The K1d executor's
[K1c review](evidence/2026-10-16-k1d-receipt-routing/K1C_AUTHOR_REVIEW.md) is not
independent; it found the two gaps K1d closes: the attested verification-config ID
is unanchored (R1) and there is no server-controlled routing (R2).

**K1d: verification-config authority and trusted routing — local, synthetic only.**

Decisions:

1. **Authority.** Migration 0046 adds `gba.provider_verification_configs`: per
   connection, versioned (the trigger assigns previous + 1), at most one active
   version per connection, an opaque `secret_ref` in `store:name` form, never a key.
   A value that looks like a Stripe secret is refused. Rows are immutable except a
   one-way revocation; a config cannot be created for a revoked connection.
   Company-scoped RLS like the other K tables; `created_by` records the database principal.
2. **Who may create and revoke.** Only the database owner (the operator path) creates
   configs and routes, inside an explicit company context. No grant, role or
   security-definer function lets the runtime or the writer create, change or
   reactivate them. Runtime and writer may revoke: it only removes authority, and the
   writer's FOR SHARE needs UPDATE(revoked), as for connections.
3. **Not admission.** A config states which key may verify deliveries for a connection.
   It is not operational admission: connections stay `not_admitted` and test-mode only.
   No positive operational evidence is created; H4 stays a declaration.
4. **Routing.** `gba.provider_receipt_routes` maps a server-generated opaque ingress ID
   to company and connection IDs only; one route per connection; immutable. It follows
   the `tenant_hosts` pattern, but narrower: only `gba_receipt_writer` may read it
   without a company context; the runtime has no access.
5. **One entry point.** `receive_routed_receipt(pool, ingress_id, raw, signature,
   key_store=…)` replaces K1c's caller-supplied `ReceiptVerifierBinding`, which is removed.
   Order: writer role and schema guard → route → company context from the route →
   active config and connection binding under FOR SHARE → key by `secret_ref` from the
   server-held key store (missing → refuse) → K1a raw-body check against the
   connection's namespace, account and API version → K1b archive → attestation with the
   config ID → commit → result. Before the signature check only authority rows (route,
   config, binding) are read; no inbox, ledger or business rows. Every refusal is one
   generic error without IDs, references or keys.
6. **Anchored attestation.** A composite key (company, connection, config ID) from
   attestations to configs, plus an insert trigger that takes FOR SHARE on the config and
   refuses a revoked or foreign one. Revocation waits for in-flight receipts and applies
   from the next transaction.
7. **Upgrade.** An existing K1c attestation has no authority behind it, so 0046 refuses to
   apply instead of back-filling or relabelling. K1c was never published or deployed; such
   rows exist only in disposable test databases. The refusal is an explicit check under a
   temporary owner policy (the 0042 precedent), dropped in the same transaction: a test
   showed that adding the validated key alone does not see rows that forced row security
   hides from the owner.
8. **Guards.** The schema guard covers the two tables, new functions, triggers, policies
   (by role name), the partial unique index and per-role privileges. Writer-role safety
   covers six tables.

Acceptance criteria (failing tests first):

| id | Requirement |
|---|---|
| D-01 | A routed receipt commits archive and attestation with the active config ID; no journal rows |
| D-02 | Unknown ingress, missing key, wrong key, revoked config and revoked connection refuse with no rows |
| D-03 | Company A's ingress with an event for company B's account refuses; no rows in either company |
| D-04 | Rotation: v1 revoked, v2 active as version 2; a delivery signed only with the old key refuses, the new one records v2; two active versions are refused |
| D-05 | Direct SQL: runtime cannot create, change, delete or reactivate configs, nor read or write routes; writer cannot create configs or routes, nor attest with a missing, foreign or revoked config; owner cannot provision without company context; secret-like refs and configs for revoked connections are refused; routes and configs are immutable |
| D-06 | Config revocation waits behind an in-flight receipt (observed `pg_locks` wait); the receipt commits; the next receipt refuses |
| D-07 | 0045 with an attestation: 0046 fails and 0045 stays intact. Nonempty 0045 without attestations upgrades with rows unchanged |
| D-08 | Schema drift (runtime read grant on routes, dropped partial index, changed route policy, changed config trigger) makes guarded operations refuse |
| D-09 | Existing K1c tests run through the routed entry point and pass; full suite green |

Limits: synthetic fixtures only (fake `acct_` IDs, keys generated in memory); no HTTP
route, provider account or key, worker or money; no config expiry (rotation is an
operator action). K-01–K-14 stay NOT TESTED: D-01–D-08 are partial local evidence for
K-01/K-02. FIN-02/STOCK-01 planned; ADR-0026/0027 Proposed; 0001–0045 immutable; K not published.

## Previous checkpoint — 2026-10-16: K1c receipt attestations locally verified

Source `0c72a719cb9743a1f3cd7d60ea26bc46e9e2638c`,branch `codex/package-k1c-receipt-attestations`,base `f5f7987a534a518f3019b7aced28be970f18ad0d`.0045 adds protected per-delivery
verifier attestations;ordinary archive remains untrusted. Dedicated writer validates
raw K1a signatures before DB,refuses unsafe role ancestry/session context and commits
archive+attestation before result.40 new tests,2 observed pg_locks waits,no auth backfill.
Focused **369 passed in 322.44s (0:05:22)**;full **1930 passed, 4 skipped in 1685.52s (0:28:05)**;static/mypy309/web114/build PASS.
Runtime audit0 PASS;existing development5high FAIL;4 container/external skips.
No HTTP/global routing/operational admission/worker/money. Full K acceptance,independent
review,production isolation and exact K CI NOT TESTED. FIN-02/STOCK-01 planned;
ADR0026/0027 Proposed. K local only;main=fedd0f1,published J=df88c20. Next0046.
[Validation](evidence/2026-10-16-k1c-receipt-attestations/VALIDATION.md),
[reuse](evidence/2026-10-16-k1c-receipt-attestations/ARCHITECTURE_REUSE.md),
[handoff](NEXT_AGENT_PACKAGE_K1C_2026-10-16.md),[prompt](NEXT_AGENT_PACKAGE_K1C_PROMPT_2026-10-16.md).

## Previous checkpoint — 2026-10-15: K1b schema guard review locally verified

Local source `db96f005442201428700995c09f028e1b6da08c0` on `codex/package-k1b-guard-review`, base `84d4177e97ebc16e1743dcb995abf54c1b81269d`. Six schema conformance gaps
were reproduced before the correction; the existing guard now binds approved trigger
identity/shape, shared immutable source, FK parent schema and column PUBLIC privileges.
Focused **316 passed in 106.89s (0:01:46)**; full **1890 passed, 4 skipped in 1454.00s (0:24:14)**; static/build/web114 PASS.
No migration/dependency/ingress/worker/money authority. FIN-02/STOCK-01 planned;
ADR0026/0027 Proposed; full K acceptance/independent review/exact K CI NOT TESTED.
Runtime npm audit0 PASS, existing development5high FAIL;4 container/external skips.
K remains local; main=fedd0f1 and published J=df88c20 unchanged.
[Validation](evidence/2026-10-15-k1b-guard-review/VALIDATION.md),
[review](evidence/2026-10-15-k1b-guard-review/REVIEW.md),
[handoff](NEXT_AGENT_PACKAGE_K1B_REVIEW_2026-10-15.md),
[prompt](NEXT_AGENT_PACKAGE_K1B_REVIEW_PROMPT_2026-10-15.md).

## Previous checkpoint — 2026-10-15: local K1b storage foundation

Source `543b73221ac1dd0aa738bd8cf33dd468366ef27a`; full 1884 passed, 4 skipped in 1502.59s (0:25:02); focused 252 passed in 79.86s (0:01:19);40 new tests PASS.
Migration0044 and the internal repository implement receipt-only bindings, immutable
event identity, distinct deliveries/conflicts, rollback/replay, three observed pg_locks
races, RLS denials and a nonempty0043 upgrade. The binding always says `not_admitted`;
it is not the proposed verified operational connection. No HTTP route/acknowledgement,
global routing lookup, worker or money effect. Complete K1 and K-01–K-14 NOT TESTED.
Next migration0045;0001–0044 immutable in this local history.
[Evidence](evidence/2026-10-15-k1b-receipt-inbox/VALIDATION.md),
[current handoff](NEXT_AGENT_PACKAGE_K1B_2026-10-15.md).
The proposal and K1a statements below describe their historical baselines.

## Execution checkpoint — 2026-10-15: K1a only

A later owner `continue` was interpreted as proceeding with the bounded local offline
foundation, without provider actions. K1a is locally implemented in `7d25aa2d72874271a62e363817e0624fb502497c`: 96 synthetic signature/
decoder tests, focused 191 passed in 53.85s, full 1844 passed, 4 skipped in 1444.23s (0:24:04), static/build/web114 PASS.
[Evidence](evidence/2026-10-15-k1a-event-boundary/VALIDATION.md),
[current handoff](NEXT_AGENT_PACKAGE_K1A_2026-10-15.md).
The complete K1 and all K-01–K-14 remain NOT TESTED. FIN-02/STOCK-01 stay planned,
ADR-0027 Proposed; no K push/CI or actual admission. K1b connection/inbox and K2/K3
worker/effects remain ahead. Planning-baseline statements below describe e8783f6's
proposal; only the offline boundary and pinned SDK now exist.

Status: **Proposed; local planning only, 2026-10-15.** The owner's `continue`
is interpreted as preparing the next package in the agreed
[stage-2 sequence](STAGE2_PLAN_2026-10-06.md). It is not an instruction to access a
Stripe account, create credentials or provider resources, move main, or enable a module.

Baseline: `df88c20687333668d39fe76a26eabca691e62cb0`, Package J technical acceptance,
[CI 158 PASS](https://github.com/alexeyalexandrov2026-tech/GORGONA-Booking-Platform_new/actions/runs/38697747829).
Local branch: `codex/package-k-plan`; checkout remains
`C:/Users/alexa/.codex/worktrees/package-j-review2-fixes/Gorgona Booking`.
Main remains `fedd0f115f24aad52f6256298296e8c5123fb427`.
This new K branch has no publication authorization: the existing exception covers J branches only.

[ADR-0027 (Proposed)](../adr/0027-provider-events-and-reconciliation.md),
[architecture and reuse evidence](evidence/2026-10-15-package-k-plan/ARCHITECTURE_REUSE.md),
[validation](evidence/2026-10-15-package-k-plan/VALIDATION.md),
[handoff](NEXT_AGENT_PACKAGE_K_PLAN_2026-10-15.md).

## Observable result and boundaries

FIN-02 requires that repeats and reordering of provider events never duplicate a
payment, refund or journal, and that the source operation remains traceable.
For an explicitly admitted test merchant, K would durably receive verified events,
process them with retries, link each supported financial effect to its provider
operation and internal obligation, and expose unresolved reconciliation work.

The recommended first integration follows the accepted SaaS/direct-charge ownership
model in [ADR-0024](../adr/0024-invoices-obligations-and-external-settlements.md):
the connected merchant owns the payment. K observes incoming payment and refund
facts; it does not introduce charge/refund initiation, transfers, payouts, split
checkout, platform commissions, tax calculation, FX or booking auto-confirmation.
A provider refund is a new fact linked to a previously issued refund obligation,
not an edit of the original payment or a fabricated H correction.

FIN-02 and STOCK-01 stay `planned`; ADR-0026 stays Proposed. The current FIN-01,
FIN-03 and WORK-01 acceptance is preserved. Technical evidence, operational
admission, product enablement and deployment are separate records.

## What already exists

- H4 records owner-supplied provider declarations. Its schema and contracts force
  charge/refund/transfer/payout capabilities to false; no verified test admission exists
  in that code. A submitted request never grants provider authority.
- H settlements reserve and confirm manually attested external money; G provides
  the book, currency scale, immutable journals and `gba.lock_ledger(tenant)`.
- Shared command receipts, audit, tenant transactions, permissions and schema guards
  are reusable mechanisms. Provider identity must outlive ordinary command receipts.
- Booking has no webhook route, Stripe adapter, provider event inbox/outbox or event
  worker in `api/src`. The separate AI jobs runtime is not a payment worker.
- The current host resolver is for live customer booking sites. Provider delivery
  must not require a merchant's storefront to be live or take tenant identity from metadata.

The [reuse evidence](evidence/2026-10-15-package-k-plan/ARCHITECTURE_REUSE.md)
names inspected files, candidates that cannot be reused unchanged, and current sources.

## Proposed flow

```mermaid
flowchart LR
  S[Stripe delivery] --> V[Bounded raw-body signature check]
  V --> B[Verified connection and account binding]
  B --> I[Durable PostgreSQL inbox]
  I --> A[Commit before acknowledgement]
  I --> W[Retryable scoped worker]
  W --> R[Reconcile provider operation]
  R --> H[Validate explicit settlement binding]
  H --> G[One atomic G and H financial effect]
  R --> Q[Unresolved review queue]
```

1. **Connection authority.** Introduce a separately verified, versioned binding of
   provider, platform/sandbox namespace, mode, connected account, business, legal
   entity, book, permitted observation operations and evidence. Store an opaque
   secret/configuration reference, never the credential. Only the authorized
   operator verification path can create positive operational evidence; H4 remains
   a declaration. Revocation is effective on the next worker transaction.
2. **Routing and trust.** A server-controlled ingress connection identifier selects
   the verification configuration. A minimal read-only routing record may expose
   only opaque connection/tenant IDs, following the existing `tenant_hosts` pattern;
   signature verification must finish before business data is touched. Cross-check
   the verified event account and environment against that connection. Untrusted
   request host, JSON metadata or a client-supplied business ID never grant scope.
   Any new routing privilege needs direct-SQL denial tests and review before adoption.
3. **Typed ingress.** Validate raw-body size, signature freshness, endpoint key
   versions and the supported provider API/event format. Use a versioned Pydantic
   normalized envelope. Unknown format/version goes to a bounded recorded refusal
   or quarantine, without financial effects. Choose and pin the event API version
   and official SDK only after Python 3.14 compatibility and license checks. Verify
   the delivery signature timestamp; an old event creation time alone is not replay proof.
4. **Durable receipt.** Proposed inbox key:
   `(provider, platform_or_sandbox, mode, connected_account, event_id)`.
   Record each delivery digest and only the payload fields needed for supported workflows;
   enforce immutable identity and a documented retention policy for sensitive data.
   Compare typed immutable event facts after signature verification: transport or
   serialization differences alone are not conflicting money facts. Same event key
   with inconsistent financial/account/object facts requires review, never overwrite.
   Return 2xx
   only after durable commit or a known durable duplicate; unavailable storage
   returns a retryable failure. Acknowledgement does not claim a payment was posted.
5. **Worker.** Claim a bounded batch with recoverable lease/attempt fencing. Persist
   attempts and typed errors. One financial transaction validates the lease, takes
   the ledger lock, applies the permissible operation and records its effect/result.
   Expired workers cannot commit after a newer claimant. No provider network call
   while a financial transaction or ledger lock is held. Pending retry, ignored,
   reconciled, applied and needs-review outcomes are explicit.
6. **Semantic identity and state.** Separate event identity from operation identity.
   One charge/payment fact has one canonical provider operation link; separate
   events for PaymentIntent and Charge cannot produce two effects. Each refund has
   its own refund ID, distinct from a payment. Stale delivery cannot regress state;
   do not rank lifecycle states by a numeric enum or event timestamp. Ambiguous,
   incomplete or incompatible facts require an account-scoped provider retrieval
   under admission and a repeatable reconciliation decision.
7. **Financial bridge.** Require an explicit, authorized binding of the provider
   object to the same merchant/book/currency and an existing reserved settlement;
   compare exact integer minor units and the actual successful amount. Do not infer
   allocations from email, customer name, booking price or arbitrary metadata.
   Reuse H cap/date/control-account checks through a reviewed shared posting
   primitive; do not call `settlements.confirm` with a forged manual attestation.
   Add provider provenance and journal lineage with a forward migration, retaining
   all existing manual-attestation contracts. SQL must require the verified operation,
   same-transaction effect and balanced journal together.
8. **Accounting limits.** A provider payment is not evidence of a bank payout or
   recognized revenue. The company explicitly selects its appropriate provider
   clearing/control accounts and posting date. Fees, net payout and gross collection
   are distinct. Use only provider/book currency combinations whose minor-unit
   interpretation is verified; discrepancies, closed periods, missing reserves,
   unsupported currencies or uncertain fees yield review without partial posting.
9. **Cross-path duplicates.** The object binding can explicitly link an already
   manually recorded payment only after matching scope, identity and exact amounts.
   Preserve its original manual provenance and append verification evidence; do not
   post again or relabel history. Unlinked manual references cannot prove whether
   the same physical money was recorded: quarantine the uncertainty rather than
   promise automatic semantic dedup across unrelated free text.
10. **Refunds and suspension.** Observe authorized successful refund facts against
    the existing H refund obligation and reserve; pending/failed events do not post.
    Partial refunds, duplicates and reordering preserve the cap and original payment.
    Unsupported disputes/chargebacks and unbound refunds create a reconciliation
    item, never a generic negative payment. On module/admission revocation, retain
    already-authenticated inbox/history/recovery and refuse new money effects;
    define and test receipt-only draining separately from operational processing.

Table names, route and worker models above are proposals, not existing interfaces.
The next migration is **0044**; recheck the maximum before implementation. Migrations
0001–0043 are immutable. No dependency, schema, worker or route is added by this plan.

## Reviewable slices

| Slice | Deliverable | Required evidence before advancing |
|---|---|---|
| K0 | Select the permitted test environment, merchant/book and operation scope; approve integration policy and verified-admission contract | Explicit owner authorization for provider/credential actions; actual safe test-admission evidence; never infer it from H4 |
| K1 | Typed signature adapter, scoped routing and durable inbox; new forward schema and guards | Red-to-green body/signature/account/mode tests, raw HTTP and SQL refusals, duplicate commit race, crash-before/after-ack proof |
| K2 | Bounded worker, fencing, operation identity and reconciliation decisions | Real concurrent claims/restarts, stale worker refusal, different events/one operation, reordering and provider failure; observed pg_locks waits for race claims |
| K3 | Provider provenance and atomic G/H payment/refund application | Direct SQL and API parity, cap and closed-period races, cross-path identity, no partial journals, existing H contract regression |
| K4 | Finance review UI and recovery, redacted metrics and operational runbook | Real desktop/mobile/axe; all list cursors; unknown outcome/retry/reconciliation UX; no false paid/verified labels |
| K5 | Complete FIN-02 evidence and separately authorized readiness decision | Actual admitted Stripe test execution, full disposable PostgreSQL suite, static/web/container gates, independent review, published exact-head CI |

K0 provider execution is **BLOCKED** by the standing separate provider/credential
authorization boundary. The plan and local architecture inspection are completeable
without those actions. Later local coding and publication scope must be made explicit
when the owner selects this proposal; no K branch push is authorized by the J exception.

## Acceptance matrix — all NOT TESTED

These are test requirements, not a statement that implementation exists.

| ID | Observable requirement | Status |
|---|---|---|
| K-01 | Modified/raw-body, missing/bad/stale signature and wrong verification key fail before tenant business reads, inbox acceptance or money effects | NOT TESTED |
| K-02 | Unknown/revoked account, mismatched merchant/tenant/book, test/live or sandbox mismatch fail closed; verified admission cannot be forged by H4/manual SQL | NOT TESTED |
| K-03 | Same event delivered repeatedly/concurrently has one durable inbox identity; ack lost after commit causes safe replay; delivery-only differences never duplicate effects, conflicting immutable facts are visible | NOT TESTED |
| K-04 | Different events and different object representations of one successful payment have one operation/effect/journal; duplicates survive receipt expiry | NOT TESTED |
| K-05 | All supported event permutations converge without payment-state regression; equal timestamps, stale snapshots and missing objects force safe reconciliation | NOT TESTED |
| K-06 | Tenant/book/currency/amount/binding/reserve must match; unsupported scales, overflows, negative/zero money and partial mismatches produce no partial posting | NOT TESTED |
| K-07 | Success, partial refund, failed/pending refund and duplicate/reordered refund events preserve the original payment and exact H obligations; no double refund effect | NOT TESTED |
| K-08 | Inbox, operation, ledger lineage and H cap cannot be bypassed by runtime/direct SQL; rollback leaves no partial financial effect | NOT TESTED |
| K-09 | Two workers, expired lease, crash/retry and period close have one legal outcome; every claimed race has an observed pg_locks wait with the intended blocker | NOT TESTED |
| K-10 | Existing manual attestation remains truthful; explicit prior-payment verification adds no duplicate journal; unresolved cross-path identity needs review | NOT TESTED |
| K-11 | Module/admission disablement prevents new effects while preserving history/recovery; schema/policy/function corruption refuses affected operations | NOT TESTED |
| K-12 | Worker retries/backoff/dead-letter/reconciliation remain bounded; provider timeout and cancellation never fabricate success; payloads/credentials/customer data stay out of logs and browser recovery | NOT TESTED |
| K-13 | Finance rights only; branch/delegate/support/foreign tenant refusals; real desktop/mobile/axe, complete pagination and safe action recovery | NOT TESTED |
| K-14 | Actual admitted Stripe test events plus static, unit, fresh PostgreSQL, browser, production-image CI, independent review and exact-SHA evidence; Booking/FIN-01/FIN-03/WORK-01/STOCK-01 regression | NOT TESTED |

## Decisions to resolve before implementation

Recommended defaults for a concrete owner review:

1. **Scope:** event observation and reconciliation for merchant-owned direct charges
   and refunds, with no payment/refund creation or new checkout. Any initiation path
   is a later explicitly selected slice.
2. **Test target:** one owner-selected test/sandbox merchant, legal-entity book and
   verified currency first; expand the explicit currency/operation matrix before
   broader acceptance. No production credentials or real funds.
3. **Ambiguity:** require explicit financial binding and human reconciliation of
   unbound/mismatched or previously manually attested facts. No automatic booking,
   revenue recognition, allocation guessing or period reopening.

After scope selection, the provider test authorization must name the environment,
account/operation boundaries and safe credential mechanism. Do not request secrets
in chat or documents. This requirement comes from the owner's explicit prohibition
on provider, funds and credential actions, and the stage-2 K admission prerequisite.
