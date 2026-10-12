# Independent review of I4 and the shift-visibility setting — 2026-10-11

The reviewer did not write this code. Product code, tests and migrations were not
changed; the only change in Git is this file. The request reviewed against is the
"Готовый запрос независимому рецензенту" of the
[handoff](../../NEXT_AGENT_PACKAGE_I_REVIEW_2026-10-11.md), six points.

## What was reviewed

| Field | Value |
|---|---|
| Author's branch | `codex/package-i4-workforce-screens`, head `a8063804aec2fb18cab62c2157e3cea690e9c6ef` |
| Published head | `git ls-remote --heads origin codex/package-i4-workforce-screens` answers the same commit |
| Final code commit | `419eda8097554c024cb76cde38fe901c386a5e29`; `git diff --name-only 419eda8..a806380` lists 12 documentation files only |
| Base of I4 | `d22b61cf53612ab85c157c00ecd75fd1630ba1c2` |
| Review branch | `codex/package-i4-review`, own worktree `gorgona-package-i4-review`, created from `a806380` |
| Cluster | the reviewer's own PostgreSQL 18.6, `i4-review-20261011`, 127.0.0.1:51511, started with `-o "-p 51511 -c max_connections=400 -c listen_addresses=127.0.0.1"`; stopped after the review |
| Tools | Python 3.14.6, Node 24.18.0, the author's virtual environment and the cached Playwright browsers |

**SHA256.** Every row of both tables was recomputed from the blob
(`git show <commit>:<path> | sha256sum`):

| Table | Commit | Rows | Match | File list against the diff |
|---|---|---|---|---|
| [I4](../2026-10-11-i4-workforce-screens/SOURCE_SHA256.md) | `f4a7395` | 25 | 25 | equal to the 25 non-document files of `d22b61c..f4a7395` |
| [Setting](SOURCE_SHA256.md) | `419eda8` | 19 | 19 | equal to the 19 non-document files of `5f0e58f..419eda8` |

## Summary

No finding is critical or high. No leak between companies, no leak between
branches through the new routes, no way for a delegate or platform support to
reach them, and no double effect were found. Two findings are medium: the hidden
setting can be read around with the swap command and the request read, and the
"Outside the schedule" mark follows the pending or declined version instead of the
one in effect. Seven are low, seven are notes. Everything the author recorded as
PASS and that was run again here passed with the same counts.

## Findings

"Run" means reproduced on the reviewer's cluster; "reading" means found in the
code and not executed. Reproductions R1–R10 are described at the end. Server paths
without a prefix are under `api/src/gorgona_booking/`; test paths are under
`api/tests/integration/`.

### F1 — medium — hidden shifts stay readable through an open-shift id, the swap command and the request read

- **Where.** `api/src/gorgona_booking/api/workforce_desk.py:66-73` and
  `business/workforce_desk.py:240-257` (the request read);
  `api/shift_changes.py:29-50` (a proposal is not checked against the setting);
  `api/shift_changes.py:193-212` (open shifts with their ids stay listed while
  hidden); `db/migrations/0033_shift_changes.sql:162-171` (the refusal tells a
  holder from a non-holder).
- **What is wrong.** Hiding closes `GET /colleagues/{id}/shifts` only. An
  employee who has ever seen a shift id still learns who holds that shift and its
  position, time and skills.
- **Scenario.** The branch hides shifts. Employee A lists `/open-shifts` and sees
  open shift S. A manager assigns S to colleague B (S is now version 2), so S
  leaves the open list and `/colleagues/B/shifts` answers 403
  `COLLEAGUE_SHIFTS_HIDDEN`. A sends `PUT /changes/{new id}` with `kind=swap`,
  their own shift, `other_shift_id=S`, `expected_other_shift_revision=2`,
  `target_profile_id=B`: 200. `GET /my-changes/{id}/shifts` then returns S
  version 2 with `position`, `starts_at`, `ends_at`, `required_skill_ids` and
  `staff_profile_id=B`. A withdraws the request; the read keeps working.
