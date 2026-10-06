# GORGONA F — shared resource occupancy, 2026-10-05

Branch `claude/package-f-occupancy` (from the F plan `b4c8563`, on top of accepted
E3 `b8834fb`). Separate worktree `C:\Users\alexa\Documents\ChatGPT\gorgona-e2-documents`;
owner checkout, other worktrees and cluster 51454 untouched; local tests on the
disposable PostgreSQL 18.6 cluster 127.0.0.1:51455 only. Owner decisions of
2026-10-05 and the design are in [ADR-0022](../../../adr/0022-shared-resource-occupancy.md)
and the [package F plan](../../PACKAGE_F_PLAN_2026-10-05.md).

## Step 1 — shared occupancy and the exact booking mirror

**Gate: implemented; CORE-04 not yet tested (needs step 2).** Code
`f74b5deb166d67d9273d71f45e42525134742855` passed its exact-SHA push CI
([run 37408551883](https://github.com/alexeyalexandrov2026-tech/GORGONA-Booking-Platform_new/actions/runs/37408551883),
job `api` 112091535587: success, 17 executed steps, with mandatory PostgreSQL,
browser and container gates). No module readiness changes; registry version 1.

Boundary: migration 0018 — `gba.resource_allocations` (FORCE RLS, branch scope
through the resource, exclusion `resource_allocations_no_overlap` for
held/confirmed, guard trigger: no delete, immutable identity and interval,
forward-only state, booking rows must match their booking), mirror trigger on
`booking_allocations` (insert and status cascade), `gba.booking_occupancy_mismatches()`
and `gba.backfill_booking_occupancy()`; operator command
`gba-db backfill-occupancy <company id or slug>`; booking maps both exclusion
constraints to the same `SLOT_CONFLICT`; schema guard checks the policy, the
constraint definition, the state function and the trigger bodies and columns.

| Check | Exact observed outcome |
|---|---|
| Red before the migration | Expected FAIL: 3 failed, 1 error (no `resource_allocations`) |
| In-migration backfill attempt | FAIL: `test_migrations_never_disable_or_bypass_rls` refused `no force row level security` — redesigned as the per-company operator command; the rule was not relaxed |
| Independent review | 2 medium + 3 low: backfill race and non-healing rerun (fixed: SHARE lock, forward healing), hidden mirror row in a branch session (disproved by test: the cascade runs the mirror in the foreign-key context), slot conflict as 500 (fixed), unknown company reported consistent (fixed), guard gaps (fixed: `tgattr`, constraint definition, state function) |
| Slot conflict on the shared constraint, red | Expected FAIL: unhandled `ExclusionViolation` on `resource_allocations_no_overlap` with the previous repository |
| Occupancy tests after fixes | PASS: 8 passed, 5.62 s |
| Python static | PASS: Ruff check/format, strict mypy 183 files |
| Full local suite | PASS: **775 passed / 4 skipped / 241.79 s**, exit 0; mandatory PostgreSQL 18.6 and browsers; skips: 3 Docker container gates (CI) and the external tenant-site gate |
| Exact code push CI `f74b5de` | PASS: run 37408551883, job 112091535587 |

Limits: pre-0018 booking allocations of a company enter the shared table only
after `backfill-occupancy` for that company (no automatic per-company marker yet;
the reservation path checks un-copied active booking allocations itself);
`booking_occupancy_mismatches()` in a branch session compares only visible rows;
`units`/capacity and `resource_blocks` stay out (owner decisions). Production
migration, Azure, load and pilots: NOT TESTED. No merge or deployment.

## Step 2 — staff resource reservations and CORE-04

**Gate: CORE-04 technically verified locally and in CI.** Code
`bf3645d987f06f9993d6e6b4087f54168bc0fc26` passed its exact-SHA push CI
([run 37411493038](https://github.com/alexeyalexandrov2026-tech/GORGONA-Booking-Platform_new/actions/runs/37411493038),
job `api` 112100698263: success, 17 executed steps, mandatory PostgreSQL, browser
and container gates). Module `booking_resources` keeps its readiness; its limits
now name reservations sharing one occupancy with bookings. Registry version 1.

Boundary: migration 0019 — `gba.resource_reservations` (FORCE RLS, branch scope,
insert-only except one cancellation, `resource_count` allocations made in its own
transaction and checked before commit, booking-module gate), source
`reservation` in `resource_allocations` (confirmed, released only by the
cancellation, which fails closed when a resource left the caller's branch; the
guard also refuses overlaps with booking allocations not copied yet). API
`/v1/businesses/{id}/resource-reservations` (staff permissions, branch scope, no
delegates; 409 `SLOT_CONFLICT`); customer availability skips reserved intervals;
web page `/reservations/`.

| Check | Exact observed outcome |
|---|---|
| Red without migration 0019 | Expected FAIL: 6 failed |
| Availability red (old query) | Expected FAIL: a reserved slot was still offered to customers |
| CORE-04, services | PASS: 5 bookings + 5 reservations of two resources race → exactly one winner, 9 typed conflicts; a two-resource reservation meeting a booking leaves no reservation and no allocation |
| CORE-04, raw SQL without application locks | PASS: 5 rounds of booking vs reservation on two connections → one commit and one exclusion conflict (or deadlock abort) each round; active intervals = rounds |
| First full suite | FAIL: 2 failed — the changed booking `stops` text broke two expectations; text restored compatibly, both pass |
| Independent review | No high; 3 medium (release hidden by branch security, concurrent cancels → 500, CORE-04 not shown by the constraint) + lows — all fixed with tests |
| Browser harness | PASS: desktop + mobile, axe clean, SQL checks |
| Web | PASS: typecheck, ESLint, Prettier, 63 unit tests, production export |
| Python static | PASS: Ruff check/format, strict mypy 188 files |
| Final full local suite | PASS: **787 passed / 4 skipped / 348.42 s**, exit 0; mandatory PostgreSQL 18.6 and browsers; the usual 4 skips |
| Exact code push CI `bf3645d` | PASS: run 37411493038, job 112100698263 |

Limits: no capacity above one or multi-resource booking; `resource_blocks` stay
separate; reservations in the past are accepted (internal record); author
columns can be forged by direct runtime SQL (as E1–E3); booking summaries still
read `booking_allocations` (owner decision 4). Production migration (including
`backfill-occupancy` per company), Azure, load and pilots: NOT TESTED. No merge
or deployment.
