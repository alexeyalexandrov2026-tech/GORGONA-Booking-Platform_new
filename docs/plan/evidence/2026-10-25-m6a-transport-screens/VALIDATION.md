# M6a — dispatch board, trip page and list pagination: local validation

**PASS for this bounded local, synthetic slice (package M, transport screens).** Branch
`codex/package-m6a-transport-screens`, parent `9bcc51c` ([M6a design](../../PACKAGE_M6A_DESIGN_2026-10-25.md)),
source commit `76519b8`. [CHECKS.json](CHECKS.json) was written before the source commit and binds every source
blob, command, exit code and log digest. Owner's word 2026-10-25: «Поднятнуть а потом продолжить» (`main`
fast-forwarded to `ad21888`, CI SUCCESS run 40165514386; then package M continues).

## What changed

- `GET trips`, `GET drivers`, `GET vehicles` take `?after=<id>` and return at most 50 items in id order with
  `next_cursor` (the last id when more remain, else `null`); a malformed cursor is 422. No migration.
- `/transport/` (owner or manager, not a delegate; in the navigation): every trip with status, first and last
  window in the stop's own time zone, current driver and truck; trips, drivers and vehicles read to the end.
- Trip page: stops, legs (planned, loaded, delivered, refused, damaged, open), assignments with periods, event
  log; assign or replace from a moment in the first stop's zone; record a stop event with leg quantities in the
  stop's zone; check clearance with the reasons per role.
- A command keeps its Idempotency-Key and a stop event its source event id until success, so a retry after a
  lost answer records it once. Strict zod contracts for every transport response the screens use.

## Proof

`test_m6a_transport_lists.py` (M6a-01): 53 trips, 52 drivers and 52 vehicles paged to the end, the empty page
after the last id and 422 on a malformed cursor. `test_m6a_transport_browser.py` (M6a-02..07, real Chromium,
desktop and mobile, axe, no horizontal scroll): board and trip page times in their zones, driver then truck then
a replacement truck at 12:00 Chicago, arrived/loaded/delivered with the first delivery answer dropped and the
retry recording once, legs 7 delivered and 3 open, event log, clearance cleared (desktop, fresh duty records)
and unknown with "no duty records" (mobile); PostgreSQL read back. `transport-contracts.spec.ts` (4).

## Failures kept

- red-1: 2 failed — no `next_cursor` and the screen not built (expected RED).
- dev-1: ruff S608 on the fixed pagination clause (now `noqa` with its reason) and an import order; the web was
  not built so the browser test failed. dev-2: the alert check also matched Next's route announcer. dev-3: the
  assign helper went on before the answer and truck 1 was never assigned; the helper now waits for the reset.
- full-1: **2 failed**, 2601 passed. `test_i4_browser` (workforce approval status not shown) failed again alone at
  about 03:10 EDT, then passed at 03:17 EDT on the same source and on a `9bcc51c` baseline without M6a: it
  depends on the time of day; **root cause not established — an open defect in an existing test.**
  `test_provider_screen` U-07 answered 401 on a 300 s test token minted at fixture setup and passed alone;
  likely expiry under full-suite load, not proven. Gates were rerun as suffix 2.
- Record field: every record since L7c carries the template line "none: BEAUTY-01 stays partial until L8"
  (stale after L8c); in the BEAUTY-01 readiness record `readiness_unchanged: true` is false. Committed records
  are left as they are; this record carries the correct field.

## Gates (suffix 2)

Run folder `GorgonaBookingTests/package-m6a-20261025-9bcc51c`: **static-2** PASS; **focused-2** PASS,
**721 passed**; **full-2** PASS, **2603 passed, 4 skipped** (0:53:35 locally).

## Remaining

M6b (order and trip forms, fleet registration, transport rights in the grant screen, dispatcher navigation),
M7 (money), M8 (acceptance). The two open test defects above. Transport stays not enableable until package M's
acceptance and the owner's word. Next migration **0079**.
