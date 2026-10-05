# GORGONA — E2-A continuation, 2026-10-05

Read [AGENTS](../../AGENTS.md), [master plan](GORGONA_MASTER_PLAN.md),
[registry](GORGONA_IMPLEMENTATION_STATUS.md), [ADR-0020](../adr/0020-counterparties-documents-and-contracts.md),
[ADR-0021](../adr/0021-bounded-file-validation-profile.md),
[E2-A evidence](evidence/2026-10-05-file-validation/ACCEPTANCE.md) and
[E1 handoff](NEXT_AGENT_PACKAGE_E1_2026-10-05.md).

## Current source

Active repository GORGONA-Booking-Platform_new; branch `codex/package-e2-file-validation`
in `C:\Users\alexa\.codex\worktrees\booking-state-isolation\Gorgona Booking`.
Base E1 `3983dd4f36e67830427cc09fafcb51ae68c7705d`, draft PR#7 into E0.
Fetch and inspect current branch/PR/CI before editing; acceptance is specific to SHA.
Owner checkout `C:\Users\alexa\Documents\ChatGPT\Gorgona Booking` retains its dirty
work. No reset/clean/restore/merge/overwrite. E1 source and separate owner backups
remain under Desktop/GORGONA_HANDOFF_2026-10-05; do not apply old drafts over E1.

This increment adds only `business/file_validation.py`, `pdf_validation.py`,
`file_errors.py`, unit tests and an API CSP preservation fix. It has no upload
endpoint, storage, migration or document UI. Module `documents` is still planned,
registry1 and business baseline unchanged. Preserve all39 industries/28 criteria,
existing generic booking, FORCE RLS, permissions and current migration lineage.

## Parser boundary

Read ADR-0021 before reuse. The validator supports a deliberately small fail-closed
PDF/PNG/JPEG profile, exact size≤10MiB, SHA256, safe names and explicit not_scanned.
PDF supports one classic xref, direct lengths, raw/Flate streams; positive key/type/
action vocabularies, real references/page tree, active-feature refusal including
EF/FileAttachment and3D/OnInstantiate. General PDFs, incremental/signed forms,
object streams and other filters are not supported. PNG is8-bit/noninterlaced with
limited metadata; JPEG has baseline marker/table/scan checks and at most10 blocks
per interleaved MCU, no entropy decoding. PDF custom resource keys require direct
map dictionaries; separately referenced maps can be conservatively refused.
Aggregate decoded budget32MiB,4096 objects/chunks,100k tokens, depth32, names127.
Do not equate this with malware detection or rendering safety.

API framing appends a separate CSP policy; never append a second frame-ancestors
directive inside an existing policy, where the first directive may win.

## Next coherent increment: complete E2 persistence/API/UI

1. Migration0016 per ADR0020: immutable document_files, documents, append-only
   document_versions and link event log; FORCE RLS/company-only restrictions,
   two module gates on links, guard38 definitions/10 optional gates. Never edit0015.
2. Typed versioned schemas; reference-only receipts/audit; expected revision/
   sequence, existing commands and module/publication locks. Manual links only.
3. Raw upload: staging/production503 before body read; short initial authorization;
   actual streamed cap with/without Content-Length; validate off event loop with
   bounded work; final reauthorization, schema guard, claim/module check, insert
   and audit in one transaction. A slow upload must not hold membership locks.
4. Download rechecks hash, attachment/nosniff/CORP/CSP; use preserved policy. Browser
   independently checks actual type/size/hash before saving; never inline preview.
5. Documents UI, loss-of-response retry, conflicts, history, archive, counterparty
   links, mobile/keyboard/automated accessibility. Errors must disclose no bytes,
   names or titles in audit or receipts.
6. Real registry refusal while implemented, test-only override through actual
   publication for unaccepted module, full gates and independent review; promote
   only after exact-code CI and a separate evidence commit. Never bump registry1
   just for readiness. E2 is not accepted because this prerequisite is green.

After E2: E3 agreements, then CORE-04 shared occupancy; no separate resource store.
Azure/production/provider actions require their own authorization and acceptance.

## Verification workflow

`api`: `uv run pytest -q tests/unit/test_file_validation.py tests/unit/test_framing_policy.py`;
then Ruff format/check and strict mypy. Web typecheck/lint/format/unit/build first,
then full suite with required PostgreSQL/browser and fresh export. One executor,
no parallel fixture suites. E1 ignored helper `handoff/run_test_database.py` uses
private LOCALAPPDATA/GorgonaBookingTests/postgres-18.6 settings without printing
them. Do not include them in Git or artifacts; start only known loopback51454.
Docker gates are local skips and required in exact-HEAD CI. See evidence for exact
results and review limits. General-format support, scanner and E2 workflow remain
NOT TESTED, as do providers, Azure, load/restore, pilots and production.
