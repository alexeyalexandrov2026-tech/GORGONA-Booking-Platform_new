# L9a — published fee policy for late cancellations and no-shows: local validation

**PASS for this bounded local, synthetic slice (BEAUTY-01 gap L-06).** Branch `codex/package-l9a-fee-policy`,
parent `a3fd1d4` ([L9 design](../../PACKAGE_L9_DESIGN_2026-10-23.md), decisions 76-80), source commit `8a90567`.
[CHECKS.json](CHECKS.json) was written before the source commit and binds every source blob, command, exit code
and log digest. Owner's word 2026-10-23: close both gaps, same process; readiness and `main` untouched.

## What changed

- Migration **0072**: `gba.visit_fee_policies` (insert-only versions: free cancellation minutes, late and
  no-show fee as basis points or hundredths) and `gba.visit_no_shows` (once, a started confirmed visit without
  completion); database guards for the next version, the no-show and the completion of a no-show visit.
- Routes: `GET/POST /v1/salons/{id}/visit-fee-policy` (read: booking read; publish: settings rights, expected
  version), `POST/GET /v1/salons/{id}/bookings/{booking}/no-show` (booking write, branch scope).
- Billing: a cancelled visit (not by its own reschedule, later than the free window) is billed one line "Late
  cancellation fee"; a no-show visit one line "No-show fee"; the version in force when the visit was booked;
  percentage half up, fixed amount exact in 0-, 2- and 3-decimal currencies; typed fee lines on these visits are
  refused (`VISIT_FEE_FROM_POLICY`). A no-show visit cannot be completed, moved or cancelled.
- Screens: Settings "Cancellation and no-show fees" (current version, publish a new one); visit desk "Mark as
  no-show" with the fee of the booked version.

## Proof

`tests/integration/test_l9a_fee_policy.py` (5): versions insert-only, stale version refused, direct SQL refused,
another company sees none; the version in force at booking (33.35 % of 70.00 = 23.35, a later 10 % ignored; no
policy then, no fee); fixed 15.00 billed as 15.00 / 15 / 15.000 (USD, JPY, KWD), a rescheduled or early
cancellation not billable; a no-show once (same answer for any key), billed 35.00, completion `VISIT_NO_SHOW`,
cancel `VISIT_ALREADY_RECORDED`, not started `VISIT_NOT_STARTED`, completed `VISIT_ALREADY_COMPLETED`; typed
fees refused on cancelled and no-show visits, kept on an attended one. `test_l9a_upgrade.py`: 0071 -> 0072 keeps
every row. Browser (`visit-desk.spec.ts`, desktop and mobile, keyboard, axe): settings publish a newer version;
the desk records the no-show and shows 25.00, the fee of version 1 the visit was booked under.

## Failures kept

- red-1: 8 failed, 11 passed — the route did not exist (404), expected RED.
- dev-1: 6 failed — a fee rule serialized its empty key as null (fixed); the late-cancellation tests booked
  visits in 2031, beyond the one-year free window, so every cancellation counted as early (test design bug;
  visits now a few hours ahead).
- dev-4: browser — the web response registry did not know `/visit-fee-policy` and would have parsed
  `/no-show` as a booking; strict contracts added.
- Slip: the record script adaptation broke a string (SyntaxError) before any gate ran; fixed.
- gates-1: focused-1 1 failed, 478 passed — the billing browser wrapper checked an invoice for every seeded
  visit and the shared seeder now also books the missed visits; test bug of this slice, fixed.
- The record script expected 71 migrations; updated to 72 after the gates.
- Line endings: some edits were written with CRLF in the working copy; git stores LF (the record binds the
  normalized blobs).

## Gates (final, suffix 2)

Run folder `GorgonaBookingTests/package-l9a-20261023-a3fd1d4`: **static-2** PASS; **focused-2** PASS,
**479 passed**; **full-2** PASS, **2556 passed, 4 skipped** (62 minutes locally).

## Remaining

L9b: commission reversal after a refund (L-07). L9c: acceptance record update. Next migration **0073**.
