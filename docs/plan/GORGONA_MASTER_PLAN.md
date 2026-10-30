# GORGONA — полный обновленный мастер-план универсальной бизнес-платформы

> **Решение владельца 2026-10-20 — цель продакшена: все 39 направлений одновременно.**
> GORGONA — универсальная платформа, а не система для салонов. В промышленную эксплуатацию
> выходят **все 39 направлений каталога (§3) вместе**, одним запуском: компания любого из 39
> направлений (или их сочетания) может сама зарегистрироваться и сразу начать работать. Ни одно
> направление не является «первым», «основным» или пилотным вместо остальных; красота (№ 1) —
> одно из 39. Исходный код вырос из системы записи салонов — это история проекта, а не приоритет.
> Этапы §13 задают только порядок разработки модулей; запуск (§13, этап 9) охватывает все 39
> направлений. Агентам: не планировать и не описывать запуск «только для салонов» или любой
> другой одной отрасли; оценки готовности давать по всем 39 направлениям.

## Current checkpoint — 2026-10-30: N8 fixes of the independent review of package N, locally verified

N8 on `codex/package-n8-review-fixes` (code `b6cd7ef`, [N8 evidence](evidence/2026-10-30-n8-review-fixes/CHECKS.json), [package N acceptance record](evidence/2026-10-29-n7-acceptance/ACCEPTANCE.md)): with the owner's consent («Yes, run review») one read-only agent reviewed package N at `4861b85` and found RN-01..RN-09 (2 high, 5 medium, 2 low); each is fixed with a test that failed first — RN-01 the tender accrual draft is frozen; RN-02 a tendered trip is not re-planned; RN-03 a carrier never closes a shared stop; RN-04 no withdrawal or new rate version after the accrual; RN-05 a carrier answers at server time; RN-06 an unlinked carrier keeps its restriction; RN-07 a carrier reads only its own trips; RN-08 the margin never adds currencies; RN-09 a started trip is not tendered. N7 is now a true brokered flow (tenders before events, carrier A acts on the platform); N-09 is PARTIAL (keyboard-only not run). Migration **0086** (triggers only). Gates-5: focused **844 passed**, full **2665 passed, 4 skipped**; gates-1..4 failed and are recorded (mypy; vanished Playwright files, reinstalled on the owner's word; a crashed git call; the existing `test_i4_browser` "read ECONNRESET", passed alone and in gates-5, cause open). Readiness, enabling transport and `main` wait for the owner's word. Next migration **0087**.

## Previous checkpoint — 2026-10-29: package N acceptance (N7), technically accepted locally; independent review open

N7 on `codex/package-n7-acceptance` (code `08f519c`, [acceptance record](evidence/2026-10-29-n7-acceptance/ACCEPTANCE.md)): one end-to-end test of a brokered two-leg load through the API and PostgreSQL (no authority refused, a carrier without a profile refused, two carriers on two legs, a covered leg refuses a second acceptance, rate confirmation version 2 agreed with version 1 kept, stop events close the leg and a repeat changes nothing, each pay accrues once, margin 1500.00 − 900.00 − 450.00 = 150.00 with no margin column); the record maps TMS-01..03 and N-01..N-09 to proofs and limits. Gates-1 found an N6 defect (Save authority enabled before the authority was read, so a fast save sent revision 0); the button now waits for the read. Gates-2: focused **833 passed**, full **2654 passed, 4 skipped**. No migration. **The one independent review of package N waits for the owner's consent**; readiness, enabling transport and `main` wait for the owner's word. Next migration **0086**.

## Previous checkpoint — 2026-10-28: N6 brokerage on the transport screens, locally verified

N6 on `codex/package-n6-screens` (code `33fc82e`, [validation record](evidence/2026-10-28-n6-brokerage-screens/VALIDATION.md)): strict web contracts for the N1–N5 routes and brokerage panels on the transport screen for company-wide owners and managers — broker authority, carriers with eligibility in words, loads to cover, tenders with answers, rate confirmation versions, carrier pay and the order margin; a real-browser test on desktop and mobile. No migration. Dev and gates-1 failures kept in the record; gates-2: focused **832 passed**, full **2653 passed, 4 skipped**. A branch-limited member is covered by the page rule and the server refusal, not by a browser run. Readiness and enabling transport wait for the owner's word. Next migration **0086**.

## Previous checkpoint — 2026-10-28: N5 carrier pay and margin, locally verified

N5 on `codex/package-n5-carrier-pay` (code `5dd4700`, [validation record](evidence/2026-10-28-n5-carrier-pay/VALIDATION.md)): migration **0085** books one insert-only FIN-03 payable manual accrual per accepted tender with closed legs, for the rate confirmation in force (fixed or per mile); `GET orders/{order}/margin` derives the invoice total less the accrued pay of the order's own tenders, listing shared tenders without subtracting them. One dev failure kept in the record (the accrual kind); gates-1: focused **831 passed**, full **2652 passed, 4 skipped**. Readiness and enabling transport wait for the owner's word. Next migration **0086**.

## Previous checkpoint — 2026-10-28: N4 carrier companies and tracking, locally verified

N4 on `codex/package-n4-tracking` (code `cd301f1`, [validation record](evidence/2026-10-28-n4-carrier-companies/VALIDATION.md)): migration **0084** links a carrier to its own company on the platform in insert-only versions; that company's delegates answer the tenders and rate confirmations addressed to their carrier through a grant with `transport.tender` (source `platform`) and record stop events only on their accepted tendered legs. gates-1 failed once (a unit test listing the delegable rights; fixed; kept in the record); gates-2: focused **826 passed**, full **2647 passed, 4 skipped**. Readiness and enabling transport wait for the owner's word. Next migration **0085**.

## Previous checkpoint — 2026-10-27: N3 rate confirmations, locally verified

N3 on `codex/package-n3-rate-confirmations` (code `526189e`, [validation record](evidence/2026-10-27-n3-rate-confirmations/VALIDATION.md)): migration **0083** keeps rate confirmation versions of accepted tenders and the carrier's answers as insert-only facts; accepting a tender writes version 1, agreed; a change is in force only once the carrier agrees. gates-1 failed once (4 tests outside transport under load, passed alone; kept in the record); gates-2: focused **820 passed**, full **2641 passed, 4 skipped**. Not tested: a signed copy that is the business's own document; the backfill on accepted tenders. Readiness and enabling transport wait for the owner's word. Next migration **0084**.

## Previous checkpoint — 2026-10-27: N2 tenders, locally verified

`main` was fast-forwarded to `590a8f3` on the owner's word (2026-10-27): package M with its review fixes, the package N plan and N1. N2 on `codex/package-n2-tenders` (code `80183b5`, [validation record](evidence/2026-10-27-n2-tenders/VALIDATION.md)): migration **0082** keeps tenders of trip legs to other carriers and their answers as insert-only facts with a source; the state is derived; offering and accepting need an eligible broker and carrier on the local date; a leg has at most one accepted tender. gates-1 failed once (two upgrade tests lacked the new tables; kept in the record); gates-2: focused **814 passed**, full **2635 passed, 4 skipped**. Readiness and enabling transport wait for the owner's word. Next migration **0083**.

## Previous checkpoint — 2026-10-26: package M review fixes, locally verified

Review fixes on `codex/package-m-review-fixes` (code `44b8505`, [validation record](evidence/2026-10-26-m-review-fixes/VALIDATION.md)): all nine findings of the independent package M review are fixed. FIN-03 freezes transport drafts; a leg loaded short closes once its pickup is departed; migration **0081** keeps the loads of an invoiced order; money lines are bounded and exact (422); a concurrent pay component on the same id is compared; stop windows carry an end date; module text and grant label corrected. gates-1: focused **807 passed**, full **2628 passed, 4 skipped**. The `main` fast-forward (M6a..M8, the N plan, N1 and these fixes) is proposed to the owner and waits for their word, as do readiness and enabling transport. Next migration **0082**.

## Previous checkpoint — 2026-10-26: N1 broker authority and carrier profiles, locally verified

N1 on `codex/package-n1-broker-carriers` (code `a3d85d3`, [validation record](evidence/2026-10-26-n1-broker-carriers/VALIDATION.md)): migration **0080** keeps a business's broker authority and each carrier's profile as insert-only dated versions; eligibility for a date names every failing reason; right `transport.broker` (permissions version 10) for owners and managers, not delegable. gates-1 failed once on an unrelated catalog browser test (kept in the record); gates-2: focused **800 passed**, full **2621 passed, 4 skipped**. The owner approved one independent review of package M (2026-10-26); it found nine issues, two high (transport drafts editable through FIN-03; a short-loaded leg never closes); fixes come next, before N2. Readiness and `main` wait for the owner's word; transport stays not enableable. Next migration **0081**.

## Previous checkpoint — 2026-10-26: package M technically accepted locally, independent review open

M7b CI SUCCESS (run 40272483262). M8 on `codex/package-m8-acceptance`: TMS-01..03 PASS locally ([acceptance record](evidence/2026-10-26-m8-acceptance/ACCEPTANCE.md)), with a new end-to-end TMS-01 test in `6d5c86c` (one trip, two orders' loads, three stops in three zones, the truck replaced after loading, a partial delivery with refusals and damage, all history kept). Focused **735 passed**; full **2616 passed, 4 skipped**. The owner deferred the independent review (2026-10-26); it stays open. Readiness of the transport module and `main` wait for the owner's word; the module stays not enableable. Next migration **0080**.

## Previous checkpoint — 2026-10-26: M7b transport money on the screens, locally verified

Defect fixes CI SUCCESS (run 40261326556). M7b in `f44db22` on `codex/package-m7b-money-screens`: a company-wide owner or manager sets an order's rate, creates its FIN-03 customer invoice with extras and sees what is paid and open; on the trip page registers pay components (driver, dispatch fee, …) and accrues them; a branch-limited member and a delegate never see money. Focused **734 passed**; full **2615 passed, 4 skipped** ([validation](evidence/2026-10-25-m7b-money-screens/VALIDATION.md)). Next: M8 (package M acceptance; the independent review needs the owner's consent for an extra agent). Next migration **0080**.

## Previous checkpoint — 2026-10-25: package M defects D-01 and D-02 fixed, locally verified

M7a CI SUCCESS (run 40245557506). The two open defects are fixed in `099bc84` on `codex/package-m-defects`: the "night-time" workforce browser failure was the live test server's loop dying with WinError 10055 (socket buffers exhausted), so the harness now fails a test with the server's own error; a refused grant offer now stays visible after the list reloads. Focused **733 passed**; full **2614 passed, 4 skipped** ([validation](evidence/2026-10-25-m-defects/VALIDATION.md)). Next: M7b (money on the screens), then M8. Next migration **0080**.

## Previous checkpoint — 2026-10-25: M7a transport money through FIN-03, locally verified

M6b CI SUCCESS (run 40227240451). M7a in `b2998d5` on `codex/package-m7-transport-money` (ADR-0033): an
order's agreed rate is kept as versions and frozen by its one FIN-03 customer invoice (freight per mile or fixed
plus named extras, only when nothing is open); a trip's pay components (driver, owner-operator, dispatch fee)
are registered once and each accrues once as its own FIN-03 payable obligation on a closed trip; FIN-03 keeps
payments within the open balance. Finance rights only, never a delegate. Focused **730 passed**; full **2612
passed, 4 skipped** ([validation](evidence/2026-10-25-m7a-transport-money/VALIDATION.md)); full-1 lost a Chromium session in an unrelated browser test,
recorded. Next: M7b (money on the screens), then M8. Next migration **0080**.

## Previous checkpoint — 2026-10-25: M6b planning forms, fleet and carrier grants, locally verified

M6a CI SUCCESS (run 40177073619). M6b in `ba9cb64` on `codex/package-m6b-transport-forms`: owners and
managers enter and correct orders, plan and correct trips with stops in their own time zones and register
drivers and vehicles; the grant form offers a carrier transport actions with or without bookings, and the
carrier's dispatcher sees Transport only through such a grant, with only the granted forms. Orders are paged by
cursor. Real browser desktop and mobile with the database read back. Focused **723 passed**; full **2605
passed, 4 skipped** ([validation](evidence/2026-10-25-m6b-transport-forms/VALIDATION.md)). Next: M7 (money), then M8 (acceptance). Next migration **0079**.

## Previous checkpoint — 2026-10-25: M6a dispatch board and trip page, locally verified

`main` fast-forwarded to `ad21888` on the owner's word (CI SUCCESS, run 40165514386). M6a in `76519b8` on
`codex/package-m6a-transport-screens`: the Transport screen (owner or manager) lists every trip with status,
first and last window in the stop's own time zone and the current crew; the trip page shows stops, legs with
loaded, delivered, refused, damaged and open, assignments with periods and the event log, assigns or replaces
a crew member from a moment, records stop events with leg quantities (a retry after a lost answer records the
event once) and checks clearance. Trips, drivers and vehicles are paged by cursor and read to the end. Real
browser desktop and mobile with the database read back. Focused **721 passed**; full **2603 passed, 4 skipped**
([validation](evidence/2026-10-25-m6a-transport-screens/VALIDATION.md)). full-1 failed on two existing tests (a time-of-day-dependent workforce browser test
and a 401 on an expired test token); both recorded, not hidden. Next: M6b (order and trip forms, fleet,
transport rights in the grant screen, dispatcher navigation), then M7 and M8. Next migration **0079**.

## Previous checkpoint — 2026-10-24: BEAUTY-01 technically verified (owner's word)

Owner's word 2026-10-24: «BEAUTY-01 accept». In `84fb150` on `codex/beauty-01-readiness` the readiness registry
records BEAUTY-01 as `technically_verified` for code `8b6b37d` and schema 73 (exact-head CI 40040514685), citing
the package L acceptance (L-01..L-12 PASS), the L8 review, L9a, L9b and the [readiness record](evidence/2026-10-24-beauty-01-readiness/RECORD.md). Not a pilot
and not a production approval; no module becomes enableable; the salon profile stays `planned`. Focused **719
passed**; full **2601 passed, 4 skipped**. M5 CI green (40152895317). `main` still waits for the owner. Next:
package M slice M6 (screens); next migration **0079**.

## Previous checkpoint — 2026-10-24: M5 hours-of-service and telematics clearance locally verified

M5 in `1180d41` on `codex/package-m5-clearance` ([ADR-0032](../adr/0032-transport-clearance.md)): versioned hours-of-service profiles; duty
records and telematics pings as insert-only facts with source ids; clearance computed for a moment and never
positive on stale or unknown data (TMS-03); migration 0078. Focused **683 passed**; full **2600 passed, 4
skipped** ([validation](evidence/2026-10-24-m5-clearance/VALIDATION.md)). M4 CI green (40116278936). BEAUTY-01 readiness and `main` still wait for the
owner. Next migration **0079**; next slice M6 (screens).

## Previous checkpoint — 2026-10-24: M4 dispatcher scope on carrier grants locally verified

M4 in `4b6cd75` on `codex/package-m4-dispatcher-grants` ([ADR-0031](../adr/0031-transport-dispatcher-grants.md)): a carrier grants an independent
dispatcher transport work by action (read, plan, assign, events) through the ADR-0017 grants; fleet registration
is never delegated; revocation, delegate removal and expiry block the next command; earlier facts keep their
executor; permissions version 9, migration 0077. Focused **676 passed**; full **2593 passed, 4 skipped**
([validation](evidence/2026-10-24-m4-dispatcher-grants/VALIDATION.md)). M3 CI green (40081070256). BEAUTY-01 readiness and `main` still wait for the owner. Next
migration **0078**.

## Previous checkpoint — 2026-10-24: M3 stop events and partial delivery locally verified

M3 in `f6ac5f1` on `codex/package-m3-stop-events` ([ADR-0030](../adr/0030-transport-stop-events.md)): stop events are insert-only facts with a
source event id (a repeat changes nothing); partial delivery per leg, never beyond the plan or the load; the first
event starts the trip and freezes its plan; trucks can be replaced in transit (migration 0076). Focused
**660 passed**; full **2587 passed, 4 skipped** ([validation](evidence/2026-10-24-m3-transport-events/VALIDATION.md)). M2 CI green (40072696483). BEAUTY-01
readiness and `main` still wait for the owner. Next migration **0077**.

## Previous checkpoint — 2026-10-24: M2 transport assignments locally verified

