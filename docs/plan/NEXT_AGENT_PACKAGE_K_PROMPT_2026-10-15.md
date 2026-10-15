Continue GORGONA Booking stage 2 Package K (FIN-02) from the local planning checkpoint.

Checkout `C:/Users/alexa/.codex/worktrees/package-j-review2-fixes/Gorgona Booking`,
local branch `codex/package-k-plan`, based on df88c20687333668d39fe76a26eabca691e62cb0.
Inspect actual HEAD/status first. The directory name is historical; do not assume it
is still on the J branch. Main must stay fedd0f115f24aad52f6256298296e8c5123fb427.

Read in order: docs/plan/NEXT_AGENT_PACKAGE_K_PLAN_2026-10-15.md;
docs/plan/PACKAGE_K_PLAN_2026-10-15.md;
docs/adr/0027-provider-events-and-reconciliation.md;
docs/plan/evidence/2026-10-15-package-k-plan/ARCHITECTURE_REUSE.md, VALIDATION.md and CHECKS.json;
stage-2 plan, accepted ADR-0024 and current master/status/CLOUD_CODE_HANDOFF.

K is a proposal, not implemented. All K-01–K-14 are NOT TESTED. FIN-02 and STOCK-01
remain planned, ADR-0026/0027 Proposed. The owner's generic continue authorized this
bounded local preparation, not provider access or a readiness promotion. The plan
contains concrete scope/test-target/reconciliation recommendations for their selection.
Do not treat H4 declarations as verified admission or call the H manual-attestation
confirmation API to fabricate a provider result. There is no Booking webhook/inbox/
outbox/worker or Stripe SDK in the current source. Reuse G/H invariants and the existing
typed auth/RLS/audit/command/harness patterns; add only the components of the selected slice.

Published J branch stays df88c20 with CI158 PASS, run38697747829. Its inherited source
has local full1748passed4skipped, focused141, web114; these are not K verification.
K's planning commit has local documentation checks only: publication and exact-head
CI NOT TESTED. No K branch push is authorized by the Package J publication exception.

Run folder `C:/Users/alexa/AppData/Local/Packages/Claude_pzs8sxrjxfjjc/LocalCache/Local/GorgonaBookingTests/package-k-plan-20261015-df88c20`,
validator validate_plan.py; use this checkout's api/.venv/Scripts/python.exe.
No PR/merge/rebase/amend/reset/clean/force-push, readiness change, CodeRabbit, Azure,
deployment, production migration, provider/funds/credential action without separate
direct owner authorization. Never request/output secrets. Migrations0001–0043 immutable,
next0044. One executor per checkout/cluster; no extra agents. Preserve other checkouts,
processes and ports51454/51458/51474/51511. Races count only with a pg_locks wait.
Use they/them for the owner; keep exact PASS/FAIL/BLOCKED/NOT TESTED and update handoff/prompt.
