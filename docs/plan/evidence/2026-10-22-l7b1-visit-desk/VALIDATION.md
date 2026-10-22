# L7b1 — visit desk: local validation

**PASS for this bounded local, synthetic slice.** Branch `codex/package-l7b1-visit-desk`, parent `9c4dfbb`
([L7 design](../../PACKAGE_L7_DESIGN_2026-10-22.md), L7b split), source commit `d1c12ca9af26f6a8fff81f394c40d63791ef1a41`.
[CHECKS.json](CHECKS.json) was written before the source commit and binds every source blob, command,
exit code and log digest. No migration; readiness unchanged.

## What changed

| Area | Change |
|---|---|
| Bookings screen | "Visit desk" on a confirmed booking: complete the visit (optional actual quantities; planned and actual shown) and write its materials off (owner, storage place of the visit's branch, date); reopening shows what is done |
| API | `GET .../bookings/{id}/completion` (`booking.read`, branch scope; 404 `VISIT_NOT_COMPLETED`) |
| Contracts | One strict web schema for complete, consumption and the completion read, chosen by path; paged owner, place and material lists read to the end |

## Proof

Real Chromium through the actual OIDC/PKCE sign-in, desktop and mobile: a visit started three hours
ago is completed with 3.0 ml of dye instead of the recipe's 2.5, the table shows both, the materials are
written off from the branch's shelf, keyboard-only close, axe without violations, no horizontal scroll;
after a reload the desk shows the completed, written-off visit. The database then holds two completions
with their stock documents, uses (planned 25, actual 30 tenths of a millilitre) and 60 tenths written off.

## Failures kept

- Web contract spec red (1 failed) and the API read test and browser test red (route missing, no desk)
  — expected; this time the browser spec and wrapper were written before the code.
- **dev-1**: the browser test failed before the browser — `asyncio.run` used the Windows Proactor loop,
  which psycopg's async mode cannot use; the test uses the selector loop.

## Gates (final, suffix 1)

Run folder `GorgonaBookingTests/package-l7b1-20261022-9c4dfbb`: **static-1** PASS; **focused-1** PASS, **436
passed**; **full-1** PASS, **2514 passed, 4 skipped** (51 minutes locally).

## Remaining

L7b2: the invoice, commission, prepaid redemption, commission plan and prepaid sale on screen. The next
migration is **0072**.
