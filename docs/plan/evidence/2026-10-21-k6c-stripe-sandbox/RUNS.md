# K6c real sandbox run — 2026-10-21
Branch codex/package-k6c-sandbox at 9b741a7 (K6b2 docs).
k6c-1: FAIL in the driver: the new-event filter used the local start time; this computer runs a few
  seconds ahead of Stripe, so the payment events (Stripe time 1792640955-56) fell before it while the
  refund events (958-59) passed. Stripe shows all events, api_version 2026-08-26.dahlia, account present.
  Fix: start minus 120 s. Its sandbox objects stay (test mode). Logs kept in run-k6c-1.
k6c-2: phases A-C PASS (first run seen 14 recorded 14; second run 14 duplicates, 0 recorded). Phase D FAIL in the
  driver: `stripe events resend` answered (exit 0) "No CLI endpoints found to retry delivery" for an event created
  while nothing listened. Changed D to the other order (webhook first, then reconcile); cli() now fails on an error body.
k6c-3: my mistake — the driver edit script failed (anchor mismatch) but the run command was not chained to it, so
  k6c-3 reran the k6c-2 driver unchanged (same phase D failure; one more test-mode payment and refund in the sandbox).
k6c-3 fix applied with the Edit tool: phase D = webhook first, then reconcile; cli() fails on an error body.
k6c-4: PASS (1 passed, 33.9 s). first run 28/28 recorded, second 28 duplicates, webhook-then-retrieval 30 duplicates with both verifiers; payment 20.00 and refund 1.00 applied; 0 whsec_ values in logs.
