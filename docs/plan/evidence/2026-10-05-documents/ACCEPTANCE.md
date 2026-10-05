# GORGONA E2 — documents, immutable files and counterparty links, 2026-10-05

Implementation branch: `claude/package-e2-documents`, based on E2-A
`4a6f63b` (`codex/package-e2-file-validation`, draft PR #8). Separate worktree;
the owner checkout `C:\Users\alexa\Documents\ChatGPT\Gorgona Booking` and other
agents' worktrees and test cluster 51454 were not touched. Local tests used the
disposable PostgreSQL 18.6 cluster 127.0.0.1:51455 only; its DSN stayed in the
child process environment.

**Gate: IMPLEMENTED, not technically verified.** Module `documents` is
`implemented` and cannot be enabled by a business. Promotion to
`technically_verified` requires green CI on the exact code SHA and a separate
acceptance commit (ADR-0019/0020). Registry version stays 1; the business
baseline stays booking-only.

## Implemented boundary

Migration `0016_documents.sql`: `document_files` (bytea, external storage, size
1..10,485,760 equal to `octet_length`, SHA-256 equal to the stored content,
PDF/PNG/JPEG, safe name with the type's extension, validator version),
`documents`, `document_versions` (title, category, optional ordered validity
dates, archived flag, optional tenant-scoped file reference) and
`document_counterparty_links` (linked/unlinked event log per pair). FORCE RLS,
tenant isolation and restrictive company-only policies on all four; runtime has
column-limited INSERT and SELECT only; update/delete triggers refuse rewrites;
revision and link sequence continuity, link alternation, current-document and
active-card rules are enforced in SQL under the documents (exclusive) and
counterparties (shared) locks. Five gate triggers: four `documents`, plus
`counterparties` on links. The guard checks 38 definitions and ten optional
gates including timing, enabled state, function, exact argument, no WHEN clause
and no constraint trigger.

API (`api/documents.py`): list/search/paging, read by revision, history, save
with expected revision, raw upload, metadata, verified attachment download,
link/unlink with expected sequence, documents of a counterparty including merged
duplicates. Upload order: staging/production 503 before the body is read →
declared type 415 → `Content-Length` 413 → short authorization and early module
check without locks (skipped only when the caller's key already holds a stored
result) → capped streaming read (also chunked) → validation in a worker thread →
exclusive documents lock, guard, claim, module check, insert, audit and receipt
in one transaction. Receipts hold `{file_id}`, `{document_id, revision}` or
`{link_id}`; audit details hold identifiers, revisions, category, media type,
size, SHA-256, validator version and sequences only.

Web: `/documents/` page (company-wide owner/manager navigation only), card with
dates, archive flag and file attachment, history and saved-version reads,
verified download, counterparty search/link/unlink, link history; "Linked
documents" on the counterparty card. Uploads send exactly the hashed bytes and
compare the stored metadata; downloads verify type, size, `X-File-SHA256` and
the computed hash and save an `application/octet-stream` attachment, never a
preview. Lost responses keep the command pending and retry with the same key.
`authorizedResponse` was extracted from `managementFetch` for binary requests.

## Direct evidence

| Check | Exact observed outcome |
|---|---|
| Migration/guard/location/counterparty/unit baseline with 0016 | PASS: 446 passed, 43.84 s |
| Replay after disable (red) | Expected FAIL: upload replay after disabling answered 409 `MODULE_DISABLED`; fixed with `precheck_upload`; 27 passed, 15.17 s |
| Documents integration suite | PASS: 27 passed, 15.17 s (before review fixes) |
| Browser harness alone | PASS: 1 pytest harness 15.07 s; Playwright desktop + mobile 2 passed, 9.1 s |
| First full suite | FAIL: 1 failed / 725 passed / 4 skipped, 276.81 s — focus check raced a disabled button in `documents.spec.ts`; fixed by waiting for enabled; harnesses then passed 3/3 runs (2 passed each, 21–23 s) |
| Independent review (read-only agent) | 4 confirmed defects (2 medium, 2 low) — all fixed below; suggestions recorded under limitations |
| Guard WHEN clause (red) | Expected FAIL: `when_false` case 1 failed / 4 passed, 4.44 s without the fix; PASS with it |
| Focused documents/counterparties/location after review fixes | PASS: 76 passed, 42.12 s |
| Web | PASS: typecheck, ESLint, Prettier, 55 unit tests, 16-page production export |
| Python static | PASS: Ruff format/check and strict mypy, 171 files |
| Final full local suite | PASS: **728 passed / 4 skipped / 286.50 s**, exit 0; mandatory PostgreSQL 18.6 and browsers, fresh export; skips: 3 Docker container gates (required in CI) and the external tenant-site gate |

Review fixes: web schemas count code points like the server (astral titles,
file names and E1 display names no longer break whole lists); the guard refuses
gate triggers with a WHEN clause or constraint trigger; an identical retry by
the same user after the 24 h key expiry returns the stored file instead of 409;
a refused new-document save for a disabled module no longer freezes the form.
Branch-session SQL visibility now also covers link rows.

## Limitations and NOT TESTED

- No malware scanner: files are `not_scanned`; uploads are refused in staging and
  production. Azure storage, private endpoints and a scanner need ADR-0012 work.
- Each in-flight upload holds about 2–3 copies of up to 10 MiB in memory; there is
  no upload concurrency limit or storage quota; uploaded but never attached files
  are kept (insert-only). Uploads are local/test only until a scanner exists.
- An old key skips the early module check, so its body is read before the final
  transaction answers with a replay or 422.
- The guard covers policies of the restrictive scope and module gates; like E1 it
  does not cover immutability/continuity triggers or extra permissive policies.
  Author columns (`created_by`, `uploaded_by`, `decided_by`) are not checked
  against membership, as in E1. A counterparty shows documents of duplicates
  merged directly into it (one level), as booking links do.
- Real-world PDFs/images outside the ADR-0021 profile are refused by design.
- Production, providers, Azure, load/restore, pilots and manual screen-reader
  acceptance: NOT TESTED. No merge, deployment or production migration.
