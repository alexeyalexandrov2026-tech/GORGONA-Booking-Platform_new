# PROPERTY-01 — internal showings

This is slice 2b of the [listings plan](PACKAGE_PROPERTY01_LISTINGS_DESIGN_2026-11-15.md).
The catalog and listings stay on their published contracts.

- A showing records an object, a prospect counterparty, a branch inferred from the object,
  a bounded half-open interval and an optional active bookable employee resource. The latter
  uses the existing `artist` resource kind. Workforce-only `staff` resources remain bound to
  shifts. The first successful showing creates a dedicated resource for its object.
- Migration 0114 adds the showing and cancellation records and uses the shared occupancy table
  for the object and host. Creation uses ordered schedule locks and one transaction. PostgreSQL
  checks exact allocation references and rejects partial writes. Cancellation releases all
  allocations in its own transaction and keeps the original showing.
- Company-wide property managers and owners create and cancel. Branch-scoped managers and
  owners read their branch's schedule. Responses to schedule reads omit the prospect identifier.
  Creation requires the property module and its counterparty dependency. Cancellation remains
  available to release occupancy after disablement.
- Use the authenticated `/v1/businesses/{business_id}/property/showings` routes. Replaying a
  creation returns its initial state. Replaying a cancellation returns the same cancellation.
  Public booking and the management screen are later slices.
