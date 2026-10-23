# L8b2 — package L acceptance gaps (races, modules, room): local validation

**PASS for this bounded local, synthetic slice.** Branch `codex/package-l8b2-acceptance-gaps`, parent `3c402ec`
([L8 design](../../PACKAGE_L8_DESIGN_2026-10-23.md), decisions 69-72), source commit `1e4368a`.
[CHECKS.json](CHECKS.json) was written before the source commit and binds every source blob, command, exit
code and log digest. No API change, no new route, no migration; readiness unchanged.

## What changed

| Decision | Result |
|---|---|
| 69 (L-03) | Proof only: two racing consumptions of one visit, two racing accruals and two racing redemptions of a one-unit package each leave one write; both calls are observed waiting in `pg_locks` behind a barrier that holds the row the service locks |
| 70 (L-10) | The visit desk reads `effective_module_ids` once: no write-off form without inventory, no billing without `finance_documents`, no commission form without workforce — one plain line instead; if the configuration cannot be read every step stays shown and the server refuses |
| 71 (L-10) | Proof only: billing, prepaid sale and redemption without `finance_documents` answer `MODULE_DISABLED` and write nothing (consumption, plan and accrual were proven in L8b1) |
| 72 (L-04) | Proof only: a room stage holds the room in the shared occupancy; an overlapping staff reservation of it is `SLOT_CONFLICT`, the specialist stays free during processing, the room is free after the visit |

## Proof

`tests/integration/test_l8b2_finance_races.py` (3, real PostgreSQL), `test_l8b2_stock_race.py` (1),
`test_l8b2_room_stage.py` (1). Browser (desktop and mobile, axe clean): `visit-desk.spec.ts` shows the
materials line with inventory off and writes off once it is back; `visit-billing.spec.ts` shows the billing
line with invoices off and the commission line with workforce off, then bills and accrues as before. The
configuration answer is altered in the browser only; the server state is unchanged.

## Failures kept

- red-1: 2 failed, 5 passed. Both browser specs did not find the "turned off" line — expected RED. The 5 API
  proofs passed at once on the existing code: decisions 69, 71 and 72 needed no API change. This is said
  plainly: they are proofs of existing behaviour, not fixes.
- L8a CI run 39971712190 failed on two untouched specs; fixed on the L8b1 branch (`c9434b7`); L8b1 CI run
  39981532055 SUCCESS.

## Gates (final, suffix 1)

Run folder `GorgonaBookingTests/package-l8b2-20261023-3c402ec`: **static-1** PASS; **focused-1** PASS,
**471 passed**; **full-1** PASS, **2548 passed, 4 skipped** (38 minutes locally).

## Remaining

L8c: the BEAUTY-01 acceptance record mapping L-01..L-12, every gap named (readiness and `main` only on the
owner's word). Next migration **0072**.
