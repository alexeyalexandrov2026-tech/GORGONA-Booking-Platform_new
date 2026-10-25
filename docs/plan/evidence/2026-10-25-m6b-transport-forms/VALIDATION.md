# M6b — planning forms, fleet, carrier grants and the dispatcher's navigation: local validation

**PASS for this bounded local, synthetic slice (package M, transport screens).** Branch
`codex/package-m6b-transport-forms`, parent `75b4915` ([M6b design](../../PACKAGE_M6B_DESIGN_2026-10-25.md)),
source commit `ba9cb64`. [CHECKS.json](CHECKS.json) was written before the source commit and binds every source
blob, command, exit code and log digest. User 2026-10-25: "Continue with M6b the same way."

## What changed

- `GET orders` takes `?after=<id>` and returns at most 50 orders in id order with `next_cursor`; it stopped
  silently at 100 before. No migration.
- Owners and managers: an **order** form (an active customer, up to 50 loads, corrected with its revision; each
  load shows how much is planned), a **trip** form (location, stops with windows entered in each stop's own
  time zone, legs from the order's loads; a planned, unassigned trip can be corrected) and **fleet** forms
  (a driver, a truck or trailer, registered once with fixed details under ADR-0029). Refusals are shown in words
  and the form keeps what was entered; a save clears the previous notice.
- The **grant form** offers transport actions (plan trips, assign crews, record stop events) with or without
  booking access ("No bookings"); any action brings `transport.read`; grants are listed in words, for example
  "Transport: view, assign crews, record stop events".
- **Navigation:** a delegate sees Transport with `transport.read`, the calendar and bookings only with
  `booking.read`; the transport screen shows a delegate only the granted forms and never the fleet forms.

## Proof

`test_m6b_order_list.py` (M6b-01): 103 orders paged to the end, the empty page after the last id and 422 on a
malformed cursor. `test_m6b_transport_browser.py` (M6b-02..07, real Chromium desktop and mobile, axe, no
horizontal scroll): driver and truck registered; an order with two loads, corrected to revision 2; a trip with
three stops in three zones whose overplanned leg (9 of 8 crates) is refused in words and saved as 8; the trip
corrected while planned; the carrier offered "assign crews" and "record stop events" without bookings; the
carrier accepts for its dispatcher; the dispatcher sees Transport but not the calendar, bookings or company
areas, sees no planning or fleet form, assigns a driver and truck and records an arrival. The mobile run revokes
the desktop grant first (one open delegation per pair). PostgreSQL read back: names, loads, stop instants,
legs, assignments and the event by the dispatcher, grant rights and status. `transport-contracts.spec.ts` (+2).

## Failures kept

- red-1: the order list had no `next_cursor` (expected RED); the browser part failed on a refused connection
  because the spec had no base URL — a test defect, not the intended RED. red-2: the Driver form did not exist
  (intended RED).
- Before dev: ruff E501 and PT018 in the new browser test.
- dev-1: **design slip** — the design said a driver's name is corrected with `PUT` on the same id; ADR-0029
  decision 1 registers once and the server refuses other details. Correction is left out of M6b and the design
  was amended. A repeated "saved" notice could read as the next save's answer; each form now clears it first.
- dev-2: **test design slip** — one open delegation per pair of businesses, so the mobile run's second offer
  was refused; the mobile run revokes the desktop grant first. The refused offer showed no message inside the
  delegated access region (noted as an open defect).
- Gates passed on the first run.

## Gates (suffix 1)

Run folder `GorgonaBookingTests/package-m6b-20261025-75b4915`: **static-1** PASS; **focused-1** PASS,
**723 passed**; **full-1** PASS, **2605 passed, 4 skipped** (0:59:21 locally).

## Remaining

Planning forms for a delegate (a delegate cannot read the owner's customers or locations), fleet corrections
(their own decision), M7 (money), M8 (acceptance). Open defects: the time-of-day-dependent workforce browser
test (found in M6a) and the silent refused grant offer. Transport stays not enableable until package M's
acceptance and the owner's word. Next migration **0079**.
