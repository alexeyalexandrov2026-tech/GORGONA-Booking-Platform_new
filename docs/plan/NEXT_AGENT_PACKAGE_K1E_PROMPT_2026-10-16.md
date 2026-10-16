# Ready-to-paste prompt — after K1e

Continue GORGONA Booking stage 2, Package K / FIN-02, locally and inline.
Checkout `C:/Users/alexa/.codex/worktrees/package-j-review2-fixes/Gorgona Booking`, local branch
`codex/package-k1e-http-ingress`, K1e source `eb46748fa7446754e96e9290ce5261607ae45ce0` plus the following docs commit.
Check the actual HEAD and status first. Read `docs/plan/NEXT_AGENT_PACKAGE_K1E_2026-10-16.md`,
the K1e VALIDATION, CHECKS.json and the independent review of K1a–K1d, the K plan checkpoint and
ADR-0027 before editing.

K1e adds a separate ASGI application for the receipt writer process,
`create_receipt_ingress_app(pool, key_store, limits=…)`, with one route
`POST /v1/provider-events/stripe/{ingress_id}`: bounded raw body (256 KiB, read budget), one
`Stripe-Signature` header, 200 only after the commit, one byte-identical 400 for every refusal,
503 + `Retry-After` for storage, timeouts, guards and a full concurrency quota, 500 otherwise.
After the independent review (IR-01) `receive_routed_receipt` does only a cheap writer-membership
check and unlocked authority reads before the signature, then full guards and a FOR SHARE re-read
that must match; lock and statement timeouts are transaction-local. No migration (next 0047), no
process entry point, deployment, provider account or key, worker or money. Connections stay
`not_admitted`. Final focused 450 passed in 273.91s; full 2034 passed, 4 skipped in 1700.22s (0:28:20); static, mypy, web and build PASS;
runtime audit 0, development audit 5 high (existing). Human review, K CI and the real provider
are NOT TESTED / BLOCKED.

Next: ask the owner which follow-up to take — review follow-ups IR-06/IR-05/IR-03/IR-07 as small
local slices, a local writer process entry point (key-store shape needs the owner), or K2 design.
K0 stays BLOCKED until separately authorized. Design into the K plan and ADR first; failing test
first.

Rules: no push, PR, merge, main, rebase, amend, reset, clean, force-push, readiness, CodeRabbit,
Azure, production, provider, account, key, credential or funds action without the owner's
separate direct word; the J push exception does not apply to K. 0001–0046 immutable. One
executor and one own disposable cluster (explicit port, 127.0.0.1, max_connections 400; avoid
51454/51458/51474/51511/49981). Races need observed pg_locks waits. Credentials in memory only,
never printed. Do not run historical PID scripts. Work inline; save state early. The owner is
they/them. Finish with exact files, commands, counts and PASS/FAIL/BLOCKED/NOT TESTED.
