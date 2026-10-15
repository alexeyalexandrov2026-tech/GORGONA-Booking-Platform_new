Continue GORGONA Booking, stage 2 Package J (STOCK-01), inline.

Checkout: `C:/Users/alexa/.codex/worktrees/package-j-review2-fixes/Gorgona Booking`. Branch: `codex/package-j-review2-fixes`.
Source commit: `7b96feca22b430d0ea98ef8081ac89cf7e292fc6`. Implementation/documentation CI head: `aedbb982a696052d606499f737b1754fce362b6a`,
CI run 157 PASS: https://github.com/alexeyalexandrov2026-tech/GORGONA-Booking-Platform_new/actions/runs/38693973265.
The acceptance documentation commit is above that head and changes no api/web source.
Inspect actual HEAD/status/remotes first; main must stay fedd0f115f24aad52f6256298296e8c5123fb427.

Read in order:

1. docs/plan/NEXT_AGENT_PACKAGE_J_REVIEW2_FIXES_2026-10-14.md.
2. docs/plan/evidence/2026-10-15-stock-01-acceptance/ACCEPTANCE.md and ACCEPTANCE.json.
3. docs/plan/evidence/2026-10-14-j5-j6-review-fixes-part2/VALIDATION.md and CHECKS.json.
4. The J5/J6 review, Package J plan J-01–J-14, ADR-0026 and current entry documents.

M1, L2, L3 and the two-source new-destination INSERT wait test are implemented and verified.
Static PASS: 114 web tests/build, Ruff/mypy/TypeScript/lint/format. Focused PASS: 141 passed.
Full local PASS: 1748 passed, 4 skipped in 1448.82s (0:24:08). All 14 technical evidence rows PASS.
The first full run was interrupted at 61%; it was preserved and replaced by full-2.
Fresh dependency audit: runtime 0; development audit FAIL, 5 existing high findings.

Read `C:/Users/alexa/AppData/Local/Packages/Claude_pzs8sxrjxfjjc/LocalCache/Local/GorgonaBookingTests/package-jr2p2-20261014-abbdfeb/ci-acceptance.json` and require its head_sha to equal
actual HEAD, status completed, conclusion success; otherwise read exact-current-head CI
via the public GitHub REST API. That final receipt is generated after the documentation
commit and is also linked by the final delivery message. No source rerun is needed just
because documentation changed; any new source mutation requires affected checks and gates.

STOCK-01 remains planned, inventory stays locked, and ADR-0026 remains Proposed. Promotion
requires the owner's separate explicit word. No further Package J fix is authorized by
this prompt alone. Preserve L1/L4, review gaps 3–5, maintenance-window limits, the platform
guard follow-up and the pre-existing archived-outbound-selector UI gap from the record.
Ask the owner to select subsequent product work before starting a new scope.

Run folder: `C:/Users/alexa/AppData/Local/Packages/Claude_pzs8sxrjxfjjc/LocalCache/Local/GorgonaBookingTests/package-jr2p2-20261014-abbdfeb`. Helpers: runner.py, write_record.py,
update_docs_jr2p2.py, validate_docs.py, accept_stock01.py, wait_ci.py. Their preconditions
are phase-specific; do not rerun the docs updater against a later HEAD. Fresh DB reruns
must use a new phase name; never reuse the preserved interrupted cluster.

No PR, merge, rebase, amend, reset, clean, force-push, readiness changes, CodeRabbit, Azure, production migrations, deployment, provider, funds or credential actions. Only publishing Package J branches without a PR for CI is authorized. Migrations 0001–0043 are immutable; the next is 0044. One executor per checkout and cluster; do not touch other checkouts, processes or ports 51454/51458/51474/51511. Credentials are generated in memory and never printed. Races require a wait observed in pg_locks. Use they/them for the owner. Work inline; no extra agents.
