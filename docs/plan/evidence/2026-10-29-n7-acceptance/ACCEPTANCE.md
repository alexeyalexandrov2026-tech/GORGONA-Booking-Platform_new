# Brokerage and 3PL (N-01..N-09, TMS-01..03 for brokered loads) — package N acceptance record (local, synthetic)

**Verdict: technically accepted locally; the independent review is done and its findings are fixed (N8).**
Owner 2026-10-30: "Yes, run review" — one read-only agent reviewed package N at HEAD `4861b85` and found
RN-01..RN-09 (2 high, 5 medium, 2 low) and overstated claims in this record; owner "Start N8"; N8 fixes every
finding with a test that failed first ([N8 design](../../PACKAGE_N8_DESIGN_2026-10-30.md),
[N8 CHECKS.json](../2026-10-30-n8-review-fixes/CHECKS.json)). This record **does not** change the readiness
registry, **does not** make the transport module enableable and **does not** touch `main`; each waits for the
owner's separate word. No deployment, no production migration, no live provider (FMCSA, insurance, load board,
payment) action. Full delegation: «Делай как считаешь нужным я доверяю тебе».

Requirements: [PACKAGE_N_PLAN_2026-10-26.md](../../PACKAGE_N_PLAN_2026-10-26.md) N-01..N-09 and decisions 1-9;
ADR-0034 (broker authority and carrier profiles); [N7 design](../../PACKAGE_N7_DESIGN_2026-10-29.md).

## Slices and evidence

| Slice | Code | Local full suite | CI |
|---|---|---|---|
| N1 broker authority and carrier profiles (0080) | `a3d85d3` | 2621 passed | SUCCESS 40384347338 |
| Package M review fixes R-01..R-09 (0081) | `44b8505` | see its record | — |
| N2 tenders, one accepted tender per leg, races (0082) | `80183b5` | 2635 passed | SUCCESS 40465260205 |
| N3 rate confirmation versions (0083) | `526189e` | 2641 passed | SUCCESS 40597178642 |
| N4 carrier companies answer through grants, tracking (0084) | `cd301f1` | 2647 passed | SUCCESS 40742570688 |
| N5 carrier pay and margin (0085) | `5dd4700` | 2652 passed | SUCCESS 40792662378 |
| N6 brokerage on the screens | `33fc82e` | 2653 passed | SUCCESS 40809549398 |
| N7 a brokered two-leg load end to end, N6 authority save fix | `08f519c` | 2654 passed | SUCCESS 40926758583 |
| N8 fixes of the independent review RN-01..RN-09 (0086) | `b6cd7ef` | 2665 passed | see the N8 checkpoint |

Every local run: one executor, one disposable PostgreSQL 18 cluster, 4 skipped tests that need outside services
(named in each CHECKS.json).

## Independent review (done 2026-10-30) and its fixes

| id | Severity | Finding | N8 fix (test failed first) |
|---|---|---|---|
| RN-01 | high | The tender accrual's FIN-03 draft stayed editable | A draft linked from a tender accrual is frozen: 409 `FINANCIAL_DOCUMENT_LINKED` |
| RN-02 | high | A re-plan moved legs and stops under an accepted tender | `save_trip` refuses 409 `TRANSPORT_TRIP_TENDERED` under an open offer or accepted tender (lock `gba:trip-tender` first); 0086 triggers refuse direct SQL |
| RN-03 | medium | Carrier A's departure at a shared stop closed carrier B's leg | A carrier records a stop-level event only at a stop serving its own legs alone: 403 `TRANSPORT_EVENT_OUT_OF_SCOPE` |
| RN-04 | medium | Withdrawal or a new rate version after the accrual (pay twice) | Withdrawal, a new version or its answer after accrual: 409 `TRANSPORT_ALREADY_ACCRUED`; `accrue` takes the lock and re-reads; 0086 backs it |
| RN-05 | medium | A carrier set its own answer time | A carrier's answer is recorded at server time; `occurred_at` from a carrier is 422; the screen takes the time at the click |
| RN-06 | medium | Unlinking a carrier widened its rights | A company ever linked as a carrier keeps the restriction: 403 |
| RN-07 | medium | A linked carrier read the broker's whole book | A carrier lists only its own trips; others 404; orders, drivers, vehicles 403 |
| RN-08 | low | The margin added carrier pay in different currencies | `carrier_cost` and `margin` null, `currencies_differ` true; the screen says so in words |
| RN-09 | low | Legs already run by the own fleet could be tendered | A tender on a trip that is not `planned`: 409 `TRANSPORT_LEG_STARTED` |

The review also found claims in this record stated more strongly than the tests proved; they are corrected
below (N7 brokered flow, N-09, self-check point 2).

## N-01..N-09

