# PROPERTY-01, catalog backend

The first backend slice of [PROPERTY-01](PACKAGE_PROPERTY01_PLAN_2026-11-14.md) starts at
`ef00defc97e134a46264004e6c55263544bd16bf`. It defines the internal catalog and its access rules.

- A parcel, building or unit belongs to one company and branch. The identifier, branch and type
  are fixed. A parcel has no parent, a building can name a parcel, and a unit must name a
  building. Typed foreign keys enforce the same company and branch and rule out cycles.
- Revisions are append-only. Every revision has a name and parent, and a company-only companion
  record with the owner and manager counterparty references. The roles can change independently.
  This slice models one counterparty per role and records its change at the time of the revision.
- A company-wide owner or manager may use the new `property.manage` permission for writes and
  history. An owner or manager scoped to a branch may read that branch with `property.read`.
  Scoped users see catalog fields only. Support and delegation do not grant these permissions.
- Under `/v1/businesses/{business_id}/property`, `GET /objects` is paged,
  `GET /objects/{id}` returns the public catalog fields, `GET /objects/{id}/history`
  returns private revisions to authorized company-wide members, and `PUT /objects/{id}`
  writes one revision and its audit entry. A retry with the same idempotency key returns the
  exact revision it wrote, from an identifier-only receipt. Concurrent writes serialize per
  object and a stale revision receives 409. Tenant and branch scope are enforced in PostgreSQL.
- The module depends on counterparties. It is registered as implemented and waits for package
  acceptance before enablement. Migration 0112 adds catalog tables without modifying earlier
  migrations. Configuration publication and shared back-end gates retain their existing behavior.

The next slice adds the catalog screen and browser coverage. Publication and showing use
ADR-0022 in a later slice. Ownership shares, historical effective dates, external portal grants
and regulated workflows remain outside this backend slice.
