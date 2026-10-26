# Package M — two open defects before M7b (2026-10-25)

User 2026-10-25: "First fix the two open defects (night-time workforce test, silent refused grant offer), then
M7b." Branch `codex/package-m-defects` from `8e50fb2` (M7a).

## D-01: the "night-time" workforce browser failure

Found in M6a: `test_i4_browser` failed in full-1 (about 01:30-03:00 EDT) and again alone in dev-5 (about 03:10),
then passed at 03:17 on the same source and on a baseline without M6a. **Cause found in dev-5's log:** the live
test server's event loop crashed with `OSError: [WinError 10055]` ("the system lacked sufficient buffer space or
a queue was full", WSAENOBUFS) inside `select()`, five times, before the browser step failed. The server thread
died, the approve request was never answered and the browser waited out its five-second expectation. Nothing in
the workforce code or the test depends on the hour; the hour only matched a machine-wide shortage of socket
resources right after a long full-suite run. full-1's log of the same failure carries no traceback, so its cause
is likely the same but not proven.

Fix: the harness reports a dead live server as the failure. `live_server` keeps the server thread's exception and,
when the test leaves the block, fails with "the live server stopped during the test: …" (chained to whatever the
browser reported), instead of leaving only a UI timeout. The machine's socket settings are system settings and
stay untouched.

## D-02: a refused grant offer showed no message

Found in M6b: offering access to a business that already has an open delegation answers 409 with "This business
already has an open delegation. Revoke it before issuing a new one.", but the delegated access section showed
nothing. **Cause:** one error state served both commands and list loading; after a 409 the section reloads the
list and the successful reload cleared the command's error. Fix: command refusals and loading problems are kept
apart, so a reload never clears a refusal.

## Acceptance (PASS locally in `099bc84`)

| id | Requirement |
|---|---|
| D-01 | A live test server that dies during a test fails that test with the server's own error |
| D-02 | A refused grant offer stays visible as an alert after the list reloads; the corrected offer then succeeds |
| D-03 | The full suite stays green |
