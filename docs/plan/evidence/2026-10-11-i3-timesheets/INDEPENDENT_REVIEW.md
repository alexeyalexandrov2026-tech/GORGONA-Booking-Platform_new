# I3 independent corrected-source review — 2026-10-11

PASS: final corrected-source review after all four fixes. Independent SHA256
comparison found14 matches and0 mismatches. No remaining reproducible blocker
found in the bounded review. This is not an independent runtime test or package
acceptance. The earlier three-fix PASS was superseded by the fourth finding and
is not reused to validate the final correction.

Reviewer checkout: C:/Users/alexa/Documents/ChatGPT/gorgona-package-i3-review.
Branch: codex/package-i3-review. Base HEAD:
49276bf800eb929589785e192db489e17ac77fa7. Root copied14 canonical API files to
the separate checkout. Reviewer independently compared the readonly manifest:
14 matches,0 mismatches. Reviewer made no changes and did not read the canonical
checkout. The evidence-engineering skill requires independent review for
high-risk security/data changes; this isolated source review fulfils that scope.

## Retained findings and corrections

1. **FAIL, P1: raw branch manager could decide another home.** The original
   revision guard checked role but omitted the actor's actual membership home.
   With runtime location context empty, a homeB manager could approve/decline
   a homeA employee's entry. Root reproduced2 raw failures and2 API refusals in
   6.30s before the fix. Forward0034 now reads the active membership home and
   requires company-wide or matching entry home for both decision actions.
   Own approval still compares stable user identity and only permits an owner,
   with the immutable visible tag. A scoped-home manager success test protects
   the legitimate path.
2. **FAIL, P2: old RR snapshot accepted a replaced shift link.** Locking an
   unchanged shift head did not refresh immutable history reads. After another
   transaction cancelled/reassigned the shift, old revision1 could still link
   to a fresh time entry. Root reproduced both races with observed resource
   wait. Forward0034 locks the exact existing confirmed allocation FOR SHARE,
   whose physical release triggers40001 under a stale snapshot. No occupancy
   is created. Tests require40001/42501 and zero time entries after refusal.
3. **FAIL, P2: old RR snapshot bypassed the module off-switch.** A shared
   configuration advisory lock did not refresh a prior enabled snapshot.
   Root reproduced clock-in, correction and approval after a committed disable,
   with observed config lock waits. The new guard physically locks the effective
   module row FOR SHARE. Only the tenant-scoped config lock-read widens branch
   context, restoring it before staff/entry access; this is needed because the
   config UPDATE RLS also applies to SELECT FOR SHARE. Tests require40001/GBM01
   and no new head/revision/projection effect.

4. **FAIL, P1: starting break101 stranded an open entry.** Root self-review and
   the independent reviewer confirmed that break_start allowed100 completed
   breaks, while subsequent break_end/clock_out appended101 and violated the
   array limit; corrections cannot repair an open entry. Root reproduced four
   API/raw admission failures, with two positive boundary cases passing, in
   8.07s. Forward0034 now refuses break_start once100 breaks are completed,
   before changing any snapshot. Tests require unchanged revision/state/audit/
   key counts, then successful closure with100 breaks, including module-off.
   The hundredth break can end normally or close automatically with the entry.

The five RR red cases failed in6.45s. The initial implementation snapshot was
FAIL. Corrected PASS does not retroactively validate earlier source.

## Reviewed guarantees

The reviewer checked immutable snapshots, exact current-xid projection and
one-step updates, deferred orphan completeness, full-interval immediate GiST
exclusions on stable user, pending/declined old-effective preservation, same-home
reinvite closure, owner tag, current optional shift link, UTC ordering and duration,
as-of receipt replay, own/scoped management access, real delegation refusal,
off-switch narrow closure, package source/grant/policy/exclusion approvals,
policy restoration and nonempty upgrade.

Corrected-source tests include native SQL40001 mapping/key rollback, invalid
array shapes/order/bounds, projection tampering, orphan heads/events, no journal
or shared occupancy effects, three repeated corrections, and17 races requiring
observed pg_locks waits. The reviewer assessed test code without executing it.

Trusted gba.user_id context is application authentication context, not
cryptographic identity for arbitrary database clients. Reported clock timestamps
are not device/location proof. Labour/payroll rules and I4 screens are out of I3.

Reviewer commands: read-only git status/branch/rev-parse, source reads and
Get-FileHash -Algorithm SHA256. Independently reported raw hashes:

| File | SHA256 |
|---|---|
| api/src/gorgona_booking/db/migrations/0034_timesheets.sql | 282423D4E9F581F89E51BE33E12073FA6EF3C5E15C3BCBD27F9B52EA5FA01A2F |
| api/src/gorgona_booking/db/workforce_guard.py | CF8AC94AF16F62A92D2F204243BA627E32DDEF0D3AC9A1A2EFCEBE2B2346232B |
| api/tests/integration/test_timesheet_guards.py | 049F1205D8AD238010F09CF7113503004EF99660348EC6A035EC3473752C53E3 |
| api/tests/integration/test_timesheet_races.py | 7990631F409A77440B22BBB19049383C473FD696C473A86AEC612B2E6EB7C7BA |

NOT TESTED by reviewer: PostgreSQL, pytest, browser, static checks, full suite,
CI, deployment and production; zero test runs. Root's runtime results are only
in [VALIDATION.md](VALIDATION.md). No CodeRabbit or external operation occurred.
The older I1 review checkout's accidental helper duplicates remain preserved
after automatic approval policy rejected their deletion; there was no retry.
