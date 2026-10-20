# Next agent — Package K after K5a-fix, 2026-10-19 (updated 2026-10-20)

Read this whole file before any command. It replaces the K3b handoff. The ready-to-paste prompt is
[NEXT_AGENT_PACKAGE_K5A_FIX_PROMPT_2026-10-19.md](NEXT_AGENT_PACKAGE_K5A_FIX_PROMPT_2026-10-19.md).

## 1. State (verified 2026-10-20)

- Checkout `C:/Users/alexa/.codex/worktrees/package-j-review2-fixes/Gorgona Booking`, branch
  `codex/package-k5a-review-fixes` (parent `59c54a0`): source
  `76f776447b0b4fcb1699047aa2fa496531ee6b34` and docs `7b08507`, plus this handoff update. It
  contains K1f–K4b, K3b, the K5 plan, the K5a review and K5a-fix. Run `git status` and
  `git log -5 --oneline` first; the tree must be clean.
- **Published for CI only, no PR, no merge** (each by the owner's word):
  `codex/package-k1e-http-ingress`, `codex/package-k4a-provider-screen` (SUCCESS),
  `codex/package-k4b-provider-review` (SUCCESS), `codex/package-k3b-provider-links` (`c2a891d`, run
  39296081078 SUCCESS) and `codex/package-k5a-review-fixes` (`7b08507`, run 39371433810 SUCCESS at
  2026-10-20T05:09:16Z). This handoff update is local until the owner says to push it.
- `main` is `fedd0f1`; published J is `df88c20`. Migrations 0001–0056 are immutable; the next is
  **0057**. FIN-02 and STOCK-01 are `planned`; ADR-0026 and ADR-0027 are Proposed. No readiness
  change has been made or may be made without the owner.
- K5a-fix gates (exact): focused **527 passed in 577.17s**; full **2250 passed, 4 skipped in
  1868.37s** (3 container, 1 tenant-site: NOT TESTED); ruff, strict mypy (332 files), web
  typecheck, lint, format, unit (122), build PASS; runtime npm audit 0, development audit 5 high
  (existing, not required). [Validation](evidence/2026-10-19-k5a-review-fixes/VALIDATION.md),
  [CHECKS.json](evidence/2026-10-19-k5a-review-fixes/CHECKS.json),
  [review](evidence/2026-10-19-k5a-review/REVIEW.md).

## 2. Master plan reminder (read the sources, this is only the frame)

Sources, in priority order: the owner's latest decisions → [the master plan](GORGONA_MASTER_PLAN.md)
→ accepted ADRs → historical material. The root `AGENTS.md` and the repository transition note
[REPOSITORY_TRANSITION_2026-10-04.md](REPOSITORY_TRANSITION_2026-10-04.md) bind every agent.

- **Product.** GORGONA is an independent universal business platform (US market first). Keep the
  existing generic booking engine, services, staff, schedules, client flows and published APIs
  compatible. Extend through shared catalogs, documents, finance and resource occupancy; never a
  second ledger or duplicate logic. KA Nails is a separate project: do not develop, publish or use
  its site, brand or data here.
- **Order (master plan §13).** We are in stage 2 (finance, staff, basic materials): FIN-01–03,
  STOCK-01, WORK-01. Package K is FIN-02 (provider events and reconciliation). Stage 3 (beauty and
  TMS pilots) comes after stage 2 is accepted. A slice never declares a stage ready.
- **Money (§11).** Each business takes its clients' payments through its own provider connection;
  GORGONA is the platform, not the merchant. No simulated charges: a payment is either a human
  attestation with source and audit (H) or an attested, decided provider fact (K).
- **Provider admission (§11.2.1).** A connection registry holds company, legal entity, country,
  activity, provider, requested operation, external account, admission state, limits, check time
  and evidence. States: not checked, **test access**, approved for specific operations,
  suspended, not supported. **Test access never allows production payments.** Provider admission
  and industry admission are separate checks. K0a must follow this model.
- **Architecture.** Azure per ADR-0012 and `docs/architecture/AZURE_ARCHITECTURE.md` (Container
  Apps, private PostgreSQL, Front Door, managed identity/Key Vault, Bicep). The camera product's
  Local Gateway is not a Booking dependency. Tenant isolation (FORCE RLS), transactional booking
  and money integrity, typed versioned contracts at every boundary, human control over AI.
- **Readiness (§14).** Readiness is proven by working scenarios and recorded in
  [GORGONA_IMPLEMENTATION_STATUS.md](GORGONA_IMPLEMENTATION_STATUS.md); a catalog entry is not a
  workflow. Only the owner changes a readiness entry.

## 3. Rules (same as the [K1e handoff](NEXT_AGENT_PACKAGE_K1E_2026-10-16.md#rules), restated)

- Without the owner's separate, direct word: no push (beyond the five branches above, and even
  those only for a new word), PR, merge, `main` change; no rebase, amend, reset, clean,
  force-push; no readiness change, CodeRabbit; no Azure or other cloud action, production
  migration or deployment; no provider, account, key, credential or money action. Each Azure
  action needs consent for that action. Never repeat the Azure sign-in address.
