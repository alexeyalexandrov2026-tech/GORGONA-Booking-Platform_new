# GORGONA — реестр реализации

## Current checkpoint — 2026-10-23: L7c customer site, several services and stages, locally verified

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

## Previous: повторный независимый обзор I4 — FAIL, три находки — 2026-10-12

Своя копия `C:/Users/alexa/.codex/worktrees/package-i4-review-2/Gorgona Booking`,
локальная ветка `codex/package-i4-review-2` от `0356eb5`. Проверен diff
`a806380..b66eb41`, SHA256 16/16 и неизменность рабочих source/test файлов.
[Обзор](evidence/2026-10-11-i4-shift-visibility/INDEPENDENT_REVIEW_2.md),
[точные команды и результаты](evidence/2026-10-11-i4-shift-visibility/INDEPENDENT_REVIEW_2_CHECKS.json).

Две medium/P2: скрытая смена читается через swap после повторного приглашения
в тот же филиал до создания нового профиля (R2-1); два cancel разных ключей
проходят последний слот дневного лимита — 21 маркер вместо 20 (R2-2, три состояния
модуля, настоящие pg_locks waiters). Одна low/P3: экран скрывает человеческую
причину `Clock-in` по совпадению с системной строкой (R2-3). Отрицательные пробы:
3 failed / 10.70s; 1 failed, 2 passed / 7.99s; browser 1 failed / 72.26s.
Эти дефекты не исправлялись в review-копии. I-09/I-12 текущего плана FAIL;
старые C1-числа сохранены как результат только выбранных случаев того прогона.

Свежие PASS: focused 86 / 104.38s; стандартный browser 1 / 150.78s и отдельный
browser UTC≠local + company-wide staff 1 / 149.74s, оба desktop/mobile, три фазы.
Ruff/format/mypy 264; web typecheck/lint/format, unit 102 и build 23 страницы.
Production audit FAIL 2 high, next/source-map-js. Полный suite в этом обзоре
не повторялся; CI c6b8e34 success перечитан, CI локального review-коммита NOT TESTED.
Оба своих кластера остановлены; временные проверки сохранены вне Git и удалены/
восстановлены в копии. Код, тесты, миграции 0001–0035 и зависимости не изменены.
Готовность WORK-01/CORE-04 не повышена, пакет не принят. Следующий срез —
исправления R2-1/R2-2/R2-3 с red→green и свежими полными воротами, на отдельной
ветке. Push/PR/merge/production и CodeRabbit не выполнялись.

## Previous: Package I acceptance prepared; readiness unchanged — 2026-10-12

Local branch `codex/package-i-acceptance` from verified local/remote I4 head
`c6b8e341a7e88957ee5011e54e9aa06453b31b49`. Documentation/evidence only:
[fresh acceptance matrix](evidence/2026-10-12-i-acceptance/ACCEPTANCE.md),
[executed cases and exact commands](evidence/2026-10-12-i-acceptance/CHECKS.json),
[source hashes](evidence/2026-10-12-i-acceptance/SOURCE_SHA256.json),
[CI evidence](evidence/2026-10-12-i-acceptance/CI_EVIDENCE.json).

PASS: fresh serial PostgreSQL/browser-required full suite, 1506 passed / 4 skipped /
1026.84s; I4 browser six successful desktop/mobile cases across closed/enabled/off
phases; Ruff/format/mypy (264 files), web typecheck/lint/format, 102 unit cases and
23-page build. Exact-source CI c6b8e34 passed: run 38204334830, job 114664366391,
1509 passed / 1 skipped / 595.96s, including required containers. Local container
checks and the optional external tenant site were skipped, not PASS. Own disposable
clusters are stopped. Production npm audit FAIL: 2 high, next and source-map-js.

I-01–I-11 PASS for their recorded executed cases. I-12 conservatively BLOCKED:
the original review covers a806380, fourteen fixes in b66eb41 have fresh passing
regressions but no second independent source review. All 16 author-response source
hashes match. Package I is not accepted; WORK-01/CORE-04 stay planned and workforce
stays closed outside fixtures. Migrations 0001–0035, code and dependency locks are
unchanged. Plan/ADR approval, policy choices, readiness and stack/publication
decisions remain with the owner. New documentation-commit CI is NOT TESTED because
the acceptance branch remains local. No push/PR/merge or production action.
Continue from the [updated acceptance handoff](NEXT_AGENT_PACKAGE_I_ACCEPTANCE_2026-10-12.md).

## Previous: видимость смен коллег — настройка филиала; ветка опубликована — 2026-10-11

Решение владельца 2026-10-11 по первому открытому варианту I4: сотрудник по
умолчанию видит опубликованные смены коллег своего филиала, а владелец, менеджер
компании или менеджер этого филиала может их скрыть. Та же ветка
codex/package-i4-workforce-screens поверх записи I4 5f0e58f; итоговый коммит кода
419eda8097554c024cb76cde38fe901c386a5e29. Forward 0035: версии настройки филиала только
добавляются; SQL проверяет автора и упорядочивает версии одной блокировкой на
филиал; таблица входит в охранную проверку пакета и в восстановление политик.
Новые маршруты: GET/PUT /workforce/locations/{id}/settings и
GET /workforce/my-changes/{id}/shifts (участник запроса читает смены своего
запроса и при скрытых сменах). На экране расписания появился раздел «Privacy»;
на экране своих смен обмен при скрытых сменах выбрать нельзя, причина показана.
[Доказательства](evidence/2026-10-11-i4-shift-visibility/VALIDATION.md),
[команды](evidence/2026-10-11-i4-shift-visibility/COMMANDS.md),
[передача следующему агенту: приёмка, инструкции и готовые запросы](NEXT_AGENT_PACKAGE_I_ACCEPTANCE_2026-10-12.md).
PASS: полный прогон 1500 passed / 4 skipped / 953.19s на 419eda8; настоящий браузер на компьютере и
телефоне 1 / 103.56s; гонка с наблюдаемым ожиданием в pg_locks; Ruff/format/mypy
263; web unit 102, сборка 23 страницы. Ветка опубликована по разрешению
владельца; CI точного коммита 5f0e58f — success (run 38132277248); CI более
поздних голов читать на GitHub. PR не создан. Независимый обзор ВЫПОЛНЕН
2026-10-11 исполнителем, который не писал код: критических и высоких находок
нет, две средние, семь низких, семь заметок
([обзор](evidence/2026-10-11-i4-shift-visibility/INDEPENDENT_REVIEW.md),
[ответ автора](evidence/2026-10-11-i4-shift-visibility/AUTHOR_RESPONSE.md)).
Четырнадцать из шестнадцати исправлены в b66eb41: при скрытых сменах сервер
отказывает и в новом обмене, пометка «вне расписания» следует действующей
версии, отмена ограничена 20 в сутки; две описаны и оставлены владельцу. Полный
прогон после исправлений: 1506 passed / 4 skipped / 2306.13s. Отменённый ключ не может
записаться 24 часа, пока живёт его квитанция, а не навсегда.
Контейнеры, внешний сайт, HawkScan, нагрузка, deploy/production NOT TESTED.
Унаследованный production npm audit FAIL 2 high. WORK-01/CORE-04 и замок
workforce не изменены; миграции 0001–0034 не тронуты.

## Previous: I4 реализован и проверен локально — 2026-10-11

Локальная ветка codex/package-i4-workforce-screens поверх передачи I4
d22b61cf53612ab85c157c00ecd75fd1630ba1c2; итоговый коммит кода
f4a7395e3ab9515e410143103142f44072af6cba. Три экрана кабинета поверх I1–I3:
расписание, свои смены и табели — на компьютере и телефоне. После падающих
тестов добавлены пять небольших маршрутов чтения и исхода команды; миграций нет.
Потерянный ответ выясняется у сервера по исходному ключу; в браузере хранятся
только идентификаторы.
[Доказательства](evidence/2026-10-11-i4-workforce-screens/VALIDATION.md),
[команды](evidence/2026-10-11-i4-workforce-screens/COMMANDS.md),
[что открыто и готовые запросы](NEXT_AGENT_PACKAGE_I_REVIEW_2026-10-11.md).
PASS: полный прогон 1486 passed / 4 skipped / 907.37s на f4a7395; настоящий браузер на
компьютере и телефоне 1 / 92.97s; две гонки отмены с наблюдаемым ожиданием в
pg_locks; Ruff/format/mypy 261; web unit 101, сборка 23 страницы. Независимый
обзор НЕ ВЫПОЛНЕН: автор только перечитал свои изменения. Push/PR не
выполнялись; CI точного коммита, контейнеры, внешний сайт, HawkScan, нагрузка,
deploy/production NOT TESTED. Унаследованный production npm audit FAIL 2 high.
Миграции 0001–0034, WORK-01/CORE-04 и замок workforce не изменены. Приёмка
пакета по матрице I-01–I-12 и публикация — решения владельца.

