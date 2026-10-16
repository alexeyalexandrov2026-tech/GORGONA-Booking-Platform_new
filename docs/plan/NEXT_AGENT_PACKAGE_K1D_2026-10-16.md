# Next agent — Package K after K1d, 2026-10-16

## State

- Checkout `C:/Users/alexa/.codex/worktrees/package-j-review2-fixes/Gorgona Booking`,
  local branch `codex/package-k1d-receipt-routing`, parent `46ab31dd6f41ae820a85a09f19fd5812584fc89d`.
  K1d source commit `e9c86bfbd1d22e00ea66a96637cd98e9a58f27b4`, then one docs commit. Inspect the actual HEAD and status first.
- **Not published.** No K branch exists on the remote. `main` is `fedd0f1`; published J is `df88c20`.
- Migrations 0001–0046 are local history; 0001–0045 must not change. The next migration is **0047**.
- FIN-02 and STOCK-01 stay `planned`; ADR-0026 and ADR-0027 stay Proposed.

## What K now has (all local, synthetic)

| Slice | What it adds |
|---|---|
| K1a | Offline Stripe signature check and typed snapshot decoder |
| K1b | Receipt-only inbox (0044); the ordinary runtime may archive, never authenticate |
| K1c | Separate writer group, protected per-delivery attestations (0045) |
| K1d | Owner-provisioned verification configs and writer-only routes (0046); one entry point `receive_routed_receipt(pool, ingress_id, raw, signature, key_store=…)` |

K1d details, criteria D-01–D-09 and evidence:
[VALIDATION](evidence/2026-10-16-k1d-receipt-routing/VALIDATION.md),
[CHECKS.json](evidence/2026-10-16-k1d-receipt-routing/CHECKS.json),
[K1c review by the K1d executor](evidence/2026-10-16-k1d-receipt-routing/K1C_AUTHOR_REVIEW.md),
the K plan checkpoint and the ADR-0027 K1d section.

Facts to keep in mind:

- A config is verification authority, not admission. Connections stay `not_admitted`, test-mode only.
- Only the database owner provisions configs and routes, in an explicit company context.
  The runtime and the writer may only revoke a config. The runtime cannot read routes.
- Before the signature check only the route, the active config and the connection binding are read.
- Under forced row security the migration owner does not see company rows: a validated
  foreign key added by the owner did not detect a violating row. 0046 uses an explicit check
  under a temporary owner policy. A read-only audit of earlier migrations was suggested to the
  owner as a separate task; do not change published migrations.
- The writer process holds every key in its key store; SQL still does not verify a MAC.

## Recommended next steps

1. **Independent review of K1a–K1d** before any HTTP exposure. All K reviews so far are self-reviews.
   Ask the owner before starting a reviewer agent; the J delegation does not carry over.
2. **K1e, raw HTTP ingress, local only:** a route keyed by the ingress ID in the path, bounded raw
   ASGI body reads, 2xx only after the durable commit or a known duplicate, retryable failure when
   storage is unavailable, quotas and retention. Design and criteria into the K plan and ADR first,
   failing test first, migration 0047 only if needed.
3. Recorded limits to consider: revocation author/time, config expiry, an operator provisioning
   tool, a production key store (K0, owner authorization).

K0 (real test merchant, keys, admission) stays **BLOCKED** until the owner authorizes it separately.

## Rules

- No push, PR, merge, `main` change, rebase, amend, reset, clean or force-push; no readiness
  change, CodeRabbit, Azure or cloud change, production migration or deploy; no provider,
  account, key, credential or funds action — without the owner's separate direct word.
  The J exception (push J branches without PR for CI) does not apply to K.
- One executor per checkout and per disposable PostgreSQL cluster. Explicit port,
  `listen_addresses=127.0.0.1`, `max_connections=400`; check the data directory before stopping.
  Never use ports 51454, 51458, 51474, 51511, 49981 or other executors' clusters.
- Races count only with an observed `pg_locks` wait. No skips, `first()`, forced waits or retries
  instead of a check. Never commit as green while a required suite fails.
- Credentials are generated in memory and never printed. No secrets in logs, docs or prompts.
- Do not run historical PID scripts from earlier run folders.
- Work inline; extra agents only with the owner's consent. Save state early.
- Report PASS / FAIL / BLOCKED / NOT TESTED with exact commands and numbers. The owner is they/them.

## Run folder

`C:\Users\alexa\AppData\Local\GorgonaBookingTests\package-k1d-20261016-46ab31d`: `runner.py`
(`python runner.py <phase> <static|focused|full> [files]`, fresh own cluster per phase),
`run_gates.py <n>` (static, focused, full in order), `write_record.py <n>`, `STATE.md`.
Python: `api/.venv/Scripts/python.exe`. Copy these into a new run folder for the next slice;
do not rerun the K1d record script at a later HEAD.
