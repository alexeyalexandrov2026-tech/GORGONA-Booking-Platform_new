# K1c inline self-review and boundaries

Source `0c72a719cb9743a1f3cd7d60ea26bc46e9e2638c`;this is not independent security review. The source/test record
is [CHECKS.json](CHECKS.json),with [validation](VALIDATION.md).

Observed and corrected test-first:

- Nested transaction could return after savepoint release:require an IDLE borrowed
  connection and own the outer transaction;real deferred commit failure proves rollback.
- SET ROLE hid an original runtime login:SQL checks session_user runtime membership;
  ordinary runtime cannot attest even after a deliberately misconfigured NOINHERIT grant.
- Noninherited dangerous parent escaped current-role checks:inspect role ancestry too.
- BootstrapSpec repr exposed source-declared FAKE unit passwords:password fields repr=False;
  generated real fixture credentials were never printed.
- Legacy CASCADE cleanup omitted the new company policy/permission:restore packaged0045
  policy and writer execute grant,then assert healthy boundaries. Keep0043→0044 upgrade
  pinned to its own slice;new nonempty0044→0045 test checks archive preservation/no backfill.
- Full-3 exposed the preexisting MyShifts stale-response race after a date change.
  A natural repeat alone passed and was not treated as a fix. Add controlled old/new
  response ordering first,then allow only the latest load to publish screen state.
- Full-2 exposed pathological historical fixture-copy SQL after the100000-row scale test.
  Preserve the interruption as FAIL. A2s source-query-budget regression fails first;
  compute incompatible tenant IDs once in the test-only helper,retain filtering semantics,
  then verify both minimal synthetic filtering and actual historical migrations.

Trust/availability limits:

- SQL protects a trusted verifier's assertion;it does not compute a Stripe MAC. A
  compromised writer credential/code or database owner can lie. The ordinary API must
  never receive the writer DSN or signing keys. Local separate-logins proof does not
  establish deployed process/secret isolation;independent review remains NOT TESTED.
- Server-supplied binding/config UUID is not proof of actual merchant ownership,
  operational admission or key provenance. Receipt connections stay `not_admitted`.
- Ordinary runtime-writable archive rows remain untrusted. A forged exact digest with
  inconsistent facts fails closed and may block receipt availability;this is not an
  automatic repair/reconciliation feature. Only a fresh verified delivery can add a
  protected attestation. Conflicts need review;an attestation is not a payment.
- No HTTP handler,global routing,quota/retention enforcement,worker lease/operation
  identity or atomic G/H provider provenance exists. Do not expose ingress until bounded
  ASGI reads,commit-before-2xx,storage-failure/replay and deployment-isolation proof exist.
- Power-loss/process-kill durability,actual provider,container/exact K CI and complete
  K acceptance are NOT TESTED or separately BLOCKED. Manual attestation/readiness unchanged.
