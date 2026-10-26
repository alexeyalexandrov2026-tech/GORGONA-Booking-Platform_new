# Package M defects D-01 and D-02: local validation

**PASS.** Branch `codex/package-m-defects`, parent `7dd0bcd`
([design](../../PACKAGE_M_DEFECTS_2026-10-25.md)), source commit `099bc84`. [CHECKS.json](CHECKS.json) was
written before the source commit and binds every source blob, command, exit code and log digest. User
2026-10-25: "First fix the two open defects (night-time workforce test, silent refused grant offer), then M7b."

## D-01 — the "night-time" workforce browser failure

**Cause.** In M6a's dev-5 the live test server's event loop died with `OSError: [WinError 10055]` (WSAENOBUFS,
"the system lacked sufficient buffer space or a queue was full") inside `select()`, five times, before the
browser step failed: the approve request was never answered and the browser waited out its expectation.
Nothing in the workforce code or the test depends on the hour; the hour matched a machine-wide shortage of
socket resources right after a long full-suite run. M6a's full-1 failure of the same test left no traceback;
its cause is likely the same but **not proven**.

**Fix.** `tests/integration/live_server.py` keeps the server thread's error and, when the test leaves the
block, fails with `LiveServerStoppedError: the live server stopped during the test: …` chained to that error,
instead of leaving only a UI timeout. The machine's socket settings are system settings and were not changed.

## D-02 — a refused grant offer showed no message

**Cause.** `components/delegations.tsx` used one error state for commands and for list loading; after a 409
("This business already has an open delegation. Revoke it before issuing a new one.") the section reloaded the
list and the successful reload cleared the refusal. **Fix:** command refusals and loading problems are kept
apart; a reload clears only its own problem.

## Proof

`tests/unit/test_live_server_harness.py` (2): a server whose loop raises `OSError(10055)` fails the block with
`LiveServerStoppedError` chained to the `OSError`; a healthy server stops quietly. `test_m6b_transport_browser`
(real Chromium, mobile run): the offer while the desktop grant is open is refused in words and the alert is
still there after the list reloads; revoking clears it and the next offer succeeds.

## Failures kept

- red-1: collection error — `LiveServerStoppedError` did not exist (expected RED for D-01); the session stopped
  before the browser test. red-2: the refusal alert was never seen (intended RED for D-02).
- Before dev: ruff RUF100, E501 and RUF043 in the harness and its test.
- Gates passed on the first run.

## Gates (suffix 1)

Run folder `GorgonaBookingTests/package-m-defects-20261025-7dd0bcd`: **static-1** PASS; **focused-1** PASS,
**733 passed**; **full-1** PASS, **2614 passed, 4 skipped** (0:51:27 locally).

## Remaining

M7b (money on the order and trip screens), then M8 (acceptance). Next migration **0080**.
