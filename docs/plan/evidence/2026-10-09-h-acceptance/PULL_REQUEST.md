# Draft pull request text — package H audit and FIN-03 acceptance

Not opened as of 2026-10-09: GitHub sign-in is needed. Source
`codex/package-h-acceptance` (pushed at `ec39622`), target
`codex/package-h4-ui-admission`, the head of draft
[PR22](https://github.com/alexeyalexandrov2026-tech/GORGONA-Booking-Platform_new/pull/22).
Open once, as a draft. Do not merge or enable auto-merge.

## Title

Package H: independent audit and technical acceptance (FIN-03)

## Description

~~~markdown
## Summary

On top of H4 (#22, `319f144`). Draft: not for merge.

- `71359f9` — documents only. Independent audit of package H at `319f144`: full reproduction, mutation checks of the SQL guards, selective source review, eleven findings. Refreshes the stale entry documents for agents.
- `ec39622` — FIN-03 becomes `technically_verified` by the owner's decision of 2026-10-09, following the FIN-01 acceptance pattern (`a6f2d8b`). The readiness registry records code `319f144` and schema 31; tests move from the closed registry to the accepted one; ADR-0024 becomes Accepted.
- A documents-only successor records the publication and the CI result of `ec39622`.

Money code, migrations `0001`–`0031`, web sources, dependencies and lockfiles are unchanged.

## What changes

`finance_documents` becomes enableable. A company turns it on only through its own published configuration, together with `finance` and `counterparties`. Existing configurations are unchanged. FIN-02 stays `planned`.

Test-only readiness overrides are removed from the invoice and browser fixtures: H is now enabled by a real publication. The withdrawal tests stay: with readiness set back to `planned` the selection is refused with `MODULE_NOT_READY`.

## Evidence

- Exact-SHA CI of `319f144`: [push 37876007880](https://github.com/alexeyalexandrov2026-tech/GORGONA-Booking-Platform_new/actions/runs/37876007880) and [pull_request 37876031010](https://github.com/alexeyalexandrov2026-tech/GORGONA-Booking-Platform_new/actions/runs/37876031010), both success, including the production image build.
- Exact-SHA CI of the acceptance commit `ec39622`: [push 37887856597](https://github.com/alexeyalexandrov2026-tech/GORGONA-Booking-Platform_new/actions/runs/37887856597), success — web build and checks, PostgreSQL 18, production image build, Ruff format and lint, mypy, pytest.
- Independent local reproduction at `319f144`: **1231 passed / 4 skipped / 662.06 s** with mandatory PostgreSQL 18.6 and browser. Ruff, format and strict mypy clean on 230 files. Web typecheck, lint, format, 94 unit tests and build (19 routes) pass.
- Mutation checks: 4 of 4 weakened SQL guards are caught by existing tests — the `P + C + R <= A` cap, credit issue with an active reserve, the `P + C <= A` credit cap, and case folding of the external payment identity.
- Published migrations and lockfiles are unchanged across every head of the H stack; SHA-256 of `0030` and `0031` match the recorded values.
- Acceptance commit locally: red run **2 failed / 64 passed** before the registry change; afterwards unit **526 passed**, focused integration **147 passed**, full suite **1231 passed / 4 skipped / 666.05 s** without readiness overrides. Ruff, format and strict mypy clean on 230 files.

Records: `docs/plan/evidence/2026-10-09-h-acceptance-audit/AUDIT.md`, `docs/plan/evidence/2026-10-09-h-acceptance/ACCEPTANCE.md`. Handoff: `docs/plan/NEXT_AGENT_H_ACCEPTANCE_2026-10-09.md`.

## Audit findings

No P1. One P2 (A-01): the provider admission registry is writable when only `finance` is enabled, independent of the FIN-03 gate. Closed by owner decision without a code change. Ten P3: stale documents (fixed here), a route miscount in earlier evidence, and observations on reviewability, health checks, narrow SQL test coverage and one per-row read.

## Owner decisions recorded

1. FIN-03 → `technically_verified` (2026-10-09).
2. A-01: no code change; H4 is not deployed before H is accepted; the admission registry is accepted together with H.
3. ADR-0024 is Accepted in the scope implemented.
4. Accepted as implemented, without separate discussion: one person may prepare and approve a settlement; journal read schema 2 was extended in place; a release frees the whole unconfirmed remainder.

## Not tested / not done

- Independent check of the acceptance commit by someone other than its author: NOT DONE.
- CI of the documents-only successor and the `pull_request` run: inspect the current head.
- Test counts of CI run 37887856597 were not read: the job log needs GitHub sign-in.
- The audit is not independent for H2: the auditor wrote migrations `0022`–`0024`.
- Admission guards (`0031`) were not mutation-tested; source reading was selective.
- Local Docker gates (CI runs them), HawkScan, production data and migration, real providers and money, load.
- The description of #22 still says `CI_PENDING`; both runs finished with success.

## Status

Draft only. No merge, deployment, production migration, Azure, provider or money authorization.

🤖 Generated with [Claude Code](https://claude.com/claude-code)
~~~