- **Without leaving a request.** A wrong holder is refused 403 and a stale
  version 409. Sending the same swap under the id of an existing request answers
  409 "This workforce record already exists" for the real holder and 403 for
  anyone else, because the holder check runs before the primary key. The number
  of requests stays 1.
- **Reproduction.** R3. **Confirmed by run.**
- **Relation to the author's record.** The Limits say that the swap command
  accepts an id "already known to the sender". They do not say that ids keep
  arriving from `/open-shifts` while hidden, or that the request read turns a
  known id into the whole hidden shift. This is question 1 of the setting's
  author review; see the answers.

### F2 — medium — "Outside the schedule" follows the latest version, not the version in effect

- **Where.** `web/components/timesheets.tsx:313-315` shows the badge from
  `entry.out_of_schedule`; `business/timesheets.py:36` computes it from the head
  version; `business/timesheet_contracts.py:109` (`EffectiveTime`) has no such
  field; `db/migrations/0034_timesheets.sql:247-248` copies the proposed times
  into a decline version.
- **Scenario A.** Shift 10:00–12:00. Clock in 10:00, out 11:00, approved: version
  3 is in effect and inside the shift. A correction starting 09:00 is declined
  (version 5). The API answers `status=declined`, `effective.revision=3` starting
  10:00, `out_of_schedule=true`. The screen shows "Outside the schedule" beside
  "In effect: approved version 3".
- **Scenario B.** Shift 15:00–17:00. Clock in 14:00, approved: version 3 is in
  effect and outside the shift, `out_of_schedule=true`. A correction starting
  15:00 is proposed: `out_of_schedule=false`. It is declined: still `false`. The
  mark of the time that counts disappears as soon as an in-schedule correction is
  proposed, and stays away after the correction is declined.
- **Reproduction.** R4 (hours of the fixture day). **API confirmed by run; the
  screen by reading; not exercised in a browser.**
- **Not covered by tests.** The browser test checks the mark only on a record
  without a shift and without a second version.

### F3 — low — cancel answers 500 for a valid key longer than 200 characters

- **Where.** `business/workforce_desk.py:312-320` writes the key as the audit
  target; `db/migrations/0004_identity.sql:245-246` limits a target to 200
  characters; a key may have 8–255 (`booking/idempotency.py:13`,
  `api/businesses.py:25-28`, `web/lib/workforce-contracts.ts:298`).
- **Scenario.** Key of 201 characters. `resolve`: 200 `unresolved`. `cancel`:
  `psycopg.errors.CheckViolation` 23514, which the API's catch-all handler turns
  into 500; no marker is stored. The command itself accepts the same key (200). A
  key of 200 characters cancels normally.
- **Reproduction.** R1. **Confirmed by run.** The screens use UUID keys of 36
  characters; only other API clients are affected. A command sent under such a
  key and lost can be resolved but never discarded.

### F4 — low — a cancelled key commits after its marker expires, while the API still answers "cancelled"

- **Where.** `booking/idempotency.py:46-58` lets any claim reuse an expired row;
  `business/workforce_desk.py:281-292` and `298-300` report an expired marker
  without renewing it.
- **Scenario.** Cancel key K: `cancelled`; the original command: 422. After the
  marker's `expires_at` has passed (24 hours; set by the test), `resolve` and a
  second `cancel` still answer `cancelled`, and the original command sent under K
  answers 200 and writes its time entry; `resolve` then answers `committed`.
- **Reproduction.** R2. **Confirmed by run.**
- **Documents.** "A cancelled key can never commit" (I4 VALIDATION, Recovery 5),
  "a cancelled key can never write" (setting VALIDATION, Behaviour 6) and the
  handoff hold for 24 hours, not for ever. A second effect still needs the old
  body to arrive a day later and the record to accept it; revision checks refuse
  most such commands.

### F5 — low — an unsaved Privacy choice of one location is shown for another

- **Where.** `web/components/schedule.tsx:119` and `230` (`choice` overrides the
  loaded value); the location filter of Shifts (`528-532`) does not reset it, the
  one of Privacy (`974-977`) does.
