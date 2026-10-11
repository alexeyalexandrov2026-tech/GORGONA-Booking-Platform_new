# I4 author's review — 2026-10-11

This is the author re-reading their own changes. It is **not** an independent
review and does not replace one. A copyable request for an independent reviewer is
in the [handoff](../../NEXT_AGENT_PACKAGE_I_REVIEW_2026-10-11.md).

Question 1 below was answered by the owner on 2026-10-11; see
[the setting's record](../2026-10-11-i4-shift-visibility/VALIDATION.md).

## Found and corrected

| # | Finding | How it was found | Correction |
|---|---|---|---|
| 1 | A success message appeared while the list still showed the previous version; opening "Versions" at that moment listed one version instead of two | First real-browser run: `Expected: 2, Received: 1` | The message is shown after the lists are reloaded (`workforce-shared.tsx`, `send` and `settle`) |
| 2 | Two activations of a control before the screen re-rendered: the second was refused through the saved record, but its error text stayed beside the success message | Re-reading `run` | A synchronous lock ignores the second activation; the saved record remains the second line of defence |
| 3 | A shift of a location outside the caller's view was shown in UTC without saying so | Re-reading `zoneOf` | Such times now carry the suffix "UTC" |
| 4 | The FAKE identity provider of the fixtures refused the application's real post-logout address `/auth/logout/`, so no browser test could use "Sign out" | Reading `web/lib/auth.ts` against `_provider` | The fixture accepts that address; product code is unchanged |
| 5 | The claim that cancelling waits for a running command rested on the existing receipt mechanism only | Re-reading `cancel_command` | Two race tests with an observed wait in `pg_locks` (`test_workforce_desk_races.py`): PASS 2 |

## Checked and left as it is

- **Scope of the new reads.** `/desk` clears the branch filter and reads only the
  caller's own profile by the trusted user id. `/directory` needs
  `workforce.read`; for a branch manager the SQL keeps profiles of that branch and
  members whose membership is in that branch, and row security hides profiles of
  other branches. `/colleagues/{id}/shifts` answers 404 for a profile outside the
  caller's home branch and for a caller without a profile, then narrows row
  security to the home branch.
- **Command outcomes.** The lookup includes the actor, so a key of another person
  resolves as `unresolved`. A reference to another subject or version is refused,
  which also stops a key from being read as something it was not. A receipt that
  expired still reports what happened: `cancel` reads before it claims, so it
  cannot overwrite a recorded command.
- **Cancel is not a workforce write.** It works while the module is off, because a
  person must be able to settle a lost closing command then. It writes an audit
  event with the operation and version only.
- **Browser storage.** One record per person and business, six identifier fields,
  size-limited, schema-checked, removed when it cannot be read.
- **A refused command (4xx)** clears the saved record: the transaction rolled
  back. A 5xx, a network error or an unreadable answer keeps it.

## Not verified by the author

- No second person read the code.
- No test damages the SQL guards and calls the five new routes; they share
  `_access` with the existing routes, whose 503 path is tested in I1–I3.
- The delegate and platform-support refusals of the new routes rely on the same
  `_access` gate and the permission map; only another company's manager and a
  plain employee are tested directly against them.
- The screens were exercised by one scripted scenario per screen size. Lists
  longer than one page, more than 20 shift versions and a clock change inside a
  shift were not exercised in the browser.
- No real screen reader was used; axe and keyboard focus were checked.

## Questions for the independent reviewer

1. Is showing home-branch colleagues' published shifts to an employee acceptable,
   or should a swap be proposed without seeing them?
2. Should `cancel` be limited in number per person and day? Each call can add one
   row to `gba.idempotency_keys` for 24 hours, as any command can.
3. Should the directory hide the role of a member from a branch manager?
