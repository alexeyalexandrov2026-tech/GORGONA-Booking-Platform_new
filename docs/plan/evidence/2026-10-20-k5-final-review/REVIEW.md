# K5 final independent review (K5a-fix, K0b, K5b) — findings and decisions (2026-10-20)

One read-only review agent (owner's «Да, запусти», 2026-10-20) over `git diff 59c54a0 e03c678 -- api web`
(51 files; code commits `76f7764` K5a-fix, `1eacc1d` K0b, `58cf561` K5b; migrations 0055–0060). The
reviewer edited nothing and ran no tests. The author verified R1–R3 inline against the code; R4–R9
are recorded as reported with the author's decision.

**Result: no Critical or High finding.** Two Medium, five Low, two Info.

| # | Sev. | Finding | Verified | Decision |
|---|---|---|---|---|
| R1 | Medium | Finding 6 is only narrowed: every check still decodes all events of the connection through `gba.provider_receipt_operation` (assert_provider_payment at commit under the ledger lock, the link trigger, the list query `_FACTS`); the new index removes only other connections | CONFIRMED (0056 `assert_provider_payment`, `_FACTS`) | Fix: an expression index on the operation key of the facts and predicates that use it; measure at volume |
| R2 | Medium | A suspension refuses deliveries instead of keeping them; facts sent during it (e.g. a later `refund.failed`) are lost after Stripe's retries, and re-admission makes a stale success applicable again | CONFIRMED (`_ACTIVE_AUTHORITY`) | Fix: a suspension is final for a connection; re-admission is refused (a new connection is provisioned instead). This changes the K0a default of question 7 |
| R3 | Low | The worker loop has no exception handling; one failed batch ends the process | CONFIRMED (`run_worker`) | Fix: log the failure class, back off one interval, continue |
| R4 | Low | No test proves the 0058 SQL money gate on its own (Python refuses first) | as reported | Fix: direct SQL tests for provenance and links |
| R5 | Low | The refund cap counts only provider-applied refunds, not linked manual ones (pre-existing) | as reported | Fix: count linked refunds in the cap; a refund of a linked parent stays refused (recorded limit) |
| R6 | Low | "Names the ID" ignores direction, so a payable naming a PaymentIntent blocks applying it | as reported | Fix: only a manual payment of the operation's direction names it |
| R7 | Low | Web: a time zone the browser does not know throws in the editor initializer | as reported | Fix: fall back to an empty date (the user types it), never the UTC date |
| R8 | Info | Resends of older partial-capture events now decode differently and show as delivery conflicts (safe direction, test mode) | — | Accepted; recorded |
| R9 | Info | Small deviations: admission compares account only; a link refused by the 0058 gate reports `facts`; pool errors may log host and user | — | Fix the link reason (`not_admitted`); the rest recorded |

Checked and found correct by the reviewer (summary): trigger order and lock ordering (no hard cycle;
queued exclusive admission requests only resolved by the deadlock detector), time-of-check re-reads
under READ COMMITTED, the admission table's owner-only writes, policies and append-only rules, 0059
grants, 0060 trigger and qualified `abs`, both guards' coverage of 0055–0060, refund conflicts in both
orders, finding-4 revocation rule, effective amounts and voids, captured amounts, metric counting after
authorization, process login checks, 127.0.0.1 binding, secrets as `SecretStr`, the disabled access
logger, and the web zone defaults.

## Resolution — K5r, 2026-10-20

Locally implemented in `b4e69e82152961380d21761c9a100515ea1645d1` ([validation](../2026-10-20-k5r-review-fixes/VALIDATION.md)): R1–R7 and
R9 fixed as decided, PASS. R1 needed a second design: the expression index was unusable under FORCE
RLS (measured), so the key is stored in generated columns. R8 accepted; a refund of a linked parent
stays a recorded limit.

Next: the fix slice **K5r** (failing tests first, same process), then the FIN-02 acceptance record
(K-01–K-14). FIN-02 stays `planned` until both are done.
