# Author's response to the independent review — 2026-10-11

The [independent review](INDEPENDENT_REVIEW.md) was written by a reviewer who did
not write this code. It was made on the published head `a806380`, in the
reviewer's own worktree, branch `codex/package-i4-review` and PostgreSQL cluster,
and is included here unchanged (commit `cd906d3` of that branch). It found no
critical or high defect, two medium and seven low findings and seven notes, and it
ran the author's checks again with the same counts.

This file says what the author did with each finding. Final code commit after the
fixes: `b66eb4140c1101d78e1bd4068eac537aab922b38`. Readiness is unchanged: WORK-01 and CORE-04 stay
`planned`. No migration was added or edited; `0035` is still the latest.

## Findings

| # | Severity | Decision | What changed | Proof |
|---|---|---|---|---|
| F1 | medium | **Fixed** | A branch that hides colleagues' shifts refuses a new swap with 403 `COLLEAGUE_SHIFTS_HIDDEN` before anything is looked up, so the holder, another colleague and a stale version get one answer, also under the id of an existing request. A swap sent while shown keeps its replay and stays readable to its two people. Handover and open-shift requests are unchanged | `test_a_hidden_branch_refuses_a_new_swap_and_tells_nothing_about_the_holder` (red first: the swap answered 200) and `test_a_swap_sent_while_shown_replays_its_first_answer_after_hiding` |
| F2 | medium | **Fixed** | The version in effect carries its own `out_of_schedule`; the entry's mark keeps describing its latest version. The badge follows the version in effect, and a pending correction says when it would move the time into or out of the schedule | `test_the_outside_schedule_mark_of_the_time_in_effect_ignores_later_versions` (red first: the field did not exist), both scenarios of the review; the strict web schema requires the field. The screen was not exercised in a browser for this case |
| F3 | low | **Fixed** | The audit target of a discarded command is the key while it fits 200 characters, else `sha256:` and its digest | `test_a_long_valid_key_can_be_discarded` for 200, 201 and 255 characters (red first: `CheckViolation`) |
| F4 | low | **Documented; behaviour unchanged** | The documents now say that a discarded key cannot write while its receipt lives, 24 hours. The lifetime belongs to the shared receipt mechanism of every command; a marker that never expires would change that mechanism for one case. A second effect still needs the old body a day later and must pass the version checks | Wording in both VALIDATION files, the handoff and the module docstring |
| F5 | low | **Fixed** | An unsaved Privacy choice is kept with its location and shown only for it | Real browser, both screen sizes: a choice made for the home location, then the other location shows its own value and Save is disabled |
| F6 | low | **Fixed** | The sentence no longer says that nothing was changed; it says the server has no record yet and the action may still be in progress | Reading; the browser test still finds the start of the sentence |
| F7 | low | **Fixed** | Schedule and My shifts start on today's date of the location (home location on My shifts) until a date is chosen | Real browser: "Week from" equals the date computed for the location's time zone. On a day when that date equals the UTC date the check cannot tell the two apart |
| F8 | low | **Fixed** | Staff shows the location choice to a company-wide person with a sentence that a home location cannot be changed later, and the button reads "Add to the schedule of <location>" | Real browser: the location shown on Staff and the button name. Adding a company-wide member without a location was not exercised: the fixture has none |
| F9 | low | **Fixed** | One person may discard at most 20 commands per business in 24 hours; the next is refused with 429 `TOO_MANY_DISCARDED_COMMANDS`. Outcomes, repeats and real commands are not limited. Rows are still not removed after 24 hours; that statement of the I4 author review was wrong and is corrected there | `test_discarding_has_a_daily_limit_per_person` (red first: the 21st was accepted) |
| N1 | note | **Fixed** | The directory joins active accounts only | `test_the_directory_skips_a_disabled_account` (red on the earlier query) |
| N2 | note | **Fixed** | A declined record with nothing approved says that nothing is in effect | Reading |
| N3 | note | **Fixed** | The server's own clock texts are not shown as a reason given, on the card and in the history | Reading |
| N4 | note | **Fixed** | The audit event of a setting change carries the chosen value | The author's visibility test now expects it |
| N5 | note | **Not changed** | The colleague read returns the shared shift view of I1 and limits one request to 62 days, not the dates. Bounding the dates or trimming the view is a product choice for the owner | — |
| N6 | note | **Fixed** | The form of a published or cancelled shift does not offer Draft | Real browser: the options of a published shift are Published and Cancelled |
| N7 | note | **Fixed** | The race tests look in `pg_locks` for a waiter on the very transaction that holds this key's receipt row; the plain-staff test now checks plain staff; the comment of the SQL author case says what it proves | The three tests, run again |

## Where the fix of F1 lives

In the service that records a proposal (`business/shift_changes.py`), after the
idempotency claim, so a repeat of an earlier swap still returns its first answer.
It is not repeated in SQL: the read it protects is also refused in the API only,
and a trigger on the request table would need another migration. The screen
already disabled the swap; the server now refuses it too.

## Still open after the review

- F4 behaviour and N5, as above.
- I4 question 3 (the role shown to a branch manager in the directory): the
  reviewer calls it a small widening, not a defect; unchanged.
