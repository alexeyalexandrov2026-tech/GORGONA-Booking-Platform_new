# K1b storage conformance review

Inline review of base `84d4177e97ebc16e1743dcb995abf54c1b81269d`; corrected source `db96f005442201428700995c09f028e1b6da08c0`. This is not an independent
security review or complete K acceptance. Scope: providers/inbox.py's real write flow,
provider_receipt_guard.py, migration0044, shared ledger/financial guard approvals and tests.

| Finding | Reproduction against original guard | Correction/evidence |
|---|---|---|
| M1:trigger binding and WHEN incomplete | Same-named function in another schema or WHEN(false) passed guard | Exact function OID/signature and unconditional approved trigger shape;two RED→GREEN cases |
| M2:shared immutable function not approved | Replace gba.reject_ledger_mutation body with RETURN NEW;receipt guard accepted | Reuse packaged ledger approval, compare body/language/signature/config;RED→GREEN |
| M3:FK parent namespace omitted | Move actual ledger_books into another schema;receipt guard accepted same parent relname | Require gba-qualified FK parent;RED→GREEN |
| L1:trigger arguments omitted | Add unexpected trigger argument;guard accepted | Require zero arguments, column filter/transition/clone metadata absent;RED→GREEN |
| L2:column PUBLIC ACL omitted | Grant SELECT(facts) to PUBLIC without table ACL changes;guard accepted | Check column ACL separately;RED→GREEN |

All six failures were specifically DID NOT RAISE DatabaseUnavailableError, not fixture
setup errors. All six now refuse before archive writes. Each test verifies health before
damage and after restoring the exact packaged definition. Runtime permission tests and
existing ledger/receipt/upgrade/financial regressions run in focused and full gates.

Threat-model limit: these mutations require owner/schema privileges. Ordinary runtime
cannot perform them. PUBLIC grant reproduction proves missed conformance, not observed
data exfiltration; existing RLS and schema privileges still apply. This guard detects
the inspected drift at its check; it cannot defend against a malicious database owner
or prove concurrent privileged schema changes impossible.

Unfixed architectural boundary (by design, not a green admission claim): runtime can
insert typed archive facts. Those facts are not authenticated financial provenance.
Before K2/K3 use a separately permissioned receipt writer/attestation or cryptographic
re-verification, with direct SQL forgery denials. Admission of a connection alone does
not authenticate its rows. Public HTTP remains closed until scoped trusted routing,
bounded reads, quotas/retention and durable acknowledgement/failure/replay tests exist.
No money operation or readiness is authorized by this review.