## Previous: I3 реализован и проверен локально — 2026-10-11

Локальная ветка codex/package-i3-timesheets поверх I2
49276bf800eb929589785e192db489e17ac77fa7. Forward0034: отметки начала/конца и
перерывов, неизменяемые версии исправлений/решений, последняя утверждённая
версия, запрет двух открытых записей и пересечений по стабильному пользователю.
Менеджер ограничен домашним филиалом сотрудника; своё утверждение разрешено
только владельцу с видимой неизменяемой пометкой. При отключении остаются
чтение истории и закрытие своей уже открытой записи. Денежных проводок нет.
[Доказательства](evidence/2026-10-11-i3-timesheets/VALIDATION.md),
[независимый обзор](evidence/2026-10-11-i3-timesheets/INDEPENDENT_REVIEW.md).
PASS: final focused76/67.46s, Ruff/format/mypy254, web94/build,
обзор14 файлов по SHA. Все17 гонок требуют ожидания pg_locks. Четыре находки
SQL/state воспроизведены до исправления. Полный I3 PASS:
1473 passed / 4 skipped / 832.46s.
Миграции0001–0033, WORK-01/CORE-04 и замок workforce не изменены.
I4/приёмка впереди; exact-commit CI/контейнеры/нагрузка/deploy/production NOT TESTED.
Push/PR не выполнялись. Унаследованный production npm audit FAIL2 high.
Независимая проверка FIN-03 не включена в этот срез.

## Previous: I2 реализован и проверен локально — 2026-10-10

Локальная ветка codex/package-i2-shift-changes поверх I1
69270cc8bfdfb763cc8f5fc9b7892b13db987bce. Новая forward-only0033: передача,
обмен и взятие домашней открытой смены, явное согласие и утверждение менеджером,
неизменяемые снимки навыков/события, атомарное применение в общей занятости и
повтор первоначального результата команды. API использует права и квитанции I1.
[Проверки](evidence/2026-10-10-i2-shift-changes/VALIDATION.md),
[независимый обзор](evidence/2026-10-10-i2-shift-changes/INDEPENDENT_REVIEW.md).
PASS: сфокусированный156/114.89s и отдельно шесть случаев навыков7.48s;
Ruff/format/mypy248, web94/build, независимый обзор исправленного кода16 файлов.
Полный прогон PASS:1380 passed / 4 skipped / 738.66s. Гонки API и SQL
засчитаны только после наблюдаемого ожидания в pg_locks. Находки обзора о скрытой
старой занятости и pickup чужого филиала воспроизведены тестами и исправлены.
Миграции0001–0032, WORK-01, CORE-04 и production-замок workforce не менялись.
I3 табели, I4 экраны и приёмка впереди. CI/контейнеры/нагрузка/production:
NOT TESTED; пропущены три контейнерные проверки и один внешний сайт.
Push/PR/deploy не выполнялись. Унаследованный npm production audit:
FAIL,2 high. Отдельная независимая проверка FIN-03 в эту задачу не включалась.

## Previous: срез I1 реализован и проверен локально — 2026-10-09

Ветка codex/package-i1-workforce поверх I0 14190730.
[Доказательства I1](evidence/2026-10-09-i1-workforce/VALIDATION.md),
[независимый обзор](evidence/2026-10-09-i1-workforce/INDEPENDENT_REVIEW.md).
Добавлены профили, стабильный ресурс сотрудника, версии навыков и смен,
назначения в общей занятости, API, права версии6 и защита схемы; только новая
миграция 0032. Полный прогон PASS: 1301 passed / 4 skipped / 772.12s.
Сфокусированный: 81 passed / 45.49s; Ruff/format/mypy 239 и web 94/build PASS;
независимый обзор кода PASS. Первый полный FAIL из-за DiskFull сохранён.
Контейнеры (3 skip) и отдельный внешний сайт (1 skip): NOT TESTED.
WORK-01, CORE-04 и production-замок workforce не менялись. Ветка локальная,
CI NOT TESTED. I2–I4 и приёмка остаются следующими срезами. Перенос домашнего
филиала сотрудника требует отдельного жизненного цикла; небезопасные изменения
отклоняются. Найден унаследованный FAIL npm audit:2 high зависимости production
дерева, без изменений пакетов в I1. Промышленная готовность не заявляется.

## Previous: пакет I начат — план и срез I0, 2026-10-09

[Передача](NEXT_AGENT_PACKAGE_I_2026-10-09.md),
[продвижение по мастер-плану](PROJECT_PROGRESS_2026-10-09.md),
[план пакета I](PACKAGE_I_PLAN_2026-10-09.md),
[ADR-0025](../adr/0025-workforce-shifts-and-timesheets.md),
[перечень I0](evidence/2026-10-09-i0-resource-kinds/INVENTORY.md).

Пакет I (смены, замены, табели; WORK-01): написаны план и ADR-0025. Явного
согласования владельца не было; варианты A приняты как рабочие, потому что
владелец поручил исполнителю решать самому. Срез I0 (ветка `codex/package-i0-resource-kinds`) не
меняет схему и исходный код: семь тестов закрепляют нынешнее поведение записи,
резерваций и настройки для видов ресурсов, а перечень называет обязательные
изменения среза I1. Полный прогон: PASS, 1238 passed / 4 skipped / 644.59 s. WORK-01 и модуль
`workforce` остаются planned. Ветки пакета I локальные.

Открыто по пакету H: черновик PR приёмки и независимая проверка коммита
`ec39622`. Merge, deployment, production-миграции и операции с провайдерами не
разрешены.

## Previous: пакет H принят технически (FIN-03), 2026-10-09

H1–H4 в коде на `319f144` (`codex/package-h4-ui-admission`, черновики PR15–PR22,
ничего не слито). CI точного SHA — success. Независимый аудит в отдельной
рабочей копии и на отдельном кластере PostgreSQL 18.6: полный прогон
1231 passed / 4 skipped / 662.06 s с обязательными PostgreSQL и браузером;
ruff/format/mypy 230 и web-проверки PASS; 94 web-теста; четыре мутации
SQL-защит обнаружены тестами. Денежных дефектов не найдено.

Находки A-01–A-11 записаны в [аудите](evidence/2026-10-09-h-acceptance-audit/AUDIT.md).
Единственная P2 — реестр допуска провайдеров доступен при включённом `finance`
без собственного замка — закрыта решением владельца 2026-10-09: код не
меняется, H4 не развёртывается до приёмки H. Остальные находки — устаревшие
документы и наблюдения.

**FIN-03 — `technically_verified` по решению владельца 2026-10-09**, код
`319f144`: [запись о приёмке](evidence/2026-10-09-h-acceptance/ACCEPTANCE.md),
[передача](NEXT_AGENT_H_ACCEPTANCE_2026-10-09.md). `finance_documents` включается
опубликованной конфигурацией компании; тестовые подмены готовности сняты.
Полный прогон на дереве коммита приёмки: 1231 passed / 4 skipped / 666.05 s.
ADR-0024 — Accepted. FIN-02 остаётся planned. Ветка
`codex/package-h-acceptance` отправлена 2026-10-09 по решению владельца; CI
точного SHA коммита приёмки `ec39622` — success (push 37887856597). Черновик PR
поверх PR22 не открыт; независимая проверка коммита приёмки — NOT DONE. Merge,
deployment, production-миграции и операции с провайдерами не разрешены.

## Previous H4/UI и admission, 2026-10-08

Ветка `codex/package-h4-ui-admission` от parent PR21 `12875e8` добавляет
Financial documents и metadata-only Provider admission в management workspace.
Существующие H money APIs и G ledger переиспользованы; current credit
counteraccount выбирается явно. Серверный overview сообщает фактический gate;
production H остаётся закрытым. Новая forward-only 0031 не меняет прежние
финансовые записи или миграции 0001–0030.

Admission draft/submitted/withdrawn сохраняет неизменяемую историю, unverified
evidence и capabilities=false; network/provider integration не реализуется.
Tenant/book/roles, прямой SQL, version/recovery races и populated upgrade
проверены в disposable PostgreSQL. Desktop/mobile actual OIDC/API/PG browser
проверяет invoice/reserve/partial pay, потерю ответа/reload/retry,
credit/refund/void и admission с Axe/overflow.

