# ADR-0024 — Invoices, obligations and externally confirmed settlements

- Status: **Proposed (2026-10-06)**; no implementation or acceptance is implied.
- Scope: package H of the owner-approved stage 2; FIN-03 and the admission-record
  foundation of FIN-02. [Execution plan](../plan/PACKAGE_H_PLAN_2026-10-06.md).
- Base: accepted G at 5be6e7abd7b552903a4f4b2884b150c62532c17d; ADR-0023.
- Decision owners: unassigned; owner confirmation of the proposed package rules
  is required before adding money-effect operations.

## Context

G has real ledger books, chart, immutable balanced journals, reversal, monthly
periods, company-wide finance permissions and command recovery. It is technically
verified, while FIN-03 is planned. Finance module readiness for G must never be
treated as acceptance of a new invoice or payout path. Bookings remain price
snapshots, not payment or revenue evidence.

The master plan distinguishes price, issued invoice, received money, recognized
revenue, deposit and an obligation to a recipient. FIN-03 requires two settlement
documents competing for one obligation to preserve the unpaid balance across
reservation, partial payout and reversal. H must therefore include a general
obligation/settlement model rather than only sales invoice CRUD.

The selected implementation is a PostgreSQL domain extension of G, not a second
cash ledger, payment gateway or cloud service. Architecture/reuse evidence:
[ARCHITECTURE_REUSE](../plan/evidence/2026-10-06-package-h-plan/ARCHITECTURE_REUSE.md).

## Proposed decision

1. **Documents and parties.** Versioned internal receivable/payable invoices and
   credit notes, tied to one legal-entity book, one currency and an immutable
   counterparty version. Drafts use expected revision; issued content is insert-only.
   Human-readable numbers are scoped by book/type; they do not replace UUID/source
   identity or imply a statutory invoice for an unselected jurisdiction.
2. **Explicit posting.** At issue, the authorized user chooses control and
   counter-accounts and explicitly confirms recognition when selecting a revenue
   or expense account. Invoice state or booking state never chooses that policy.
   Issue records document, obligation, journal link, audit and receipt in one
   transaction. Ledger G remains the sole source of posted money/balance.
3. **Obligation identity and origin.** Immutable principal A and key
   `(tenant,book,counterparty,source_kind,source_id,component)`. Invoice/manual/
   credit_refund are distinct sources. A manual obligation is a new accrual,
   with explicit control/counter accounts and its balanced G origin posted in the
   same transaction; it is not an arbitrary budget row. Settlement uses that
   control account. Importing/linking existing manual/opening G entries is outside
   initial H and requires a separate reconciliation process, never duplicate accrual.
   Industry references remain typed identifiers, not executable instructions.
4. **Settlement lifecycle.** Prepared, approved, reserved, externally sent/unknown,
   partially confirmed, confirmed, cancelled/released are separate audited facts.
   H does not send funds. A sent/unknown external outcome cannot release a reserve
   merely because time passed, finance was disabled or a response was lost.
   An authorized human must confirm the fact or explicitly attest a resolved
   no-payment outcome with source/reason. Same-actor approval is visible; a future
   separation-of-duties policy needs its own accepted scope.
5. **One cap.** At commit, confirmed allocations P, credit settlement C and active
   reserves R satisfy `P+C+R<=A`, all nonnegative. Reservations produce no journal
   entry. Partial confirmation transfers the exact amount from R to P and posts
   G; unconfirmed remainder stays reserved until explicit release/resolution.
   One settlement document may allocate to several obligations only when book,
   counterparty, direction and currency match.
6. **External identity.** Cash/bank/other-external confirmations have stable
   source-account alias and receipt/transaction reference, unique within book and
   direction. Exact allocations equal confirmed money; no implicit unallocated
   advance. Idempotency-key dedup and semantic financial-source dedup are separate.
   Manual confirmation is labeled as such, never as provider-verified payment.
7. **Credits and refunds.** Credit amount is limited by uncredited invoice lines;
   an active reserve first needs explicit resolution. Unpaid credit becomes C;
   the paid part creates a distinct opposite-direction refund obligation. Original
   principal and cash records do not change. Invoice100/paid70/credit50 yields
   C30/refund20. Refund obligations use the same reserve/payment cap. Corrections
   of facts create immutable events and mirrored G entries; they never rewrite
   a physical refund just to make an original correction possible. Effective P/C
   excludes explicitly corrected/voided versions, with their full history retained.
   Payment states confirmed/corrected/voided keep external identity permanently
   bound to the same payment_id. A replacement corrects an erroneous attestation
   under expected revision, mirrors the old effect, restores its allocations to
   reserve and confirms the replacement within that reserve in one transaction.
   No credit/refund dependency may exist for this initial H correction. Issued
   credit, real refund or sent/unknown dependency instead produces
   FINANCIAL_RECONCILIATION_REQUIRED without effects. Credit void is only allowed
   when its refund has no real/sent/unknown allocations or reserves; mirror credit,
   undo C and cancel the untouched claim are atomic. More complex reconciliation
   after a real refund is a separately accepted future capability, not a fake undo.
8. **Atomic locking.** Reuse `gba.lock_ledger(tenant)` and READ COMMITTED. Acquire
   ledger before membership share; any new cross-domain lock order is explicit.
   SQL and service enforce identical state/source/budget rules. Ledger deferred
   balance checks are completed before the command receipt becomes durable.
   This is an application design requiring actual race/failure checks, not a
   concurrency guarantee inferred only from documentation.
