# Handoff — package O (construction, BUILD-01) after O6b; next is O7 screens (2026-11-02)

Written by the agent that built O3b-O6b. Read this whole file and the O6 handoff
([NEXT_AGENT_PACKAGE_O6_2026-11-02.md](NEXT_AGENT_PACKAGE_O6_2026-11-02.md)) before any action.

## 1. Where things stand

The owner delegated package O («Делай как считаешь нужным я доверяю тебе») and said «Продолжай дальше
по проекту, по плану». That covers designing, building and pushing each slice branch **for CI only,
without a PR**. It does not cover PRs, merges, `main`, readiness, enabling modules, deploy, Azure,
production migrations or live providers.

| Slice | Branch | Design | Code | Docs | Migration | CI |
|---|---|---|---|---|---|---|
| O6a acceptance, retainage release | `codex/package-o6a-acceptance` | `a756265` | `c06ec73` | `04d0329` | 0094 | run 41490808670 success |
| O6b warranty claims, repair cost, reconciliation | `codex/package-o6b-reconciliation` | `381deeb` | `44736e8` | the docs commit with this file | 0095 | pushed for CI with this commit; check it first |

Each slice branch starts from the previous slice's docs commit. Next migration: **0096**; migrations
0001-0095 are immutable. Readiness: `construction` is implemented and **not enableable**.

## 2. Heavy runs on the VM

The owner asked that dev runs and gates run on the Google Cloud VM `gorgona-dev`, not on the laptop:
`ssh gorgona-dev`, repo `~/gorgona` (detached HEAD), Python `~/gorgona/api/.venv/bin/python`, run
folders under `~/gba-runs/`, long jobs with nohup. It powers off after 60 minutes idle; start it with
`gcloud compute instances start gorgona-dev --zone us-central1-a --project gorgona-one-ai`. Copy new
files in by scp, check them equal by sha256, copy run folders back without the database data, then
write the record locally (it hashes the local tree).

## 3. Next: O7 construction screens

Screens for projects, budget, cost links, schedule and daily reports, quality items, pay
applications, acceptances, warranty claims and the reconciliation view, on the existing routes.
Real browser on desktop and mobile with axe, as earlier screen slices did; failing tests first.
Then O8 acceptance of BUILD-01 (owner's word for readiness).

Known open test defect: `test_i4_browser` fails now and then in the full suite and passes alone
(separate task).
