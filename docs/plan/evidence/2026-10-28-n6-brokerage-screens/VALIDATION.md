# N6 — brokerage on the transport screens: local validation

**PASS for this bounded local, synthetic slice (package N, N6).** Branch `codex/package-n6-screens`, parent
`a833b22` ([N6 design](../../PACKAGE_N6_DESIGN_2026-10-28.md)), source commit `33fc82e`.
[CHECKS.json](CHECKS.json) was written before the source commit and binds every source blob, command, exit code
and log digest; the thirteen committed blobs were checked against it. Owner 2026-10-28: "Start N6" under full
delegation («Делай как считаешь нужным я доверяю тебе»).

## What changed

- No migration; the next stays **0086**.
- `web/lib/brokerage-contracts.ts`: strict zod contracts of the N1–N5 routes (broker authority, carrier profile,
  eligibility, tenders, rate confirmation, carrier pay, margin), wired into the transport response map; the board
  rule (legs no accepted tender covers) and eligibility reasons in words.
- `web/components/transport-brokerage.tsx` on the transport screen, for a company-wide owner or manager only:
  **Broker authority** (versioned, today's eligibility in words), **Carriers** (profile, eligibility),
  **Loads to cover** (tender a leg, record the carrier's answer, propose and agree rate confirmation versions,
  accrue the carrier's pay) and the order's **Margin** next to its money. Commands keep their id and
  Idempotency-Key until success; a refusal is shown in words and the form keeps what was entered.

## Proof

| id | Result | Test |
|---|---|---|
| N6-01 | PASS | browser: authority saved as a version, "May tender loads today."; profile makes the carrier eligible |
| N6-02 | PASS | browser: tender sent and accepted; the board drops the leg; API read-back one accepted tender |
| N6-03 | PASS | browser: version 2 (950.00) proposed and agreed, three table rows; read-back versions 1 and 2 agreed |
| N6-04 | PASS | browser: refused offer in words with the amount kept (nothing stored); accrual 950.00 for version 2; margin 1500.00 − 950.00 = 550.00 |
| N6-05 | PASS (delegate) | `transport-forms.spec.ts`: no brokerage headings for a delegate; see Not tested |
| N6-06 | PASS | `test_n6_brokerage_browser.py` desktop and mobile, axe clean, no horizontal scroll, DB counts; web unit contracts; full suite below |

## Failures kept

- red-1: the web unit spec failed, `brokerage-contracts` missing — intended RED.
- dev-1: the route map was not wired (1 unit failure); a substring button-name match after acceptance (1 browser
  failure, now exact). dev-2: on mobile a Carriers table covered the board button — the tables used a
  non-existent class; now `mgmt-table-container`. dev-3: 2 passed.
- gates-1: static failed, ruff E501 on a docstring line of the browser test; rewrapped; focused and full not run.

## Not tested

- A branch-limited member is covered by the page rule (brokerage only when the membership has no location) and
  the server's refusal, not by a browser run.
- The carrier's company link and its own answers through a grant stay API-only (N4).

## Gates (suffix 2)

Run folder `GorgonaBookingTests/package-n6-20261028-a833b22`: **static-2** PASS; **focused-2** PASS,
**832 passed**; **full-2** PASS, **2653 passed, 4 skipped** (0:44:18 locally).

## Remaining

N7 acceptance. Readiness and enabling transport wait for the owner's word. Next migration **0086**.