- A company-wide default of the setting: the reviewer agrees it can come later.
  A new branch starts visible, so a company that hides everywhere must hide each
  new branch itself.
- Not exercised in a browser: the mark of F2, the texts of F6, N2 and N3, a
  company-wide member added from Staff, a lost answer of the setting change, a 5xx
  answer, lists longer than one page.
- The reviewer's NOT TESTED list stands: containers, the external tenant site,
  HawkScan, load, deployment, production, a real screen reader.

## Results after the fixes

| Check | Result |
|---|---|
| New tests for the findings, before the fixes | **FAIL (expected red):** 5 failed, 1 passed / 12.97s; the directory test was red on the earlier query after its own setup was corrected (1 failed / 7.19s) |
| Focused API tests after the fixes | **PASS:** 86 passed / 146.63s (review fixes, visibility, desk, desk races, contracts, timesheets, timesheet guards, shift changes) |
| Race tests with the exact waiter | **PASS:** 2. The first attempt matched the row's own transaction id and failed: a waiter on a row written inside a released savepoint waits for the top-level transaction, so the tests now match that one |
| Real browser, desktop and phone, three phases | **PASS:** 1 passed / 274.67s on `b66eb41` |
| Complete pytest, PostgreSQL and browser required | **PASS:** 1506 passed / 4 skipped / 2306.13s on `b66eb41` |
| Ruff; format; mypy | **PASS:** exit 0; 264 files |
| Web typecheck, lint, format, unit, build | **PASS:** exit 0 each; unit 102 passed; build 23 static pages |
| Production `npm audit` | **FAIL:** 2 high, `next` and `source-map-js`; inherited, not addressed |
| Exact-commit CI | **PASS** for `5f0e58f` (run 38132277248) and `a806380` (run 38135230218). CI of the head that carries this file starts on its push and is read on GitHub |
| A second independent review of these fixes | **NOT DONE** |
| Containers, external tenant site, HawkScan, load, deployment, production | **NOT TESTED** |

Commands are the ones of [COMMANDS.md](COMMANDS.md); the new test file is
`api/tests/integration/test_workforce_review_fixes.py`.

## SHA256 of the sources changed by the fixes

Every source and test file changed between `a806380` and `b66eb4140c1101d78e1bd4068eac537aab922b38`,
hashed from the blobs of that commit.

| SHA256 | File |
|---|---|
| `112cbc39058a38885b1c236f7d06e44ea07fe382e5e31a215089d0d8bafb72e6` | `api/src/gorgona_booking/api/workforce_desk.py` |
| `c134711d578ff297028df876afd2ab9c159ba772c994379752440e6cc440f551` | `api/src/gorgona_booking/business/shift_changes.py` |
| `d38d7ba299d019a69b9012a42f7c458a23834be7d72dbf18e58d8d577a393dc5` | `api/src/gorgona_booking/business/timesheet_contracts.py` |
| `721466efdd759df2a8af1edb242f720b03e1a22e08bf822360463b6c904b1d55` | `api/src/gorgona_booking/business/timesheets.py` |
| `fde3087df7351b29530b4717ca4f5b8f5fd08953443e5f2df4ced25ee9a751b7` | `api/src/gorgona_booking/business/workforce_desk.py` |
| `c6e7352b8414fccedd5998873cd58342e4abebdca0d8131794510242a9c0b12a` | `api/tests/integration/test_workforce_desk.py` |
| `4c41fa49077dea63ae25e1cc5c177b1d5523dbac59f5c591352f68743baf0161` | `api/tests/integration/test_workforce_desk_races.py` |
| `795aa83374d72d04c76397775f86ca1b3bb4409e860ba797d597f744b45df1cd` | `api/tests/integration/test_workforce_review_fixes.py` |
| `4da282f0f2730df3c7e335861f5fc69faa9f3976b6845f5081a4a5c49c3c9fcc` | `api/tests/integration/test_workforce_visibility.py` |
| `111fb8f9a2743a1047607f37eba8cf3183ff2fb523ec86237c48235e1b439a45` | `web/components/my-shifts.tsx` |
| `759f13c9c1662e3ed416cabf13c841ae8c2e52058a4f72b1bfc5ec3968254d8e` | `web/components/schedule.tsx` |
| `34f3d3e923571e1a26ab99a3378c54c166ead325083a090e73bfb59d5041c57c` | `web/components/timesheets.tsx` |
| `66f5b1fb5ff493f34d0d63b7526c538ca851a202a10e087f0a2a76db3ff845ad` | `web/components/workforce-shared.tsx` |
| `9296e5490d3cf71bec83e40e314e11f1c2943c32089dbfd3a43a67ba307d90c0` | `web/lib/workforce-contracts.ts` |
| `042ce7facb908ab5bf465e6c04d62c6c7a78e43bc09d92347792bf243185934f` | `web/tests/workforce-contracts.spec.ts` |
| `da7a7534fdaed5f782c5b248ae0610a63cfbf4cd0a4849e23a5336accda27161` | `web/tests/workforce.spec.ts` |

16 files.
