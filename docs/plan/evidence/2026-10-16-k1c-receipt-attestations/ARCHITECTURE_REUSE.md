# K1c architecture and reuse

Source `0c72a719cb9743a1f3cd7d60ea26bc46e9e2638c`. Loaded evidence-engineering and inspected the actual K1a/K1b write
flow, bootstrap.py/pool.py, packaged guard approvals, migrations0001/0009/0020/0044,
role/inbox/upgrade/CASCADE tests, proposed ADR0027/accepted0024 and current master/status/
CLOUD/AGENTS. No extra agent;the owner requested inline work. Other routed skill names
were not found in the local SKILL catalog. Routing alone is not verification.

Chosen design:use the existing PostgreSQL role boundary rather than a new signing-key
system or custom signature protocol. Reuse K1a's pinned SDK verification and frozen
minimal facts, K1b record_event/idempotency/SHARE revocation locks, scoped psycopg
transactions, bootstrap's identifier/SCRAM provisioning, schema guard catalog approvals,
and shared ledger immutable-history trigger. No new dependency or security-definer.
The required-suite MyShifts correction reuses component-local typed refs and effect
cleanup;it adds no cache,global state or new data layer. Existing workforce response
schemas validate the deliberately held real response in the browser regression.

Flow:trusted server binding+raw bytes→K1a signature check→safe dedicated writer role→
outer company-scoped READ COMMITTED transaction→K1b archive→protected attestation→commit→
typed result `signature_checked_not_admitted`. A borrowed INTRANS connection is refused
because releasing a savepoint would not establish durable receipt. Ordinary runtime
retains archive INSERT for compatibility,but cannot mint attestations or assume writer.
Runtime startup refuses writer authority. The writer's current/session and ancestor
roles must be safe and lack unrelated table privileges. SQL also checks original
session runtime membership so SET ROLE cannot hide a mixed login.

The attestation references `(tenant,event,delivery_sha256)`,not merely the original event.
A verified conflicting delivery is retained without trusting the original poisoned
facts;future K2 must review conflicts and join this exact delivery identity. New0045
never backfills authentication from existing archive rows. An opaque config UUID is
an audit reference,not an actual secret,merchant-ownership proof or verified admission.
No environment variable,public routing resolver or HTTP adapter is invented here.
The internal caller supplies a dedicated pool and trusted policy/key configuration.

Default bootstrap creates the NOLOGIN group;only an explicit optional writer role/
password spec creates a login and grants CONNECT to that database. Production use
requires operator-controlled bootstrap before0045 and actual isolated credentials;
none were provisioned outside owned disposable clusters. The writer may monotonically
revoke a receipt connection because FOR SHARE needs column UPDATE;reactivation and
other history mutations remain refused. No finance-table or general runtime membership.

Official PostgreSQL18 sources consulted:
[role membership/SET/INHERIT](https://www.postgresql.org/docs/18/role-membership.html),
[SELECT row-lock privilege](https://www.postgresql.org/docs/18/sql-select.html),
[role/privilege information](https://www.postgresql.org/docs/18/functions-info.html).
Actual selected behavior is tested on18.6.
The installed CPython 3.14
[sys.remote_exec](https://docs.python.org/3.14/library/sys.html#sys.remote_exec)
operated only on validated own pytest children: stack/SQL-plan diagnostics for full-2,
and failure-report capture plus a normal pytest stop for full-3. Only redacted reports,
stack locations and the own SQL plan were saved, without local-variable dumps or
credentials. The scripts contain historical PIDs and must never be rerun.
No profiler dependency was installed. [Limits](SELF_REVIEW.md) remain explicit;
there is no operational/payment authority or claim of production process isolation.
