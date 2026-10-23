# L7c — customer site: several services in one visit, stages shown: local validation

**PASS for this bounded local, synthetic slice.** Branch `codex/package-l7c-customer-site`, parent `8f678eb`
([L7 design](../../PACKAGE_L7_DESIGN_2026-10-22.md), decisions 48-53), source commit `1b00d01`.
[CHECKS.json](CHECKS.json) was written before the source commit and binds every source blob, command,
exit code and log digest. No API change, no migration; readiness unchanged.

## What changed

| Area | Change |
|---|---|
| Service step | "Add another service" adds up to four more services (five in all), each with its own select (`aria-label` "Service N"), add-ons and "Remove service N"; a further line offers services not yet in the visit and in its currency |
| Add-ons | Judged across the whole visit (currency, once per visit, requirements met by any line, no duplicate or conflict), as the server's rules (L2 decision 12) |
| Specialist | Only specialists of the branch serving every service of the visit are offered |
| Summary | The server's quote: every line with its price, the total and duration; a version 2 quote also lists its stages in order ("With your specialist", "Processing — your specialist is free meanwhile", "Finish") with minutes; review and confirmation name the services |
| Requests | `extra_lines` only for a visit of several services; a one-service request is byte-identical to before (same idempotency fingerprint) |
| Refusals | A refusal of the visit itself (`INCOMPATIBLE_SELECTION`, `SERVICE_NOT_BOOKABLE`, `ADD_ON_NOT_BOOKABLE`) shows the server's words without "Retry"; other failures keep it |
| Contracts | Strict `quoteSchema` reused unchanged; pure helpers in `web/lib/visit.ts` with unit tests |

## Proof

Web unit (`customer-visit.spec.ts`, 7 cases): one-service request without `extra_lines`, a visit's lines in
order, services offered to a further line, add-ons across the visit, specialists serving every service, stage
words, a two-service version 2 quote parsed strictly.

Real Chromium against the exported site, FastAPI and PostgreSQL 18, desktop and mobile, keyboard only: a guest
chooses the staged FAKE gel (30 active, 60 processing, 20 finish) and the FAKE style (30 min) that only artist
A1 serves; the request carries one extra line; the summary shows both lines ($65.00, $30.00), $95.00, 140
minutes and the four stages; only A1 is offered; hold, details, review and confirmation name both services;
axe without violations, no horizontal scroll. The database then holds per project one confirmed booking whose
quote (version 2) has FAKE_GEL then FAKE_STYLE, total 9500, and intervals: A1 for the first 30 minutes and
again from 90 to 140, the chair 0-110, the processor 30-90. Gel plus FAKE base is refused with the server's
words "FAKE FAKE_BASE duplicates something already in this visit", no retry, and nothing is written. The old
one-service journey (`booking.spec.ts`, 16 cases) passes unchanged.

## Failures kept

- Web unit red: `customer-visit.spec.ts` could not load (`../lib/visit` missing) — expected.
- red-1: the browser timed out waiting for "Add another service" — expected.
- No failure after the code: dev-1 and gates-1 passed at the first attempt.
- Development dependency audit: 5 high, the same as L7b2b with an unchanged lockfile; runtime audit 0.

## Gates (final, suffix 1)

Run folder `GorgonaBookingTests/package-l7c-20261023-8f678eb` (worktree `package-l7b2b`): **static-1**
PASS; **focused-1** PASS, **444 passed**; **full-1** PASS, **2521 passed, 4 skipped** (46 minutes locally).

## Remaining

L8: BEAUTY-01 acceptance — L-01..L-12 against the evidence of L1-L7c with honest gaps, one independent review
(owner's consent), a readiness record (owner's word) and the fast-forward of `main` (owner's word). The next
migration is **0072**.
