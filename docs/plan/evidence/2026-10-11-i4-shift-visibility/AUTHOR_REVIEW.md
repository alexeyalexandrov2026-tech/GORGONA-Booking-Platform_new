# Shift-visibility setting: the author's review — 2026-10-11

This is the author re-reading their own changes. It is **not** an independent
review and does not replace one. A copyable request for an independent reviewer is
in the [handoff](../../NEXT_AGENT_PACKAGE_I_REVIEW_2026-10-11.md).

## Found and corrected

| # | Finding | How it was found | Correction |
|---|---|---|---|
| 1 | With colleagues' shifts hidden, the person asked to take or swap a shift could not see which shift it was: a request stores ids only and the screen named them by browsing | Designing the browser scenario | `GET /workforce/my-changes/{id}/shifts` for the two participants, after a failing test; My shifts uses it in both states |
| 2 | A test expected the check constraint to answer version 0; the insert guard runs first and answers "stale" | First green run of the SQL test | The expectation was corrected; the check remains a second line |
| 3 | The hidden check had moved the lookup of the colleague under the home-branch scope | Re-reading `colleague_shifts` | The lookup returned to the caller's own scope. A new test for a company-wide member passes with either order, so this was a precaution, not a demonstrated defect |
| 4 | Two test defects of the author: a wrong audit column, two overlapping shifts for one person | Test runs | Corrected; listed in COMMANDS.md |

## Checked and left as it is

- **Who may change.** The route needs `workforce.manage` and the branch of the
  path; the SQL guard independently requires an active owner or manager
  membership that covers the branch and the authenticated author. A forged
  author, another branch's manager and a plain employee are each refused by SQL
  alone in the tests.
- **Hidden means the same answer for everyone.** A hidden branch answers 403
  before saying whether the colleague exists.
- **The request read shares only the request.** It returns the versions the
  request was made for, not the current ones, and only to its proposer and
  recipient.
- **The default stores nothing.** A company that never opens Privacy has no rows
  and behaves as I4 did.
- **Module off.** The setting cannot be changed and stays in force; the SQL gate
  is tested separately from the API refusal.
- **Recovery.** The change uses the same key, resolve and cancel as the other
  commands; the browser keeps identifiers only.

## Not verified by the author

- No second person read the code.
- A swap sent directly to the API with a known shift id is still accepted while
  the branch hides shifts. That is slice I2, left unchanged; see the limits.
- The delegate and platform-support refusals of the three new routes rely on the
  shared `_access` gate; only another company's manager, front desk and a plain
  employee are tested directly.
- More than twenty unnamed requests on My shifts and more than one page of
  locations were not exercised in the browser.
- No real screen reader was used; axe and keyboard operation were checked.
- A lost answer of the setting change itself was not exercised in the browser;
  it uses the command path that the browser test loses elsewhere, and the API
  test resolves and cancels it by key.

## Questions for the independent reviewer

1. Should a hidden branch also refuse the swap command, not only the browsing?
2. Is one lock per branch in the insert guard the right order of locks next to
   the membership share lock taken just before it?
3. Should staff be told on My shifts who hid the shifts, or is the note enough?
4. Is a company-wide default worth adding before acceptance, or later?
