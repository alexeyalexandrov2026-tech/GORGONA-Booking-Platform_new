# E2-A file profile and CSP evidence — 2026-10-05

Scope: security prerequisite for E2, not complete documents/files acceptance.
Base `3983dd4f36e67830427cc09fafcb51ae68c7705d` (accepted E1), branch
`codex/package-e2-file-validation`. No migration or readiness promotion.
[Decision](../../../adr/0021-bounded-file-validation-profile.md).

Code SHA: `ce31e21de2d1d290408ace74628ed928d728deb8`.
Draft [PR #8](https://github.com/alexeyalexandrov2026-tech/GORGONA-Booking-Platform_new/pull/8)
targets `codex/package-e1-counterparties`; no merge.
Disposition: **PASS for the bounded E2-A prerequisite**, not complete E2 acceptance.
The follow-up evidence commit changes documentation only; inspect its exact-head
CI in PR checks rather than treating this code-SHA proof as its own result.

## Observable flow and reuse

File bytes → actual size/signature → bounded structural profile → immutable metadata.
No file I/O/network/execution, storage, upload/download route or scanner. Reuse stdlib
and DomainError. Existing API response → preserve every existing CSP → additional
independent framing policy; no auth, tenant or HTML embedding rewrite.

## Direct checks

| Check | Observed outcome |
|---|---|
| Unchanged E1 baseline, required PostgreSQL/browser | PASS, exit0:596 passed/4 skipped/198.74s |
| New framing regressions before fix | FAIL, exit1:2 failed/1 passed/0.31s; existing CSP was overwritten |
| New validator checks before implementation | FAIL, exit2:1 collection error/0.17s; missing module |
| Initial profile and framing | PASS, exit0:47/0.41s |
| Additional name/PNG/Huffman regressions before fix | FAIL, exit1:9 failed/44 deselected/0.17s |
| After those fixes | PASS, exit0:56/0.28s |
| Review findings: attachment aliases, decimal lookahead, geometry | FAIL, exit1:9 failed/53 deselected/0.19s |
| Page root/stream node regression before fix | FAIL, exit1:1 failed/63 deselected/0.14s |
|3D/unknown-feature regressions before fix | FAIL, exit1:9 failed/65 deselected/0.28s |
| Focused before final MCU review | PASS, exit0:77 passed/0.37s |
| Interleaved JPEG MCU regression before fix | FAIL, exit1:2 failed/2 passed/74 deselected/0.14s |
| Final focused validator/CSP | PASS, exit0:81 passed/0.30s |
| Ruff lint | PASS, exit0 |
| Ruff format | PASS, exit0:168 files already formatted |
| Strict mypy | PASS, exit0:168 source files |
| Web typecheck/lint/format | PASS, exit0 each |
| Web unit tests | PASS, exit0:47 passed/1.0s |
| Fresh web export | PASS, exit0:15 pages |
| Full local suite before final MCU review | PASS, exit0:673 passed/4 skipped/200.00s |
| Final full local suite, required PostgreSQL/browser | PASS, exit0:677 passed/4 skipped/204.12s |
| Exact code PR CI, ce31e21 | PASS:680 passed/1 skipped/127.85s; [run37280252370](https://github.com/alexeyalexandrov2026-tech/GORGONA-Booking-Platform_new/actions/runs/37280252370), job111666417806 |
| Exact code push CI, ce31e21 | PASS:680 passed/1 skipped/154.96s; [run37280214524](https://github.com/alexeyalexandrov2026-tech/GORGONA-Booking-Platform_new/actions/runs/37280214524), job111666297033 |
| CI web/static/image checks | PASS both runs:47 web tests (1.4s/1.5s),15-page export, Ruff/format/mypy168, production-image build |
| Changed documentation | PASS, exit0:11 UTF-8 files/135 local links; git diff --check and staged check |
| Final independent implementation review | PASS for bounded prerequisite:20 PDF and9 final JPEG probes, exit0; no edits/DB |

Local four skips are three Docker/container gates and one optional external tenant
site gate; mandatory PostgreSQL/browser gates are not skipped. Both code CI runs
executed all required PostgreSQL, browser and three container gates; the only skip
was the optional external site. One executor used the disposable 18.6 cluster,
loopback51454/max_connections250. Credentials remain in child environment only;
private connection settings are never printed, copied or committed.
The known test cluster was stopped after the final local suite, exit0.

Observed CI tooling warnings: Node deprecations in existing action/tool runners,
`setup-uv@v6` targets the deprecated Node20 action runtime (forced to24), and
`eslint@9.39.5` reports unsupported status. These remain a separate toolchain
maintenance item; no dependency audit/upgrade was performed in E2-A. They do not
replace the earlier dependency findings with a fresh audit result.

## Changed files

Source: `business/file_errors.py`, `file_validation.py`, `pdf_validation.py`,
`api/framing.py`; regression suites `test_file_validation.py` and
`test_framing_policy.py`. Documentation: ADR0020/0021, master/Package E plan,
implementation registry/audit, DEVELOPMENT, CLOUD_CODE_HANDOFF, START_HERE,
E2-A handoff and this evidence record. Total:17 files in the code commit.

## Independent security review

Reviewer read actual ADR/dependencies/middleware and ran pure-memory probes, with
no shared fixture suite, edits or DB operations. Findings produced fresh regressions:
optional EmbeddedFile Type can be absent (deny EF/FileAttachment aliases);3D
OnInstantiate can execute an unnamed stream; decimal reference lookahead; invalid
page root/stream nodes; name/comment costs; PNG metadata order and JPEG Huffman
structure and interleaved MCU size. Fixes use a positive PDF feature vocabulary,
explicit bounds and no new dependency. Final amended-source disposition is PASS
for this prerequisite, with no remaining grounded blocker from the independent
review. Reviewer did not independently run the full suite or CI. Final validator
SHA-256: `67da51683f9f8c5dd2e8a876a648a518b0a5bb043926bc2a999ff1e38f025691`.
Scope excludes a general reader, full image decoding and malware safety.

## Unverified boundaries

E2 persistence, migration0016, upload authorization/body cap and production scanner
gate, idempotency/audit, document links, binary download integrity, browser verified
downloads/UI remain planned. General PDF compatibility, JPEG entropy/rendering,
antivirus, memory/latency benchmark, full manual screen-reader audit, providers,
Azure, load/restore, industry pilots and production are NOT TESTED. E3 and CORE-04
are still next. Dependency audit was not repeated; manifests/lockfiles unchanged.
No merge, cloud change, deployment or production migration occurred.
