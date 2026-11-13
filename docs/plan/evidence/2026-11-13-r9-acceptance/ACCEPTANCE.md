# Package R rental acceptance on gorgona-dev

**RENT-01 PASS in the development VM.** Class bookings reserve capacity, unit assignments use shared
occupancy to prevent overlap, and security, damage charges and refunds are separate records. R9
checks all three in one rental through the API and reads the resulting rows in PostgreSQL. The
independent package review remains open. Rental is registered as `implemented` and requires an owner
decision on readiness and enablement. The production launch scope covers all 39 industry directions.
[Package R plan](../../PACKAGE_RENT_PLAN_2026-11-03.md) · [R9 design](../../PACKAGE_R9_DESIGN_2026-11-13.md)
· [R9 checks](CHECKS.json) · [Shared resource occupancy ADR](../../../adr/0022-shared-resource-occupancy.md)
· [Rental catalogue ADR](../../../adr/0036-rental-classes-and-units.md)

## Requirements and evidence

| ID | Result | Evidence | Coverage limits |
|---|---|---|---|
| R-01 | PARTIAL against the plan wording | The catalogue reports `implemented` and enableable false. A write before readiness returns `MODULE_NOT_READY`. In R1 the module-off writes are refused, the branch and tenant boundaries hold, and SQL privileges and constraints protect the records. R9 turns the module off, gets `MODULE_DISABLED` on a refund, and confirms the counts are unchanged. The test fixture enables the module for synthetic cases. [R1](../../PACKAGE_R1_DESIGN_2026-11-03.md) | Authorized reads still work when the module is off. The plan's wording about every route is broader than the implemented write gate. |
| R-02 | PASS | R2 checks peak availability per class and branch. Two attempts for the last unit leave one booking after an observed PostgreSQL lock wait. R9 reserves two cars by class, refuses a third overlapping booking and reads zero unit holds before assignment. [R2](../../PACKAGE_R2_DESIGN_2026-11-03.md) | |
| R-03 | PASS | R3a verifies shared occupancy exclusion, concurrent assignment, replacement and release history. R3b verifies blocks and availability. R9 refuses an overlapping assignment and an extension into maintenance, both with `RENTAL_UNIT_BUSY`. [R3a](../../PACKAGE_R3A_DESIGN_2026-11-03.md) · [R3b](../../PACKAGE_R3B_DESIGN_2026-11-03.md) | An administrative move changes the branch and resource when there are no current or future holds. Transit occupancy and inspection-driven one-way return moves remain unimplemented. |
| R-04 | PASS | Rate cards and agreement versions are retained. R9 verifies a later rate card leaves the agreement frozen and an allowed extension writes version 2 using the original card. [R4a](../../PACKAGE_R4A_DESIGN_2026-11-04.md) · [R4b](../../PACKAGE_R4B_DESIGN_2026-11-06.md) · [R4c](../../PACKAGE_R4C_DESIGN_2026-11-06.md) | Extensions and extras are API-only. Signed-copy attachment remains outside the verified rental agreement flow. |
| R-05 | PASS | R5a verifies the separate security lifecycle, partial capture with a basis and one closing event. R5b links verified test-mode receipts. In R9 a basis-free capture gets 422, the settlement leaves security intact and the second release is refused. [R5a](../../PACKAGE_R5A_DESIGN_2026-11-07.md) · [R5b](../../PACKAGE_R5B_DESIGN_2026-11-07.md) | Provider evidence is sandbox-only. Provider hold creation and live card operations are outside the implementation. |
| R-06 | PASS | R6a verifies meter readings, optional fuel or charge level, notes and damage marks with image document versions. R6b derives usage. R9 reads a distance of 500 with 300 allowed and two started hours late. R8c covers handover and return in the browser. [R6a](../../PACKAGE_R6A_DESIGN_2026-11-07.md) · [R6b](../../PACKAGE_R6B_DESIGN_2026-11-07.md) · [R8c](../../PACKAGE_R8C_DESIGN_2026-11-11.md) | Mark photo attachments are API-only. Structured inspection checklists and inspection-driven branch moves remain unimplemented. |
| R-07 | PASS | Damage charges require `rental.approve` and new return marks. R7b verifies independent charge and refund records and the refund ceiling. R9 refuses the front desk (403) and an old mark, leaves the settlement intact and records the external refund. [R7b](../../PACKAGE_R7B_DESIGN_2026-11-08.md) | The front-desk case uses a role without rental rights. Both built-in roles with `rental.manage` also have `rental.approve`. |
| R-08 | PASS | R7a derives the FIN-03 receivable draft from frozen terms and usage. R7c derives reconciliation from documents, security and refunds. R9 verifies USD 150.00 rental + 50.00 excess + 6.00 late = 206.00, a separate 80.00 damage charge, 286.00 total charged and a 10.00 external refund. [R7a](../../PACKAGE_R7A_DESIGN_2026-11-07.md) · [R7c](../../PACKAGE_R7C_DESIGN_2026-11-08.md) | The rental line includes any frozen extras. Fuel pricing is unimplemented. FIN-03 issues, posts and receives payment for the drafts. |
| R-09 | PARTIAL | Staff record Paper or Email with the name and time. R9 verifies 422 for `platform` on acceptance, agreement change and period change. Desktop and mobile expose exactly Paper and Email. The read contract and database can represent `platform` for historical records and a future grant path. [R4b](../../PACKAGE_R4B_DESIGN_2026-11-06.md) · [R9 checks](CHECKS.json) | Customer responses through a rental grant remain unimplemented. |
| R-10 | PARTIAL keyboard coverage | Real desktop and mobile browsers exercise the management login and rental flows. axe reports zero violations on the checked screens, and mobile fits without horizontal scrolling. R8a submits the cancellation with Enter. [R8a](../../PACKAGE_R8A_DESIGN_2026-11-09.md) · [R8b](../../PACKAGE_R8B_DESIGN_2026-11-11.md) · [R8c](../../PACKAGE_R8C_DESIGN_2026-11-11.md) | A keyboard-only walkthrough of all rental screens remains unverified. |

