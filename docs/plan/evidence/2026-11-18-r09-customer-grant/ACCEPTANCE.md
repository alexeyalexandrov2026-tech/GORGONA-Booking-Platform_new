# R-09 customer answers through a rental grant on gorgona-dev

**R-09 PASS on gorgona-dev and in GitHub Actions.** A customer company answers on the platform only
through a live grant with `rental.customer_answer`. When the business records an answer or a report
itself, it records the source (paper, email, phone) and the person's name. This closes the gap left in
the [R9 acceptance record](../2026-11-13-r9-acceptance/ACCEPTANCE.md), where R-09 was PARTIAL because
customer responses through a rental grant were unimplemented. Rental stays registered as `implemented`;
readiness and enablement require an owner decision. The production launch scope covers all 39 industry
directions. [Package R plan](../../PACKAGE_RENT_PLAN_2026-11-03.md) · [Checks](CHECKS.json)

Plan wording for R-09: "Customers on the platform answer only through a grant; otherwise the source is
recorded."

## Cases and evidence

| Case | Result | Evidence | Coverage limits |
|---|---|---|---|
| Customer company of a booking | PASS | Migration 0122. A company-wide manager links the booking's customer to a business. The link is versioned, append-only and retry-safe; a reused key with another body gets 422 `IDEMPOTENCY_KEY_REUSED`. A branch-limited manager and the front desk get 403. `test_r09_rental_customer_company.py` (3 tests). | Only company-wide managers manage the link. |
| Proposal acceptance through a grant | PASS | Migration 0123. The delegate accepts the exact base quote with its review hash. Another binding, another branch, an expired or revoked grant are refused. The database refuses a platform acceptance recorded for a user who is not a current delegate of the grant. `test_r09_rental_customer_answer.py` (3 tests), browser `test_r09_rental_proposal_browser.py` on desktop and mobile. | |
| Agreement changes through a grant | PASS | Migration 0124. The customer accepts only the latest issued terms; a period change obeys live occupancy and moves the hold; an offline version supersedes an unanswered offer. `test_r09_rental_customer_changes.py` (3 tests), browser `test_r09_rental_change_offer_browser.py` on desktop and mobile. | |
| Problem reports | PASS | Migration 0125. A delegate reports a breakdown, damage, accident or other problem through the live grant and sees only the company's own reports. Staff record reports that came by phone, email or paper with the reporter's name. Reports are insert-only and numbered per booking; a cancelled booking or a future moment is refused; the rental module gate holds. `test_r09_rental_problem_reports.py` (3 tests), browser `test_r09_rental_problem_reports_browser.py` on desktop and mobile, including a lost reply retried with the same key. | No photo attachments and no notification to staff for new reports. The customer page shows times in the delegate's own time zone. |
| Staff-recorded sources | PASS | Unchanged from R4b and R9: staff record Paper or Email with name and time for acceptances and changes; `platform` is refused on staff routes. | |

### Database rechecks

The 0123 and 0125 guards run as the caller, like the construction guard (0119). They bind each platform
row to the active tenant, the recorded user and the transaction time, and require the booking's current
customer binding under the caller's row security. In company-wide sessions they also recheck the live
grant, its permission and the current delegate. In a branch-scoped session the grant tables are not
readable (0012); there authorization has already locked and checked the grant in the same transaction,
and row security shows only bookings of the grant's branch.

## Commits

| Commit | Tree | Content | GitHub Actions |
|---|---|---|---|
| `19a285d` | `50e2792` | Customer company, proposal acceptance, change offers and their screens (0122–0124) | [Failure](https://github.com/alexeyalexandrov2026-tech/GORGONA-Booking-Platform_new/actions/runs/44378780501): 12 failed, 2948 passed, 1 skipped |
| `2488ef9` | `34a9db4` | Problem reports API (0125) | [Failure](https://github.com/alexeyalexandrov2026-tech/GORGONA-Booking-Platform_new/actions/runs/44384201291): 13 failed, 2950 passed, 1 skipped |
| `efbcc1b` | `9ead801` | Problem report screens for the business and the customer | Not run separately; included in the next row |
| `1ea7008` | `1cab88d` | Guards without SECURITY DEFINER; the boundary test restores R-09 policies | [Success](https://github.com/alexeyalexandrov2026-tech/GORGONA-Booking-Platform_new/actions/runs/44413721541) on branch `codex/package-r09-ci-fixes` |

The test counts of the successful run were not recorded: downloading its log failed.

## Why the first two CI runs failed

The VM had run only the R-09 test files, and they passed there. GitHub CI runs the full suite, which
exposed two problems:

1. `test_migration_files` forbids `SECURITY DEFINER` in any migration; 0123 used it.
2. `test_location_access` drops `gba.current_location_id()` with CASCADE and then rebuilds only the
   policies it lists, which stopped at 0118. Every later R-09 test in the same session ran with no
   tenant policy on `rental_customer_companies`, so every insert was refused.

The full suite on the VM at `efbcc1b` reproduced both (14 failed). The fix rewrote the 0123 and 0125
guards and made the boundary test re-create the 0122 and 0124 tenant policies and the 0125 branch scope.

## Checks on gorgona-dev

| Run | Tree | Result |
|---|---|---|
| Codex R-09 API and screens (from the handoff) | `50e2792` | R09 45 passed, 1 skipped; R09_UI 38 passed, 2 skipped |
| Problem reports API: before the fix | — | 4 expected failures (missing routes and the delegation contract) |
| Problem reports API: after the fix | `34a9db4` | ruff, mypy; 41 of 41 API and PostgreSQL tests |
| Problem screens: first run | `cb977f0` | Web checks passed; ruff found one docstring line of 101 characters |
| Problem screens: second run | `9ead801` | Contract test failed before the change as expected; typecheck, lint, format, unit, build; ruff, mypy; 27 of 27 API tests; 3 of 3 Chromium scenarios on desktop and mobile |
| Full suite at `efbcc1b` | `9ead801` | 14 failed, 2947 passed, 4 skipped: reproduced CI |
| CI fix, first attempt | `3584001` | 35 of 36 in the ordered short run: the unnamed-actor database check no longer raised |
| CI fix | `1cab88d` | Ordered short run 36 of 36; full suite 2960 passed, 4 skipped, 1 failed: the salon catalog browser test on mobile timed out after 5 s waiting for "Stages saved"; it passed twice when rerun alone on the same tree |

The four VM skips are three container tests and the external tenant-site test. PostgreSQL 18.7 on the
VM; Chromium was required.

## Open items

- Readiness: RENT-01 stays `planned` in the readiness registry until the owner decides.
- Problem reports have no attachments and no staff notification.
- R-10 keeps its keyboard coverage limit from the R9 record.
