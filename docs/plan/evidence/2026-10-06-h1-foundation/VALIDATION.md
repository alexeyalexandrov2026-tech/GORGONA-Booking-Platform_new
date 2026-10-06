# H1 foundation checkpoint — contracts, arithmetic and a closed workflow gate

2026-10-06. **Foundation checked; H1 invoice workflow IN PROGRESS.**
Source SHA: `843d0b3d1808e8de56ac732ad39107caa700426e`.
Branch: `codex/package-h-invoices`; base `925ae02b581d22cf1e7897a3d94844b8ebc24648`
of the published [H planning PR13](https://github.com/alexeyalexandrov2026-tech/GORGONA-Booking-Platform_new/pull/13).
The owner instructed `continue` after the scope/publication proposal. Local
implementation follows the full H plan; this does not accept a runtime, pilot,
production deployment or provider action. No further permission loop is needed
for ordinary local implementation and its disposable checks.

## Actual architecture and changed source

Seven API source/test files changed:

- `api/src/gorgona_booking/business/financial_contracts.py`: strict H1 invoice
  drafts, issue attestation, consistent view/recovery revisions and minimal
  references. Issued views require actual reference fields and revision >=2;
  schema bools, false totals and extra private fields are rejected.
- `api/src/gorgona_booking/business/financial_math.py`: pure exact projections
  for invoice minor-unit totals and P+C+R<=A, reserve/confirm/release, credit
  splits and effective correction. **These functions authorize and persist
  nothing**; future domain/SQL code must resolve source, scope, dependencies and
  ownership under the G lock, not treat a projection as an external cash fact.
- `api/src/gorgona_booking/business/ledger_contracts.py`: expose the existing
  single-line normalizer as `single_line_text`; G normalization and its money
  conversion policy remain the reused implementation.
- `api/src/gorgona_booking/business/modules.py`: registry2 with planned,
  non-enableable `finance_documents`, whose readiness comes from FIN-03 and
  depends on finance/counterparties. Existing G finance remains verified. Old
  published configuration versions are unchanged; new feature selection must
  be explicitly published after complete H acceptance.
- `api/tests/unit/test_financial_documents.py`: 47 new parameterized cases for
  decimal scales, exact0.1+0.2, bounds, strict versions, issued refs, partial
  allocation, credit/refund and new-feature denial.
- `api/tests/unit/test_configuration_contracts.py`: intentional19-module count.
- `api/tests/integration/test_configurations.py`: registry2 snapshots/stale1
  validation, plus real SQL/auth/publication preservation of a simulated
  previous-server v1 publication and rejection of unverified H.

G journal source enums, six-command recovery, permission map, migrations0001–0020,
dependency locks and web source are unchanged. No H endpoint, SQL table, public
posting seam, financial document, payout or refund has been implemented yet.

## Independent review and red-to-green

[Gate design review](GATE_REVIEW.md) confirms reuse of the current publication
pattern: registry2, no unconditional money gate on OFF recovery/release, child
lineage controls only on H-owned journals and explicit readiness withdrawal checks
in future H commands. These future controls are requirements, not existing SQL.

[Initial source review](INITIAL_REVIEW.md) found H-F01/P2: an otherwise-valid
issued view accepted revision1 while recovery required2; H-F02/P3: one Ruff
formatting failure. The revision regression first failed1/46passed, then the
view minimum was fixed and project formatting applied in843d0b3.
[Final source review](FINAL_REVIEW.md): both findings CLOSED; independently87
unit, scoped lint/format/mypy PASS in a separate clean branch/checkout. It is
not independent H money/PostgreSQL/browser acceptance.

Original external reports are retained. Copies here intentionally use repository
LF newlines; source and normalized-file SHA256 are distinguished:

| Report | Original external SHA256 | Repository LF SHA256 |
|---|---|---|
| GATE_REVIEW.md | 8ed77ec00f801ccce1e55669eb26514f8d9c32b870f962360d0dbdc04ebb38cb | 1e0293ed171cf366f9ec9bf8cda95148a13ba82567462c3ece392b684e09a9c5 |
| INITIAL_REVIEW.md | 7cfb26ffa0f6a7ecc3ac70e9716b00f480d383f7f58fe366347588b745764098 | b7a35000dc79bef7f8c84adc0eb897f20a9cd7cb499d7f3f93fe77a85b5c2724 |
| FINAL_REVIEW.md | f4c093d8336431e0b3a657e012ffd3d3eb1e92363da720aadb517795f0e29e34 | 98af214b0ec4fac0c5c2e8137a14766d54c6534bc27602885eb30aba3ed92748 |

Initial test run failed collection because H contracts did not exist. Subsequent
three negative checks reproduced gate/version/total gaps; they passed after the
implementation. The deliberate missing-attestation case now uses model_validate
so strict static typing remains valid without weakening the command.

## Root validation and scope

- `pytest -q tests/unit -p no:cacheprovider --basetemp <fresh private task path>`:
  **PASS486 passed/7.00s**, exit0 after source fixes. An earlier attempt had8
  Windows temp-directory permission errors; rerun used a fresh bounded task path.
- Focused real PostgreSQL Configuration/G-ledger plus financial/config/G-contract
  unit tests: **PASS146 passed/27.55s**, exit0 before the final view-only revision
  fix. The updated view regression was rechecked by all-unit and independent
  runs; Configuration/SQL behavior did not change in the correction.
- `ruff check --no-cache .`: **PASS**, exit0.
- `ruff format --check --no-cache .`: **PASS200 files**, exit0.
- Strict configured mypy: **PASS200 source files**, exit0.
- `git diff --check` and base-to-HEAD source diff: **PASS**, exit0.

The private existing disposable PostgreSQL18.6 on127.0.0.1:51456 was the sole
root test target. Its DSN/password stayed outside Git and tool output. The
Windows sandbox cannot inspect the outside-owned postmaster; live status was
checked with the same explicit task permissions used to start it. Startup
capture holds inherited Windows handles until server shutdown; this is not a
test/runtime failure. Other PostgreSQL instances were untouched. At that
focused checkpoint the broader checks had not run; their actual final local
and exact-head CI outcomes are recorded below. Green planning CI alone is not
proof for the new source.

## Final broader checks and delivery

At unchanged reviewed API source843d0b3, local full suite:
**PASS906 passed/4 skipped/327.81s**, exit0. PostgreSQL and real
OIDC/Chromium/browser gates were mandatory. The4 skips are3 local Docker gates
and1 optional separate tenant-site integration. No H invoice workflow was
exercised; it remains unimplemented, and this is G/configuration regression plus
the new contract/arithmetic tests. Docker is NOT TESTED locally.

`npm run build`: PASS, exit0; existing Next16.3.7/Turbopack compiled the unchanged
web and18 static routes. A first attempt used an own junction to existing
dependencies and failed because Turbopack refuses an outside-root target. Only
that junction was removed nonrecursively; its G target was preserved. Unchanged
locked dependencies were then installed via `npm ci --offline --ignore-scripts`,
exit0, and the build passed. Neither package.json nor lockfiles nor web source
changed. This build does not add an invoice UI.

The owned PostgreSQL51456 was stopped after tests (pg_ctl stop exit0). Its
captured startup process then completed exit0. G checkout stays clean at5be6e7a;
owner/incoming checkouts retain their19/9 paths and original heads. No service
other than this owned test postmaster was started or stopped.

Planning PR13 is published at925ae02 with completed/success CI37525975637.
The initial source push was blocked by automatic review because it interpreted
the earlier authorization as documentation-only. The owner subsequently
explicitly approved pushing codex/package-h-invoices/da3966b and creating its
draft PR. This historical publication block is RESOLVED.

[Draft PR14](https://github.com/alexeyalexandrov2026-tech/GORGONA-Booking-Platform_new/pull/14)
is OPEN/unmerged, targets planning925ae02 and published foundation checkpoint
`da3966b571062654993f72c8f65c23ab2c843829`. Connected GitHub verified the exact
head and [CI37534227319](https://github.com/alexeyalexandrov2026-tech/GORGONA-Booking-Platform_new/actions/runs/37534227319):
completed/success, **909 passed/1 skipped/266.98s**. Mandatory PG, real browser
and all3 Docker gates PASS. Web unit68 passed/2.2s, typecheck/lint/format/build
and production image PASS; Ruff/format200 and strict mypy200 PASS.
The only skip is the optional separate tenant-site integration.

The [complete successor handoff](../../NEXT_AGENT_PACKAGE_H1_2026-10-06.md)
and [copyable prompt](../../NEXT_AGENT_PROMPT_H1_2026-10-06.md) were prepared
after this publication, without source changes. They record the next H1 SQL/API
slice, preservation inventory and test environment. Their docs-only successor
has its own HEAD/CI; inspect current PR14 rather than treating this stable
checkpoint's run as proof for a later revision. The ignored local
`handoff/package-h-foundation/FINAL_VALIDATION.md` records final delivery checks.

The prepublication doc checks passed11 changed Markdown docs and25 added/
changed local link targets. The handoff successor adds a prompt and fresh doc
checks; exact updated counts/outcomes are in its final delivery record.
Both checkpoints retain unchanged reviewed source,12 NOT TESTED H cases,
normalized independent-report hashes and clean diff checks. External helper
syntax is checked by AST without executing mutation scripts. Historical links
and anchors outside added/changed lines are not claimed as verified.

## Remaining work

H1 remains IN PROGRESS: forward0021 data/constraints, invoice draft/issue API,
atomic document→obligation→G posting, typed public ledger seam, actual source
lineage, explicit journal v2 negotiation/G-v1 preservation and minimal H command
recovery are not built. Then H2 reserves/payments, H3 credits/corrections and H4
admission/UI must be implemented and verified. H-01..H-12 remain NOT TESTED as
complete acceptance cases; do not promote FIN-03 or enable finance_documents
from these arithmetic/metadata tests.

No new dependency, external account access, funds sent, production migration,
deployment, Azure/DNS/billing/credential change or another-project modification.
Tools: existing Python/pytest/Pydantic/G money helpers, Git/PowerShell, locked
Ruff/mypy, disposable PostgreSQL, GitHub connector and independent agent under
the already-read Riqor evidence-engineering skill.