- Do not touch the other copy `C:/Users/alexa/Documents/ChatGPT/Gorgona Booking`.
- **Stripe (owner decision 2026-10-19):** the owner performs the Stripe login, `stripe listen`
  and the triggers personally. Agents never enter credentials. The signing secret goes into a
  local environment variable that the owner sets; the process reads it by name; nobody prints it.
- One executor per checkout and per disposable PostgreSQL cluster: explicit port,
  `listen_addresses=127.0.0.1`, `max_connections=400`; never ports 51454, 51458, 51474, 51511,
  49981 or other executors' clusters. Before stopping a cluster compare the data directory and
  the port in `postmaster.pid`. Never start `pg_ctl` with captured output.
- Passwords and keys only generated in memory, never printed; no secrets in logs, docs or
  prompts; synthetic data only.
- A race counts only with an observed `pg_locks` wait. Never replace a check with a skip,
  `first()`, a forced delay or a retry. The test database is shared for the run: tests must not
  rely on an empty database. During `full` do not change files in `api` or `web`.
- Never hide a failure; never commit as green while a required suite fails. Report PASS, FAIL,
  BLOCKED or NOT TESTED with exact commands and numbers.
- Work inline; an extra agent only with the owner's consent for that package. Write Russian,
  simply and briefly, to the owner; the owner is they/them. Commit trailer:
  `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.

## 4. Next step: K0a, a design with questions before any code

Per [the K5 plan](PACKAGE_K5_PLAN_2026-10-19.md) (criteria E-01–E-08). Write
`docs/plan/PACKAGE_K0A_DESIGN_2026-10-20.md`, commit it as docs only, show it to the owner and wait
for the answers. Inspect first: `providers/receipt_ingress.py` (the app factory, not mounted),
`providers/receipt_worker.py` (`process_batch`, no entry point), migration 0044
(`provider_receipt_connections.admission` accepts only `not_admitted`), 0046 (routes), 0048
(revocation record), `db/provider_receipt_guard.py`, `db/bootstrap.py`, `ai/` and the CI workflow.

The design must cover, each with a default and alternatives for the owner:

1. **Admission record (migration 0057, K).** An admission state aligned with master plan
   §11.2.1 (at least `test_access` for this run; never production). Who records it (an owner-only
   SQL path or a CLI run by the owner; never the runtime or the receipt roles), what it binds
   (company, connection, Stripe account `acct_…`, environment `test`, operations: payments and
   refunds, USD), evidence and time, append-only history, suspension; guards, grants, the K guard
   list, and refusals for everything else. Ingress, worker and money stay refused for a connection
   without an active admission.
2. **Ingress entry point.** A process that mounts the existing ingress factory on a local port
   (`127.0.0.1` only), reads the signing secret by environment variable name (`secret_ref` names
   it; the value never enters Git, logs, chat or the browser) and fails closed without it.
3. **Worker entry point.** One batch per run or a loop with a bounded interval and a clean stop;
   which role and DSN source; logs without payloads.
4. **Tests (K0b).** Synthetic signed events through the real entry points; the secret absent,
   wrong and rotated; duplicate and retried deliveries create no second effect (E-05); admission
   refusals; no secret in captured logs.
5. **The owner's run (K0c).** The exact commands the owner will run (`stripe login`,
   `stripe listen --forward-connect-to localhost:<port>/<path>`, triggers for a successful
   payment, a failed payment and a refund of one connected test account), what the agent then
   checks in the database, and the redacted evidence (event IDs, decisions, payments, journals; no
   payload, secret or customer data).

Questions to ask (the owner's to decide): who records the admission and how; the worker mode;
the port and path; whether K0b may add a new CLI dependency (prefer none: the standard library
and existing FastAPI/uvicorn); how evidence of the owner's Stripe run is captured.

After K0a answers: K0b on a new branch (failing tests first, as in every slice), then K0c with the
owner, then K5b (exact-head CI and VALIDATION K-01–K-14) and K5c (the owner's readiness decision).

## 5. How a slice is run here (proven in K3a–K5a-fix)

1. New branch from the current HEAD; failing tests first; record red runs and every failure.
2. Run folder `C:\Users\alexa\AppData\Local\GorgonaBookingTests\<slice>-<date>-<parent>`; copy
   `runner.py`, `run_gates.py`, `write_record.py` from
   `package-k5a-fix-20261019-59c54a0` and adapt them (slice name, focused list, sources, new
   modules and cases, migrations count, failures). **Check line endings first**: a CRLF file makes
   Python `replace` edits silently miss; always `assert s.count(old) == 1`.
3. Run everything with `api/.venv/Scripts/python.exe`. `python runner.py <phase> focused <files>`
   for red/dev runs; `python run_gates.py <n>` for static → focused → full (about 45 minutes; run
   it in the background, do not edit `api`/`web` meanwhile). Build `web` (`npm run build`) before a
   focused run that includes a browser test.
4. `write_record.py <n>` before the code commit (it writes `CHECKS.json` and refuses unless every
   source blob matches the final gates); then the code commit; then docs: VALIDATION, the K plan,
   ADR-0027, the three status files (`GORGONA_IMPLEMENTATION_STATUS.md`, `GORGONA_MASTER_PLAN.md`,
   `CLOUD_CODE_HANDOFF.md`, the last with `docs/plan/` links), a new handoff and prompt, and
   "Superseded" on the old ones; then a link check and `git diff --check` (run it through Python
   `subprocess`; a hook rewrites the shell form); then the docs commit.
5. Read a published branch's CI once through the public GitHub API with `curl` after a background
   `sleep` (`gh` is not installed); no polling loops.

## 6. Traps found in K5a-fix

- An owner session without `owner_tenant_transaction` sees no rows under FORCE RLS
  (`gba.business_timezone` returns UTC there). Query company data in the company's context.
- The receipt roles (writer, worker, groups) cannot call `gba.lock_ledger`; 0055 takes the same
  advisory key directly (`hashtextextended('gba:ledger:' || tenant, 0)`). Keep the two keys equal.
- H refuses correcting a payment an issued credit depends on and voiding a refund payment; a
  manual payment may no longer name a provider operation whose money counts. Test data must
  respect this; two manual payments need different alias and reference (H identity).
- H functions: plpgsql, volatile, no `search_path`, every helper listed in `financial_guard`
  `_HELPERS` and granted to `gba_runtime`. K functions: `set search_path=pg_catalog`, listed in
  the receipt guard's migration tuple. A `CHECK` in H needs a `-- CHECK_APPROVAL` line.
- Use the 0056 helpers (`provider_reference_ids`, `effective_payment_amount`,
  `provider_manual_payment`, `provider_operation_payment`) for any new name or amount rule; do not
  write another regex.
- `Path.write_text` on Windows writes CRLF; write bytes with `\n`.

## 7. Open items

1. K0a/K0b/K0c above (K0 is BLOCKED only on the owner's own Stripe steps).
2. Review findings 6 (index and measurement), 8 (workflow trigger on links), 9 (IR-03), 12
   (captured amount of a partial capture) and 15 (latent currency and `abs()` items).
3. The manual financial editors still default to the UTC date.
4. Fees, payouts and bank reconciliation; other currencies; a worker schedule, alerts and
   dashboards (each needs the owner's word).

## 8. Run folder

`C:\Users\alexa\AppData\Local\GorgonaBookingTests\package-k5a-fix-20261019-59c54a0` (`STATE.md`,
phase logs, scripts, `PRECOMMIT_RECORD.json`). The stopped clusters' data directories are removed
by the runner; logs and `results.json` stay.
