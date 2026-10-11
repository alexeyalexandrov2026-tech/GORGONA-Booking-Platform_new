# I4 validation — Schedule, My shifts and Timesheets screens (2026-10-11)

Slice I4 of package I (WORK-01). Local branch `codex/package-i4-workforce-screens`
on top of the I4 handoff `d22b61cf53612ab85c157c00ecd75fd1630ba1c2`
(`codex/package-i3-timesheets`; I3 code `ec9524a`). Nothing was pushed and no PR
was opened. Exact commands and first failures are in [COMMANDS.md](COMMANDS.md);
the hashes of the reviewed sources are in [SOURCE_SHA256.md](SOURCE_SHA256.md).

Readiness is unchanged: WORK-01 and CORE-04 stay `planned`, and the `workforce`
module stays closed outside test fixtures. Migrations `0001`–`0034` are untouched
and no new migration was needed.

Later on 2026-10-11 the owner decided the first choice listed below: it is now a
branch setting, with migration `0035`. See
[the setting's record](../2026-10-11-i4-shift-visibility/VALIDATION.md). The text
below describes the tree at `f4a7395`.

## What was built

| Part | Files |
|---|---|
| Three screens, desktop and phone | `web/app/schedule`, `web/app/my-shifts`, `web/app/timesheets`, `web/components/schedule.tsx`, `my-shifts.tsx`, `timesheets.tsx`, `workforce-shared.tsx`, `web/app/workforce.css`, three links in `management-layout.tsx` |
| Typed contracts, client, recovery | `web/lib/workforce-contracts.ts`, `workforce-api.ts`, `workforce-recovery.ts`, one branch in `management-contracts.ts` |
| Minimal API support for the screens | `api/src/gorgona_booking/api/workforce_desk.py`, `business/workforce_desk.py`, `business/workforce_desk_contracts.py`, one line in `api/app.py` |
| Tests | `api/tests/integration/test_workforce_desk.py`, `test_workforce_desk_races.py`, `api/tests/unit/test_workforce_desk_contracts.py`, `api/tests/integration/test_i4_browser.py`, `web/tests/workforce-contracts.spec.ts`, `web/tests/workforce.spec.ts` |

**Schedule** (owner, manager, also of one branch): shifts of a location for a
week, create and edit, draft, publish, cancel, assign and unassign, every version
of a shift with its assignment; staff with a "add to the schedule" action; the
company skills catalogue (written only with company-wide access); granting and
revoking a skill with its history; change requests with approve and decline, the
applied result and the history of each request.

**My shifts** (every own member): own shifts for four weeks, open shifts of the
home branch, handover and swap with a choice of a home colleague and of their
shift, a request for an open shift with an explicit confirmation, accept, decline,
withdraw and the history of each request.

**Timesheets** (every own member; decisions for owner and manager): clock in and
out, breaks, a correction with a reason and breaks, every version, the pending
version shown apart from the one in effect, the owner's approval of their own time
marked, work outside the schedule marked, approve and decline with a reason.

## Real API gaps and the minimal extensions

The handoff allows an extension only for a real gap, after a failing test. Five
gaps were found; each has a red test first (see COMMANDS.md).

| Gap | Why a screen cannot work without it | Extension |
|---|---|---|
| A person's own staff profile | Clock-in and an open-shift request need `staff_profile_id`; `GET /staff` needs `workforce.read`, so a new employee could not learn their own id | `GET /workforce/desk` (`workforce.self`): own profile and whether new actions are open |
| Whether new actions are open | A closed module was visible only as a refused write | the same `/desk`: `open`, `module_disabled`, `not_accepted` |
| Names | `ProfileView` has identifiers only; `GET /salons/{id}/members` refuses a branch manager | `GET /workforce/directory` (`workforce.read`): active members with profile and home, limited to the manager's branch |
| The other side of a swap | A swap needs the colleague's shift id and version; an employee could list only own and open shifts | `GET /workforce/colleagues/{profile_id}/shifts` (`workforce.self`): published assigned shifts of a home-branch colleague |
| The outcome of a sent command | The API answered only to a resent body; a screen that reloaded has no body and must not keep one | `POST /workforce/commands/{key}/resolve` and `/cancel` (`workforce.self`) |

All five are reads, except `cancel`, which writes one marker into the existing
`gba.idempotency_keys` row space. They use the same `_access` gate as every other
workforce route: tenant isolation, branch scope, no delegation, no platform
support, and 503 when the SQL guards are damaged.

Choices made here that the owner may change:

1. **An employee sees the published shifts of colleagues of the home branch.**
   Position, time and required skills, 62 days at most. Without it a swap cannot
   be proposed from a screen. Another branch stays hidden (404).
2. **A branch manager sees members of that branch only**, and may add to the
   schedule only a member whose membership is in that branch.

## Recovery after a lost answer

1. Before a command is sent, the screen saves in `sessionStorage` only: the
   idempotency key, the operation, the subject id, the version the command should
   produce, the actor and the business. No reason, name, position, time or body.
2. An answer that did not arrive, a broken answer or a 5xx leaves the result
   unknown. The screen blocks new actions and asks the server by the original key.
3. `resolve` reads the receipt of that key for that actor and operation:
   `committed`, `unresolved` or `cancelled`. A reference to another subject or
   version is refused (422).
4. While the page still holds the body, an unresolved command may be sent again
   under the same key. After a reload the body is gone; the person may only
   discard it.
5. `cancel` claims the key with a marker in the shared receipt table. The claim
   waits for a command still running under that key. A cancelled key can never
   commit: the original command then gets 422 `IDEMPOTENCY_KEY_REUSED`. Only after
   that does the person start again with a new key.
6. The saved record is bound to the actor and the business. Another person in the
   same tab, or the same person in another business, is shown nothing.

A success message is shown only after the lists have been reloaded. The first
browser run found the opposite order: the message appeared while the list still
showed the previous version (FAIL in COMMANDS.md), and it was corrected.

## Results

| Check | Result |
|---|---|
| New API tests, before the routes existed | **FAIL (expected red):** 7 failed / 6.56 s |
| New API and contract tests | **PASS:** 10 passed / 8.73 s |
| Web unit, before the recovery module existed | **FAIL (expected red):** the spec could not be loaded |
| Web unit for the new contracts and recovery | **PASS:** 7 passed |
| Real browser, desktop and phone, three phases | **PASS:** 1 passed / 92.97 s on the final tree (closed 2, enabled 2, switched off 2 Playwright tests; database counts asserted); four earlier runs failed and are listed in COMMANDS.md |
| Complete pytest, PostgreSQL and browser required | **PASS:** 1486 passed / 4 skipped / 907.37 s on `f4a7395` (first complete run on `7442ff7`: 1484 passed / 4 skipped / 931.53 s) |
| Races of cancel against the command itself | **PASS:** 2, each with an observed wait in `pg_locks` |
| Ruff; format; mypy | **PASS:** exit 0; format 261 files; mypy 261 files |
| Web typecheck, lint, format, unit, build | **PASS:** exit 0 each; unit 101 passed / 1.4 s; build 23 static pages |
| Production `npm audit` | **FAIL:** 2 high nodes, `next` and `source-map-js`; inherited, not addressed |
| HawkScan | **NOT TESTED:** no scanner runtime or key on this machine |
| Independent review by a non-author | **NOT DONE.** The author re-read the diff ([AUTHOR_REVIEW.md](AUTHOR_REVIEW.md)); that is not an independent review |
| Exact-commit CI | **NOT TESTED:** the branch is local |
| Containers, optional external tenant site | **NOT TESTED:** skipped as in I1–I3 |
| Load, soak, deployment, production | **NOT TESTED** |

## What the browser test proves

`api/tests/integration/test_i4_browser.py` starts the real API on PostgreSQL 18,
a FAKE loopback identity provider and the built web export, then runs
`web/tests/workforce.spec.ts` on desktop Chromium and on an emulated phone. Nothing
in the browser is mocked; requests are only delayed or dropped by the test where a
lost answer is the subject.

| Requirement of the handoff | Where it is checked |
|---|---|
| 1. Profiles, skills, schedule, versions, publish, cancel, assignments and their history | Owner: adds a member to the schedule, creates a skill, grants it, creates four shifts, cancels a draft and reads two versions; manager reads the assignment history after a handover |
| 2. Own shifts, handover, swap, open shift, colleagues, consent, withdraw and decline, manager approval with a result | Employee proposes a handover, a swap with the colleague's shift, an open-shift request with confirmation, withdraws one request; the colleague accepts two and declines one; the branch manager approves three and sees "is now version 2" |
| 3. Clock, breaks, close, correction with a reason, decisions, full history, pending apart from effective, owner self-approval, outside the schedule | Employee: clock in, break, clock out, correction; "In effect: approved version 5" beside "Version 6 is a pending correction"; decline with a reason; seven versions in the history; the owner approves own time and the mark is shown; "Outside the schedule" is shown |
| 4. Loading, error, empty lists, version conflict, refused rights, closed module | Empty lists in the closed phase; a refused assignment without the skill; a stale edit after the same shift changed in a second tab; `/schedule/` refused to an employee; six management reads answer 403 to the employee's token; a company skill write answers 403 to a branch manager; closed and switched-off phases |
| 5. Lost answer, original key, no double effect, reload, change of person and business, no leak | Three lost answers: the owner's own-time approval (business changed and back), the employee's handover (another person signs in, then the employee after a full reload), and two dropped commands (one sent again under the same key, one discarded). The saved record has six identifier fields and no name, reason, position or body. The database holds one handover per project and two cancelled commands in total |
| 6. Desktop and phone, keyboard and focus, axe, rights of employee, branch manager and owner | Both Playwright projects; Enter opens a form, focus lands on its heading, Escape closes it and focus returns to the control; axe reports no violations on sixteen screen states per project (3 closed, 10 enabled, 3 switched off); no sideways scroll on six of them; the three roles as above |

The closed path uses the registry as it is (`workforce` is `planned`, so the
screens show "not available yet" and every new action is disabled). Only the
fixture then opens readiness. The switched-off path publishes a configuration
without the module: history stays readable and an open time record is closed from
the screen.

## Limits

- Server permissions stay the source of truth. A hidden button is a convenience.
- The directory, skills and lists are read up to 1000 records; a note is shown
  beyond that. No search or filtering by person.
- Times are entered and shown in the timezone of the record's location, to the
  minute. A local time that does not exist or occurs twice at a clock change is
  refused by the form with an explanation.
- A shift's history shows the latest 20 versions.
- The screens are in English, like the rest of the management area.
- No payroll, labour-law rules, geolocation or PIN, notifications, automatic
  scheduling or time off: outside package I.
- The inherited production `npm audit` finding is not addressed here.
- A FAKE identity provider is a test fixture only. Its logout now also accepts
  the application's real `/auth/logout/` return address, which the fixture
  refused before; no product code changed for that.
