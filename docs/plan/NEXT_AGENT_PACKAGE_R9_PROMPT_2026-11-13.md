# Ready-to-paste prompt — package R, slice R9 (acceptance of RENT-01), work on the server

Continue GORGONA Booking. **We work on the server, not locally** (owner, 2026-11-13: «Нет, мы работаем на сервере. Мы
не работаем локально.»).
- All edits, test runs, records, commits and pushes happen on the Google Cloud VM `gorgona-dev`, in `~/gorgona`, on the
  branch `codex/package-r9-rental-acceptance`.
- From the laptop use only `gcloud`, `ssh`, `scp` and `curl`. Do not edit or run anything in the old laptop worktree.

The owner's goal is production for **all 39 directions of the master plan at once**; never plan or estimate a
one-industry launch. Package R (rental, RENT-01) is build order. The owner delegated packages O and R fully («Делай
как считаешь нужным я доверяю тебе»): design, build and push each slice branch for CI without a PR. Nothing else is
delegated.

1. Read `docs/plan/NEXT_AGENT_PACKAGE_R9_2026-11-13.md` whole. It has:
   - how to start and reach the VM;
   - the keep-alive SSH session;
   - how to edit files there;
   - the test harness;
   - git, push and CI;
   - the exact state of R9 and its next steps;
   - the draft acceptance record;
   - the traps.

   You can read it on GitHub on that branch, or on the VM once it runs.
2. Then read:
   - `docs/plan/PACKAGE_R9_DESIGN_2026-11-13.md`;
   - `docs/plan/PACKAGE_RENT_PLAN_2026-11-03.md`;
   - `~/gba-runs/package-r9-20261113-a323b58/STATE.md` on the VM.
3. If the VM is stopped, ask the owner in one short Russian sentence for the word to start it (every start has needed
   it), and record the word in `STATE.md`. Start it, keep an SSH session open the whole time (the VM stops after
   60 idle minutes), and check that `git status` on the VM shows exactly the two uncommitted R9 test files with the
   checksums in `wip/sha256.txt`.
4. Continue R9 from section 4.3 of the handoff:
   1. the R-09 code fix;
   2. dev runs, the gates on the VM and the source-bound record;
   3. the code and docs commits;
   4. the push for CI without a PR.

   Then report to the owner in Russian and ask for consent to the one independent review of package R.

Hard rules:

- No PR, merge, `main`, readiness, enabling a module, deploy, Azure, production migration or live provider without
  the owner's separate direct word.
- No rebase, amend, reset, clean, force-push, CodeRabbit or bare `git stash`. Migrations 0001-0107 are immutable;
  the next is 0108.
- One executor and one disposable PostgreSQL 18 cluster per run; never ports 51454, 51458, 51474, 51511 or 49981.
- Failing tests first. A race test only with an observed `pg_locks` wait. No edits to `api/`, `web/` or
  `docs/runbooks/` while tests run.
- Record every slip in `STATE.md` and the record («Не скрывай ни одного сбоя»).
- Extra agents only with the owner's consent.
- Never touch `C:/Users/alexa/Documents/ChatGPT/Gorgona Booking` or the worktree `package-l7b2b`.
- Write to the owner in Russian, simply; the owner is they/them. Report PASS/FAIL/BLOCKED/NOT TESTED with exact
  numbers.
- End every commit message with `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.