- **Scenario.** Company-wide owner. Privacy of location A, never changed: choose
  "Staff see only their own shifts and open shifts" and do not save. Open Shifts,
  choose location B, open Privacy. The page reads "Never changed: colleagues'
  shifts are visible by default" for B, yet "only their own shifts" is selected
  and Save is enabled. One activation of Save hides B's shifts.
- **Reproduction.** A temporary step in `web/tests/workforce.spec.ts` after the
  owner opens Schedule; both projects printed
  `OWN_ONLY checked = true , Save enabled = true`. **Confirmed in a real browser
  on desktop and phone.** The spec was restored from a copy; `git status` is
  clean.

### F6 — low — "nothing was changed" is shown while the command may still be running

- **Where.** `web/components/workforce-shared.tsx:306-308`;
  `business/workforce_desk.py:277-292` reads committed receipts only.
- **Scenario.** The command's transaction is still open, for example waiting
  for a lock longer than the client's 15 s timeout. `resolve` answers
  `unresolved`; the screen says "The server has no record of your last action, so
  nothing was changed." The command then commits.
- **Effect.** Only the sentence. Both offered actions stay safe: sending again
  replays by the key, and discarding waits for the command and reports
  "recorded". A person who leaves at that point was told nothing changed.
- **Reproduction.** R7. **API confirmed by run; the sentence by reading.**

### F7 — low — Schedule opens on the UTC date, not the date of the location

- **Where.** `web/components/schedule.tsx:92` and `214-222`;
  `web/components/my-shifts.tsx:70`. The helper `today(zone)` in
  `workforce-shared.tsx:389` is exported and never used.
- **Scenario.** Location in America/New_York, 23:00 local on 11 October (03:00
  UTC on the 12th). Schedule opens with "Week from 2026-10-12", and its filter
  compares dates of the location, so shifts that end today are not listed until
  the date is changed. My shifts asks for a padded window and still lists them;
  only its date field is a day ahead.
- **Reproduction.** Reading, and both dates printed with `node` at review time
  (`2026-10-12` against `2026-10-11`). **Not exercised in a browser.** The
  browser test always fills the date, so the default is never checked.

### F8 — low — "Add to the schedule" fixes a company-wide member's home branch without naming it

- **Where.** `web/components/schedule.tsx:429-442` (`entry.location_id ??
  selected`) and `741-782` (the Staff section shows no location);
  `business/workforce.py:146-147` (a second home is refused).
- **Scenario.** The owner last chose location B on Shifts or Privacy. On Staff,
  "Add <name> to the schedule" for a member with company-wide access creates the
  profile with home B, with no location shown and no confirmation. The message
  afterwards names B. The home cannot be changed: a profile in another branch is
  refused and no transfer exists.
- **Reproduction.** **Reading only.** The browser test adds a member whose
  membership already names the branch; the fixture has no company-wide member
  without a profile.

### F9 — low — any member can add receipt rows and audit events without limit through cancel

- **Where.** `api/workforce_desk.py:119-128`,
  `business/workforce_desk.py:295-321`; `db/migrations/0003_booking.sql:240`
  grants the runtime no delete on `gba.idempotency_keys`, and no code removes
  expired rows.
- **What.** Each cancel with a new key writes one receipt row and one
  `workforce.command_cancelled` audit event whose target is the caller's own text.
  It needs only `workforce.self` (staff and front desk included), works while the
  module is closed or off, and the application has no rate limit.
- **Document.** Question 2 of the I4 author review says the row lives "for 24
  hours". Expiry only allows reuse; nothing deletes the row.
- **Reproduction.** **Reading.** The writes themselves are seen in the author's
  tests and in R1 and R2.

### Notes

