# Cloud Code handoff — GORGONA business platform

## Current checkpoint — 2026-10-26: package M review fixes, locally verified

Review fixes on `codex/package-m-review-fixes` (code `44b8505`, [validation record](docs/plan/evidence/2026-10-26-m-review-fixes/VALIDATION.md)): all nine findings of the independent package M review are fixed. FIN-03 freezes transport drafts; a leg loaded short closes once its pickup is departed; migration **0081** keeps the loads of an invoiced order; money lines are bounded and exact (422); a concurrent pay component on the same id is compared; stop windows carry an end date; module text and grant label corrected. gates-1: focused **807 passed**, full **2628 passed, 4 skipped**. The `main` fast-forward (M6a..M8, the N plan, N1 and these fixes) is proposed to the owner and waits for their word, as do readiness and enabling transport. Next migration **0082**.

## Previous checkpoint — 2026-10-26: N1 broker authority and carrier profiles, locally verified

N1 on `codex/package-n1-broker-carriers` (code `a3d85d3`, [validation record](docs/plan/evidence/2026-10-26-n1-broker-carriers/VALIDATION.md)): migration **0080** keeps a business's broker authority and each carrier's profile as insert-only dated versions; eligibility for a date names every failing reason; right `transport.broker` (permissions version 10) for owners and managers, not delegable. gates-1 failed once on an unrelated catalog browser test (kept in the record); gates-2: focused **800 passed**, full **2621 passed, 4 skipped**. The owner approved one independent review of package M (2026-10-26); it found nine issues, two high (transport drafts editable through FIN-03; a short-loaded leg never closes); fixes come next, before N2. Readiness and `main` wait for the owner's word; transport stays not enableable. Next migration **0081**.

## Previous checkpoint — 2026-10-26: package M technically accepted locally, independent review open

M7b CI SUCCESS (run 40272483262). M8 on `codex/package-m8-acceptance`: TMS-01..03 PASS locally ([acceptance record](docs/plan/evidence/2026-10-26-m8-acceptance/ACCEPTANCE.md)), with a new end-to-end TMS-01 test in `6d5c86c` (one trip, two orders' loads, three stops in three zones, the truck replaced after loading, a partial delivery with refusals and damage, all history kept). Focused **735 passed**; full **2616 passed, 4 skipped**. The owner deferred the independent review (2026-10-26); it stays open. Readiness of the transport module and `main` wait for the owner's word; the module stays not enableable. Next migration **0080**.

## Previous checkpoint — 2026-10-26: M7b transport money on the screens, locally verified

Defect fixes CI SUCCESS (run 40261326556). M7b in `f44db22` on `codex/package-m7b-money-screens`: a company-wide owner or manager sets an order's rate, creates its FIN-03 customer invoice with extras and sees what is paid and open; on the trip page registers pay components (driver, dispatch fee, …) and accrues them; a branch-limited member and a delegate never see money. Focused **734 passed**; full **2615 passed, 4 skipped** ([validation](docs/plan/evidence/2026-10-25-m7b-money-screens/VALIDATION.md)). Next: M8 (package M acceptance; the independent review needs the owner's consent for an extra agent). Next migration **0080**.

## Previous checkpoint — 2026-10-25: package M defects D-01 and D-02 fixed, locally verified

M7a CI SUCCESS (run 40245557506). The two open defects are fixed in `099bc84` on `codex/package-m-defects`: the "night-time" workforce browser failure was the live test server's loop dying with WinError 10055 (socket buffers exhausted), so the harness now fails a test with the server's own error; a refused grant offer now stays visible after the list reloads. Focused **733 passed**; full **2614 passed, 4 skipped** ([validation](docs/plan/evidence/2026-10-25-m-defects/VALIDATION.md)). Next: M7b (money on the screens), then M8. Next migration **0080**.

## Previous checkpoint — 2026-10-25: M7a transport money through FIN-03, locally verified

M6b CI SUCCESS (run 40227240451). M7a in `b2998d5` on `codex/package-m7-transport-money` (ADR-0033): an
order's agreed rate is kept as versions and frozen by its one FIN-03 customer invoice (freight per mile or fixed
plus named extras, only when nothing is open); a trip's pay components (driver, owner-operator, dispatch fee)
are registered once and each accrues once as its own FIN-03 payable obligation on a closed trip; FIN-03 keeps
payments within the open balance. Finance rights only, never a delegate. Focused **730 passed**; full **2612
passed, 4 skipped** ([validation](docs/plan/evidence/2026-10-25-m7a-transport-money/VALIDATION.md)); full-1 lost a Chromium session in an unrelated browser test,
recorded. Next: M7b (money on the screens), then M8. Next migration **0080**.

## Previous checkpoint — 2026-10-25: M6b planning forms, fleet and carrier grants, locally verified

M6a CI SUCCESS (run 40177073619). M6b in `ba9cb64` on `codex/package-m6b-transport-forms`: owners and
managers enter and correct orders, plan and correct trips with stops in their own time zones and register
drivers and vehicles; the grant form offers a carrier transport actions with or without bookings, and the
carrier's dispatcher sees Transport only through such a grant, with only the granted forms. Orders are paged by
cursor. Real browser desktop and mobile with the database read back. Focused **723 passed**; full **2605
passed, 4 skipped** ([validation](docs/plan/evidence/2026-10-25-m6b-transport-forms/VALIDATION.md)). Next: M7 (money), then M8 (acceptance). Next migration **0079**.

## Previous checkpoint — 2026-10-25: M6a dispatch board and trip page, locally verified

`main` fast-forwarded to `ad21888` on the owner's word (CI SUCCESS, run 40165514386). M6a in `76519b8` on
`codex/package-m6a-transport-screens`: the Transport screen (owner or manager) lists every trip with status,
first and last window in the stop's own time zone and the current crew; the trip page shows stops, legs with
loaded, delivered, refused, damaged and open, assignments with periods and the event log, assigns or replaces
a crew member from a moment, records stop events with leg quantities (a retry after a lost answer records the
event once) and checks clearance. Trips, drivers and vehicles are paged by cursor and read to the end. Real
browser desktop and mobile with the database read back. Focused **721 passed**; full **2603 passed, 4 skipped**
([validation](docs/plan/evidence/2026-10-25-m6a-transport-screens/VALIDATION.md)). full-1 failed on two existing tests (a time-of-day-dependent workforce browser test
and a 401 on an expired test token); both recorded, not hidden. Next: M6b (order and trip forms, fleet,
transport rights in the grant screen, dispatcher navigation), then M7 and M8. Next migration **0079**.

## Previous checkpoint — 2026-10-24: BEAUTY-01 technically verified (owner's word)

Owner's word 2026-10-24: «BEAUTY-01 accept». In `84fb150` on `codex/beauty-01-readiness` the readiness registry
records BEAUTY-01 as `technically_verified` for code `8b6b37d` and schema 73 (exact-head CI 40040514685), citing
the package L acceptance (L-01..L-12 PASS), the L8 review, L9a, L9b and the [readiness record](docs/plan/evidence/2026-10-24-beauty-01-readiness/RECORD.md). Not a pilot
and not a production approval; no module becomes enableable; the salon profile stays `planned`. Focused **719
passed**; full **2601 passed, 4 skipped**. M5 CI green (40152895317). `main` still waits for the owner. Next:
package M slice M6 (screens); next migration **0079**.

## Previous checkpoint — 2026-10-24: M5 hours-of-service and telematics clearance locally verified

M5 in `1180d41` on `codex/package-m5-clearance` ([ADR-0032](docs/adr/0032-transport-clearance.md)): versioned hours-of-service profiles; duty
records and telematics pings as insert-only facts with source ids; clearance computed for a moment and never
positive on stale or unknown data (TMS-03); migration 0078. Focused **683 passed**; full **2600 passed, 4
skipped** ([validation](docs/plan/evidence/2026-10-24-m5-clearance/VALIDATION.md)). M4 CI green (40116278936). BEAUTY-01 readiness and `main` still wait for the
owner. Next migration **0079**; next slice M6 (screens).

## Previous checkpoint — 2026-10-24: M4 dispatcher scope on carrier grants locally verified

M4 in `4b6cd75` on `codex/package-m4-dispatcher-grants` ([ADR-0031](docs/adr/0031-transport-dispatcher-grants.md)): a carrier grants an independent
dispatcher transport work by action (read, plan, assign, events) through the ADR-0017 grants; fleet registration
is never delegated; revocation, delegate removal and expiry block the next command; earlier facts keep their
executor; permissions version 9, migration 0077. Focused **676 passed**; full **2593 passed, 4 skipped**
([validation](docs/plan/evidence/2026-10-24-m4-dispatcher-grants/VALIDATION.md)). M3 CI green (40081070256). BEAUTY-01 readiness and `main` still wait for the owner. Next
migration **0078**.

## Previous checkpoint — 2026-10-24: M3 stop events and partial delivery locally verified

M3 in `f6ac5f1` on `codex/package-m3-stop-events` ([ADR-0030](docs/adr/0030-transport-stop-events.md)): stop events are insert-only facts with a
source event id (a repeat changes nothing); partial delivery per leg, never beyond the plan or the load; the first
event starts the trip and freezes its plan; trucks can be replaced in transit (migration 0076). Focused
**660 passed**; full **2587 passed, 4 skipped** ([validation](docs/plan/evidence/2026-10-24-m3-transport-events/VALIDATION.md)). M2 CI green (40072696483). BEAUTY-01
readiness and `main` still wait for the owner. Next migration **0077**.

## Previous checkpoint — 2026-10-24: M2 transport assignments locally verified

M2 in `31bb854` on `codex/package-m2-assignments` ([ADR-0029](docs/adr/0029-transport-assignments-occupancy.md)): drivers, trucks and trailers have their own
lanes in the shared occupancy; an assignment holds its period, a replacement ends one period and starts the next
all or none, a busy truck changes nothing, an open assignment freezes the trip's span (migration 0075). Focused
**653 passed**; full **2580 passed, 4 skipped** ([validation](docs/plan/evidence/2026-10-24-m2-transport-assignments/VALIDATION.md)). M1 CI green (40065762379). A record slip was
found and is stated there: earlier records carried a stale `next_migration` 72. BEAUTY-01 readiness and `main`
still wait for the owner. Next migration **0076**.

## Previous checkpoint — 2026-10-24: package M started; M1 transport planning locally verified

Owner's word 2026-10-23: add the transport module, not enableable until acceptance, and start package M
([plan](docs/plan/PACKAGE_M_PLAN_2026-10-23.md)). M1 in `32bb8a4` on `codex/package-m1-planning`: the module `transport` (implemented, not
enableable; registry version 4, permissions version 8), migration 0074 with shipment orders, loads, trips, stops
in their own time zones and legs; a load is never over-planned. Focused **494 passed**; full **2571 passed, 4
skipped** ([validation](docs/plan/evidence/2026-10-23-m1-transport-planning/VALIDATION.md)). BEAUTY-01 readiness and `main` still wait for the owner. Next migration **0075**.

## Previous checkpoint — 2026-10-23: BEAUTY-01 gaps closed; zod security update; owner decides readiness and main

L9b CI SUCCESS (run 40034329906). A new high advisory (GHSA-mrhx-c7xc-m3w5, zod <4.6.6) found by the L9b
audit is fixed in `609159f`: zod 4.6.7 pinned; npm audit 0; focused **486 passed**, full **2563 passed, 4
skipped** ([validation](docs/plan/evidence/2026-10-23-l9-zod-security/VALIDATION.md)). Readiness and `main` wait for the owner's word. Next migration **0074**.

## Previous checkpoint — 2026-10-23: BEAUTY-01 gaps closed (L9a, L9b); owner decides readiness and main

L9a CI SUCCESS (run 40023359035). L9b in `00aadee` on `codex/package-l9b-commission-reversal` (migration 0073):
each refund reverses the commission's share of its service, cumulatively and once, with lineage; decision 85
fixed a defect (a visit settled by a prepaid unit earned no commission). Focused **486 passed**; full **2563
passed, 4 skipped** ([validation](docs/plan/evidence/2026-10-23-l9b-commission-reversal/VALIDATION.md)). The [acceptance record](docs/plan/evidence/2026-10-23-l8c-acceptance/ACCEPTANCE.md) now shows L-06 and L-07 PASS. Kept: the
L9b record was written after its code commit; npm audit found a new high advisory in zod (fixed in its own
commit). Readiness and `main` wait for the owner's word. Next migration **0074**.

## Previous checkpoint — 2026-10-23: L9a fee policy and no-shows locally verified (BEAUTY-01 gap L-06)

Owner's word 2026-10-23: close both BEAUTY-01 gaps, same process; readiness and `main` untouched. L8c CI
SUCCESS (run 39999584445). L9a in `8a90567` on `codex/package-l9a-fee-policy` (migration 0072): a versioned
fee policy, the no-show fact, billing computes the late-cancellation and no-show fee from the version in force
when the visit was booked; settings form and desk step. Focused **479 passed**; full **2556 passed, 4 skipped**
([validation](docs/plan/evidence/2026-10-23-l9a-fee-policy/VALIDATION.md)). Next: L9b (commission reversal after a refund), then the acceptance record update. Next
migration **0073**.

## Previous checkpoint — 2026-10-23: package L (BEAUTY-01) acceptance record written; owner decides readiness and main

L8c in `558b580` on `codex/package-l8c-acceptance` proves L-09 for the commission and prepaid tables (direct
SQL refused, the use guard holds, another company sees nothing). Focused **473 passed**; full **2550 passed,
4 skipped** ([validation](docs/plan/evidence/2026-10-23-l8c-acceptance/VALIDATION.md)). The [acceptance record](docs/plan/evidence/2026-10-23-l8c-acceptance/ACCEPTANCE.md) maps L-01..L-12: ten PASS, two PASS with a named
GAP — L-06 cancellation and no-show lines are not computed from a published policy; L-07 a refund does not
reverse the commission automatically. Readiness and the fast-forward of `main` wait for the owner's word.
Next migration **0072**.

## Previous checkpoint — 2026-10-23: L8b2 acceptance gaps locally verified; L8b1 CI green

L8b1 CI SUCCESS (run 39981532055, includes the spec fix for the L8a CI failure). L8b2 in `1e4368a` on
`codex/package-l8b2-acceptance-gaps`: the visit desk follows the business's modules (no write-off without
inventory, no billing without invoices, no commission without workforce); races of consumption, accrual and
redemption leave one write after an observed `pg_locks` wait; billing and prepaid refuse without invoices; a
room stage holds the room against staff reservations. The API proofs passed at once on existing code (no API
change). Focused **471 passed**; full **2548 passed, 4 skipped** ([validation](docs/plan/evidence/2026-10-23-l8b2-acceptance-gaps/VALIDATION.md)).
Next: L8c (BEAUTY-01 acceptance record). Next migration **0072**.

## Previous checkpoint — 2026-10-23: L8b1 review fixes R8-R15 locally verified; L8a CI failed on two specs

