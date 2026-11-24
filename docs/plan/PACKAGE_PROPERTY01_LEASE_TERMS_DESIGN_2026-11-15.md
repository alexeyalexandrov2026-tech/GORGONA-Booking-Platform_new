# PROPERTY-01 · 3b · Signed extensions and release

## Term and authority

Use the existing company-wide `property.manage` permission and the recorded 3a lease. An
extension uses the current agreed amendment of that same ADR-0020 agreement. The amendment
keeps the initial first day and adds at least one day to the current term. Its exact
document version has a stored file. An unsigned draft leaves the latest agreed version
current. A later agreed or terminated version supersedes it.

A release uses the current termination of the same agreement. Treat the operator's
`terminated_on` value as the last day of possession for the calendar. Record the earlier
of that date and the current last day. A termination before the first day leaves an empty
period. A release is terminal for the property lease. A company can record the release of an
existing term after disabling new Property registrations. An extension needs Property enabled.

## Storage and API

History starts with revision 1 from the immutable registration facts in `property_leases`.
Each change appends an immutable event and advances the current revision and last day on
the same lease row in one transaction. The original registration fields stay intact. The
event records who made the change and the exact agreement version. PostgreSQL enforces
exclusion on the current period. An exclusion conflict rolls back the event and its receipt.

Use the agreement tenant lock in READ COMMITTED. The projection guard admits only the next
event inserted in that transaction. The grant covers only the projected columns. The
registration and extension take the agreement lock before the configuration lock.

Use GET and POST on `/v1/businesses/{business_id}/property/leases/{lease_id}/terms`. GET
pages from newest to oldest including the original registration. POST accepts `extend`
or `release`, the expected term revision and the exact agreement revision. It returns the
new historical revision. A retry with the same idempotency key returns that same revision.
The existing lease GET and registration replay return the originally recorded lease.
A term revision with no occupied days has `ends_on` set to null.

## Evidence

Verify extension, an overlap rollback followed by a retry, shortening at the inclusive
boundary, release before the first day, module disablement, exact replay, authorization,
concurrent changes under an observed lock, and upgrade from populated 0115. Move-in and
condition evidence follow in 3c.