## Slice evidence

| Slice | Code | VM full suite passed | GitHub Actions |
|---|---|---:|---|
| [R1](../2026-11-03-r1-rental-catalog/CHECKS.json) | `15a884d` | 2756 | [Success](https://github.com/alexeyalexandrov2026-tech/GORGONA-Booking-Platform_new/actions/runs/41590287564) |
| [R2](../2026-11-03-r2-rental-bookings/CHECKS.json) | `e34ac3f` | 2763 | [Success](https://github.com/alexeyalexandrov2026-tech/GORGONA-Booking-Platform_new/actions/runs/41606651336) |
| [R3a](../2026-11-03-r3a-rental-assignment/CHECKS.json) | `ab98936` | 2771 | [Success](https://github.com/alexeyalexandrov2026-tech/GORGONA-Booking-Platform_new/actions/runs/41627679283) |
| [R3b](../2026-11-03-r3b-rental-blocks/CHECKS.json) | `b5cff95` | 2777 | [Success](https://github.com/alexeyalexandrov2026-tech/GORGONA-Booking-Platform_new/actions/runs/41708625225) |
| [R4a](../2026-11-04-r4a-rental-rates/CHECKS.json) | `79d678f` | 2787 | [Success](https://github.com/alexeyalexandrov2026-tech/GORGONA-Booking-Platform_new/actions/runs/41900546592) |
| [R4b](../2026-11-06-r4b-rental-agreements/CHECKS.json) | `a098477` | 2793 | [Success](https://github.com/alexeyalexandrov2026-tech/GORGONA-Booking-Platform_new/actions/runs/42291512691) |
| [R4c](../2026-11-06-r4c-rental-extensions/CHECKS.json) | `c38efe8` | 2799 | [Success](https://github.com/alexeyalexandrov2026-tech/GORGONA-Booking-Platform_new/actions/runs/42394185544) |
| [R5a](../2026-11-07-r5a-rental-security/CHECKS.json) | `ffe05b8` | 2805 | [Failure](https://github.com/alexeyalexandrov2026-tech/GORGONA-Booking-Platform_new/actions/runs/42404010560). R6a later passed with R5a included. |
| [R5b](../2026-11-07-r5b-rental-provider-holds/CHECKS.json) | `e4efe63` | 2811 | [Failure](https://github.com/alexeyalexandrov2026-tech/GORGONA-Booking-Platform_new/actions/runs/42413235532). R6a later passed with R5b included. |
| [R6a](../2026-11-07-r6a-rental-inspections/CHECKS.json) | `78db1a8` | 2818 | [Success](https://github.com/alexeyalexandrov2026-tech/GORGONA-Booking-Platform_new/actions/runs/42426865948) |
| [R6b](../2026-11-07-r6b-rental-usage/CHECKS.json) | `010692f` | 2828 | [Success](https://github.com/alexeyalexandrov2026-tech/GORGONA-Booking-Platform_new/actions/runs/42438106172) |
| [R7a](../2026-11-07-r7a-rental-settlement/CHECKS.json) | `31cf73d` | 2834 | [Success](https://github.com/alexeyalexandrov2026-tech/GORGONA-Booking-Platform_new/actions/runs/42449693704) |
| [R7b](../2026-11-08-r7b-rental-damage-refunds/CHECKS.json) | `b174d1b` | 2839 | [Success](https://github.com/alexeyalexandrov2026-tech/GORGONA-Booking-Platform_new/actions/runs/42511820796) |
| [R7c](../2026-11-08-r7c-rental-reconciliation/CHECKS.json) | `6876fee` | 2842 | [Success](https://github.com/alexeyalexandrov2026-tech/GORGONA-Booking-Platform_new/actions/runs/42558093855) |
| [R8a](../2026-11-09-r8a-rental-screens/CHECKS.json) | `06b3c25` | 2843 | [Failure](https://github.com/alexeyalexandrov2026-tech/GORGONA-Booking-Platform_new/actions/runs/43058107935), [subsequent success](https://github.com/alexeyalexandrov2026-tech/GORGONA-Booking-Platform_new/actions/runs/43061387414) |
| [R8b](../2026-11-11-r8b-rental-agreement-screens/CHECKS.json) | `b3528b8` | 2844 | [Success](https://github.com/alexeyalexandrov2026-tech/GORGONA-Booking-Platform_new/actions/runs/43128481780) |
| [R8c](../2026-11-11-r8c-rental-settlement-screens/CHECKS.json) | `c45d3da` | 2845 | [Success](https://github.com/alexeyalexandrov2026-tech/GORGONA-Booking-Platform_new/actions/runs/43368792577) |
| [R9](CHECKS.json) | `2388cda` | 2846 | [Branch runs](https://github.com/alexeyalexandrov2026-tech/GORGONA-Booking-Platform_new/actions?query=branch%3Acodex%2Fpackage-r9-rental-acceptance) |

## R9 checks

- **Before the fix** — `red-1` recorded two expected failures in 28.50 s. The agreement endpoint accepted
  `platform`, and the desktop form offered Platform.
- **After the fix** — `dev-1` static checks and web build passed. `dev-2` passed 12 tests, including
  two Playwright cases inside the agreement browser test and the R9 PostgreSQL read-back.
- **Final VM gates** — `gates-1` static PASS, focused **1102 passed in 2655.30s (0:44:15)**, full **2846 passed, 4 skipped in 5764.45s (1:36:04)**.
  The four VM skips are three container tests and the external tenant-site test. Their names and reasons,
  all run exit codes, and the verified source hashes are recorded in CHECKS.json.
- **Dependency audit** — 0 runtime findings and 7 moderate development findings, also present in R8c.
  R9 adds no dependency or migration. The next migration is 0108.

The independent read-only review remains pending owner approval. Its scope is R1 through R9 and the
claims in this record, including the plan-to-implementation gaps.
