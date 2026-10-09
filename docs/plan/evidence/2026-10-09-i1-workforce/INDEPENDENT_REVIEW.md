# Independent I1 review, 2026-10-09

Final corrected canonical snapshot: PASS. No remaining actionable blocker found
in the bounded code/static review. Runtime and release evidence remain separate.

Reviewer checkout: C:/Users/alexa/Documents/ChatGPT/gorgona-package-i1-review;
branch codex/package-i1-review. The executor copied21 canonical api files and
verified their SHA256 against its source before the final review. The reviewer
rehash before/after review found all21 unchanged.

## Findings retained and resolved

1. P1: WHEN(false) bypassed incomplete trigger metadata approval. Red runtime
   mutation returned200; full trigger qualification/fields now produce503.
2. P1: revoke/re-invite could create another resource for the same person.
   Stable tenant/user resource ownership now spans immutable membership profiles;
   repeated same-home invitation reuses it and overlapping shifts conflict.
3. P1: case/quote/whitespace normalization could approve changed expressions or
   advisory namespaces. Deparse comparison preserves quoted spans; trigger prosrc
   is exact; changed shared allocation function is explicitly guarded in I1.
4. P2: SQL admitted nested UUID arrays and dates unreadable by Python. One-dimensional
   arrays, finite supported UTC epoch bounds, strict typed inputs and directSQL
   refusals now agree.
5. P1: target membership was not locked during profile creation. SQL FOR SHARE
   closes the creation/home-move race; executor observed transaction-id waiting.
6. P1: scoped SQL hid the old profile from the home guard. Scoped membership
   moves now fail before inspecting hidden profiles; global edits still preserve
   the immutable staff home.
7. P2: near-max datetime overflowed duration addition. API validates durations
   by subtraction; max-year write gives typed ValidationError.

The first two review rounds were FAIL. Their findings were retained and
reproduced/corrected by the executor; the final corrected-snapshot conclusion
does not retroactively turn those snapshots into PASS.

## Independent fresh checks

Python -B checks, exit0: four semantic mutation pairs distinct, one harmless
formatting pair equal, max-date ShiftInput gives ValidationError, two UTC epoch
constants equal independently calculated Python bounds: eight checks PASS.
Historical migration and readiness/module diffs showed no change.

Reviewed SHA256:

- 0032_workforce.sql:
  DAD200C8C54F64A38020B27415ABB082D9E4D81A5690B6D6621A8971AAD9427D
- workforce_guard.py:
  31B769049D2CFB1F5B7B8884FD21015E6FF25DC658C5DC07FE1968FD131E8595
- business/workforce.py:
  FE0E0381717AC3A5CC6AF38A01367F499229AC8838480DACEA69A472E86D76D0

PostgreSQL, full suite and CI: NOT TESTED by reviewer. No edits, deletes,
credentials, shared cluster or external actions. Extra root src/tests helper
copies were ignored; only canonical api paths were reviewed.

## Supplemental test-only review

PASS after the executor added an explicit management POST booking refusal with
zero staff allocations and a real booking-readiness snapshot equality check.
The staff lookalike has services, hours and a real offered slot; the payload is
valid, so the refusal checks the resource boundary. Snapshot equality catches
a widened artist count even when the ready boolean would remain unchanged.
Fresh SHA256 comparison of 21 canonical files found only those two test files
changed. All production source remains identical to the prior PASS snapshot.
No new blocker. PostgreSQL and the executor's mutation/full test outcomes were
not independently executed by the reviewer.
