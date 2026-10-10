# I2 independent implementation review — 2026-10-10

PASS: corrected source review. No remaining reproducible correctness, security,
atomicity or schema-guard blocker found in the bounded review. This is not an
independent runtime or release acceptance.

Reviewer checkout: C:/Users/alexa/Documents/ChatGPT/gorgona-package-i2-review.
Branch: codex/package-i2-review. Base HEAD:
69270cc8bfdfb763cc8f5fc9b7892b13db987bce. Root copied sixteen canonical API files
into that separate checkout and verified SHA256 against the final full-suite
source snapshot. Reviewer read source only; no edits or PostgreSQL execution.
The evidence-engineering skill requires independent review for high-risk data
and security changes; this was the purpose of the isolated reviewer.

## Findings retained and resolved

1. **FAIL, P1: hidden prior allocation could remain active.** A shift in branchB
   assigned to a homeA employee could be opened/cancelled by direct runtime SQL
   scoped to B. The prior resource was hidden by RLS; UPDATE released zero rows,
   and a version without a new profile did not create a deferred assignment
   check. Root reproduced both outcomes before the fix. Forward0033 now checks
   visibility of every previous profile/resource and verifies actual releases
   equal expected prior assignments. Both SQL regressions require42501 and
   unchanged revision1/confirmed old occupancy.
2. **FAIL, P2: self pickup widened open-shift access.** Knowing a foreign branch
   shift UUID allowed pickup proposal and an owned history object despite the
   home-only open-shift listing. Root reproduced API200 and raw SQL acceptance.
   The proposal guard now requires pickup shift location to equal the active
   target profile's home. API/raw SQL regressions require403/42501 and no request,
   event, snapshot or command receipt. Own cross-home handover/swap remains valid.
3. **NOT TESTED, mandatory coverage gap: replacement future/revoked skills.**
   Earlier tests exercised missing replacement skill and I1 future/revoked
   assignments only. Root added all three replacement states × API/raw SQL, with
   snapshots created after the skill event and unchanged version/event/occupancy
   after refusal. Six cases PASS7.48s. This test-only change needed no production
   modification; the I1 SQL effective-skill check was already reused correctly.

The initial implementation review was FAIL. Corrected-source PASS does not
retroactively accept its earlier snapshots.

## Reviewed guarantees and limits

Source review covered eight areas: statement-level atomic swap and duplicate-head
refusal; sorted locks; exact immutable skill snapshots and stale refusal;
recipient consent and a different manager for pickup; self/manager branch scope;
original-event receipt replay; immutable/RLS/grants/module boundaries; packaged
0033 approvals, policy restoration and the nonempty upgrade test.

The retained I1 manual manager reassignment path and trusted application
gba.user_id context were explicitly acknowledged. This review does not claim
cryptographic user identity for arbitrary SQL clients or mandatory employee
consent for all I1 manual version inserts.

Reviewer commands: git status/rev-parse/branch and source reads; SHA256 via
Get-FileHash -Algorithm SHA256. Final independently reported raw hashes:

| File | SHA256 |
|---|---|
| api/src/gorgona_booking/db/migrations/0033_shift_changes.sql | 5A5F7408E78C294D2AE2A06A88B605DB25CE8221D254AB387B328FD753230CEB |
| api/src/gorgona_booking/db/workforce_guard.py | 8C6D2BDABC8341366F2B9B15B5A562DAA483459AFEE10EBB2C0ADBC1E66B517C |
| api/tests/integration/test_shift_changes_guards.py | 2D34EA7521E1FF90BB124A234C44A99C1FD822935610F54F439BC8BA309B2437 |

NOT TESTED by the reviewer: PostgreSQL, pytest, browser, static tools, full suite,
CI and production, zero test runs. Root's runtime results remain in
[VALIDATION.md](VALIDATION.md), not represented as independent execution.
No CodeRabbit or external operation occurred. The separate I2 checkout contains
canonical api paths; the older I1 review checkout's accidental helper duplicates
remain preserved after their deletion was rejected by automatic approval policy.
