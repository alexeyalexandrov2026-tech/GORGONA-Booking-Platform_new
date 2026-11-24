# Package O, slice O7a — construction screens: projects, estimates, proposal, contract and change orders (2026-11-02)

Plan: [PACKAGE_O_PLAN_2026-10-30.md](PACKAGE_O_PLAN_2026-10-30.md), slice O7 ("screens: projects, estimate
editor, change orders, budget, daily reports, pay applications, reconciliation; real browser desktop and
mobile") and acceptance O-10 (real browser desktop and mobile, keyboard, axe; the full suite stays green).
Architecture: [ADR-0035](../adr/0035-construction-projects-and-estimates.md). Previous slice:
[O6b](PACKAGE_O6B_DESIGN_2026-11-02.md), handoff [NEXT_AGENT_PACKAGE_O7_2026-11-02.md](NEXT_AGENT_PACKAGE_O7_2026-11-02.md).
Branch `codex/package-o7a-construction-screens` from the O6b docs commit `04db17c`, in the O5 worktree.
Same process as O1-O6b: failing tests first, one executor, one disposable PostgreSQL 18 cluster per run,
gates on the Google Cloud VM `gorgona-dev`, a source-bound record, code and docs commits, push for CI
without a PR.

## O7 is split in three

The construction API has about fifty routes (O1-O6b). One screen slice for all of them would be too large
to review, so O7 is split like O3, O4 and O6, each with its own branch, failing tests first, gates and
record:

| Slice | Screens | Routes it uses |
|---|---|---|
| **O7a** (this) | Construction list and project form; project page with estimate versions and the estimate editor; the proposal; the customer's acceptance (the contract); change orders (propose, approve, reject, withdraw) | O1, O2 |
| O7b | Budget per phase and line with committed and actual; commitments; actual cost links and reversals; schedule; daily reports; completed quantities | O3a, O3b, O4a |
| O7c | Inspections and quality items; retainage rate; pay applications; stage and final acceptance with retainage release; warranty claims and repairs; the reconciliation view (BUILD-01) | O4b, O5, O6a, O6b |

O8 (acceptance of BUILD-01 and O-01..O-10) follows O7c.

## Scope of O7a

- Web only; **no API change and no migration** (next migration stays 0096). If a test shows that a read the
  screen needs is missing, the slice stops and records it instead of adding a route quietly.
- `web/app/construction/page.tsx`, `web/components/construction.tsx` (list, project form, project page),
  `web/components/construction-estimates.tsx` (estimate versions and editor, proposal, contract),
  `web/components/construction-changes.tsx` (change orders), `web/lib/construction-contracts.ts` (strict zod
  contracts of every O1-O2 response, registered in `managementResponseSchema`), `web/lib/construction-api.ts`
  (reads and commands), a navigation entry "Construction".
- Tests: `web/tests/construction-contracts.spec.ts` (contracts and the pure helpers, in `test:unit`),
  `web/tests/construction.spec.ts` (real browser, desktop and mobile, `test:management:construction`) and
  `api/tests/integration/test_o7a_construction_browser.py` (seeds through the routes, runs the browser,
  reads the database back).

## Decisions (O7a, agent, under the owner's delegation)

1. **Who sees the screen.** An active, non-delegated owner or manager (the roles that hold
   `construction.read`, `.manage` and `.approve`; construction is not delegable). Everyone else sees
   "This area requires owner or manager access." The server still decides every call; a refusal is shown
   as the server's message in an alert. A branch-limited manager sees only its branch's projects because
   the server returns only those.
2. **The list** shows every project (read to the end through `?after=`), with number, name, customer name,
   branch name, currency and the latest estimate version. "No projects yet." when empty, "Loading the
   projects…" while reading. If the module is off the read is refused and the alert shows why.
3. **The project form** creates or edits a project: number, name, customer (active counterparties with the
   customer role), branch, site address, time zone (an IANA name; the server checks it) and currency (three
   capital letters). It sends the whole project with the revision it read. A new project keeps its id and a
   command keeps its Idempotency-Key until the save succeeds, so a retry after a lost answer saves once
   (as on the transport screens, ADR-0030). The server's refusals (number taken, currency or customer fixed
   once a contract exists, unknown time zone, stale revision) are shown, not guessed.
4. **The project page** shows the project, its estimate versions (version, based on, note, proposed or not,
   cost and price totals) and the lines of the selected version. **Totals are the server's** (derived,
   O-02); the screen never adds them up itself.
5. **The estimate editor** starts from the latest version's lines (or one empty line) and saves the next
   version with `based_on` = the latest version the page read; a stale page gets the server's
   `CONSTRUCTION_ESTIMATE_STALE` and must reload. Each line: kind, description, phase, quantity, unit, unit
   cost and unit price. Money is typed in the project currency's major units and sent as exact minor units
   (no float), with the currency's decimal places taken from ISO 4217 through `Intl`. A quantity has up to 4
   decimal places. The editor is closed once the project has a contract (the server refuses it too).
6. **The proposal**: "Send as proposal" on the latest version that is not proposed, while there is no
   contract. A proposed version is shown as frozen with its time.
7. **The contract**: with a proposal and no contract, "Record the customer's acceptance" (signatory, source
   paper or email, optional note) records it for the latest proposed version. Then the contract shows the
   accepted version, signatory, source, time, the original, approved-changes and current sums (cost, price)
   and approved days, all as the server derived them (O-03).
8. **Change orders** are listed with number, title, state, days, cost and price. The proposal form has a
   title, an optional reason, days (may be negative) and lines that either add scope (as an estimate line)
   or remove scope (a contract line and a quantity). A proposed change order can be approved or rejected
   with the customer's source (paper or email) and an optional note, or withdrawn; the server checks each
   answer (states, scope, completed and billed limits, races).
9. **Times** are shown in the project's time zone (site), with the zone named. **Accessibility**: every form
   is a named `form`, every table has a name and sits in a focusable scroll region, every control has a
   label, the result of a command is announced in a status line and a refusal in an alert; no horizontal
   page scroll at 375 px; axe finds no violation on the list, the project page and the change orders.

## Acceptance of O7a — PASS 2026-11-02 (code `6c5ea3d`, [evidence](evidence/2026-11-02-o7a-construction-screens/CHECKS.json))

| id | Requirement | Result |
|---|---|---|
| O7a-01 | Strict contracts accept every O1-O2 response and refuse an unknown field, a bad id, a bad quantity or a negative amount; money input is converted to exact minor units by the currency's decimal places | PASS |
| O7a-02 | In a real browser (desktop and mobile) an owner creates a project, saves two estimate versions (the second after a lost answer, saved once), sends the second as the proposal and records the customer's acceptance; the database holds two versions, the second proposed, and the contract on it with source and recorder | PASS |
| O7a-03 | In the same browser the owner proposes a change order that adds and removes scope and approves it by keyboard with its source; the contract's current sum shown is the server's original plus the approved change; the database holds the decision with its source | PASS |
| O7a-04 | Axe finds no violation on the list, the project page and the change orders; no horizontal scroll on mobile | PASS |
| O7a-05 | Web static checks (typecheck, lint, format, unit, build) and the full suite stay green | PASS |

## Not in O7a

Budget, commitments, costs, schedule, daily reports and completed quantities (O7b); quality, retainage, pay
applications, acceptances, warranty and reconciliation (O7c); a material picker for estimate lines (the
line's `material_id` is kept when an existing version is copied but not chosen on the screen); the
customer answering on the platform through a grant (plan decision 11, not built); a signed copy as a
document version; readiness and enabling construction (owner's word).