| # | Note | Where | Confirmed |
|---|---|---|---|
| N1 | The directory lists a member whose account is disabled and offers "Add to the schedule"; the colleague list filters `u.status='active'` | `business/workforce_desk.py:169-179`, `business/shift_changes.py:251-254` | run (R8) |
| N2 | A declined record with no approved version shows only "Declined"; no line says that nothing is in effect | `web/components/timesheets.tsx:323-337` | reading |
| N3 | System texts such as "Recorded clock-out" are shown as "Reason given" | `web/components/timesheets.tsx:338`, `0034_timesheets.sql:209-229` | reading |
| N4 | The audit event of a setting change holds the version only, not the value | `business/workforce_desk.py:124-131`, `business/workforce.py:434-442` | reading; the author's test shows `{"revision": n}` |
| N5 | The colleague read limits one request to 62 days, not the dates: every past and future published shift a home colleague holds can be paged through; the answer includes `assignment_id` | `api/workforce_desk.py:58-63` | reading |
| N6 | The shift form offers Draft for a published shift; the server always refuses that change | `web/components/schedule.tsx:674-679` | reading |
| N7 | Three test remarks, below | | reading |

N7, tests that say more than they check:

- `test_workforce_visibility.py:314` is refused because that author's membership
  does not cover the branch, not because the author is forged. Line 315 is the
  real forged-author case and it is correct.
- `test_another_company_and_plain_staff_get_no_management_reads`
  (`test_workforce_desk.py:293`) checks only another company's manager. Plain
  staff is checked for `/directory` in another test.
- `_wait_for_key_waiter` (`test_workforce_desk_races.py:34-47`) accepts any
  ungranted `transactionid` lock in the database. COMMANDS.md says the wait is
  "for the first one's uncommitted receipt key"; the test does not identify the
  row. By reading, the key is the only thing that request can wait for.

## Checked, no remarks

**1. Routes.**

- Company isolation. Every new route enters through `_access`
  (`api/workforce.py:46-63`); every statement carries the tenant id and runs under
  row security. Another company's manager gets 403 (author's tests, run again).
- Delegate and platform support. `workforce.self`, `.read` and `.manage` are in
  neither `DELEGABLE_PERMISSIONS` nor `PLATFORM_ADMIN_PERMISSIONS`
  (`auth/permissions.py:79-101`) and `_access` does not admit delegation. Run
  (R5): an active delegate and a platform administrator each get 403 on `/desk`,
  `/directory`, `/colleagues/{id}/shifts`, `/my-changes/{id}/shifts`, the setting
  read and write, `resolve` and `cancel`; no setting version and no cancel marker
  was written.
- Damaged guards. Run (R6): with an extra update grant on the setting table,
  `/directory`, `/colleagues/{id}/shifts`, `/my-changes/{id}/shifts`, `resolve`
  and `cancel` answer 503. The author's test covers `/desk` and the setting routes
  for four kinds of damage.
- Branch scope. A branch manager's directory is limited by the statement and by
  row security of `staff_profiles`; the setting routes call `require_location`;
  the colleague read narrows row security to the caller's home branch and never
  widens it; `/desk` and the request read clear the scope and filter by the
  trusted user id.
- What an employee learns. Names and profile ids of home colleagues
  (`/colleagues`, unchanged from I2). While shown: for a home colleague's
  published shifts in the home branch, the full shift view. Own profile and the
  two states of `/desk`. The two shift versions of a request they take part in.
  The state of their own keys. Nothing of another branch by browsing (404).

**2. Cancel.**

- A cancelled command cannot be recorded within the receipt's lifetime (author's
  tests, run again). After it: F4.
- Cancel cannot replace a recorded command: it reads first and returns
  `committed`, and a claim that meets a receipt returns it unchanged
  (`booking/idempotency.py:61-73`). Run (R10): for a recorded command whose
  receipt has expired, cancel answers `committed`, the receipt row is unchanged
  and no cancel event is written.
- Races. Both of the author's tests passed here. Cancel does not sit inside a
  savepoint; a failure rolls the marker back (seen in R1: no row left).
- Another person's key. The receipt key includes the actor
  (`business/workforce_desk.py:260-261`). Run (R2b): a colleague cancels my key
  string and my command still commits. A malformed key is refused by
  `IdempotencyScope`.
- Receipts match the screen. Run (R9): `profile`, `skill`, `staff_skill`, `shift`,
  `change.propose` and `change.event` each resolve as `committed` with exactly the
  reference `commandReference` produces. The author's tests cover `time.clock_in`,
  `time.event` and `location_setting`.

