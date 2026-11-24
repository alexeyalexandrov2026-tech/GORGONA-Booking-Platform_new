# PROPERTY-01 · 3c · Record move-in condition

## Acceptance

A company-wide owner or manager records one move-in per lease. The command names the reviewed
lease term revision, the actual civil day of move-in, a condition report and a bounded list of
photos. The day is inside the recorded lease period and at or before the property's current
local day. The condition report and photos are exact ADR-0020 document versions with stored
files. A photo has stored JPEG or PNG data. The condition report has the report category.

The command and the release of a lease use the same tenant agreement lock and READ COMMITTED.
The submitted revision must equal the current lease term revision. Once a move-in is recorded,
the last day of possession cannot move before that actual day. The move-in record keeps its
lease, term revision, actor, day and file references when the term later changes.

## Reuse and API

Use the same company authorization and reference-only commands as the lease APIs. Use the
ADR-0020 document upload, hash, version and verified download paths. Adapt the transaction and
ordered evidence pattern from rental inspections 0105. Under the lease route, GET and PUT
`/{lease_id}/move-in` read and record the report. PUT returns that immutable report on an exact
idempotent retry. File bytes are served by the existing document endpoints. Use restrictive
company scope for both the report and its photo rows.

## Checks

Upload valid synthetic documents and photos through the existing API. Verify stale term
revision, impossible move-in days, incompatible media, stable retries, exact historical
documents, tenant and branch isolation, a competing release, and upgrade from populated 0116.
Show that a failed photo leaves neither a report nor a command receipt and that a release
cannot erase a recorded occupied day. Move-out condition and financial calculations follow
their existing PROPERTY-01 phases.