[Точные результаты и границы](evidence/2026-10-08-h4-ui-admission/VALIDATION.md),
[H-01–H-12 mapping](evidence/2026-10-08-h4-ui-admission/H_ACCEPTANCE_MATRIX.md),
[передача](NEXT_AGENT_H4_UI_ADMISSION_2026-10-08.md). Full run/review/exact-SHA CI
являются обязательными отдельными gates в evidence/новом Draft PR. FIN-03/FIN-02
остаются planned; merge/deploy/production/provider operations не разрешены.

## Previous H3: independent-review corrections F1–F5, 2026-10-08

Owner approved all five findings, including strictly verified historical mirrors
on archived accounts. Branch `codex/h3-forward-corrections` from review commit
`785fb7f`; separate draft PR targets `codex/package-h3-credit-voids`. Forward-only
`0030_h3_forward_corrections.sql` adds Unicode caseless identity, causal revision
ordering, the 198-line credit bound, exact historical mirror permission and
readiness checks for helper execution/defaults. Published 0001–0029 are unchanged.

The owner-side `gba-db check-h3-upgrade` rehearses the complete 0030 and always
rolls back. Both rehearsal and migration refuse existing identity collisions,
out-of-order payment events or oversized credits without changing financial
facts. Archive flags remain unchanged; ordinary/replacement postings still
require active accounts. [Validation and verification boundaries](evidence/2026-10-08-h3-forward-corrections/VALIDATION.md).
Local PostgreSQL regressions/upgrade/security: 47 PASS; full core run 1182 PASS,
4 SKIP before the operator command's final additions. Final-head CI is a separate
delivery gate. FIN-03/FIN-02 remain planned; no merge or production authorization.

## Previous H3 slice: credit voids, 2026-10-08 (historical snapshot)

Branch `codex/package-h3-credit-voids` from the corrections head `1d96a64`; no
merge. Forward `0029_credit_voids.sql`: an issued credit is voided by a new
immutable version that mirrors its journal (`credit_void`), undoes its C and
cancels its untouched refund (C = A); paid or unknown-outcome refunds and credits
another refunded credit relied on give `FINANCIAL_RECONCILIATION_REQUIRED`.
Code commit `5ca2165` pushed; no pull request yet. Local full 1160 passed/4
skipped/531.92s with mandatory PostgreSQL/browser; ruff/format/mypy PASS; web
gates PASS; SQL mutation red; upgrade 0028 → 0029: only 0029 applied, no row or
balance changed. [Validation](evidence/2026-10-08-h3-credit-voids/VALIDATION.md),
[handoff](NEXT_AGENT_H3_VOIDS_2026-10-08.md). H4 is next; FIN-03/FIN-02 remain
planned.

## Previous H3 slice: payment corrections, 2026-10-08

Branch `codex/package-h3-payment-corrections` from the credit-notes head
`807ed59`; no merge. Read actual HEAD/origin/PR/CI. Forward
`0028_payment_corrections.sql`: a confirmed external payment is voided or
corrected by a new revision of the same payment under a new settlement event;
its external identity stays bound forever; the replaced version's journal is
mirrored by a `payment_correction` journal, its allocations return to the
reserve of a held settlement (a released one only loses P) and a correction
confirms its replacement within that reserve. Effective P/R
(`gba.effective_payment_allocations`) everywhere. Issued credit, refund
obligation or unknown sent dependencies give `FINANCIAL_RECONCILIATION_REQUIRED`
without effects; the service checks and SQL rechecks at commit. Code commit
`238b157` pushed; no pull request yet (browser signed out). Local results:
full 1138 passed/4 skipped/493.79s with mandatory PostgreSQL/browser;
ruff/format/mypy 216 PASS; web gates PASS; SQL mutation red; upgrade 0027 → 0028
on a populated database: only 0028 applied, no row and no balance changed.
[Validation](evidence/2026-10-08-h3-payment-corrections/VALIDATION.md),
[handoff](NEXT_AGENT_H3_CORRECTIONS_2026-10-08.md),
[prompt](NEXT_AGENT_PROMPT_H3_CORRECTIONS_2026-10-08.md). Credit voids are not
implemented; FIN-03/FIN-02 remain planned.

## Previous H3 slice: credit notes and refund obligations, 2026-10-07

Branch `codex/package-h3-credits` from the PR17 head `c6c5d89`; no merge. Read
actual HEAD/origin/PR/CI. Forward `0027_credit_notes.sql` adds credit notes
against invoice and manual-accrual obligations: line by line, the unpaid
balance credited first (C), the paid remainder a separate opposite-direction
`credit_refund` obligation (100/70/50 → C 30, refund 20), one `credit` journal
that G reverse refuses. No active reserve, line capacity, a reason exactly for
another account, an explicit non-cash refund control exactly when a refund
arises, posting not before the accrual; the service checks and SQL rechecks at
commit. `gba.obligation_balance` now derives C. Code commit `76ed64e` pushed;
no pull request yet (browser signed out). Local full 1099 passed/4
skipped/513.90s with mandatory PostgreSQL/browser; ruff/format/mypy 214 PASS;
web gates PASS; SQL mutation red; upgrade 0026 → 0027 on a populated database:
only 0027 applied, no row changed.
[Validation](evidence/2026-10-07-h3-credits/VALIDATION.md),
[handoff](NEXT_AGENT_H3_CREDITS_2026-10-07.md),
[prompt](NEXT_AGENT_PROMPT_H3_CREDITS_2026-10-07.md). Payment corrections and
credit voids are not implemented; FIN-03/FIN-02 remain planned.

## Previous H3 slice: settlement guards after the H2 review, 2026-10-07