M2 in `31bb854` on `codex/package-m2-assignments` ([ADR-0029](../adr/0029-transport-assignments-occupancy.md)): drivers, trucks and trailers have their own
lanes in the shared occupancy; an assignment holds its period, a replacement ends one period and starts the next
all or none, a busy truck changes nothing, an open assignment freezes the trip's span (migration 0075). Focused
**653 passed**; full **2580 passed, 4 skipped** ([validation](evidence/2026-10-24-m2-transport-assignments/VALIDATION.md)). M1 CI green (40065762379). A record slip was
found and is stated there: earlier records carried a stale `next_migration` 72. BEAUTY-01 readiness and `main`
still wait for the owner. Next migration **0076**.

## Previous checkpoint — 2026-10-24: package M started; M1 transport planning locally verified

Owner's word 2026-10-23: add the transport module, not enableable until acceptance, and start package M
([plan](PACKAGE_M_PLAN_2026-10-23.md)). M1 in `32bb8a4` on `codex/package-m1-planning`: the module `transport` (implemented, not
enableable; registry version 4, permissions version 8), migration 0074 with shipment orders, loads, trips, stops
in their own time zones and legs; a load is never over-planned. Focused **494 passed**; full **2571 passed, 4
skipped** ([validation](evidence/2026-10-23-m1-transport-planning/VALIDATION.md)). BEAUTY-01 readiness and `main` still wait for the owner. Next migration **0075**.

## Previous checkpoint — 2026-10-23: BEAUTY-01 gaps closed; zod security update; owner decides readiness and main

L9b CI SUCCESS (run 40034329906). A new high advisory (GHSA-mrhx-c7xc-m3w5, zod <4.6.6) found by the L9b
audit is fixed in `609159f`: zod 4.6.7 pinned; npm audit 0; focused **486 passed**, full **2563 passed, 4
skipped** ([validation](evidence/2026-10-23-l9-zod-security/VALIDATION.md)). Readiness and `main` wait for the owner's word. Next migration **0074**.

## Previous checkpoint — 2026-10-23: BEAUTY-01 gaps closed (L9a, L9b); owner decides readiness and main

L9a CI SUCCESS (run 40023359035). L9b in `00aadee` on `codex/package-l9b-commission-reversal` (migration 0073):
each refund reverses the commission's share of its service, cumulatively and once, with lineage; decision 85
fixed a defect (a visit settled by a prepaid unit earned no commission). Focused **486 passed**; full **2563
passed, 4 skipped** ([validation](evidence/2026-10-23-l9b-commission-reversal/VALIDATION.md)). The [acceptance record](evidence/2026-10-23-l8c-acceptance/ACCEPTANCE.md) now shows L-06 and L-07 PASS. Kept: the
L9b record was written after its code commit; npm audit found a new high advisory in zod (fixed in its own
commit). Readiness and `main` wait for the owner's word. Next migration **0074**.

## Previous checkpoint — 2026-10-23: L9a fee policy and no-shows locally verified (BEAUTY-01 gap L-06)

Owner's word 2026-10-23: close both BEAUTY-01 gaps, same process; readiness and `main` untouched. L8c CI
SUCCESS (run 39999584445). L9a in `8a90567` on `codex/package-l9a-fee-policy` (migration 0072): a versioned
fee policy, the no-show fact, billing computes the late-cancellation and no-show fee from the version in force
when the visit was booked; settings form and desk step. Focused **479 passed**; full **2556 passed, 4 skipped**
([validation](evidence/2026-10-23-l9a-fee-policy/VALIDATION.md)). Next: L9b (commission reversal after a refund), then the acceptance record update. Next
migration **0073**.

## Previous checkpoint — 2026-10-23: package L (BEAUTY-01) acceptance record written; owner decides readiness and main

L8c in `558b580` on `codex/package-l8c-acceptance` proves L-09 for the commission and prepaid tables (direct
SQL refused, the use guard holds, another company sees nothing). Focused **473 passed**; full **2550 passed,
4 skipped** ([validation](evidence/2026-10-23-l8c-acceptance/VALIDATION.md)). The [acceptance record](evidence/2026-10-23-l8c-acceptance/ACCEPTANCE.md) maps L-01..L-12: ten PASS, two PASS with a named
GAP — L-06 cancellation and no-show lines are not computed from a published policy; L-07 a refund does not
reverse the commission automatically. Readiness and the fast-forward of `main` wait for the owner's word.
Next migration **0072**.

## Previous checkpoint — 2026-10-23: L8b2 acceptance gaps locally verified; L8b1 CI green

L8b1 CI SUCCESS (run 39981532055, includes the spec fix for the L8a CI failure). L8b2 in `1e4368a` on
`codex/package-l8b2-acceptance-gaps`: the visit desk follows the business's modules (no write-off without
inventory, no billing without invoices, no commission without workforce); races of consumption, accrual and
redemption leave one write after an observed `pg_locks` wait; billing and prepaid refuse without invoices; a
room stage holds the room against staff reservations. The API proofs passed at once on existing code (no API
change). Focused **471 passed**; full **2548 passed, 4 skipped** ([validation](evidence/2026-10-23-l8b2-acceptance-gaps/VALIDATION.md)).
Next: L8c (BEAUTY-01 acceptance record). Next migration **0072**.

## Previous checkpoint — 2026-10-23: L8b1 review fixes R8-R15 locally verified; L8a CI failed on two specs

L8b1 in `ee7fc1b` on `codex/package-l8b1-review-fixes` fixes the remaining review findings R8-R15 (stage
revision, 50 stages on the site, reschedule checks every service, workforce and inventory gates on writes, plan
references and the first-save race, write-off place in the visit's branch, prepaid currency, the desk hides a
used balance). Focused **466 passed**; full **2543 passed, 4 skipped** ([validation](evidence/2026-10-23-l8b1-review-fixes/VALIDATION.md)).
**L8a CI run 39971712190 FAILED** on two browser specs L8a did not touch (`management.spec.ts` strict-mode
status, `service-catalog.spec.ts` slow row); the spec fix is its own commit on the L8b1 branch.
Next: L8b2 (races, module gates on the desk, room stage), then L8c (acceptance). Next migration **0072**.

## Previous checkpoint — 2026-10-23: package L reviewed; L8a review fixes R1-R7 locally verified

