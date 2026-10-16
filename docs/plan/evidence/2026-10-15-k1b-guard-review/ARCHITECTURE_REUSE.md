# Architecture and reuse — K1b guard review

Source `db96f005442201428700995c09f028e1b6da08c0`. Acceptance: the six reproduced schema changes refuse before receipt
storage, healthy approved schema continues to work, no financial authority is introduced.

Inspected the actual flow: providers/inbox.py record_event → provider_receipt_guard →
0044 connection SHARE lock / inbox and delivery INSERT / deferred completeness / caller commit.
Inspected existing db/ledger_guard.py and financial_guard.py catalog approvals, migration0020
shared immutable function and0044 packaged definitions, schema_guard/pool role boundary,
K1b/role/upgrade tests, K plan and proposed ADR0027/accepted ADR0024/current master/status/CLOUD.

Reused the existing guard pattern: function OID/qualified signature, no WHEN/args/column
filter, expected constraint-trigger metadata, approved language and function body. Exported
LEDGER_IMMUTABLE_SOURCE from ledger_guard's existing packaged approvals, instead of keeping
a second approval body in receipt storage. FK parent is schema-qualified; column ACLs are
checked in the existing catalog round trip. No new dependency, role, table or service.
Runtime still uses ordinary tenant/company-scoped transactions and receipt-only authority.

Official PostgreSQL18 catalog references consulted for the actual metadata:
[pg_trigger](https://www.postgresql.org/docs/18/catalog-pg-trigger.html),
[pg_constraint](https://www.postgresql.org/docs/18/catalog-pg-constraint.html),
[pg_attribute](https://www.postgresql.org/docs/18/catalog-pg-attribute.html).
Observed behavior is tested on18.6; documentation alone is not test evidence.

This does not turn a schema guard or a typed SignedStripeEvent into receipt authenticity.
The archive is writable by the ordinary runtime, and no operational admission is supplied.
Do not feed its rows into K2/K3 as authority. The next local design must select a separately
permissioned authentic-receipt writer/attestation or cryptographic re-verification and
prove direct SQL forgeries cannot create financial authority. Do not grant that writer
general finance capabilities. Keep H4 declarations and manual attestation unchanged.
Public routing, bounded ASGI reads, commit-before-2xx, retryable storage failures,
retention/quotas, worker fencing and atomic G/H provenance remain unimplemented.
Independent review/actual provider/container/exact K CI remain unverified.
