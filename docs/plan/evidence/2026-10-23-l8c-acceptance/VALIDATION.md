# L8c — L-09 proofs for the commission and prepaid tables: local validation

**PASS for this bounded local, synthetic slice.** Branch `codex/package-l8c-acceptance`, parent `2798c55`
([L8 design](../../PACKAGE_L8_DESIGN_2026-10-23.md), decisions 73-75), source commit `558b580`.
[CHECKS.json](CHECKS.json) was written before the source commit and binds every source blob, command, exit
code and log digest. No API change, no new route, no migration; readiness unchanged. The acceptance record is
[ACCEPTANCE.md](ACCEPTANCE.md).

## Proof

`tests/integration/test_l8c_direct_sql.py` (2, real PostgreSQL, runtime role): updating or deleting a visit
commission, a commission rule or a plan is refused (`InsufficientPrivilege`); rewriting or deleting a prepaid
sale or redemption is refused; lowering what is used, or raising it without its redemption, is refused by the
use guard (`CheckViolation`) and the used unit stays 1; another company sees none of these rows.

## Failures kept

- red-1: 2 passed at once on the existing code — the grants, the use guard and RLS already hold. This is a
  proof, not a fix, and is said so.
- Slip: the docs commit `241854c` went out with a one-line placeholder for this file (an edit hook blocked
  the write); the full text follows in the next commit.

## Gates (final, suffix 1)

Run folder `GorgonaBookingTests/package-l8c-20261023-2798c55`: **static-1** PASS; **focused-1** PASS,
**473 passed**; **full-1** PASS, **2550 passed, 4 skipped** (37 minutes locally).

## Remaining

The owner's word on the readiness of BEAUTY-01 and on merging package L into `main`; the two named gaps
(L-06 policy, L-07 reversal after a refund). Next migration **0072**.
