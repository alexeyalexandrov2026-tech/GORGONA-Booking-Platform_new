# K1c review by the K1d executor — 2026-10-16

**Not independent.** The K1d executor (a different agent from the K1c author) read
the K1c source before building on it. Nothing was run for this review; every point
below comes from reading `0c72a71`/`46ab31d`. It does not replace the independent
review that remains a gate for package K.

## Scope read

`0044_provider_receipt_inbox.sql`, `0045_provider_receipt_attestations.sql`,
`providers/inbox.py`, `providers/authenticated_receipts.py`,
`db/provider_receipt_guard.py`, `db/bootstrap.py` (writer role), the fixtures of
`test_provider_receipt_attestations.py` and `test_provider_event_inbox.py`,
the K1c handoff and self-review, the K plan and ADR-0027.

## Findings

| id | Level | Place | Observation | Disposition |
|---|---|---|---|---|
| R1 | Medium, traced | `0045`, column `verification_config_id`; `authenticated_receipts.py`, `ReceiptVerifierBinding` | The attestation records a verification configuration ID, but no table or key stands behind it: any UUID is accepted. The caller also supplies the tenant, connection, book, policy and signing keys together. The database therefore cannot say which key was entitled to verify deliveries for a connection; the ID looks like provenance but proves nothing | K1d: versioned verification-config authority, attestation key to it, keys selected only through it |
| R2 | Medium, traced | `authenticated_receipts.py` | No server-controlled routing: the trusted process must already know tenant and connection. The plan requires a server-owned ingress identifier and a minimal read-only routing record | K1d: routing record readable only by the writer group |
| R3 | Low, traced | `0045`, `check_provider_receipt_attestation` (also `0044`, `check_provider_receipt`) | Binding fields are compared with `<>`, which yields NULL rather than refusal for a missing value. Safe today: `provider_receipt_facts_valid` requires `namespace`, `account_id` and `api_version` as strings, and connection columns are NOT NULL | Recorded; a later trigger should use `is distinct from`. Migrations 0044/0045 stay unchanged |
| R4 | Low, by design | `0045` grants | The writer may set any company context and, with UPDATE(revoked), revoke a connection (needed for FOR SHARE). It is a trusted global verifier; revocation only reduces authority | Recorded; K1d keeps the same shape for its new authority |
| R5 | Note | `0044` grants | The ordinary runtime can still archive receipts (K1b receipt-only design). Only an attestation distinguishes a signature-checked delivery | Unchanged; documented in ADR-0027 K1b note |

Not found: a way for the runtime to insert, alter or delete an attestation; a way to
attest a delivery whose namespace, account or API version differs from its connection;
a way to attest under a branch context; an unguarded writer role (mixed membership,
ownership, CREATE or unrelated table rights are refused before each write).

## What K1d takes from this

R1 and R2 define the K1d slice. R3–R5 are recorded limits. See the
[K plan checkpoint](../../PACKAGE_K_PLAN_2026-10-15.md) and the
[ADR-0027 K1d decision](../../../adr/0027-provider-events-and-reconciliation.md).
