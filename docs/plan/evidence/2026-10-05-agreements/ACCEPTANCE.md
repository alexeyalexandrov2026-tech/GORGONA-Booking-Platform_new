# GORGONA E3 — contracts with counterparties, 2026-10-05

Implementation branch: `claude/package-e3-agreements`, based on accepted E2
`c5a3908` (`claude/package-e2-documents`). Separate worktree
`C:\Users\alexa\Documents\ChatGPT\gorgona-e2-documents`; the owner checkout, other
agents' worktrees and test cluster 51454 were not touched. Local tests used the
disposable PostgreSQL 18.6 cluster 127.0.0.1:51455 only; its DSN stayed in the
child process environment. An earlier interrupted session had left the E3 code
uncommitted in this worktree; it was verified, changed for the owner's decisions
and reviewed before the first commit.

**Gate: contracts implemented inside the already `technically_verified`
`counterparties` module.** Code `3044f973e4404bb1eb9cba4728fccbae402e142d` passed
its exact-SHA push CI ([run 37389126365](https://github.com/alexeyalexandrov2026-tech/GORGONA-Booking-Platform_new/actions/runs/37389126365), job `api` 112029736295: success, all 17 executed steps successful, with mandatory PostgreSQL, browser and container gates). No module is promoted; registry version
stays 1, and every business still enables `counterparties` only by publishing a
configuration. The acceptance SHA needs its own CI; never transfer a code CI
result to another SHA.

## Owner decisions applied (2026-10-05)

1. A termination acts on the latest agreed (executed) version, never on an
   unsigned amendment draft. An open amendment draft stays in the history,
   reported `abandoned` (closed by the termination); the audit records
   `terminates_revision` and `abandoned_draft_revision`.
2. The termination date (`terminated_on`) is the day it takes effect and may be in
   the future; the agreed version stays in force until then. Signing dates still
   cannot be in the future (latest calendar day on Earth, UTC+14).

## Implemented boundary

Migration `0017_agreements.sql`: `agreements` (counterparty, optional own legal
entity; identity immutable; a deferred constraint trigger requires revision 1 in
the same transaction) and `agreement_versions` (insert-only; draft → draft |
agreed; agreed → draft (amendment) | terminated; draft → terminated only after an
earlier agreed version). SQL enforces contiguous revisions, attested fields per
state, agreeing exactly as drafted, a termination that names the latest agreed
revision (`terminates_revision`, self-referencing key) and repeats it exactly, no
future signing dates, `terminated_on ≥ signed_on`, an active card for new
contracts, drafts and agreements (termination stays possible for archived or
merged cards) and tenant-scoped document and legal-entity references. FORCE RLS,
tenant isolation, restrictive company-only scope, column-limited INSERT/SELECT,
update/delete refused, two `counterparties` gates; guard 40 definitions and twelve
optional gates; branch-scope marker 17.

API (`api/agreements.py`, base `/v1/businesses/{business_id}`):
`counterparties/{id}/agreements` (keyset; includes duplicates merged into the
card), `agreements/{id}` (GET by revision; PUT draft with expected revision),
`agreements/{id}/versions`, `agreements/{id}/agree`, `agreements/{id}/terminate`.
Views expose `in_force_revision` and `terminates_revision`; list rows carry the
agreed version in force (`in_force`); history rows mark the abandoned draft.
Errors: `AGREEMENT_STATE_INVALID` 409, `COUNTERPARTY_STATE_INVALID` 409,
`ATTESTATION_REQUIRED` 422, `AGREEMENT_DATE_INVALID` 422, `AGREEMENT_INVALID` 422.
Receipts hold `{agreement_id, revision}`; audit details hold revisions, the
counterparty id, flags and dates only — no titles, numbers or summaries.

Web: "Contracts" panel on the counterparty card — drafts, attested agreement,
amendments, termination with a possibly future effective date. The agreed version
in force is always shown (also during an amendment draft and until a termination
takes effect); the status follows the viewer's calendar day, as document validity
does. Agreed/terminated appear only from a server answer; agreeing is disabled
while the draft form has unsaved edits; a lost response is retried with the same
key and survives card edits; contracts listed through a merged duplicate are
read-only there except termination; older history pages load on request.

## Direct evidence

| Check | Exact observed outcome |
|---|---|
| Uncommitted code from the interrupted session | PASS: unit + integration 31 passed, 8.90 s |
| Owner decisions, red before the change | Expected FAIL: future termination 422 `AGREEMENT_DATE_INVALID`; termination during an amendment draft 409 `AGREEMENT_STATE_INVALID`; the two new tests failed (`in_force_revision` missing; `terminates_revision` column missing) |
| Agreements after the change | PASS: 33 passed, 10.77 s |
| Browser harness, first run | FAIL: the in-force block showed the termination revision 6 instead of agreed version 4 — fixed (the version named by `in_force_revision` is loaded when it differs) |
| Browser harness after the fix | PASS: pytest harness 1 passed, 11.98 s; Playwright desktop + mobile 2 passed, 7.7 s; axe clean; SQL checks of versions, `terminates_revision`, audit and receipts |
| Full local suite before review | PASS: 762 passed / 4 skipped / 279.39 s, exit 0 |
| Independent read-only review | No high findings; 2 medium + 7 low confirmed — all fixed below |
| Review regressions, red before the fixes | Expected FAIL: list row had no `in_force` (KeyError); C1 control in a title answered 409 `CONFLICT` instead of 422 |
| Agreements after review fixes | PASS: unit + integration 38 passed, 9.27 s |
| Web | PASS: typecheck, ESLint, Prettier, 61 unit tests, production export |
| Python static | PASS: Ruff check/format, strict mypy 180 files; `git diff --check` |
| Final full local suite (code SHA) | PASS: **767 passed / 4 skipped / 276.37 s**, exit 0; mandatory PostgreSQL 18.6 and browsers; skips: 3 Docker container gates (required in CI) and the external tenant-site gate |
| Exact code push CI `3044f97` | PASS: [run 37389126365](https://github.com/alexeyalexandrov2026-tech/GORGONA-Booking-Platform_new/actions/runs/37389126365), job 112029736295, conclusion success; test counts are in the authenticated job log |

Review fixes: list rows carry the agreed version in force, so an open amendment
never describes the unsigned draft (or its term) as the contract; a new amendment
starts without the agreed version's signed copy; only the draft immediately
before a termination is `abandoned`; every save of an open amendment is audited as
an amendment; refused text (including C1 controls) answers 422; a contract cannot
exist without its first version (runtime role, deferred constraint trigger);
merged-family contracts are read-only from the surviving card; the panel stays
mounted across card edits so a pending command keeps its key; older history pages
load. The archive-versus-amendment race test now checks the stored outcome; an
archived card's contract terminates through the API. The web helper tests
(`canDraftOrAgree`, `draftDocument`, list schema) were written together with those
helpers.

## Limitations and NOT TESTED

- A recorded termination is final: withdrawing a scheduled termination needs a
  future version state. A company-wide contract has no single time zone, so
  "in force" versus "terminated" on the effective day follows the viewer's date.
  "In force" is shown before `effective_from` as well (the term start is shown).
- The signed copy is an optional reference to one saved document version; the UI
  does not attach or change it (API only). No electronic signature, templates,
  consent, import, erasure or per-contract access; contracts share the counterparty
  permissions (owner/manager of the whole company only).
- The panel keeps a pending command across card edits, not across leaving the
  card or reloading the page. List order follows identifiers, not dates.
- Guard limits as in E1/E2: immutability triggers and extra permissive policies
  are not covered; author columns are not checked against membership; one-level
  merge family.
- Production, providers, Azure, load/restore, pilots and manual screen-reader
  acceptance: NOT TESTED. No merge, deployment or production migration.
