# ADR-0025 — Workforce: shifts, shift changes and versioned timesheets

- Status: **Proposed (2026-10-09); not explicitly approved.** The owner delegated
  the choice of next steps on 2026-10-09, so the recommended options are working
  defaults for slice I0 of the
  [package I plan](../plan/PACKAGE_I_PLAN_2026-10-09.md). Slice I0 changes no
  schema. The owner can still change any choice before the slice it affects.
- Scope: package I of the owner-approved stage 2; criterion WORK-01 ("a shift
  handover checks skills, conflicts and approval; a timesheet correction keeps the
  previous version").
- Base: `9ef3734` on `codex/package-h-acceptance`. Builds on ADR-0022 (shared
  resource occupancy), ADR-0014 (location scope) and ADR-0019 (module gates).
- Decision owner: the product owner. The nine open choices are listed in the plan;
  this record states the recommended option for each.

## Context

Staff exist today only as memberships (one live membership per user and company,
a role, an optional branch) and, separately, as bookable `artist` resources with
weekly hours. Nothing links the two. Weekly hours describe when customers may
book; they are not shifts, cannot be handed over and keep no history. The
readiness registry says so: WORK-01 is `planned`.

The master plan asks for shift planning by position and skill, handover and swap
with approval, clock-in and clock-out with breaks, and timesheet corrections. It
also states that a customer booking, a work shift and a kitchen order are separate
processes that share staff, resources and finance, and that no new module may
reserve a shared resource in a table of its own (§12.2.1). The stage 2 plan
therefore requires staff occupancy to go through the shared occupancy table.

## Proposed decision

1. **A staff member is a membership.** A `staff_profile` marks a membership that
   takes part in shifts. No second person record is introduced.
2. **Work time has its own resource.** Each staff profile owns one resource of a
   new kind `staff`, located in the member's home branch. Shift assignments
   allocate that resource in `gba.resource_allocations` with a new source kind
   `shift`. The existing exclusion constraint then guarantees that one person is
   never on two overlapping shifts, across branches and under direct SQL.
3. **A shift does not occupy a bookable resource.** Bookings keep allocating the
   `artist` resource. A booking during the artist's shift is not a conflict.
   Deriving booking availability from shifts is out of scope.
4. **Skills are a company catalogue.** `work_skills` are versioned; granting and
   revoking a skill are dated events. A shift lists required skills. Assignment
   and approval of a change require every required skill to be effective at the
   start of the shift. SQL repeats the check.
5. **Shifts are versioned and single-seat.** A shift belongs to one branch, has a
   half-open interval, a position and required skills, and holds at most one
   active assignment. Published versions are insert-only. Changing the time of a
   published shift creates a new version and a new allocation; the old allocation
   is released in the same transaction. Cancelling is an event.
6. **Changes need two consents.** Handover, swap and picking up an open shift are
   requests with insert-only events: proposed, accepted by the colleague, approved
   and applied, declined, withdrawn. Approval by a member with `workforce.manage`
   re-checks skills and conflicts and applies the change atomically. A swap changes
   both assignments or neither. A request whose shift, assignment or skill changed
   since the proposal is refused.
7. **Timesheets are versioned.** Clock-in and clock-out create the first version of
   a time entry. A correction is a new version with author and reason; earlier
   versions stay readable and unchanged. The effective version is the latest
   approved one, and correcting an approved entry needs a new approval. One person
   has at most one open entry, and effective intervals do not overlap.
8. **Approval rules.** A change request is approved by a manager of the shift's
   branch. Nobody approves their own time entry, except the owner, and that case
   is shown as self-approved.
9. **One lock order.** Commands take the resource advisory locks in resource-id
   order, as booking does, and then lock shift rows in id order. Opposite swaps
   therefore cannot deadlock.
10. **Commands are idempotent.** Assignment, change and clock commands carry an
    idempotency key and an expected revision and reuse the existing receipt
    mechanism. A repeated command returns the first result.
11. **No money.** A time entry posts nothing to the ledger and computes no pay.
12. **Permissions.** `workforce.self` for every role, `workforce.read` and
    `workforce.manage` for owner and manager, limited to the member's branch scope.
    Not delegable, no platform-support access. Audit records carry identifiers only.
13. **Module and readiness.** The `workforce` module depends only on
    `users_access` and takes its readiness from WORK-01. Until acceptance a server
    gate refuses its writes. When the module is off, history stays readable and an
    open time entry can still be closed; new shifts, assignments and changes are
    refused. Booking does not depend on it.

## Bounded change to existing code

- Forward-only migrations from `0032`; migrations `0001`–`0031` are unchanged.
- `resources_kind_valid` gains `staff`; `resource_allocations_source_kind` gains
  `shift`; the allocation guard learns the new source and still refuses deletes
  and interval changes.
- Booking setup, staff reservations and customer availability must not list or
  accept `staff` resources. Characterization tests are written before the schema
  changes.
- A new guard module checks the approved function bodies and policies of the new
  tables; damage gives 503 on the package's routes.
- Permission map version 6. No new dependency.

## Alternatives considered

- **Shifts on the bookable `artist` resource.** Rejected: a shift would exclude the
  bookings it exists to serve, and staff without a bookable resource could not be
  scheduled.
- **A separate occupancy table for staff.** Simpler, but it contradicts §12.2.1 and
  the stage 2 plan, and a later module that needs the person exclusively would
  have to check two places.
- **Skills taken from booking services.** Rejected as the default: it ties
  workforce to the booking module, which a restaurant may not enable.
- **Mutable timesheet rows with an audit trail.** Rejected: WORK-01 requires the
  previous version to remain, and an audit trail is not a readable version.

## Acceptance and status

WORK-01 stays `planned` until every row I-01–I-12 of the plan passes, an
independent review is done, the exact commit passes CI and the owner approves a
separate acceptance commit. A single slice does not change readiness.

The plan also records one observation outside this decision: package F's
acceptance record states CORE-04 as technically verified, while the readiness
registry in code still lists CORE-04 as `planned`. Package I depends on F, so the
owner is asked to resolve the difference before I1.

## Limits

I1 implementation note (2026-10-09): immutable membership profiles reference
one stable resource per company/user, so revoke/re-invite cannot open another
occupancy lane. An existing person's home transfer requires a separate audited
lifecycle; same-home re-invite works and silent home moves fail closed. This
does not introduce a second person record or change WORK-01/CORE-04 readiness.
User-written timestamps use UTC bounds [0002-01-01,9999-01-01), with timezone
padding for Python/Psycopg; window checks subtract durations rather than adding
to max datetime. Own-schedule reads admit only that trusted user's cross-branch
assignments after workforce.self authorization; other route scopes remain.
[Evidence](../plan/evidence/2026-10-09-i1-workforce/VALIDATION.md).

No payroll, rates, tips or commissions; no labour-law rules for overtime or
breaks; no time off (unless the owner chooses it); no automatic scheduling or
demand forecast; no notifications; no geolocation, kiosk or PIN clock; no offline
mode; no retention or erasure policy for staff data; no group-level reporting.
This record authorizes no merge, deployment or production migration.
