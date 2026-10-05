# ADR-0020 — Counterparties, documents and contracts

> Source snapshot received 2026-10-04; original preserved in the owner's handoff777 archive. Current E1 implementation and fresh evidence are in [acceptance](../plan/evidence/2026-10-05-counterparties/ACCEPTANCE.md) and [handoff](../plan/NEXT_AGENT_PACKAGE_E1_2026-10-05.md). E1 migration 0015 has run only in disposable tests. E2/E3 and production migrations remain planned. Initial context below describes the pre-E1 source snapshot.


Status: accepted by the owner on 2026-10-04 together with the package plan (package E of stage 1). Planned for implementation in steps E1–E3, each with its own migration, commit, full CI and acceptance record; this ADR is updated with the exact commits when each step is verified.

## E1 implementation, 2026-10-05

Counterparty cards, contacts, explicit match decisions and confirmed booking links
are implemented with migration 0015 and permission map v4. The module remains
`implemented` until exact code CI is green; it cannot yet be enabled by the real
registry. E2/E3 remain planned. Existing booking customer snapshots are untouched.

Historical card views exclude current merged-child relationships; the separate
`merged-from` endpoint exposes those, preserving immutable command replay. Merge
and separation decisions identify the exact card revision, are unique for it,
and must create the matching version in the same transaction. SQL rechecks the
graph at version insertion, rejecting staged cycles and chains. A separation
restores the pre-merge card state with a new version.

