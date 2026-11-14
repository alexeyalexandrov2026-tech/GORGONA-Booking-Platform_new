# Package R review fixes — assignment, handover and fleet capacity

Base 5319468, branch `codex/package-r-review-occupancy-fixes`. Independent review findings RR-01 through
RR-04. Run folder `~/gba-runs/package-rr1-20261113-5319468`.

- Use the existing class row lock before changing a booking, assignment, inspection or fleet capacity.
  Re-read the current state while holding the lock. Preserve the shared occupancy exclusion constraint.
- A second handover of the same unit waits for a recorded return. Planned intervals retain their current meaning.
- Assignment replacement, cancellation and the current release-and-reassign period command close at handover.
  Returns keep the recorded assignment. In-use extension requires a dedicated transition in a later slice.
- Moving or retiring a unit must preserve current and future holds and the source branch's committed class capacity.
  Check peak availability through the last outstanding booking using the existing SQL function.
- Migration 0108 adds guards for these transitions and preserves earlier migrations and history.
  Verify concurrent operations with an observed PostgreSQL lock wait and verify a nonempty 0107 upgrade.

Status **NOT TESTED** until regression, upgrade and full gate evidence is recorded. The remaining review
findings and PROPERTY-01 follow this slice.