**3. Recovery in the browser.**

- Stored: `schema_version`, `actor_id`, `business_id`, `key`, `saved_at` and a
  reference of `operation`, `subject_id`, `revision`, `skill_id`
  (`web/lib/workforce-recovery.ts:9-16`). No body, name, reason or token.
- Bound to the person and the business by the storage key and by the stored
  ids; the screen is remounted on a change of either.
- No new key while an outcome is unknown: `run` refuses while a record is held,
  and `preserveWorkforceRecovery` refuses a second key in storage. A resend uses
  the saved key. A missing token, a timeout, a broken answer and a 5xx all keep
  the record.
- Three ways out remain without the server's answer, each as designed: a 4xx
  refusal clears the record; a record that cannot be read is removed with a
  message; a new tab has no record. In each the server's revision checks are the
  protection.

**4. Screens.** Page gates and controls follow the server's roles for owner,
manager, branch manager and staff. Where they differ, the screen is the stricter
one or the server's refusal is shown: N6, and a branch manager's decision on a
request whose people have another home. Clock-out stays possible while the module
is off or not accepted, on the screen and on the server. The pending version is
shown apart from the one in effect, and the owner's approval of own time is taken
from the version in effect. Remarks: F2, F5, F7, F8, N2, N3.

**5. The setting.**

- Author. The guard requires an active owner or manager whose membership covers
  the branch and `created_by = gba.current_user_id()`
  (`0035_work_location_settings.sql:20-26`). The function runs as the caller; the
  membership lookup names the tenant, so the self-read policy of memberships
  cannot bring in another company.
- Several memberships of one person. `memberships_one_live_per_user`
  (`0004_identity.sql:66-67`) allows one membership that is not revoked per person
  and company, so the lookup finds at most one active row; a revoked earlier
  membership is excluded by status.
- Order of versions. One advisory lock per company and branch, then latest plus
  one; the primary key is a second line.
- Order of locks. Membership row (share), receipt key, branch lock. Member
  management takes its own advisory lock and the membership row for update and
  never the branch lock; publishing a configuration does not take it either. No
  cycle was found. The author's race test passed here.
- Row security, grants, immutability. Forced row security, tenant and branch
  policies, insert on five columns only, update and delete refused by trigger also
  for the owner. Truncate is not granted and has no trigger, as for the other
  workforce tables.
- Guard and policy restore. `workforce_guard.py` reads `0035`, so the table, both
  policies, the three triggers, the check, the keys and the grants are compared on
  every workforce request; `test_location_access.py` restores the `0035` policy.
- The 403 answer is the same for a known and an unknown colleague.
- The request read answers only the proposer and the recipient; a manager and
  another employee get 404.
- Other ways round. `/colleagues` gives names only. Staff resources are excluded
  from the booking resource lists and shift occupancy is not part of customer
  availability (`api/salons.py:518,1342`, `customer/queries.py:251-255`), by
  reading. The one way found is F1.

**6. Tests.** Not covered before this review: a delegate and platform support on
the new routes (R5); 503 on five of the new routes (R6); six of nine operations
through `resolve` (R9); the expired marker (F4); a long key (F3); `resolve` during
a running command (F6); the mark against the version in effect (F2); the way
round the hidden setting (F1); the default date (F7); a company-wide member added
from the screen (F8); the Privacy choice across locations (F5); a 5xx answer and
an unreadable saved record in the browser; a lost answer of the setting change in
the browser; more than one page of any list. Tests that pass for another reason
than stated: N7.

## Results