L8b1 in `ee7fc1b` on `codex/package-l8b1-review-fixes` fixes the remaining review findings R8-R15 (stage
revision, 50 stages on the site, reschedule checks every service, workforce and inventory gates on writes, plan
references and the first-save race, write-off place in the visit's branch, prepaid currency, the desk hides a
used balance). Focused **466 passed**; full **2543 passed, 4 skipped** ([validation](docs/plan/evidence/2026-10-23-l8b1-review-fixes/VALIDATION.md)).
**L8a CI run 39971712190 FAILED** on two browser specs L8a did not touch (`management.spec.ts` strict-mode
status, `service-catalog.spec.ts` slow row); the spec fix is its own commit on the L8b1 branch.
Next: L8b2 (races, module gates on the desk, room stage), then L8c (acceptance). Next migration **0072**.

## Previous checkpoint — 2026-10-23: package L reviewed; L8a review fixes R1-R7 locally verified

L7c CI SUCCESS (run 39901727848). One independent review of package L (owner's consent) found 15 defects
([review](docs/plan/evidence/2026-10-23-l8-review/REVIEW.md)); two high: a cancelled visit's paid fee accrued the full commission, and prices in 0- or
3-decimal currencies were billed at the wrong scale. L8a in `e3d45de` on `codex/package-l8a-review-fixes`
fixes R1-R7 (commission only for a confirmed visit, exact price conversion, free lines not billed, prepaid
units by matching line and whole worth, linked drafts frozen, recorded visits not moved or cancelled).
Focused **458 passed**; full **2535 passed, 4 skipped** ([validation](docs/plan/evidence/2026-10-23-l8a-review-fixes/VALIDATION.md)). Next: L8b (R8-R15, races,
module gates, room stage), then L8c (acceptance). Next migration **0072**.

## Previous checkpoint — 2026-10-23: L7c customer site, several services and stages, locally verified

L7b2b CI SUCCESS (run 39886335939). L7c in `1b00d01` on `codex/package-l7c-customer-site`: on the customer
site a guest books up to five services in one visit, each with its own add-ons, sees every line, the total,
the duration and the stages of a staged visit, and is offered only specialists who serve every service; real
browser desktop and mobile with the database read back. Focused **444 passed**; full **2521 passed, 4
skipped** ([validation](docs/plan/evidence/2026-10-23-l7c-customer-site/VALIDATION.md)). Next: L8 (BEAUTY-01 acceptance; owner's consent for the review, owner's
word for readiness and `main`). Next migration **0072**.

## Previous checkpoint — 2026-10-23: L7b2b prepaid screen and redemption, locally verified

L7b2a CI: the first run failed after UTC midnight (browser tests took today in UTC); fix `d2ac158` takes
today in the branch or business zone, CI SUCCESS (run 39879172808). L7b2b in `3d2658a` on
`codex/package-l7b2b-prepaid-screens`: a Prepaid screen lists and sells packages and certificates, and the
visit desk redeems a usable balance against an open visit invoice; real browser desktop and mobile with
the database read back. Focused **442 passed**; full **2520 passed, 4 skipped** ([validation](docs/plan/evidence/2026-10-23-l7b2b-prepaid-screens/VALIDATION.md)). Next:
L7c (customer site). Next migration **0072**.

## Previous checkpoint — 2026-10-22: L7b2a visit billing and commission screens, locally verified

L7b1 CI SUCCESS (run 39855981830). L7b2a in `56ab1ee` on `codex/package-l7b2a-billing-desk`: the visit desk
bills a visit, shows it paid and accrues the specialist's commission once; the Staff screen edits the
commission plan; real browser desktop and mobile with the database read back. Focused **439 passed**; full
**2517 passed, 4 skipped** ([validation](docs/plan/evidence/2026-10-22-l7b2a-billing-desk/VALIDATION.md)). Two load-only flakes kept with causes not proven. Next:
L7b2b (prepaid sale and redemption on screen). Next migration **0072**.

## Previous checkpoint — 2026-10-22: L7b1 visit desk, locally verified

L7a CI SUCCESS (run 39838977982). L7b1 in `d1c12ca` on `codex/package-l7b1-visit-desk`: on a confirmed
booking the visit desk completes the visit with actual quantities and writes its materials off; real
browser desktop and mobile with the database read back. Focused **436 passed**; full **2514 passed, 4
skipped** ([validation](docs/plan/evidence/2026-10-22-l7b1-visit-desk/VALIDATION.md)). Next: L7b2 (billing,
commission, prepaid on screen). Next migration **0072**.

## Previous checkpoint — 2026-10-22: L7a catalog screens, locally verified; Next.js security upgrade

L6 CI SUCCESS (run 39828302644). L7 designed ([design](docs/plan/PACKAGE_L7_DESIGN_2026-10-22.md), `259cfd2`).
L7a in `13919b3` on `codex/package-l7a-catalog-screens`: the Services screen edits the stages and the
materials of a service, equipment is a resource kind; real browser desktop and mobile. `npm audit`
flagged a critical Next.js advisory (GHSA-2464-fhr4-w9xw); `next` upgraded to 16.4.2 here — `main` and
earlier branches still pin 16.3.8 until merged. Focused **434 passed**; full **2512 passed, 4 skipped**
([validation](docs/plan/evidence/2026-10-22-l7a-catalog-screens/VALIDATION.md)). Next: L7b, the visit desk.
Next migration **0072**.

## Previous checkpoint — 2026-10-22: L6 prepaid packages and gift certificates, locally verified

L5 CI SUCCESS (run 39819887470). L6 designed ([design](docs/plan/PACKAGE_L6_DESIGN_2026-10-22.md), `7c7230a`) and
built in `affdaf3` on `codex/package-l6-prepaid` (migration 0071): a package or certificate is sold by an
invoice line on the prepayment liability and usable once paid; using it on a visit is a FIN-03 credit note
of the visit invoice, so the prepayment becomes revenue when the service is delivered. Focused **427
passed**; full **2510 passed, 4 skipped** ([validation](docs/plan/evidence/2026-10-22-l6-prepaid/VALIDATION.md)).
Next: L7, the screens. Next migration **0072**.

## Previous checkpoint — 2026-10-22: L5 commissions and tips, locally verified

L4 CI SUCCESS (run 39812765674). L5 designed ([design](docs/plan/PACKAGE_L5_DESIGN_2026-10-22.md), `12b64c9`;
decision 30 revised) and built in `7ff9249` on `codex/package-l5-commissions` (migration 0070): a commission
plan per specialist; once the visit invoice is fully paid, the commission is one FIN-03 payable accrual to
the payee; tips stay a liability on the visit invoice (never revenue) and are recorded with the
commission. Focused **388 passed**; full **2504 passed, 4 skipped**
([validation](docs/plan/evidence/2026-10-22-l5-commissions/VALIDATION.md)). Next: L6, packages and
certificates. Next migration **0071**.

## Previous checkpoint — 2026-10-22: L4 visit billing, locally verified

L3 CI SUCCESS after raising the CI job limit to 75 minutes (run 39805277086, 43 min; the first run was
cancelled at 45). L4 designed ([design](docs/plan/PACKAGE_L4_DESIGN_2026-10-22.md), `c45607f`) and built in
`0738b4a` on `codex/package-l4-billing` (migration 0069): a visit is billed as one FIN-03 invoice (its
services and add-ons, plus fee lines; a cancelled visit only fees); deposit and the rest are FIN-03
payments of it. Focused **378 passed**; full **2494 passed, 4 skipped**
([validation](docs/plan/evidence/2026-10-22-l4-billing/VALIDATION.md)). Next: L5, commissions and tips. Next
migration **0070**.

## Previous checkpoint — 2026-10-22: L3 visit completion and material consumption, locally verified

L2c CI SUCCESS (run 39783826823). L3 designed ([design](docs/plan/PACKAGE_L3_DESIGN_2026-10-22.md), `2402352`)
and built in `4ed11af` on `codex/package-l3-consumption` (migration 0068): recipes per service and add-on;
completing a started visit records planned and actual materials (booking right, branch scope); posting the
consumption writes them off once through STOCK-01 (inventory and finance rights). Focused **257 passed**;
full **2487 passed, 4 skipped** ([validation](docs/plan/evidence/2026-10-22-l3-consumption/VALIDATION.md)). Next:
L4, visit billing. Next migration **0069**.

## Previous checkpoint — 2026-10-22: L2c visits with several services, locally verified

L2b CI SUCCESS (run 39777287553). L2c in `c32a1b0` on `codex/package-l2c-visits` (no migration): one
booking holds several services in order (`extra_lines` after the first); the composition rules apply
across the visit; one artist serves the whole visit; staff, the hold API and guests book it. Focused
**234 passed**; full **2479 passed, 4 skipped**
([validation](docs/plan/evidence/2026-10-22-l2c-visits/VALIDATION.md)). L2 (occupancy, guests, visits) is
complete; next: L3, visit completion and material consumption. Next migration **0068**.

## Previous checkpoint — 2026-10-22: L2b guests book staged services, locally verified

L2a CI SUCCESS (run 39765610640). L2b in `ca44785` on `codex/package-l2b-guest-stages` (no migration):
guests see a staged start only when the artist is free in their working stages and a chair, room or
processor is free for each stage that needs one; the hold places every stage, all or nothing; the web
quote parser accepts version 2 with stages. Focused **219 passed**; full **2464 passed, 4 skipped**
([validation](docs/plan/evidence/2026-10-22-l2b-guest-stages/VALIDATION.md)). Next: L2c, visits with several
services. Next migration **0068**.

## Previous checkpoint — 2026-10-22: L2a stage-by-stage occupancy locally verified

L1 CI SUCCESS (run 39758206502; package L plan run 39758206876). L2 designed under the owner's full
delegation ([design](docs/plan/PACKAGE_L2_DESIGN_2026-10-22.md), `f1403eb`). L2a in `edd0849` on
`codex/package-l2-occupancy` (migration 0067): a staged visit holds each resource only for its stages,
so the specialist is free while a colour develops and the chair stays held; all or nothing; chair,
room or equipment named or found. Staff booking, reschedule and the hold API handle staged services;
the customer site refuses them until L2b. 20 new tests; focused **214 passed**; full **2459 passed, 4
skipped** ([validation](docs/plan/evidence/2026-10-22-l2a-stage-occupancy/VALIDATION.md)). Next: L2b.
Next migration **0068**.

## Previous checkpoint — 2026-10-22: package L started; L1 service stages and equipment locally verified

Package L (BEAUTY-01, build order of stage 3, not a separate launch) planned under the owner's full
delegation ([plan](docs/plan/PACKAGE_L_PLAN_2026-10-22.md), `5eb534c`). L1 in `7ce60ef` on
`codex/package-l1-stages` (migration 0066): a service variant may have ordered stages (active,
processing, finish) with minutes and resource kinds; its duration is their sum (checked in SQL);
`equipment` is a resource kind; a variant without stages quotes exactly as before. Booking still holds
one resource per visit until L2. 21 new tests; focused **133 passed**; full **2439 passed, 4 skipped**
([validation](docs/plan/evidence/2026-10-22-l1-service-stages/VALIDATION.md)). Next: L2, stage-by-stage
occupancy. Next migration **0067**.

## Previous checkpoint — 2026-10-22: FIN-02 K-05 and K-12 PASS after K6

FIN-02 stays `technically_verified`; its record now names the reviewed K6r source `2eb6cf7`, schema
65: events lost on the way are fetched back by a read-only reconciler with the same facts, every run is
recorded, a failing event is retried and then parked until a finance user releases it
([K6 acceptance](docs/plan/evidence/2026-10-22-fin-02-k6-acceptance/ACCEPTANCE.md)). Evidence: the real sandbox
run with lost webhooks (K6c), one independent review with its fixes (K6r), CI SUCCESS on every K6 head
(K6r run 39732441848). Registry commit `47e60c5` on `codex/package-k6s-fin02-record`; full **2415
passed, 4 skipped**. Limit: the product's HTTP client still needs one call with a restricted test key
that only the owner may create. No live mode, no production approval. Next migration **0066**.

## Previous checkpoint — 2026-10-22: K6 reviewed, CI green; K6r review fixes locally verified

K6a, K6b1, K6b2 and K6c published for CI on the owner's word («Да, и то и другое»), no PR: CI SUCCESS
on all four heads (runs 39724421746, 39724425326, 39724428029, 39724431070). One independent read-only
review: APPROVE with conditions, no Critical or High ([REVIEW](docs/plan/evidence/2026-10-22-k6-review/REVIEW.md)).
K6r fixes R1–R8 in `2eb6cf7` on `codex/package-k6r-review-fixes` (migration 0065): focused **700
passed**; full **2415 passed, 4 skipped** ([validation](docs/plan/evidence/2026-10-22-k6r-review-fixes/VALIDATION.md)).
The real sandbox run K6c passed ([validation](docs/plan/evidence/2026-10-21-k6c-stripe-sandbox/VALIDATION.md)).
Next: the FIN-02 record and acceptance update (K-05, K-12). Next migration **0066**.

## Previous checkpoint — 2026-10-21: K6b2 delivery source and stalled operations on the screen

Code `0af2a46`, local branch `codex/package-k6b2-screen`, parent `9435e7f` (K6b1). Each delivery names
how it arrived (signed webhook or fetched by reconciliation); an operation without a final event for
over 24 hours is marked. Focused **676 passed**; full **2398 passed, 4 skipped**; npm audit NOT TESTED
(registry timeout, no dependency changed). Next: K6c, the real sandbox run.
[Validation](docs/plan/evidence/2026-10-21-k6b2-screen/VALIDATION.md).

## Previous checkpoint — 2026-10-21: K6b1 lost provider events reconciled from the Stripe API

Code `73f5c45`, local branch `codex/package-k6b-event-backfill`, parent `73570bd` (K6b detailed
decisions). A reconciler of one platform namespace lists each admitted connection's events from the
Stripe API and records them through the same inbox as webhooks (same facts; provenance
`stripe_api_v1` on the attestation; every run recorded, migration 0064; retries 1, 2, 4 s then a
visible failure). Tested against a local fake Stripe API; the real sandbox run is K6c. Focused
**673 passed**; full **2395 passed, 4 skipped**. FIN-02 unchanged (K-05/K-12 PARTIAL until K6c).
Next migration **0065**. [Validation](docs/plan/evidence/2026-10-21-k6b-event-backfill/VALIDATION.md).

## Previous checkpoint — 2026-10-21: K6a bounded retries and parked provider events (FIN-02 gaps)

Code `2f577bc`, local branch `codex/package-k6a-bounded-retries`, parent `8b8f8a3` (K6 design,
owner: «1» and «Да, все умолчания»). The receipt worker no longer lets one failing event stop its
batch or retry forever: failures are recorded (migration 0063), retried after 1, 2, 4, 8 minutes and
parked after 5; a finance user presses **Try again** with a note. Every order of a payment and its
refund (720) converges (K-05). Focused **599 passed**; full **2354 passed, 4 skipped**. FIN-02 stays
`technically_verified` with K-05/K-12 PARTIAL until K6b (event backfill) and K6c (sandbox run). Next
migration **0064**. [Validation](docs/plan/evidence/2026-10-21-k6a-bounded-retries/VALIDATION.md),
[K6 design](docs/plan/PACKAGE_K6_DESIGN_2026-10-21.md).

## Previous checkpoint — 2026-10-21: STOCK-01 technically verified; inventory may be enabled

Code `3f68e3f`, local branch `codex/package-stock01-readiness`, parent `1a8a180` (`main`, CI SUCCESS run
39536393894). On the owner's «ok» the readiness registry records **STOCK-01 `technically_verified`** for
code `ea74bec`, schema 62, citing the [2026-10-15 acceptance](docs/plan/evidence/2026-10-15-stock-01-acceptance/ACCEPTANCE.md)
(J-01–J-14 PASS) and the [readiness record](docs/plan/evidence/2026-10-20-stock-01-readiness/RECORD.md). The
`inventory` module follows STOCK-01 and **may now be enabled** with `finance`; nothing is enabled
automatically. Limits unchanged (no customer-owned goods, batches, serial numbers, purchase orders or
multi-warehouse WMS); no production approval. Focused **261 passed**; full **2329 passed, 4 skipped**.

## Previous checkpoint — 2026-10-20: FIN-02 technically verified (K5c)

Code `ea74bec66808f217f7ea56370b9292b4844f7d2b`, local branch `codex/package-k5c-fin02-readiness`, parent
`2b640e2` (K5r, CI SUCCESS run 39523031370). On the owner's delegation («делай, как ты считаешь нужным…
я доверяю тебе») the readiness registry records **FIN-02 `technically_verified`** for code `b4e69e8`,
schema 62: Stripe Connect test mode, USD, one admitted connection; K-01–K-14 PASS except K-05 and K-12
PARTIAL (no provider retrieval, reconciliation or dead-letter queue); no live mode and no production
approval. Focused **827 passed**; full **2328 passed, 4 skipped**. STOCK-01 stays `planned`.
[Acceptance](docs/plan/evidence/2026-10-20-fin-02-acceptance/ACCEPTANCE.md),
[handoff](docs/plan/NEXT_AGENT_AFTER_FIN02_2026-10-20.md), [prompt](docs/plan/NEXT_AGENT_AFTER_FIN02_PROMPT_2026-10-20.md).

