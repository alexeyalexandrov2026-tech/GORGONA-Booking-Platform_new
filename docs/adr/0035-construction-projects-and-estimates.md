# ADR-0035: Construction module, projects and estimate versions

Status: accepted for package O slice O1 (2026-10-30). Taken by the agent under the owner's full delegation
(«Делай как считаешь нужным я доверяю тебе») after the user's "continue"; the module is registered as
`implemented` and **not enableable**, so no business can use it before acceptance and the owner's word.

## Context

Stage 4 of the master plan starts with BUILD-01: "An estimate change does not change the original contract;
stage acceptance, retainage and the invoice reconcile with the budget." Package O's plan is
`docs/plan/PACKAGE_O_PLAN_2026-10-30.md`. The first slice needs the place every later fact hangs on (a
construction project) and the priced scope the contract is made from (the estimate).

## Decision

1. **Module.** A new optional module `construction` ("Construction and repair"), depending on `counterparties`
   and `finance_documents` (progress billing and retainage go through FIN-03 in O5). Registered as
   `implemented`; it **cannot be enabled** until acceptance (ADR-0020 rule). A new module id is a structural
   registry change: `MODULE_REGISTRY_VERSION` becomes 5 (ADR-0019: a published configuration is never
   altered). Writes are gated by `gba.require_enabled_module('construction')` and the early module check;
   reads are not gated. The generic `projects` module stays for professional services (PRO-01, stage 5).
2. **Permissions.** `construction.read`, `construction.manage` and `construction.approve` (recording a
   customer's acceptance, used from O2); owners and managers hold all three; permissions version 11. Nothing
   of construction is delegable in O1.
3. **Project.** A construction project belongs to one business and one branch (location), names a customer
   counterparty, a number unique in the business, a name, a site address and the site's IANA time zone, and
   **one currency** (ISO 4217 letters). It is replaced whole with its expected revision. Once the project has an
   estimate its currency is fixed (`CONSTRUCTION_CURRENCY_FIXED`): every amount of the project is in it.
4. **Estimate versions are insert-only.** Each save of an estimate creates the next version (1, 2, ...) based on
   the latest one the client read (`based_on`; a stale base is `CONSTRUCTION_ESTIMATE_STALE`). A version lists
   lines in order: kind (`material`, `labor`, `equipment`, `subcontract`, `other`), description, phase label,
   quantity (decimal, up to 4 places) with a unit, unit cost and unit price in minor units, and an optional
   STOCK-01 material. Lines and versions are never updated or deleted by the runtime.
5. **Totals are derived.** A line's cost and price are quantity × unit amount rounded half up to a minor unit;
   a version's totals are the sums. Nothing stores a total.
6. **Proposal.** A version becomes a proposal when it is sent to the customer: `proposed_at` and `proposed_by`
   are set once (a trigger refuses any other change); only the latest version can be proposed. A later version
   may still be made (a revised proposal); the proposed one never changes. Accepting a proposal as the original
   contract is slice O2.
7. **Races.** Saving a version and proposing lock the project row; two racing saves on one base leave one
   version and one `CONSTRUCTION_ESTIMATE_STALE` (proved with an observed `pg_locks` wait).
8. **Scope and isolation.** RLS by company on every table; projects, estimate versions and lines are scoped to
   the caller's branch (the project's location). Direct SQL updates of lines and deletes are refused.

## Consequences

O2 adds the contract (an accepted proposal, frozen) and change orders; O3 phases, budget, commitments and actual
cost links; O4 execution; O5 pay applications with retainage; O6 acceptance and warranty; O7 screens; O8
acceptance. The module stays `implemented` and not enableable until package O's acceptance and the owner's word.