L7c CI SUCCESS (run 39901727848). One independent review of package L (owner's consent) found 15 defects
([review](evidence/2026-10-23-l8-review/REVIEW.md)); two high: a cancelled visit's paid fee accrued the full commission, and prices in 0- or
3-decimal currencies were billed at the wrong scale. L8a in `e3d45de` on `codex/package-l8a-review-fixes`
fixes R1-R7 (commission only for a confirmed visit, exact price conversion, free lines not billed, prepaid
units by matching line and whole worth, linked drafts frozen, recorded visits not moved or cancelled).
Focused **458 passed**; full **2535 passed, 4 skipped** ([validation](evidence/2026-10-23-l8a-review-fixes/VALIDATION.md)). Next: L8b (R8-R15, races,
module gates, room stage), then L8c (acceptance). Next migration **0072**.

## Previous checkpoint — 2026-10-23: L7c customer site, several services and stages, locally verified

L7b2b CI SUCCESS (run 39886335939). L7c in `1b00d01` on `codex/package-l7c-customer-site`: on the customer
site a guest books up to five services in one visit, each with its own add-ons, sees every line, the total,
the duration and the stages of a staged visit, and is offered only specialists who serve every service; real
browser desktop and mobile with the database read back. Focused **444 passed**; full **2521 passed, 4
skipped** ([validation](evidence/2026-10-23-l7c-customer-site/VALIDATION.md)). Next: L8 (BEAUTY-01 acceptance; owner's consent for the review, owner's
word for readiness and `main`). Next migration **0072**.

## Previous checkpoint — 2026-10-23: L7b2b prepaid screen and redemption, locally verified

L7b2a CI: the first run failed after UTC midnight (browser tests took today in UTC); fix `d2ac158` takes
today in the branch or business zone, CI SUCCESS (run 39879172808). L7b2b in `3d2658a` on
`codex/package-l7b2b-prepaid-screens`: a Prepaid screen lists and sells packages and certificates, and the
visit desk redeems a usable balance against an open visit invoice; real browser desktop and mobile with
the database read back. Focused **442 passed**; full **2520 passed, 4 skipped** ([validation](evidence/2026-10-23-l7b2b-prepaid-screens/VALIDATION.md)). Next:
L7c (customer site). Next migration **0072**.

## Previous checkpoint — 2026-10-22: L7b2a visit billing and commission screens, locally verified

L7b1 CI SUCCESS (run 39855981830). L7b2a in `56ab1ee` on `codex/package-l7b2a-billing-desk`: the visit desk
bills a visit, shows it paid and accrues the specialist's commission once; the Staff screen edits the
commission plan; real browser desktop and mobile with the database read back. Focused **439 passed**; full
**2517 passed, 4 skipped** ([validation](evidence/2026-10-22-l7b2a-billing-desk/VALIDATION.md)). Two load-only flakes kept with causes not proven. Next:
L7b2b (prepaid sale and redemption on screen). Next migration **0072**.

## Previous checkpoint — 2026-10-22: L7b1 visit desk, locally verified

L7a CI SUCCESS (run 39838977982). L7b1 in `d1c12ca` on `codex/package-l7b1-visit-desk`: on a confirmed
booking the visit desk completes the visit with actual quantities and writes its materials off; real
browser desktop and mobile with the database read back. Focused **436 passed**; full **2514 passed, 4
skipped** ([validation](evidence/2026-10-22-l7b1-visit-desk/VALIDATION.md)). Next: L7b2 (billing,
commission, prepaid on screen). Next migration **0072**.

## Previous checkpoint — 2026-10-22: L7a catalog screens, locally verified; Next.js security upgrade

L6 CI SUCCESS (run 39828302644). L7 designed ([design](PACKAGE_L7_DESIGN_2026-10-22.md), `259cfd2`).
L7a in `13919b3` on `codex/package-l7a-catalog-screens`: the Services screen edits the stages and the
materials of a service, equipment is a resource kind; real browser desktop and mobile. `npm audit`
flagged a critical Next.js advisory (GHSA-2464-fhr4-w9xw); `next` upgraded to 16.4.2 here — `main` and
earlier branches still pin 16.3.8 until merged. Focused **434 passed**; full **2512 passed, 4 skipped**
([validation](evidence/2026-10-22-l7a-catalog-screens/VALIDATION.md)). Next: L7b, the visit desk.
Next migration **0072**.

## Previous checkpoint — 2026-10-22: L6 prepaid packages and gift certificates, locally verified

L5 CI SUCCESS (run 39819887470). L6 designed ([design](PACKAGE_L6_DESIGN_2026-10-22.md), `7c7230a`) and
built in `affdaf3` on `codex/package-l6-prepaid` (migration 0071): a package or certificate is sold by an
invoice line on the prepayment liability and usable once paid; using it on a visit is a FIN-03 credit note
of the visit invoice, so the prepayment becomes revenue when the service is delivered. Focused **427
passed**; full **2510 passed, 4 skipped** ([validation](evidence/2026-10-22-l6-prepaid/VALIDATION.md)).
Next: L7, the screens. Next migration **0072**.

## Previous checkpoint — 2026-10-22: L5 commissions and tips, locally verified

L4 CI SUCCESS (run 39812765674). L5 designed ([design](PACKAGE_L5_DESIGN_2026-10-22.md), `12b64c9`;
decision 30 revised) and built in `7ff9249` on `codex/package-l5-commissions` (migration 0070): a commission
plan per specialist; once the visit invoice is fully paid, the commission is one FIN-03 payable accrual to
the payee; tips stay a liability on the visit invoice (never revenue) and are recorded with the
commission. Focused **388 passed**; full **2504 passed, 4 skipped**
([validation](evidence/2026-10-22-l5-commissions/VALIDATION.md)). Next: L6, packages and
certificates. Next migration **0071**.

## Previous checkpoint — 2026-10-22: L4 visit billing, locally verified

L3 CI SUCCESS after raising the CI job limit to 75 minutes (run 39805277086, 43 min; the first run was
cancelled at 45). L4 designed ([design](PACKAGE_L4_DESIGN_2026-10-22.md), `c45607f`) and built in
`0738b4a` on `codex/package-l4-billing` (migration 0069): a visit is billed as one FIN-03 invoice (its
services and add-ons, plus fee lines; a cancelled visit only fees); deposit and the rest are FIN-03
payments of it. Focused **378 passed**; full **2494 passed, 4 skipped**
([validation](evidence/2026-10-22-l4-billing/VALIDATION.md)). Next: L5, commissions and tips. Next
migration **0070**.

## Previous checkpoint — 2026-10-22: L3 visit completion and material consumption, locally verified

L2c CI SUCCESS (run 39783826823). L3 designed ([design](PACKAGE_L3_DESIGN_2026-10-22.md), `2402352`)
and built in `4ed11af` on `codex/package-l3-consumption` (migration 0068): recipes per service and add-on;
completing a started visit records planned and actual materials (booking right, branch scope); posting the
consumption writes them off once through STOCK-01 (inventory and finance rights). Focused **257 passed**;
full **2487 passed, 4 skipped** ([validation](evidence/2026-10-22-l3-consumption/VALIDATION.md)). Next:
L4, visit billing. Next migration **0069**.

## Previous checkpoint — 2026-10-22: L2c visits with several services, locally verified

L2b CI SUCCESS (run 39777287553). L2c in `c32a1b0` on `codex/package-l2c-visits` (no migration): one
booking holds several services in order (`extra_lines` after the first); the composition rules apply
across the visit; one artist serves the whole visit; staff, the hold API and guests book it. Focused
**234 passed**; full **2479 passed, 4 skipped**
([validation](evidence/2026-10-22-l2c-visits/VALIDATION.md)). L2 (occupancy, guests, visits) is
complete; next: L3, visit completion and material consumption. Next migration **0068**.

## Previous checkpoint — 2026-10-22: L2b guests book staged services, locally verified

L2a CI SUCCESS (run 39765610640). L2b in `ca44785` on `codex/package-l2b-guest-stages` (no migration):
guests see a staged start only when the artist is free in their working stages and a chair, room or
processor is free for each stage that needs one; the hold places every stage, all or nothing; the web
quote parser accepts version 2 with stages. Focused **219 passed**; full **2464 passed, 4 skipped**
([validation](evidence/2026-10-22-l2b-guest-stages/VALIDATION.md)). Next: L2c, visits with several
services. Next migration **0068**.

## Previous checkpoint — 2026-10-22: L2a stage-by-stage occupancy locally verified

L1 CI SUCCESS (run 39758206502; package L plan run 39758206876). L2 designed under the owner's full
delegation ([design](PACKAGE_L2_DESIGN_2026-10-22.md), `f1403eb`). L2a in `edd0849` on
`codex/package-l2-occupancy` (migration 0067): a staged visit holds each resource only for its stages,
so the specialist is free while a colour develops and the chair stays held; all or nothing; chair,
room or equipment named or found. Staff booking, reschedule and the hold API handle staged services;
the customer site refuses them until L2b. 20 new tests; focused **214 passed**; full **2459 passed, 4
skipped** ([validation](evidence/2026-10-22-l2a-stage-occupancy/VALIDATION.md)). Next: L2b.
Next migration **0068**.

## Previous checkpoint — 2026-10-22: package L started; L1 service stages and equipment locally verified

Package L (BEAUTY-01, build order of stage 3, not a separate launch) planned under the owner's full
delegation ([plan](PACKAGE_L_PLAN_2026-10-22.md), `5eb534c`). L1 in `7ce60ef` on
`codex/package-l1-stages` (migration 0066): a service variant may have ordered stages (active,
processing, finish) with minutes and resource kinds; its duration is their sum (checked in SQL);
`equipment` is a resource kind; a variant without stages quotes exactly as before. Booking still holds
one resource per visit until L2. 21 new tests; focused **133 passed**; full **2439 passed, 4 skipped**
([validation](evidence/2026-10-22-l1-service-stages/VALIDATION.md)). Next: L2, stage-by-stage
occupancy. Next migration **0067**.

## Previous checkpoint — 2026-10-22: FIN-02 K-05 and K-12 PASS after K6

FIN-02 stays `technically_verified`; its record now names the reviewed K6r source `2eb6cf7`, schema
65: events lost on the way are fetched back by a read-only reconciler with the same facts, every run is
recorded, a failing event is retried and then parked until a finance user releases it
([K6 acceptance](evidence/2026-10-22-fin-02-k6-acceptance/ACCEPTANCE.md)). Evidence: the real sandbox
run with lost webhooks (K6c), one independent review with its fixes (K6r), CI SUCCESS on every K6 head
(K6r run 39732441848). Registry commit `47e60c5` on `codex/package-k6s-fin02-record`; full **2415
passed, 4 skipped**. Limit: the product's HTTP client still needs one call with a restricted test key
that only the owner may create. No live mode, no production approval. Next migration **0066**.

## Previous checkpoint — 2026-10-22: K6 reviewed, CI green; K6r review fixes locally verified

K6a, K6b1, K6b2 and K6c published for CI on the owner's word («Да, и то и другое»), no PR: CI SUCCESS
on all four heads (runs 39724421746, 39724425326, 39724428029, 39724431070). One independent read-only
review: APPROVE with conditions, no Critical or High ([REVIEW](evidence/2026-10-22-k6-review/REVIEW.md)).
K6r fixes R1–R8 in `2eb6cf7` on `codex/package-k6r-review-fixes` (migration 0065): focused **700
passed**; full **2415 passed, 4 skipped** ([validation](evidence/2026-10-22-k6r-review-fixes/VALIDATION.md)).
The real sandbox run K6c passed ([validation](evidence/2026-10-21-k6c-stripe-sandbox/VALIDATION.md)).
Next: the FIN-02 record and acceptance update (K-05, K-12). Next migration **0066**.

## Previous checkpoint — 2026-10-21: K6b2 delivery source and stalled operations on the screen

Code `0af2a46`, local branch `codex/package-k6b2-screen`, parent `9435e7f` (K6b1). Each delivery names
how it arrived (signed webhook or fetched by reconciliation); an operation without a final event for
over 24 hours is marked. Focused **676 passed**; full **2398 passed, 4 skipped**; npm audit NOT TESTED
(registry timeout, no dependency changed). Next: K6c, the real sandbox run.
[Validation](evidence/2026-10-21-k6b2-screen/VALIDATION.md).

## Previous checkpoint — 2026-10-21: K6b1 lost provider events reconciled from the Stripe API

Code `73f5c45`, local branch `codex/package-k6b-event-backfill`, parent `73570bd` (K6b detailed
decisions). A reconciler of one platform namespace lists each admitted connection's events from the
Stripe API and records them through the same inbox as webhooks (same facts; provenance
`stripe_api_v1` on the attestation; every run recorded, migration 0064; retries 1, 2, 4 s then a
visible failure). Tested against a local fake Stripe API; the real sandbox run is K6c. Focused
**673 passed**; full **2395 passed, 4 skipped**. FIN-02 unchanged (K-05/K-12 PARTIAL until K6c).
Next migration **0065**. [Validation](evidence/2026-10-21-k6b-event-backfill/VALIDATION.md).

## Previous checkpoint — 2026-10-21: K6a bounded retries and parked provider events (FIN-02 gaps)

Code `2f577bc`, local branch `codex/package-k6a-bounded-retries`, parent `8b8f8a3` (K6 design,
owner: «1» and «Да, все умолчания»). The receipt worker no longer lets one failing event stop its
batch or retry forever: failures are recorded (migration 0063), retried after 1, 2, 4, 8 minutes and
parked after 5; a finance user presses **Try again** with a note. Every order of a payment and its
refund (720) converges (K-05). Focused **599 passed**; full **2354 passed, 4 skipped**. FIN-02 stays
`technically_verified` with K-05/K-12 PARTIAL until K6b (event backfill) and K6c (sandbox run). Next
migration **0064**. [Validation](evidence/2026-10-21-k6a-bounded-retries/VALIDATION.md),
[K6 design](PACKAGE_K6_DESIGN_2026-10-21.md).

## Previous checkpoint — 2026-10-21: STOCK-01 technically verified; inventory may be enabled

Code `3f68e3f`, local branch `codex/package-stock01-readiness`, parent `1a8a180` (`main`, CI SUCCESS run
39536393894). On the owner's «ok» the readiness registry records **STOCK-01 `technically_verified`** for
code `ea74bec`, schema 62, citing the [2026-10-15 acceptance](evidence/2026-10-15-stock-01-acceptance/ACCEPTANCE.md)
(J-01–J-14 PASS) and the [readiness record](evidence/2026-10-20-stock-01-readiness/RECORD.md). The
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
[Acceptance](evidence/2026-10-20-fin-02-acceptance/ACCEPTANCE.md),
[handoff](NEXT_AGENT_AFTER_FIN02_2026-10-20.md), [prompt](NEXT_AGENT_AFTER_FIN02_PROMPT_2026-10-20.md).

## Previous checkpoint — 2026-10-20: K5r fixes of the K5 final review locally verified

Source `b4e69e82152961380d21761c9a100515ea1645d1`, local branch `codex/package-k5r-review-fixes`, parent `ec25a1f`. One independent
review of K5a-fix, K0b and K5b (owner's «Да, запусти») found no Critical or High issue; K5r fixes the
two Medium and the Low findings: stored operation keys with an index for the money checks (measured
~390 ms -> 0.02 ms at 100k events; an expression index was found unusable under FORCE RLS), a
suspension is final, the refund cap counts linked refunds, direction-aware "names the ID", a worker
that survives a failed batch, plus web and refusal details. Migrations 0061 (K) and 0062 (H); next
0063. Focused **787 passed in 817.60s (0:13:37)**; full **2327 passed, 4 skipped in 1907.66s
(0:31:47)**; static/web/build PASS. Not published. FIN-02 and STOCK-01 stay `planned` until the FIN-02
acceptance record. [Review](evidence/2026-10-20-k5-final-review/REVIEW.md),
[validation](evidence/2026-10-20-k5r-review-fixes/VALIDATION.md).

## Previous checkpoint — 2026-10-20: K5-CI SUCCESS after K0c

Branch `codex/package-k5b-open-findings` published for CI only (owner's trust, no PR, no `main`); exact head `e03c678` CI SUCCESS, run 39502582514, including the production image build. FIN-02 stays `planned` until its acceptance record (K-01–K-14) and one independent review of K5a-fix, K0b and K5b. [K5 plan](PACKAGE_K5_PLAN_2026-10-19.md).

## Previous checkpoint — 2026-10-20: K0c real Stripe sandbox events PASS

On `dd013fd` (no source change), owner-delegated («ты сам все делай»): Stripe sandbox
`acct_1UJtGO0mkpVWlKYX` as the Connect platform, connected test account `acct_1USjOo0mkpWSHVnd`, test
mode only. Real signed events (success, failure, refund) reached the local ingress through
`stripe listen`, were attested and decided; one payment (20.00) and one refund (1.00) were applied with
provider provenance; a Stripe resend made no second effect; a suspension refused the next deliveries
(400, nothing stored). E-02–E-05 PASS; the signing secret stayed in memory (0 in every log). Next:
K5-CI (exact-head CI; publishing needs the owner's word) and K5c (the owner's readiness decision for
FIN-02, still `planned`). [Validation](evidence/2026-10-20-k0c-stripe-sandbox/VALIDATION.md).

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
[Validation](evidence/2026-10-20-k5b-open-findings/VALIDATION.md),
[handoff](NEXT_AGENT_PACKAGE_K5B_2026-10-20.md), [prompt](NEXT_AGENT_PACKAGE_K5B_PROMPT_2026-10-20.md).

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
[Validation](evidence/2026-10-20-k0b-entry-points/VALIDATION.md),
[handoff](NEXT_AGENT_PACKAGE_K0B_2026-10-20.md), [prompt](NEXT_AGENT_PACKAGE_K0B_PROMPT_2026-10-20.md).

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
[Validation](evidence/2026-10-19-k5a-review-fixes/VALIDATION.md), [handoff](NEXT_AGENT_PACKAGE_K5A_FIX_2026-10-19.md), [prompt](NEXT_AGENT_PACKAGE_K5A_FIX_PROMPT_2026-10-19.md).

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
[Validation](evidence/2026-10-19-k3b-provider-links/VALIDATION.md), [handoff](NEXT_AGENT_PACKAGE_K3B_2026-10-19.md), [prompt](NEXT_AGENT_PACKAGE_K3B_PROMPT_2026-10-19.md).

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
[Validation](evidence/2026-10-18-k4b-provider-review/VALIDATION.md), [handoff](NEXT_AGENT_PACKAGE_K4B_2026-10-18.md), [prompt](NEXT_AGENT_PACKAGE_K4B_PROMPT_2026-10-18.md).

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
[Validation](evidence/2026-10-18-k4a-provider-screen/VALIDATION.md), [handoff](NEXT_AGENT_PACKAGE_K4A_2026-10-18.md), [prompt](NEXT_AGENT_PACKAGE_K4A_PROMPT_2026-10-18.md).

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
[Validation](evidence/2026-10-17-k3a-provider-money/VALIDATION.md), [handoff](NEXT_AGENT_PACKAGE_K3A_2026-10-17.md), [prompt](NEXT_AGENT_PACKAGE_K3A_PROMPT_2026-10-17.md).

## Previous checkpoint — 2026-10-17: K2a receipt decisions without money locally verified

Source `6e9bbfc74a09a5d472aaff25328356d6f71e8706`, local branch `codex/package-k2a-receipt-decisions`, parent `b6c8040`.
First K2 slice, by the owner's decisions of 2026-10-17: a separate `gba_receipt_worker` group turns
each attested receipt into one permanent decision (`observed` or `needs_review`) linked to one
provider operation; leases with fencing stop duplicate and expired workers; every conflict goes
to manual review; nothing touches the ledger, settlements or obligations. Migration 0050, 59 new
cases. Focused **571 passed in 478.99s (0:07:58)**; full **2154 passed, 4 skipped in 1765.52s
(0:29:25)**; a first focused gate failed (kept in the record). Not published.
FIN-02/STOCK-01 planned; ADR-0026/0027 Proposed. main=fedd0f1, published J=df88c20. Next 0051.
[Validation](evidence/2026-10-17-k2a-receipt-decisions/VALIDATION.md), [handoff](NEXT_AGENT_PACKAGE_K2A_2026-10-17.md), [prompt](NEXT_AGENT_PACKAGE_K2A_PROMPT_2026-10-17.md).

## Previous checkpoint — 2026-10-17: K1k TRUNCATE guard and random route IDs locally verified

Source `a5f21e41f550d5d07e428c644e9f718082b3f619`, local branch `codex/package-k1k-truncate-guard`, parent `ae9e1e2`.
Closes independent-review findings IR-09 and the default part of IR-08: migration 0049 refuses
TRUNCATE (also a cascade) of all six receipt tables for the owner and superusers, and route IDs
default to a random UUID. 18 new cases. Focused **512 passed in 443.01s (0:07:23)**; full
**2095 passed, 4 skipped in 1656.78s (0:27:36)**. Not published.
FIN-02/STOCK-01 planned; ADR-0026/0027 Proposed. main=fedd0f1, published J=df88c20. Next 0050.
[Validation](evidence/2026-10-17-k1k-truncate-guard/VALIDATION.md), [handoff](NEXT_AGENT_PACKAGE_K1K_2026-10-17.md), [prompt](NEXT_AGENT_PACKAGE_K1K_PROMPT_2026-10-17.md).

## Previous checkpoint — 2026-10-17: K1j revocation record locally verified

Source `201847856aa768bbeb25751d5b219e154383c293`, local branch `codex/package-k1j-revocation-record`, parent `84bc4d7`.
Closes independent-review finding IR-07: migration 0048 makes a revocation of a receipt
connection or verification config name its reason (rotation, compromise, retired) and records
when and by which login; the record is permanent, earlier revocations keep an empty record, and
attestations and configs record the login behind `SET ROLE`. 21 new cases. Focused **494 passed
in 358.27s (0:05:58)**; full **2077 passed, 4 skipped in 1598.78s (0:26:38)**. Not published.
FIN-02/STOCK-01 planned; ADR-0026/0027 Proposed. main=fedd0f1, published J=df88c20. Next 0049.
[Validation](evidence/2026-10-17-k1j-revocation-record/VALIDATION.md), [handoff](NEXT_AGENT_PACKAGE_K1J_2026-10-17.md), [prompt](NEXT_AGENT_PACKAGE_K1J_PROMPT_2026-10-17.md).

## Previous checkpoint — 2026-10-17: K1i stock posting plans independent of statistics locally verified

Source `42ead59a3ff975d0daa6ee294af6b34b2b8ce5ff`, local branch `codex/package-k1i-stock-plan-stability`, parent `0760553`.
Fixes the K1h finding: with statistics that did not describe a company, one stock document's
checks could read the whole history. Migration 0047 makes the history keys unusable for a company
predicate, reads source documents by key and drops history-key equalities from the line check; the
inventory guard approves the new indexes. 5 new cases; at most 1 row per stock-table node with a
100,016-row history (red: 100,031). Focused **473 passed in 329.46s (0:05:29)**; full **2056 passed,
4 skipped in 1556.26s (0:25:56)**; a first full run failed (kept in the record). Not published.
FIN-02/STOCK-01 planned; ADR-0026/0027 Proposed. main=fedd0f1, published J=df88c20. Next 0048.
[Validation](evidence/2026-10-17-k1i-stock-plan-stability/VALIDATION.md), [handoff](NEXT_AGENT_PACKAGE_K1I_2026-10-17.md), [prompt](NEXT_AGENT_PACKAGE_K1I_PROMPT_2026-10-17.md).

## Previous checkpoint — 2026-10-17: K1g receipt guard additions locally verified

Source `4401a2e7bcdc716eaa5664285c0ca383ddf77163`, local branch `codex/package-k1g-guard-additions`, parent `af26f1d`.
Closes independent-review finding IR-05: the receipt schema guard now checks group membership
topology, K table shape and ACLs, function ACLs and the RLS context functions. No migration.
10 new cases. Focused **468 passed in 294.65s (0:04:54)**; full **2052 passed, 4 skipped in
2011.34s (0:33:31)**; a first full run failed once on the pre-existing, near-limit
`test_stock_scale` timing check (kept in the record). Not published.
FIN-02/STOCK-01 planned; ADR-0026/0027 Proposed. main=fedd0f1, published J=df88c20. Next 0047.
[Validation](evidence/2026-10-17-k1g-guard-additions/VALIDATION.md), [handoff](NEXT_AGENT_PACKAGE_K1G_2026-10-17.md), [prompt](NEXT_AGENT_PACKAGE_K1G_PROMPT_2026-10-17.md).

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
[Validation](evidence/2026-10-17-k1f-bootstrap-hardening/VALIDATION.md),
[handoff](NEXT_AGENT_PACKAGE_K1F_2026-10-17.md), [prompt](NEXT_AGENT_PACKAGE_K1F_PROMPT_2026-10-17.md).

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
NOT TESTED/BLOCKED. FIN-02/STOCK-01 planned; ADR-0026/0027 Proposed. K local only;
main=fedd0f1, published J=df88c20. Next 0047.
[Validation](evidence/2026-10-16-k1e-http-ingress/VALIDATION.md),
[review](evidence/2026-10-16-k1e-http-ingress/INDEPENDENT_REVIEW_K1A_K1D.md),
[handoff](NEXT_AGENT_PACKAGE_K1E_2026-10-16.md), [prompt](NEXT_AGENT_PACKAGE_K1E_PROMPT_2026-10-16.md).

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
[Validation](evidence/2026-10-16-k1d-receipt-routing/VALIDATION.md),
[handoff](NEXT_AGENT_PACKAGE_K1D_2026-10-16.md), [prompt](NEXT_AGENT_PACKAGE_K1D_PROMPT_2026-10-16.md).

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
[Validation](evidence/2026-10-15-k1b-receipt-inbox/VALIDATION.md),
[handoff](NEXT_AGENT_PACKAGE_K1B_2026-10-15.md),
[prompt](NEXT_AGENT_PACKAGE_K1B_PROMPT_2026-10-15.md).

## Previous checkpoint — 2026-10-15: K1a offline boundary locally verified; not published

K1a source `7d25aa2d72874271a62e363817e0624fb502497c` on `codex/package-k1a-event-boundary`: signature-first strict
test snapshot decoding with stripe16.0.0, 96 synthetic tests. Static/build/web114 PASS;
focused **191 passed in 53.85s**; full **1844 passed, 4 skipped in 1444.23s (0:24:04)** on fresh disposable PostgreSQL.
No HTTP route/inbox/worker/schema or money effect; full K1 and K acceptance NOT TESTED.
Provider admission is BLOCKED by separate authorization; K push/CI NOT TESTED.
FIN-02/STOCK-01 stay planned, ADR-0026/0027 Proposed; main remains fedd0f1.
Runtime npm audit0; existing development audit5high FAIL. No provider/credential action.
[K1a record](evidence/2026-10-15-k1a-event-boundary/VALIDATION.md), [handoff](NEXT_AGENT_PACKAGE_K1A_2026-10-15.md).

## Previous checkpoint — 2026-10-15: Package K proposed locally; provider gate closed

The next stage-2 package K / FIN-02 now has a local implementation and acceptance
proposal on `codex/package-k-plan`, based on `df88c20687333668d39fe76a26eabca691e62cb0`.
Documentation only: no K route, worker, schema, dependency or provider operation.
K-01–K-14 are NOT TESTED; actual Stripe test admission is BLOCKED by the separate
provider/credential authorization rule. The K branch is not authorized for push.
FIN-02 and STOCK-01 stay planned; ADR-0026/0027 Proposed. Main remains fedd0f1.
Published J exact-head CI 158 PASS; its accepted technical evidence is preserved.
[K plan](PACKAGE_K_PLAN_2026-10-15.md),
[reuse and validation](evidence/2026-10-15-package-k-plan/ARCHITECTURE_REUSE.md),
[current handoff](NEXT_AGENT_PACKAGE_K_PLAN_2026-10-15.md).

## Previous checkpoint — 2026-10-15: STOCK-01 technical evidence PASS; readiness unchanged

J-01–J-14 technical evidence PASS against `aedbb982a696052d606499f737b1754fce362b6a` with exact CI run 157
success. Full local **PASS: 1748 passed, 4 skipped in 1448.82s (0:24:08)**. STOCK-01 remains planned,
ADR-0026 Proposed; readiness requires the owner's separate explicit authorization. Main
remains fedd0f1. No PR, merge, deployment or production changes. The acceptance documentation
commit needs its own exact-head CI read; api/web source trees are unchanged and recorded.
[Acceptance](evidence/2026-10-15-stock-01-acceptance/ACCEPTANCE.md),
[handoff](NEXT_AGENT_PACKAGE_J_REVIEW2_FIXES_2026-10-14.md).

## Previous checkpoint — 2026-10-15: Package J review fixes part 2 locally verified; acceptance pending

M1, L2, L3 and the two-source destination-insert race are fixed in `7b96fec` on
`codex/package-j-review2-fixes`. Full local **PASS: 1748 passed, 4 skipped in 1448.82s (0:24:08)**. Static/focused PASS;
114 web tests; production audit 0, existing development audit 5 high. No migration or
dependency changed. Exact new CI NOT TESTED at this pre-publication checkpoint.
STOCK-01 remains planned, ADR-0026 Proposed; technical acceptance J-01–J-14 is next.
Main remains fedd0f1. L1/L4 are recorded limits, not fixes.

[Current handoff](NEXT_AGENT_PACKAGE_J_REVIEW2_FIXES_2026-10-14.md), [part-2 record](evidence/2026-10-14-j5-j6-review-fixes-part2/VALIDATION.md).

## Previous checkpoint — 2026-10-14: review of J5 and J6 done; H1 fixed (part 1); not merged

Независимый обзор J5 и J6 проведён: высокая находка H1 (подделка остатка проходила проверку
0042 при смене контекста перед фиксацией) исправлена миграцией 0043: `f366afe` на ветке
`codex/package-j-review2-fixes`. Полный локальный прогон — **PASS: 1746 passed, 4 skipped in 1428.69s (0:23:48)**. Ветка J6 опубликована, CI её
вершины `b3982ba` — PASS. Открыты M1, L2, L3 и тест гонки (часть 2), затем приёмка.
CI этой ветки на момент записи — NOT TESTED. `main` не переносился.

[Актуальный handoff](NEXT_AGENT_PACKAGE_J_REVIEW2_FIXES_2026-10-14.md),
[запись обзора](evidence/2026-10-14-j5-j6-review/REVIEW.md).

## Previous checkpoint — 2026-10-14: package J acceptance preparation (J6) committed; M2 fixed; not merged

Находка M2 независимого обзора измерена и устранена миграцией 0042: при 100 000 движений
одной строки остатка проводка шла 960 мс, теперь 43 мс (45 мс без истории). Добавлены
тесты строк J-12 и J-13 и пробела 10; закоммичено `35227cd` на ветке `codex/package-j-acceptance-prep`.
Полный локальный прогон — **PASS: 1745 passed, 4 skipped in 1646.70s (0:27:26)**. Ветка J5b опубликована, CI её вершины
`f521528` — PASS. Открыты независимый обзор J5 и J6 и сама приёмка STOCK-01. CI этой
ветки на момент записи — NOT TESTED. `main` не переносился.

[Актуальный handoff](NEXT_AGENT_PACKAGE_J6_ACCEPTANCE_PREP_2026-10-14.md),
[запись о срезе](evidence/2026-10-14-j6-acceptance-prep/VALIDATION.md).

## Previous checkpoint — 2026-10-14: package J slice J5b (Stock documents screen) committed; J5 complete; not merged

Вторая часть среза J5 — экран «Складские документы» (`/stock-documents/`) —
закоммичена: `c3da59d` на ветке `codex/package-j5b-stock-documents`; срез J5 завершён. Полный локальный
прогон — **PASS: 1735 passed, 4 skipped in 1587.30s (0:26:27)**. Browser-тест на компьютере и телефоне: доступность без
нарушений, потеря ответа без второго документа, отказ с названной причиной, менеджер
филиала — только перемещения и без сумм. Ветка J5a опубликована, CI её вершины `b003b75`
— PASS. Открыты M2, L6, тесты J-12 и J-13, обзор J5 и приёмка. CI этой ветки на момент
записи — NOT TESTED. `main` не переносился.

[Актуальный handoff](NEXT_AGENT_PACKAGE_J5B_STOCK_DOCUMENTS_2026-10-14.md),
[запись о срезе](evidence/2026-10-14-j5b-stock-documents/VALIDATION.md).

## Previous checkpoint — 2026-10-14: package J slice J5a (Materials screen) committed; not merged

Первая часть среза J5 — экран «Материалы» (`/materials/`) и проверка неопределённой
команды запасов по ключу — закоммичена: `afda55b` на ветке `codex/package-j5-screens`. Полный
локальный прогон — **PASS: 1734 passed, 4 skipped in 1279.06s (0:21:19)**. Browser-тест на компьютере и телефоне: доступность
без нарушений, потеря ответа и её проверка после перезагрузки, повтор тем же ключом,
отмена с отказом поздней копии. Ветка исправлений по обзору опубликована, CI её
вершины `5e3a801` — PASS. Открыты J5b «Складские документы», M2, L6 и приёмка. CI этой
ветки на момент записи — NOT TESTED. `main` не переносился.

[Актуальный handoff](NEXT_AGENT_PACKAGE_J5_MATERIALS_2026-10-14.md),
[запись о срезе](evidence/2026-10-14-j5-screens/VALIDATION.md).

## Previous checkpoint — 2026-10-14: package J review fixes committed; J1–J4 published

Независимый обзор J1–J4 проведён; его находки M1, L1, L2, L4, L5 и часть L3 исправлены и
закоммичены: `33a3ec6` на ветке `codex/package-j-review-fixes`. Главное — перемещение и приёмка
больше не блокируют друг друга намертво; строки остатка и стоимости существуют только
через документы (миграция 0041). Полный локальный прогон — **PASS: 1724 passed, 4 skipped in 1300.24s (0:21:40)**. Предел времени CI поднят до 45 минут. Открыты M2 и L6, экраны (J5) и
приёмка. Владелец 2026-10-14 передал исполнителю три вопроса обзора: «Делай, как ты считаешь нужным. Я доверяю полностью тебе, и ты принимаешь решение.»
CI этой ветки на момент записи — NOT TESTED. `main` не переносился.

[Актуальный handoff](NEXT_AGENT_PACKAGE_J_REVIEW_FIXES_2026-10-14.md),
[запись об исправлениях](evidence/2026-10-14-j-review-fixes/VALIDATION.md),
[запись обзора](evidence/2026-10-13-j-review/REVIEW.md).

## Previous checkpoint — 2026-10-13: package J slice J4 (transfers and returns) published; CI success; not merged

**Обновление 2026-10-13: независимый обзор J1–J4 проведён.** Блокирующих находок нет; две
средние и шесть низких находок не исправлены. Следующий шаг — исправить их в новой ветке от
этой вершины: [запись обзора](evidence/2026-10-13-j-review/REVIEW.md). Строки ниже о том,
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

[Актуальный handoff](NEXT_AGENT_PACKAGE_J4_RETURNS_2026-10-13.md),
[готовый prompt](NEXT_AGENT_PACKAGE_J4_RETURNS_PROMPT_2026-10-13.md),
[запись о срезе](evidence/2026-10-13-j4-returns/VALIDATION.md),
[план пакета J](PACKAGE_J_PLAN_2026-10-13.md),
[ADR-0026 (Proposed)](../adr/0026-materials-and-stock-movements.md).

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

[Актуальный handoff](NEXT_AGENT_PACKAGE_J4_TRANSFERS_2026-10-13.md),
[готовый prompt](NEXT_AGENT_PACKAGE_J4_TRANSFERS_PROMPT_2026-10-13.md),
[запись о срезе](evidence/2026-10-13-j4-transfers/VALIDATION.md),
[план пакета J](PACKAGE_J_PLAN_2026-10-13.md),
[ADR-0026 (Proposed)](../adr/0026-materials-and-stock-movements.md).

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

[Актуальный handoff](NEXT_AGENT_PACKAGE_J3_2026-10-13.md),
[готовый prompt](NEXT_AGENT_PACKAGE_J3_PROMPT_2026-10-13.md),
[запись о срезе](evidence/2026-10-13-j3-writeoffs/VALIDATION.md),
[план пакета J](PACKAGE_J_PLAN_2026-10-13.md),
[ADR-0026 (Proposed)](../adr/0026-materials-and-stock-movements.md).

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

[Актуальный handoff](NEXT_AGENT_PACKAGE_J2_2026-10-13.md),
[готовый prompt](NEXT_AGENT_PACKAGE_J2_PROMPT_2026-10-13.md),
[запись о срезе](evidence/2026-10-13-j2-receipts/VALIDATION.md),
[план пакета J](PACKAGE_J_PLAN_2026-10-13.md),
[ADR-0026 (Proposed)](../adr/0026-materials-and-stock-movements.md).

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

[Актуальный handoff](NEXT_AGENT_PACKAGE_J1_2026-10-13.md),
[готовый prompt](NEXT_AGENT_PACKAGE_J1_PROMPT_2026-10-13.md),
[запись о срезе](evidence/2026-10-13-j1-materials/VALIDATION.md),
[план пакета J](PACKAGE_J_PLAN_2026-10-13.md),
[ADR-0026 (Proposed)](../adr/0026-materials-and-stock-movements.md).

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

[Актуальный handoff](NEXT_AGENT_PACKAGE_J_PLAN_2026-10-13.md),
[готовый prompt](NEXT_AGENT_PACKAGE_J_PLAN_PROMPT_2026-10-13.md),
[план пакета J](PACKAGE_J_PLAN_2026-10-13.md),
[ADR-0026 (Proposed)](../adr/0026-materials-and-stock-movements.md).

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

[Актуальный handoff](NEXT_AGENT_WORKFORCE_SCREENS_2026-10-13.md),
[готовый prompt](NEXT_AGENT_WORKFORCE_SCREENS_PROMPT_2026-10-13.md),
[запись о срезе](evidence/2026-10-13-workforce-screen-situations/VALIDATION.md).

## Previous checkpoint — 2026-10-12: main fast-forwarded to the head of the stack

`main` перенесён с `46cd866` на `8a34a80` одним обычным push без force по решению владельца
от 2026-10-12. В `main` теперь вся основная линия: 113 коммитов, миграции 0001–0035.
CI на `main`: **PASS**, [run 38338644832](https://github.com/alexeyalexandrov2026-tech/GORGONA-Booking-Platform_new/actions/runs/38338644832) на `8a34a80`: задание 1108 с, pytest 958 с; текст логов не читался.
Ничего не развёрнуто; статусы готовности не менялись. PR #2–#5 признаны заменёнными и не
сливаются. Страницы PR: отмечены как слитые: #1; закрыты без слияния: нет; остаются открытыми: #2, #3, #4, #5, #6, #7, #8, #9, #10, #11, #12, #13, #14, #15, #16, #17, #18, #19, #20, #21, #22.

Новая работа начинается от `main`. Запись о выполнении лежит на ветке `codex/merge-plan`, на один
коммит документов впереди `main`.

[Handoff после переноса `main`](NEXT_AGENT_AFTER_MERGE_2026-10-12.md),
[готовый prompt](NEXT_AGENT_AFTER_MERGE_PROMPT_2026-10-12.md),
[план слияния и его выполнение](MERGE_PLAN_2026-10-12.md).

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
([план](MERGE_PLAN_2026-10-12.md)); PR #2–#5 считаются заменёнными и не сливаются. Где сейчас
`main`, читать из `git ls-remote origin main`; запись о выполнении — на ветке `codex/merge-plan`.

[Handoff среза аудита](NEXT_AGENT_WEB_DEPENDENCY_AUDIT_2026-10-12.md),
[готовый prompt](NEXT_AGENT_WEB_DEPENDENCY_AUDIT_PROMPT_2026-10-12.md),
[запись о срезе](evidence/2026-10-12-web-dependency-audit/VALIDATION.md).

## Previous checkpoint — 2026-10-12: package I accepted technically; WORK-01 and CORE-04 verified

WORK-01 записан как `technically_verified` на коде `f41f9a8`. Модуль `workforce` стал
включаемым: компания получает его, только опубликовав конфигурацию с ним. CORE-04
записан как `technically_verified` отдельным коммитом `1b925f1` по основаниям пакета F.
ADR-0025 — Accepted as implemented. Решение: 2026-10-12 владелец поручил исполнителю
выбирать самостоятельно и на предложение выполнить приёмку ответил «Continue»;
трактовка записана в [записи о приёмке](evidence/2026-10-12-work-01-acceptance/ACCEPTANCE.md).

Проверки дерева приёмки: full local **PASS: 1531 passed, 4 skipped in 972.96s (0:16:12)**; Ruff, format и mypy PASS на
265 файлах; web typecheck, lint, format, 102 unit и 23 страницы PASS; независимая
проверка изменения PASS. CI коммита приёмки: **PASS**, [run 38236481277](https://github.com/alexeyalexandrov2026-tech/GORGONA-Booking-Platform_new/actions/runs/38236481277) на `75f2b9b`: задание 1037 с, pytest 899 с; текст логов не читался.
Production audit **FAIL: 2 high** (next, source-map-js).

Это техническая приёмка. Пилота и разрешения на production нет. PR и merge не
выполнялись; миграции и зависимости не менялись. Утверждения ниже о том, что
WORK-01 или CORE-04 planned, а workforce закрыт, относятся к своим датам.

[Handoff приёмки](NEXT_AGENT_PACKAGE_I_CORRECTIONS_2026-10-12.md),
[готовый prompt](NEXT_AGENT_PACKAGE_I_PROMPT_2026-10-12.md),
[запись о приёмке](evidence/2026-10-12-work-01-acceptance/ACCEPTANCE.md),
[независимая проверка](evidence/2026-10-12-work-01-acceptance/INDEPENDENT_CHECK.md),
[предыдущий срез: исправления и публикация](evidence/2026-10-12-i4-review-corrections/FOLLOWUP_VALIDATION.md).
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

[Актуальный handoff](NEXT_AGENT_PACKAGE_I_CORRECTIONS_2026-10-12.md),
[готовый prompt](NEXT_AGENT_PACKAGE_I_PROMPT_2026-10-12.md),
[evidence и точные ограничения](evidence/2026-10-12-i4-review-corrections/VALIDATION.md).
Ниже сохранены исторические срезы. Их инструкции/результаты не заменяют текущий
handoff и не означают, что dirty corrections входят в HEAD490652b.

**H acceptance checkpoint, 9 October:** FIN-03 is `technically_verified` on code
`319f144` by the owner's decision, after exact-SHA CI, the recorded reviews and an
independent audit. [Acceptance](evidence/2026-10-09-h-acceptance/ACCEPTANCE.md),
[audit](evidence/2026-10-09-h-acceptance-audit/AUDIT.md),
[handoff](NEXT_AGENT_H_ACCEPTANCE_2026-10-09.md). `finance_documents` is enableable
by a company's own published configuration. FIN-02 remains planned. No merge,
deployment or production migration is authorized. Earlier H checkpoint statements
below are historical for their source and date.

**Historical H4/UI checkpoint, 8 October:** branch `codex/package-h4-ui-admission` from
F1–F5 parent PR21 `12875e8` adds Financial documents UI and provider admission
metadata without activation. Reuses the existing H APIs/G ledger and adds only
forward 0031. [Current evidence](evidence/2026-10-08-h4-ui-admission/VALIDATION.md),
[H matrix](evidence/2026-10-08-h4-ui-admission/H_ACCEPTANCE_MATRIX.md),
[handoff](NEXT_AGENT_H4_UI_ADMISSION_2026-10-08.md).
FIN-03/FIN-02 remain planned; production H registry stays closed. Full tests,
independent review and final exact-SHA CI are separate evidence gates. Earlier
H checkpoint statements below are historical for their source/date.

**Historical H1 backend checkpoint, 6 October:** reviewed source2d5a8f9 on
codex/package-h1-persistence adds forward0021 and real invoice draft/history/
atomic issue with one obligation and balanced G accrual. Journal read-v2 and
permanent minimal recovery are implemented. [Draft PR15](https://github.com/alexeyalexandrov2026-tech/GORGONA-Booking-Platform_new/pull/15)
targets foundation PR14. Root full953/4skip and independent47 PG/109 units PASS;
H1-R01 closed. [Current handoff](NEXT_AGENT_H1_BACKEND_2026-10-06.md),
[evidence](evidence/2026-10-06-h1-backend/VALIDATION.md).
FIN-03/02 remain planned and finance_documents closed; H2 settlements, H3
credits/refunds and H4 invoice UI/admission remain ahead. Local progression
and draft publication are authorized; no production/provider acceptance.
Earlier planning statements are historical for their SHA.

**Historical H1 foundation, 6 октября:** после указания владельца продолжить опубликован план PR13
и создана ветка codex/package-h-invoices. Контракты, денежная арифметика и
закрытый finance_documents/registry2 проверены на source843d0b3. Это основа;
полный H1 еще IN PROGRESS, FIN-03/02 planned. [Передача H1](NEXT_AGENT_PACKAGE_H1_2026-10-06.md),
[фактические проверки](evidence/2026-10-06-h1-foundation/VALIDATION.md).

**Продолжение H, 6 октября:** подготовлены
[план](PACKAGE_H_PLAN_2026-10-06.md) и
[ADR-0024 Proposed](../adr/0024-invoices-obligations-and-external-settlements.md)
на основе принятого G5be6e7a: счета, обязательства, резервы, частичные внешние
подтверждения, credits/refund и admission без activation. Это предложение;
FIN-03/02 planned, код/приемка H не заявляются. Платеж и выручка остаются
отдельными источниками. Независимый обзор предложенного дизайна PASS;
объем H ожидает решения владельца. [Проверки](evidence/2026-10-06-package-h-plan/VALIDATION.md),
[передача H](NEXT_AGENT_PACKAGE_H_2026-10-06.md).

**Исправленная версия от 4 октября 2026 года.** Этот документ объединяет предыдущие требования и последние дополнения. Он заменяет прежние варианты плана, сохраняя весь согласованный функциональный охват.

**Цель:** создать одну платформу, в которой индивидуальный специалист, малый бизнес, сеть, франшиза или корпорация смогут организовать работу через общие инструменты и подходящие отраслевые модули.

**Продолжение G, 6 октября:** согласованный этап 2 начинается финансовой основой
FIN-01 по ADR-0023: книги юридических лиц, план счетов, проводки, сторно, месячные
периоды и раздельная по валютам ведомость. Реальные API/UI реализованы локально;
готовность technically_verified на evidence `95a0de4` (local 858 PASS, CI 861 PASS,
независимые обзоры в своих пределах). Finance включается публикацией конфигурации;
приемочный HEAD требует свежего CI в PR #12. [Передача G](NEXT_AGENT_PACKAGE_G_2026-10-06.md),
[доказательства](evidence/2026-10-06-ledger/ACCEPTANCE.md). Пакеты H–K и промышленная
приемка остаются отдельными. Старые следующие шаги ниже относятся к своим датам/SHA.

**Продолжение E3, 5 октября:** договоры с контрагентами (версии только для
вставки, подписание вне платформы с отметкой, дополнения, расторжение последней
подписанной версии, в том числе с будущей датой) — внутри модуля counterparties.
[Передача E3](NEXT_AGENT_PACKAGE_E3_2026-10-05.md),
[проверки](evidence/2026-10-05-agreements/ACCEPTANCE.md). Следующий — план CORE-04.

**Следующий шаг E2-A, 5 октября:** реализован ограниченный валидатор файлов и
исправлено сохранение защитных API-заголовков. Это не готовый модуль документов:
хранение, загрузка/скачивание и UI впереди, documents остается planned.
[Передача E2-A](NEXT_AGENT_E2_FILE_VALIDATION_2026-10-05.md),
[проверки](evidence/2026-10-05-file-validation/ACCEPTANCE.md).

**Продолжение от 5 октября 2026:** пакет E1 добавляет общие карточки контрагентов,
контакты, ручные решения о дублях и подтвержденные связи с записями. Точные
проверки и разрешение включения модуля — в [приемке E1](evidence/2026-10-05-counterparties/ACCEPTANCE.md)
и [актуальной передаче](NEXT_AGENT_PACKAGE_E1_2026-10-05.md). Документы E2,
договоры E3 и общая занятость CORE-04 впереди; этап 1 остается частичным.
Все 39 направлений и 28 критериев сохраняются. Исторические проверки ниже
относятся к своим SHA и не подтверждают готовность всей платформы.

**Основной репозиторий по решению владельца 2026-10-04:** [GORGONA-Booking-Platform_new](https://github.com/alexeyalexandrov2026-tech/GORGONA-Booking-Platform_new). Сохранение исходной работы, истории и отдельные проверки переноса описаны в [отчете перехода](REPOSITORY_TRANSITION_2026-10-04.md).

**Граница проекта, уточненная владельцем:** здесь разрабатывается самостоятельная универсальная платформа GORGONA. KA Nails — отдельный проект; его разработка, запуск и приемка не входят в этот план. Унаследованные документы и тестовые примеры других проектов не создают зависимость платформы от них.

**Историческая проверка юридических лиц от 4 октября:** [аудит](GORGONA_PLAN_AUDIT_2026-10-04.md) сопоставляет все 28 критериев с исходниками и доказательствами. Общая основа выполнена частично; обход клиентских правил через development endpoint исправлен и проверен. [Черновики юридических лиц](evidence/2026-10-04-legal-entities/ACCEPTANCE.md) технически проверены на `d97924f`: 413 Python tests и 11 web unit прошли, один дополнительный внешний site gate пропущен. Этот исторический пакет не закрывает этап 1 и не означает готовности полных отраслевых циклов. Актуальное продолжение E1 и дальнейшие шаги указаны выше и в реестре.

---

## 1. Основные решения

**Статус документа:** целевая спецификация и последовательность разработки, утвержденные владельцем для начала локальной реализации. Это не заявление о готовности перечисленных модулей. Фактические результаты каждого изменения ведутся в [реестре реализации](GORGONA_IMPLEMENTATION_STATUS.md). Приоритет: последние решения владельца → этот план → принятые ADR → исторические материалы. [ADR-0012](../adr/0012-azure-hosting.md) остается решением о размещении в Azure. Архитектура камер Local Gateway относится к отдельному продукту наблюдения и не заменяет архитектуру Booking.

1. **Сохранить существующее.** Общий движок записи, услуги, специалисты, расписания, клиентские сценарии и опубликованные API сохраняют совместимость.
2. **Расширять без дублирования.** Новые направления используют общие справочники, документы, финансовую основу и управление ресурсами.
3. **Поддерживать несколько видов деятельности одновременно.** Компания может сочетать услуги, торговлю, аренду, обучение, производство и перевозки.
4. **Разрабатывать собственные основные модули.** Интеграции дополняют платформу и помогают переносить работу из существующих систем.
5. **Начать с рынка США.** Предусмотреть дальнейшее расширение стран, языков, валют и правил.
6. **GORGONA остается поставщиком программной платформы и посредником.** Перевозки, товары, склады, производство и недвижимость принадлежат компаниям-клиентам.
7. **Разделять финансовую ответственность компаний.** Каждый бизнес принимает платежи своих клиентов через собственное подключение.
8. **Монетизация GORGONA:** подписка и оплата использования. Комиссия маркетплейса на первом этапе отсутствует.
9. **Предусмотреть индивидуальные витрины и общий маркетплейс GORGONA.** Также поддерживать компании, управляющие собственными маркетплейсами.
10. **Офлайн-режим:** чтение разрешенных данных и подготовка черновиков. Подтверждение операций выполняется после подключения к серверу.
11. **Регулируемые отрасли сохраняются в охвате.** Специализированные операции запускаются после необходимых проверок, интеграций и отраслевой приемки.
12. **Готовность подтверждается рабочими сценариями.** Название отрасли в каталоге само по себе не является подтверждением ее поддержки.
13. **Один запуск для всех 39 направлений (решение владельца 2026-10-20).** Платформа выходит в промышленную эксплуатацию сразу для всех направлений каталога; компания любого направления регистрируется и работает без ожидания «своей очереди». Платформа не привязана к салонам или иной одной отрасли. Проверки, интеграции и приемка регулируемых операций (п. 11) выполняются до этого общего запуска, а не после него.

---

## 2. Текущее состояние и рыночные ориентиры

### 2.1. Что подтверждено в проекте

В проверенном исходном проекте есть основа салонного бизнеса:

- Каталог услуг, вариантов и совместимых дополнений.
- Расчет стоимости и продолжительности.
- Мастера и доступность.
- Удержание времени, подтверждение, отмена и перенос записи.
- Управленческие страницы календаря, записей, услуг, сотрудников, клиентов и настроек.
- Разделение компаний и основа аутентификации.

Полноценные модули логистики, строительства, аренды, ресторанной работы, бухгалтерии и корпоративного управления пока не подтверждены.

**Недельная доступность мастера пока не равна системе управления сменами. История клиентов по записям пока не равна полноценной CRM.**

На исходной версии перед расширением выявлены следующие проблемы; их исправление и проверки фиксируются отдельно в реестре реализации:

- Расхождение нумерации дней недели между интерфейсом и сервером.
- Использование границ дня в UTC вместо локального дня бизнеса.
- Отображение стоимости подтвержденных записей как выручки без подтверждения оплаты.
- Недостаточную детализацию прав по филиалам и новым предметным областям.
- Связи данных, которые необходимо дополнительно закрепить принадлежностью компании.

### 2.2. Что берем из анализа рынка

| Класс систем | Проверенные ориентиры | Требование для GORGONA |
|---|---|---|
| Универсальные бизнес-системы | [Odoo](https://www.odoo.com/all-industries), [Zoho One](https://www.zoho.com/one/applications/web.html) | Общая основа и подключаемые функции |
| Управление финансами и операциями | [Microsoft Dynamics 365 Business Central](https://www.microsoft.com/en/dynamics-365/products/business-central) | Связанные продажи, закупки, проекты, запасы и учет |
| Рестораны и продажи | [Square for Restaurants](https://squareup.com/us/en/point-of-sale/restaurants) | Столики, заказы, кухня, расчеты и клиентская история |
| Графики и персонал | [Fourth / HotSchedules](https://www.fourth.com/solution/workforce-management-software/scheduling) | Смены, доступность, обмен сменами, часы и согласования |
| Beauty | [Vagaro](https://www.vagaro.com/pro/salon-software) | Запись, продажи, материалы, персонал, лояльность и сети |
| Брокеры и 3PL | [DAT](https://www.dat.com/solutions/transportation-tms) | Грузы, перевозчики, ставки, отслеживание и документы |
| Траковый бизнес | [TruckingOffice](https://www.truckingoffice.com/tms/trucking-software-features/driver-settlement-management/) | Рейсы, расходы и расчеты с водителями |
| Строительство | [Procore](https://www.procore.com/project-financials/contract-management) | Договоры, изменения, согласования и оплата этапов |
| Автоаренда | [HQ Rental Software](https://hqrentalsoftware.com/) | Автопарк, договоры, выдача, возврат и осмотры |
| Недвижимость | [Buildium](https://www.buildium.com/portfolios/residential-property-management/) | Арендаторы, договоры, обслуживание и собственники |
| Юридические фирмы | [Clio](https://www.clio.com/features/) | Дела, документы, сроки, время и счета |
| Маркетплейсы | [Mirakl](https://www.mirakl.com/products/marketplace-platform/) | Управление независимыми продавцами и предложениями |

**Вывод для архитектуры GORGONA:** объединить общие данные и управление, сохранив отдельные полноценные процессы каждой отрасли. Эта рекомендация следует из сопоставления рассмотренных систем; она не является заявлением об одинаковых возможностях всех конкурентов.

---

## 3. Полный каталог направлений

Сохранить номера и содержание первоначальных 36 разделов. Уточнения добавлять внутри соответствующего раздела. Новые самостоятельные направления добавлять следующими номерами.

| № | Направление | Какие компании и специалисты включены |
|---|---|---|
| 1 | Красота и персональный уход | Салоны, барбершопы, ногтевые студии, косметические кабинеты, SPA, массаж, татуировки, пирсинг, выездные мастера |
| 2 | Рестораны и общепит | Рестораны любого размера, сети, кафе, бары, кофейни, пекарни, фудтраки, кейтеринг, кухни доставки |
| 3 | Розничная торговля | Продукты, одежда, косметика, электроника, мебель, цветы, стройматериалы, специализированные магазины |
| 4 | Интернет-торговля | Интернет-магазины, цифровые товары, подписки, продавцы внешних маркетплейсов |
| 5 | Оптовая торговля | Дистрибьюторы, поставщики продуктов, материалов, оборудования и запчастей |
| 6 | Юридические услуги | Юридические фирмы, адвокаты, иммиграционные практики, нотариальные услуги |
| 7 | Бухгалтерия и налоги | Бухгалтеры, аудиторы, налоговые консультанты, аутсорсинговые фирмы |
| 8 | Консалтинг | Управленческие, финансовые, кадровые и отраслевые консультанты |
| 9 | Маркетинг и творческие услуги | Агентства, дизайнеры, фотографы, видеостудии, продакшены |
| 10 | IT и программное обеспечение | Разработчики, SaaS-компании, интеграторы, IT-поддержка |
| 11 | Медиа и телекоммуникации | Издательства, цифровой контент, медиакомпании, провайдеры связи |
| 12 | Образование | Репетиторы, школы, колледжи, учебные центры, автошколы, онлайн-курсы |
| 13 | Спорт и фитнес | Залы, студии, тренеры, спортивные школы, площадки и клубы |
| 14 | Медицина и реабилитация | Кабинеты, клиники, стоматологии, лаборатории, терапевты, медицинская косметология |
| 15 | Ветеринария и услуги для животных | Ветклиники, груминг, дрессировка, гостиницы для животных |
| 16 | Социальные услуги и уход | Уход на дому, помощь пожилым, детские центры, службы поддержки |
| 17 | Гостиницы и туризм | Отели, курорты, гостиницы, турагентства, экскурсионные компании |
| 18 | События, культура и развлечения | Организаторы, площадки, театры, музеи, развлекательные центры |
| 19 | Строительство и проектирование | Генподрядчики, субподрядчики, ремонтные фирмы, архитекторы, инженеры, девелоперы |
| 20 | Выездные и бытовые услуги | Электрики, сантехники, HVAC, ремонт техники, садовники, монтажники |
| 21 | Автомобильный бизнес | Автосервисы, шиномонтаж, детейлинг, автомойки, дилеры |
| 22 | Недвижимость | Риелторы, управляющие компании, аренда жилья и коммерческих объектов, коворкинги |
| 23 | Аренда и прокат | Автомобили, грузовики, оборудование, инструменты, лодки, одежда, инвентарь, индивидуальное хранение |
| 24 | Транспорт и логистика | Перевозчики, диспетчерские, брокеры, экспедиторы, курьеры, переезды, пассажирский транспорт |
| 25 | Складские операторы | Склады клиентов, 3PL, фулфилмент, распределительные центры |
| 26 | Производство | Пищевые предприятия, мебель, швейные цеха, металлообработка, сборочные производства |
| 27 | Сельское и лесное хозяйство | Фермы, теплицы, питомники, животноводство, лесные предприятия, рыболовство |
| 28 | Энергетика и коммунальные услуги | Электроэнергия, газ, вода, тепло, солнечная энергетика, обслуживание инфраструктуры |
| 29 | Добывающие предприятия | Карьеры, горнодобывающие компании, нефтегазовые предприятия и подрядчики |
| 30 | Финансы и страхование | Агентства, брокеры, консультанты, банки, кредитные организации, инвестиционные и платежные компании |
| 31 | Подбор и предоставление персонала | Рекрутеры, кадровые агентства, временный персонал, HR-аутсорсинг |
| 32 | Охрана и безопасность | Охранные предприятия, монтаж и обслуживание систем безопасности |
| 33 | Клининг и обслуживание объектов | Уборка, прачечные, химчистки, эксплуатация зданий |
| 34 | Экология и отходы | Вывоз, переработка, экологические услуги, восстановление окружающей среды |
| 35 | Другие персональные услуги | Ателье, ремонт обуви, домашние организаторы, ритуальные и иные персональные услуги |
| 36 | Организации и объединения | Фонды, ассоциации, профессиональные, религиозные и членские организации |
| 37 | Научные и исследовательские услуги | Исследовательские центры, испытательные лаборатории, разработка новых продуктов |
| 38 | Управление компаниями | Управляющие компании холдингов, корпоративные центры, общие сервисные подразделения |
| 39 | Государственное и муниципальное управление | Учреждения, службы, государственные организации и обслуживающие подразделения |

Контроль полноты вести через версионированную таблицу сопоставления каждого профиля с кодами NAICS и 20 секторами NAICS. У профиля может быть несколько кодов; регистрационный код не дает разрешения на регулируемую деятельность. Профиль с пользовательским названием ссылается на существующие отраслевые идентификаторы и не создает дубликат отрасли. Эта классификация включает также управление компаниями и государственное управление. [Census Bureau](https://www.census.gov/programs-surveys/economic-census/year/2022/guidance/understanding-naics.html)

**Маркетплейс, франшиза, холдинг, B2B, B2C и гибридная деятельность — дополнительные характеристики бизнеса.** Они сочетаются с отраслью и не создают повторные копии компании.

Нестандартный бизнес может использовать собственный профиль деятельности на общей основе платформы. Числа 1–39 и стабильные символьные идентификаторы сохраняются между версиями; переводы, теги и синонимы служат поиску. Каталог отраслей описывает охват, а доступность конкретной операции определяется отдельной записью готовности.

Границы близких профилей: № 21 — продажа и обслуживание автомобилей, № 23 — договоры проката автомобилей и другого имущества; № 22 — договоры недвижимости; № 24 — перевозки, № 25 — обработка товаров на складах клиентов; № 19 — строительные проекты, № 20 — выездные задания. Одна компания подключает нужные сочетания без повторного создания контрагентов и ресурсов.

---

## 4. Общие модули платформы

| Модуль | Обязательный состав |
|---|---|
| Организации и структура | Компании, юридические лица, филиалы, подразделения, сети, франшизы и группы |
| Пользователи и права | Сотрудники, роли, области доступа, приглашения, делегирование, журнал действий |
| Клиенты и контрагенты | Частные лица, компании, контакты, обращения, история, договоры и согласия |
| Продажи | Воронки, предложения, договорные цены, заказы, возвраты, подписки |
| Товары и услуги | Варианты, дополнения, комплекты, совместимость, единицы измерения, версии цен |
| Запись и ресурсы | Люди, помещения, оборудование, транспорт, вместимость, исключения и многоресурсная запись |
| Персонал | Смены, доступность, отпуска, обмен сменами, часы, ставки, комиссии и согласования |
| Проекты и работы | Этапы, задачи, исполнители, зависимости, бюджеты, приемка и регулярные задания |
| Документы | Шаблоны, версии, подписи, вложения, сроки действия, ограничение доступа |
| Финансы | Счета, платежи, расходы, задолженность, бухгалтерские проводки, периоды и сверка |
| Закупки | Поставщики, запросы цен, заказы, приемка, счета и согласования |
| Запасы и склады клиентов | Места хранения, партии, серийные номера, движения, сборка, отгрузка и возвраты |
| Активы и обслуживание | Оборудование, автомобили, объекты, осмотры, ремонт и обслуживание |
| Коммуникации | Сообщения, уведомления, шаблоны, история доставки и настройки согласий |
| Поддержка | Обращения, очереди, назначение ответственных, сроки и база знаний |
| Аналитика | Операционные и финансовые отчеты, показатели филиалов, сводные отчеты группы |
| Автоматизация и AI | Проверяемые правила, согласования, рекомендации и разрешенные действия |
| Витрины и маркетплейсы | Публичные предложения, поиск, заявки, запись, заказы, отзывы и модерация |

Пакеты функций скрывают ненужные разделы интерфейса. Малый бизнес получает простой кабинет, корпорация — более подробную структуру на той же основе.

### Настройка под конкретную компанию

Последовательность подключения:

1. Создать компанию и юридические лица.
2. Выбрать одну или несколько специализаций.
3. Подключить необходимые модули.
4. Настроить филиалы, ресурсы, сотрудников и права.
5. Загрузить услуги, товары, тарифы, договоры и начальные данные.
6. Настроить рабочие процессы, согласования и отчеты.
7. Проверить конфигурацию в предварительном просмотре.
8. Опубликовать проверенную версию.

Неизвестные часы, продолжительности услуг, условия договоров и другие бизнес-факты не заполнять вымышленными значениями.

### Версии конфигурации и доступность модулей

Настройка имеет состояния «черновик → проверена → опубликована → заменена». Сохраняются автор, номер версии, результат проверки и предыдущая опубликованная версия. Опубликованная конфигурация неизменяема. Сохранение требует ожидаемого номера версии; конфликт не перезаписывает чужие изменения. Повтор команды возвращает прежний результат, а изменение тела с прежним ключом отклоняется.

Выбор отрасли не включает неподготовленные операции. Список разрешенных модулей и их зависимостей проверяется сервером. Отключение модуля останавливает новые операции, сохраняя доступ к истории, незавершенным обязательствам и экспорту согласно правам. Новый обязательный модуль не включается незаметно при обновлении пакета. Пользовательские поля имеют тип, ограничения, видимость и версию; процессы настраиваются только из разрешенных действий, без исполнения произвольного SQL или кода.

---

## 5. Полная сфера beauty

### Охват

Парикмахерские услуги, барберинг, окрашивание, наращивание волос, маникюр, педикюр, оформление ногтей, брови, ресницы, макияж, депиляция, уход за кожей, SPA, массаж, татуировки, пирсинг, перманентный макияж, выездная работа, аренда рабочих мест и обучение.

Медицинская косметология получает дополнительный квалифицированный клинический модуль.

### Рабочий цикл

**Выбор услуги → расчет состава и времени → подбор мастера и ресурсов → запись → подтверждение → обслуживание → оплата → повторное посещение.**

Обязательные возможности:

- Несколько услуг в одном посещении.
- Совместимые дополнения и исключение повторной оплаты уже включенной процедуры.
- Этапы услуги: активная работа, выдержка, завершение.
- Раздельная занятость мастера, кресла, комнаты и оборудования.
- Квалификация и доступность мастеров.
- Буферы, перерывы, лист ожидания и повторяющиеся посещения.
- Предоплата, отмена и неявка по опубликованной политике.
- Абонементы, пакеты, сертификаты и лояльность.
- Карточки клиентов, предпочтения, согласия и защищенные фотографии.
- Продажа косметики и учет расходных материалов.
- Комиссии, чаевые, часы и аренда рабочих мест.
- Общая работа сети с настройками филиалов.

Существующий движок цен и совместимости расширяется с сохранением его правил и старых записей.

---

## 6. Рестораны и управление персоналом

Поддержать одиночный ресторан, небольшое кафе, сеть, франшизу и корпоративного оператора.

### Персонал

- Планирование по должностям, навыкам и потребности смены.
- Доступность, отпуска, открытые смены.
- Обмен, передача и принятие смен с согласованием.
- Начало и завершение работы, перерывы и исправления табеля.
- Предупреждения о переработках и конфликтах.
- Чаевые, распределение по утвержденным правилам и подготовка данных для зарплаты.
- Общая отчетность по точкам.

### Гости и операционная работа

- План зала, столики, посадка, бронирование и очередь.
- Меню, варианты, модификаторы и доступность блюд.
- Заказы в зале, навынос, онлайн, доставка и кейтеринг.
- Передача заказов на кухню и управление этапами приготовления.
- Разделение счета, частичные оплаты и возвраты.
- Рецептуры, ингредиенты, закупки, остатки и списания.
- Контроль обслуживания, чек-листы и журнал менеджера.

**Запись гостя, рабочая смена и кухонный заказ — отдельные процессы**, связанные общими сотрудниками, ресурсами и финансами.

---

## 7. Логистика, траковый бизнес и диспетчерские компании

### 7.1. Бизнес-профили

- Перевозчик с одним траком.
- Небольшой и крупный автопарк.
- Владелец-водитель.
- Независимая диспетчерская.
- Грузовой брокер.
- Экспедитор и 3PL.
- Курьерская служба, последняя миля и переезды.
- Корпоративная транспортная служба.
- Международные и мультимодальные перевозки.

Внутри профиля задаются типы транспорта, груза, оборудования и территории работы: межштатные перевозки, местные рейсы, полные и сборные грузы, рефрижераторы, платформы, контейнеры, автовозы и другие специализации.

### 7.2. Полный рабочий цикл TMS

| Этап | Требуемое поведение |
|---|---|
| Заказ | Клиентская заявка, ручной ввод или разрешенный импорт |
| Карточка груза | Состав, вес, размеры, требования, отправитель, получатель и документы |
| Ставка | Цена, топливная надбавка, дополнительные услуги, согласование и подтверждение |
| План | Погрузки, разгрузки, временные окна, маршрут и часовые пояса |
| Назначение | Перевозчик, водитель, трак, прицеп, оборудование и резерв |
| Проверка | Занятость, вместимость, обслуживание, документы и доступное рабочее время |
| Диспетчеризация | Доска грузов и рейсов, назначения, сообщения, задержки и история |
| Погрузка | Прибытие, прием груза, транспортная накладная, фотографии и отклонения |
| Перевозка | Остановки, местоположение, расчет прибытия и подтверждение событий |
| Доставка | Разгрузка, подпись, подтверждение доставки, недостачи и повреждения |
| Закрытие | Проверка документов и согласование дополнительных расходов |
| Счет | Начисления заказчику, задолженность, поступления и корректировки |
| Расчеты | Водители, владельцы траков, подрядчики и диспетчерские |
| Автопарк | Осмотры, обслуживание, ремонт, топливо и сроки документов |
| Аналитика | Маржа, расходы, стоимость мили, порожний пробег, загрузка и своевременность |

**Модель перевозок:** заказ на перевозку, груз, транспортный этап, рейс и остановка существуют отдельно.

Это позволяет:

- Перевозить несколько грузов одним рейсом.
- Разделять груз между рейсами.
- Выполнять частичную доставку.
- Передавать груз между транспортными этапами.
- Менять водителя или транспорт с сохранением истории.
- Учитывать возврат, отказ в приемке и претензии.

### 7.3. Кабинеты

**Диспетчер:** планирование, назначения, карта, предупреждения, документы, коммуникации и контроль выполнения.

**Водитель:** задания, остановки, инструкции, статусы, фотографии, подписи, документы и расходы. В офлайн-режиме подготавливаются черновики; подтвержденные изменения появляются после серверной проверки.

**Заказчик:** заявки, согласованные ставки, разрешенные статусы, документы доставки и счета.

**Перевозчик:** автопарк, водители, рейсы, финансовые показатели и доступы диспетчерской.

### 7.4. Независимая диспетчерская

Диспетчерская имеет собственную компанию и договоры обслуживания. Перевозчики предоставляют ей ограниченные полномочия.

Доступ разграничивается по:

- Обслуживаемому перевозчику.
- Конкретным действиям.
- Документам и финансовым данным.
- Сроку полномочий.
- Уполномоченным сотрудникам.

Отзыв полномочий прекращает доступ, сохраняя аудит ранее выполненных действий.

Брокерский профиль имеет отдельные разрешения. По разъяснению FMCSA самостоятельное распределение грузов между перевозчиками может влиять на необходимость брокерских полномочий; роль определяется фактической деятельностью. [FMCSA](https://www.federalregister.gov/documents/2023/06/16/2023-13080/definitions-of-broker-and-bona-fide-agents)

### 7.5. Расчеты

Предусмотреть договорные формулы:

- Фиксированная сумма.
- Оплата за милю.
- Процент от согласованной базы.
- Доплаты, расходы, авансы и разрешенные удержания.
- Вознаграждение диспетчерской.
- Ускоренная оплата и факторинг через соответствующие подключения.

Каждое обязательство перед получателем имеет устойчивый идентификатор: компания-владелец, юридическое лицо, получатель, источник и компонент начисления. Например, оплата водителю и вознаграждение диспетчерской за один рейс — разные обязательства. Во всех расчетных документах суммарно нельзя зарезервировать или выплатить больше невыплаченного остатка одного обязательства. Проверка и резервирование выполняются атомарно с блокировкой; частичные выплаты уменьшают остаток. Повтор команды, другой документ или повтор события провайдера не создают вторую выплату. Начисление, утверждение, резервирование, отправка и подтвержденная выплата имеют отдельные состояния. Изменение суммы оформляется связанной корректировкой или сторно с аудитом, а не повторным созданием исходного начисления.

### 7.6. Межштатные перевозки и интеграции

- Учитывать применимые правила HOS и исключения через версионированные профили. [FMCSA HOS](https://www.fmcsa.dot.gov/regulations/hours-service/summary-hours-service-regulations)
- Подключать электронные журналы и телематику; сохранять источник и актуальность данных.
- Не представлять устаревшие или отсутствующие сведения как подтверждение допустимости рейса.
- Использовать маршруты с ограничениями грузового транспорта.
- Для применимых перевозчиков собирать данные пробега и топлива для IFTA.
- Предусмотреть подготовку отчетов и экспорт с проверкой уполномоченным сотрудником.

Первый адаптер грузовой биржи — DAT после получения доступа. Официальные API требуют учетной записи и соответствующих разрешений. [DAT API](https://www.dat.com/api-integration)

Первый адаптер телематики и диспетчерских заданий — Motive. Его официальная документация предусматривает интерфейсы работы с заданиями. [Motive](https://developer-docs.gomotive.com/reference/overview-dispatches-v3)

Международные, морские, воздушные, железнодорожные, опасные и негабаритные перевозки получают дополнительные процессы и отдельную приемку.

---

## 8. Строительство, ремонт и выездные услуги

### Строительство

**Обращение → обследование → смета → предложение → договор → план → выполнение → приемка → расчеты → гарантия.**

Включить:

- Сметные позиции, материалы, труд, оборудование и себестоимость.
- Генеральные договоры, субподряды и заказы поставщикам.
- Этапы, зависимости, бригады и календарь ресурсов.
- Бюджеты, обязательства и фактические расходы.
- Ежедневные отчеты, фотографии и выполненные объемы.
- Чертежи, версии, запросы разъяснений и согласования.
- Изменения состава работ, стоимости и сроков.
- Проверки, дефекты и перечни незавершенных работ.
- Поэтапные счета, договорные удержания и итоговую приемку.
- Гарантийные обращения.

Изменение договора не переписывает исходную согласованную версию.

### Выездные услуги

**Заявка → диагностика → назначение → выезд → работы → приемка → счет.**

Добавить адрес объекта, оборудование клиента, повторное обслуживание, чек-листы, использованные материалы, фотографии и подпись заказчика.

Для клининга, HVAC, сантехников, электриков, монтажников и садовников использовать общий модуль выездных работ с профильными формами.

---

## 9. Автоаренда, прокат и аренда недвижимости

### 9.1. Автоаренда и прокат

**Поиск → бронирование → договор → обеспечение оплаты → выдача → использование → возврат → итоговый расчет.**

Обязательные возможности:

- Классы имущества и конкретные единицы.
- Автомобили, VIN, филиалы и расположение.
- Суточные, недельные, месячные и долгосрочные тарифы.
- Дополнительные водители и услуги.
- Пробег, топливо, продление и просрочка.
- Осмотры до выдачи и после возврата.
- Фотографии, повреждения и подтверждение состояния.
- Обслуживание и блокировка недоступного имущества.
- Перемещение между точками и возврат в другом филиале.
- Счета, возвраты и завершение договора.

Бронирование класса отделить от назначения конкретной машины. Залог, блокировка средств и начисление за повреждение имеют разные состояния и основания.

Для инструментов, оборудования, лодок и другого имущества использовать тот же модуль с соответствующими характеристиками.

### 9.2. Недвижимость

**Объект → публикация → обращение → показ → заявка → проверка → договор → заселение → обслуживание → завершение аренды.**

Включить:

- Здания, помещения, участки и владельцев.
- Жилую, коммерческую, краткосрочную и долгосрочную аренду.
- Договоры и условия начислений.
- Депозиты, аренду, задолженность и платежи.
- Акты состояния, фотографии и имущество помещения.
- Продления и изменения договора.
- Заявки на ремонт и подрядчиков.
- Кабинеты арендатора и собственника.
- Доходы, расходы и расчеты по объектам.
- Выезд и итоговый расчет депозита.

Проверки кандидатов выполняются через подходящих провайдеров с необходимыми согласиями. Решение принимает уполномоченный человек.

Депозиты и средства собственников учитываются отдельно от доходов управляющей компании.

---

## 10. Остальные отраслевые процессы

| Направление | Рабочий цикл и дополнительные функции |
|---|---|
| Розница, интернет-магазины, опт | Предложение → заказ → оплата → исполнение → возврат; договорные цены, каналы, товары и остатки |
| Юридические услуги | Обращение → проверка конфликта → дело → сроки и документы → учет времени → счет → закрытие; ограничение доступа по делу |
| Бухгалтерия и консалтинг | Клиент → договор → регулярные задания или проект → документы → согласование → счет |
| IT, маркетинг, медиа, исследования | Проект, версии результатов, согласования, задачи, бюджеты, подписки и поддержка |
| Образование | Набор → зачисление → группы и расписание → занятия → задания и результаты → завершение |
| Фитнес и клубы | Абонементы, занятия, тренеры, посещения, вместимость и аренда площадок |
| Медицина, ветеринария, уход | Запись, специалисты, визиты, планы обслуживания, расчеты; профильные записи и процедуры через квалифицированные модули |
| Гостиницы | Номерной фонд, бронирование, заселение, услуги, уборка, обслуживание и выезд |
| Мероприятия | План → площадка → подрядчики → регистрация или билеты → проведение → расчеты |
| Склады и 3PL | Приемка → размещение → хранение → сборка → отгрузка → возврат; отдельный учет собственников товаров |
| Производство | Заказ → спецификация → материалы → операции → качество → выпуск → себестоимость |
| Сельское хозяйство | Участки, сезоны, животные, работы, техника, партии продукции и затраты |
| Энергетика, добыча, эксплуатация | Активы, смены, технические задания, обслуживание, аварийные обращения и снабжение |
| Финансы и страхование | Клиенты, заявки, договоры, согласования и обслуживание; профильные операции через специализированные системы |
| Подбор персонала | Вакансия → кандидат → оценка → назначение → часы → расчеты |
| Охрана, клининг, отходы | Посты или объекты, смены, маршруты, задания, инциденты, приемка и регулярные счета |
| Организации и учреждения | Участники, обращения, взносы, пожертвования, мероприятия, бюджеты и согласования |

Отраслевые правила сроков, документов, разрешений и чувствительных данных проверять для применимой юрисдикции перед запуском соответствующих функций.

---

## 11. Финансовая система, витрины и бизнес-модель

### 11.1. Собственная финансовая основа

Предусмотреть:

- План счетов и двойную запись.
- Продажи, закупки, расходы и задолженность.
- Счета, кредитовые документы, возвраты и сверку платежей.
- Доходы и расходы по филиалам, проектам, объектам, рейсам и подразделениям.
- Валюту операции и базовую валюту юридического лица.
- Начальные остатки и сверку при переносе.
- Закрытие периодов.
- Корректировки через отдельные операции с сохранением истории.
- Сводную отчетность группы с разграничением юридических лиц.

**Разделять:** стоимость заказа, выставленный счет, поступившие деньги, признанную выручку, депозит и обязательство перед исполнителем.

Денежные расчеты выполнять точными числовыми типами и едиными правилами округления. Для новых финансовых контрактов хранить валюту и сумму в минимальных единицах либо Decimal с установленным масштабом валюты; не предполагать два знака у любой валюты. Старые снимки цен в центах сохраняются с прежним смыслом. Разные валюты не суммируются без явного курса, даты, источника курса и операции пересчета.

У каждой проводки есть юридическое лицо, период, валюта, источник и уникальный идентификатор хозяйственной операции. Дебет равен кредиту; опубликованные проводки не редактируются и не удаляются. Запрет закрытого периода проверяется в той же транзакции. Идентификатор webhook сам по себе не защищает от двух событий об одной операции: входящие сообщения дедуплицируются по провайдеру, его аккаунту и ID события, а финансовый эффект — по исходной операции и допустимому переходу состояния. Подпись проверяется до обработки. Запоздавшее событие не возвращает платеж в более раннее состояние; неоднозначность требует сверки с провайдером.

До появления подтвержденного учета оплаты интерфейс показывает стоимость записей по валютам. Оплаченная сумма и признанная выручка имеют отдельные источники и не вычисляются из статуса «запись подтверждена».

### 11.2. Платежи, налоги и зарплата

Первое платежное подключение — Stripe Connect по модели SaaS с direct charges и Stripe-owned pricing, где подключенный продавец принимает платежи своих клиентов, является merchant of record и несет установленную провайдером ответственность за свой платежный баланс. Применимость условий подтверждается при подключении каждого юридического лица; название SaaS само по себе не определяет ответственность. Такая модель предусмотрена официальной документацией Stripe. [Stripe Connect SaaS](https://docs.stripe.com/connect/saas)

На первом этапе:

- Отдельный checkout каждого бизнеса.
- Раздельные платежные аккаунты.
- Подписка GORGONA учитывается отдельно от клиентских продаж.
- Отсутствует комиссия GORGONA за сделки маркетплейса.
- Возвраты и споры связаны с исходной операцией и конкретным бизнесом.

Налоги и зарплатные перечисления подключать через провайдеров. Для зарплаты первый кандидат — Gusto; промышленный доступ требует партнерского согласования и проверки интеграции. [Gusto](https://docs.gusto.com/app-integrations/docs/introduction)

До получения доступа доступен честно обозначенный экспорт подготовленных данных. Он не считается выполненным перечислением или подачей отчетности.

### 11.2.1. Допуск провайдеров до разработки зависимых операций

Реестр подключений хранит компанию и юридическое лицо, страну, профиль деятельности, провайдера, запрошенную операцию, внешнюю учетную запись, состояние допуска, ограничения, время проверки и доказательство. Состояния: не проверен, тестовый доступ, одобрен для конкретных операций, приостановлен, не поддерживается. Статус тестового подключения не разрешает промышленную оплату.

| Подключение | Условие включения | Разрешенная работа без подключения |
|---|---|---|
| Stripe Connect | Допущенная деятельность и страна, завершенное подключение продавца, проверенные capabilities | Счета, задолженность; подтвержденный сотрудником внешний платеж с источником и аудитом, без имитации списания |
| DAT | Лицензия, разрешенные API и договорные права на данные | Ручные заявки и разрешенный импорт; без обхода доступа к бирже |
| Motive | Авторизация перевозчика, доступ к нужным интерфейсам, проверенная актуальность данных | Ручная диспетчеризация; HOS и местоположение показываются как неизвестные, если не подтверждены |
| Gusto | Партнерское согласование, проверка безопасности и промышленный доступ | Проверяемый экспорт; перечисление и подача отчетности не объявляются выполненными |
| Налоги, подписи, screening и другие отраслевые провайдеры | Проверка страны, операции, согласия и необходимых договоров | Только доступные общие операции, без подмены специализированного результата |

Допуск провайдера и допуск отраслевого процесса — разные проверки. Ограничение платежного провайдера не блокирует всю разрешенную нефинансовую работу компании. Некоторые виды деятельности ограничены или не поддерживаются Stripe; «все отрасли» не означает универсальное право принимать платежи через одного провайдера. [Stripe restricted businesses](https://stripe.com/legal/restricted-businesses)

### 11.3. Витрины и маркетплейсы

**Витрина бизнеса:** бренд, филиалы, услуги, товары, доступность, заявки, запись, заказы и контакты.

**Маркетплейс GORGONA:** поиск компаний и предложений, категории, география, отзывы, модерация и переход к оформлению у выбранного бизнеса.

**Маркетплейс клиента:** продавцы, подключения, каталоги, правила публикации, заказы, обслуживание и отчеты.

Общие данные остаются в компании-владельце. Публичная публикация выполняется через явно выбранные поля и права.

### 11.3.1. Ответственность участников маркетплейса

В первом выпуске продавец — владелец предложения и получатель оплаты, возвратов и споров. Его юридическое лицо имеет собственное разрешенное платежное подключение. Заказ относится к одному продавцу; выбор нескольких продавцов разделяется на самостоятельные заказы и checkout. GORGONA и оператор клиентского маркетплейса получают лишь явно делегированные права на публикацию, обслуживание и отчеты.

Комиссия GORGONA за сделку равна нулю на первом этапе. Подписка и использование GORGONA выставляются отдельным счетом. Коммерческое вознаграждение оператора клиентского маркетплейса, если предусмотрено его договором, учитывается отдельным обязательством и счетом продавцу; оно не удерживается автоматически из клиентского платежа в первом выпуске. Сбор денег оператором, распределение платежей, escrow, вложенные платежные платформы и роль оператора как продавца требуют отдельной принятой схемы ответственности и интеграционной приемки. До этого они не включаются.

---

## 12. Архитектура, данные, безопасность и AI

### 12.1. Сохранение существующей архитектуры

Развивать текущий стек:

- Python и FastAPI — серверные процессы.
- PostgreSQL — основные данные и ограничения целостности.
- Next.js и TypeScript — интерфейсы.
- Отдельный существующий AI-контур.
- Модульное приложение с явными границами подсистем.

Azure остается целевой платформой размещения согласно [принятому архитектурному решению](../adr/0012-azure-hosting.md):

- Container Apps.
- Закрытая база PostgreSQL.
- Front Door с защищенной границей входа.
- Managed Identity и Key Vault.
- Bicep как единый способ описания инфраструктуры.
- Отдельное выполнение миграций.
- Проверенное staging-окружение перед промышленным запуском.

Новые сервисы выделять при подтвержденной необходимости независимого масштабирования или изоляции отказов.

### 12.2. Основные предметные модели

**Граница владения:** публичный `business_id` обозначает существующий `tenant_id`, а не новую копию организации. Старый `salon_id` — совместимое имя того же идентификатора. Юридические лица, филиалы и подразделения принадлежат одному бизнесу; финансовая запись дополнительно закреплена за юридическим лицом. Исторические записи не получают вымышленное юридическое лицо: привязка выполняется через подтвержденный перенос.

Самостоятельная франшиза, продавец или перевозчик сохраняет собственный бизнес. Группа компаний связывает бизнесы через явные разрешения; принадлежность группе не дает доступа к строкам других компаний. Сводный отчет читает только разрешенные наборы с указанием владельца и юридического лица. Межфирменные операции создают связанные документы у обеих сторон, не смешивая их книги.

Делегирование хранит бизнес-владелец → обслуживающий бизнес → конкретные сотрудники, действия, области данных, срок, версию и отзыв. Каждая операция проверяет обе активные учетные записи и действующее полномочие, затем выполняется в транзакции с одним целевым `tenant_id`; аудит содержит реального исполнителя, его компанию, компанию-владельца и использованное разрешение. Отзыв запрещает следующую операцию и применение отложенных черновиков. Общая учетная запись с обходом RLS не является механизмом делегирования.

Членство с ограничением филиала разрешает только явно поддерживающие эту область операции. До внедрения фильтров такой запрос отклоняется, а не расширяется до всей компании. Полная поддержка филиалов требует фильтрации чтения, проверки ссылок при записи, разрешений на документы и фоновые задания, а не только фильтра интерфейса.

Общие модели:

- Компания, юридическое лицо, филиал и подразделение.
- Пользователь, членство, роль и делегированное полномочие.
- Контрагент, контакт и договор.
- Товар, услуга, тариф и опубликованная версия каталога.
- Ресурс, доступность и распределение ресурса.
- Документ, версия и подпись.
- Денежная сумма, счет, платеж, проводка и расчет.

Отраслевые модели:

- Запись, смена и табель.
- Заказ, проект и рабочее задание.
- Юридическое дело.
- Груз, транспортный этап, рейс и остановка.
- Договор проката и осмотр.
- Объект, помещение и договор недвижимости.
- Складское движение и производственное задание.

Не объединять эти процессы в один универсальный объект с неограниченными полями. Расширяемые поля имеют тип, правила доступа и валидацию.

### 12.2.1. Единая занятость ресурсов и переход со старой модели

Существующая `booking_allocations` привязана к записи и остается авторитетной для действующего движка до завершения миграции. Общая модель должна поддерживать ресурс, владельца, источник операции, версию, интервал `[начало, конец)`, состояние и потребляемую вместимость. Запись, рейс, аренда и рабочее задание имеют отдельные доменные таблицы и явные проверяемые связи с распределением ресурса.

Порядок перехода: расширить схему → перенести существующие активные интервалы → сверить количество, владельцев и интервалы → обеспечить запись старого API и новых процессов через один транзакционный механизм → проверить конкурентные конфликты → переключить чтение → сохранить совместимое представление и возможность отката. Пока переход не принят, новые модули не резервируют общий ресурс в независимой таблице. Двойная запись без единого механизма блокировки недопустима.

Для эксклюзивных ресурсов сохраняется ограничение пересечений в PostgreSQL. Для вместимости больше одного используется атомарная проверка суммарной занятости под блокировкой ресурса. Многоресурсная операция резервирует все интервалы либо ничего; блокировки берутся в стабильном порядке. Разные этапы beauty занимают разные ресурсы. Перенос между филиалами сохраняет один идентификатор ресурса и историю.

### 12.3. API и совместимость

Добавить семейство `/v1/businesses/{business_id}/…` с интерфейсами общих и отраслевых модулей.

Сохранить `/v1/salons/…` и существующие клиентские сценарии. Старые и новые интерфейсы используют одинаковую доменную логику.

Обязательные правила:

- Сервер проверяет принадлежность компании и полномочия. Новые `/v1/businesses` вызывают те же доменные функции; HTTP-переадресация и копирование салонной логики не заменяют совместимость.
- Запросы и ответы имеют версионированные схемы.
- Повторные команды защищены от двойного выполнения.
- Одновременные изменения проверяют актуальность версии.
- События содержат идентификатор, версию схемы, компанию, время и связь с исходной операцией.
- Старые записи и договорные снимки сохраняют исходный смысл.
- Внешние сайты компаний остаются самостоятельными проектами; общие интерфейсы платформы не требуют конкретного внешнего сайта.

### 12.4. Защита от дублирования

Применять на разных уровнях:

| Уровень | Правило |
|---|---|
| Каталог отраслей | Постоянные идентификаторы; переводы и синонимы не создают новые отрасли |
| Компания | Один профиль организации с несколькими видами деятельности |
| Контрагенты | Сопоставление и предварительная проверка; одинаковое имя или телефон не гарантируют совпадение |
| Ресурсы | Один ресурс используется несколькими модулями с общей проверкой занятости |
| Импорт | Источник и внешний идентификатор предотвращают повторную загрузку |
| Команды и уведомления | Повторная доставка не повторяет операцию |
| Финансы | Один источник начисления не создает несколько одинаковых проводок или выплат |

Спорные объединения подтверждаются владельцем данных. История связей сохраняется.

### 12.5. Безопасность

- Изоляция компаний на сервере и уровне базы.
- Дополнительное разграничение филиалов, дел, объектов и назначений.
- Минимальные полномочия интеграций и AI.
- Защищенное хранение секретов.
- Аудит изменения прав, финансов, договоров и настроек.
- Ограничение публичных данных.
- Проверка загружаемых файлов.
- Управление согласиями, хранением и доступом к чувствительной информации.
- Корпоративный единый вход и управление жизненным циклом сотрудников.
- Поддержка отзыва делегированных доступов.
- Резервное копирование и проверенное восстановление.

### 12.6. AI и автоматизация

AI может помогать с:

- Поиском и объяснением информации.
- Подготовкой предложений и документов.
- Рекомендациями расписаний и назначений.
- Выявлением конфликтов, пропусков и отклонений.
- Прогнозами при достаточных данных.
- Подготовкой ответов и отчетов.

Действия выполняются через разрешенные типизированные инструменты. Финансовые, договорные и другие значимые изменения требуют соответствующего согласования.

Для исправления AI сохранять:

- Исходный результат и коррекцию.
- Заметку и доказательства.
- Контекст и уверенность.
- Время, версии модели и агента.
- Статус проверки и допустимую область обучения.

Изменения проходят оценку, регрессионные проверки, сравнение версий, теневую проверку и возможность отката. Одна коррекция не запускает бесконтрольное переобучение.

### 12.6.1. Границы безопасной автоматизации

Коррекции не меняют рабочий код, модель или общую память других компаний. Область коррекции определяется владельцем данных и правами. Предложение AI, одобренная команда и выполненная операция имеют отдельные состояния; подтверждение привязано к версии предложения и данным, а изменение исходных условий требует повторной проверки. Отзыв прав проверяется непосредственно перед выполнением. AI не использует учетную запись мигратора или обход RLS.

Перед продвижением версии обязательны: отсутствие новых нарушений доступа и критических ошибок на утвержденном наборе, отсутствие регрессии детерминированных сценариев, сравнение точности/ошибок/задержки с зафиксированным базовым результатом, теневой прогон, разрешение ответственного и проверенный откат. Численные пороги для вероятностных рекомендаций утверждаются для конкретного сценария до эксперимента. Данные иных компаний, спорные и неподтвержденные исправления не попадают в обучение автоматически.

### 12.7. Перенос данных и отказоустойчивость

Перенос выполняется последовательно:

**Предварительный просмотр → сопоставление → проверка дублей → пробный импорт → сверка → подтвержденное переключение.**

Для каждого набора данных установить один управляющий источник.

Интеграции используют очереди, проверку подлинности уведомлений, повторные попытки и обработку событий не по порядку. Сбой провайдера отображается пользователю с действительным состоянием операции.

Миграции добавляют новые структуры и сохраняют старые данные. Примененные миграции не переписываются. Переключение предусматривает сверку и безопасный откат. Восстановление старого приложения допускается только если оно понимает текущую схему; удаление новой схемы после появления новых данных не считается безопасным откатом.

### 12.8. Офлайн-режим, надежность и эксплуатационные цели

Офлайн-кэш использует явный список разрешенных полей и версию политики, привязан к пользователю и компании, имеет срок жизни; выход, смена компании и отзыв доступа очищают доступный локальный кэш. Чувствительные документы и секреты в кэш по умолчанию не входят. Защита хранилища и управление ключами проверяются до включения офлайн-режима. Сервер не обещает удаленно стереть данные с отключенного устройства: короткие сроки доступа и корпоративное управление устройствами учитывают это ограничение.

Черновик содержит автора, компанию, исходную версию, локальный идентификатор и время. После подключения сервер заново проверяет права, состояние документа, занятость, цены и ключ повторной команды. Конфликт возвращается пользователю; последнее локальное изменение не побеждает автоматически. Запись, выдача имущества, платеж, подпись и доставка не считаются подтвержденными до ответа сервера.

Предварительные цели восстановления для основной транзакционной базы: RPO не более 15 минут, RTO не более 4 часов. Это инженерные цели, не договорное обещание и не измеренный результат. До промышленного запуска выполнить восстановление в отдельное окружение, сверку проводок/записей/прав и повтор очередей; измерить реальное RPO/RTO. Для файлов и внешних провайдеров отдельно установить и проверить достижимые цели. Сигналы наблюдения: ошибки по операциям, p95/p99, очередь и ее возраст, повторы, дедлоки, пропуски уведомлений, ошибки авторизации, стоимость компании и ошибки сверки. Назначить ответственного за инциденты и проверить инструкции восстановления.

---

## 13. Порядок разработки

Этапы определяют последовательность **разработки** модулей и их технической приемки, а не очередность запуска отраслей. Промышленный запуск (этап 9) один и общий для всех 39 направлений (решение владельца 2026-10-20, §1 п. 13); ни одна отрасль не выходит раньше остальных и не считается основной.

| Этап | Результат | Условие завершения |
|---|---|---|
| 0. Базовая проверка и исправления | Зафиксированная исходная версия; исправления дней недели, локальных дат, показателей и опасного расширения прав | BASE-01–04; регрессия существующей записи, API и клиентского интерфейса платформы; непройденные проверки обозначены явно |
| 1. Общая бизнес-основа | Стабильные 39 профилей, один бизнес с несколькими специализациями, версии конфигурации, юридические лица, филиалы, права, контрагенты, документы; модель групп и делегирования; единая занятость | CORE-01–04; малый бизнес, сеть и гибридная компания проходят сценарии без дублирования и утечки данных |
| 2. Финансы, персонал и базовые материальные операции | Проводки, счета, платежи, смены, табели, согласования; базовые закупки, приемка, остатки и движения материалов; ранняя проверка допуска провайдеров | FIN-01–03, STOCK-01, WORK-01; повтор команды не удваивает деньги или движение; учет и права связаны |
| 3. Beauty и TMS | Полный beauty-контур и контуры TMS в порядке разработки: перевозчик, затем независимая диспетчерская, затем брокер/3PL (порядок разработки, не отдельные запуски) | BEAUTY-01, TMS-01–03; замкнутые циклы, актуальность транспорта и действительность делегирования подтверждены |
| 4. Строительство и аренда | Сметы, проекты, изменения договоров, прокат, недвижимость, обслуживание | BUILD-01, RENT-01, PROPERTY-01; ресурсы, приемка, депозиты и обязательства сверены |
| 5. Рестораны и профессиональные услуги | Гости, столики, кухня, заказы; юридические дела, проекты и регулярные услуги | REST-01, PRO-01; процессы используют уже проверенные персонал, платежи и материалы |
| 6. Товарные и производственные процессы | Развитая торговля, многоскладской WMS клиентов, партии/серии, 3PL, производство и себестоимость | SUPPLY-01; исходные базовые складские движения расширены, не заменены вторым учетом |
| 7. Витрины, маркетплейсы и корпоративные возможности | Публикация, независимые продавцы, группы, расширенная аналитика, единый вход и управление сотрудниками | MARKET-01, ENTERPRISE-01; модель владельцев и групп этапа 1 сохранена; нет общего неразделенного платежа |
| 8. Специализированные отрасли | Остальные профили и квалифицированные операции/интеграции | Приемка отдельных сценариев и юрисдикций; профиль сам по себе не дает статуса готовности |
| 9. Промышленный запуск | Один общий запуск всех 39 направлений: инфраструктура Azure, самостоятельная регистрация компании любого направления, перенос, наблюдение, восстановление, поддержка | OPS-01–03; все 39 профилей и их сценарии прошли приемку; проверки staging, устраненные критические дефекты и разрешение владельца на запуск |

Каждый этап включает интерфейс, серверную логику, данные, права, документацию и проверки. Наличие отдельных экранов не считается завершением модуля. Этап разбивается на небольшие законченные изменения, но готовность этапа не объявляется по одному из них. Полный охват сохраняется. Модули разрабатываются и проверяются по этапам, чтобы не объединять несколько непроверенных финансовых и операционных контуров в одно изменение, но запускаются в промышленную эксплуатацию вместе: один общий запуск для всех 39 направлений после их приемки (решение владельца 2026-10-20).

Первый пакет реализации: сохранить исправленный план; обновить действующие архитектурные указания; исправить подтвержденные дефекты записи с регрессией; добавить типизированный каталог направлений и начало `/v1/businesses` без объявления отраслевых модулей готовыми. Последующие пакеты — версии настройки и юридические лица, разграничение филиалов, общая занятость, затем финансово-материальная основа. Производственные миграции, подключения провайдеров и развертывание выполняются отдельно после их приемки.

---

## 14. Приемка, измерения и статус готовности

### 14.1. Обязательные проверки

| Область | Проверяемые сценарии |
|---|---|
| Совместимость | Существующие записи, цены, дополнения, отмены, переносы и клиентский интерфейс платформы |
| Изоляция | Чужие компании, филиалы, дела, перевозчики и документы недоступны |
| Расписания | Часовые пояса, переход времени, многоресурсные услуги и вместимость |
| Персонал | Обмен сменами, согласования, табели и повторные исправления |
| Beauty | Этапы услуги, совместимость дополнений, пакеты и расходные материалы |
| Логистика | Межштатный рейс, несколько остановок, сборные грузы, частичная доставка и поломка |
| Диспетчерская | Несколько перевозчиков, ограниченные полномочия и отзыв доступа |
| Данные транспорта | Устаревшие координаты, неизвестный HOS, повторные и запоздавшие события |
| Строительство | Изменение сметы, дополнительные работы, приемка и поэтапные счета |
| Прокат | Двойная бронь, замена имущества, продление, повреждение и возврат обеспечения |
| Недвижимость | Начисления, депозиты, обслуживание и расчеты собственников |
| Финансы | Частичная оплата, возврат, корректировка, закрытый период и повторная выплата |
| Склады и производство | Движения, собственники товаров, возвраты, выпуск и себестоимость |
| Перенос | Повторный импорт, сверка остатков, сохранение связей и откат |
| Интерфейс | Мобильные устройства, клавиатура, доступность и понятные ошибки |
| Надежность | Сбой провайдера, повтор события, восстановление данных и очередей |

После существенных изменений выполнять релевантные серверные тесты, проверки типов, линтинг, сборку, интеграционные и сквозные проверки.

### 14.1.1. Проверяемые сценарии с постоянными идентификаторами

| ID | Критерий приемки |
|---|---|
| BASE-01 | Понедельник=1 и воскресенье=7 проходят чтение, изменение и повторное открытие графика; 0/8 отклоняются |
| BASE-02 | Локальный день филиала, границы суток и DST проверены; отсутствующее/неоднозначное локальное время не становится произвольной записью |
| BASE-03 | Подтверждение записи без оплаты не увеличивает показатель оплаченных денег; валюты показаны раздельно |
| BASE-04 | Ограниченное филиалом членство не получает доступ всей компании; чужая ссылка не проходит проверку |
| CORE-01 | Все 39 ID уникальны и стабильны; один бизнес подключает несколько профилей; старый salon_id совпадает с business_id |
| CORE-02 | Два конкурентных обновления одной версии дают один успех и один конфликт; повтор команды не создает вторую версию |
| CORE-03 | Независимые бизнесы в группе/диспетчерской сохраняют владельцев; отзыв полномочия блокирует следующую команду и синхронизацию черновика |
| CORE-04 | Старый API записи и новая аренда одновременно запрашивают один ресурс: только один подтвержденный интервал; неудача откатывает все ресурсы |
| FIN-01 | Двойная запись сбалансирована; разные юридические лица и валюты не смешаны; закрытый период запрещает проведение |
| FIN-02 | Повтор и перестановка provider-событий не повторяют оплату/возврат/проводку; источник операции прослеживается |
| FIN-03 | Два расчетных документа конкурируют за одно обязательство: резерв/выплата не превышает остаток; частичные выплаты и сторно сохраняют историю |
| STOCK-01 | Приемка, списание и возврат материала связаны с документом и владельцем; повтор команды не повторяет движение |
| WORK-01 | Передача смены проверяет навыки, конфликты и согласование; исправление табеля оставляет предыдущую версию |
| BEAUTY-01 | Многоэтапная услуга, дополнения, ресурсы, оплата, комиссия и расход материалов образуют сверяемый цикл |
| TMS-01 | Межштатный рейс с несколькими грузами/остановками, частичной доставкой и заменой транспорта сохраняет историю |
| TMS-02 | Диспетчер работает только в выданной области каждого перевозчика; отзыв и истечение запрещают операции |
| TMS-03 | Устаревшая телематика и неизвестный HOS не дают положительного разрешения; повтор события не меняет доставку дважды |
| BUILD-01 | Изменение сметы не меняет исходный договор; приемка этапа, удержание и счет сверяются с бюджетом |
| RENT-01 | Бронь класса отделена от назначения; двойная выдача невозможна; обеспечение оплаты, ущерб и возврат отражены отдельно |
| PROPERTY-01 | Аренда, депозит, ремонт и расчет собственника имеют раздельные обязательства и права |
| REST-01 | Столик, смена и кухонный заказ независимы; модификаторы, разделение счета, возврат и списание ингредиентов согласованы |
| PRO-01 | Ограничения по делу/проекту соблюдаются в поиске, файлах, задачах, счетах и экспорте |
| SUPPLY-01 | Товар другого собственника недоступен; выпуск/возврат сохраняют партии, движения и себестоимость |
| MARKET-01 | Публикуются только выбранные поля; каждый заказ и платеж относятся к одному продавцу |
| ENTERPRISE-01 | Отключенный сотрудник теряет доступ; группа получает только разрешенные отчеты без переноса владения |
| OPS-01 | Восстановление и повтор очередей измерены; перенос сверен, обратное переключение проверено |
| OPS-02 | Нагрузочный профиль ниже воспроизведен с результатами и исходной версией |
| OPS-03 | Мобильный интерфейс, клавиатура, ошибки, сбой провайдера и конфликты офлайн-синхронизации проверены |

В реестре каждого сценария: ID, владелец реализации, ответственный за отраслевую приемку, версия кода/схемы/настроек, ссылки на тест и отчет, дата, ограничения, статус. До назначения ответственного поле остается явно незаполненным; приемка не выполняется автоматически. Только технический PASS допускает следующий технический этап; отраслевой пилот и промышленное разрешение — отдельные решения.

### 14.2. Нагрузочные цели

Сохранить ранее выбранные цели испытаний:

- 1 000 компаний.
- Корпоративный сценарий со 100 филиалами и 10 000 сотрудников.
- 100 запросов в секунду, пики до 200.
- p95 чтения — до 500 мс.
- p95 записи — до 1 секунды без времени внешнего провайдера.

Это **цели для измерений**, а не подтвержденные показатели текущей системы.

Начальный воспроизводимый профиль: 1 000 синтетических компаний с 1 000 000 исторических записей суммарно; одна корпоративная компания со 100 филиалами и 10 000 сотрудников; фиксированная версия генератора и распределение данных в отчете. После 10 минут прогрева — 30 минут при 100 запросах/с и три пика по 2 минуты при 200 запросах/с с 5 минутами восстановления между ними. Смесь: 70% разрешенное чтение каталога/расписания/операций, 20% запись, 10% отчеты и поиск. Указать характеристики Azure, размер пула, долю кэша, реальные и тестовые адаптеры. Измерять p95 отдельно для чтения и записи, p99, очередь, ошибки и стоимость. Приемка: заданные p95, менее 0,1% неожиданных ошибок, ноль утечек и нарушений денежных/ресурсных инвариантов. Ожидаемые конфликты измеряются отдельно, не скрываются как успех. Нагрузку выполнять только в выделенном тестовом окружении.

Дополнительно измерять ошибки операций, задержку очередей, время уведомлений, конфликты ресурсов, восстановление данных, стоимость обслуживания и качество AI.

### 14.3. Реестр готовности

Для каждого профиля и рабочего сценария хранить отдельный статус:

1. Запланирован.
2. Реализован.
3. Проверен технически.
4. Принят в отраслевом пилоте.
5. Подтвержден для промышленной эксплуатации.

Публиковать только подтвержденные возможности. Доступные модули и ограничения должны быть понятны компании до подключения.

Цель общего запуска (решение владельца 2026-10-20): статус 5 «Подтвержден для промышленной эксплуатации» одновременно у всех 39 профилей и их сценариев; компания любого направления может самостоятельно зарегистрироваться и работать. Оценки готовности проекта даются по всем 39 направлениям, а не по одной отрасли.

### 14.4. Исходное состояние и доказательства реализации

На начало работ 4 октября 2026 года исходная версия — `76ce4e52f1c19b176586c8f69e55d4df735d1a1e`, рабочая копия была чистой. В предыдущей проверке этой версии: 151 тест API прошел, 12 тестов AI прошли, 17 тестов AI пропущены; проверка типов web прошла. Это историческая проверка исходной версии, не результат измененного кода.

Промышленная готовность универсальных модулей, платежных подключений, нагрузочные цели и работоспособность облачного окружения не подтверждены этим документом. Текущие изменения, новые проверки, пропуски и блокеры ведутся в [реестре реализации](GORGONA_IMPLEMENTATION_STATUS.md). Реализованы исправления этапа 0 и начальные пакеты общей основы, включая операции назначенного филиала; остальные согласованные направления остаются в плане.

Филиальные операции исходной записи реализуются через явный допуск обработчиков и ограничивающие RLS-политики; общие настройки остаются отдельными полномочиями. Определения и пределы текущего пакета зафиксированы в [ADR-0014](../adr/0014-location-scoped-workspace.md), свежие проверки — в реестре. Это не подтверждает корпоративные группы, несколько филиальных грантов или полный отраслевой цикл.