## Previous checkpoint — 2026-10-20: K5r fixes of the K5 final review locally verified

Source `b4e69e82152961380d21761c9a100515ea1645d1`, local branch `codex/package-k5r-review-fixes`, parent `ec25a1f`. One independent
review of K5a-fix, K0b and K5b (owner's «Да, запусти») found no Critical or High issue; K5r fixes the
two Medium and the Low findings: stored operation keys with an index for the money checks (measured
~390 ms -> 0.02 ms at 100k events; an expression index was found unusable under FORCE RLS), a
suspension is final, the refund cap counts linked refunds, direction-aware "names the ID", a worker
that survives a failed batch, plus web and refusal details. Migrations 0061 (K) and 0062 (H); next
0063. Focused **787 passed in 817.60s (0:13:37)**; full **2327 passed, 4 skipped in 1907.66s
(0:31:47)**; static/web/build PASS. Not published. FIN-02 and STOCK-01 stay `planned` until the FIN-02
acceptance record. [Review](docs/plan/evidence/2026-10-20-k5-final-review/REVIEW.md),
[validation](docs/plan/evidence/2026-10-20-k5r-review-fixes/VALIDATION.md).

## Previous checkpoint — 2026-10-20: K5-CI SUCCESS after K0c

Branch `codex/package-k5b-open-findings` published for CI only (owner's trust, no PR, no `main`); exact head `e03c678` CI SUCCESS, run 39502582514, including the production image build. FIN-02 stays `planned` until its acceptance record (K-01–K-14) and one independent review of K5a-fix, K0b and K5b. [K5 plan](docs/plan/PACKAGE_K5_PLAN_2026-10-19.md).

## Previous checkpoint — 2026-10-20: K0c real Stripe sandbox events PASS

On `dd013fd` (no source change), owner-delegated («ты сам все делай»): Stripe sandbox
`acct_1UJtGO0mkpVWlKYX` as the Connect platform, connected test account `acct_1USjOo0mkpWSHVnd`, test
mode only. Real signed events (success, failure, refund) reached the local ingress through
`stripe listen`, were attested and decided; one payment (20.00) and one refund (1.00) were applied with
provider provenance; a Stripe resend made no second effect; a suspension refused the next deliveries
(400, nothing stored). E-02–E-05 PASS; the signing secret stayed in memory (0 in every log). Next:
K5-CI (exact-head CI; publishing needs the owner's word) and K5c (the owner's readiness decision for
FIN-02, still `planned`). [Validation](docs/plan/evidence/2026-10-20-k0c-stripe-sandbox/VALIDATION.md).

## Previous checkpoint — 2026-10-20: K5b open review findings and manual editor dates locally verified

Source `58cf561d0f2d065ad44dac850182fdd61d3fae20`, local branch `codex/package-k5b-open-findings`, parent `1b89958` (the owner postponed
K0c; FIN-02 stays planned). 0059 (K): inbox index by connection (finding 6); only the receipt writer
inserts events and deliveries, the runtime reads (finding 9, IR-03). 0060 (H): a provider link needs
the enabled finance workflow in SQL (finding 8); the link date window calls `pg_catalog.abs`
(finding 15). A Stripe charge counts `amount_captured` (finding 12). Manual financial editors default
their dates to today in the business time zone, not UTC. Red-1 on the old code: 7 failed for the
expected reasons. Focused **775 passed in 841.46s (0:14:01)**; full **2315 passed, 4 skipped in
2410.31s (0:40:10)**; static/web/build PASS; runtime audit 0. Not published; next migration 0061.
FIN-02/STOCK-01 planned; ADR-0026/0027 Proposed. Owner decision the same day: production is **all 39
directions at once** (master plan, top). K0c resumed: the Stripe CLI is authorized for the owner's
sandbox; Connect still has to be enabled there by the owner.
[Validation](docs/plan/evidence/2026-10-20-k5b-open-findings/VALIDATION.md),
[handoff](docs/plan/NEXT_AGENT_PACKAGE_K5B_2026-10-20.md), [prompt](docs/plan/NEXT_AGENT_PACKAGE_K5B_PROMPT_2026-10-20.md).

## Previous checkpoint — 2026-10-20: K0b connection admission and receipt processes locally verified

Source `1eacc1d73c4d13a759be95084d994ef1be6cf4fe`, local branch `codex/package-k0b-entry-points`, parent `4e0665c` (K0a design and the
owner's answers: «i trust you», all defaults). 0057 adds the owner-only, append-only admission of a
receipt connection (test access or suspension, test mode, USD, charge and refund flags); receipts,
worker decisions and provider money need the latest revision to be test access, under one advisory
lock per connection. 0058 gates provider payments and links in H. New processes:
`python -m gorgona_booking.providers.ingress_main` (127.0.0.1 only, keys from named variables) and
`python -m gorgona_booking.providers.worker_main`; owner command `gba-db admit-receipt-connection`.
Found and fixed: uvicorn's raw-path access log carried the ingress ID. 58 new cases; focused
**623 passed in 703.66s (0:11:43)**; full **2308 passed, 4 skipped in 2316.92s (0:38:36)**; static/mypy 340/web/build PASS; runtime audit 0;
development audit 5 high (existing). K0c (the owner's real Stripe test run) next. Not published;
next migration 0059. FIN-02/STOCK-01 planned; ADR-0026/0027 Proposed.
[Validation](docs/plan/evidence/2026-10-20-k0b-entry-points/VALIDATION.md),
[handoff](docs/plan/NEXT_AGENT_PACKAGE_K0B_2026-10-20.md), [prompt](docs/plan/NEXT_AGENT_PACKAGE_K0B_PROMPT_2026-10-20.md).

## Previous checkpoint — 2026-10-19: K5a-fix of verified review findings locally verified

Source `76f776447b0b4fcb1699047aa2fa496531ee6b34`, local branch `codex/package-k5a-review-fixes`, parent `59c54a0`.
The K5a review's verified findings, by the owner's decisions of 2026-10-19: a manual payment
cannot name a provider operation whose money counts; a refund failure and success conflict in
either order; the counter counts only authorized requests; only a compromised key blocks money; a
voided manual payment no longer blocks; a revocation waits for applications (ledger lock); SQL
refusals are typed; the refund cap uses effective amounts; names ignore case and invisible
characters; the apply form defaults to today in the business zone (migrations 0055 K, 0056 H).
18 new cases. Focused **527 passed in 577.17s (0:09:37)**; full **2250 passed, 4 skipped in 1868.37s (0:31:08)**. K5a-fix and K3b published for CI
only, no PR (`7b08507` run 39371433810 SUCCESS; `c2a891d` SUCCESS). Findings 6, 8, 9, 12, 15 open.
FIN-02/STOCK-01 planned; ADR-0026/0027 Proposed. main=fedd0f1, published J=df88c20. Next 0057.
[Validation](docs/plan/evidence/2026-10-19-k5a-review-fixes/VALIDATION.md), [handoff](docs/plan/NEXT_AGENT_PACKAGE_K5A_FIX_2026-10-19.md), [prompt](docs/plan/NEXT_AGENT_PACKAGE_K5A_FIX_PROMPT_2026-10-19.md).

## Previous checkpoint — 2026-10-19: K3b links of earlier manual payments locally verified

Source `8bb2eb43e16a05092065a09bee8082733737fe1f`, local branch `codex/package-k3b-provider-links`, parent `199eada`.
By the owner's decisions of 2026-10-19: an operation whose ID an earlier manual payment names is
`needs_link`; a finance user links it to that payment (amount, currency, direction exactly equal,
dates at most 3 days apart, one to one); no journal is written, the link is append-only (migration
0054, H) and a linked operation is never applied; a void of the linked payment returns it to
review. Real desktop and mobile browser with axe. 20 new cases. Focused **424 passed in 622.38s
(0:10:22)**; full **2232 passed, 4 skipped in 2272.05s (0:37:52)**. K3b not published; K4a and
K4b branches published for CI only (both SUCCESS).
FIN-02/STOCK-01 planned; ADR-0026/0027 Proposed. main=fedd0f1, published J=df88c20. Next 0055.
[Validation](docs/plan/evidence/2026-10-19-k3b-provider-links/VALIDATION.md), [handoff](docs/plan/NEXT_AGENT_PACKAGE_K3B_2026-10-19.md), [prompt](docs/plan/NEXT_AGENT_PACKAGE_K3B_PROMPT_2026-10-19.md).

## Previous checkpoint — 2026-10-18: K4b provider review, attention and runbook locally verified

Source `60a12e14d461ef3d9a9b6dbca8e35c25f402055d`, local branch `codex/package-k4b-provider-review`, parent `45f15df`.
Second K4 slice, by the owner's decisions of 2026-10-18: each provider operation opens a detail
of its events, decisions and deliveries with the differing fields and both values; a Needs
attention view lists undecided events and decisions without an operation, and a finance user
acknowledges the latter with a required note (migration 0053, append-only); counters per company;
an English runbook. Real desktop and mobile browser with axe. 20 new cases. Focused **345 passed
in 502.38s (0:08:22)**; full **2212 passed, 4 skipped in 2388.14s (0:39:48)**. K4b not published;
K4a branch `codex/package-k4a-provider-screen` (`09d8187`) published for CI only, run
39185366331 SUCCESS.
FIN-02/STOCK-01 planned; ADR-0026/0027 Proposed. main=fedd0f1, published J=df88c20. Next 0054.
[Validation](docs/plan/evidence/2026-10-18-k4b-provider-review/VALIDATION.md), [handoff](docs/plan/NEXT_AGENT_PACKAGE_K4B_2026-10-18.md), [prompt](docs/plan/NEXT_AGENT_PACKAGE_K4B_PROMPT_2026-10-18.md).

## Previous checkpoint — 2026-10-18: K4a finance screen for provider operations locally verified

Source `374f60c2adb04060bd69c526dbf14b687c52698c`, local branch `codex/package-k4a-provider-screen`, parent `c1ff170`.
First K4 slice, by the owner's decisions of 2026-10-18: in Financial documents a finance user
sees the book's provider operations and connections, registers a connection's clearing account
once after a confirmation step, and applies an observed operation from its reserved settlement
with the amount, currency and date from the provider; a later conflict shows a manual review
marker; refusals are plain, the input is kept and a lost response is retried safely. Real desktop
and mobile browser with axe. No migration, 10 new cases. Focused **352 passed in 419.21s
(0:06:59)**; full **2192 passed, 4 skipped in 1782.61s (0:29:42)**. Not published.
FIN-02/STOCK-01 planned; ADR-0026/0027 Proposed. main=fedd0f1, published J=df88c20. Next 0053.
[Validation](docs/plan/evidence/2026-10-18-k4a-provider-screen/VALIDATION.md), [handoff](docs/plan/NEXT_AGENT_PACKAGE_K4A_2026-10-18.md), [prompt](docs/plan/NEXT_AGENT_PACKAGE_K4A_PROMPT_2026-10-18.md).

## Previous checkpoint — 2026-10-17: K3a observed provider money into H locally verified

Source `2f91368271458d6f20030e43ab9409751c3fa62d`, local branch `codex/package-k3a-provider-money`, parent `1476108`.
First K3 slice, by the owner's decisions of 2026-10-17: a finance user applies one observed
provider payment or refund to a reserved H settlement; the database takes amount, currency (USD
only), date and reference from the attested and decided facts, posts to the connection's
registered clearing account and records the provenance in the same transaction; one operation
moves money at most once; voids and corrections stay the human H paths. Migrations 0051–0052,
28 new cases. Focused **777 passed in 626.41s (0:10:26)**; full **2182 passed, 4 skipped in
1723.33s (0:28:43)**; a first full gate failed on the strict web payment contract (kept in the
record). Not published.
FIN-02/STOCK-01 planned; ADR-0026/0027 Proposed. main=fedd0f1, published J=df88c20. Next 0053.
[Validation](docs/plan/evidence/2026-10-17-k3a-provider-money/VALIDATION.md), [handoff](docs/plan/NEXT_AGENT_PACKAGE_K3A_2026-10-17.md), [prompt](docs/plan/NEXT_AGENT_PACKAGE_K3A_PROMPT_2026-10-17.md).

## Previous checkpoint — 2026-10-17: K2a receipt decisions without money locally verified

Source `6e9bbfc74a09a5d472aaff25328356d6f71e8706`, local branch `codex/package-k2a-receipt-decisions`, parent `b6c8040`.
First K2 slice, by the owner's decisions of 2026-10-17: a separate `gba_receipt_worker` group turns
each attested receipt into one permanent decision (`observed` or `needs_review`) linked to one
provider operation; leases with fencing stop duplicate and expired workers; every conflict goes
to manual review; nothing touches the ledger, settlements or obligations. Migration 0050, 59 new
cases. Focused **571 passed in 478.99s (0:07:58)**; full **2154 passed, 4 skipped in 1765.52s
(0:29:25)**; a first focused gate failed (kept in the record). Not published.
FIN-02/STOCK-01 planned; ADR-0026/0027 Proposed. main=fedd0f1, published J=df88c20. Next 0051.
[Validation](docs/plan/evidence/2026-10-17-k2a-receipt-decisions/VALIDATION.md), [handoff](docs/plan/NEXT_AGENT_PACKAGE_K2A_2026-10-17.md), [prompt](docs/plan/NEXT_AGENT_PACKAGE_K2A_PROMPT_2026-10-17.md).

## Previous checkpoint — 2026-10-17: K1k TRUNCATE guard and random route IDs locally verified

Source `a5f21e41f550d5d07e428c644e9f718082b3f619`, local branch `codex/package-k1k-truncate-guard`, parent `ae9e1e2`.
Closes independent-review findings IR-09 and the default part of IR-08: migration 0049 refuses
TRUNCATE (also a cascade) of all six receipt tables for the owner and superusers, and route IDs
default to a random UUID. 18 new cases. Focused **512 passed in 443.01s (0:07:23)**; full
**2095 passed, 4 skipped in 1656.78s (0:27:36)**. Not published.
FIN-02/STOCK-01 planned; ADR-0026/0027 Proposed. main=fedd0f1, published J=df88c20. Next 0050.
[Validation](docs/plan/evidence/2026-10-17-k1k-truncate-guard/VALIDATION.md), [handoff](docs/plan/NEXT_AGENT_PACKAGE_K1K_2026-10-17.md), [prompt](docs/plan/NEXT_AGENT_PACKAGE_K1K_PROMPT_2026-10-17.md).

## Previous checkpoint — 2026-10-17: K1j revocation record locally verified

Source `201847856aa768bbeb25751d5b219e154383c293`, local branch `codex/package-k1j-revocation-record`, parent `84bc4d7`.
Closes independent-review finding IR-07: migration 0048 makes a revocation of a receipt
connection or verification config name its reason (rotation, compromise, retired) and records
when and by which login; the record is permanent, earlier revocations keep an empty record, and
attestations and configs record the login behind `SET ROLE`. 21 new cases. Focused **494 passed
in 358.27s (0:05:58)**; full **2077 passed, 4 skipped in 1598.78s (0:26:38)**. Not published.
FIN-02/STOCK-01 planned; ADR-0026/0027 Proposed. main=fedd0f1, published J=df88c20. Next 0049.
[Validation](docs/plan/evidence/2026-10-17-k1j-revocation-record/VALIDATION.md), [handoff](docs/plan/NEXT_AGENT_PACKAGE_K1J_2026-10-17.md), [prompt](docs/plan/NEXT_AGENT_PACKAGE_K1J_PROMPT_2026-10-17.md).

## Previous checkpoint — 2026-10-17: K1i stock posting plans independent of statistics locally verified

Source `42ead59a3ff975d0daa6ee294af6b34b2b8ce5ff`, local branch `codex/package-k1i-stock-plan-stability`, parent `0760553`.
Fixes the K1h finding: with statistics that did not describe a company, one stock document's
checks could read the whole history. Migration 0047 makes the history keys unusable for a company
predicate, reads source documents by key and drops history-key equalities from the line check; the
inventory guard approves the new indexes. 5 new cases; at most 1 row per stock-table node with a
100,016-row history (red: 100,031). Focused **473 passed in 329.46s (0:05:29)**; full **2056 passed,
4 skipped in 1556.26s (0:25:56)**; a first full run failed (kept in the record). Not published.
FIN-02/STOCK-01 planned; ADR-0026/0027 Proposed. main=fedd0f1, published J=df88c20. Next 0048.
[Validation](docs/plan/evidence/2026-10-17-k1i-stock-plan-stability/VALIDATION.md), [handoff](docs/plan/NEXT_AGENT_PACKAGE_K1I_2026-10-17.md), [prompt](docs/plan/NEXT_AGENT_PACKAGE_K1I_PROMPT_2026-10-17.md).

## Previous checkpoint — 2026-10-17: K1g receipt guard additions locally verified

Source `4401a2e7bcdc716eaa5664285c0ca383ddf77163`, local branch `codex/package-k1g-guard-additions`, parent `af26f1d`.
Closes independent-review finding IR-05: the receipt schema guard now checks group membership
topology, K table shape and ACLs, function ACLs and the RLS context functions. No migration.
10 new cases. Focused **468 passed in 294.65s (0:04:54)**; full **2052 passed, 4 skipped in
2011.34s (0:33:31)**; a first full run failed once on the pre-existing, near-limit
`test_stock_scale` timing check (kept in the record). Not published.
FIN-02/STOCK-01 planned; ADR-0026/0027 Proposed. main=fedd0f1, published J=df88c20. Next 0047.
[Validation](docs/plan/evidence/2026-10-17-k1g-guard-additions/VALIDATION.md), [handoff](docs/plan/NEXT_AGENT_PACKAGE_K1G_2026-10-17.md), [prompt](docs/plan/NEXT_AGENT_PACKAGE_K1G_PROMPT_2026-10-17.md).

## Previous checkpoint — 2026-10-17: K1f bootstrap hardening locally verified

Source `3e18c938a505bbb4583778cdf40df0e7bed2aceb`, local branch `codex/package-k1f-bootstrap-hardening`, parent `be97fbd`.
Closes independent-review finding IR-06: bootstrap refuses equal owner/runtime/writer passwords,
`gba-db bootstrap` can create the writer login (`GBA_RECEIPT_WRITER_ROLE`/`_PASSWORD`), and
migrations refuse, applying nothing, before bootstrap created `gba_runtime`/`gba_receipt_writer`.
No migration. 8 new cases. Focused **458 passed in 408.78s (0:06:48)**; full **2042 passed,
4 skipped in 3100.84s (0:51:40)**; static/mypy 315/web/build PASS; runtime audit 0; existing
development audit 5 high FAIL. K1f not published. K1e branch CI: one transient image-build
failure (run 38991120703), re-run 38996263458 SUCCESS on `e5279cb` (same tree as `be97fbd`).
FIN-02/STOCK-01 planned; ADR-0026/0027 Proposed. main=fedd0f1, published J=df88c20. Next 0047.
[Validation](docs/plan/evidence/2026-10-17-k1f-bootstrap-hardening/VALIDATION.md),
[handoff](docs/plan/NEXT_AGENT_PACKAGE_K1F_2026-10-17.md), [prompt](docs/plan/NEXT_AGENT_PACKAGE_K1F_PROMPT_2026-10-17.md).

## Previous checkpoint — 2026-10-16: K1e raw HTTP ingress locally verified

Source `eb46748fa7446754e96e9290ce5261607ae45ce0`, local branch `codex/package-k1e-http-ingress`, parent `2d434bff8081e03d38765caa0b61f5df006dde27`.
A separate writer-process ASGI application serves one route, `POST /v1/provider-events/stripe/{ingress_id}`:
bounded raw body, one signature header, 200 only after the commit, one byte-identical 400 for
every refusal, 503 + Retry-After for storage, timeouts, guards and a full concurrency quota.
The owner-approved independent read-only review of K1a–K1d found 0 High, 2 Medium (both
addressed: cheap unlocked pre-signature path, uniform refusals) and 9 Low/Note (recorded).
No migration. 46 new cases. Focused **450 passed in 273.91s (0:04:33)**; full
**2034 passed, 4 skipped in 1700.22s (0:28:20)**; static/mypy 314/web 114/build PASS; runtime
audit 0 PASS; existing development audit 5 high FAIL; 4 container/tenant-site skips NOT TESTED.
No process entry point, admission, worker or money. Human review, K CI and real provider
NOT TESTED/BLOCKED. FIN-02/STOCK-01 planned; ADR-0026/0027 Proposed. Update 2026-10-16: the
owner authorized pushing branch `codex/package-k1e-http-ingress` only (no PR, no merge); old
clean worktrees and stopped test clusters were removed to free disk space.
main=fedd0f1, published J=df88c20. Next 0047.
[Validation](docs/plan/evidence/2026-10-16-k1e-http-ingress/VALIDATION.md),
[review](docs/plan/evidence/2026-10-16-k1e-http-ingress/INDEPENDENT_REVIEW_K1A_K1D.md),
[handoff](docs/plan/NEXT_AGENT_PACKAGE_K1E_2026-10-16.md), [prompt](docs/plan/NEXT_AGENT_PACKAGE_K1E_PROMPT_2026-10-16.md).

## Previous checkpoint — 2026-10-16: K1d verification authority and routing locally verified

Source `e9c86bfbd1d22e00ea66a96637cd98e9a58f27b4`, local branch `codex/package-k1d-receipt-routing`, parent `46ab31dd6f41ae820a85a09f19fd5812584fc89d`.
Migration 0046 adds owner-provisioned, versioned verification configs (opaque key reference,
one active version, one-way revocation) and writer-only routes from an ingress ID to company
and connection IDs. One entry point, `receive_routed_receipt`, replaces caller-supplied scope.
60 new cases, 28 K1c cases ported. Focused **404 passed in 267.91s (0:04:27)**; full
**1988 passed, 4 skipped in 1970.01s (0:32:50)**; static/mypy 312/web 114/build PASS; runtime
audit 0 PASS; existing development audit 5 high FAIL; 4 container/tenant-site skips NOT TESTED.
Finding: a validated key added by the migration owner did not see rows hidden by forced row
security; 0046 checks under a temporary owner policy. No HTTP, admission, worker or money.
Independent review, K CI and real provider NOT TESTED/BLOCKED. FIN-02/STOCK-01 planned;
ADR-0026/0027 Proposed. K local only; main=fedd0f1, published J=df88c20. Next 0047.
[Validation](docs/plan/evidence/2026-10-16-k1d-receipt-routing/VALIDATION.md),
[handoff](docs/plan/NEXT_AGENT_PACKAGE_K1D_2026-10-16.md), [prompt](docs/plan/NEXT_AGENT_PACKAGE_K1D_PROMPT_2026-10-16.md).

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
[Validation](docs/plan/evidence/2026-10-16-k1c-receipt-attestations/VALIDATION.md),
[reuse](docs/plan/evidence/2026-10-16-k1c-receipt-attestations/ARCHITECTURE_REUSE.md),
[handoff](docs/plan/NEXT_AGENT_PACKAGE_K1C_2026-10-16.md),[prompt](docs/plan/NEXT_AGENT_PACKAGE_K1C_PROMPT_2026-10-16.md).

## Previous checkpoint — 2026-10-15: K1b schema guard review locally verified

Local source `db96f005442201428700995c09f028e1b6da08c0` on `codex/package-k1b-guard-review`, base `84d4177e97ebc16e1743dcb995abf54c1b81269d`. Six schema conformance gaps
were reproduced before the correction; the existing guard now binds approved trigger
identity/shape, shared immutable source, FK parent schema and column PUBLIC privileges.
Focused **316 passed in 106.89s (0:01:46)**; full **1890 passed, 4 skipped in 1454.00s (0:24:14)**; static/build/web114 PASS.
No migration/dependency/ingress/worker/money authority. FIN-02/STOCK-01 planned;
ADR0026/0027 Proposed; full K acceptance/independent review/exact K CI NOT TESTED.
Runtime npm audit0 PASS, existing development5high FAIL;4 container/external skips.
K remains local; main=fedd0f1 and published J=df88c20 unchanged.
[Validation](docs/plan/evidence/2026-10-15-k1b-guard-review/VALIDATION.md),
[review](docs/plan/evidence/2026-10-15-k1b-guard-review/REVIEW.md),
[handoff](docs/plan/NEXT_AGENT_PACKAGE_K1B_REVIEW_2026-10-15.md),
[prompt](docs/plan/NEXT_AGENT_PACKAGE_K1B_REVIEW_PROMPT_2026-10-15.md).

## Previous checkpoint — 2026-10-15: K1b receipt storage locally verified; not published

K1b source `543b73221ac1dd0aa738bd8cf33dd468366ef27a`, `codex/package-k1b-inbox`, base `ffb176b3cc4bd83637eff29246f6045e0705b9d3`.
Migration0044 adds owner-provisioned `not_admitted` receipt bindings and an append-only
typed event/delivery inbox. Equal facts replay safely; conflicting facts never overwrite
history. Three races observe the intended pg_locks waits.40 new tests PASS.
Static/build/web114 PASS; focused **252 passed in 79.86s (0:01:19)**;
full **1884 passed, 4 skipped in 1502.59s (0:25:02)**, fresh disposable PostgreSQL18.6.
No HTTP route, global routing grant, worker, operational admission or financial effect.
Complete K-01–K-14 NOT TESTED; FIN-02/STOCK-01 planned; ADR0026/0027 Proposed unchanged.
K push/CI and independent review NOT TESTED. Actual provider execution separately gated.
Runtime npm audit0 PASS; existing development audit5high FAIL. Four container/external skips.
[Validation](docs/plan/evidence/2026-10-15-k1b-receipt-inbox/VALIDATION.md),
[handoff](docs/plan/NEXT_AGENT_PACKAGE_K1B_2026-10-15.md),
[prompt](docs/plan/NEXT_AGENT_PACKAGE_K1B_PROMPT_2026-10-15.md).

## Previous checkpoint — 2026-10-15: K1a offline boundary locally verified; not published

K1a source `7d25aa2d72874271a62e363817e0624fb502497c` on `codex/package-k1a-event-boundary`: signature-first strict
test snapshot decoding with stripe16.0.0, 96 synthetic tests. Static/build/web114 PASS;
focused **191 passed in 53.85s**; full **1844 passed, 4 skipped in 1444.23s (0:24:04)** on fresh disposable PostgreSQL.
No HTTP route/inbox/worker/schema or money effect; full K1 and K acceptance NOT TESTED.
Provider admission is BLOCKED by separate authorization; K push/CI NOT TESTED.
FIN-02/STOCK-01 stay planned, ADR-0026/0027 Proposed; main remains fedd0f1.
Runtime npm audit0; existing development audit5high FAIL. No provider/credential action.
[K1a record](docs/plan/evidence/2026-10-15-k1a-event-boundary/VALIDATION.md), [handoff](docs/plan/NEXT_AGENT_PACKAGE_K1A_2026-10-15.md).

## Previous checkpoint — 2026-10-15: Package K proposed locally; provider gate closed

The next stage-2 package K / FIN-02 now has a local implementation and acceptance
proposal on `codex/package-k-plan`, based on `df88c20687333668d39fe76a26eabca691e62cb0`.
Documentation only: no K route, worker, schema, dependency or provider operation.
K-01–K-14 are NOT TESTED; actual Stripe test admission is BLOCKED by the separate
provider/credential authorization rule. The K branch is not authorized for push.
FIN-02 and STOCK-01 stay planned; ADR-0026/0027 Proposed. Main remains fedd0f1.
Published J exact-head CI 158 PASS; its accepted technical evidence is preserved.
[K plan](docs/plan/PACKAGE_K_PLAN_2026-10-15.md),
[reuse and validation](docs/plan/evidence/2026-10-15-package-k-plan/ARCHITECTURE_REUSE.md),
[current handoff](docs/plan/NEXT_AGENT_PACKAGE_K_PLAN_2026-10-15.md).

## Previous checkpoint — 2026-10-15: STOCK-01 technical evidence PASS; readiness unchanged

J-01–J-14 technical evidence PASS against `aedbb982a696052d606499f737b1754fce362b6a` with exact CI run 157
success. Full local **PASS: 1748 passed, 4 skipped in 1448.82s (0:24:08)**. STOCK-01 remains planned,
ADR-0026 Proposed; readiness requires the owner's separate explicit authorization. Main
remains fedd0f1. No PR, merge, deployment or production changes. The acceptance documentation
commit needs its own exact-head CI read; api/web source trees are unchanged and recorded.
[Acceptance](docs/plan/evidence/2026-10-15-stock-01-acceptance/ACCEPTANCE.md),
[handoff](docs/plan/NEXT_AGENT_PACKAGE_J_REVIEW2_FIXES_2026-10-14.md).

## Previous checkpoint — 2026-10-15: Package J review fixes part 2 locally verified; acceptance pending

M1, L2, L3 and the two-source destination-insert race are fixed in `7b96fec` on
`codex/package-j-review2-fixes`. Full local **PASS: 1748 passed, 4 skipped in 1448.82s (0:24:08)**. Static/focused PASS;
114 web tests; production audit 0, existing development audit 5 high. No migration or
dependency changed. Exact new CI NOT TESTED at this pre-publication checkpoint.
STOCK-01 remains planned, ADR-0026 Proposed; technical acceptance J-01–J-14 is next.
Main remains fedd0f1. L1/L4 are recorded limits, not fixes.

[Current handoff](docs/plan/NEXT_AGENT_PACKAGE_J_REVIEW2_FIXES_2026-10-14.md), [part-2 record](docs/plan/evidence/2026-10-14-j5-j6-review-fixes-part2/VALIDATION.md).

## Previous checkpoint — 2026-10-14: review of J5 and J6 done; H1 fixed (part 1); not merged

Независимый обзор J5 и J6 проведён: высокая находка H1 (подделка остатка проходила проверку
0042 при смене контекста перед фиксацией) исправлена миграцией 0043: `f366afe` на ветке
`codex/package-j-review2-fixes`. Полный локальный прогон — **PASS: 1746 passed, 4 skipped in 1428.69s (0:23:48)**. Ветка J6 опубликована, CI её
вершины `b3982ba` — PASS. Открыты M1, L2, L3 и тест гонки (часть 2), затем приёмка.
CI этой ветки на момент записи — NOT TESTED. `main` не переносился.

[Актуальный handoff](docs/plan/NEXT_AGENT_PACKAGE_J_REVIEW2_FIXES_2026-10-14.md),
[запись обзора](docs/plan/evidence/2026-10-14-j5-j6-review/REVIEW.md).

## Previous checkpoint — 2026-10-14: package J acceptance preparation (J6) committed; M2 fixed; not merged

Находка M2 независимого обзора измерена и устранена миграцией 0042: при 100 000 движений
одной строки остатка проводка шла 960 мс, теперь 43 мс (45 мс без истории). Добавлены
тесты строк J-12 и J-13 и пробела 10; закоммичено `35227cd` на ветке `codex/package-j-acceptance-prep`.
Полный локальный прогон — **PASS: 1745 passed, 4 skipped in 1646.70s (0:27:26)**. Ветка J5b опубликована, CI её вершины
`f521528` — PASS. Открыты независимый обзор J5 и J6 и сама приёмка STOCK-01. CI этой
ветки на момент записи — NOT TESTED. `main` не переносился.

[Актуальный handoff](docs/plan/NEXT_AGENT_PACKAGE_J6_ACCEPTANCE_PREP_2026-10-14.md),
[запись о срезе](docs/plan/evidence/2026-10-14-j6-acceptance-prep/VALIDATION.md).

## Previous checkpoint — 2026-10-14: package J slice J5b (Stock documents screen) committed; J5 complete; not merged

Вторая часть среза J5 — экран «Складские документы» (`/stock-documents/`) —
закоммичена: `c3da59d` на ветке `codex/package-j5b-stock-documents`; срез J5 завершён. Полный локальный
прогон — **PASS: 1735 passed, 4 skipped in 1587.30s (0:26:27)**. Browser-тест на компьютере и телефоне: доступность без
нарушений, потеря ответа без второго документа, отказ с названной причиной, менеджер
филиала — только перемещения и без сумм. Ветка J5a опубликована, CI её вершины `b003b75`
— PASS. Открыты M2, L6, тесты J-12 и J-13, обзор J5 и приёмка. CI этой ветки на момент
записи — NOT TESTED. `main` не переносился.

[Актуальный handoff](docs/plan/NEXT_AGENT_PACKAGE_J5B_STOCK_DOCUMENTS_2026-10-14.md),
[запись о срезе](docs/plan/evidence/2026-10-14-j5b-stock-documents/VALIDATION.md).

## Previous checkpoint — 2026-10-14: package J slice J5a (Materials screen) committed; not merged

Первая часть среза J5 — экран «Материалы» (`/materials/`) и проверка неопределённой
команды запасов по ключу — закоммичена: `afda55b` на ветке `codex/package-j5-screens`. Полный
локальный прогон — **PASS: 1734 passed, 4 skipped in 1279.06s (0:21:19)**. Browser-тест на компьютере и телефоне: доступность
без нарушений, потеря ответа и её проверка после перезагрузки, повтор тем же ключом,
отмена с отказом поздней копии. Ветка исправлений по обзору опубликована, CI её
вершины `5e3a801` — PASS. Открыты J5b «Складские документы», M2, L6 и приёмка. CI этой
ветки на момент записи — NOT TESTED. `main` не переносился.

[Актуальный handoff](docs/plan/NEXT_AGENT_PACKAGE_J5_MATERIALS_2026-10-14.md),
[запись о срезе](docs/plan/evidence/2026-10-14-j5-screens/VALIDATION.md).

## Previous checkpoint — 2026-10-14: package J review fixes committed; J1–J4 published

Независимый обзор J1–J4 проведён; его находки M1, L1, L2, L4, L5 и часть L3 исправлены и
закоммичены: `33a3ec6` на ветке `codex/package-j-review-fixes`. Главное — перемещение и приёмка
больше не блокируют друг друга намертво; строки остатка и стоимости существуют только
через документы (миграция 0041). Полный локальный прогон — **PASS: 1724 passed, 4 skipped in 1300.24s (0:21:40)**. Предел времени CI поднят до 45 минут. Открыты M2 и L6, экраны (J5) и
приёмка. Владелец 2026-10-14 передал исполнителю три вопроса обзора: «Делай, как ты считаешь нужным. Я доверяю полностью тебе, и ты принимаешь решение.»
CI этой ветки на момент записи — NOT TESTED. `main` не переносился.

[Актуальный handoff](docs/plan/NEXT_AGENT_PACKAGE_J_REVIEW_FIXES_2026-10-14.md),
[запись об исправлениях](docs/plan/evidence/2026-10-14-j-review-fixes/VALIDATION.md),
[запись обзора](docs/plan/evidence/2026-10-13-j-review/REVIEW.md).

## Previous checkpoint — 2026-10-13: package J slice J4 (transfers and returns) published; CI success; not merged

**Обновление 2026-10-13: независимый обзор J1–J4 проведён.** Блокирующих находок нет; две
средние и шесть низких находок не исправлены. Следующий шаг — исправить их в новой ветке от
этой вершины: [запись обзора](docs/plan/evidence/2026-10-13-j-review/REVIEW.md). Строки ниже о том,
что обзора нет, написаны до него.

Вторая часть среза J4 пакета J (возврат по строке исходного документа) написана,
закоммичена и опубликована: `4bd346c` на ветке `codex/package-j4-returns`, поверх опубликованной вершины
первой части (`014e611`). Возврат называет приёмку или списание того же владельца и их
строки, движется обратно источнику и не превышает количества исходной строки. Строка
возврата забирает долю суммы исходной строки; по приёмке запасы уходят по средней цене,
а разница идёт на счёт разницы цен; по списанию материал возвращается по доле его
стоимости. Миграция 0040 таблиц не добавляет. Срез J4 этим закончен; экранов ещё нет.
STOCK-01 остаётся `planned`, модуль в продукте включить нельзя; ADR-0026 остаётся
Proposed.

Проверки: full local **PASS: 1709 passed, 4 skipped in 1637.88s (0:27:17)**; Ruff, format и mypy
PASS на 284 файлах; web typecheck, lint, format, 102 unit и сборка PASS. Гонка двух
возвратов последнего количества засчитана с наблюдаемым ожиданием в `pg_locks`.
Независимый обзор J1–J4 — NOT TESTED: исполнитель проводит его после этой части. Ветка
опубликована 2026-10-13 без PR; CI точного коммита `c7c94ed` — **PASS** (run 38505095541).
`main` не переносился. Где `main` и что опубликовано, читать из `git ls-remote origin`.

[Актуальный handoff](docs/plan/NEXT_AGENT_PACKAGE_J4_RETURNS_2026-10-13.md),
[готовый prompt](docs/plan/NEXT_AGENT_PACKAGE_J4_RETURNS_PROMPT_2026-10-13.md),
[запись о срезе](docs/plan/evidence/2026-10-13-j4-returns/VALIDATION.md),
[план пакета J](docs/plan/PACKAGE_J_PLAN_2026-10-13.md),
[ADR-0026 (Proposed)](docs/adr/0026-materials-and-stock-movements.md).

## Previous checkpoint — 2026-10-13: package J slice J4 part one (transfers) published; CI success; not merged

Первая часть среза J4 пакета J (перемещение между местами хранения) написана,
закоммичена и опубликована: `0d923a4` на ветке `codex/package-j4-transfers`, поверх опубликованной вершины
среза J3 (`07bde5b`). Перемещение проводится одной командой: документ, строки и по два
движения на строку — расход из места документа и приход в место назначения. Денег оно
не двигает: нет денежной части, оценки и проводки, стоимость владельца не меняется,
блокировка книги не берётся. Внутри филиала его проводит менеджер филиала, между
филиалами — владелец или менеджер всей компании. Миграция 0039 таблиц не добавляет.
Возврата и экранов ещё нет. STOCK-01 остаётся `planned`, модуль в продукте включить
нельзя; ADR-0026 остаётся Proposed.

Проверки: full local **PASS: 1676 passed, 4 skipped in 1876.88s (0:31:16)**; Ruff, format и mypy
PASS на 283 файлах; web typecheck, lint, format, 102 unit и сборка PASS. Пять вариантов
гонок засчитаны с наблюдаемым ожиданием блокировки строки в `pg_locks`. Независимый
обзор — NOT TESTED: исполнитель решил провести его один раз после обеих частей J4. Ветка
опубликована 2026-10-13 без PR; CI точного коммита `7e31cc8` — **PASS** (run 38498098941).
`main` не переносился. Где `main` и что опубликовано, читать из `git ls-remote origin`.

[Актуальный handoff](docs/plan/NEXT_AGENT_PACKAGE_J4_TRANSFERS_2026-10-13.md),
[готовый prompt](docs/plan/NEXT_AGENT_PACKAGE_J4_TRANSFERS_PROMPT_2026-10-13.md),
[запись о срезе](docs/plan/evidence/2026-10-13-j4-transfers/VALIDATION.md),
[план пакета J](docs/plan/PACKAGE_J_PLAN_2026-10-13.md),
[ADR-0026 (Proposed)](docs/adr/0026-materials-and-stock-movements.md).

## Previous checkpoint — 2026-10-13: package J slices J1–J3 published; CI success; not merged

Срез J3 пакета J (списание по средней цене) написан, закоммичен и опубликован:
`565b68f` на ветке `codex/package-j3-writeoffs`, поверх среза J2. Списание проводится одной
командой: документ, строки, расходные движения, остатки, стоимость и одна проводка
`stock` в книге владельца — в одной транзакции. Сумму расхода считает база по
скользящей средней; остаток не уходит в минус. Миграция 0038 таблиц не добавляет.
Возвратов, перемещений и экранов ещё нет. STOCK-01 остаётся `planned`, модуль в
продукте включить нельзя; ADR-0026 остаётся Proposed.

Проверки: full local **PASS: 1651 passed, 4 skipped in 1727.29s (0:28:47)**; Ruff, format и mypy
PASS на 282 файлах; web typecheck, lint, format, 102 unit и 23 страницы PASS. Три гонки
засчитаны с наблюдаемым ожиданием в `pg_locks`. Ветка опубликована 2026-10-13 без PR;
она несёт план, J1, J2 и J3. CI точного коммита `c4a2422` — **PASS** (run 38482480419).
`main` не переносился. Независимый обзор — NOT TESTED: исполнитель решил провести его
один раз после среза J4. Где `main` и что опубликовано, читать из `git ls-remote origin`.

[Актуальный handoff](docs/plan/NEXT_AGENT_PACKAGE_J3_2026-10-13.md),
[готовый prompt](docs/plan/NEXT_AGENT_PACKAGE_J3_PROMPT_2026-10-13.md),
[запись о срезе](docs/plan/evidence/2026-10-13-j3-writeoffs/VALIDATION.md),
[план пакета J](docs/plan/PACKAGE_J_PLAN_2026-10-13.md),
[ADR-0026 (Proposed)](docs/adr/0026-materials-and-stock-movements.md).

## Previous checkpoint — 2026-10-13: package J slice J2 committed locally; not published

Срез J2 пакета J (счета материалов для книги и приёмка с суммами) написан и закоммичен
локально: `f8e1212` на ветке `codex/package-j2-receipts`, поверх среза J1. Приёмка
проводится одной командой: документ, строки, движения, остатки, стоимость по скользящей
средней и одна проводка `stock` в книге владельца — в одной транзакции. Миграция 0037
добавляет восемь таблиц `stock_*`; суммы видит только участник всей компании. Списаний,
возвратов, перемещений и экранов ещё нет. STOCK-01 остаётся `planned`, модуль в продукте
включить нельзя; ADR-0026 остаётся Proposed.

Проверки: full local **PASS: 1616 passed, 4 skipped in 1295.93s (0:21:35)**; Ruff, format и mypy
PASS на 281 файле; web typecheck, lint, format, 102 unit и 23 страницы PASS. Независимый
обзор и CI — NOT TESTED: ни одна ветка пакета J на момент записи не опубликована. Где
`main` и опубликованы ли ветки, читать из `git ls-remote origin`.

[Актуальный handoff](docs/plan/NEXT_AGENT_PACKAGE_J2_2026-10-13.md),
[готовый prompt](docs/plan/NEXT_AGENT_PACKAGE_J2_PROMPT_2026-10-13.md),
[запись о срезе](docs/plan/evidence/2026-10-13-j2-receipts/VALIDATION.md),
[план пакета J](docs/plan/PACKAGE_J_PLAN_2026-10-13.md),
[ADR-0026 (Proposed)](docs/adr/0026-materials-and-stock-movements.md).

## Previous checkpoint — 2026-10-13: package J slice J1 committed locally; not published

Срез J1 пакета J (материалы и места хранения, денег нет) написан и закоммичен локально:
`39fc819` на ветке `codex/package-j1-materials`. Миграция 0036 добавляет четыре таблицы
`stock_*` с защитой строк по компании и филиалу, упорядоченными неизменяемыми версиями и
замком модуля; API `/v1/businesses/{id}/inventory/items` и `/places`; карта прав версии 7;
реестр модулей версии 3, где `inventory` зависит от `finance`. STOCK-01 остаётся
`planned`, модуль в продукте включить нельзя; ADR-0026 остаётся Proposed.

Проверки: full local **PASS: 1573 passed, 4 skipped in 1342.47s (0:22:22)**; новые тесты
J1 — 40 passed; Ruff, format и mypy PASS на 274 файлах; web typecheck, lint, format, 102
unit и 23 страницы PASS. Независимый обзор и CI — NOT TESTED: ветка на момент записи не
опубликована. Где `main` и опубликована ли ветка, читать из `git ls-remote origin`.

[Актуальный handoff](docs/plan/NEXT_AGENT_PACKAGE_J1_2026-10-13.md),
[готовый prompt](docs/plan/NEXT_AGENT_PACKAGE_J1_PROMPT_2026-10-13.md),
[запись о срезе](docs/plan/evidence/2026-10-13-j1-materials/VALIDATION.md),
[план пакета J](docs/plan/PACKAGE_J_PLAN_2026-10-13.md),
[ADR-0026 (Proposed)](docs/adr/0026-materials-and-stock-movements.md).

## Previous checkpoint — 2026-10-13: package J plan approved; code not started

Владелец согласовал план пакета J этапа 2 (базовые материалы, STOCK-01), выбрав
двенадцать решений. Главное: материалы ведутся со стоимостью по скользящей средней и сами
делают проводки в книге учёта; приёмку, списание и возврат проводит владелец или менеджер
всей компании; модуль «Запасы» зависит от «Финансов». ADR-0026 остаётся Proposed до
приёмки STOCK-01. Кода пакета нет: изменены только документы.

Проверки: `git diff --check` PASS; ссылки новых документов ведут на существующие файлы.
Тесты и CI — NOT TESTED: кода в срезе нет, ветка `codex/package-j-plan` на момент записи не
опубликована. Основа — `main` на `fedd0f1`; где `main` сейчас, читать из
`git ls-remote origin main`. Сервер, API, миграции и статусы готовности не менялись.

[Актуальный handoff](docs/plan/NEXT_AGENT_PACKAGE_J_PLAN_2026-10-13.md),
[готовый prompt](docs/plan/NEXT_AGENT_PACKAGE_J_PLAN_PROMPT_2026-10-13.md),
[план пакета J](docs/plan/PACKAGE_J_PLAN_2026-10-13.md),
[ADR-0026 (Proposed)](docs/adr/0026-materials-and-stock-movements.md).

## Previous checkpoint — 2026-10-13: workforce screens checked in eight untested situations

Экраны «Персонала» проверены в настоящем браузере в восьми ситуациях, которые приёмка
Package I назвала непроверенными: 16 из 16 на компьютере и телефоне. Найдены и исправлены
два дефекта экрана «Мои смены»: он показывал смены вне выбранных четырёх недель и молча
обрезал длинный список. Сервер, API, миграции и статусы готовности не менялись.

Проверки: full local **PASS: 1532 passed, 4 skipped in 1419.45s (0:23:39)**; Ruff, format и mypy PASS на
266 файлах; web typecheck, lint, format, 102 unit и 23 страницы PASS. CI на
момент записи NOT TESTED. 2026-10-13 владелец решил опубликовать ветку `codex/workforce-screen-situations` и после
зелёного CI точного коммита перенести на неё `main` одним обычным push; результат CI и
положение `main` читать из GitHub Actions и `git ls-remote origin main`.

[Актуальный handoff](docs/plan/NEXT_AGENT_WORKFORCE_SCREENS_2026-10-13.md),
[готовый prompt](docs/plan/NEXT_AGENT_WORKFORCE_SCREENS_PROMPT_2026-10-13.md),
[запись о срезе](docs/plan/evidence/2026-10-13-workforce-screen-situations/VALIDATION.md).

## Previous checkpoint — 2026-10-12: main fast-forwarded to the head of the stack

`main` перенесён с `46cd866` на `8a34a80` одним обычным push без force по решению владельца
от 2026-10-12. В `main` теперь вся основная линия: 113 коммитов, миграции 0001–0035.
CI на `main`: **PASS**, [run 38338644832](https://github.com/alexeyalexandrov2026-tech/GORGONA-Booking-Platform_new/actions/runs/38338644832) на `8a34a80`: задание 1108 с, pytest 958 с; текст логов не читался.
Ничего не развёрнуто; статусы готовности не менялись. PR #2–#5 признаны заменёнными и не
сливаются. Страницы PR: отмечены как слитые: #1; закрыты без слияния: нет; остаются открытыми: #2, #3, #4, #5, #6, #7, #8, #9, #10, #11, #12, #13, #14, #15, #16, #17, #18, #19, #20, #21, #22.

Новая работа начинается от `main`. Запись о выполнении лежит на ветке `codex/merge-plan`, на один
коммит документов впереди `main`.

[Handoff после переноса `main`](docs/plan/NEXT_AGENT_AFTER_MERGE_2026-10-12.md),
[готовый prompt](docs/plan/NEXT_AGENT_AFTER_MERGE_PROMPT_2026-10-12.md),
[план слияния и его выполнение](docs/plan/MERGE_PLAN_2026-10-12.md).

## Previous checkpoint — 2026-10-12: production dependency audit cleared

Production-аудит зависимостей web (`npm audit --omit=dev`) — **PASS: 0 находок**; было
FAIL: 2 high. Обновлены `next` 16.3.7 → 16.3.8 и `source-map-js` 1.2.1 → 1.2.2. Код
приложения, тесты и миграции не менялись. Полный аудит вместе с инструментами
разработки — **FAIL: 5 high**: одна цепочка `braces`, исправленной версии которой не
существует; в production-образ она не попадает.

Проверки обновлённого дерева: full local **PASS: 1531 passed, 4 skipped in 1023.50s (0:17:03)**; Ruff, format и mypy PASS на
265 файлах; web typecheck, lint, format, 102 unit и 23 страницы PASS. CI:
**PASS**, [run 38315410876](https://github.com/alexeyalexandrov2026-tech/GORGONA-Booking-Platform_new/actions/runs/38315410876) на `8a1a7ab`: задание 1204 с, pytest 1057 с; текст логов не читался.
Ветка `codex/web-dependency-audit` опубликована с разрешения владельца (основа `4630ca3`).

Состояние Package I не изменилось и описано в следующем разделе.

Владелец 2026-10-12 выбрал перемотку `main` на вершину ветки `codex/merge-plan`
([план](docs/plan/MERGE_PLAN_2026-10-12.md)); PR #2–#5 считаются заменёнными и не сливаются. Где сейчас
`main`, читать из `git ls-remote origin main`; запись о выполнении — на ветке `codex/merge-plan`.

[Handoff среза аудита](docs/plan/NEXT_AGENT_WEB_DEPENDENCY_AUDIT_2026-10-12.md),
[готовый prompt](docs/plan/NEXT_AGENT_WEB_DEPENDENCY_AUDIT_PROMPT_2026-10-12.md),
[запись о срезе](docs/plan/evidence/2026-10-12-web-dependency-audit/VALIDATION.md).

## Previous checkpoint — 2026-10-12: package I accepted technically; WORK-01 and CORE-04 verified

WORK-01 записан как `technically_verified` на коде `f41f9a8`. Модуль `workforce` стал
включаемым: компания получает его, только опубликовав конфигурацию с ним. CORE-04
записан как `technically_verified` отдельным коммитом `1b925f1` по основаниям пакета F.
ADR-0025 — Accepted as implemented. Решение: 2026-10-12 владелец поручил исполнителю
выбирать самостоятельно и на предложение выполнить приёмку ответил «Continue»;
трактовка записана в [записи о приёмке](docs/plan/evidence/2026-10-12-work-01-acceptance/ACCEPTANCE.md).

Проверки дерева приёмки: full local **PASS: 1531 passed, 4 skipped in 972.96s (0:16:12)**; Ruff, format и mypy PASS на
265 файлах; web typecheck, lint, format, 102 unit и 23 страницы PASS; независимая
проверка изменения PASS. CI коммита приёмки: **PASS**, [run 38236481277](https://github.com/alexeyalexandrov2026-tech/GORGONA-Booking-Platform_new/actions/runs/38236481277) на `75f2b9b`: задание 1037 с, pytest 899 с; текст логов не читался.
Production audit **FAIL: 2 high** (next, source-map-js).

Это техническая приёмка. Пилота и разрешения на production нет. PR и merge не
выполнялись; миграции и зависимости не менялись. Утверждения ниже о том, что
WORK-01 или CORE-04 planned, а workforce закрыт, относятся к своим датам.

[Handoff приёмки](docs/plan/NEXT_AGENT_PACKAGE_I_CORRECTIONS_2026-10-12.md),
[готовый prompt](docs/plan/NEXT_AGENT_PACKAGE_I_PROMPT_2026-10-12.md),
[запись о приёмке](docs/plan/evidence/2026-10-12-work-01-acceptance/ACCEPTANCE.md),
[независимая проверка](docs/plan/evidence/2026-10-12-work-01-acceptance/INDEPENDENT_CHECK.md),
[предыдущий срез: исправления и публикация](docs/plan/evidence/2026-10-12-i4-review-corrections/FOLLOWUP_VALIDATION.md).
Ниже сохранены исторические срезы; их результаты не заменяют текущий handoff.

## Previous checkpoint — 2026-10-12: corrections uncommitted; full suite FAIL

R2-1/R2-2/R2-3/CR-1 исправлены в рабочей копии
`C:/Users/alexa/.codex/worktrees/package-i4-review-corrections/Gorgona Booking`,
branch `codex/package-i4-review-corrections`, HEAD490652b. **Нового коммита нет.**
Final focused47PASS,20новых regressionsPASS, workforce browser/static/web и
ограниченный независимый source reviewPASS. Full **1failed,1525passed,4skipped /
1124.75s**: counterparty desktop ambiguous alert locator; mobile module-off timeout.
Причина mobile ещё не доказана. Следующий шаг — diagnosis/focused/full/review,
после зелёных ворот local commit. Production auditFAIL2high. I-09 scopedPASS,
I-12FAIL; acceptanceBLOCKED, WORK-01/CORE-04planned, workforce закрыт.
Миграции/dependencies/readiness не менялись; API/web strict v1 reason_source
требует согласованного выпуска. Новая ветка не опубликована; её CI NOT TESTED.

[Актуальный handoff](docs/plan/NEXT_AGENT_PACKAGE_I_CORRECTIONS_2026-10-12.md),
[готовый prompt](docs/plan/NEXT_AGENT_PACKAGE_I_PROMPT_2026-10-12.md),
[evidence и точные ограничения](docs/plan/evidence/2026-10-12-i4-review-corrections/VALIDATION.md).
Ниже сохранены исторические срезы. Их инструкции/результаты не заменяют текущий
handoff и не означают, что dirty corrections входят в HEAD490652b.

## Previous: I4 fixes re-reviewed; acceptance blocked by three findings — 2026-10-12

Local branch `codex/package-i4-review-2`, own managed checkout
`C:/Users/alexa/.codex/worktrees/package-i4-review-2/Gorgona Booking`, base `0356eb5`.
Read [review 2](docs/plan/evidence/2026-10-11-i4-shift-visibility/INDEPENDENT_REVIEW_2.md),
[measured evidence](docs/plan/evidence/2026-10-11-i4-shift-visibility/INDEPENDENT_REVIEW_2_CHECKS.json)
and the [updated continuation](docs/plan/NEXT_AGENT_PACKAGE_I_ACCEPTANCE_2026-10-12.md).

Review result FAIL: R2-1/P2, hidden-shift access through swap after same-home
reinvitation with no current profile; R2-2/P2, concurrent different-key cancels
leave 21 markers despite the cap of 20 (open/off/not-accepted); R2-3/P3, a valid
human reason `Clock-in` is hidden by the screen's string filter. Five targeted
checks fail across these three findings; no product correction was made.

Fresh PASS: 86 focused / 104.38s; standard browser 1 / 150.78s; timezone≠UTC and
company-wide addition browser 1 / 149.74s, desktop/mobile across three phases.
Static/web PASS, unit 102, pages 23; source hashes 16/16. Production audit FAIL
2 high. Full suite was not repeated in this review; earlier full C1 is a separate
snapshot. CI c6b8e34 is still success; exact local review-commit CI NOT TESTED.
Temporary probes restored/removed, own clusters stopped, runtime unchanged.

I-09 and I-12 now FAIL in the current plan. Correct the three findings on a new
branch with failing checks first, smallest coherent fixes, focused/full/static/web
and actual browser checks, then independent review and fresh evidence. WORK-01,
CORE-04 and workforce stay planned/closed. Owner policy/acceptance/publication
decisions remain pending. No push/PR/merge/deployment/production migration.

## Previous: Package I acceptance evidence prepared; no promotion — 2026-10-12

Continue from [the updated handoff](docs/plan/NEXT_AGENT_PACKAGE_I_ACCEPTANCE_2026-10-12.md)
and [the fresh matrix](docs/plan/evidence/2026-10-12-i-acceptance/ACCEPTANCE.md).
Local branch `codex/package-i-acceptance` starts at verified local/remote I4 head
`c6b8e341a7e88957ee5011e54e9aa06453b31b49`; changes are documentation/evidence only.
Read the final local documentation SHA from Git. The branch is not published.

Fresh PASS: complete PostgreSQL/browser-required suite 1506 passed / 4 skipped /
1026.84s; I4 three phases on desktop/mobile (six Playwright cases); Ruff/format/mypy
264; web typecheck/lint/format, unit 102 and build 23 pages. Exact-source CI c6b8e34
PASS: run 38204334830, job 114664366391, 1509 passed / 1 skipped / 595.96s, including
required container checks. Local container skips and the optional external site
remain NOT TESTED locally. Source hashes match 16/16; own clusters stopped.
Current production npm audit FAIL: 2 high (next, source-map-js).

I-01–I-11 PASS for recorded cases; I-12 conservatively BLOCKED pending a second
independent source review of a806380..b66eb41. The first review exists, but fresh
regression execution does not replace a source review of the fourteen fixes.
Package I is not accepted. WORK-01/CORE-04 and workforce readiness are unchanged;
migrations 0001–0035, code and dependency locks are preserved. Owner decisions on
the working plan/ADR, policy choices, acceptance/readiness, PRs and stack order
remain open. Exact-SHA CI for the new local documentation commit is NOT TESTED.
No push/PR/merge, deployment, production migration or CodeRabbit.

## Previous: colleague-shift visibility is a branch setting; branch published — 2026-10-11

Successor entry point: [handoff for the next agent: acceptance of package I, instructions and copyable prompts](docs/plan/NEXT_AGENT_PACKAGE_I_ACCEPTANCE_2026-10-12.md).
Owner decision of 2026-10-11 on the first open choice of I4: staff see colleagues'
published shifts by default, and the owner, a manager or the manager of that
branch may hide them. Same branch codex/package-i4-workforce-screens on the I4
record 5f0e58f; final code commit 419eda8097554c024cb76cde38fe901c386a5e29. Forward 0035
adds append-only branch setting versions with an SQL guard for the author and one
lock per branch; it is part of the packaged workforce approvals and of the
branch-policy restore. New routes: GET/PUT /workforce/locations/{id}/settings and
GET /workforce/my-changes/{id}/shifts (a participant reads the shifts their own
request names, also while browsing is hidden). Schedule has a Privacy section; My
shifts closes the swap choice and says why.
[Evidence](docs/plan/evidence/2026-10-11-i4-shift-visibility/VALIDATION.md),
[commands](docs/plan/evidence/2026-10-11-i4-shift-visibility/COMMANDS.md).
PASS: complete suite 1500 passed / 4 skipped / 953.19s on 419eda8; real browser on desktop and phone
1 / 103.56s; one race with an observed pg_locks wait; Ruff/format/mypy 263;
web unit 102 and build 23 pages. The owner allowed publishing this branch: it is
pushed; exact-commit CI of 5f0e58f is success (run 38132277248); CI of later heads
is read on GitHub. No PR. Independent review DONE on 2026-10-11 by a non-author:
no critical or high finding, two medium, seven low, seven notes
([review](docs/plan/evidence/2026-10-11-i4-shift-visibility/INDEPENDENT_REVIEW.md),
[author's response](docs/plan/evidence/2026-10-11-i4-shift-visibility/AUTHOR_RESPONSE.md)).
Fourteen of sixteen are fixed in b66eb41: a hidden branch now also refuses a new
swap, the outside-schedule mark follows the time in effect, discarding is limited
to 20 a day; two are documented and left to the owner. Complete suite after the
fixes: 1506 passed / 4 skipped / 2306.13s. A discarded key cannot write for the 24 hours its
receipt lives, not for ever. Containers, external site,
HawkScan, load/soak, deployment/production NOT TESTED. Inherited production npm
audit FAIL 2 high. WORK-01/CORE-04 and the workforce readiness lock are unchanged;
migrations 0001–0034 are untouched. No CodeRabbit.

## Previous: I4 implemented and locally validated — 2026-10-11

Successor entry point: [package I after I4: open items and copyable prompts](docs/plan/NEXT_AGENT_PACKAGE_I_REVIEW_2026-10-11.md).
Local branch codex/package-i4-workforce-screens on the I4 handoff
d22b61cf53612ab85c157c00ecd75fd1630ba1c2; final code commit
f4a7395e3ab9515e410143103142f44072af6cba. Three management screens over I1–I3:
Schedule, My shifts and Timesheets, on desktop and phone. Five small read and
outcome routes were added after failing tests; no migration. A lost answer is
settled with the server by the original key; the browser keeps identifiers only.
[Evidence](docs/plan/evidence/2026-10-11-i4-workforce-screens/VALIDATION.md),
[commands](docs/plan/evidence/2026-10-11-i4-workforce-screens/COMMANDS.md).
PASS: complete suite 1486 passed / 4 skipped / 907.37s on f4a7395; real browser on desktop and phone
1 / 92.97s; two cancel races with observed pg_locks waits; Ruff/format/mypy 261;
web unit 101 and build 23 pages. Independent review NOT DONE (the author's
re-read only). No push/PR; exact-commit CI, containers, external site, HawkScan,
load/soak, deployment/production NOT TESTED. Inherited production npm audit
FAIL 2 high. Migrations 0001–0034, WORK-01/CORE-04 and the workforce readiness
lock are unchanged. Package acceptance (matrix I-01–I-12) and publication remain
owner decisions. FIN-03 check stays a separate task. No CodeRabbit.

## Previous: I3 implemented and locally validated — 2026-10-11

Successor entry point: [I4 handoff and copyable prompt](docs/plan/NEXT_AGENT_PACKAGE_I4_2026-10-11.md).
Verified I3 code commit: `ec9524aa77d0d26fee7253380d226f394cc587fd`.
The handoff is a separate documentation change; I4 is not started here.

Local branch codex/package-i3-timesheets on I2
49276bf800eb929589785e192db489e17ac77fa7. Forward0034 adds own start/end/breaks,
immutable corrections/decisions, last-approved effective time, stable-user
one-open/overlap protection and original-revision replay. Own closure/history
work when workforce is off. No journal or shared occupancy is created.
[Evidence](docs/plan/evidence/2026-10-11-i3-timesheets/VALIDATION.md),
[independent source review](docs/plan/evidence/2026-10-11-i3-timesheets/INDEPENDENT_REVIEW.md).
PASS: final focused76/67.46s, Ruff/format/mypy254,
web94/build and corrected-source review14 SHA matches. All17 I3 races require
observed pg_locks waits. Four SQL/state findings reproduced and fixed.
Full I3 suite PASS:1473 passed / 4 skipped / 832.46s.
Migrations0001–0033, WORK-01/CORE-04 and workforce readiness remain unchanged.
No push/PR; exact-commit CI, I4 screens, containers, deployment/production and
load/soak NOT TESTED. Inherited production npm audit FAIL2 high.
Next slice I4 and package acceptance remain. FIN-03 check stays a separate task.
No CodeRabbit.

## Previous: I2 implemented and locally validated — 2026-10-10

Local branch codex/package-i2-shift-changes on I1
69270cc8bfdfb763cc8f5fc9b7892b13db987bce. Forward0033 adds handover, swap and
home-open pickup with explicit consent, manager approval, exact skill snapshots,
atomic shared occupancy and original-event receipt replay. No new dependency.
[Evidence](docs/plan/evidence/2026-10-10-i2-shift-changes/VALIDATION.md),
[independent source review](docs/plan/evidence/2026-10-10-i2-shift-changes/INDEPENDENT_REVIEW.md).
Focused156/114.89s plus six replacement-skill cases/7.48s, Ruff/format/mypy248,
web94/build and corrected-source review PASS. Full suite PASS:
1380 passed / 4 skipped / 738.66s. All ten races require observed pg_locks waits.
Independent findings reproduced and fixed: hidden prior resource release under
RLS and foreign self pickup. Migrations0001–0032 unchanged. WORK-01/CORE-04 and
the workforce readiness lock remain unchanged. No push/PR; exact-SHA CI,
containers (3 skip), external site (1 skip), deployment, production and load/soak
NOT TESTED. Inherited production
npm audit FAIL:2 high nodes. I3 timesheets, I4 screens and package acceptance
remain; the FIN-03 acceptance check is a separate task. No CodeRabbit.

## Previous: I1 implemented and locally validated — 2026-10-09

Branch codex/package-i1-workforce from I0 14190730. Forward0032 adds
membership profiles sharing a stable user resource, versioned skills and shifts,
atomic shared occupancy assignments, typed API, permission6 and fail-closed
schema approval. [Evidence](docs/plan/evidence/2026-10-09-i1-workforce/VALIDATION.md),
[independent review](docs/plan/evidence/2026-10-09-i1-workforce/INDEPENDENT_REVIEW.md).
Focused 81/45.49s, Ruff/format/mypy 239 and web 94/build PASS; independent final
code review PASS. Full project suite PASS: 1301 passed / 4 skipped / 772.12s.
The first full run failed with DiskFull and remains preserved in the evidence.
Three container tests and one external-site test remain NOT TESTED.
WORK-01/CORE-04 unchanged;
workforce remains closed outside test readiness overrides. No push/PR/CI,
deployment, production migrations, cloud or provider action.
I2 changes, I3 timesheets, I4 screens and acceptance remain. Staff home transfer
is a separate lifecycle; unsafe moves fail closed. Inherited npm production
dependency audit reports2 high nodes, not repaired by I1.

## Previous: package I started, plan and slice I0 — 2026-10-09

[Handoff and copyable prompt](docs/plan/NEXT_AGENT_PACKAGE_I_2026-10-09.md),
[progress against the master plan](docs/plan/PROJECT_PROGRESS_2026-10-09.md),
[package I plan](docs/plan/PACKAGE_I_PLAN_2026-10-09.md),
[ADR-0025](docs/adr/0025-workforce-shifts-and-timesheets.md),
[slice I0 inventory](docs/plan/evidence/2026-10-09-i0-resource-kinds/INVENTORY.md).
Package I (shifts, shift changes, timesheets; WORK-01) has a plan and ADR-0025.
The owner did not approve them explicitly but delegated the choice of next
steps, so the recommended options are working defaults. Slice I0 on
`codex/package-i0-resource-kinds` changes no schema or source: seven tests pin
what booking, reservations and staff setup do with resource kinds today, and the
inventory lists what slice I1 must change with the planned `staff` kind. Full
local run: PASS, 1238 passed / 4 skipped / 644.59 s. WORK-01 and the `workforce` module stay planned; no
shift, change or timesheet code exists. The package I branches are local.
Package H is described in the next section; its draft PR and the independent
check of the acceptance commit are still open. No
merge/deploy/production/provider/funds action.

## Previous: package H technically accepted (FIN-03) — 2026-10-09

[Handoff and copyable prompt](docs/plan/NEXT_AGENT_H_ACCEPTANCE_2026-10-09.md),
[audit](docs/plan/evidence/2026-10-09-h-acceptance-audit/AUDIT.md),
[acceptance record](docs/plan/evidence/2026-10-09-h-acceptance/ACCEPTANCE.md).
H1–H4 are implemented at `319f144` on `codex/package-h4-ui-admission`:
migrations 0021–0031, the H API and the Financial documents and Provider
admission screens. Draft PR15–PR22 are stacked and open; nothing is merged.
Exact-SHA CI for `319f144` is success (push 37876007880, pull_request
37876031010); its steps build the web app and the production image and run
PostgreSQL 18, Ruff, mypy and pytest.
Independent audit on a separate checkout and cluster: full local suite
1231 passed / 4 skipped / 662.06 s with mandatory PostgreSQL and browser;
Ruff/format/mypy 230 and web gates PASS; four SQL guard mutations were all
caught. No money defect was found. Findings A-01–A-11 are in the audit; the only
P2 (provider admission is writable with `finance` alone) is closed by the
owner's decision of 2026-10-09: no code change, H4 is not deployed before H
acceptance, admission is accepted together with H.
**FIN-03 is `technically_verified` by the owner's decision of 2026-10-09** on
code `319f144`. `finance_documents` is enableable by a company's own published
configuration and the test-only readiness overrides are removed. Full local run
on the acceptance tree: 1231 passed / 4 skipped / 666.05 s. ADR-0024 is
Accepted. FIN-02 remains planned. Branch `codex/package-h-acceptance` holds the
audit `71359f9` and the acceptance commit `ec39622`; it was pushed on 2026-10-09
by the owner's decision and exact-SHA CI for `ec39622` is success (push
37887856597). No draft PR is open for it yet (GitHub sign-in needed); an
independent check of the acceptance commit is NOT DONE.
No merge/deploy/production/provider/funds action. The sections below are
historical snapshots.

## Historical H2 backend handoff — 2026-10-07

[Full successor handoff](docs/plan/NEXT_AGENT_H2_2026-10-07.md),
[copyable prompt](docs/plan/NEXT_AGENT_PROMPT_H2_2026-10-07.md),
[changed files/checks/limits](docs/plan/evidence/2026-10-07-h2-settlements/VALIDATION.md).
Branch codex/package-h2-settlements from the delivered H1 backend 75e809b.
**Published in [draft PR16](https://github.com/alexeyalexandrov2026-tech/GORGONA-Booking-Platform_new/pull/16), target H1 PR15; no merge.**
Original eight docs committed/pushed as75c36da; final docs are a successor.
Read actual final HEAD/origin/current-head CI in PR16/exported delivery state.
Corrective source `15edbed1d608ada9d0901a7710c00eff28c23e71` fixes a diagnosed ledger refresh race in two web files;
financial Python/SQL and frozen migrations are unchanged from54852b4. [CI37578255793](https://github.com/alexeyalexandrov2026-tech/GORGONA-Booking-Platform_new/actions/runs/37578255793) PASS:1044 passed/1 skipped/379.86s;
all3 Docker/image, PG/browser, web69/2.3s and static211 PASS.
Fresh local full:1041 passed/4 skipped/434.68s; focused browser1/17.95s.
Bounded independent UI review PASS; full H2 money/state review remains NOT DONE.
Forward 0022–0024 add manual accruals as new obligations, settlement documents
with approval/reserve/sent/release/cancel, and externally attested partial
confirmations that move exactly R→P with one balanced journal and a permanent
external identity. PostgreSQL and the service both enforce P+C+R<=A at commit.
Historical author full suite1041/4/459.51s; fresh corrective results are above.
Mandatory PostgreSQL18.6 and browser;
Ruff/format/mypy211 and web gates PASS. Exact-checkpoint CI75c36da
[37573680437](https://github.com/alexeyalexandrov2026-tech/GORGONA-Booking-Platform_new/actions/runs/37573680437) PASS:1044 passed/1 skipped/381.36s; all3 Docker/image,
PG/browser, 69 web tests/2.3s and static211 PASS.
Independent money/state review NOT DONE; HawkScan was not run.
FIN-03/02 remain planned and finance_documents unavailable. H3 credits, refund
obligations and corrections and H4 UI/admission remain unfinished.
Owner/E2 dirty trees preserved; own cluster 51462 stopped.
No merge/deploy/production/provider/funds action. The H1 section below is
superseded for continuation; its evidence remains snapshot-specific.

## Historical H1 backend handoff — 2026-10-06

[Full successor handoff](docs/plan/NEXT_AGENT_H1_BACKEND_2026-10-06.md),
[copyable prompt](docs/plan/NEXT_AGENT_PROMPT_H1_BACKEND_2026-10-06.md),
[changed files/checks/reviews](docs/plan/evidence/2026-10-06-h1-backend/VALIDATION.md).
Delivery branch codex/package-h1-persistence; reviewed source2d5a8f9 from
foundation18e3f5e. [Draft PR15](https://github.com/alexeyalexandrov2026-tech/GORGONA-Booking-Platform_new/pull/15)
targets PR14. Read exact current delivery HEAD/CI there.
Real forward0021 and invoice API persist one immutable issue, principal
obligation and G accrual atomically; minimal permanent recovery and explicit
journal-v2 are implemented. Root953/4skip/378.14s, Ruff/format/mypy204 PASS;
independent corrective review47 PG/109 units PASS, H1-R01 closed.
FIN-03/02 remain planned and finance_documents unavailable. H2 settlement/
manual accrual, H3 credits/refunds and H4 UI/admission remain unfinished.
Owner/E2 dirty trees preserved; own root51456 and review51460 stopped.
No merge/deploy/production/provider/funds action. Historical foundation below
has been superseded for continuation; its evidence remains snapshot-specific.

## Historical H1 foundation — 2026-10-06

Owner continued local work and explicitly approved H1 source publication.
[Draft PR14](https://github.com/alexeyalexandrov2026-tech/GORGONA-Booking-Platform_new/pull/14)
targets planning PR13. Delivery branch codex/package-h-invoices; reviewed
source843d0b3, checkpointda3966b. Exact-head CI37534227319 PASS909 passed/
1 optional skip with PG/browser/Docker and build. This handoff update is a
docs-only successor; refresh current PR14 head/CI.
[Copyable successor prompt](docs/plan/NEXT_AGENT_PROMPT_H1_2026-10-06.md).
Read [H1 handoff](docs/plan/NEXT_AGENT_PACKAGE_H1_2026-10-06.md) and
[checks/boundaries](docs/plan/evidence/2026-10-06-h1-foundation/VALIDATION.md).
Strict contracts, pure allocation math and planned finance_documents/registry2
are implemented. H1 workflow is IN PROGRESS; actual H SQL/API/UI is not built.
FIN-03/02 remain planned; G acceptance and old published configurations remain.
Earlier planning/review statements below describe their own snapshots.

## Historical H planning snapshot — 2026-10-06

Own branch codex/package-h-finance-plan from G head5be6e7a.
Read [H handoff](docs/plan/NEXT_AGENT_PACKAGE_H_2026-10-06.md),
[H plan](docs/plan/PACKAGE_H_PLAN_2026-10-06.md) and
[ADR-0024 Proposed](docs/adr/0024-invoices-obligations-and-external-settlements.md).
Docs only: typed invoices/obligations/settlement reserves, externally attested
partial payments, credits/refund obligations and admission requests are proposed.
No H money code/schema/provider activation; FIN-03/02 remain planned.
Independent proposed-design review PASS; owner scope confirmation remains
pending before code. [Review/check evidence](docs/plan/evidence/2026-10-06-package-h-plan/VALIDATION.md).
G finance remains technically verified; its exact-SHA CI is not H validation.

## Current G continuation — 2026-10-06

Read [package G handoff](docs/plan/NEXT_AGENT_PACKAGE_G_2026-10-06.md) and
[fresh evidence](docs/plan/evidence/2026-10-06-ledger/ACCEPTANCE.md).
Branch codex/package-g-ledger-review from accepted stage-2 plan 151472a;
own checkout under .codex/worktrees/package-g-ledger-review/Gorgona Booking.
The original gorgona-e2-documents and owner checkout are preserved.
Ledger books/accounts/double entry/reversals/periods/trial balance and real API/UI
are implemented. The early-SET-CONSTRAINTS balance bypass was reproduced and fixed.
All seven independent findings are closed, including unexpected permissive SQL policies.
Evidence code 95a0de4: full local 858 passed/4 skipped, exact-SHA CI 861 passed/1 skipped
with required Docker gates; independent final guard-delta code/unit review PASS.
Fresh accepted-registry focused: 68 Python and 4 desktop/mobile browser flows,
without positive readiness overrides; 68 web unit tests PASS. Recovery and safe cancellation prevent
the delayed original from running after an unresolved request is cancelled.
Finance/FIN-01 are technically verified by a separate acceptance commit. A new
configuration publication enables finance; no existing configuration is changed.
Check the fresh acceptance HEAD CI in draft PR #12; evidence names source SHA and review boundaries.
No merge, deployment, production migration, providers or Azure changes.
Older continuation sections below are historical for their own code versions.

## Current E2-A continuation — 2026-10-05

Read [E2-A handoff](docs/plan/NEXT_AGENT_E2_FILE_VALIDATION_2026-10-05.md) and
[evidence](docs/plan/evidence/2026-10-05-file-validation/ACCEPTANCE.md).
Branch codex/package-e2-file-validation from accepted E1 3983dd4. This increment
is the bounded file-profile/CSP prerequisite, no storage/API/UI/migration or
documents readiness promotion. Continue E2 persistence/integration per ADR0020/0021,
then E3 and CORE-04. Owner dirty checkout is preserved; no production action.

## Current E1 continuation — 2026-10-05

Read [the E1 handoff](docs/plan/NEXT_AGENT_PACKAGE_E1_2026-10-05.md) and
[acceptance](docs/plan/evidence/2026-10-05-counterparties/ACCEPTANCE.md) first.
Current branch codex/package-e1-counterparties builds on audited E0 bbe6ecd and
targets that branch in its own draft PR. Owner checkout remains untouched.
Versioned counterparties/contacts, explicit duplicate decisions and manual booking
links are implemented; E2 documents/files and E3 agreements are next, then CORE-04.
Code 2392566595a2df59f8ec3f073ed9bf184df6447f has green exact push/PR CI (599/1);
a separate acceptance promotes counterparties to technically_verified. Registry v1
and booking-only baseline remain unchanged; each business explicitly publishes it. Local API/browser/static gates passed with explicit
container/external-site skips; production/providers/Azure/load remain unverified.
The October-4 continuation and earlier counts below are historical, not current
code acceptance. Preserve all 39 profiles, 28 criteria and generic booking.

## Current continuation — 2026-10-04

The owner authorized correction of the complete universal-business plan and the start of implementation. Read [the corrected master plan](docs/plan/GORGONA_MASTER_PLAN.md) and [implementation evidence](docs/plan/GORGONA_IMPLEMENTATION_STATUS.md) first. Preserve all 39 industry profiles and existing generic booking workflows. `business_id` is the existing tenant boundary; multiple profiles do not create duplicate companies. GORGONA supplies software, including inventory and transport tools for its customers, without operating its own warehouse or carrier.

The current repository develops GORGONA only. KA Nails is a separate project, outside this implementation and release scope. The first-tenant proposals and brand instructions below are historical context; do not treat them as current tasks or platform acceptance requirements.

The [2026-10-04 plan-conformance audit](docs/plan/GORGONA_PLAN_AUDIT_2026-10-04.md) maps all 28 acceptance criteria. Stage 1 is partial. A confirmed security issue in the old development hold endpoint has been corrected: `/v1/holds` is registered only in local/test/CI, while hosted bookings retain the customer validation/capability path. The linked audit records the failing regression, fresh focused PASS and independent review; compare every later CI result with its exact commit.

Azure is the accepted deployment direction ([ADR-0012](docs/adr/0012-azure-hosting.md)); the OCI proposal below is historical. Production actions still require their acceptance gates and owner authorization. Begin with baseline defects, then the typed business foundation and shared resource/financial/material invariants. No provider approval or production readiness is implied by this handoff.

Baseline at the start of this work: clean checkout at `76ce4e52f1c19b176586c8f69e55d4df735d1a1e`. Prior results on that unchanged version were 151 API tests passed, 12 AI tests passed, 17 AI tests skipped, and web type checking passed. Rerun relevant checks after changes; do not reuse these as evidence for a new tree.

The current implementation also includes location-scoped booking/resource operations, branch invitations, legacy command-receipt compatibility and a fail-closed PostgreSQL access-definition guard. Read [ADR-0014](docs/adr/0014-location-scoped-workspace.md) and the latest [next-agent handoff](docs/plan/NEXT_AGENT_HANDOFF_2026-10-04.md) before continuing. No industry-wide or production readiness is implied.

## Historical handoff — 2026-09-30 (preserved reference)

The sections below describe the original proposal, audit and later repository separation. They are not current deployment instructions or current implementation status. The current continuation, master plan and accepted ADRs take precedence.

Prepared 2026-09-30. This document is the starting context for the next coding environment. Read it before writing application code. The complete local project is this repository; all paths below are relative to its root.

## Objective and scope

Build a reusable, tenant-aware appointment platform named **GORGONA Booking AI** with **KA Nails** as its first tenant. The customer-facing KA Nails experience should follow the supplied official logo. Implement a deterministic booking system before the AI concierge. This handoff is Phase 0 audit/design; do not report the product as implemented.

The owner asked for a new GitHub project and considered Cloudflare/Supabase. They then asked whether **Oracle server could replace Supabase and Cloudflare**. Proposed direction: OCI-hosted web/API plus PostgreSQL, with Cloudflare optional for DNS/CDN/WAF. This is an architecture proposal, not a deployed system. The owner explicitly chose **not** to pause existing Supabase projects; the new Supabase project is deferred. Preserve existing GORGONA/Fresh Nails services and data.

## What exists here

- `assets/brand/ka-nails-logo.png`: exact supplied logo; SHA-256 `BB2FE1C05EB7183B8B8F55EEE861B06D80256CF5349B2958E1432FA3B83FBF53`.
- `source/PRODUCT_BRIEF.txt`: complete pasted owner brief, copied verbatim for full context. The later OCI/deferred-Supabase decisions in this handoff take precedence.
- `docs/architecture/INITIAL_AUDIT.md`: evidence and limitations from the two owner-controlled Fresh Nails reference repositories.
- `docs/architecture/TARGET_ARCHITECTURE.md`: proposed OCI-first modular monolith and decision list.
- `docs/architecture/DATA_MODEL.md`, `BOOKING_ENGINE.md`, `MULTITENANCY.md`, `SECURITY_MODEL.md`, `AI_TOOL_MODEL.md`: domain, trust and concurrency contracts.
- `docs/architecture/DESIGN_SYSTEM.md`, `ANALYTICS.md`, `OBSERVABILITY.md`, `RELEASE_PLAN.md`: customer experience and quality gates.
- Local Git repository on `main`, with no external remote until account access is restored.

## Verified findings and blockers

1. This task's starting folder had no Git repository. The owner's accessible GitHub account is `alexeyalexandrov2026-tech`. `Fresh-Nails` is a Vite/React marketing site with static JSX prices and Square links. `Fresh-Nails-AI-Receptionist-by-Gorgona-One-AI` is a separate Next.js/Dify/Supabase chat project. Neither is a KA Nails booking core. They were cloned read-only into this task's `work/` folder, outside this deliverable.
2. The old OCI `gorgona-node` was recorded as **TERMINATED** in a prior audit. On 2026-09-30, `oci iam region-subscription list --profile GORGONA --auth security_token` failed because the session expired. No current VM, cost, IP, SSH access or deployed application was verified. Do not target historical IP `150.136.90.12`.
3. Supabase organization `Gargona One` is free; creation reported $0/month but failed because its owner has reached the two active free-project limit. Active projects are `gorgona-camera-feed` and `Gorgona-one-claude`. The owner chose to keep both running and defer the new project.
4. The GitHub connector lacks a create-repository operation. GitHub's in-app page was unauthenticated and Git Credential Manager supplied no reusable credential. No GitHub repo or remote exists for this project. Cloudflare's in-app page was also at sign-in. No Cloudflare project or DNS change was made.
5. The product brief refers to a separate GORGONA/KA Nails architecture image, but only the logo image and text brief were available. Authentic KA Nails photos, domain, address, schedule, staff, legal/policy wording and the base Hammam booking duration were not supplied/verified.

## Next execution sequence

1. Reconcile owner decisions: confirm OCI compartment and current host plan, budget, domain, business timezone, staff/hours, service durations, deposit/cancellation/tax rules, photo rights and whether Square remains temporary booking. Do not infer these from Fresh Nails.
2. Renew OCI browser security-token session using `GORGONA` profile; list current instances/compartments and verify exact target. No VM restart, infrastructure creation or production deployment before cost, blast radius and rollback are reviewed with owner. Do not create an OCI API signing key by default.
3. Once GitHub login is available, create a **private** `gorgona-booking-ai` repository under the owner's chosen account, add its URL as `origin`, push the reviewed local `main`, and verify GitHub file/hash parity. Do not push cloned Fresh Nails references, secrets or task `work/` files.
4. Turn the approved architecture into ADRs, exact migrations, typed API contracts and tests. Implement tenant/catalog and staff/scheduling first; then transactional holds and appointments. Use PostgreSQL `tstzrange` + GiST exclusion for exclusive resources; the 100-concurrent-attempt acceptance is one success and 99 typed conflicts. Keep the AI outside booking authority.
5. Set up isolated staging on verified OCI infrastructure, private PostgreSQL, TLS, backups/PITR, restore drill, telemetry and CI before production. Cloudflare remains optional. Do not turn on a public booking CTA until it reaches a real validated booking/payment flow.

## Product facts from supplied brief that may be seeded after owner validation

- Hammam Luxury: $145; heel care and ritual included; gel not included.
- Hammam Luxury + Gel: $160, public duration range 120–145 minutes.
- Hammam Luxury + Gel French: $175, public range 130–155 minutes.
- Extra Foot Massage: +$20 and exactly +15 minutes booking time.
- Other Salon Gel Removal: +$15, subject to staff assessment when required.
- Hammam Spa Upgrade: +$40 only for compatible pedicures; must not stack with Hammam Luxury.
- French Gel: +$15 and only with compatible gel service.
- Base Hammam deterministic booking duration is **unknown**. Do not invent one or publish it as bookable.

## Security and release rules

No browser service-role credentials; trusted tenant context; composite tenant foreign keys and RLS; verified payment webhooks and idempotency; transactional outbox; structured, redacted logs; tested restore. AI tools are typed, tenant-scoped, policy-checked and have no arbitrary SQL/shell/HTTP access. Preserve human correction and audit history. Treat tests and live validation as separate evidence, and keep the status labels PASS / FAIL / BLOCKED / NOT TESTED.

## Suggested first prompt in Cloud Code

> Open this repository and read `CLOUD_CODE_HANDOFF.md` and every file in `docs/architecture/`. Treat the supplied KA Nails logo as the brand source. First verify Git state and the current OCI/GitHub access. Do not reuse Fresh Nails as KA Nails source. Make a detailed, testable M1 plan for an OCI-first modular monolith, identify owner decisions and deployment gates, and implement only the next approved, reviewable slice. Do not claim application or infrastructure completion from these design documents.

## Repository separation update (30 September 2026)
The logo source paths above record Phase 0 provenance. The unchanged PNG now belongs to the independent KA-nails repository at `public/assets/ka-nails-logo.png`; the old bytes remain in Git history. Platform origin is `alexeyalexandrov2026-tech/-GORGONA-Booking-Platform`. No push or deployment was performed. See `docs/architecture/REPOSITORY_SEPARATION.md`.
