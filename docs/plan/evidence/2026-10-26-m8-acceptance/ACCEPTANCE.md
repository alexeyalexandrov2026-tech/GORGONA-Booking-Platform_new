# Transport (TMS-01..03) — package M acceptance record (local, synthetic)

**Verdict: technically accepted locally, without the independent review.** The owner chose on 2026-10-26:
"Start M8, but prepare the acceptance without the extra reviewer agent for now." The one independent review
that package M's plan foresees (M8) has **not** been done; it needs the owner's consent for an extra agent and
stays open below. This record **does not** change the readiness registry, **does not** make the transport
module enableable and **does not** touch `main`; each waits for the owner's separate word. No deployment, no
production migration, no live provider (ELD, telematics, payment) action.

Requirements: [PACKAGE_M_PLAN_2026-10-23.md](../../PACKAGE_M_PLAN_2026-10-23.md) TMS-01..03 and decisions 1-10;
decisions ADR-0028..0033. Package M is a build order of stage 3, not a separate launch: the owner's goal stays
production for all 39 directions at once.

## Slices and evidence

| Slice | Code | Local full suite | CI |
|---|---|---|---|
| M1 orders, loads, trips, stops, legs (0074) | `32bb8a4` | 2571 passed | SUCCESS 40065762379 |
| M2 drivers, vehicles, assignments with periods (0075) | `31bb854` | 2580 passed | SUCCESS 40072696483 |
| M3 stop events, partial delivery (0076) | `f6ac5f1` | 2587 passed | SUCCESS 40081070256 |
| M4 dispatcher scope on carrier grants (0077) | `4b6cd75` | 2593 passed | SUCCESS 40116278936 |
| M5 hours-of-service and telematics clearance (0078) | `1180d41` | 2600 passed | SUCCESS 40152895317 |
| M6a dispatch board and trip page | `76519b8` | 2603 passed (full-1 failed twice, recorded) | SUCCESS 40177073619 |
| M6b planning forms, fleet, carrier grants | `ba9cb64` | 2605 passed | SUCCESS 40227240451 |
| M7a money through FIN-03 (0079) | `b2998d5` | 2612 passed (full-1 lost a browser session, recorded) | SUCCESS 40245557506 |
| Defects D-01 (live server crash) and D-02 (silent refused offer) | `099bc84` | 2614 passed | SUCCESS 40261326556 |
| M7b money on the screens | `f44db22` | 2615 passed | SUCCESS 40272483262 |
| M8 TMS-01 end to end | `6d5c86c` | 2616 passed, 4 skipped | see the checkpoint |

Every local run: one executor, one disposable PostgreSQL 18 cluster, 4 skipped tests that need outside services
(named in each CHECKS.json).

## TMS-01..03

| id | Result | Proof | Limit or gap |
|---|---|---|---|
| TMS-01 | PASS | M8 `test_tms_01_an_interstate_trip_keeps_its_history`: two orders' loads on one trip with three stops in three time zones, the truck replaced at noon after loading (period ended, replacement linked), a partial delivery of 7 with 2 refused and 1 damaged, the rest delivered, every event in the log, the started trip's plan refused; M1 several loads per trip and a load split across trips, racing plans; M2 replacement keeps history, busy truck refused, racing assignments leave one; M3 partial delivery, quantities never above the plan, racing deliveries; M6a/M6b real browser desktop and mobile | Transfers between legs of different trips are not a separate operation (a load is split across trips when planned) |
| TMS-02 | PASS | M4: transport rights grantable per action, fleet registration never; a dispatcher acts only within the granted actions and only for the granting carrier; revocation, removal of the delegate and expiry each block the next command while earlier facts stay; a location-limited grant keeps other branches out; M6b browser: the dispatcher sees only the granted forms and no fleet, planning or money; D-02 a refused offer is shown | Planning for a delegate is not offered on the screen (the API allows it with `transport.plan`) |
| TMS-03 | PASS | M5: stale or unknown hours-of-service data (no profile, no records, stale, a gap in the cycle, unassigned) and stale or missing telematics never clear; exceeded driving, window and cycle limits give "not cleared" with their reason; a repeated fact changes nothing; M3: a repeated event changes nothing, including a delivery (source and source event id); M6a browser: a lost answer retried records the event once | One rule profile per business; exemptions, split sleeper berth and real ELD/telematics connectors are later |

## Package decisions kept

- Separate entities (order, load, trip, stop, leg) — M1; shared occupancy of drivers and vehicles with periods
  (ADR-0022, ADR-0029) — M2; idempotent facts with a source (ADR-0030, ADR-0032) — M3, M5.
- Money through FIN-03 with one obligation per recipient and component (ADR-0033, master plan §7.5) — M7a: the
  agreed rate frozen by the order's one invoice, components registered once and accrued once, FIN-03 keeping
  payments within the open balance; M7b on the screens.
- Every transport table: tenant isolation, branch scope where it has a branch, the transport module gate;
  every write route refuses without the module; upgrade tests 0073 → 0079 keep every row.

## Self-check (not an independent review)

The open items and limits I know of, kept honest because no independent reviewer has looked yet:

1. **The independent review is not done** (owner, 2026-10-26). L8's review found 15 issues in package L; a
   review of package M may find comparable ones.
2. D-01: the M6a full-1 failure of the workforce browser test left no traceback; its cause is likely the
   machine's socket shortage seen in dev-5 but not proven. The harness now names such a crash.
3. Fleet details are registered once; corrections need their own decision.
4. Advances, deductions, fuel surcharge formulas, factoring and quick pay are not built (master plan §7.5 lists
   them); extras are named invoice lines today.
5. IFTA, truck routing and load boards (master plan §7.6) are not part of package M.
6. The transport module stays `implemented` and not enableable; the tests switch it on only through a fixture.

## Gates of this record

Run folder `GorgonaBookingTests/package-m8-20261026-3c9b892`: focused **735 passed**; full **2616 passed, 4 skipped**.

## Recommendation (owner decides)

1. Consent to the one independent review of package M (one extra agent), then fix what it finds.
2. After that, the owner's word on the readiness of the transport module and on `main`.
