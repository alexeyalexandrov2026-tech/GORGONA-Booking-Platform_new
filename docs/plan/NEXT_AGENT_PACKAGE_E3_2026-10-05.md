# GORGONA — E3 continuation (contracts), 2026-10-05

Read [AGENTS](../../AGENTS.md), [master plan](GORGONA_MASTER_PLAN.md),
[registry](GORGONA_IMPLEMENTATION_STATUS.md), [ADR-0020](../adr/0020-counterparties-documents-and-contracts.md)
(section "E3 implementation"), [E3 evidence](evidence/2026-10-05-agreements/ACCEPTANCE.md)
and the [E2 handoff](NEXT_AGENT_PACKAGE_E2_2026-10-05.md).

## Current source

Branch `claude/package-e3-agreements` in worktree
`C:\Users\alexa\Documents\ChatGPT\gorgona-e2-documents`, based on accepted E2
`c5a3908`. Code `3044f97` (contracts, migration 0017) passed its exact push CI run 37389126365;
this acceptance commit records the evidence and needs its own CI. Nothing is
merged. Fetch and check the exact HEAD, PR and CI before editing — acceptance is
specific to a SHA.

Pull requests: no GitHub CLI, the GitKraken connector was not signed in and the
Chrome extension was not connected in this session, so **no PR was opened** for
E2 or E3. Ready texts are kept locally in the gitignored `handoff/` folder of this
worktree (`PR_E2_DOCUMENTS.md`, `PR_E3_AGREEMENTS.md`) and in the owner's
`OneDrive\Desktop\GORGONA_HANDOFF_2026-10-05` folder. Open them as drafts:
`claude/package-e2-documents` → `codex/package-e2-file-validation` (stacked on
draft PR #8), then `claude/package-e3-agreements` → `claude/package-e2-documents`.
PR CI then runs on each head SHA.

The owner checkout `C:\Users\alexa\Documents\ChatGPT\Gorgona Booking` keeps
uncommitted work: no reset/clean/restore/overwrite/merge there. Each agent uses
its own worktree/branch and its own disposable cluster; only one executor runs
the PostgreSQL suite at a time. This session used cluster 127.0.0.1:51455
(`%LOCALAPPDATA%\GorgonaBookingTests\claude-cluster`, runner
`handoff/run_pytest_51455.py`, gitignored); 51454 belongs to another agent.

## What E3 delivers

Migration 0017 (`agreements`, `agreement_versions`; insert-only, FORCE RLS,
restrictive company-only scope, two `counterparties` gates, first version required
before commit), `business/agreement_contracts.py`, `business/agreements.py`,
`api/agreements.py`, guard 40 definitions / twelve gates, contracts panel on the
counterparty card, integration/unit/web/browser tests. Owner decisions of
2026-10-05: termination ends the latest agreed version (an open amendment draft
is abandoned, never signed by it) and may take effect on a future date. The
`counterparties` module stays `technically_verified`; registry version 1.

## Next steps, in order

1. Check the acceptance SHA's own CI; open both draft PRs (texts above) and record
   their PR CI. If red: cause, red→green regression, new SHA.
2. CORE-04 (package F, shared resource occupancy, master plan §12.2.1): the owner
   asked for **documents only first** — a package plan and ADR-0022 (Proposed) on a
   separate branch from this acceptance SHA, for the owner's approval before any
   code. No separate resource store and no double write without one locking
   mechanism.
3. Afterwards stage-2+ packages per the master plan.

## Known limitations (do not silently "fix" by relaxing)

See evidence: a recorded termination is final; status by the viewer's calendar
day; signed-copy reference is API-only; pending command survives card edits but
not leaving the card; guard does not cover immutability triggers or extra
permissive policies; author columns unchecked; one-level merge family. No
production, provider, cloud, deploy, merge or production migration without the
owner's explicit authorization.
