# Independent bounded ledger refresh review

**PASS at `15edbed1d608ada9d0901a7710c00eff28c23e71` — no remaining concrete finding in the two-file corrective delta.** Full H2 financial money/state review remains **NOT DONE**. This report does not accept FIN-03 or authorize publication, merge, deployment or production migration.

Reviewed only `web/components/ledger.tsx` and `web/tests/ledger.spec.ts` against committed base `15e8d0cd2a58544b7c6fefa73a2c78ade63c1861`. The Git delta contains those two files only; H2 financial Python/SQL/controls are unchanged by this correction.

## Source assessment

The typed loaded business/book/tick marker synchronously makes existing-book controls wait after a command increments tick. It is accepted only by the active refresh effect after book/accounts/journal and the period/report resets are applied. The existing active-effect cleanup prevents superseded refreshes from marking a different selection ready. A failed book fetch leaves the marker unmatched, so reads/writes remain locked; Refresh uses `blocked` rather than `blocked || waitingForBook`, making the retry reachable after failure. The scoped loading message and ledger-only alert assertion fit the existing UI.

The held actual book GET regression deterministically observes the refresh request and requires Read month to remain disabled before releasing it. The subsequent period read must show closed, then reopening and reading must show open. A separately aborted book GET must display the ledger alert, keep Read month disabled and leave Refresh enabled; successful retry must restore the period read. Promise release in `finally` and `unrouteAll({ behavior: "wait" })` settle route handlers before continuing. Both desktop and mobile exercised these assertions against the real fixture API/database.

## Independent exact-source evidence

Source review checkout: `C:\Users\alexa\.codex\worktrees\package-g-final-review\Gorgona Booking`, branch `codex/package-h2-ledger-refresh-review`. The local committed successor was fetched from the implementation repository and fast-forwarded without resetting prior work.

Browser/build checkout: `C:\Users\alexa\.codex\worktrees\package-h2-ledger-refresh-review\Gorgona Booking`, separate branch `codex/package-h2-ledger-refresh-browser-review`. Both checkouts remain clean at the exact reviewed SHA. Their two reviewed file hashes match:

| File | SHA256 |
|---|---|
| `web/components/ledger.tsx` | `269173fef6ea428123677f82ec39fff7c30fe918875d13f6b0c0bf5fa2da5e50` |
| `web/tests/ledger.spec.ts` | `329047622b1a168cd541226f0502767f1c447f377326e9df8aab4752b128547f` |

| Check | Exact result |
|---|---|
| Typecheck, scoped ESLint, scoped Prettier, Git diff check | PASS; combined shell elapsed **7.50s**, individual durations not captured |
| Standard `npm.cmd run build` in the fresh checkout | PASS, Next 16.3.7 Turbopack, **18 static pages**; stdout recorded compile **2.8s**, TypeScript **4.6s**, static generation **382ms**; total elapsed not captured |
| Focused real PostgreSQL/HTTP/OIDC/PKCE/Chromium fixture | PASS: **1 pytest test in 19.70s** |
| Nested ledger Playwright suite, one worker, desktop/mobile | PASS: **4 tests in 14.9s**; individual cases **5.3s**, **1.6s**, **3.9s**, **1.6s** |

Commands, run from the corresponding checkout's `web` or `api` directory:

```text
npm.cmd run typecheck -- --incremental false
node node_modules/eslint/bin/eslint.js components/ledger.tsx tests/ledger.spec.ts --max-warnings=0
node node_modules/prettier/bin/prettier.cjs --check components/ledger.tsx tests/ledger.spec.ts
git diff --check 15e8d0cd2a58544b7c6fefa73a2c78ade63c1861..15edbed1d608ada9d0901a7710c00eff28c23e71
npm.cmd run build
python -m pytest tests/integration/test_ledger_browser.py -q -s -p no:cacheprovider --basetemp <owned-private-temp> --tb=short
```

Node **24.18.0**, npm **11.16.0**. Existing installed dependencies were copied into the new checkout, with no dependency addition or package installation. Python: `C:\Users\alexa\.codex\worktrees\package-g-ledger-review\Gorgona Booking\api\.venv\Scripts\python.exe`. `PYTHONPATH` pointed exclusively to the new review checkout's `api\src`; bytecode/cache writes were disabled or redirected outside source. The private launcher asserts the exact Git HEAD before testing, sets required PostgreSQL/browser flags internally, and never prints its private DSN.

Owned PostgreSQL **18.6**, loopback **51460**, private target `%LOCALAPPDATA%\GorgonaBookingTests\package-h1-independent-review-51460`. Ownership, absent PID file and free port were checked before starting. Fixtures ran sequentially. Successful run stop returned **0**; final PID file absent and listener count **0**. Root 51456 and historical 51462/51458 were not used or changed. No root source was edited. Prior H1 branches/reports remain preserved.

## Harness limitations and safe recovery

The initial standard Turbopack build in the source-review checkout failed because its ignored dependency junction pointed outside Turbopack's filesystem root. This was an environment limitation, not a source compilation failure. Automatic approval review rejected removing that junction with the stated reason **“blocked by policy.”** The junction and checkout were preserved; the reviewer created a separate clean snapshot and copied ordinary local dependencies there. The same standard build then passed.

The first private browser launcher stalled while capturing PostgreSQL startup output through a pipe, before pytest created its fixture database. It produced no browser result. The reviewer confirmed ownership and no fixture database sessions, cleanly stopped only the owned cluster, and repaired only the external launcher to redirect startup output to a file. The final independent run above then passed and stopped the cluster normally. The initial timeout remains recorded separately and is not counted as a browser source failure or a PASS.

Redacted result/command evidence is under `%LOCALAPPDATA%\GorgonaBookingTests\package-h1-independent-review-51460\review-evidence\ledger-refresh\15edbed1d608ada9d0901a7710c00eff28c23e71-*`. Credentials remain private outside Git. The earlier design report remains unchanged, SHA256 `95e5a155e9594f4abfdc4712e58cedc22d4b190838bee1c94a0f653a91a4c322`.

## Boundaries

Independent baseline deterministic RED execution: **NOT TESTED**; the implementer's reported 1 failed/26.84s is not used as independent execution proof. Full Python suite, all 69 pure web unit cases, fresh exact-SHA remote CI and separately delayed business/selection-switch scenarios: **NOT TESTED independently** in this bounded correction review. Source isolation for superseded effects was reviewed; the focused real browser regression was executed directly.

The fixture validates this existing G ledger UI refresh/recovery behavior. It does not establish full H2 payment/refund/credit/reservation/provider money/state correctness. Full H2 financial acceptance remains **NOT DONE** and FIN-03 remains unpromoted.
