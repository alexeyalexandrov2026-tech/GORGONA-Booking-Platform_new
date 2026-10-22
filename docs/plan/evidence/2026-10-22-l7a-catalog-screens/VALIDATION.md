# L7a — catalog screens: local validation

**PASS for this bounded local, synthetic slice.** Branch `codex/package-l7a-catalog-screens`, parent
`259cfd2` ([L7 design](../../PACKAGE_L7_DESIGN_2026-10-22.md)), source commit `13919b33471f0f90627cf1128de4dd1bb42d23ed`.
[CHECKS.json](CHECKS.json) was written before the source commit and binds every source blob, command,
exit code and log digest. Readiness unchanged.

## What changed

| Area | Change |
|---|---|
| Services screen | "Stages and materials" per service: stages (kind, minutes, resource kinds; total; a stale revision reloads with a notice) and materials (material and quantity; read back) |
| Staff screen | Equipment is a resource kind |
| API | `GET .../services/{id}/materials` and `.../add-ons/{id}/materials` (`catalog.read`, branch scope allowed) |
| Contracts | Strict web schemas for stages and recipes, chosen by path |
| Security | `npm audit` flagged GHSA-2464-fhr4-w9xw (critical, Next.js Image Optimization remote code execution, `next` ≤ 16.4.0), published after L6. `next` and `eslint-config-next` upgraded to 16.4.2; runtime audit 0. The app is a static export that does not serve that API; the five development-only findings predate this slice |

## Proof

Real Chromium through the actual OIDC/PKCE sign-in, desktop and mobile: three stages saved (90 minutes),
a change made elsewhere reloads with a notice, a quantity finer than the material refused then saved,
keyboard-only close, axe without violations, no horizontal scroll; after the browser the database holds
exactly those stages, durations and the recipe (25 tenths of a millilitre), and two equipment resources.

## Failures kept

- Web contract spec red first (2 failed, 1 passed) — expected.
- **Process**: the API read test and the browser spec were written after the code, not run red first.
- **dev-1/dev-2**: a real bug the browser found — the materials editor kept the service revision seen
  when the dialog opened; saving the stages moves it, so the materials save looked stale. It now uses
  the latest revision.
- The npm audit finding above (fixed in this slice).

## Gates (final, suffix 1)

Run folder `GorgonaBookingTests/package-l7a-20261022-259cfd2`: **static-1** PASS (runtime audit 0);
**focused-1** PASS, **434 passed**; **full-1** PASS, **2512 passed, 4 skipped** (48 minutes locally).

## Remaining

No screen for add-on recipes yet; the visit desk is L7b; the customer site is L7c. `main` and the
earlier L branches still pin `next` 16.3.8 until merged. No migration; the next is **0072**.