| Check | Command | Result |
|---|---|---|
| SHA256, both tables | `git show <commit>:<path> \| sha256sum` | **PASS:** 25 of 25 and 19 of 19 |
| Focused API tests | `pytest -q tests/unit/test_workforce_desk_contracts.py tests/integration/test_workforce_desk.py tests/integration/test_workforce_desk_races.py tests/integration/test_workforce_visibility.py tests/integration/test_workforce_visibility_upgrade.py --tb=short` | **PASS:** 26 passed / 26.72s |
| Reviewer's reproductions R1–R10 | `pytest -q tests/integration/test_review_i4_repro.py --tb=short`, then `…/test_review_i4_repro2.py` (temporary files, not committed) | 10 passed / 12.40s and 1 passed / 8.28s. Each asserts what was observed: 6 confirm a finding (R1, R2, R3, R4, R7, R8), 5 confirm no defect (R2b, R5, R6, R9, R10) |
| Real browser, desktop and phone | `pytest -q -s tests/integration/test_i4_browser.py --tb=short` with `GBA_REQUIRE_BROWSER=1` | **PASS:** 1 passed / 98.43s; closed 2, enabled 2 (31.7s and 36.6s), switched off 2 |
| Real browser with the temporary step for F5 | the same command | 1 passed / 97.06s; the step shows the defect on both projects |
| Complete pytest, PostgreSQL and browser required | `pytest -q -ra --tb=short` with `GBA_REQUIRE_BROWSER=1`, on the head with the web export built from it | **PASS:** 1500 passed / 4 skipped / 1103.78s. The 4 skips are the three container checks and the external tenant site; they are not counted as PASS. Ruff and mypy ran beside it for part of the time |
| Ruff | `python -m ruff check src tests` | **PASS:** exit 0 |
| Format | `python -m ruff format --check src tests` | **PASS:** 263 files already formatted |
| Mypy | `python -m mypy src tests` | **PASS:** no issues in 263 source files |
| Web typecheck, lint, format | `npm run typecheck`, `npm run lint`, `npm run format:check` | **PASS:** exit 0 each |
| Web unit | `npm run test:unit` | **PASS:** 102 passed / 1.8s |
| Web build | `npm run build` | **PASS:** exit 0, 23 static pages |
| Production `npm audit` | `npm audit --omit=dev --json` | **FAIL:** exit 1, 2 high (`next`, `source-map-js`); inherited, as the author recorded |
| Axe and overflow counts in VALIDATION | counted calls in `workforce.spec.ts` | **PASS:** 4 + 12 + 4 axe checks and 1 + 6 + 1 overflow checks per screen size, as written |
| CI of the head | | **NOT TESTED:** no GitHub client on this machine; only the published head was compared |
| Containers, optional external tenant site | | **NOT TESTED:** skipped, as in the author's runs |
| HawkScan, load, soak, deployment, production | | **NOT TESTED** |
| Real screen reader | | **NOT TESTED** |

All pytest commands ran from `api` of the review worktree with
`-p no:cacheprovider --basetemp <new folder>`, `PYTHONPATH` set to its `api/src`
and `api`, `PYTHONDONTWRITEBYTECODE=1`, `GBA_REQUIRE_POSTGRES=1` and the
connection taken from a private file outside Git. No connection value appears
here.

## Not reviewed or not tested

- F2 (screen), F7 and F8 were not exercised in a browser; N2–N6 by reading only.
- Lists longer than one page, more than 20 versions of a shift, more than 20
  unnamed requests, a clock change inside a shift, more than one page of
  locations.
- A 5xx answer, an unreadable saved record and a lost answer of the setting
  change in the browser.
- The I1–I3 code was read only where the new routes call it; it was not reviewed
  again.
- CSS and visual layout beyond the author's axe and overflow checks.
- CI, containers, the external tenant site, HawkScan, load, deployment,
  production, a real screen reader.

## The author's "not verified" lists

I agree with both lists; nothing in them was hidden as a pass.

| Item | After this review |
|---|---|
| No second person read the code (both lists) | Done here |
| No test damages the guards and calls the five I4 routes | 503 confirmed by run for the routes the author's later test does not cover (R6) |
| Delegate and platform support rely on `_access` (both lists) | 403 confirmed by run on all eight calls for both (R5) |
| A swap sent to the API is accepted while hidden | Confirmed by run, and it goes further than recorded: F1 |
| Long lists, more than 20 versions, a clock change inside a shift | Still not tested |
| More than twenty unnamed requests, more than one page of locations | Still not tested |
| No real screen reader | Still not tested |
| A lost answer of the setting change in the browser | Still not tested in the browser; `resolve` for `location_setting` passed in the author's API test here |

