# I4 workforce browser test: keep-alive race in the test harness — local validation

**PASS.** Branch `codex/i4-browser-keep-alive`, parent `4861b85` (`origin/codex/package-n7-acceptance`),
source commit `48746ac` ([finding](../../I4_BROWSER_KEEP_ALIVE_2026-10-30.md)). [CHECKS.json](CHECKS.json) was
written before the source commit and binds every source blob, command, exit code and log digest.

## Cause

N8 full-4 failed `test_i4_real_browser_closed_then_enabled_then_switched_off` with
`apiRequestContext.post: read ECONNRESET` (workforce.spec.ts:35, called from :965). Playwright 1.63's request
client (`page.request`, `route.fetch`) pools sockets in `http.Agent({ keepAlive: true })` with no idle limit and
no retry; `live_server` ran uvicorn 0.54 with its default `timeout_keep_alive` of 5 s. A socket idle for about
5 s is closed by the server; if the client reuses it before it sees the close, the request is reset.

## Fix

`api/tests/integration/live_server.py` passes `timeout_keep_alive=3600` (`KEEP_ALIVE_SECONDS`). Stopping the
server still closes idle connections at once. Production code is unchanged.

## Proof

`api/tests/integration/test_live_server_keep_alive.py` (3, run with `GBA_REQUIRE_BROWSER=1`):

- a bare keep-alive agent (built as Playwright builds it) whose event loop is busy across the 5 s edge reuses
  the closed socket — deterministic `ECONNRESET` before the fix, answered after;
- 200 Playwright request contexts re-posting after gaps spread over 4.85–5.10 s — several `read ECONNRESET`
  before the fix, none after;
- guard: the server stops within 5 s while a client holds an idle pooled connection, and the next post fails.

| Run | live_server | Result |
| --- | --- | --- |
| red-1 | as on `4861b85` | 2 failed (bare agent, Playwright sweep), 2 passed |
| green-1 | with the fix | 5 passed |
| red-2 | as on `4861b85`, final test text | 2 failed (same two), 3 passed (guard included) |

## Not established (kept open)

M6a dev-5 was the server loop dying with `WinError 10055` (D-01, reported since `099bc84`); its Windows cause is
unknown. M6a full-1 and J3 full-2 show no reset and no server death; their causes are not established, and the
time-of-day dependence is neither proven nor refuted. Details in the finding.

## Failures kept

- Exploration: the busy trick through Playwright's own client was always answered, so the deterministic test
  uses a bare agent and the real client is checked by a sweep.
- The stop guard was written after red-1, so red-2 was run on the final test text (live_server change stashed,
  then restored).
- Before the gates: ruff E501 on a long JavaScript line in the test (split); in the run folder a `sed` edit of
  `runner.py` did not apply (redone in Python).
- Gates passed on the first run.

## Gates (suffix 1)

Run folder `GorgonaBookingTests/i4-keep-alive-20261030-4861b85`, one executor, one fresh PostgreSQL 18 cluster
per phase: **static-1** PASS (incl. web build); **focused-1** PASS, **75 passed, 1 skipped** (16 min);
**full-1** PASS, **2657 passed, 4 skipped** (1:02:04). Skips are the usual BLOCKED container and tenant-site
checks. The i4 browser test passed in both (159 s and 161 s).

## Remaining

Push for CI. If the J3 or M6a symptom returns, copy `web/test-results/**/error-context.md` into the run folder
before the next run.
