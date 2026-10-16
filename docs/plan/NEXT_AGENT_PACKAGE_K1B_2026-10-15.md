# Next agent — K1b receipt storage, 2026-10-15

Current successor: [K1b guard review handoff](NEXT_AGENT_PACKAGE_K1B_REVIEW_2026-10-15.md).
The original K1b evidence below is historical; inspect the current Git state.

Local source `543b73221ac1dd0aa738bd8cf33dd468366ef27a`, branch `codex/package-k1b-inbox`, base `ffb176b3cc4bd83637eff29246f6045e0705b9d3`.
Checkout `C:/Users/alexa/.codex/worktrees/package-j-review2-fixes/Gorgona Booking`.
A documentation commit follows the source; inspect actual HEAD/status. K is local only.
Main remote fedd0f115f24aad52f6256298296e8c5123fb427; published J remains
codex/package-j-review2-fixes=df88c20687333668d39fe76a26eabca691e62cb0, CI158 historical PASS.

Read [validation](evidence/2026-10-15-k1b-receipt-inbox/VALIDATION.md), CHECKS.json,
[reuse](evidence/2026-10-15-k1b-receipt-inbox/ARCHITECTURE_REUSE.md),
[K plan](PACKAGE_K_PLAN_2026-10-15.md), [ADR0027](../adr/0027-provider-events-and-reconciliation.md),
accepted ADR0024 and current master/status/CLOUD_CODE_HANDOFF/AGENTS.

PASS:40 new cases; focused 252 passed in 79.86s (0:01:19); full 1884 passed, 4 skipped in 1502.59s (0:25:02); static/build/web114.
Existing development npm audit5high FAIL; runtime0 PASS. Four skips (3 container,
1 optional external site). Docker unavailable. Exact K CI and independent review NOT TESTED.

Initial full-1 had25 failed/1859 passed/4 skipped: an older test's DROP FUNCTION CASCADE
cleanup omitted the three new company policies. Guard refusal was correct. A narrow
RED proved it; test_location_access now restores packaged0044 policies and checks the
healthy boundary before/after damage. Full failure and subsequent green gates are retained.

Implemented migration0044, providers/inbox.py, db/provider_receipt_guard.py and real PG
tests. Internal caller must open a company-scoped READ COMMITTED transaction and supply
K1a's signature-checked model. ReceiptResult is provisional until commit. PostgreSQL
checks typed integrity, not a signature. Connections are synthetic owner fixtures,
always not_admitted, without secrets/config refs. No HTTP route, global routing lookup,
actual admission, worker or money effect. Exact retries add no rows; distinct digest
variants persist conflicts without overwrite. Three observed race waits, rollback/replay
and a nonempty0043 upgrade passed. All complete K acceptance rows remain NOT TESTED.

Next local work: review storage and design a separately verified operational binding
plus least-privilege server-controlled ingress configuration. Never treat H4 or a receipt
row as admission. Define storage quotas/retention before exposing an external caller.
Keep public HTTP closed until scoped authority, bounded ASGI reads,
commit-before-2xx, retryable DB failures and raw HTTP tests exist. Failing test first
for each defect. K2 fencing/operation identity, K3 atomic G/H provenance, K4 review UI/
retention and K5 actual admitted provider proof remain ahead. FIN-02/STOCK-01 stay
planned, ADR0026/0027 Proposed. Manual attestation must remain truthful.

Runtime can insert typed archive facts; PostgreSQL does not prove their signature.
Do not let K2/K3 trust those rows for money. Design a separately permissioned attestation/
writer or cryptographic re-verification and direct-SQL denials first; positive connection
admission by itself is insufficient to authenticate the archived facts.

Run folder `C:\Users\alexa\AppData\Local\Packages\Claude_pzs8sxrjxfjjc\LocalCache\Local\GorgonaBookingTests\package-k1b-20261015-ffb176b`: runner.py, run_gates.py, write_record.py, update_docs.py, validation
helper and STATE.md. Own api/.venv/Scripts/python.exe3.14.6, PG18.6. Use a new phase
directory/fresh owned cluster each run. write_record expects base ffb176b before source
commit; updater expects its source child. Do not rerun these against later HEAD.

No PR/merge/rebase/amend/reset/clean/force-push, readiness change, CodeRabbit, Azure,
production migrations/deploy, provider/funds/credential actions without separate direct
owner authorization. No K push; J's exception is not transferable.0001–0044 immutable
in this local history; next0045. One executor per checkout/cluster, inline/no extra agents.
Never touch other checkouts/processes/ports51454/51458/51474/51511. Races need observed
pg_locks waits. Credentials private/unprinted, owner they/them. Save STATE early; source
record before source commit, docs/handoff/prompt commit, final fresh documentation check.
