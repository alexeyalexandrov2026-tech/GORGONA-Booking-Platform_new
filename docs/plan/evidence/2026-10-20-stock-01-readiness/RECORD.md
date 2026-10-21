# STOCK-01 — readiness record (2026-10-20)

**Decision: STOCK-01 is `technically_verified`.** Not a pilot acceptance and not a production approval.

## Owner's word

On 2026-10-20 the agent proposed the STOCK-01 record ("Это короткий шаг того же рода, что FIN-02") and
the owner answered «ok». The [technical acceptance of 2026-10-15](../2026-10-15-stock-01-acceptance/ACCEPTANCE.md)
had left the status `planned` only because promotion "needs the owner's separate explicit word".

## Evidence

- **J-01–J-14 PASS** on `aedbb98` with exact-commit CI run 157 and a full local suite (1748 passed,
  4 skipped); the J1–J4 and J5/J6 independent reviews with their fixes (including H1 by 0043).
- **Later changes to the stock code**, each verified in its own slice: K1h statistics and K1i posting
  plans independent of statistics (0047; [K1i validation](../2026-10-17-k1i-stock-plan-stability/VALIDATION.md)).
- **Current code:** `ea74bec` (main is `1a8a180`, which contains it): full disposable PostgreSQL 18.6
  and browser suite **2328 passed, 4 skipped** (K5c gates), including every stock and inventory test
  and the Materials and Stock documents browser tests; exact-head CI SUCCESS on `1a8a180` (run
  39527769354, K5c branch).

## What this enables

The `inventory` module follows STOCK-01, so a company **may now enable it** by publishing a
configuration that also has `finance`. Nothing is enabled automatically.

## Limits (unchanged from the acceptance)

No customer-owned goods, batches, serial numbers, purchase orders or multi-warehouse WMS (stage 6,
SUPPLY-01); approximate intermediate histories backfilled by 0042 (L1); cancellation tombstones expire
after 24 hours (L4); an archived-outbound browser scenario is NOT TESTED; deployment and production
migrations are separate gates. ADR-0026 stays Proposed.