9. **Migration and interfaces.** Forward migration 0021 only. Do not edit 0020 or
   the previous checksums. G only accepts manual/opening/reversal today; legitimate
   new sources require SQL, backend and client evolution together. Introduce
   schema-v2 extended journal views and explicit client negotiation; preserve G
   write-v1 and v1 records. Legacy reads must request upgrade when an H record
   cannot be represented, never silently omit it. Trial balances include all
   entries. Unrestricted G reverse cannot change a managed H entry without its
   business correction; a DB lineage control checks that relationship too.
10. **Recovery.** Reuse shared idempotency/audit code and the minimal-reference
    recovery pattern. Extend a finite versioned command registry for H; durable
    entity/source links survive ordinary receipt expiry, and cancellation seals
    a delayed original under the same ledger lock. No full command body, amount,
    note, external reference or token is stored in browser recovery data.
11. **Feature gates and rights.** Finance stays verified for G; FIN-03-specific
    mutation gates remain closed until full H acceptance. Do not demote G or
    silently enable H from module selection. Reuse company-wide owner/manager
    finance.read/manage; no branch/delegate/support access. Module OFF blocks new
    money effects but retains history/recovery and non-money reserve release.
    Non-owner payment authority is a proposed package rule, not a claim of a new
    owner decision already made.
12. **Provider admission.** Record provider request, business/book/legal entity,
    declared country, industry, operation, opaque account reference and evidence.
    H has no positive operational capabilities, credentials or gateway actions.
    not_checked/suspended/unsupported are safe factual states; positive access
    needs a separately verified environment/account/operation. An owner-entered
    assessment alone cannot activate payment. Provider callbacks/signatures,
    event dedup/order/refund processing belong to K; FIN-02 remains planned.

## Posting examples to review

These are proposed program mappings after explicit human account selection, not
tax/accounting advice for a jurisdiction. No default silently recognizes income.
Credit counter-accounts are selected explicitly, not copied as a default from
the invoice. If a manual G reclassification changed recognition, provide reason
and an existing same-book/currency journal reference where applicable. For example,
invoice Dr AR100/Cr deferred100, later G Dr deferred100/Cr revenue100, then credit50
with the explicitly chosen revenue account gives revenue50/deferred0/AR50. G
remains the actual book report; H does not automatically certify invoice-level
recognition lineage from an arbitrary manual journal or add a recognition workflow.

| Fact | Debit | Credit | Obligation effect |
|---|---|---|---|
| Receivable invoice issued | Selected receivable asset | Selected revenue or deferred-income liability, explicitly attested | Create receivable A |
| Payable invoice issued | Selected expense or prepaid asset, explicitly attested | Selected payable liability | Create payable A |
| Confirm external incoming payment | Selected cash/bank asset | Obligation control asset | P increases, R decreases |
| Confirm external outgoing payment | Obligation control liability | Selected cash/bank asset | P increases, R decreases |
| Receivable credit partly paid | Explicit currently appropriate counter-accounts, human attested | Receivable for unpaid part; refund liability for paid part | C plus separate payable refund |
| Payable credit partly paid | Payable for unpaid part; refund asset for paid part | Explicit currently appropriate counter-accounts, human attested | C plus separate receivable refund |
| New manual receivable/payable accrual | Same explicit accounts as respective invoice direction | Matching control/counter account | A and G origin created together |
| Reservation/release | None | None | R changes only |

Posting date must be an open period of the book. Actual external date is preserved
separately; neither the client nor server reopens a period or alters an archived
account automatically. Full reversal references original lines. Partial credits
need explicit original-line allocations; rounding/line totals cannot be guessed.

## Reuse and bounded change

Use current Python/FastAPI/Pydantic/psycopg/PostgreSQL and Next/React/Zod/BigInt.
Keep the existing module system, authorized_tenant, insert-only document patterns,
command receipts, audit, app factories, fake test IdP and actual PostgreSQL/browser
harnesses. Add small public ledger posting/correction interfaces where H is a
real caller; do not fork SQL balance logic or import arbitrary private helpers.
Do not rewrite agreement, booking, counterparty or configuration modules.

Shared money strings/currency scale and G lock are candidates with proved local
source behavior. Source-kind extension, managed reversals, command recovery and
schema guard need explicit forward changes: they are not already H-ready.
No new dependency or service is justified by this design.

## Acceptance and status

All H-01..H-12 checks in the execution plan are **NOT TESTED** today. Required
evidence: red-to-green for state/budget/source controls; direct-SQL constraints;
both orders of real competing-document races; payment/release/credit/close races;
reference recovery/replay/expiry; untrusted scope denials; G/API-contract regression;
real desktop/mobile/Axe; full unit/integration/build/container CI exact code SHA;
independent review and a separate acceptance commit.

FIN-03 remains planned until code exists, implemented while the feature gate is
closed, technically_verified only after all H phases pass. FIN-02, provider
production admission, pilot and jurisdiction-specific compliance remain separate.

## Sources and limits

- Local source inspected at 5be6e7a; the G CI green is baseline evidence only.
- [PostgreSQL 18 explicit locking](https://www.postgresql.org/docs/18/explicit-locking.html),
  checked 2026-10-06: lock behavior and transaction scope inform the proposed
  serialization; actual H ordering and cap behavior still need runtime proof.
- [Stripe Connect SaaS](https://docs.stripe.com/connect/saas), checked 2026-10-06:
  the future provider path stays within the accepted SaaS/direct-charges model.
  This lookup is not access to an account, activation or an operational capability.

Production migrations, deployment, Azure, DNS, billing, provider access and changes
to other projects require separate authorization. G/owner/incoming checkouts are
preserved. No H code, schema application, real invoice, payout or refund occurred
while preparing this proposed ADR.
