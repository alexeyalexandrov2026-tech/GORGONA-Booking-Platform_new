# Next agent — Package K after K1e, 2026-10-16

Superseded on 2026-10-17 by [the K1f handoff](NEXT_AGENT_PACKAGE_K1F_2026-10-17.md). Kept below as history.

## State

- Checkout `C:/Users/alexa/.codex/worktrees/package-j-review2-fixes/Gorgona Booking`,
  local branch `codex/package-k1e-http-ingress`, parent `2d434bff8081e03d38765caa0b61f5df006dde27`.
  K1e source commit `eb46748fa7446754e96e9290ce5261607ae45ce0`, then one docs commit. Inspect the actual HEAD and status first.
- **Branch pushed, nothing merged** (see the update below): no PR. `main` is `fedd0f1`; published J is `df88c20`.
- Migrations 0001–0046 are local history and must not change. The next migration is **0047**.
- FIN-02 and STOCK-01 stay `planned`; ADR-0026 and ADR-0027 stay Proposed.

## Update — 2026-10-16, disk space and publication

- The disk was full. With the owner's answers: 174 stopped phase `data` directories under
  `GorgonaBookingTests` were deleted (logs, `results.json` and evidence kept), and the clean,
  fully pushed old worktrees of packages H/I/J were removed with `git worktree remove` (branches
  kept). Worktrees with uncommitted files and `Documents/ChatGPT/Gorgona Booking` were not touched.
- The owner authorized pushing **this branch only**: `codex/package-k1e-http-ingress` is on
  GitHub (no PR, no merge, `main` unchanged). Its first CI run started on `07645aa`; read its
  result before relying on it. Every other K action (PR, merge, readiness) still needs the
  owner's separate word.
- `runner.py` in the K1e run folder now deletes each phase's stopped cluster after `pg_ctl stop`
  (`data_removed: true` in `results.json`). Copy this version for the next slice.

## What K now has (all local, synthetic)

| Slice | What it adds |
|---|---|
| K1a | Offline Stripe signature check and typed snapshot decoder |
| K1b | Receipt-only inbox (0044); the ordinary runtime may archive, never authenticate |
| K1c | Separate writer group, protected per-delivery attestations (0045) |
| K1d | Owner-provisioned verification configs and writer-only routes (0046) |
| K1e | Raw HTTP ingress for the writer process: `create_receipt_ingress_app(pool, key_store, limits=…)`, one route `POST /v1/provider-events/stripe/{ingress_id}`; no migration |

K1e details, criteria E-01–E-13 and evidence:
[VALIDATION](evidence/2026-10-16-k1e-http-ingress/VALIDATION.md),
[CHECKS.json](evidence/2026-10-16-k1e-http-ingress/CHECKS.json),
[independent review of K1a–K1d](evidence/2026-10-16-k1e-http-ingress/INDEPENDENT_REVIEW_K1A_K1D.md),
the K plan checkpoint and the ADR-0027 K1e section.

Facts to keep in mind:

- 200 only after the commit (recorded, duplicate, retained conflict). One byte-identical 400 for
  every refusal; 503 + `Retry-After` for storage, timeouts, guards and a full quota; 500 otherwise.
- Before the signature: a cheap writer-membership check and unlocked route/config/binding reads
  only. After it: full guards and a FOR SHARE re-read that must match. Transaction-local
  `lock_timeout` 5 s and `statement_timeout` 10 s.
- The ingress is only an application factory: no process entry point, settings, key-store loader
  or deployment. Whoever adds one must turn the HTTP server's own access log off (it logs raw
  paths with the ingress ID) and give it only the writer login.
- Under forced row security the migration owner does not see company rows. A migration that
  checks or moves existing data needs a temporary owner policy (0030, 0042, 0046).

## Recommended next steps

1. Owner decisions recorded as open: a legal retention period for receipt rows; whether to
   proceed to K0 (real test merchant, keys, admission — BLOCKED until separately authorized).
2. Small local follow-ups from the independent review, each its own slice: distinct passwords
   in bootstrap and bootstrap-before-migrate (IR-06); guard additions (IR-05); revoking runtime
   INSERT on the inbox in 0047 (IR-03); revocation author/time (IR-07).
3. A writer process entry point (settings, key-store interface, server with access log off) —
   local only, no deployment, after the owner agrees on the key-store shape.
4. K2 (worker, fencing, operation identity) builds on attested deliveries only (IR-03, IR-07).

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
- Do not run historical PID scripts or earlier slices' record scripts at a later HEAD.
- Work inline; extra agents only with the owner's consent for that package. Save state early.
- Report PASS / FAIL / BLOCKED / NOT TESTED with exact commands and numbers. The owner is they/them.

## Run folder

`C:\Users\alexa\AppData\Local\GorgonaBookingTests\package-k1e-20261016-2d434bf`: `runner.py`
(`python runner.py <phase> <static|focused|full> [files]`, fresh own cluster per phase),
`run_gates.py <n>` (static, focused, full in order), `write_record.py <n>`, `STATE.md`.
Python: `api/.venv/Scripts/python.exe`. Copy these into a new run folder for the next slice.
