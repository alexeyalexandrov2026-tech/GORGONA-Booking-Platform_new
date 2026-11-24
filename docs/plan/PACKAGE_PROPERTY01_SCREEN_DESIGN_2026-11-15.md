# PROPERTY-01, internal catalog screen

The second slice of [PROPERTY-01](PACKAGE_PROPERTY01_PLAN_2026-11-14.md) starts from the verified
[catalog backend](PACKAGE_PROPERTY01_CATALOG_DESIGN_2026-11-14.md) at
`d392d5d` on `codex/package-property-01-catalog`. It adds the management screen `/property/` and
no server change or migration.

- The screen reuses the management workspace, the signed-in management client and the strict
  response contracts. `GET /objects`, `GET /objects/{id}`, `GET /objects/{id}/history` and
  `PUT /objects/{id}` each have a strict schema; public views reject private party fields.
- Active owners and managers who are not delegates see the screen. A branch-scoped member reads
  the catalog fields of the branch only. The screen does not request history and shows no form.
  Company-wide owners and managers also see the owner, manager and revision history and the
  create and edit forms. The server still decides every read and command.
- A command omits a party field to keep it and sends `null` only when the member explicitly
  chooses "No owner" or "No manager". A new object omits unset parties. A new object keeps its
  identifier and each command keeps its Idempotency-Key until it succeeds.
- A stale revision is never retried silently. The form names the current revision and offers to
  reload the property; the member applies the change again on the new revision.
- The catalog shows loading, empty and read-error states, and the error offers a retry. Opening a
  property moves focus to its heading. Tables scroll inside keyboard-focusable regions, so the
  mobile page never scrolls sideways.

The browser test seeds a business, its configuration and parties through the routes on a
disposable PostgreSQL 18 database. Only a fixture accepts the module; the registry stays
implemented and not enableable. Chromium on desktop and mobile covers the company-wide owner,
a branch manager and the manager of an empty branch, with axe checks, and the database is read
back. Listings and showings follow in a later slice.
