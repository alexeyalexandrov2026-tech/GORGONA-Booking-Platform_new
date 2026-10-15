# K1b architecture and reuse

Source `543b73221ac1dd0aa738bd8cf33dd468366ef27a`. Reused K1a's frozen SignedStripeEvent, normalized facts and synthetic
signing fixtures; existing Versioned, DomainError, psycopg Jsonb/transactions,
tenant_transaction, FORCE RLS/current tenant/location, reject_ledger_mutation,
migration checksum runner and ledger/upgrade fixtures. No dependency added.

Inspected db/pool.py, bootstrap.py, provisioning.py, migrate.py, migrations0001/0020/
0031/0043, H4 contracts/guard, ledger/stock races, K1a contracts/decoder, K plan and ADR0027.
H4 stays a declaration. The customer host resolver is not a provider authority; no
global routing read, new role, security-definer function or HTTP caller is introduced.

Connection identity is separate from event identity and delivery digest. A connection
is receipt-only forever in this schema; its tenant/book/account identity cannot be
edited or reassigned. Revocation is monotonic. Runtime's one-column UPDATE grant
permits revocation and FOR SHARE without allowing provisioning or a positive capability.
Both reads and writes force company-scoped RLS. Future user/ingress authorization
must be implemented at its actual caller before exposure.

These ordinary runtime-writable archive rows must never become payment authority.
Before K2/K3, require a separately permissioned receipt attestation/writer or renewed
cryptographic verification that the financial runtime cannot forge; verify the direct-SQL
denials. A later positive connection admission alone does not authenticate an archive row.

INSERT ON CONFLICT DO NOTHING waits on an uncommitted identity; a following READ
COMMITTED statement reads the winner. There is no no-op UPDATE of immutable history.
Connection-row SHARE locks serialize revocation. Event and original delivery commit
together; deferred completeness fails closed if transaction scope changes. No provider
network call or ledger lock occurs. SQL validates normalized storage shape, not the MAC.

Current official PostgreSQL18 sources consulted:
[SELECT privileges/locking](https://www.postgresql.org/docs/18/sql-select.html),
[READ COMMITTED conflict visibility](https://www.postgresql.org/docs/18/transaction-iso.html),
[forced row security](https://www.postgresql.org/docs/18/ddl-rowsecurity.html).
Tests exercise the chosen mechanisms on PostgreSQL18.6. Throughput, power-loss durability,
real provider availability and operational acceptance are not claimed. Independent review
is NOT TESTED before ingress exposure. Storage quotas/retention, routing, workers and
financial effects remain ahead. No external receipt route is wired by this slice.
