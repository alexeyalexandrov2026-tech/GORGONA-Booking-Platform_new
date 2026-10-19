# K5a independent review — findings and verification (2026-10-19)

One read-only review agent (owner-authorized for K5a only) reviewed `main..codex/package-k3b-provider-links`
(`fedd0f1..155038a`), focused on money and SQL defence. It ran no tests and changed nothing. Each finding was
then checked against the code by the executor. **No fix is made before the owner decides.**

Verdicts: CONFIRMED (the code does what the finding says), PLAUSIBLE (consistent with the code, not proven by a
run), KNOWN (already an open item).

| # | Severity | Finding | Where | Verdict |
|---|---|---|---|---|
| 1 | High | A manual payment that names an already applied provider operation is still accepted: the "names it" guard runs only when the provider operation is applied, not when the manual payment is recorded later, so the same money can be counted on another obligation | `settlements.confirm`; `0052` names-it check; `0054` | CONFIRMED |
| 2 | Medium | A later failed or cancelled refund event after a succeeded one is decided `not_final`, not a conflict, so the refund stays applicable (or plain `applied`) | `0050` decide trigger | CONFIRMED (logic) |
| 3 | Medium | The apply counter is labelled with the URL company ID before authorization, so denied requests with random IDs grow metric series without bound | `financial_documents.py` provider confirm route; `observability.py` | CONFIRMED |
| 4 | Medium | A configuration revoked for routine `rotation` blocks every unapplied operation attested under it (state `revoked`, never applied or linked) | `0052`, `0054`, `provider_payments._FACTS`; `0048` reasons | CONFIRMED; design decision |
| 5 | Medium-low | A voided manual payment that names an ID still blocks applying, and linking refuses voided payments: the operation stays `needs_link` forever | `settlements.confirm_provider`, `0052`; `0054`, `provider_review.link` | CONFIRMED |
| 6 | Low-medium | List and state queries scan every inbox event of the company per operation; no index on `(tenant_id, connection_id)` | `provider_payments._FACTS`, `0052` | PLAUSIBLE (not measured; known limit) |
| 7 | Low | Apply and link lock the operation but not the connection or configuration row; a revocation can commit in a very short window around an apply | `0052`, `0054`, `provider_payments.observed` | PLAUSIBLE |
| 8 | Low | `provider_payment_links` has no `require_financial_workflow` trigger (module-off is gated only in Python); `created_by` comes from the caller (as in other H tables); H money tables have no TRUNCATE guard (as before) | `0054`, `0053` | CONFIRMED |
| 9 | Low | The runtime still has INSERT on the inbox and deliveries | `0044` grants | KNOWN (IR-03) |
| 10 | Low | The link insert (and the acknowledgement insert) is outside `_writes`, so a trigger refusal in a race or after drift returns 500 instead of a typed refusal | `provider_review.link`, `acknowledge` | CONFIRMED |
| 11 | Low | The refund cap compares original amounts: a parent corrected downward allows refunds above its corrected amount; voided refunds still count | `0052` refund block, `settlements._require_refund_parent` | CONFIRMED |
| 12 | Low | A charge fact uses `amount`, not the captured amount; only `charge.succeeded` for a partial capture would book the full amount | `0050`, `stripe_events.py` | PLAUSIBLE |
| 13 | Low | The "names it" regex is case-sensitive and ignores invisible characters, while the H identity key normalizes them | `0052`, `settlements`, `provider_review` | CONFIRMED |
| 14 | Low | The apply form's default posting date is the UTC date, not the business time zone | `provider-operations.tsx` | CONFIRMED |
| 15 | Low | Latent: ISK/UGX scale differs from Stripe's; a currency missing from `gba.currencies` breaks the strict list; unqualified `abs()` in invoker functions | various | PLAUSIBLE (latent while USD only) |

The reviewer also listed what it found sound: provenance and apply rechecks in SQL, lock order (ledger, then
operation), link rules, RLS and grants on the new tables, no SQL injection (fixed fragments and bound
parameters), permissions, idempotency, the receipt signature path and the UI's truthful labels.

## Proposed fix slice (after the owner's decision)

- **K5a-fix** (one slice, failing tests first): 1, 2, 3, 5, 10, 11, 13, 14 and the share lock of 7.
- **Owner decision first**: 4 (does a `rotation` revocation block earlier attestations?).
- **Later or separate**: 6 (index and measurement), 8 (workflow trigger on links), 9 (IR-03), 12 and 15
  (latent, recorded).
