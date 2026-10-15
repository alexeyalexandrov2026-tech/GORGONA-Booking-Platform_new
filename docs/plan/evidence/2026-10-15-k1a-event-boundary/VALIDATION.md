# Package K1a — local offline signature/event boundary, 2026-10-15

**PASS locally** on source commit `7d25aa2d72874271a62e363817e0624fb502497c`, branch `codex/package-k1a-event-boundary`,
base `e8783f63254d1cffdbf6360513b5bf8f3ff411d1`. This is the first bounded part of K1, not a complete webhook or FIN-02 acceptance.
[CHECKS.json](CHECKS.json) was written before the code commit and binds all six source files.
[Architecture/reuse](ARCHITECTURE_REUSE.md), [handoff](../../NEXT_AGENT_PACKAGE_K1A_2026-10-15.md).

## Changed source and exact scope

- `api/pyproject.toml`, `api/uv.lock`: pin the official `stripe==16.0.0`. Only this
  package was added; all existing resolved package versions stayed unchanged.
- `api/src/gorgona_booking/providers/__init__.py`: bounded provider namespace.
- `stripe_contracts.py`: frozen versioned test snapshot contracts, finite event/resource
  kinds, exact integer minor units, namespace/account/version and separate delivery/facts hashes.
- `stripe_events.py`: use the official signature verifier on bounded original bytes
  before JSON parsing; reject stale/future/ambiguous signatures, mismatched account,
  live mode and API version; strict UTF-8/JSON with duplicate/non-finite rejection.
- `api/tests/unit/test_stripe_event_boundary.py`: 96 synthetic cases. Signing keys are
  generated only in test memory and masked with SecretStr. No real Stripe key or account.

The output explicitly says `signature_only`; it carries no tenant/book/admission or
paid/posted assertion. Selected metadata/customer/contact/request fields are omitted.
Event facts hashing tolerates delivery formatting/metadata differences and detects changed
selected facts; it is not operation-level dedup across different provider event IDs.

There is no HTTP route, inbox, worker, schema/migration, user/service role, provider
client call, money effect or readiness change. K1b must supply durable admitted connection
routing and receipt before any acknowledgement. Do not attach this decoder directly to a
success-returning webhook. Its 11-event snapshot decoder and API-version candidate
`2026-09-30.endive` are proven with synthetic fixtures, not a real admitted merchant.

## Checks

| Check | Observed result |
|---|---|
| Initial boundary import | FAIL as expected: 1 missing-package collection error, exit 2 |
| New public-contract regression | FAIL as expected: numeric 0 mode, unconstrained event type and overflowing ignored float; 3 failed/2 passed/87 deselected |
| UTF-16/32 signed JSON regression | FAIL as expected: 4 failed/92 deselected; corrected to explicit UTF-8 parsing |
| Focused boundary | PASS: 96 passed in 0.40s |
| Initial Ruff | FAIL: test-style findings; preserved focused logs, corrected without suppressing security checks |
| Ruff check/format, strict mypy | PASS, static-1; mypy checks 299 files |
| Web typecheck/lint/format, 114 unit tests, production web build | PASS, static-1 |
| Focused suite, fresh disposable PostgreSQL | PASS: 191 passed in 53.85s |
| Complete suite, another fresh disposable PostgreSQL | PASS: 1844 passed, 4 skipped in 1444.23s (0:24:04) |
| Runtime npm audit | PASS: 0 findings |
| Documentation and source bindings | PASS: 11 Markdown files, 1 JSON record, 23 new local links; UTF-8, source hashes and whitespace, exit 0 |
| Development npm audit | FAIL: 5 existing high findings, unchanged web dependency tree |
| Actual Stripe SDK on Python 3.14.6 | PASS: import and all signature boundary fixtures; package MIT license inspected |
| Real Stripe admission/delivery/API or account eligibility | BLOCKED by separate provider/credential authorization; NOT TESTED |
| Complete K1, K-01–K-14, independent review | NOT TESTED; no whole-row acceptance claimed |
| K publication/exact-head CI, local container and optional external-site gates | NOT TESTED; no K push authorization; four local full-suite skips preserved |
| Azure/production, funds, credential setup, readiness promotion | NOT TESTED; no such actions authorized/taken |

Every completed DB phase used a new cluster and stopped it; no postmaster.pid remained.
Sources and built web output were unchanged throughout focused/full checks. Required
runner failures return nonzero; the development audit is explicitly non-gating and FAIL.
No new race is claimed by K1a. Existing full-suite races still require actual pg_locks waits.

Commands from the checkout (use its own `api/.venv/Scripts/python.exe`):

```text
python <run>/runner.py static-1 static
python <run>/runner.py focused-1 focused tests/unit/test_stripe_event_boundary.py tests/unit/test_provider_admission_contracts.py tests/unit/test_settlement_contracts.py tests/unit/test_payment_correction_contracts.py tests/integration/test_provider_admission.py tests/integration/test_external_payments.py
python <run>/runner.py full-1 full
python <run>/write_record.py
```

Run folder: `C:/Users/alexa/AppData/Local/Packages/Claude_pzs8sxrjxfjjc/LocalCache/Local/GorgonaBookingTests/package-k1a-20261015-e8783f6`. CHECKS.json retains exact expanded commands,
versions, log hashes, initial failures and source digests. Code commit precedes this
documentation commit; final actual local HEAD is captured outside Git in FINAL_VERIFICATION.json.
There is no current-K CI claim. Published J CI158 is inherited baseline evidence only.
FIN-02/STOCK-01 stay planned; ADR-0026/0027 remain Proposed. J's recorded limits are unchanged.
