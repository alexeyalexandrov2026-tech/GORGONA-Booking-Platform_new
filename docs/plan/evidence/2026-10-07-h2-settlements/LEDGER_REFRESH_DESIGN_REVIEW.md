# Bounded ledger refresh design review

Source baseline: `15e8d0cd2a58544b7c6fefa73a2c78ade63c1861`, separate clean checkout `C:\Users\alexa\.codex\worktrees\package-g-final-review\Gorgona Booking`, own branch `codex/package-h2-ledger-refresh-review`. Prior H1 branches and reports are preserved. Read-only inspection also covered the implementer's proposed held-GET regression before commit; it is not treated as a committed correction.

**Design direction supported; final corrective source/runtime review pending an exact committed successor.**

The reported race follows directly from the baseline source: `execute()` clears busy/pending, publishes the saved message and increments `tick`; a separate effect later awaits book/accounts/entries and clears period/report. A period read started in that interval can therefore be replaced by the late refresh. A typed loaded business/book/tick marker, compared during rendering and accepted only by the current active effect after all refresh/reset state is applied, closes that interval for an existing selected book. The active-effect guard must prevent superseded book/business responses from marking a new selection ready.

One necessary recovery detail was reported to the implementer: fetch failure must leave an available refresh/retry action. The baseline Refresh button is disabled by `locked`; adding an unmatched marker to `locked` without a separate retry rule can permanently disable the only refresh path after a failed GET.

The proposed regression holds the actual post-command book GET behind a promise, waits until that request starts, then requires Read month to remain disabled while the GET is held. Releasing the promise in `finally` and waiting for route handlers to finish provides deterministic cleanup. Subsequent closed→open period assertions check that refreshing does not erase a later read. This is a focused regression for the diagnosed race, not H2 financial acceptance.

Checks so far: local Git source/branch/clean state and own base checkout verified; relevant component/effect/control and real browser harness source inspected. Node 24.18.0/npm 11.16.0 located. Existing installed dependencies are reused read-only through an ignored junction in the separate checkout; no package installation or root-source edit. An external private runner is prepared for the exact corrected SHA and reviewer-owned PostgreSQL 51460. Database/browser checks for the correction are **NOT TESTED yet**. Owned 51460 remains stopped; root 51456 and historical 51462 were not used or changed.

The CI failure and baseline deterministic RED outcome are implementer-provided evidence, not independent executions in this design stage. Full H2 financial Python/SQL/money/state review: **NOT DONE**. FIN-03 promotion, merge, deployment and production migrations are outside this review.
