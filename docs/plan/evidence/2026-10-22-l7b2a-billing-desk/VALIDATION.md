# L7b2a — visit billing, commission and plan screens: local validation

**PASS for this bounded local, synthetic slice.** Branch `codex/package-l7b2a-billing-desk`, parent `9d9ca65`
([L7 design](../../PACKAGE_L7_DESIGN_2026-10-22.md), L7b2 split), source commit `56ab1ee`.
[CHECKS.json](CHECKS.json) was written before the source commit and binds every source blob, command,
exit code and log digest. No migration; readiness unchanged.

## What changed

| Area | Change |
|---|---|
| Visit desk | "Billing": one draft invoice of the visit (book, customer, receivable and revenue accounts, number, date); once finance issued it, "Paid X of Y"; once paid, the commission is accrued once (expense and payable accounts, number, date) |
| Staff screen | "Commission" of a specialist: who is paid, currency, rules of one service or all other services, each a percentage or a fixed amount; a stale revision reloads with a notice |
| API | `GET .../staff/{id}/commission` (404 `COMMISSION_PLAN_MISSING`) and `GET .../bookings/{id}/commission` (404 `VISIT_NOT_COMMISSIONED`), both `finance.read` |
| Contracts | Strict web schemas for the visit invoice (FIN-03 invoice and obligation), the visit commission and the plan (a rule is a percentage xor an amount), chosen by exact path |

## Proof

Real Chromium through the actual OIDC/PKCE sign-in, desktop and mobile: the specialist's plan is saved
(10 % of all other services, paid to a FAKE payee); the visit is billed from its desk as a draft; finance
issues and settles it through the FIN-03 routes; after a reload the desk shows "Paid 50.00 of 50.00" and
the commission of 5.00 is accrued; keyboard-only close, axe without violations, no horizontal scroll. The
database then holds one visit invoice per visit, accruals of 500 minor units and two default rules of
1000 basis points.

## Failures kept

- Web contract spec red (3 failed, 1 passed) and API/browser red (reads 405, no plan button) — expected.
- dev-1: two harness slips, no tests ran (interpreter without pytest; test paths given from the wrong folder).
- dev-2: the rule's "Kind" select was also named "Percentage" through its selected option — a real
  accessibility ambiguity, fixed.
- gates-1 (mobile): the wrapped "Revenue account" label carried its options' text ("2100 Customer
  prepayments"), so "Customer" matched two selects once the accounts had loaded — the same real ambiguity;
  every select of the desk, billing and plan forms now carries an explicit name.
- dev-4: "Paid 50.00 of 50.00" not visible within 5 s after payment and reload, snapshot lost; not
  reproduced in four repeats (that run was about twice slower). **Cause not proven**; the spec now waits for
  the billing load explicitly and names a refusal, and the wrapper keeps the page snapshot.
- gates-2 full: `test_h4_browser` (finance, untouched) failed once on mobile under full-suite load and
  passed alone three of three. **Cause not proven.**

## Gates (final, suffix 3)

Run folder `GorgonaBookingTests/package-l7b2a-20261022-9d9ca65`: **static-3** PASS; **focused-3** PASS, **439
passed**; **full-3** PASS, **2517 passed, 4 skipped** (48 minutes locally).

## Remaining

L7b2b: selling a prepaid balance and redeeming it from the desk. L7c: the customer site. The next
migration is **0072**.
