# BEAUTY-01 — package L acceptance record (local, synthetic)

**Verdict: technically accepted locally; the two gaps named on 2026-10-23 (L-06 policy, L-07 reversal) are
closed by L9 on the owner's word (L9c, below).** Package L is a
build order of stage 3, not a separate launch: the owner's goal stays production for all 39 directions at once.
This record **does not** change the readiness registry and **does not** fast-forward `main`; both wait for the
owner's separate word (L8 decision 75). No deployment, no production migration, no live provider action.

Requirements: [PACKAGE_L_PLAN_2026-10-22.md](../../PACKAGE_L_PLAN_2026-10-22.md) L-01..L-12. Review: one
independent review with the owner's consent, 15 findings, all fixed
([REVIEW.md](../2026-10-23-l8-review/REVIEW.md)). Design of the closing slices:
[PACKAGE_L8_DESIGN_2026-10-23.md](../../PACKAGE_L8_DESIGN_2026-10-23.md).

## Slices and evidence

| Slice | Code | Local full suite | CI |
|---|---|---|---|
| L1 stages and equipment kind (0066) | `7ce60ef` | 2439 passed | SUCCESS 39758206502 |
| L2a stage occupancy (0067) | `edd0849` | 2459 passed | SUCCESS 39765610640 |
| L2b guests book staged services | `ca44785` | 2464 passed | SUCCESS 39777287553 |
| L2c visits of several services | `c32a1b0` | 2479 passed | SUCCESS 39783826823 |
| L3 completion and consumption (0068) | `4ed11af` | 2487 passed | SUCCESS 39805277086 (first run cancelled at the 45-minute job limit; limit raised in `ef83b91`) |
| L4 visit invoices (0069) | `0738b4a` | 2494 passed | SUCCESS 39812765674 |
| L5 commissions (0070) | `7ff9249` | 2504 passed | SUCCESS 39819887470 |
| L6 prepaid (0071) | `affdaf3` | 2510 passed | SUCCESS 39828302644 |
| L7a catalog screens | `13919b3` | 2512 passed | SUCCESS 39838977982 |
| L7b1 visit desk | `d1c12ca` | 2514 passed | SUCCESS 39855981830 |
| L7b2a billing desk | `56ab1ee`, fix `d2ac158` | 2517 passed | FAILED 39873748480 (UTC "today" in tests), then SUCCESS 39879172808 |
| L7b2b prepaid screens | `3d2658a` | 2520 passed | SUCCESS 39886335939 |
| L7c customer site | `1b00d01` | 2521 passed | SUCCESS 39901727848 |
| L8a review fixes R1-R7 | `e3d45de` | 2535 passed | FAILED 39971712190 (two untouched browser specs), fixed in `c9434b7` |
| L8b1 review fixes R8-R15 | `ee7fc1b`, spec fix `c9434b7` | 2543 passed | SUCCESS 39981532055 |
| L8b2 races, modules, room | `1e4368a` | 2548 passed | see the checkpoint |
| L8c L-09 proofs | `558b580` | 2550 passed | SUCCESS 39999584445 |
| L9a fee policy and no-shows (0072) | `8a90567` | 2556 passed | SUCCESS 40023359035 |
| L9b commission reversal (0073) | `00aadee` | see [VALIDATION](../2026-10-23-l9b-commission-reversal/VALIDATION.md) | see the checkpoint |

Every local run: one executor, one disposable PostgreSQL 18 cluster, 4 skipped tests that need outside
services (named in each CHECKS.json).

## L-01..L-12

| id | Result | Proof | Limit or gap |
|---|---|---|---|
| L-01 | PASS | L1 quote v2 with stages, v1 unchanged; L2a/L2c byte-identical one-line request and fingerprint; upgrade tests 0066-0071 keep every row | — |
| L-02 | PASS | L2c `test_l2c_visits`, `test_visit_quote`: duplicate, requirement, conflict, same variant twice, currency, 720 minutes; L7c browser refusal without retry | — |
| L-03 | PASS | L2a stages all or none, specialist free during processing, two racing visits leave one after an observed wait; L8b2 consumption, accrual and redemption races each leave one write after observed `pg_locks` waits | — |
| L-04 | PASS | L2a chair and equipment; L8b2 room stage against staff reservations (`SLOT_CONFLICT`) | — |
| L-05 | PASS | L3 once at moving-average cost, repeat writes nothing, planned and actual kept; L8b1 inventory needed even with nothing to write off, place of the visit's branch; L8b2 race | — |
| L-06 | PASS (L9a) | L4 invoice equals the quote lines (L8a: exact currency scale, no zero line), a deposit settles it; L9a: a versioned published fee policy, the version in force when the visit was booked; a late cancellation and a recorded no-show are billed their computed fee (percentage half up, fixed exact, 0/2/3 decimals); typed fees refused there; settings form and desk step in the browser | The cancellation time is the booking's status event; the customer site shows the business's own policy text |
| L-07 | PASS (L9b) | L5 owed only when fully paid, once, with lineage; L8a only for a confirmed visit; tips stay a liability, never revenue; L9b: each refund reverses the commission's share of its service, cumulatively, once, as a FIN-03 credit note of the accrual with lineage; races leave one; a prepaid redemption settles the visit (decision 85 fixed a defect: such visits earned no commission) | A finance user starts the reversal from the desk; the server computes every amount. A refund voided after its reversal is not re-reversed automatically |
| L-08 | PASS | L6 liability until paid, settles the visit line by credit note, used once; L8a unit by matching line and whole worth; L8b1 currency; L8b2 race | — |
| L-09 | PASS | L3 and L4 direct SQL refusals and company scope; L8c the same for commission plans, rules, visit commissions, prepaid balances and redemptions (use guard included); finance rights per route | — |
| L-10 | PASS | L8b1 workforce and inventory refusals on writes; L8b2 billing, sale and redemption refused without invoices; the desk hides each step without its module (browser) | The desk reads the configuration once per opening; a module switched off meanwhile is refused by the server |
| L-11 | PASS | L7a-L7c and L8b2 real browser, desktop and mobile, keyboard, axe; prepaid list pagination | Lists not changed by package L were not re-checked for pagination |
| L-12 | PASS | Full suite green on every slice; CI green except the named failures above, each fixed; one independent review, all 15 findings fixed; BOOKING, FIN-01-03, WORK-01 and STOCK-01 tests are part of every full run | — |

## Recommendation (owner decides)

1. Both gaps are closed (owner's word 2026-10-23: «Доделай оба пробела BEAUTY-01 … Готовность и main пока не
   трогай.»). Marking BEAUTY-01 technically accepted in the readiness registry is the owner's decision.
2. Merging package L into `main` needs the owner's word; the branches are stacked (L1 → L9b) and each pushed
   for CI only, without a PR.
3. Production stays out of scope: no deployment, no production migration, no pilot approval.
