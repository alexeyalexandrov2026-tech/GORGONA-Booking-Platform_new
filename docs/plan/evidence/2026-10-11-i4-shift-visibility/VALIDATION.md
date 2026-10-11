# Colleague-shift visibility as a branch setting — validation (2026-10-11)

A follow-up to slice I4 of package I (WORK-01), on the same branch
`codex/package-i4-workforce-screens`, on top of the I4 record `5f0e58f`. Final code
commit `419eda8097554c024cb76cde38fe901c386a5e29`. Exact commands and first failures are in
[COMMANDS.md](COMMANDS.md); the hashes of the checked sources are in
[SOURCE_SHA256.md](SOURCE_SHA256.md); the author's re-read is in
[AUTHOR_REVIEW.md](AUTHOR_REVIEW.md).

It carries out the owner's decision of 2026-10-11 on the first open choice of I4.
The owner's words:

> «Сотрудник может видеть опубликованные смены коллег своего филиала, но также менеджер, либо вышестоящий, кто, например, владелец компании, либо менеджер филиала, управляющий, может менять в настройках приватность. То есть может менять (видимость смен коллег»

Readiness is unchanged: WORK-01 and CORE-04 stay `planned`, and the `workforce`
module stays closed outside test fixtures. Migration `0035` is new; migrations
`0001`–`0034` are untouched. No dependency changed.

## What was built

| Part | Files |
|---|---|
| Schema | `api/src/gorgona_booking/db/migrations/0035_work_location_settings.sql`; packaged approvals in `db/workforce_guard.py` |
| API | `api/src/gorgona_booking/api/workforce_desk.py`, `business/workforce_desk.py`, `business/workforce_desk_contracts.py` |
| Screens | `web/components/schedule.tsx` (Privacy section), `my-shifts.tsx`, one message in `workforce-shared.tsx` |
| Typed contracts and client | `web/lib/workforce-contracts.ts`, `web/lib/workforce-api.ts` |
| Tests | `api/tests/integration/test_workforce_visibility.py`, `test_workforce_visibility_upgrade.py`, additions in `test_i4_browser.py`, `test_workforce_desk.py`, `test_timesheet_upgrade.py`, `test_location_access.py`, `api/tests/unit/test_workforce_desk_contracts.py`, `web/tests/workforce-contracts.spec.ts`, `web/tests/workforce.spec.ts` |

## Behaviour

1. **Default.** Without any change, staff of a branch see the published shifts of
   colleagues of that branch, as in I4. No row is stored for the default.
2. **Who changes it.** The owner and a manager of the whole company change any
   branch; a manager of one branch changes that branch only. Front desk, staff,
   another company's manager, a delegate and platform support cannot.
3. **Where.** Schedule has a fourth section, Privacy: two choices for the
   selected location, Save, and a line saying who changed it last and which
   version it is. A company-wide person picks the location; a branch manager has
   no choice of location.
4. **What hiding does.** `GET /workforce/colleagues/{id}/shifts` answers
   403 `COLLEAGUE_SHIFTS_HIDDEN`, the same for a known and an unknown colleague.
   `/workforce/desk` tells the person's screen `colleague_shifts: hidden`. On
   My shifts the Swap buttons are disabled and a note says why.
5. **What hiding does not do.** Own shifts, open shifts, the list of colleagues'
   names, a handover and an open-shift request work as before. The people who
   take part in a request still see the shifts that request names.
6. **A change is a command like the others.** It carries an expected version and
   an idempotency key; a repeat returns the first answer; a stale version is 409;
   a lost answer is settled by the original key and a cancelled key can never
   write. Every change adds a version and an audit event; nothing is edited in
   place.
7. **Module off or not accepted.** The setting stays readable and stays in force;
   it cannot be changed (API 409 `MODULE_DISABLED`, SQL `GBM01`).

## The database is the source of truth

`gba.work_location_setting_versions` is append-only. Its insert guard requires
that the author is the authenticated person and holds an active owner or manager
membership that covers the branch; it takes one lock per branch and accepts only
the latest version plus one. Row security keeps a branch session inside its own
branch. Update and delete are not granted and are refused for the schema owner
too. The table, its two policies, three triggers, check and grants are part of
the packaged workforce approvals: damaging any of them makes every workforce
route answer 503. The branch-policy restore of `test_location_access.py`
includes `0035`.

## A gap found on the way

A change request stores shift ids only. In I4 the screen named those shifts by
browsing the colleague's schedule. With browsing hidden, the person asked to
take or swap a shift would not see which shift it was. One read was added after
a failing test: `GET /workforce/my-changes/{id}/shifts` returns exactly the
shift versions the request was made for, to its proposer and recipient only. A
manager or another employee gets 404, another company 403. My shifts now names
request shifts through this read in both states of the setting, so it no longer
browses a colleague's schedule for that.

## Results

| Check | Result |
|---|---|
| Baseline before any change | **PASS:** 13 passed / 15.02s (desk, desk races, desk contracts, I3 upgrade) |
| New API tests, before the schema and routes existed | **FAIL (expected red):** 9 failed / 7.61s |
| Request-shifts test, before the route existed | **FAIL (expected red):** 1 failed / 2.77s (404) |
| New API tests on the final code | **PASS:** 24 passed / 26.70s (visibility 12, upgrade 1, desk 7, contracts 4) |
| One race of two changes of one version | **PASS:** the second request is seen waiting in `pg_locks` for exactly that branch's lock, then gets 409 |
| Nonempty `0034` database upgraded to `0035` | **PASS:** applied `[35]`, earlier facts and checksums unchanged, guard ready |
| Web unit for the contracts | **FAIL first:** 1 failed / 6 passed (the desk sample lacked the new field); **PASS:** 8 passed |
| Real browser, desktop and phone, three phases | **PASS:** 1 passed / 103.56s on the final tree; the first run of the extended scenario also passed (108.35s) |
| Complete pytest, PostgreSQL and browser required | **PASS:** 1500 passed / 4 skipped / 953.19s on `419eda8` |
| Ruff; format; mypy | **PASS:** exit 0; format 263 files; mypy 263 files |
| Web typecheck, lint, format, unit, build | **PASS:** exit 0 each; unit 102 passed; build 23 static pages |
| Production `npm audit` | **FAIL:** 2 high nodes, `next` and `source-map-js`; inherited, not addressed |
| Exact-commit CI of the I4 record `5f0e58f` | **PASS:** run 38132277248, job `api` success. The owner allowed publishing this branch on 2026-10-11 |
| Exact-commit CI of the head with this record | **NOT KNOWN HERE:** it starts on the push that carries this file; read it on GitHub |
| HawkScan | **NOT TESTED:** no scanner runtime or key on this machine |
| Independent review by a non-author | **NOT DONE.** The author re-read the diff; that is not an independent review |
| Containers, optional external tenant site | **NOT TESTED:** skipped as in I1–I4 |
| Load, soak, deployment, production | **NOT TESTED** |

## What the browser test proves

The I4 scenario of `web/tests/workforce.spec.ts` was extended in place; nothing is
mocked. Per screen size:

| Step | Check |
|---|---|
| Closed registry (owner) | Privacy shows "Never changed", the choice is disabled; axe clean |
| Branch manager | No location choice. Focus on the first choice, Arrow Down selects "only their own shifts", Save; the status says so and the line reads "last changed by you"; axe clean, no sideways scroll |
| Employee | The note is shown, Swap is disabled, Hand over is enabled; the swap request still names both shifts; the server answers 403 `COLLEAGUE_SHIFTS_HIDDEN` to the employee's own token; axe clean, no sideways scroll |
| Branch manager | Shows the shifts again; the status says so |
| Employee | The note is gone and Swap is enabled |
| Module switched off (owner) | Privacy shows the last version and who made it, the choice and Save are disabled; axe clean |

The database is checked afterwards: four setting versions of the home location in
order (hidden, shown, hidden, shown: two per screen size) and four audit events.
Axe now covers twenty screen states per screen size (4 closed, 12 enabled,
4 switched off); the page does not scroll sideways on eight of them.

## Limits and choices left to the owner

- **Hiding closes browsing, not the swap command.** The server still accepts a
  swap whose other shift id is already known to the sender; the screen cannot
  choose one. Blocking the command itself would change slice I2.
- **One setting per branch.** There is no company-wide default; a new branch
  starts visible. A company-wide default can be added if wanted.
- **No exceptions per person and no schedule of the setting.** It applies to
  everyone whose home is the branch, at once.
- **Names of colleagues stay visible** to staff of the branch; a handover needs
  them.
- **Staff are not told who changed the setting**; managers are.
- **The history of the setting has no screen.** Every version is in the table and
  in the audit log; the screen shows the latest one.
- My shifts names the shifts of at most twenty requests that are not the
  person's own or open shifts; older ones read "a shift outside the dates shown".
- The screens are in English, like the rest of the management area.