Missing from the lists and found here: F2–F9 and N1–N6.

## Answers to the author's questions

**I4 author review.**

1. *Colleagues' published shifts shown to an employee.* The owner decided it.
   Two remarks for that decision: the read has no bound on the dates (N5), and
   hiding does not hide what it says (F1).
2. *A limit on cancel.* Yes, before the module is opened to a company: a limit
   per person, or a documented limit at the edge. See F9; the row is not removed
   after 24 hours.
3. *The role in the directory for a branch manager.* Not a defect. The screen
   only displays it, and the members route refuses a branch manager, so this is a
   small widening. If the role is not needed there, omit it for a branch scope.
   Separately, the directory should skip disabled accounts (N1).

**Setting author review.**

1. *Should a hidden branch also refuse the swap command?* Yes, or the setting
   should be described as "browsing only". As built, any employee reads round it
   for every shift whose id they have seen, and open shifts keep supplying ids
   (F1). Either refuse a swap proposed by a person whose home branch hides
   shifts, in the API and in SQL, or keep the swap and stop the request read from
   returning the other person's shift to the proposer. This changes I2 and is the
   owner's decision.
2. *One lock per branch after the membership share lock.* Correct. No path takes
   them in the other order; see "Order of locks" above. The author's race test
   passed here.
3. *Telling staff who hid the shifts.* The note is enough. Naming the manager
   adds personal data and no function.
4. *A company-wide default.* Later. One consequence to tell the owner now: a new
   branch starts visible, so a company that hides everywhere must hide each new
   branch itself.

## Reproductions

The temporary files `api/tests/integration/test_review_i4_repro.py` (R1–R9) and
`test_review_i4_repro2.py` (R10) reused the fixtures of `test_timesheets.py` and
the helpers of `test_workforce_desk.py` and `test_workforce_visibility.py`. They
were removed from the worktree after the runs; copies are kept beside the
reviewer's cluster, outside Git.

| # | Steps | Observed |
|---|---|---|
| R1 | `resolve`, then `cancel` with key `"k"*201`; the command under the same key; `cancel` with `"k"*200` | 200 `unresolved`; `CheckViolation` 23514 and no marker; 200; 200 `cancelled` |
| R2 | `cancel` K; the command under K; as owner `update gba.idempotency_keys set expires_at=now()-interval '1 second' where idempotency_key=K`; `resolve`; `cancel`; the command under K; `resolve` | `cancelled`; 422; `cancelled`; `cancelled`; 200 and one time entry; `committed` |
| R2b | The colleague cancels key K; I send my command under K | `cancelled` for them; 200 for me |
| R3 | As in F1, with a third home colleague as the non-holder | 403 hidden; probes 403 and 409; swap 200; the request read returns the hidden shift; by an existing request id 409 against 403; one request row |
| R4 | As in F2, scenarios A and B | A: `declined`, `effective.revision=3`, `out_of_schedule=true`. B: pending `false`, declined `false`, `effective.revision=3` |
| R5 | A delegate under an active grant and a platform administrator call the eight new routes | 403 on all sixteen calls; no setting version, no marker |
| R6 | `grant update (colleague_shifts_visible) … to gba_runtime`, five routes, revoke | 503 on all five |
| R7 | `timesheets.clock_in` in an open transaction; `resolve` over HTTP; commit; `resolve` | `unresolved`; `committed` |
| R8 | A member's account is set to `disabled`; the manager reads `/directory` | The member is listed |
| R9 | One command per operation under a known key; `resolve` with the reference the screen saves | `committed` for all six |
| R10 | A recorded clock-in; its receipt set to expired as in R2; `cancel` | `committed`; the receipt row is the same before and after; no `workforce.command_cancelled` event |

For F5 the step added to `workforce.spec.ts` was: open Privacy, choose the home
location, check "only their own shifts", open Shifts, choose the other location,
open Privacy, read the status line, the radio and the Save button.
