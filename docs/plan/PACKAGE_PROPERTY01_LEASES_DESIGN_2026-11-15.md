# PROPERTY-01 · 3a · Record an exclusive unit lease

## Contract

An active, company-wide property manager or owner registers one unit against the current
agreed version of an ADR-0020 agreement. The operator supplies the unit, agreement and exact
revision. The agreement records an external signature attestation, a bounded term and a
reference to an immutable, unarchived agreement document version with a stored file. The
operator attests to the external signing and selects the relevant unit. GORGONA stores the
associated evidence and dates.

Use the signed version's effective dates as the first and last civil days of possession.
Both dates are inclusive. A lease ending June 30 and one beginning July 1 may coexist. Two
leases of the same unit that include June 30 cannot coexist. Scope exclusivity by tenant and
unit. A recorded lease retains the dates and document of the signed version even if a later
generic agreement event changes the agreement's current state. A draft amendment preserves
the current agreed version. A subsequent signed version or termination precludes new
registrations from the superseded version. One agreement can be registered once.

GET and PUT use the company-wide property boundary under
`/v1/businesses/{business_id}/property/leases`. PUT uses the existing idempotency receipt and
audit model. A replay returns the recorded lease even after new registrations are disabled.
A PostgreSQL exclusion constraint enforces the interval boundary. The insert guard takes the
same tenant lock as agreement changes and derives the dates from the exact signed version.
The registration transaction uses READ COMMITTED so the source read sees changes committed
while waiting for that lock.
Branch and other tenant sessions cannot read lease rows. The runtime can insert only client
reference fields and the recording actor. Saved lease rows are append-only.

## Verification

Exercise the normal API with the real agreement and document upload endpoints and disposable
PostgreSQL. Verify same-day conflict, next-day handoff, contention, source rejection, replay,
branch and tenant scope, schema guard drift, and upgrade from a populated 0114.

The next lease slice covers signed term changes and early release. Move-in, condition evidence,
charging rules, deposits, and reconciliation remain in the PROPERTY-01 plan. Showing schedules
continue to represent appointment availability. A lease represents exclusive possession.
