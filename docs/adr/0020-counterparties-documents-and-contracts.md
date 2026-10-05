# ADR-0020 — Counterparties, documents and contracts

## E3 implementation, 2026-10-05

Contracts ("agreements" in code) are implemented with migration 0017 on branch
`claude/package-e3-agreements` (based on accepted E2 `c5a3908`), inside the already
verified `counterparties` module: its permissions, lock and gate apply, and its
`limits` now describe contracts (evidence is added by the acceptance commit).
Clarifications:

- SQL enforces the transitions, contiguous revisions, attested fields per state
  (`draft` has none; `agreed` has `signed_on` and the attestation; `terminated` also
  `terminated_on ≥ signed_on` and `terminates_revision`), and that agreeing keeps
  the drafted title, number, summary and term. Signing dates cannot be later than
  the latest calendar date on Earth (UTC+14), checked by the API and by SQL.
- Owner decision 2026-10-05: a termination acts on the latest agreed (executed)
  version, never on an unsigned amendment draft. It is allowed from `agreed` and
  from an amendment `draft` that follows an agreed version (`draft → terminated`,
  never for a contract that was not agreed). The termination row names that
  revision in `terminates_revision` and repeats its content exactly, including the
  signing date, attestation and document reference. An open amendment draft stays
  in the history and is reported as `abandoned` (closed by the termination); the
  audit records `terminates_revision` and `abandoned_draft_revision`.
- Owner decision 2026-10-05: `terminated_on` is the day the termination takes
  effect and may be in the future. Until then the agreed version stays legally in
  force. Views expose `in_force_revision` (the latest agreed revision up to the
  viewed one; kept on the termination) and `terminates_revision`; list summaries
  show the signing date of the version in force.
- A new contract and every draft or agreement need the card's latest version to be
  `active`; termination is allowed for archived or merged cards. A counterparty's
  contract list includes contracts of duplicates merged into it.
- The optional signed copy is a reference to one saved document version (tenant-
  scoped foreign key); when agreeing without one, the draft's reference is kept.
  Legal entity references are tenant-scoped too; the counterparty and legal entity
  of a contract never change.
- Audit details hold revision, counterparty id, amendment flag, document presence
  and dates only. The guard checks 40 definitions and twelve optional gates.
- The web shows contracts in the counterparty card. A contract is shown as agreed or
  terminated only from a server response; the attestation checkbox and signing date
  are required before the agree command can be sent. The card always shows the
  agreed version in force, also during an amendment draft and until a recorded
  termination takes effect; the status uses the viewer's calendar day, as document
  validity does.
- Review fixes before the code commit: list rows carry the agreed version in force
  as `in_force` (revision, title, number, term, signing date), so an open amendment
  never describes the unsigned draft as the contract; only the draft immediately
  before a termination is `abandoned` (earlier drafts were superseded); every save
  of an open amendment is audited as an amendment; a new amendment starts without
  the agreed version's signed copy; a contract needs its first version before
  commit (deferred constraint trigger); text the database refuses (including C1
  controls) answers 422, never a conflict; contracts listed through a merged
  duplicate are read-only there except termination; agreeing is disabled while the
  draft form has unsaved edits; history pages beyond 50 versions load on request.
- Limits: a recorded termination is final (withdrawing a scheduled termination
  needs a future version state); a company-wide contract has no single time zone,
  so "in force" vs "terminated" on the effective day follows the viewer's date.

## E2 implementation, 2026-10-05

Documents, immutable files and counterparty links are implemented with migration
0016 on branch `claude/package-e2-documents` (based on E2-A `4a6f63b`). Code
`2ab24f3` passed exact push CI (run 37289072512); a separate acceptance commit
promotes `documents` to `technically_verified` (registry version 1, explicit
publication still required). Code-commit fixtures used the test-only override and
proved the real `MODULE_NOT_READY` refusal; acceptance fixtures use the real registry.
[Evidence](../plan/evidence/2026-10-05-documents/ACCEPTANCE.md).

Clarifications made while implementing:

- The early module check before the body is read is skipped only when the caller's
  upload key already holds a stored result, so a completed upload can still be
  replayed after the module is turned off; a new key is refused before any byte is
  read. The final transaction (claim → module check → insert) remains the arbiter.
- The guard checks 38 definitions and ten optional-module gate triggers (five E1,
  four `documents`, plus the `counterparties` gate on document links); each trigger
  is matched by name, timing, enabled state, function and exact argument, and must
  have no WHEN clause and not be a constraint trigger (also for the booking gate).
- An identical upload retried by the same user after its idempotency key expired
  returns the stored file; any other reuse of a file identifier is a conflict.
- Files are linked to document versions by a tenant-scoped foreign key, so another
  business's file identifier is an unknown reference (422). Links require the latest
  document version not archived and the latest counterparty version `active`; the
  trigger takes the exclusive documents lock and the shared counterparties lock, so
  it is ordered against merges and archiving. Unlinking a merged card is allowed.
- A counterparty's documents include links to duplicates merged into it, mirroring
  booking links. Downloads of any saved version are audited (`document_file.downloaded`
  with document and revision only); an integrity failure answers 500
  `FILE_INTEGRITY_FAILED` and is not audited as a download.
- The web client hashes the chosen bytes before upload, sends exactly those bytes,
  compares type, size and SHA-256 of the stored file, and verifies type, size,
  `X-File-SHA256` and the computed SHA-256 before saving a download as an attachment.

## E2 security prerequisite, 2026-10-05

[ADR-0021](0021-bounded-file-validation-profile.md) defines the bounded initial
file profile and preserves existing API CSP policies. This is a prerequisite,
not E2 storage/API/UI acceptance: documents remains planned and migration0016
is not introduced. Reject both external GoToR and embedded GoToE, optional-type
attachments (EF/FileAttachment),3D lifecycle scripts and unknown capabilities.
No new dependency or scanner was introduced; general-format/render safety is
not claimed. [Evidence](../plan/evidence/2026-10-05-file-validation/ACCEPTANCE.md).

> Source snapshot received 2026-10-04; original was recorded in the owner's handoff777 archive (that Desktop directory is absent at the October-5 recheck). Current E1 implementation and fresh evidence are in [acceptance](../plan/evidence/2026-10-05-counterparties/ACCEPTANCE.md) and [handoff](../plan/NEXT_AGENT_PACKAGE_E1_2026-10-05.md). E1 migration 0015 has run only in disposable tests. E2/E3 and production migrations remain planned. Initial context below describes the pre-E1 source snapshot.


Status: accepted by the owner on 2026-10-04 with the stage-1 package plan. E1 has exact-code CI evidence and a separate technical-readiness acceptance; E2/E3 remain planned. Each step has its own migration, commit, full CI and acceptance record.

## E1 implementation, 2026-10-05

Counterparty cards, contacts, explicit match decisions and confirmed booking links
are implemented with migration 0015 and permission map v4. Code `2392566595a2df59f8ec3f073ed9bf184df6447f` passed exact push and PR CI (599/1
in 118.52 s and 171.17 s). This separate acceptance promotes it to
`technically_verified`; registry version stays 1 and explicit business publication
is still required. The initial implementation's real refusal is evidenced in CI;
acceptance API/browser fixtures now use the unmodified registry. Acceptance
`e68ce907ba0459ab99e4c71137c044694a920be1` also passed exact PR/push CI: 599/1 in
173.32 s and 163.07 s, with required container/browser/PostgreSQL gates. E2/E3 remain planned. Existing booking customer snapshots are untouched.

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
