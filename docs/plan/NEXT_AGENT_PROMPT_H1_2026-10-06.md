# Copyable prompt for the next agent — H1 persistence

Copy the following into the next agent's task. The authoritative local handoff is:
`C:\Users\alexa\.codex\worktrees\package-h-finance-plan\Gorgona Booking\docs\plan\NEXT_AGENT_PACKAGE_H1_2026-10-06.md`.
It and this prompt are also published in draft PR14.

~~~text
Continue GORGONA Booking Package H from the published H1 foundation.

Active repository:
alexeyalexandrov2026-tech/GORGONA-Booking-Platform_new
Delivery branch: codex/package-h-invoices
Draft PR: https://github.com/alexeyalexandrov2026-tech/GORGONA-Booking-Platform_new/pull/14
Planning parent: codex/package-h-finance-plan /925ae02b581d22cf1e7897a3d94844b8ebc24648
Accepted G: codex/package-g-ledger-review /5be6e7abd7b552903a4f4b2884b150c62532c17d
Reviewed API source:843d0b3d1808e8de56ac732ad39107caa700426e.
Published foundation checkpoint:da3966b571062654993f72c8f65c23ab2c843829.
That checkpoint's CI37534227319 passed909 tests/1 optional skip. Refresh the
current branch HEAD and exact-head CI; the handoff itself is a docs-only successor.

Read docs/plan/NEXT_AGENT_PACKAGE_H1_2026-10-06.md first, then AGENTS.md,
current master/implementation status/Cloud Code handoff, G acceptance,
ADR-0023, PACKAGE_H_PLAN_2026-10-06.md, ADR-0024, architecture reuse and
H1 validation/gate/final review. Distinguish historical document instructions
from my current request. Owner continuation authorized local full H work;
ADR-0024 remains Proposed and no production/provider action is approved.

Inspect status and use your own codex branch/checkout from current delivered
H head. Preserve dirty owner/incoming checkouts and accepted/reviewer trees.
Do not implement in C:\Users\alexa\Documents\ChatGPT\Gorgona Booking or
C:\Users\alexa\Documents\ChatGPT\gorgona-e2-documents; they contain19/9
preserved changed/untracked paths. One executor per disposable PG suite.

Current H only has strict invoice/reference contracts, pure minor-unit
arithmetic, finance_documents registry2 closed gate, and47 new unit cases.
H1 remains IN PROGRESS, FIN-03/FIN-02 planned. H SQL/API/UI, actual invoice,
obligation, payment/refund, public posting seam, journal v2 and recovery
are unimplemented. Do not claim those flows or promote readiness from tests
of arithmetic. Existing G is technically_verified.

Next implement one coherent H1 slice: forward0021 schema/history/RLS and
tenant/book source constraints; typed public G posting seam; authenticated
invoice draft/read/issue with expected revision and command idempotency;
atomic issued version +obligation +balanced G journal +audit/minimal receipt.
Reuse gba.lock_ledger(tenant), READ COMMITTED, existing money/party/commands
and guards. Do not edit migrations0001–0020 or checksums.

Explicitly evolve SQL/Pydantic/Zod journal origins and v2 view negotiation,
preserve G-v1 writes/records, include all financial entries in trial balance,
deny G generic reversal of H-owned journals. Add finite minimal H recovery,
24h domain fallback and safe late-original cancellation. Preserve
published-v1 finance; new finance_documents needs current FIN-03 readiness
and its own publication. OFF permits history/recovery/eligible non-money
release; no blanket table/G-journal insert gate.

Follow the full handoff's financial rules and then H2→H3→H4. Do not invent
payment facts, automatic recognition, opening-obligation imports, provider
activation or legacy-entry accruals. P+C+R<=A must be enforced from effective
immutable history in SQL, not just pure Python projections.

Use a private disposable PG target, inject credentials privately, run
fixtures sequentially and stop only your owned cluster. Previous51456 is
stopped; do not touch older51454. Reusing G Python3.14 venv requires
PYTHONPATH pointing at your own source. Old check_h1.py hardcodes the
previous H checkout/branch; adapt your own runner instead of testing old code.

Validate changed behavior with real SQL/API/observed races, negative scope/
history/drift/recovery/gate tests and G compatibility, then appropriate web/
browser/full mandatory-PG/container exact-head CI. Obtain an independent
financial/state review in a separate checkout, close findings and record
exact evidence. Keep H-01..H-12 NOT TESTED until their full criteria run;
FIN-03 acceptance requires whole H and a separate acceptance commit.

Proceed autonomously with safe local work. No reset/clean/force-push, merge,
deployment, production DB migration, Azure/DNS/billing/credential change,
provider money action or unrelated KA Nails/camera project work.
Report exact changed files, commands/outcomes and unverified boundaries.
~~~
