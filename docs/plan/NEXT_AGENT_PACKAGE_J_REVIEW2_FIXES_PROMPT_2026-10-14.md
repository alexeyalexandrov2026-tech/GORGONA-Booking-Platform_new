Continue GORGONA Booking Package J (STOCK-01) inline.

Use `C:/Users/alexa/.codex/worktrees/package-j-review2-fixes/Gorgona Booking`, branch `codex/package-j-review2-fixes`; source `7b96feca22b430d0ea98ef8081ac89cf7e292fc6`,
plus the subsequent documentation commit. Inspect actual Git state before edits. Main
must remain fedd0f115f24aad52f6256298296e8c5123fb427. Read docs/plan/NEXT_AGENT_PACKAGE_J_REVIEW2_FIXES_2026-10-14.md,
docs/plan/evidence/2026-10-14-j5-j6-review-fixes-part2/VALIDATION.md and CHECKS.json,
the J5/J6 independent review, Package J plan J-01–J-14, ADR-0026 and current entry documents.

Part 2 fixes M1 pagination and unknown-material rejection, L2 18-minor-digit document
totals, L3 returned subject identity, and the two-source new-destination pg_locks race.
Static PASS (114 web tests); focused PASS (141 passed in 212.19s (0:03:32)); full local PASS (1748 passed, 4 skipped in 1448.82s (0:24:08)).
All changed sources are bound by pre-commit write_record.py; no migration/dependency change.
Initial failing regressions and static-1 malformed-BigInt failure remain in the run folder.

First determine whether the documentation head is published and read exact-HEAD CI.
If not published, git push -u origin codex/package-j-review2-fixes is authorized without PR.
Then complete technical acceptance J-01–J-14 with evidence, exact source/commit and CI;
leave STOCK-01 planned and ADR Proposed until the owner's separate explicit authorization.
Keep L1/L4 and earlier review limits explicit. Update the handoff and prompt before stopping.
Run folder `C:/Users/alexa/AppData/Local/Packages/Claude_pzs8sxrjxfjjc/LocalCache/Local/GorgonaBookingTests/package-jr2p2-20261014-abbdfeb`; use this checkout's api/.venv/Scripts/python.exe.
No PR, merge, rebase, amend, reset, clean, force-push, readiness changes, CodeRabbit, Azure, production migrations, deployment, provider, funds or credential actions. Only publishing Package J branches without a PR for CI is authorized. Migrations 0001–0043 are immutable; the next is 0044. One executor per checkout and cluster; do not touch other checkouts, processes or ports 51454/51458/51474/51511. Credentials are generated in memory and never printed. Races require a wait observed in pg_locks. Use they/them for the owner. Work inline; no extra agents.
