# zod 4.6.7 security update: local validation

**PASS.** Branch `codex/package-l9b-commission-reversal`, parent `ed84938`, source commit `609159f`.
[CHECKS.json](CHECKS.json) was written before the source commit and binds both changed files, every command,
exit code and log digest. No API change, no migration; readiness unchanged.

## Why

The L9b static gate's `npm audit` reported a new high advisory, **GHSA-mrhx-c7xc-m3w5**: zod before 4.6.6 can
exhaust memory while validating oversized constrained collections. The web validates every management response
with zod. The lockfile was not changed by L9b, and the L9a audit hours earlier reported 0; the advisory is new.

## Change

`web/package.json` and `web/package-lock.json` pin **zod 4.6.7** exactly; no other package changes (the lockfile
diff is the zod entry only). After it, `npm audit --omit=dev` and `npm audit` report **0 vulnerabilities**.

## Gates (suffix 1)

Run folder `GorgonaBookingTests/package-l9-zod-20261023-ed84938`: **static-1** PASS (audit 0); **focused-1** PASS,
**486 passed**; **full-1** PASS, **2563 passed, 4 skipped**.