Branch `codex/package-h3-settlement-guards` from published H2 `e93ca5c`, stacked
on PR16; no merge. Read actual HEAD/origin/PR/CI. An independent static H2
money/state
[review](evidence/2026-10-07-h2-settlements/INDEPENDENT_MONEY_STATE_REVIEW_e93ca5c.md)
found no cap break but gaps F1–F4; forward `0025_settlement_guards.sql` and
`0026_settlement_guard_corrections.sql` fix them: one identity per external fact
(invisible characters removed, NFKC, case-folded, interior whitespace preserved),
disjoint cash and control accounts, posting date on or after the accrual and no
external date after the latest local date of the business's locations (UTC
without any location), and guard approval of column-level references. `0026`
corrects two defects a self-review found after draft
[PR17](https://github.com/alexeyalexandrov2026-tech/GORGONA-Booking-Platform_new/pull/17)
was opened. The four H2 test gaps now have tests. Red on unmodified H2 source 6
failed/12 passed; local full 1053 passed/4 skipped/429.52s with mandatory PostgreSQL/browser;
ruff/format/mypy 211 PASS; web unchanged. Upgrade on a populated H2 database:
only 0025 and 0026 applied, no row changed, 0 conflicting rows.
[Validation](evidence/2026-10-07-h3-settlement-guards/VALIDATION.md),
[handoff](NEXT_AGENT_H3_GUARDS_2026-10-07.md),
[prompt](NEXT_AGENT_PROMPT_H3_GUARDS_2026-10-07.md). CI on code commits
`24ee21b` and `372da57` PASS (push and pull_request runs). Credits, refunds and corrections
are not implemented; FIN-03/FIN-02 remain planned.

## Current H2 backend — bounded published implementation, 2026-10-07

Branch `codex/package-h2-settlements` from the delivered H1 backend 75e809b.
Published in [draft PR16](https://github.com/alexeyalexandrov2026-tech/GORGONA-Booking-Platform_new/pull/16), target H1 PR15; no merge.
Original checkpoint75c36da; final docs are a successor. Read actual HEAD/origin/CI.
Corrective source `15edbed1d608ada9d0901a7710c00eff28c23e71` fixes a diagnosed ledger refresh race in two web files;
financial Python/SQL and frozen migrations are unchanged from54852b4. [CI37578255793](https://github.com/alexeyalexandrov2026-tech/GORGONA-Booking-Platform_new/actions/runs/37578255793) PASS:1044 passed/1 skipped/379.86s;
all3 Docker/image, PG/browser, web69/2.3s and static211 PASS.
Fresh local full:1041 passed/4 skipped/434.68s; focused browser1/17.95s.
Bounded independent UI review PASS; full H2 money/state review remains NOT DONE.
[Handoff](NEXT_AGENT_H2_2026-10-07.md),
[exact checks/changed files](evidence/2026-10-07-h2-settlements/VALIDATION.md).
Forward 0022–0024: manual accrual as a second document kind with one new
obligation and a balanced G journal; settlement documents with approval,
reserve, sent, release and cancel, no money on reserve; externally attested
partial confirmations moving exactly R→P with one balanced journal and a
permanent external identity bound to one payment. SQL and service both enforce
nonnegative P/C/R and P+C+R<=A at commit.
Historical author full1041/4/459.51s; fresh corrective full is above. Mandatory PostgreSQL/browser;
lint/format/mypy 211 PASS; web typecheck/lint/format/69 unit/build PASS.
Exact-checkpoint [CI37573680437](https://github.com/alexeyalexandrov2026-tech/GORGONA-Booking-Platform_new/actions/runs/37573680437) on75c36da PASS:
1044 passed/1 skipped/381.36s, all3 Docker/image, PG/browser, 69 web tests/2.3s, static211.
Independent money/state review NOT DONE.
FIN-03/FIN-02 remain planned; H3–H4 and all twelve complete H criteria remain
NOT TESTED. G/FIN-01 retains technically_verified. No H UI, provider, funds,
merge, deployment or production migration. Next coherent work is H3 credits,
refund obligations and corrections.

## Historical H1 backend — bounded implementation, 2026-10-06

Branch `codex/package-h1-persistence` from foundation18e3f5e, reviewed
source2d5a8f9. [Draft PR15](https://github.com/alexeyalexandrov2026-tech/GORGONA-Booking-Platform_new/pull/15)
targets PR14. [Handoff](NEXT_AGENT_H1_BACKEND_2026-10-06.md),
[exact checks/changed files](evidence/2026-10-06-h1-backend/VALIDATION.md).
Forward0021, typed invoice draft/history/issue, immutable principal obligation,
atomic balanced G origin/lineage/audit/receipt, permanent recovery and negotiated
journal-v2 are implemented behind closed finance_documents readiness.
Root full953/4skip/378.14s; lint/format/mypy204 PASS. Independent H1-R01 closure:
47 real PG and109 relevant units PASS, own checkout/cluster.
FIN-03/FIN-02 remain planned; H2–H4 and complete H criteria remain NOT TESTED.
G/FIN-01 retains technically_verified. No invoice UI, provider, funds, merge,
deployment or production migration. Next coherent work is H2 settlement flow.

## Historical H1 foundation: contracts and invariants, 2026-10-06

Ветка codex/package-h-invoices, source843d0b3, parent925ae02/PR13.
[Передача H1](NEXT_AGENT_PACKAGE_H1_2026-10-06.md),
[проверки и независимый обзор](evidence/2026-10-06-h1-foundation/VALIDATION.md).
Реализована проверенная основа: строгие контракты, точная арифметика и закрытый
finance_documents gate/registry2. H1 IN PROGRESS: SQL/API/денежного выпуска/UI
еще нет. FIN-03/02 planned; G остается technically_verified. Local continuation
разрешено владельцем; никакой production/provider приемки не было.

## Актуально H: архитектурный план, 2026-10-06

От G `5be6e7a`, собственная ветка `codex/package-h-finance-plan`.
[План H](PACKAGE_H_PLAN_2026-10-06.md),
[ADR-0024 Proposed](../adr/0024-invoices-obligations-and-external-settlements.md),
[reuse evidence](evidence/2026-10-06-package-h-plan/ARCHITECTURE_REUSE.md).
Только документация; новых endpoints, money effects и migration0021 нет.
FIN-03/FIN-02 planned; положительная provider capability не выдается. G принят
отдельно и сохраняет свой статус. Независимый обзор предлагаемого дизайна
PASS: H-D01/02/03 закрыты уточнениями. [Проверки и отчеты](evidence/2026-10-06-package-h-plan/VALIDATION.md).
До кода подтвердить объем H, credit/refund и явный выбор счетов/признания.

## Актуально G: финансовая основа FIN-01, 2026-10-06

От принятого плана этапа 2 `151472a`, ветка `codex/package-g-ledger-review`.
Собственная рабочая копия, прежний незакоммиченный вариант сохранен.
Миграция 0020: книги юридических лиц, версии настроек/счетов, точные суммы,
двойная запись, неизменяемая история, сторно и события закрытия/открытия месяцев.
Реальные API и /ledger; права owner/manager всей компании, карта v5, FORCE RLS,
module gates и проверка определений.

Regression red→green подтвердил исправление SQL-обхода баланса. Пять замечаний
независимого обзора исправлены: сторно/поздние строки, stale snapshot, точные SQL
литералы, recovery после reload/nav и арифметика строки ведомости. Focused:
68 Python + 4 desktop/mobile browser после приемки без promotion override;
SQL-гонки с наблюдением lock; 68 web unit; статика 197 файлов и web build PASS.
Дополнительная permissive policy теперь вызывает 503 на всех восьми таблицах.
`95a0de4`: full local 858 passed/4 skipped; exact-SHA CI 861 passed/1 skipped,
включая обязательный Docker. Независимые обзоры закрыли 3 P1 и 4 P2; final guard
review — code/unit, PG runtime подтвержден отдельно local/CI. finance/FIN-01
technically_verified отдельным коммитом приемки. Свежий CI приемочного HEAD —
в [PR #12](https://github.com/alexeyalexandrov2026-tech/GORGONA-Booking-Platform_new/pull/12).
[Приемка](evidence/2026-10-06-ledger/ACCEPTANCE.md),
[передача](NEXT_AGENT_PACKAGE_G_2026-10-06.md). H–K и промышленная эксплуатация
этой реализацией не закрываются.

## Актуально: этап 1 технически закрыт, 2026-10-06

Ветка `claude/stage1-closure` поверх F (`ed7884e`, draft PR #11). CORE-01–04 PASS
технически; новый тест `test_stage1_scenarios.py` проводит малый бизнес, сеть
независимых компаний и гибридную компанию с двумя филиалами через все модули этапа 1
без дублирования и утечки. Исправлено: уведомление «результат неизвестен» больше не
показывается во время обычного запроса (договоры, документы, контрагенты). Полная
локальная suite 790 passed / 4 skipped / 303.39 s. CORE-03 для TMS (диспетчерские
полномочия, офлайн-черновики) — этап 3. Production-миграции и backfill NOT TESTED.
Следующий этап — 2 (финансы, персонал, материалы): сначала план и ADR на решение
владельца. [Evidence](evidence/2026-10-06-stage1/ACCEPTANCE.md).

## Актуально F шаг 2: служебные резервации и CORE-04, 2026-10-05

Миграция 0019: `resource_reservations` — второй реальный потребитель общей
занятости; запись и резервация одного ресурса одновременно дают ровно один
активный интервал (сервисы и сырой SQL без блокировок), многоресурсная неудача
ничего не оставляет. Страница `/reservations/`, доступность клиентов учитывает
резервации. Полная локальная suite 787 passed / 4 skipped; код `bf3645d` push CI
37411493038 success. CORE-04: PASS (локально и CI).
[Evidence](evidence/2026-10-05-occupancy/ACCEPTANCE.md).

## F шаг 1: общая занятость ресурсов, 2026-10-05

Ветка claude/package-f-occupancy. Миграция 0018: `resource_allocations` — одна
таблица занятости для всех модулей (исключение пересечений для held/confirmed,
FORCE RLS, область филиала через ресурс), триггеры точного зеркала
`booking_allocations` и защиты строк; перенос данных до 0018 — операторской
командой `backfill-occupancy` по компании (миграции не обходят RLS). Полная
локальная suite 775 passed / 4 skipped; код `f74b5de` push CI 37408551883 success.
CORE-04 еще NOT TESTED (шаг 2: служебная резервация).
[Evidence](evidence/2026-10-05-occupancy/ACCEPTANCE.md).

## Актуально E3: договоры с контрагентами, 2026-10-05

Ветка claude/package-e3-agreements от E2 c5a3908. Миграция 0017: `agreements` и
`agreement_versions` только для вставки (черновик → подписан вне платформы →
дополнение → … → расторгнут), FORCE RLS, ограничение всей компанией, два gate
модуля counterparties, guard 40 определений и двенадцать gates. Решения
владельца: расторжение действует на последнюю подписанную версию, открытый
черновик дополнения закрывается как отмененный; дата расторжения может быть в
будущем. Независимый обзор: 2 средних и 7 низких дефектов исправлены. Полная
локальная suite 767 passed / 4 skipped / 276.37 s; код `3044f97` прошел push CI 37389126365 (success).
counterparties остается technically_verified (реестр версии 1). PR не созданы —
нет gh/авторизации. Результаты и ограничения —
[evidence](evidence/2026-10-05-agreements/ACCEPTANCE.md),
[передача](NEXT_AGENT_PACKAGE_E3_2026-10-05.md). Электронная подпись, Azure,
провайдеры, нагрузка и production NOT TESTED; merge/deploy/промышленные миграции
не выполнялись.

## Актуально E2: документы, файлы и связи с контрагентами, 2026-10-05

Ветка claude/package-e2-documents от E2-A 4a6f63b. Миграция 0016: четыре
FORCE-RLS таблицы только для вставки (файлы в bytea до 10 MiB с проверкой SHA-256
и размера в БД, документы, версии, журнал связей), guard 38 определений и десять
module gates. API загрузки (сырое тело, 503 в staging/production до чтения тела),
проверенного скачивания, версий и связей; страница /documents/ и связанные
документы в карточке контрагента. Код `2ab24f3` прошел push CI 37289072512
(success); отдельный коммит приемки переводит documents в **technically_verified**
(реестр версии 1, включение только явной публикацией). PR CI нет — PR не создан. Независимый обзор: 4
дефекта (2 средних, 2 низких) исправлены. Результаты и ограничения —
[evidence](evidence/2026-10-05-documents/ACCEPTANCE.md),
[передача](NEXT_AGENT_PACKAGE_E2_2026-10-05.md). Антивирус, Azure, провайдеры,
нагрузка и production NOT TESTED; merge/deploy/промышленные миграции не выполнялись.

## Актуально E2-A: ограниченная проверка файлов и CSP, 2026-10-05

Новая ветка codex/package-e2-file-validation от принятого E1 3983dd4 добавляет
типизированный валидатор поддерживаемого PDF/PNG/JPEG-профиля и сохранение
существующих API CSP в отдельной политике. Новых БД/API/UI документа нет,
documents остается planned. Зависимости, роли, RLS и миграции не меняются.
Focused81, Ruff/format/mypy168, web47/typecheck/lint/format/build15 PASS.
Полная локальная suite после последнего исправления: 677 passed/4 skipped/204.12s,
exit0; PostgreSQL/браузеры обязательны, три Docker gate и один внешний site gate
пропущены локально. Контейнеры должны пройти в CI.
Код ce31e21de2d1d290408ace74628ed928d728deb8: PR CI 37280252370 —
680 passed/1 skipped/127.85s; push CI 37280214524 — 680/1/154.96s.
Обязательные PostgreSQL/browser/container gate выполнены; web 47 и build 15 PASS.
Draft [PR #8](https://github.com/alexeyalexandrov2026-tech/GORGONA-Booking-Platform_new/pull/8)
→ codex/package-e1-counterparties, без merge. Точный CI коммита документации
проверяется отдельно. [Evidence](evidence/2026-10-05-file-validation/ACCEPTANCE.md),
[передача](NEXT_AGENT_E2_FILE_VALIDATION_2026-10-05.md).
Независимый аудит: исправления PDF-вложений/3D, чисел, page-tree и JPEG MCU
проверены, 20 PDF + 9 JPEG probes PASS. Общая совместимость,
malware/render safety и полный E2 NOT TESTED.

## Текущее продолжение: E1, 2026-10-05

Общие контрагенты реализованы в отдельной ветке `codex/package-e1-counterparties`
поверх E0 `bbe6ecd80d8827ca94a63f15587704ffc22dba62`. Новая миграция 0015:
карточки и контакты с версиями, ручные решения о дублях, подтвержденные связи
с клиентами записей; исходные снимки записей не изменяются. Доступ только
owner/manager всей компании; FORCE RLS, 34 определения guard, пять module gates,
атомарные reference-only receipts/audit. Страница `/counterparties/` работает
с реальными API/БД; проверены desktop/mobile и автоматическая доступность.

Локально: полная suite **595 passed / 4 skipped / 248.75 s**, затем отдельный
добавленный readiness-тест **1 passed / 1.89 s**; web **47 unit**, сборка **15**
страниц, typecheck/lint/format PASS; Ruff/mypy **163** файла PASS. PostgreSQL
18.6 и браузеры обязательны; три контейнерных и один дополнительный внешний
site gate пропущены локально. Независимый ограниченный обзор чувствительного
кода завершен после исправлений; это не самостоятельный прогон reviewer в БД.

Код `2392566595a2df59f8ec3f073ed9bf184df6447f` прошел два полных CI: push **599 passed / 1 skipped / 118.52 s**,
PR **599 passed / 1 skipped / 171.17 s**. Контейнерные gates выполнены в CI.
Отдельный коммит приемки переводит только counterparties в **technically_verified**,
реестр версии 1; исходный business baseline остается booking-only. Проверено
явное включение через публикацию конфигурации без registry override: focused
**68 passed / 37.26 s**. Финальный SHA приемки требует своего CI; свежий результат
публикуется в PR и STATE.json архива, прежний CI не переносится на новый SHA.
Ссылки на SHA/PR/CI и точные границы — в
[приемке E1](evidence/2026-10-05-counterparties/ACCEPTANCE.md).
Начните с [актуальной передачи](NEXT_AGENT_PACKAGE_E1_2026-10-05.md).
[Draft PR #7](https://github.com/alexeyalexandrov2026-tech/GORGONA-Booking-Platform_new/pull/7) идет в `codex/package-e-isolation-audit`; PR #6 остается отдельным.
Основная копия владельца с незакоммиченной работой сохранена.

Следующие шаги: E2 документы/файлы, E3 договоры по ADR-0020, затем F/CORE-04.
Этап 1 частичен; 39 отраслей/28 критериев сохранены, полные отраслевые циклы
planned. Azure, реальные провайдеры, нагрузка/восстановление, отраслевые пилоты,
промышленная эксплуатация и ручная screen-reader приемка NOT TESTED.
Ни merge, ни deployment, ни промышленная миграция не выполнялись.
Azure/load tool ниже — исторические проверки E0. npm audit повторен 2026-10-05:
prod **0, exit 0**; общий **5 high dev, exit 1** одной braces-цепочки, без
изменения зависимостей. Прежняя Desktop/handoff777 сейчас отсутствует; новая
передача использует отдельную папку GORGONA_HANDOFF_2026-10-05.

Полный финальный локальный прогон приемки: **596 passed / 4 skipped / 251.25 s**,
exit 0, обязательные PostgreSQL/browser и обычный реестр без override. Ранее
попытка дала 302 setup errors из-за остановленной тестовой БД; после проверки
и запуска только disposable 51454 smoke и полный повтор прошли. Это не
промышленный restart. Подробности и оба результата сохранены в приемке.

Принятая версия readiness `e68ce907ba0459ab99e4c71137c044694a920be1`
имеет собственный зеленый CI: [PR run37272593391](https://github.com/alexeyalexandrov2026-tech/GORGONA-Booking-Platform_new/actions/runs/37272593391)
**599 passed / 1 skipped / 173.32 s** и
[push run37272589058](https://github.com/alexeyalexandrov2026-tech/GORGONA-Booking-Platform_new/actions/runs/37272589058)
**599 passed / 1 skipped / 163.07 s**. Web47, mypy163, PostgreSQL/browser/container
gates выполнены; единственный skip — дополнительный внешний site gate. Следующий
документационный HEAD проверяется отдельно и не выдается за эту версию кода.

## Исторические записи до E1

## Актуальное дополнение: аудит E0, 2026-10-04

Продолжение — [передача после аудита E0](NEXT_AGENT_AUDITED_E0_2026-10-04.md),
код 4ad645fc27a2334f55e5c7c47ee1e3de8eede3a5, draft PR #6 в актуальную
codex/universal-business-foundation от 2f16380. Основная копия владельца сохранена.
Исправлены company predicates и web readiness contract по полученному пакету E.
Свежая regression: 7 failed / 4 passed до кода, 1 web failed; после — focused30,
полная локальная suite 538 passed / 4 skipped / 193.26 s, web42 и сборка14,
Ruff/mypy153 PASS. CI конкретного SHA и пределы — в
[приемке E0](evidence/2026-10-04-isolation-audit/ACCEPTANCE.md).
Переданные [план E](PACKAGE_E_PLAN_2026-10-04.md) и
[ADR-0020](../adr/0020-counterparties-documents-and-contracts.md) сохранены;
E1–E3 и CORE-04 еще не выполнены. Исторические цифры/следующие задачи ниже
не считать актуальнее этого дополнения без проверки.

Azure прочитан: Container Apps env Failed, apps0; PostgreSQL18/KeyVault private.
Сквозной staging BLOCKED. В npm остаются 5 dev findings одной braces-цепочки,
prod0; load tool воспроизводит ложный PASS и пока не принят для OPS-02.
Новых провайдеров, сканера файлов, отраслевых пилотов и промышленного запуска нет.


**Рабочая копия после решения владельца 2026-10-04:** `C:\Users\alexa\Documents\ChatGPT\Gorgona Booking`, origin `alexeyalexandrov2026-tech/GORGONA-Booking-Platform_new`, ветка `codex/universal-business-foundation`. Исходный checkout и полная история сохранены; [отчет переноса](REPOSITORY_TRANSITION_2026-10-04.md) содержит свежую сверку файлов и отдельные результаты новой копии. Проверки ниже относятся к исходному пакету прав филиалов; их не выдавать за новый запуск.

**Уточненная граница:** реестр относится к самостоятельной GORGONA. KA Nails — отдельный проект, вне текущей разработки и приемки. Сохраненные проверки внешнего сайта описывают исторический дополнительный сценарий, не зависимость платформы.

## Актуальная проверка выполнения плана

[Аудит 2026-10-04](GORGONA_PLAN_AUDIT_2026-10-04.md) проверяет опубликованную базу `f8db038` и отдельные текущие изменения. Все 28 критериев сопоставлены с кодом: BASE и профильные CORE имеют ограниченное техническое доказательство; этап 1 остается частичным; полные отраслевые процессы не приняты. Полный GitHub CI базы дал 382 passed / 1 optional external-site skip с обязательными PostgreSQL/browser/container gates. Этот PASS не переносится автоматически на измененный SHA.

Обнаружен и исправлен отдельный P1: development-only `POST /v1/holds` больше не регистрируется в staging/production. Четыре regression cases дали 201 до исправления; после него 55 связанных API unit tests прошли (exit 0, 2.06 с), Ruff/format и strict mypy прошли для 123 файлов. Клиентский API, staff API и локальная разработка сохранены. Следующий продуктовый пакет — юридические лица внутри существующего tenant с версиями, разграничением, аудитом и рабочим UI; его наличие пока не заявляется.

Подробности аудита, текущего diff и новый полный CI фиксируются отдельно от исторической приемки ниже. Отдельный текущий сценарий не закрывает этап или универсальную платформу целиком.

### Следующий пакет: черновики юридических лиц

Поверх аудитной версии `511df53fc4aa4dcc9fbcc339a82a07f4a0a16db5` написан следующий связный пакет: юридические лица внутри прежнего tenant, уникальная неизменяемая внутренняя ссылка, имена и история версий, API чтения/сохранения, idempotency, конфликт версий/дублей, атомарный audit и рабочий интерфейс в Business profile. Новая миграция 0010 добавляет FORCE RLS и две company-only policies; guard требует 19 определений. Старые миграции и существующие записи не изменены. [ADR-0015](../adr/0015-tenant-owned-legal-entity-drafts.md) задает границы и приемку.

**Техническая приемка пакета:** опубликован `d97924f53a8ff34a69f82d36fe675b965e8aa6e6`; полный [PR CI 37204951503](https://github.com/alexeyalexandrov2026-tech/GORGONA-Booking-Platform_new/actions/runs/37204951503) и push CI прошли. В PR: **413 Python tests passed, 1 optional external-site skip, 91.41 с, exit 0** с обязательными PostgreSQL/browser/container gates, 15 contract и 9 legal-entity PG/API tests. Web unit11, typecheck/lint/format/build14, Ruff/format и strict mypy128 — PASS. Company-wide desktop/mobile браузеры прошли сохранение, потерю ответа/безопасный retry, историю, конфликт/перезагрузку; SQL подтвердил две отдельные записи по четыре версии и отсутствие их у другого tenant. [Полное доказательство и границы](evidence/2026-10-04-legal-entities/ACCEPTANCE.md).

Независимый review нашел пропуск новых маршрутов в центральной проверке ответов: четыре regression cases воспроизвели ошибку, после подключения строгих схем web unit11 проходит; неизвестные операции остаются запрещенными. Reviewer не запускал тесты. Локальные Python/runtime tests после реализации не выполнялись из-за отклоненного разрешения; полный runtime PASS получен в отдельно разрешенной публикации GitHub/CI, не на локальной БД. Начальный ModuleNotFoundError не является функциональным PASS. После изменения кода требуется новый точный SHA и свежие проверки.

Это подготовленные черновики организации, не подтверждение регистрации и не выполненный CORE-03: группы, подразделения, финансовые связи и межкомпанейское делегирование остаются впереди. Продолжение после приемки этого пакета — структура/делегирование, публикация и общая занятость.

### Пакет CORE-03, шаг A: подразделения

Поверх `eaa62339cf82ea69b96f2e8ec346ede585729f02` реализованы подразделения внутри прежнего tenant ([ADR-0016](../adr/0016-tenant-owned-departments.md)). Миграция 0011 добавляет неизменяемые идентичности и версии с FORCE RLS и двумя company-only policies; guard требует 21 определение. Версия хранит название, необязательные родителя, юридическое лицо и филиал своей компании (составные FK) и признак архива. Под `business-structure` lock сервер отклоняет цикл, собственного родителя, цепочку глубже 32 уровней, активное подразделение под архивным и архивирование при активных дочерних. API `/v1/businesses/{id}/departments`, idempotency, expected revision, атомарный аудит и раздел в Business profile повторяют проверенный образец юридических лиц. Сотрудники, руководители, бюджеты и права доступа не назначаются.

Порядок по решению владельца: шаг A — подразделения; шаг B — межкомпанейское делегирование с двусторонним согласием (делегат читает и изменяет записи, но не настройки, участников и структуру); шаг C — модель групп компаний. У каждого шага свой коммит и полный CI.

| Проверка шага A | Фактический результат |
|---|---|
| Ruff check и format | PASS, exit 0; 130 Python-файлов |
| Strict mypy | PASS, exit 0; 133 source files |
| API unit, включая новые контракты | PASS: 218, 11.22 с |
| Web typecheck, ESLint, Prettier | PASS, exit 0 |
| Web unit, включая 5 новых проверок границы ответов | PASS: 16 |
| Web build | PASS, 14 статических страниц |
| PostgreSQL 18.6 focused: departments, legal entities, location access, roles/migrations, identity schema, tenant isolation | PASS: 69, 29.12 с |
| Management browser harness (OIDC → API → PostgreSQL), desktop/mobile | PASS: 2 pytest; Playwright 7 passed / 1 намеренный skip, филиальный 2 passed; SQL подтвердил версии подразделений и их отсутствие у другого tenant |
| Полная API suite, PostgreSQL 18.6 и обязательные браузеры | **PASS: 445; 4 skipped; 215.10 с.** Пропуски: три container gate (Docker на машине нет) и дополнительный внешний site gate |
| Публикация и CI | Коммит `5b3c00b11e2bb2e844a3183bbd840ca36d764895` отправлен в ветку; **PASS**: PR CI [37235035509](https://github.com/alexeyalexandrov2026-tech/GORGONA-Booking-Platform_new/actions/runs/37235035509) и push CI 37235032875, все шаги успешны; точные счетчики CI не получены (логи требуют авторизации). [Приемка](evidence/2026-10-04-departments/ACCEPTANCE.md) |

Локальный кластер: прежний `%LOCALAPPDATA%\GorgonaBookingTests\postgres-18.6` уже работал на 127.0.0.1:51454, запущенный другим процессом в 15:58, и недоступен в файловом представлении этого исполнителя; его не использовали и не останавливали. Для проверки скачан официальный EDB-архив PostgreSQL 18.6 (343 808 005 байт, SHA256 `fbe23da234ee31547bf8a36d29dfd81e82b849df2d2b78d2eecb43d360252f8c`) и создан отдельный одноразовый кластер `claude-cluster` на 127.0.0.1:51455 с приватными учетными данными вне репозитория. После проверок он остановлен (`pg_ctl status`: no server running), данные сохранены; кластер на 51454 продолжает работать.

Новые тесты написаны вместе с новым кодом; красная фаза для новой функции — отсутствие модуля и маршрутов, а не воспроизведенный дефект. Контейнерные gates локально не выполнялись; их покрывает CI.

### Пакет D (CORE-02): публикация конфигурации, реестр модулей и записи готовности

Владелец согласовал план и [ADR-0019](../adr/0019-configuration-publication-and-modules.md) 2026-10-04: версии конфигурации draft → validated → published → superseded, реестр 18 модулей в коде (включать можно только готовый optional `booking_resources`), реестр готовности 28 сценариев и 39 профилей отдельно от каталога, миграция 0014, блокировка новых записей триггером БД при отключенной записи. Без публикации действует прежнее поведение.

Реализовано: `business/modules.py`, `business/readiness_registry.py` (каталог берет `workflow_readiness` из реестра), `business/configurations.py` и общий помощник команд `business/commands.py`, API `/v1/businesses/{id}/configuration…`, `module-catalog`, `readiness-registry`, `booking_enabled` в workspace; миграция 0014 (версии, выбор модулей, состояния модулей, триггеры переходов и неизменяемости, триггер `bookings_require_booking_module` с shared advisory lock); schema guard — 29 определений с раздельной проверкой USING/WITH CHECK плюс триггер записи. Web: панель «Configuration» (готовность модулей, черновик, предпросмотр, проверка, публикация с подтверждением, история, повтор тем же ключом), Calendar/Bookings/Overview скрывают создание и перенос при отключенной записи.

| Проверка пакета D | Фактический результат |
|---|---|
| Ruff check/format, strict mypy | PASS, 151 source files |
| Web typecheck, ESLint, Prettier, build | PASS, 14 страниц |
| Web unit | PASS: 41 (7 новых проверок границы ответов) |
| API unit | PASS: 268 (18 новых: входы, реестр модулей без циклов, 28 сценариев = мастер-план, 39 профилей, доказательства существуют, каталог = реестр) |
| PostgreSQL `test_configurations.py` | PASS: 13 — цикл с историей и повтором ключа; CORE-02 гонки черновиков и публикаций [200, 409]; объяснимые отказы; отключенная запись: кабинет, перенос, филиал, делегат, клиентский сайт 409 `MODULE_DISABLED`, подтверждение HOLD/отмена/чтение работают, другая компания не затронута, повторное включение; упорядочение с lock публикации; прямой SQL; 6 видов повреждения → readiness 503; права |
| Browser harness: компания, филиал, делегирование, группы, конфигурация (desktop/mobile) | PASS: 5; владелец отключил запись, проверил, увидел предпросмотр, опубликовал после потерянного ответа тем же ключом, получил 409 и экран без создания/переноса при сохраненной истории, включил запись версией 2; Axe и ширина mobile; SQL: версии 1 superseded/2 published, состояние модуля, аудит 2×(drafted, validated, published), лишних записей нет |
| Полная API suite, PostgreSQL 18.6, браузеры | **PASS: 527; 4 skipped; 354.53 с** (три container gate без Docker, внешний site gate) — до правок ревью; после правок повторно: unit + конфигурация + группы + все 5 браузерных harness **292 passed** |
| Review `/code-review high` (в той же сессии) | 6 находок: исправлены 4 (обрезанная история без пометки, кнопки до загрузки workspace, двойной запрос профиля, дубликат базового контракта); 2 записаны в ADR-0019 (клиентский bootstrap не сообщает об отключении; стоимость проверки триггера в guard) |
| Тест `test_location_access` (missing_boundary) | Обновлен: восстанавливает политики 0014 после `drop … cascade` |
| CI точного SHA | **PASS** на `5320c4a`: PR CI [37244707198](https://github.com/alexeyalexandrov2026-tech/GORGONA-Booking-Platform_new/actions/runs/37244707198), push CI 37244704525, все шаги успешны; счетчики CI не получены. [Приемка](evidence/2026-10-04-configuration/ACCEPTANCE.md). Статус CORE-02 в `readiness_registry.py` поднят до technically_verified отдельным коммитом документов/данных |

Новые тесты написаны вместе с кодом; красная фаза — отсутствие модуля/маршрутов (unit-тест реестра падал до появления интеграционного теста). Контейнерные gates локально не выполнялись.

### Пакет CORE-03, шаг C: модель групп компаний

Реализовано по [ADR-0018](../adr/0018-company-groups.md): миграция 0013 (группы организатора, история членства с двусторонним согласием, триггер переходов, RLS: участник видит только свое членство; guard 25 определений), API групп, панель «Company groups» в Business profile. Членство не используется ни одним путем авторизации и не дает доступа к данным сторон (проверено API и браузером). Сводные отчеты групп — этап 7, только через явные гранты.

| Проверка шага C | Фактический результат |
|---|---|
| Ruff check/format, strict mypy | PASS, 143 source files |
| Web typecheck, ESLint, Prettier, build | PASS, 14 страниц |
| Web unit | PASS: 34 |
| PostgreSQL `test_groups.py` | PASS: 5 (согласие и история, отсутствие доступа, стороны/права/состояния/гонка, прямой SQL, readiness) |
| Browser harness: компания, филиал, делегирование, группы (desktop/mobile) | PASS: 4; участник вступил после потерянного ответа (один ключ), получил 403 к записям партнера, создал свою группу, пригласил и исключил партнера, вышел; SQL подтвердил членства и аудит |
| Полная API suite, PostgreSQL 18.6, браузеры | **PASS: 494; 4 skipped; 319.01 с** (три container gate без Docker, внешний site gate) |
| Review `/code-review high` | 4 находки: исправлена 1 (ввод приглашения после конфликта); 3 записаны как известные ограничения в ADR-0018 (нет пагинации членств, нет блокировки приглашающих, дублирование помощников команд) |
| CI точного SHA | История: **FAIL** на `c9193b2` (PR CI 37239459492, push CI 37239457054, шаг `uv run pytest`; логи требуют авторизации). Найдена гонка в решениях групп (remove раньше accept давал 404 вместо 409). Исправлено: поиск последнего членства без фильтра статуса; детерминированный регрессионный тест FAIL до исправления и PASS после; локально группы 6 passed, полная suite 495 passed / 4 skipped. **PASS** на `6a81dfd`: PR CI [37240229184](https://github.com/alexeyalexandrov2026-tech/GORGONA-Booking-Platform_new/actions/runs/37240229184), push CI 37240226759, все шаги успешны; счетчики CI не получены. [Приемка](evidence/2026-10-04-groups/ACCEPTANCE.md) |

### Пакет CORE-03, шаг B: межкомпанейское делегирование

Реализовано по [ADR-0017](../adr/0017-cross-company-delegation.md): миграция 0012 (гранты с неизменяемыми условиями, двустороннее согласие, история делегатов, триггер переходов, RLS для обеих сторон, guard 23 определения), делегированный путь авторизации без SECURITY DEFINER и обхода RLS. Он проверяет активный неистекший грант и делегата в контексте владельца, затем активное неограниченное членство и активность обслуживающей компании в ее контексте; эффективные права равны пересечению гранта и роли. Сотрудник, приостановленный владельцем, не возвращается через грант. API выдачи/принятия/отклонения/отзыва/смены делегатов, `/v1/me.delegations`, переключатель кабинета с ограниченной навигацией и панель «Delegated access» в Business profile. Делегат работает только с записями: ровно 11 обработчиков; клиенты, аудит, настройки, юр. лица, подразделения и участники недоступны. Попутно исправлен `list_members`: он возвращал собственные членства вызывающего в других компаниях (red→green тест). Остальные такие запросы вынесены в отдельную задачу.

| Проверка шага B | Фактический результат |
|---|---|
| Ruff check/format, strict mypy | PASS, 138 source files |
| Web typecheck, ESLint, Prettier, build | PASS, 14 страниц |
| Web unit | PASS: 25 |
| PostgreSQL `test_delegations.py` | PASS: 10 (CORE-03/TMS-02 сценарии, прямой SQL, гонка, третья компания, отзыв/истечение, приостановка, член владельца) |
| Browser harness: компания, филиал, делегирование (desktop/mobile) | PASS: 3; делегат принял предложение после потерянного ответа, выдал и отозвал собственное, записал и отменил клиента в филиале владельца, завершил доступ; SQL подтвердил оба гранта, бронь в компании владельца и аудит только реального исполнителя |
| Полная API suite, PostgreSQL 18.6, браузеры | **PASS: 479; 4 skipped; 298.22 с** (три container gate без Docker, внешний site gate) |
| Независимый review (`/code-review high`) | 8 находок: исправлены 4 (обход приостановки владельцем, изменяемые поля решения, устаревший выбор делегатов, границы даты); пропущены осознанно 4 (аудит каждого запроса — требование мастер-плана; `/me` не видит статус чужой компании; хрупкий тест маршрутов; общий дефект self-read — отдельная задача) |
| CI точного SHA | **PASS** на `ed370c6`: PR CI [37238206491](https://github.com/alexeyalexandrov2026-tech/GORGONA-Booking-Platform_new/actions/runs/37238206491), push CI 37238204250, все шаги успешны. [Приемка](evidence/2026-10-04-delegation/ACCEPTANCE.md) |

## Сохраненный пакет филиальных прав

**Актуально: 2026-10-04, после второго пакета этапа 1 — права филиалов.** Предыдущая технически проверенная основа сохранена в [CHECKPOINT_2](GORGONA_IMPLEMENTATION_STATUS_CHECKPOINT_2.md); первоначальная передача — в [CHECKPOINT_1](GORGONA_IMPLEMENTATION_STATUS_CHECKPOINT_1.md). Их результаты относятся к историческому дереву.

## Реализовано в этом пакете

- Активный сотрудник с одним назначенным филиалом может открыть рабочий кабинет, календарь, записи, клиентов и сотрудников этого филиала. Менеджер создает, переносит и отменяет записи, меняет сотрудников, их часы и назначенные услуги внутри своего филиала. Права роли остаются обязательными: artist не создает записи, front_desk не управляет сотрудниками.
- Сервер берет филиал из проверенного членства в той же транзакции. Обработчики допускают филиальные права только явно; остальные сохраняют требование доступа ко всей компании. `/me` возвращает область членства.
- Миграция 0009 добавляет ограничивающие runtime RLS-политики поверх прежней изоляции компаний. Проверяются родительские связи записей, клиентов, событий, распределений, сотрудников, часов и назначенных услуг. Произвольный фильтр браузера не расширяет доступ. Миграции 0001–0008 не переписывались.
- Новый `/v1/salons/{id}/workspace` дает разрешенные филиалы и часы без общих настроек, подтверждений фактов и разрешенных доменов. Четыре рабочих экрана используют этот ответ. Общий каталог читается для выбора услуги, но изменение каталога, профиль бизнеса, настройки и управление членством остаются операциями всей компании.
- Владелец может выдать приглашение с филиалом своей компании. Филиал приглашения неизменяем; принятие сохраняет именно эту область, в том числе при повторе. Ограниченный менеджер не управляет приглашениями. Приглашение owner требует доступа ко всей компании.
- Запуск, readiness и допуск филиального запроса проверяют утвержденные определения функции и всех 17 политик, их роль, команды, FORCE/ENABLE RLS и выражения. Отсутствующие или ослабленные правила дают отказ до чтения данных. Проверка использует канонические выражения PostgreSQL 18; изменение определений или основной версии базы требует согласованного обновления миграции, guard и тестов.
- Старые сохраненные ответы операций без `location_timezone` читаются совместимо: настоящий часовой пояс берется из разрешенного филиала, исходные бизнес-значения сохраняются, операция не повторяется. Текущая область доступа проверяется до возврата старого ответа. Отзыв членства блокирует следующую операцию.
- Интерфейс показывает назначенную область и скрывает общие разделы у филиального сотрудника. Исправлено расширение мобильного viewport с 390 до 418 px из-за выбора филиала; проверка теперь сравнивает ширину с заданным размером устройства.

Прежняя основа сохранена: полный план 39 отраслей, типизированный каталог, гибридный черновик профиля, цены и дополнения, ISO-дни, локальные даты/DST, несколько интервалов часов, стоимость записи отдельно от оплаты, старый salon API и общий клиентский интерфейс платформы. Все полные отраслевые циклы в каталоге по-прежнему `planned`.

## Сохраненные проверки исходного дерева

| Проверка | Фактический результат |
|---|---|
| API, полная suite, PostgreSQL 18.6 и обязательные браузеры | **PASS: 379; 4 skipped; 113.70 с; exit 0** |
| Location API/RLS + role/migration — focused | PASS: 24, 5.63 с, exit 0 |
| Location API + оба management browser harness — focused | PASS: 13, 25.25 с, exit 0 |
| Обычный management Playwright | PASS: 3; 1 намеренный skip повторного мобильного цикла. Профиль desktop/mobile и прежняя запись desktop |
| Филиальный management Playwright | PASS: 2 — desktop/mobile, реальный OIDC PKCE → API → PostgreSQL; запись/перенос/отмена и часы. Чужая запись остается CONFIRMED |
| Web unit | PASS: 6 |
| Web typecheck, ESLint, Prettier, build | PASS, exit 0; 14 статических страниц |
| Ruff check/format и strict mypy | PASS, exit 0; 123 Python-файла |
| Axe WCAG 2 A/AA, мобильный viewport, визуальный просмотр | PASS в проверенных состояниях; изображения только FAKE-данных: [desktop](evidence/2026-10-04-location-access/location-access-1280.png) и [mobile](evidence/2026-10-04-location-access/location-access-390.png) |
| Документы и окончательный diff | **PASS**: git diff --check; UTF-8, пробелы и локальные ссылки проверены после последней правки |
| Независимый read-only reviewer | PASS: первоначальные находки воспроизведены и исправлены; итоговый обзор без новых существенных находок. Reviewer не запускал БД-тесты |

Red→green подтвержден: отсутствие scoped допуска давало 403; старый receipt вызывал ValidationError; отсутствующая/ослабленная policy или функция открывали чужой филиал; мобильный viewport был 418 вместо 390. Финальные focused проверки выше прошли после исправлений.

## Измененные файлы этого пакета

- Сервер: `api/src/gorgona_booking/api/members.py`, `api/src/gorgona_booking/api/salons.py`, `api/src/gorgona_booking/tenancy/authorization.py`, `api/src/gorgona_booking/identity/invitations.py`, `api/src/gorgona_booking/db/pool.py`, `api/src/gorgona_booking/db/provisioning.py`, новый `api/src/gorgona_booking/db/schema_guard.py`, новая `api/src/gorgona_booking/db/migrations/0009_location_access.sql`.
- Проверки: `api/tests/integration/seed.py`, `api/tests/integration/test_business_profiles.py`, `api/tests/integration/test_management_browser.py`, новый `api/tests/integration/test_location_access.py`, новый `web/tests/location-access.spec.ts`.
- Интерфейс: `web/app/bookings/page.tsx`, `web/app/calendar/page.tsx`, `web/app/overview/page.tsx`, `web/app/staff/page.tsx`, `web/app/business/page.tsx`, `web/app/globals.css`, `web/components/location-filter.tsx`, `web/components/management-layout.tsx`, `web/lib/management-api.ts`, `web/lib/management-contracts.ts`, `web/package.json`.
- Документы: новый [ADR-0014](../adr/0014-location-scoped-workspace.md), этот реестр, [handoff](NEXT_AGENT_HANDOFF_2026-10-04.md), [master plan](GORGONA_MASTER_PLAN.md), `docs/DEVELOPMENT.md`, `CLOUD_CODE_HANDOFF.md`, исторические копии CHECKPOINT_2 и снимки проверенного интерфейса.

## Границы и продолжение

**Технически проверены отдельные пакеты, платформа целиком остается в разработке.** Один филиал на членство; черновики юридических лиц приняты отдельно на `d97924f`. Несколько филиальных грантов, группы, делегирование независимой диспетчерской, отраслевые роли и филиальный аудит еще не реализованы. Общий аудит не угадывает область по JSON и недоступен филиальному пользователю; запись аудита продолжается.

В исходном локальном пакете контейнерные gates не выполнялись; в GitHub CI `d97924f` обязательные контейнеры, PostgreSQL и браузеры PASS. Дополнительный внешний site gate остается skip и вне зависимости платформы. Реальные провайдеры, Azure/staging, промышленная миграция, нагрузочные цели/RPO/RTO, отраслевые пилоты и полные TMS/аренда/финансы/ресторанные циклы не проверены. AI не менялся и повторно не проверялся. Рабочие/производственные БД не менялись; миграции применялись только к одноразовым тестовым базам. В исходном пакете прав филиалов коммитов, push, публикации и развертывания не было; актуальные публикации новой ветки и приемка фиксируются отдельно.

Следующий пакет этапа 1 после принятых черновиков юридических лиц: структура и ограниченное делегирование с собственностью независимых компаний; затем draft→preview/validation/publication и единая занятость с безопасным переносом `booking_allocations`. Далее финансы, персонал и минимальные материальные операции по мастер-плану.

Использованы локальные Git, Python/FastAPI/PostgreSQL, TypeScript/Next, Ruff/mypy, ESLint/Prettier, Playwright/Chromium/Axe, официальный справочник PostgreSQL и установленный riqor:evidence-engineering с независимым обзором. Новых зависимостей приложения нет.

Тестовый кластер после приемки остановлен; `pg_ctl status` проверен отдельно. Его данные сохранены. Перед новым запуском сверить datadir и явно передать тестовый порт. Архив продолжения: `C:\Users\alexa\Documents\ChatGPT\Gorgona Booking\handoff\GORGONA_LOCATION_ACCESS_2026-10-04_CONTINUATION.zip`; это измененные файлы и patch к указанной базе Git, не полный checkout.
