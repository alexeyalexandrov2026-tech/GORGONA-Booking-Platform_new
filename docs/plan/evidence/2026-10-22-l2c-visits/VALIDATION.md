# L2c — visits with several services: local validation

**PASS for this bounded local, synthetic slice.** Branch `codex/package-l2c-visits`, parent `d939488`
(L2 design decisions 11–15, [design](../../PACKAGE_L2_DESIGN_2026-10-22.md)), source commit `c32a1b0f37d4a2ecd52ca893973a97712fc1b9c1`.
[CHECKS.json](CHECKS.json) was written before the source commit and binds every source blob, command,
exit code and log digest. No network; no migration; readiness unchanged.

## What changed

| Area | Change |
|---|---|
| Visit | One booking holds an ordered list of services: `variant_id` and `add_on_ids` are the first, `extra_lines` (up to four) the rest; `bookings.variant_id` keeps the first |
| Quote | `build_visit_quote`: one line is exactly `build_quote`; for more, every component once, a requirement met by any line, a conflict with any line refuses, one currency, each service once, at most five services and 720 minutes; always version 2 (an unstaged line is one active stage with the specialist) |
| Paths | Staff booking, the hold API, guest availability and guest hold accept `extra_lines`; one artist must serve every service; an empty `extra_lines` keeps every earlier fingerprint and stored idempotency answer |

## Failures kept

- **red-1**: unit collection error (`build_visit_quote` missing) — expected.
- **red-2**: 4 failed (`extra_lines` refused) — expected; 1 setup error: two fixtures seeded the same
  customer setup (split into a guest and a staff fixture).
- A unit expectation put the add-on minutes on the finish stage; the L1 rule puts them on the last
  active stage. Test corrected, code unchanged.

## Gates (final, suffix 1)

Run folder `GorgonaBookingTests/package-l2c-20261022-d939488`: **static-1** PASS; **focused-1** PASS,
**234 passed**; **full-1** PASS, **2479 passed, 4 skipped**.

## Remaining

No web screen chooses several services yet (L7); different specialists per service are a later
decision. Migrations 0001–0067 unchanged; the next is **0068**.
