# Package O — construction (stage 4, BUILD-01): plan and decisions (2026-10-30)

**Status: plan; decisions taken by the agent under the owner's full delegation** («Делай как считаешь нужным
я доверяю тебе») and the user's "continue" of 2026-10-30 after package N (N8 done, CI SUCCESS 41098025188).
Branch `codex/package-o-plan` from `3df9ec2` (N8 docs). No code yet. Production stays one common launch of all
39 directions (master plan §13); this package is **build order** for stage 4, not a separate launch.

## Why this package now

Stage 3 (Beauty and TMS) is built: BEAUTY-01 is technically verified; TMS-01..03 pass locally for the carrier,
the independent dispatcher (package M) and the broker/3PL (package N, review fixed in N8). The readiness of the
transport module, enabling it and `main` wait for the owner's word; they do not block the next build stage.
Stage 4 of the master plan is "Construction and rental" with BUILD-01, RENT-01 and PROPERTY-01. This package
is the construction part (master plan §8 "Construction": request → survey → estimate → proposal → contract →
plan → execution → acceptance → settlements → warranty). Rental (RENT-01) and property (PROPERTY-01) are the
next packages; field services (§8 "Field services") follow them as their own package.

BUILD-01: "An estimate change does not change the original contract; stage acceptance, retainage and the
invoice reconcile with the budget."

## What exists and is reused

Counterparties and documents (stage 1, versioned files); branches and rights; the ledger and FIN-03 invoices,
manual accruals, obligations, external payments and credit notes; STOCK-01 materials, receipts and write-offs
at moving-average cost; WORK-01 staff, skills, shifts and time entries. Construction adds no second ledger,
no second stock and no second time-keeping: it links to those facts.

## Decisions (agent, under the owner's delegation)

1. **A new module `construction`** ("Construction and repair") in the registry, `implemented` and **not
   enableable** until acceptance and the owner's word — the same rule as `transport` (ADR-0028). It depends on
   `counterparties` and `finance_documents`. The generic `projects` module stays for professional services
   (PRO-01, stage 5). Permissions `construction.read`, `construction.manage` and `construction.approve`
   (recording the customer's acceptance of an estimate, a change order or a stage; owners and managers by
   default, delegable only explicitly).
2. **A construction project** (a job) belongs to one business and one branch, has one customer counterparty,
   a site address with its time zone and **one currency**. Its number is unique in the business.
3. **Estimates are insert-only versions.** An estimate version has lines: kind (material, labor, equipment,
   subcontract, other), description, quantity with unit, unit cost and unit price (minor units), an optional
   link to a STOCK-01 material and a phase. Totals are derived, never stored as a second truth. A version
   sent to the customer is a **proposal**; it is frozen from then on.
4. **The contract is the accepted proposal version, frozen.** Accepting records who accepted it, the source
   (on the platform, signed paper, email) and the time; the accepted version becomes the **original
   contract** and is never edited (BUILD-01, part 1). An optional signed copy is a stage-1 document version.
5. **Change orders** are numbered, insert-only, with lines that add, remove or reprice scope (cost, price,
   days); states: proposed, approved, rejected, withdrawn. The **current contract sum** is the original plus
   approved change orders, derived on read. Two racing approvals or an approval racing a withdrawal leave one
   outcome (observed `pg_locks` wait). A change order never rewrites the original or an earlier change order.
6. **The budget** is the contract's cost side per phase and line (original plus approved change orders).
   **Commitments** are subcontracts and supplier orders against budget lines (a counterparty, amount,
   versioned). **Actual costs** are links to existing facts — a STOCK-01 write-off line, a FIN-03 payable
   (supplier invoice or manual accrual) and a WORK-01 time entry with a cost rate — each linked once (unique),
   insert-only, with a reversal row instead of an edit. Budget, committed and actual are shown per line and
   phase; overruns are shown, not blocked.
7. **Execution:** phases with planned dates and dependencies; daily reports (insert-only: date in the site's
   time zone, crew, weather, notes, photos as document versions); **completed quantities** per budget line as
   cumulative insert-only measurements, never above the contracted quantity without an approved change order.
   Inspections, defects and a punch list as items with states.