The access guard checks 34 definitions and five optional-module gate triggers.
Company-wide E1 handlers invoke it too. The optional and booking gate functions
must be VOLATILE so reads after the configuration lock use a fresh snapshot;
the guard verifies volatility and other executable metadata, not source alone.
Reference: [PostgreSQL 18 volatility](https://www.postgresql.org/docs/18/xfunc-volatility.html).
Mutation, staged-SQL, runtime API and real desktop/mobile regressions plus bounded
independent source review are recorded in acceptance. No production, provider or
complete industry acceptance is implied.

## Context

The master plan names counterparty, contact and contract (§12.2 "Контрагент, контакт и договор") and document, version and signature (§12.2 "Документ, версия и подпись") as shared models, and stage 1 (§13) includes counterparties and documents. §4 lists the modules "Клиенты и контрагенты" (people, companies, contacts, requests, history, contracts, consents) and "Документы" (templates, versions, signatures, attachments, validity, access). §12.4 requires matching with a preliminary check, says that the same name or phone does not prove a match, and that disputed merges are confirmed by the data owner while link history is kept. §8 requires that a contract change never rewrites the agreed original. §12.5 requires validation of uploaded files and an audit of contracts; §12.8 says a signature is not confirmed until the server answers.

Today nothing of this exists. The `counterparties` and `documents` modules are registered as `planned` (ADR-0019). Customers of bookings exist only as a per-booking snapshot (`gba.booking_customers`: name, email, phone), and the "clients" list groups bookings by exact strings. There is no file storage, no malware scanner, no Azure storage account (ADR-0012 has none) and no Docker on the development machine.

Owner decisions for this package:

- Files are stored in PostgreSQL, at most 10 MB each, with validation but without an antivirus; the status is "not scanned", and uploads answer 503 in staging and production until a scanner is configured.
- Existing booking customers are linked to counterparties only by an explicit confirmation of the data owner; booking data is not changed.
- Only owners and managers with company-wide access see counterparties, contacts, documents and contracts; branch-limited members, delegates and platform support do not.
- Isolation defects found while planning are fixed first, in a separate step (E0).
- Approval of the plan authorizes implementation; each step is committed and pushed to the working branch without merge, deployment or production migration.

## Decision

### Shared rules

- **Permissions.** `counterparties.read`, `counterparties.manage`, `documents.read`, `documents.manage` belong to the manager role (and so to owners); `PERMISSIONS_VERSION` becomes 4. They are not delegable (ADR-0017) and not part of platform support. Every route is company-wide only: branch-limited members, delegates and platform support are refused by the existing authorization paths. Contracts use the counterparty permissions.
- **Insert-only data.** Identities are immutable and carry a client-generated UUID; content lives in append-only versions; "current" is the latest revision; links are event logs with a sequence (linked → unlinked → linked …). Nothing is updated or deleted, so history keeps its original meaning.
- **Commands** follow ADR-0019: `Idempotency-Key`, `expected_revision` (or `expected_sequence`), audit in the same transaction, a per-module advisory lock (`counterparties`, `documents`). Idempotency receipts store only references (identifiers, revisions, sequences); a replay re-reads the immutable rows, so receipts hold no personal data and no file bytes. Audit details hold identifiers, revisions, states, roles, counts, dates, media type, size and SHA-256 only — never names, e-mail addresses, phone numbers, titles, summaries or file names.
- **Module gate in the database.** One function `gba.require_enabled_module()` with the module id as trigger argument is attached `BEFORE INSERT FOR EACH ROW` to every table of a module (a table shared by two modules gets two triggers). It takes the shared advisory lock `gba:business-configuration:{business}` that publication holds exclusively and raises SQLSTATE `GBM01` unless the module is enabled in `business_module_states`. Unlike booking (enabled until a publication disables it), these modules are disabled unless a published configuration enables them; publication already writes a state row for every optional module. The API maps `GBM01` to 409 `MODULE_DISABLED` and checks the module early. Reads, history and file downloads stay available when a module is disabled (§4); a replayed command returns its stored result.
- **Access boundary.** Every new table has FORCE RLS, the tenant isolation policy and the restrictive company-only policy `<table>_unrestricted_scope`. The schema guard checks these definitions and every gate trigger (timing, enabled state, function, argument) and the gate function source; damage fails readiness. Approved definitions grow from 29 to 34 (E1), 38 (E2) and 40 (E3); gate triggers from 5 to 10 and 12, plus the booking trigger.
- **Readiness of modules.** In the commit that adds a module's code the module becomes `implemented` with its limits; it still cannot be enabled. Integration and browser tests enable it through the real draft → validate → publish path with a test-only registry override, and a separate test proves the real refusal (`MODULE_NOT_READY`) without it. After green CI on that exact commit, the acceptance commit raises the module to `technically_verified` with the evidence path. `MODULE_REGISTRY_VERSION` is not changed: readiness is not a structural registry change, and a version change would invalidate every validated draft.

### E1 — counterparties, contacts and matching (migration 0015, module `counterparties`)

- `counterparties` (kind `person` or `organization`, fixed) and `counterparty_versions`: display name, optional legal name, tax identifier and registration number (format checked, no check digits, never invented), e-mail (lower-cased), phone with derived digits, roles from `customer`, `supplier`, `contractor`, `partner`, state `active`, `archived` or `merged` with `merged_into`.
- Contacts are child rows of a counterparty version (at most 20): name, job title, e-mail, phone. One card is one revision with one `expected_revision`.
- Matching is a suggestion only: strong reasons are equal normalized e-mail, phone digits, tax identifier or registration number; equal normalized name is a weak reason. Nothing is merged automatically. A pre-creation check takes identifiers in the request body, never in the URL.
- `counterparty_match_decisions` records `merged`, `distinct` and `separated` (the reversal of a merge). A merge marks the duplicate `merged` with a new version and moves nothing: contacts, links, documents and contracts stay where they were and the surviving card shows them. Merging into a merged record or merging a record that has merged duplicates is refused.
- `counterparty_booking_links` records confirmed links between a booking customer and a counterparty, with the basis (`email`, `phone`). Candidates are bookings whose customer details match the counterparty or its contacts after normalization; the server re-checks that a booking is still a candidate when the link is confirmed. `booking_customers` is never modified.
- API under `/v1/businesses/{id}`: `counterparties` (list with search and paging), `counterparties/{cid}` (read with revision, history, save), `counterparties/match-check`, `…/duplicates`, `…/match-decisions`, `…/booking-candidates`, `…/bookings`, `…/booking-links`.
- Web: a "Counterparties" page in the management navigation for company-wide owners and managers, with search, card, contacts, history, duplicates and booking links; read-only with an explanation when the module is disabled.

### E2 — documents and files (migration 0016, module `documents`)

- `document_files`: immutable; SHA-256, size (1 byte to 10 MB, equal to the stored length), media type `application/pdf`, `image/png` or `image/jpeg`, sanitized file name, validator version, content. There is no scan status column: the API reports `not_scanned`; a future scanner records its results in its own table.
- `documents` and `document_versions`: title, category (`agreement`, `certificate`, `invoice`, `report`, `other`), optional validity dates (expiry is computed, never stored), archived flag, optional file. `document_counterparty_links` links documents to counterparties (both module gates apply).
- Upload is `PUT /document-files/{file_id}` with the raw body, the declared `Content-Type`, the file name in a header and an `Idempotency-Key`; no multipart and no new dependency. In staging and production it answers 503 `FILE_SCANNING_NOT_CONFIGURED` before reading the body. Otherwise the caller is authorized and the module checked before the body is read; the body is read with a 10 MB cap (413 also without `Content-Length`); the type is detected from the signature and must equal the declared type (415); a PDF is refused when it is encrypted or unreadable or contains active content (`/JavaScript`, `/JS`, `/Launch`, embedded files, rich media, XFA, form submission, data import, remote go-to), including inside compressed streams, decompressed with a budget; `/OpenAction` alone is allowed. The file name is normalized, reduced to a base name, stripped of control, bidirectional and reserved characters and names, limited to 120 characters and given the extension of the detected type.
- Download re-checks SHA-256 and answers with `Content-Disposition: attachment`, `nosniff`, `Cross-Origin-Resource-Policy: same-origin` and `Content-Security-Policy: default-src 'none'; sandbox; frame-ancestors 'none'`; the framing middleware appends to an existing policy instead of replacing it. Downloads are audited. The web client checks type, size and SHA-256 before saving and never previews files inline.

### E3 — contracts (migration 0017, module `counterparties`)

- In code the model is named `agreements` (the `*_contracts.py` suffix already means API schemas); the interface says "Contracts".
- `agreements` (counterparty, optional own legal entity) and insert-only `agreement_versions`: state `draft`, `agreed` or `terminated`, title, optional number, summary and effective dates; an agreed or terminated version carries the signing date and the attestation `signed_outside_platform` (there is no electronic-signature provider), optionally a signed document version; a terminated version carries the termination date and the content of the last agreed version unchanged. Allowed transitions: none → draft, draft → draft or agreed, agreed → draft (an amendment) or terminated; terminated is final. An agreed version is never rewritten. Expiry is computed from the dates.
- API: `counterparties/{cid}/agreements`, `agreements/{aid}` (read, history, save a draft), `agreements/{aid}/agree`, `agreements/{aid}/terminate`. A merged or archived counterparty cannot get new contracts. The interface shows "signed" only after the server answers.

## Acceptance

1. Every write is idempotent with an expected revision; replays return the stored result; a reused key with another body is refused; two concurrent changes of the same revision give one success and one conflict (CORE-02), including concurrent merges, links of the same booking and uploads of the same file id.
2. Matching never merges by itself; merge, "not a duplicate" and separation are recorded and reversible by a new decision; booking links are confirmed by a person and `booking_customers` is unchanged byte for byte.
3. With the module never published or disabled, every write — API and direct SQL — is refused, while reads, history and downloads work; a publication racing a write leaves no write after the disabling commit.
4. Files: exactly 10 MB is accepted and one byte more is refused with and without `Content-Length`; type mismatches, active PDF content (also compressed), encrypted PDFs and unsafe names are refused; staging and production refuse uploads; receipts contain no file bytes; download headers and integrity check hold.
5. An agreed contract version stays unchanged after an amendment and a termination; illegal transitions are refused also by direct SQL.
6. Artists, front desk, branch-limited members, delegates, platform support and other companies are refused; revocation blocks the next command (CORE-03); direct SQL cannot change history; damaged policies, gate triggers or the gate function fail readiness.
7. Scenarios without duplication or leakage: a small business keeps one counterparty that is both customer and supplier; members of a group see nothing of each other's records; a hybrid business with several profiles has one list.
8. Real browsers per step: save after a lost response with the same key, history, conflicts, duplicates and links (E1), upload and verified download (E2), draft, agree, amend and terminate (E3); mobile width and accessibility; SQL confirms versions, links and audit without personal data.

## Consequences

The runtime requires migrations 0015–0017. File content lives in the database: backups and restore cover it, but database size grows with files, and each upload or download holds up to about two copies of the file in memory. A storage account with private endpoint and a malware scanner are required before uploads are allowed in staging or production; that is a separate decision under ADR-0012.

Out of scope and left for later increments: consents, requests, document templates, an electronic-signature provider, custom fields, access restrictions on individual documents, retention and erasure of personal data (immutable versions will need a reviewed redaction procedure; older booking receipts still contain customer details), import by source and external identifier, storage quotas, offline caching of documents (they are never cached), export beyond the paged reads, access for front desk and artists, and the carrier role (it arrives with the transport module).
