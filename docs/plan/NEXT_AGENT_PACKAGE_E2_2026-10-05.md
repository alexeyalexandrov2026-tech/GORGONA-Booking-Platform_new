# GORGONA — E2 continuation (documents), 2026-10-05

Read [AGENTS](../../AGENTS.md), [master plan](GORGONA_MASTER_PLAN.md),
[registry](GORGONA_IMPLEMENTATION_STATUS.md), [ADR-0020](../adr/0020-counterparties-documents-and-contracts.md)
(section "E2 implementation"), [ADR-0021](../adr/0021-bounded-file-validation-profile.md),
[E2 evidence](evidence/2026-10-05-documents/ACCEPTANCE.md) and the
[E2-A handoff](NEXT_AGENT_E2_FILE_VALIDATION_2026-10-05.md).

## Current source

Branch `claude/package-e2-documents` in worktree
`C:\Users\alexa\Documents\ChatGPT\gorgona-e2-documents`, based on E2-A `4a6f63b`
(draft PR #8). Code `2ab24f3` passed push CI run 37289072512; the acceptance
commit promotes `documents` to `technically_verified`. No PR was opened (no GitHub CLI
in that session): open a draft PR into `codex/package-e2-file-validation`. Nothing is
merged. Fetch and check the exact HEAD, PR and CI before editing — acceptance is
specific to a SHA. The owner checkout `C:\Users\alexa\Documents\ChatGPT\Gorgona Booking`
keeps uncommitted work: no reset/clean/restore/overwrite/merge there. Each agent
uses its own worktree/branch and its own disposable cluster; only one executor
runs the PostgreSQL suite at a time. This session used cluster 127.0.0.1:51455
(`%LOCALAPPDATA%\GorgonaBookingTests\claude-cluster`, runner
`handoff/run_pytest_51455.py`, gitignored); 51454 belongs to another agent.

## What E2 delivers

Migration 0016 (four FORCE-RLS insert-only tables), `business/document_contracts.py`,
`business/documents.py`, `api/documents.py`, guard 38 definitions + ten optional
gates (no WHEN/constraint triggers), web `/documents/` page, counterparty "Linked
documents" panel, verified binary upload/download, integration/unit/web/browser
tests. Module `documents` is **technically_verified** after the acceptance commit.

## Next steps, in order

1. Done: exact code push CI green. Check the acceptance SHA's own CI and open the
   draft PR (PR CI then runs too). If red: cause, red→green regression, new SHA.
2. Done in the acceptance commit: `documents` → `technically_verified` in
   `business/modules.py` with the evidence path in `limits`; switch fixtures
   (`test_documents.py`, `test_document_browser.py`) from `verified_modules` to the
   real registry; turn `test_documents_use_real_registry_and_require_explicit_publication`
   into proof that explicit publication succeeds without the override (as E1 did);
   update `tests/unit/test_configuration_contracts.py` enableable list
   (`["counterparties", "booking_resources", "documents"]` order as in that test);
   record CI in evidence, ADR-0020, registry, audit, START_HERE. Never bump
   `MODULE_REGISTRY_VERSION`. Then CI of that SHA too.
3. E3 agreements (migration 0017, module `counterparties`) per ADR-0020: insert-only
   versions draft/agreed/terminated, `signed_outside_platform` attestation, optional
   document version reference (`document_id` + `document_revision`, needs documents
   readable — reads are never gated), guard 40 definitions / 12 gates, marker
   `-- Agreement branch scope:` (17) in `test_location_access.py`.
4. CORE-04 shared occupancy afterwards; no separate resource store.

## Known limitations (do not silently "fix" by relaxing)

See evidence: no scanner, upload memory/quota, old-key early-check skip, guard not
covering immutability triggers or extra permissive policies, unchecked author
columns, one-level merge aggregation. Uploads stay refused in staging/production.
No production, provider, cloud, deploy, merge or production migration without the
owner's explicit authorization.
