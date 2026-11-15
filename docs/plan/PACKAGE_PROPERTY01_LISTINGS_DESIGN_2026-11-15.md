# PROPERTY-01, listings and showings

Step 2 of the [PROPERTY-01 plan](PACKAGE_PROPERTY01_PLAN_2026-11-14.md) covers publication,
inquiries, showings on the shared occupancy of [ADR-0022](../adr/0022-shared-resource-occupancy.md)
and applications with a consent log. The product has no public storefront yet: the only
unauthenticated route (`/v1/holds`) is a development surface without authentication or rate
limiting. Anything that accepts data from the public therefore waits for its own decisions. The
step is split so that each slice can be verified on its own:

- **2a. Listings (this slice).** One listing per catalog object, versioned like the catalog.
- **2b. Showings.** A showing names a property object, a prospect counterparty, a period and
  optionally the staff member who leads it. It reserves the object's own resource (kind
  `property_object`, created with the first showing) and the staff resource through the shared
  occupancy in one operation, all or none, so two showings of one object or one person never
  overlap. Cancellation releases the allocations and keeps the history.
- **2c. Screens** for listings and showings on the existing Property screen.
- **2d. Public storefront, inquiries and applications.** Waits for the owner decisions below.

## 2a. Listings

- A listing belongs to exactly one catalog object and takes its company, branch and type from it;
  composite foreign keys keep them equal. A listing is never moved or deleted.
- Every save writes the next revision: state (`draft`, `published`, `withdrawn`), headline (1–120
  characters), optional description (up to 4000 characters, line breaks allowed), monthly rent in
  minor units (1 to 10^12) with an ISO-style currency code, and the date the object is available
  from. Revisions are append-only and serialized with the catalog object's lock; a stale expected
  revision receives 409 `PROPERTY_REVISION_CONFLICT`.
- `published` only marks the listing for the future storefront (2d). No public route exists.
- Under `/v1/businesses/{business_id}/property/listings`, `GET` is paged, `GET /{object_id}` returns
  the current listing, `GET /{object_id}/history` returns the revisions with who recorded them and
  `PUT /{object_id}` writes one revision with an audit entry. Reads use `property.read` within the
  member's branch; history and writes use `property.manage` and are company-wide. An exact retry
  with the same idempotency key returns the original revision, including after module disablement.
- Migration 0113 adds `property_listings` and `property_listing_revisions` with FORCE row security,
  tenant isolation, branch scope, company-only inserts and the `property` module gate. The schema
  guard checks these policies. The module stays implemented and not enableable.

## Owner decisions before 2d

1. Target jurisdictions for listings, applications and deposits.
2. How the public reaches a listing: a tenant site, a platform catalogue, or both; and the
   rate limiting and abuse protection it needs.
3. What personal data an inquiry and an application collect, the consent text and versioning, and
   how long the data is kept.
4. The screening provider, if any, and the rules a human decision must follow.
