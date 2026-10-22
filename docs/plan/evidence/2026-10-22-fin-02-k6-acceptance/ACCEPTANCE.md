# FIN-02 — K-05 and K-12 after package K6 (2026-10-22)

**Decision: FIN-02 stays `technically_verified`; K-05 and K-12 move from PARTIAL to PASS** within the
limits below. Not a pilot acceptance and not a production approval. Basis: the owner's choice of
2026-10-21 («1»: close the FIN-02 gaps) and the accepted K6 plan, whose last step is this update
"if the evidence holds" ([design](../../PACKAGE_K6_DESIGN_2026-10-21.md)). The rest of the
[2026-10-20 acceptance](../2026-10-20-fin-02-acceptance/ACCEPTANCE.md) is unchanged.

Verified source: `2eb6cf723f719bde3753ba6bd800c44bc082602d` (K6r, migrations to 0065), on top of K6a
`2f577bc`, K6b1 `73f5c45`, K6b2 `0af2a46`.

| id | Before | Now | Evidence |
|---|---|---|---|
| K-05 permutations converge; stale, equal-time and **missing** objects reconcile safely | PARTIAL: no retrieval of missing objects; permutations by representative orders | **PASS** | Every order of six events of one payment and its refund (720) and equal creation times converge (K6a); lost events are fetched back by the reconciler into the same inbox with the same facts, a webhook and its retrieval converge, a different fact is a visible conflict (K6b1); **real sandbox**: webhooks lost on purpose, fetched back, decided and applied (payment 20.00, refund 1.00), a second run all duplicates, webhook-then-retrieval converged ([K6c](../2026-10-21-k6c-stripe-sandbox/VALIDATION.md)) |
| K-12 bounded retries, dead-letter, reconciliation, no fabricated success, no secrets in logs | PARTIAL: no dead-letter queue or reconciliation | **PASS** | A failing event is recorded and retried after 1, 2, 4, 8 minutes, then parked until a finance user's **Try again** (K6a); outages never park events; every reconciliation run is recorded with balanced counts and a failed run names its class, also when a connection is suspended mid-run; 429/5xx/timeouts retried then failed, nothing fabricated (K6b1, K6r); logs keep classes and counts only, metrics count failures and runs, the screen shows parked events, delivery sources, stalled operations and each connection's latest run (K6b2, K6r) |

## Gates and reviews

- Local: K6a full 2354, K6b1 2395, K6b2 2398, K6r **2415 passed, 4 skipped** (each with the real
  browser where the screen changed).
- Exact-head CI SUCCESS: K6a run 39724421746, K6b1 39724425326, K6b2 39724428029, K6c 39724431070,
  K6r 39732441848 (head `7a70b8f`).
- One independent read-only review: APPROVE with conditions, no Critical or High; its R1–R8 fixed in
  K6r ([review and resolution](../2026-10-22-k6-review/REVIEW.md)).

## Record

The registry change is commit `47e60c5` on `codex/package-k6s-fin02-record`; this file and its
[CHECKS.json](CHECKS.json) follow in the next commit, so the branch head (not `47e60c5` alone) is the
consistent state that CI checks. Gates of the change: static, focused 43 passed, full **2415 passed, 4
skipped**.

## Limits

Test mode, USD, one admitted connection per company. The reconciler's real calls in the sandbox went
through the signed-in Stripe CLI; the product's own HTTP client was tested against a fake API that
checks the exact request, and needs one call with a restricted test key that only the owner may create.
The platform key has no own revocation record (rotate it in the environment). Run records grow without
bound. No live mode, other currency, fees, payouts or disputes; no pilot acceptance and **no
production approval**.
