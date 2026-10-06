# H foundation — independent source review

2026-10-06. Reviewed `925ae02b581d22cf1e7897a3d94844b8ebc24648..7d371f874fd2c25e788082428c5b6dfa6af90ef2`.

**Status: one P2 contract finding and one P3 formatting finding remain in this exact snapshot.** Unit, lint and type checks pass; format check fails. This foundation is not a completed H1/FIN-03 implementation.

Independent checkout: `C:\Users\alexa\.codex\worktrees\package-g-final-review\Gorgona Booking`, clean branch `codex/package-h-foundation-review`, HEAD `7d371f874fd2c25e788082428c5b6dfa6af90ef2`. It was created from the shared commit with `git switch -c codex/package-h-foundation-review 7d371f874fd2c25e788082428c5b6dfa6af90ef2`; the previous `codex/package-g-final-review` branch remains at `95a0de4ac9f5aa3c96b054c5504f59115b0e4b69`.

## Findings

### H-F01 [P2] An issued view accepts an impossible recovery revision

[financial_contracts.py:113](<C:/Users/alexa/.codex/worktrees/package-g-final-review/Gorgona Booking/api/src/gorgona_booking/business/financial_contracts.py:113>) checks issued references but permits `state=issued, revision=1`. The same module's [FinancialCommandReference:136](<C:/Users/alexa/.codex/worktrees/package-g-final-review/Gorgona Booking/api/src/gorgona_booking/business/financial_contracts.py:136>) explicitly rejects invoice_issue revision1 because issue follows a saved draft.

Reproduced independently without DB: starting from the valid unit draft, a view with revision1/state issued, exact total0.30, valid entry_id/obligation_id/issued_on/attestation is accepted. Constructing its invoice_issue recovery reference with that same revision raises ValidationError. A state accepted by the exported view contract cannot be represented by its recovery contract.

**Fix:** apply the issued minimum revision2 consistently in the view validator and add a valid-issued-references regression with revision1 (reject) and revision2 (accept). No future endpoint/SQL behavior is assumed in this finding.

### H-F02 [P3] Locked Ruff formatter does not accept modules.py

[modules.py:165](<C:/Users/alexa/.codex/worktrees/package-g-final-review/Gorgona Booking/api/src/gorgona_booking/business/modules.py:165>) splits the two unavailable-workflow literals. Ruff0.16.9, matching api/uv.lock, expects one combined line. `ruff format --check --no-cache` exits1: one file would be reformatted; six are already formatted. Lint passes. Join that literal using the locked formatter before reporting format PASS for this SHA. The reviewer did not edit it.

## Independent checks

Python: `C:\Users\alexa\.codex\worktrees\package-g-ledger-review\Gorgona Booking\api\.venv\Scripts\python.exe`. Working directory: the review checkout's api. PYTHONPATH explicitly pointed at the review checkout's api/src; PYTHONDONTWRITEBYTECODE=1. Printed imported module paths confirmed the independent snapshot, not the implementation checkout.

- `pytest tests/unit/test_financial_documents.py tests/unit/test_configuration_contracts.py -q -p no:cacheprovider`: **PASS, 65 passed/0.21s**, exit0.
- `pytest tests/unit/test_ledger_contracts.py -q -p no:cacheprovider`: **PASS, 22 passed/0.15s**, exit0.
- Ruff check of all seven changed Python files: **PASS**, exit0.
- Ruff format check of those files: **FAIL**, exit1, as H-F02.
- Strict configured mypy of those files, nonincremental with cache outside source: **PASS, no issues in7 files**, confirmed exit0.
- `git diff --check 925ae02..7d371f8`: **PASS**, exit0.
- G ledger service/API, migration0020, web ledger contracts/recovery: no diff from the plan base.

The scoped static-check argv, rendered with reusable variables:

```powershell
$reviewPython = 'C:\Users\alexa\.codex\worktrees\package-g-ledger-review\Gorgona Booking\api\.venv\Scripts\python.exe'
$env:PYTHONPATH = 'C:\Users\alexa\.codex\worktrees\package-g-final-review\Gorgona Booking\api\src'
$env:PYTHONDONTWRITEBYTECODE = '1'
$reviewFiles = @(
  'src/gorgona_booking/business/financial_contracts.py',
  'src/gorgona_booking/business/financial_math.py',
  'src/gorgona_booking/business/ledger_contracts.py',
  'src/gorgona_booking/business/modules.py',
  'tests/unit/test_financial_documents.py',
  'tests/unit/test_configuration_contracts.py',
  'tests/integration/test_configurations.py'
)
& $reviewPython -m ruff check --no-cache @reviewFiles
& $reviewPython -m ruff format --check --no-cache @reviewFiles
& $reviewPython -m mypy --no-incremental --cache-dir "$env:LOCALAPPDATA\GorgonaBookingTests\package-h-foundation-review-evidence\mypy-cache" @reviewFiles
```

The reproduction used InvoiceDocumentView.model_validate on the existing unit draft data with state issued/revision1 and valid issue references, then FinancialCommandReference(invoice_issue, same book/document/revision). It printed view accepted and reference rejected; no effects or monetary transactions were executed.

## Assessment and limits

The pure helpers use bounded integer minor units, exact G conversion, immutable balance values and the P+C+R cap. Reserve/confirm/release/correction preserve the cap; credits retain original paid cash and split unpaid credit/refund arithmetic. Their docstrings correctly leave source identity, external outcome, dependencies and transactional authorization to callers/SQL. No database/service imports, persistence or fake permission result were added to those functions.

The public single_line_text refactor preserves the G validation algorithm; current callers were updated and22 independent G-contract tests passed. Registry2 adds the planned finance_documents child, deriving status from FIN-03; dependencies remain finance/counterparties, G stays enableable, baseline omits H and the product text clearly says the workflow is unavailable. The configuration integration delta is relevant coverage for published-v1 preservation and H refusal, but it was reviewed statically here, not executed independently.

Only the current foundation was reviewed. Missing H endpoints/SQL/UI and future race/state controls are phase boundaries, not invented findings against this commit. H SQL races, actual money effects, integration/browser/full CI: **NOT TESTED independently**. No DB51456 access, own PostgreSQL startup, SQL probes, money execution, implementation edits, root-file edits, commits or pushes. Root's reported checks were not inherited as independent proof. Only this external report and outside-source mypy cache were written.
