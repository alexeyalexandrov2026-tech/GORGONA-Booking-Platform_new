# I4 workforce browser test: occasional failures in the full suite (2026-10-30)

`api/tests/integration/test_i4_browser.py::test_i4_real_browser_closed_then_enabled_then_switched_off`
(package I workforce screens; runs `web/tests/workforce.spec.ts`) failed now and then inside the full suite
and passed alone. Branch `codex/i4-browser-keep-alive` from `4861b85` (`origin/codex/package-n7-acceptance`).
Run folder `GorgonaBookingTests/i4-keep-alive-20261030-4861b85` (STATE.md there logs every run).

## The three known failures, one by one

| Run | Symptom | Finding |
| --- | --- | --- |
| N8 `full-4` (2026-10-30) | `page.request.post(issuer + "/fixture/user/ada")` → `apiRequestContext.post: read ECONNRESET` (spec :35 from :965) | **Proven: keep-alive race** in the test harness (below). Fixed. |
| M6a `dev-5` (2026-10-25, ~03:10 EDT) | mobile: "Approved and applied." not shown, approve buttons stuck | The app server's loop died with `WinError 10055` in `select()` — D-01, already reported loudly by `live_server` since `099bc84`. Why Windows refused `select()` is still not known. |
| M6a `full-1` (2026-10-25, ~02:30 EDT) | desktop: "Approved. This version is now in effect." not shown (spec :856) | **Not established.** No server error, no reset; not this race (it would show `ECONNRESET`). |
| J3 `full-2` (2026-10-13) | mobile: region "Workforce command recovery" not visible 5 s after "Send request" (spec :558) | **Not established.** Not this race and not a dead server (see below). |

## Keep-alive race (proven)

Playwright 1.63's request client — `page.request` and `route.fetch()` — sends through a Node
`http.Agent({ keepAlive: true })` (`playwright-core/lib/coreBundle.js`, `_ensureAgent`) with no idle limit of
its own and no retry (`maxRetries` defaults to 0). The loopback servers of the tests run under uvicorn 0.54
through `api/tests/integration/live_server.py`, which kept uvicorn's default `timeout_keep_alive` of 5 s. When a
pooled socket has been idle for about 5 s, the server closes it; if the client takes that socket for the next
request before it has seen the close, the server answers the request with a reset and Playwright reports
`read ECONNRESET`. Chromium itself is not affected: it resends a request that fails on a reused connection.

Proof, all against `live_server` as it was on `4861b85`:

- The real client: 200 Playwright request contexts, each re-posting after an idle gap spread across
  4.85–5.10 s. In exploration 3 of 200 failed with exactly `apiRequestContext.post: read ECONNRESET` (gaps
  4955–4957 ms); in red-1 and red-2 the test of this sweep failed with several such errors each time.
- The mechanism, deterministic: a bare `http.Agent({ keepAlive: true })` (built as Playwright builds it) whose
  event loop is busy across the 5 s limit — as a loaded test worker is — reuses the closed socket and gets
  `ECONNRESET` every time (3/3 in exploration, red-1, red-2); with a 3 s gap it is answered.
- The same busy trick through Playwright's own client is answered (its internal dispatch lets Node see the
  close first), which is why the real-client test is a sweep across the edge rather than a single request.

Fix: `live_server` passes `timeout_keep_alive=3600` to uvicorn, so an idle connection outlives any test; stopping
the server still closes it at once (guard test: the server stops within 5 s while a client holds an idle
pooled connection). Production servers are not changed (no `timeout_keep_alive` anywhere in `api/src`).

Tests (`api/tests/integration/test_live_server_keep_alive.py`, run with `GBA_REQUIRE_BROWSER=1` like the other
Node-based tests):

1. `test_a_pooled_socket_reused_after_the_default_idle_limit_is_answered` — the bare agent, deterministic.
2. `test_playwright_requests_across_the_default_idle_edge_are_answered` — the real Playwright client, sweep.
   Before the fix it fails with high probability, not certainty (a sweep can miss the few-millisecond window);
   after the fix the server never closes at that edge, so it cannot fail for this reason.
3. `test_the_server_stops_promptly_while_a_pooled_connection_is_idle` — guard for the longer limit.

Gates (suffix 1, source commit `48746ac`): static-1 PASS; focused-1 PASS, 75 passed, 1 skipped; full-1 PASS,
2657 passed, 4 skipped. The i4 browser test passed in both. Evidence:
[VALIDATION.md](evidence/2026-10-30-i4-keep-alive/VALIDATION.md), [CHECKS.json](evidence/2026-10-30-i4-keep-alive/CHECKS.json).

## J3 full-2 is not this race

`route.fetch()` in the spec's `loseAnswer` uses the same client, so a reset there was the first suspect. But a
route handler that throws is reported by Playwright as its own error (`Error: read ECONNRESET …`) before the
expect error, and the test ends at once (checked with a throwaway spec, deleted afterwards). J3's report has
only the 5 s timeout of the recovery region. Its app server also stayed alive (no captured stderr, no
unhandled-thread warning). That desktop case took 2.0 min in that run against about 50 s alone, so the machine
was heavily loaded; an answer slower than the spec's 5 s expectation fits, but is **not proven**.

## Time of day (M6a)

M6a failed between about 01:30 and 03:10 EDT and passed at 03:17. Checked: the home branch is
`America/New_York`, as is the machine; the spec's dates (week start in the location's zone, shift days from
today + 3, the timesheet window now − 18 h … now + 30 h, the correction day today − 30) cross no calendar edge
in that window. The second branch is `America/Los_Angeles`, a day behind until 03:00 EDT, but the failing
approve steps do not touch it. dev-5's failure was the dead server (10055), so at most full-1 could be
time-dependent; that is neither proven nor refuted (the system clock is a system setting and is not changed).

## Still open

- The cause of `WinError 10055` in the server's `select()` (D-01 reports it; nothing here prevents it).
- M6a full-1 and J3 full-2: causes not established. If either symptom comes back, the run's
  `web/test-results/**/error-context.md` must be copied into the run folder before the next run overwrites it.