8. **Progress billing with retainage:** a **pay application** for a period bills the completed value to date
   (completed quantity × contract unit price) minus what earlier pay applications billed; the business's
   retainage rate (basis points, set on the contract, versioned) is held from each billed amount. The amount
   due is one FIN-03 invoice; the **retained amount is a separate FIN-03 receivable obligation** that becomes
   due only on final acceptance (or a recorded partial release) — never mixed with the amount due. One pay
   application per project and period; two racing ones leave one (observed wait). Billed to date never exceeds
   the current contract sum (BUILD-01, part 2).
9. **Stage acceptance and final acceptance** are recorded facts (who, source, time) on a phase or on the
   project; a phase's acceptance is required before its retainage is released; final acceptance closes
   billing except the retainage release and starts the **warranty period** (dates on the contract). Warranty
   claims are items against the project with states; their repair cost links to actual costs.
10. **Reconciliation view (BUILD-01):** per project: contract sum (original + approved changes), budget,
    committed, actual, completed value, billed, retained, released, paid (from FIN-03), and the differences,
    all derived. No column stores a margin or a balance twice.
11. **Customers on the platform** answer in their own company through a grant (as carriers do in package N);
    otherwise the business records the customer's answer with its source.
12. **Units, money and time:** quantities are decimals with a unit code; money in minor units in the project
    currency; dates of daily reports and measurements are local to the site's time zone; times are UTC.

## Slices (each: failing tests first, gates, record, code and docs commits; next migration 0087)

| Slice | Content |
|---|---|
| O1 | Module `construction` (implemented, not enableable), permissions; projects; estimate versions and lines; proposals frozen; migration 0087 |
| O2 | Contract = accepted proposal (frozen original); change orders with states; current contract sum derived; races |
| O3 | Phases and budget; commitments; actual cost links to STOCK-01 write-offs, FIN-03 payables and WORK-01 time entries; budget vs committed vs actual |
| O4 | Execution: daily reports, completed quantities (cumulative, capped by the contract), inspections, defects, punch list |
| O5 | Pay applications with retainage through FIN-03; one per period; billed ≤ contract sum; races |
| O6 | Stage and final acceptance, retainage release, warranty period and claims; reconciliation view |
| O7 | Screens: projects, estimate editor, change orders, budget, daily reports, pay applications, reconciliation; real browser desktop and mobile |
| O8 | Acceptance: BUILD-01 and O-01..O-10; independent review only with the owner's consent; readiness only on the owner's word |

## Acceptance (all NOT TESTED)

| id | Requirement |
|---|---|
| O-01 | The module cannot be enabled before acceptance; every route refuses when it is off; company and branch scope and direct SQL refusals hold |
| O-02 | Estimate versions are insert-only; a proposal is frozen; totals are derived |
| O-03 | Acceptance freezes the original contract; a change order never rewrites it; the current sum = original + approved changes |
| O-04 | Two racing approvals of one change order (or approval vs withdrawal) leave one outcome with an observed wait |
| O-05 | Each actual cost fact is linked once; a reversal is a new row; budget, committed and actual reconcile per line and phase |
| O-06 | Completed quantity is cumulative and never above the contracted quantity without an approved change |
| O-07 | A pay application bills completed value to date minus earlier billing; retainage is a separate receivable; billed ≤ contract sum; one per period under races |
| O-08 | Retainage is released only after the phase or final acceptance; release is recorded once |
| O-09 | `construction.approve` is its own right; customers on the platform answer only through a grant |
| O-10 | Real browser desktop and mobile, keyboard, axe; the full suite stays green |

## Not in this package

Percentage-of-completion revenue recognition and tax invoices; lien waivers and jurisdiction-specific
construction forms; drawing management beyond document versions; scheduling algorithms (critical path is shown
from dependencies, not optimised); field services (own package); rental (RENT-01) and property (PROPERTY-01);
any live provider. Readiness of `construction`, enabling it and `main`: only on the owner's word.