| id | Result | Proof | Limit or gap |
|---|---|---|---|
| N-01 | PASS | N1 authority versions and eligibility reasons; N2-01 no authority and a withdrawn authority refuse the offer; N7 no authority, then one | Facts as stated by the business; no live FMCSA lookup (plan) |
| N-02 | PASS | N1 profile versions and every reason (no profile, unknown authority, expired or unknown insurance, unsatisfactory, stale check); N2-01 insurance lapsing before acceptance refuses it; N6 browser refusal in words; N7 no profile | Same: no live insurance or safety lookup |
| N-03 | PASS | N2 insert-only offers and answers; N2-04 at most one accepted tender per leg; N2 racing acceptances on overlapping legs leave one with an observed advisory-lock wait; N7 a covered leg refuses a second acceptance; N8 RN-02 (no re-plan under a tender), RN-05 (answer at server time), RN-09 (no tender on a started trip) | "Expired" is derived from the offer's expiry when the tender is read or answered, never stored by a job |
| N-04 | PASS | N3 version 1 on acceptance, a change in force only once agreed, stale or closed refused, old versions kept; N6 browser and N7 version 2 agreed with version 1 kept; N8 RN-04 no version after accrual or of a withdrawn tender | A signed copy is an optional document reference |
| N-05 | PASS | N4 the broker links a carrier to its platform company in versions; the linked company answers its tender and a rate confirmation version through its grant; N2/N3 an external answer is recorded with its source and time | The carrier's own answers are API-only (no carrier screen yet) |
| N-06 | PASS | N4 a linked carrier records stop events only for its accepted legs; N7 each carrier company records its own leg's events; a repeated event changes nothing; M3 idempotent events; N8 RN-03 no event at a shared stop | Within its own trip a carrier sees the stops of the other legs |
| N-07 | PASS | N5 one FIN-03 payable per accepted tender for the version in force, fixed or per mile, accrued once on closed legs; margin derived; N7 two carriers, 1500.00 − 900.00 − 450.00 = 150.00, no margin column; N8 RN-01 accrual draft frozen, RN-04 no withdrawal after accrual, RN-08 no sum across currencies | Quick pay and factoring are later (plan) |
| N-08 | PASS | N1/N2/N3/N5 rights tests: only owners and managers with `transport.broker`; a dispatcher and other companies refused; module off refused; direct SQL updates and deletes refused; N6 delegate sees no brokerage; N8 RN-06 unlinked carrier keeps its restriction, RN-07 a carrier reads only its own trips | A branch-limited member is covered by the page rule and the server refusal, not by a browser run |
| N-09 | PARTIAL | N6 real browser desktop and mobile through OIDC/PKCE, axe clean, no horizontal scroll, refusal in words; N8 browser check of the held authority read; full suite green in every slice | Keyboard-only use has not been run as its own browser test |

## TMS-01..03 for brokered loads

| id | Result | Proof |
|---|---|---|
| TMS-01 | PASS | A brokered leg keeps the trip's history: tenders and answers are insert-only, rate confirmation versions stay, stop events of tendered legs are kept (N2, N3, N4, N7); legs and stops of a tendered trip cannot be re-planned (N8 RN-02, 0086) |
| TMS-02 | PASS | A carrier on the platform acts only through its grant and only on its accepted legs (N4); it reads only its own trips and cannot close a shared stop (N8 RN-03, RN-07); an unlinked carrier keeps its restriction (N8 RN-06); `transport.broker` is never part of a dispatcher's default rights (N1) |
| TMS-03 | PASS | Unknown is never "fine": missing or unknown authority or insurance refuses the tender (N1, N2); repeated answers and events change nothing (N2, N4, N7) |

N7 is a true brokered flow since N8: the tenders come before any stop event, and carrier A records its own leg's
events on the platform (before N8 the test ran the legs first, which RN-09 now refuses).

## Self-check

1. **The independent review is done** (2026-10-30, one agent, HEAD `4861b85`); RN-01..RN-09 are fixed in N8.
2. **N7 found an N6 defect.** In gates-1 the N6 browser test failed on mobile: "Save authority" was enabled
   before the current authority was read, so a fast save sent revision 0 and the server rightly refused it as
   changed meanwhile. The button now stays disabled until the authority is read (N7 code commit). Since N8 a
   browser check holds the authority read back and sees "Save authority" disabled.
3. Kept slips of the slices are in each record (for example N5 the accrual kind, N6 the unwired route map and a
   missing table class; N8 red runs, a stale web build, a vanished Playwright install, a crashed runner).
4. No live connectors (FMCSA, insurance, DAT load board); facts are recorded with their source.
5. The carrier's own screen is not built; a carrier on the platform answers through the API.
6. The transport module stays `implemented` and not enableable; the tests switch it on only through a fixture.
7. Limits: once a trip is under way its remaining legs are not tendered (no relay); within its own trip a carrier
   sees the stops of the other legs.
8. An existing test, `test_i4_browser` (package I workforce screens), failed once in N8 gates-4 with
   "read ECONNRESET" from the loopback fixture identity provider and passed alone and in gates-5; it failed
   before in J3 and M6a too. Cause not established; kept open.

## Gates of these records

- N7: run folder `GorgonaBookingTests/package-n7-20261029-e8f03d0`: **static-2** PASS; **focused-2** PASS, **833 passed**; **full-2** PASS, **2654 passed, 4 skipped**.
- N8: run folder `GorgonaBookingTests/package-n8-20261030-c59e116`: **static-5** PASS; **focused-5** PASS, **844 passed**; **full-5** PASS, **2665 passed, 4 skipped** (1:03:18 locally). Earlier N8 gates and why they failed are in its CHECKS.json.

## Recommendation (owner decides)

1. The owner's word on the readiness of the transport module (enabling it) and on `main`.
2. Later: a keyboard-only browser test (N-09) and a carrier screen.
