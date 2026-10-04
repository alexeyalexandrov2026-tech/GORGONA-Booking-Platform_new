# GORGONA company groups acceptance — 2026-10-04

CORE-03 step C is technically verified on commit `6a81dfd736922c57f6ee6366f1b8cbcc0f9d5d9b`, branch `codex/universal-business-foundation`, repository `alexeyalexandrov2026-tech/GORGONA-Booking-Platform_new`. That commit carries the group implementation of `c9193b2` plus the decision-race fix. Later commits do not extend this acceptance to changed application code.

An organizer business creates a group, invites independent businesses, and each invited business accepts, declines or later leaves for itself; the organizer can end an invitation or membership, and a new invitation creates a new history row. Members see only their own membership. Membership is referenced by no authorization path: it opens no bookings, workspace, profile, legal entities or departments of another party, and `/v1/me` gains nothing from it. Consolidated group reports (stage 7), TMS dispatcher work and offline drafts are outside this increment. See [ADR-0018](../../../adr/0018-company-groups.md).

## Direct evidence

| Check | Exact outcome |
|---|---|
| Full GitHub PR CI | **PASS**: [run 37240229184](https://github.com/alexeyalexandrov2026-tech/GORGONA-Booking-Platform_new/actions/runs/37240229184), job `111547311138`, exact commit above; all steps succeeded (web build/unit, PostgreSQL 18, production image, Ruff format/check, mypy, pytest) |
| GitHub push CI | **PASS**: [run 37240226759](https://github.com/alexeyalexandrov2026-tech/GORGONA-Booking-Platform_new/actions/runs/37240226759), job `111547304072`, same commit |
| CI test counts | Not retrieved: job logs require authentication and `gh` was unavailable. Step conclusions were read through the public GitHub API |
| Earlier CI of `c9193b2` | **FAIL** in the `uv run pytest` step: PR run 37239459492, push run 37239457054. Cause found locally: when a removal committed before a concurrent accept, the accept lookup skipped the ended membership and returned 404 instead of a stale-revision 409. The lookup now takes the latest membership regardless of status |
| Regression for the race | `test_decision_after_a_committed_removal_is_a_stale_revision` failed before the fix and passes after it |
| Local full Python suite, PostgreSQL 18.6, required browsers | After the fix: **495 passed, 4 skipped**. Before the fix: 494 passed, 4 skipped, 319.01 s. Skips: three container gates without local Docker (covered by CI) and the optional external site gate, which is not a passed check |
| Groups PostgreSQL/API | **PASS: 6** — consent and history, no data access; parties, roles, states and accept/remove race; direct SQL; scope-policy damage fails readiness (both tables); decision after a committed removal |
| Browser harnesses | **PASS: 4** (company, branch, delegation, groups). Groups: a member joins after a lost response with the same key, receives 403 for the partner's bookings, creates its own group, invites and removes the partner, and leaves; mobile Axe WCAG 2 A/AA and no horizontal overflow; SQL confirms memberships and per-company audit |
| Web unit / static | Web unit **34**; typecheck, ESLint, Prettier, 14-page build PASS; Ruff and strict mypy PASS (143 source files) |
| Review | `/code-review high` in the same session: 4 findings; 1 fixed (invitation input after a conflict); 3 recorded as known limits in ADR-0018 (no membership paging, no invitation block list, duplicated command helpers) |

Tests and source: [contracts](../../../../api/tests/unit/test_group_contracts.py), [PostgreSQL/API](../../../../api/tests/integration/test_groups.py), [browser](../../../../web/tests/groups.spec.ts), [harness/SQL assertions](../../../../api/tests/integration/test_management_browser.py), [response boundaries](../../../../web/tests/management-contracts.spec.ts), [migration 0013](../../../../api/src/gorgona_booking/db/migrations/0013_business_groups.sql).

## Boundaries

The review ran in the same session as the implementation, not as a separate reviewer. Azure, staging, production migration, live providers, load and industry pilots were not verified. With steps A–C the CORE-03 organization foundation exists for current modules; the full CORE-03 scenario (dispatcher authority and offline draft synchronization) and TMS-02 remain NOT TESTED until those modules exist.
