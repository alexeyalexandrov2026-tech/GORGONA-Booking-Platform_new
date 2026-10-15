# Next agent — K1a offline event boundary, 2026-10-15

PASS locally: source `7d25aa2d72874271a62e363817e0624fb502497c`, `codex/package-k1a-event-boundary`, based on `e8783f63254d1cffdbf6360513b5bf8f3ff411d1`.
Checkout: `C:/Users/alexa/.codex/worktrees/package-j-review2-fixes/Gorgona Booking`.
The subsequent documentation commit is above the source commit: inspect actual HEAD/status.
No K push or CI is authorized by the J publication exception. Main remains fedd0f1;
published J stays df88c20, CI158 PASS. The local K planning branch stays e8783f6.

Read [K1a validation](evidence/2026-10-15-k1a-event-boundary/VALIDATION.md), CHECKS.json,
[reuse](evidence/2026-10-15-k1a-event-boundary/ARCHITECTURE_REUSE.md),
[K plan](PACKAGE_K_PLAN_2026-10-15.md), [ADR-0027](../adr/0027-provider-events-and-reconciliation.md),
accepted ADR-0024 and current master/status/CLOUD_CODE_HANDOFF.

The owner's later `continue` was interpreted as local K1a coding with synthetic
fixtures only; no provider/credential authorization was inferred. Implemented the
strict signature-first offline decoder with stripe==16.0.0. All 96 boundary cases
pass; focused: 191 passed in 53.85s; full: 1844 passed, 4 skipped in 1444.23s (0:24:04).
Static checks, build and 114 web tests PASS. Six source files are bound by the
pre-code-commit CHECKS. Five existing development audit highs remain FAIL; runtime audit: 0.
Local container/external site remain four skips. Exact-current-K CI NOT TESTED.

The output is signature_only and test-mode only, with no tenant/book/admission or
financial authority. There is no webhook route, connection binding, inbox, worker,
money effect or migration. This is K1a, not all K1 and not any full K acceptance row.
FIN-02/STOCK-01 remain planned; ADR-0026/0027 remain Proposed. Real provider execution
is BLOCKED until separate direct owner authorization and actual test admission.

Next bounded local candidate: K1b typed connection authority and durable inbox on
forward 0044, using synthetic fixtures and a closed operational gate. Inspect current
architecture and choose least-privilege routing/worker access before code; test SQL
and RLS refusals before connecting an HTTP caller. Bound ASGI body reads before
calling the decoder. Only acknowledge after durable
commit; do not wire the decoder alone to a 2xx endpoint. No positive admission may
come from H4 metadata, a client business ID or a fabricated staff actor. K2/K3 provide
operation identity, lease fencing and financial lineage; they are not implemented here.
Actual Stripe target/environment/version needs owner-scoped selection/admission.

Run folder `C:/Users/alexa/AppData/Local/Packages/Claude_pzs8sxrjxfjjc/LocalCache/Local/GorgonaBookingTests/package-k1a-20261015-e8783f6`: runner.py, run_gates.py, write_record.py, update_docs.py,
and validate_docs.py. Use this checkout's api/.venv/Scripts/python.exe. Each runner
phase needs a new name and a fresh disposable cluster. write_record runs before
code commit; update_docs expects source HEAD whose parent is e8783f6. Do not rerun
phase-specific helpers against a later HEAD. FINAL_VERIFICATION.json is outside Git.

No PR/merge/rebase/amend/reset/clean/force-push, readiness change, CodeRabbit, Azure,
production migration/deployment, provider/funds/credential actions without separate
direct owner authorization. No K push. Migrations 0001–0043 are immutable; next: 0044.
One executor per checkout/cluster, no extra agents. Never touch other checkouts,
processes or ports 51454/51458/51474/51511. Races need an observed pg_locks wait.
Credentials remain private and unprinted; use they/them for the owner.
