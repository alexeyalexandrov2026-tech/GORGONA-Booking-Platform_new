# K1b receipt-only inbox — local validation

**PASS for the bounded local storage slice.** Source `543b73221ac1dd0aa738bd8cf33dd468366ef27a`, parent `ffb176b3cc4bd83637eff29246f6045e0705b9d3`,
branch `codex/package-k1b-inbox`. [CHECKS.json](CHECKS.json) was generated before the
source commit by write_record.py. No K branch was published.

Changed source files:

- `api/src/gorgona_booking/db/migrations/0044_provider_receipt_inbox.sql`
- `api/src/gorgona_booking/db/provider_receipt_guard.py`
- `api/src/gorgona_booking/providers/inbox.py`
- `api/tests/integration/test_provider_event_inbox.py`
- `api/tests/integration/test_provider_receipt_upgrade.py`
- `api/tests/integration/test_location_access.py` (restore K1b policies after CASCADE)

Three tables store a fixed `not_admitted` tenant/book connection, one immutable
normalized event per test namespace/account/event ID, and distinct delivery digests
with normalized facts/conflict classification. Provider/test/snapshot identity is
fixed by SQL. The book implies the existing same-tenant legal entity. No raw body,
header, metadata, customer/contact data or credential is stored. No public route,
new role, global routing grant, privileged function, worker or money effect is added.
Connections are provisioned only in synthetic owner test fixtures, not a production tool.

| Gate | Observed outcome |
|---|---|
| New PostgreSQL cases | PASS:40, present and passing in full JUnit |
| Focused | PASS: 252 passed in 79.86s (0:01:19) |
| Full disposable PostgreSQL18.6/browser suite | PASS: 1884 passed, 4 skipped in 1502.59s (0:25:02) |
| Ruff check/format, strict mypy | PASS, exit0; counts/commands in CHECKS.json |
| Web typecheck/lint/format/unit/build | PASS, exit0;114 web unit tests |
| Runtime npm audit | PASS:0 vulnerabilities |
| Existing development/full npm audit | FAIL:5 high; unchanged web lock, existing nonrequired finding |
| Actual production image | NOT TESTED: Docker unavailable;3 container skips |
| Optional external tenant-site | NOT TESTED:1 skip; not a current GORGONA dependency |
| Exact-current-K CI/publication | NOT TESTED: no K publication authorization |
| Independent security/integration review | NOT TESTED; required before exposure/acceptance |
| Actual Stripe account/admission/credentials/funds | BLOCKED by separate owner authorization; no action taken |
| Complete K1 / FIN-02 / K-01–K-14 | NOT TESTED; partial deterministic storage evidence only |

Exact gate entry point from this checkout, Python3.14.6:

```powershell
& '.\api\.venv\Scripts\python.exe' 'C:\Users\alexa\AppData\Local\Packages\Claude_pzs8sxrjxfjjc\LocalCache\Local\GorgonaBookingTests\package-k1b-20261015-ffb176b/run_gates.py'
```

It runs `runner.py static-2 static`, then `runner.py focused-2 focused` with the new
inbox/upgrade cases, migration unit, K1a signature, provider admission, settlements,
payment correction and external payment regressions; finally `runner.py full-2 full`.
CHECKS.json records every expanded command, exit, duration, version and log hash.
Each DB phase gets a fresh owned cluster, binds localhost, avoids reserved ports,
and stops its own postmaster. Final required gates exit0 with unchanged source hashes.
Passwords are generated privately; initdb's temporary file is removed immediately;
logs redact DSNs/passwords. No provider credential or account is accessed.

Three races require a real pg_locks transaction-ID wait with the intended blocker
and query: duplicate insert after leader commit, duplicate after leader rollback,
and revocation waiting on the connection-row lock. Rollback leaves no event/delivery;
committed replay through a new transaction preserves one identity. This is transaction
evidence, not a process-kill, power-loss or HTTP acknowledgement crash test.

Equal facts/different digest is a duplicate. Different facts/new digest is a durable
conflict. Digest reuse with different facts is refused. Runtime cannot provision or
reactivate bindings or update/delete/truncate history. Unscoped/foreign/branch/revoked
bindings fail closed. Direct SQL rejects private/untyped facts. Deferred completeness
refuses scope switching before commit. Schema checks compare policies, grants,
triggers, packaged function bodies, keys, checks and column/default definitions;
tests corrupt representative definitions. This is not a general database-tamper proof.

Synthetic signed PaymentIntent/Charge/Refund events reach PostgreSQL without customer
data or journals. A nonempty0043 snapshot upgrades once, preserving all prior row
snapshots and43 migration checksums. No old migration is edited.

Initial full-1: **FAIL,25 failed,1859 passed,4 skipped in1785.08s**. The legacy branch
boundary damage test dropped current_location_id() CASCADE and restored only older
policies. K1b's three company policies stayed absent; the guard correctly refused all
later receipts. A narrow missing_boundary regression failed before its cleanup was
extended from packaged0044. The test now checks K1b both before damage and after cleanup;
schema-damage cases first assert a healthy baseline. No guard was weakened. Final
static-2/focused-2/full-2 are the required green source-bound gates.

RED history is retained in CHECKS.json/run folder: missing module, OID serialization
mismatch in approvals,2 metadata failures before strengthening, READ COMMITTED refusal
before implementation, a corrected isolation fixture and a misplaced test assertion.
No failed required gate is reported green.

H4 false capabilities, manual attestation, readiness, main and published J remain unchanged.
HTTP streaming/commit acknowledgement, verified admission/routing, storage quotas/retention, K2 worker
and K3 financial effects are absent. [Handoff](../../NEXT_AGENT_PACKAGE_K1B_2026-10-15.md),
[reuse](ARCHITECTURE_REUSE.md).
