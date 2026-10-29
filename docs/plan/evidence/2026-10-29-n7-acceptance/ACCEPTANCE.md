# Brokerage and 3PL (N-01..N-09, TMS-01..03 for brokered loads) — package N acceptance record (local, synthetic)

**Verdict: technically accepted locally, without the independent review.** The plan foresees one independent
review in N7 "only with the owner's consent"; that consent has not been asked for or given in this run, so the
review has **not** been done and stays open below. This record **does not** change the readiness registry,
**does not** make the transport module enableable and **does not** touch `main`; each waits for the owner's
separate word. No deployment, no production migration, no live provider (FMCSA, insurance, load board, payment)
action. Owner 2026-10-29: "continue" under full delegation («Делай как считаешь нужным я доверяю тебе»).

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
| N7 a brokered two-leg load end to end, N6 authority save fix | `08f519c` | 2654 passed | see the checkpoint |

Every local run: one executor, one disposable PostgreSQL 18 cluster, 4 skipped tests that need outside services
(named in each CHECKS.json).

## N-01..N-09

| id | Result | Proof | Limit or gap |
|---|---|---|---|
| N-01 | PASS | N1 authority versions and eligibility reasons; N2-01 no authority and a withdrawn authority refuse the offer; N7 no authority, then one | Facts as stated by the business; no live FMCSA lookup (plan) |
| N-02 | PASS | N1 profile versions and every reason (no profile, unknown authority, expired or unknown insurance, unsatisfactory, stale check); N2-01 insurance lapsing before acceptance refuses it; N6 browser refusal in words; N7 no profile | Same: no live insurance or safety lookup |
| N-03 | PASS | N2 insert-only offers and answers; N2-04 at most one accepted tender per leg; N2 racing acceptances on overlapping legs leave one with an observed advisory-lock wait; N7 a covered leg refuses a second acceptance | "Expired" is derived from the offer's expiry when the tender is read or answered, never stored by a job |
| N-04 | PASS | N3 version 1 on acceptance, a change in force only once agreed, stale or closed refused, old versions kept; N6 browser and N7 version 2 agreed with version 1 kept | A signed copy is an optional document reference |
| N-05 | PASS | N4 the broker links a carrier to its platform company in versions; the linked company answers its tender and a rate confirmation version through its grant; N2/N3 an external answer is recorded with its source and time | The carrier's own answers are API-only (no carrier screen yet) |
| N-06 | PASS | N4 a linked carrier records stop events only for its accepted legs; N7 the broker closes the leg and a repeated event changes nothing; M3 idempotent events | — |
| N-07 | PASS | N5 one FIN-03 payable per accepted tender for the version in force, fixed or per mile, accrued once on closed legs; margin derived (own tenders subtracted, shared listed); N7 two carriers, 1500.00 − 900.00 − 450.00 = 150.00, no margin column in the schema | Quick pay and factoring are later (plan) |
| N-08 | PASS | N1/N2/N3/N5 rights tests: only owners and managers with `transport.broker`; a dispatcher and other companies refused; module off refused; direct SQL updates and deletes refused; N6 delegate sees no brokerage | A branch-limited member is covered by the page rule and the server refusal, not by a browser run |
| N-09 | PASS | N6 real browser desktop and mobile through OIDC/PKCE, axe clean, no horizontal scroll, refusal in words; full suite green in every slice | Keyboard-only use was not run as its own browser test in N6 |

## TMS-01..03 for brokered loads

| id | Result | Proof |
|---|---|---|
| TMS-01 | PASS | A brokered leg keeps the trip's history: tenders and answers are insert-only, rate confirmation versions stay, stop events of tendered legs are kept (N2, N3, N4, N7) |
| TMS-02 | PASS | A carrier on the platform acts only through its grant and only on its accepted legs (N4); `transport.broker` is never part of a dispatcher's default rights (N1) |
| TMS-03 | PASS | Unknown is never "fine": missing or unknown authority or insurance refuses the tender (N1, N2); repeated answers and events change nothing (N2, N4, N7) |

## Self-check (not an independent review)

1. **The independent review is not done.** Package M's review found nine issues (R-01..R-09); a review of
   package N may find comparable ones.
2. **N7 found an N6 defect.** In gates-1 the N6 browser test failed on mobile: "Save authority" was enabled
   before the current authority was read, so a fast save sent revision 0 and the server rightly refused it as
   changed meanwhile. The button now stays disabled until the authority is read (N7 code commit); the race is
   timing-dependent and is not reproduced by its own test.
3. Kept slips of the slices are in each record (for example N5 the accrual kind, N6 the unwired route map and a
   missing table class).
4. No live connectors (FMCSA, insurance, DAT load board); facts are recorded with their source.
5. The carrier's own screen is not built; a carrier on the platform answers through the API.
6. The transport module stays `implemented` and not enableable; the tests switch it on only through a fixture.

## Gates of this record

Run folder `GorgonaBookingTests/package-n7-20261029-e8f03d0`: **static-2** PASS; **focused-2** PASS, **833 passed**; **full-2** PASS, **2654 passed, 4 skipped** (1:07:44 locally).

## Recommendation (owner decides)

1. Consent to the one independent review of package N (one extra agent), then fix what it finds.
2. After that, the owner's word on the readiness of the transport module and on `main`.
