# Ready-to-paste prompt — after K1d

Continue GORGONA Booking stage 2, Package K / FIN-02, locally and inline.
Checkout `C:/Users/alexa/.codex/worktrees/package-j-review2-fixes/Gorgona Booking`, local branch
`codex/package-k1d-receipt-routing`, K1d source `e9c86bfbd1d22e00ea66a96637cd98e9a58f27b4` plus the following docs commit.
Check the actual HEAD and status first. Read `docs/plan/NEXT_AGENT_PACKAGE_K1D_2026-10-16.md`,
the K1d VALIDATION, CHECKS.json and K1c review, the K plan checkpoint and ADR-0027 before editing.

K1d (migration 0046) adds owner-provisioned, versioned verification configs (an opaque
`store:name` key reference, one active version per connection, one-way revocation) and
writer-only routes from an ingress ID to company and connection IDs. The single entry point
`receive_routed_receipt` reads only route, active config and binding before the K1a signature
check, then archives and attests in one commit. Attestations must name an active config of their
own connection. Synthetic only: no HTTP route, provider account or key, worker or money.
Connections stay `not_admitted`. Final focused 404 passed in 267.91s; full 1988 passed, 4 skipped in 1970.01s (0:32:50);
static, mypy (312 files), web 114 and build PASS; runtime audit 0, development audit 5 high (existing).
Independent review, K CI and the real provider are NOT TESTED / BLOCKED.

Important: the migration owner does not see company rows under forced row security, and a
validated foreign key added by the owner did not detect a violating row. Use an explicit check
under a temporary owner policy (0042, 0046) when a migration must inspect existing data.

Next: propose an independent review of K1a–K1d to the owner (ask before starting a reviewer
agent), then the smallest local K1e slice — raw HTTP ingress keyed by the ingress ID, bounded
raw body reads, 2xx only after durable commit or known duplicate, retryable failure otherwise,
quotas and retention. Design into the K plan and ADR first; failing test first; next migration 0047.

Rules: no push, PR, merge, main, rebase, amend, reset, clean, force-push, readiness, CodeRabbit,
Azure, production, provider, account, key, credential or funds action without the owner's
separate direct word; the J push exception does not apply to K. 0001–0045 immutable. One
executor and one own disposable cluster (explicit port, 127.0.0.1, max_connections 400; avoid
51454/51458/51474/51511/49981). Races need observed pg_locks waits. Credentials in memory only,
never printed. Do not run historical PID scripts. Work inline; save state early. The owner is
they/them. Finish with exact files, commands, counts and PASS/FAIL/BLOCKED/NOT TESTED.
