# Independent review of K1a–K1d — 2026-10-16

**Read-only, by a separate agent.** The owner chose this review when the K1e session started
("Да, параллельно с K1e"). A separate agent instance (security reviewer profile, same model
family as the K1e executor) read the code at `2d434bff8081e03d38765caa0b61f5df006dde27`. It had
no context from the K1a–K1d sessions beyond the prompt. It did not edit files, run tests, start
PostgreSQL or use the network. It is the first non-author review of K; it is not a human review
and does not replace the review gate before any exposure (K5).

Scope: `git diff df88c20..2d434bf -- api` (K1a `7d25aa2`, K1b `543b732` + `db96f00`, K1c `0c72a71`,
K1d `e9c86bf`), migrations 0044–0046, `providers/*`, `db/provider_receipt_guard.py`,
`db/bootstrap.py`, the provider tests, the K plan, ADR-0027 and the K1a–K1d evidence. Commands
were read-only `git log/diff/grep` and file reads (listed in section 4 of the report).

## Verdict (reviewer)

No High findings. The trust order matches the plan: only route, config and connection rows are
read before the signature check. Signature parsing is strict, and the SDK and local parsers
cannot disagree. RLS is enabled and forced on all six tables. Grants, immutability, one-way
revocation and FOR SHARE serialization hold on reading. 0044–0046 have no blind data check
except the one in 0046, which is correct. The real risks begin when K1e attaches HTTP (IR-01,
IR-02). Nothing was executed, so cost claims are hypotheses from reading.

## Findings and dispositions

| id | Level | Place | Observation (reviewer, shortened) | Disposition (K1e executor) |
|---|---|---|---|---|
| IR-01 | Medium | `providers/authenticated_receipts.py:95-104,160-165`; `db/provider_receipt_guard.py:260-353` | Before any signature check each request runs two catalog queries (the writer-role scan and the schema guard). It then takes FOR SHARE on config and connection rows and holds a pool connection until the signature fails. Anyone who knows an ingress ID can drive that cost; an unknown ingress still pays for both catalog queries. There is no lock timeout, so a pending revoker stalls every receipt. The K1d claim "an unknown ingress costs one indexed read" is inaccurate | **K1e decision 9:** unlocked authority reads before the signature, guards and a FOR SHARE re-read with an identity comparison after it; transaction-local lock and statement timeouts; body cap and concurrency slot before any database work. The K1d claim is corrected here and in the K plan |
| IR-02 | Medium | `providers/inbox.py:21`; `providers/stripe_events.py:50-59,159-165`; `api/errors.py:132-144` | Refusal classes differ in type and code, and `ProviderEventRejectedError` carries `details.reason`. The generic handler would send code and details to the caller, so a prober could tell a valid active ingress from an unknown one and `body_budget` from `signature` | **K1e decision 4/5:** a dedicated handler, not `install_error_handlers`; one byte-identical 400 for every refusal class, 503 for storage and guard refusals, 500 otherwise; each class tested (E-03, E-06–E-09) |
| IR-03 | Low | `0044:205-206`; `test_provider_receipt_attestations.py:434-467` | The runtime keeps INSERT on inbox and deliveries. An unattested row can occupy an event identity, so a later genuine delivery becomes `conflict`; a `duplicate` can rest on an unattested original. Needs knowledge of a random `evt_` ID | Recorded. K2 invariant: consume only attested deliveries whose facts match the original. Revoking the runtime INSERT is a candidate for a later migration (not K1e) |
| IR-04 | Low | `stripe_events.py:75,200-201`; `test_stripe_event_boundary.py:261-280` | `_Event.type` is a Literal, so an unsupported signed type fails as `event_shape`; the `event_type` branch is dead and tests do not assert reasons. Under K1e a subscribed but unsupported type gets 400, so Stripe retries and may disable the endpoint | Recorded. K1e keeps 400 (no 2xx without a durable record). K0 prerequisite: the endpoint subscribes only to the 11 supported event types. The dead branch stays (K1a unchanged) |
| IR-05 | Low | `provider_receipt_guard.py:339,373,424`; `authenticated_receipts.py:77`; `schema_guard.py:531` | Guard gaps: expected privileges flip with the caller's writer status; no check of extra members of `gba_receipt_writer`, grants to third roles, grant options, rewrite rules, persistence or function ACLs beyond PUBLIC; the writer path never checks the bodies of `current_tenant_id()`/`current_location_id()`. Owner-level drift only | Recorded limit; candidate guard additions for a later slice |
| IR-06 | Low | `bootstrap.py:44-47`; `cli.py:32-42` | `validate()` does not require distinct owner, app and writer passwords; the CLI cannot create the writer login; 0045 fails on a database bootstrapped before K1c (group missing) | Recorded for operations: reject equal passwords and document bootstrap-before-migrate. Not changed in K1e |
| IR-07 | Low | `0045:60`; `0046:99` | Revocation is a bare boolean (no who/when) and cannot tell rotation from compromise; `verified_by` records `current_user` (the group after SET ROLE); a revoked connection cannot be re-provisioned in the same namespace | Recorded (already a K1d limit for who/when). K2 constraint: operation identity must not depend on the namespace |
| IR-08 | Low | `0046:28,92-93` | `ingress_id` has no default or entropy rule; one immutable route per connection; no per-route disable; the owner cannot list routes | Recorded. The ingress ID is treated as non-secret; the signature is the authentication. A random default can follow |
| IR-09 | Low | `test_provider_receipt_routing.py:497-525` | The "permanent even for owner and superuser" claim covers UPDATE and DELETE only; no table has a TRUNCATE guard | Recorded: the claim is narrowed to UPDATE/DELETE. No change in K1e |
| IR-10 | Low | `test_provider_receipt_routing.py:186-190,531-600` | The refusal message check compares a constant and never inspects `details`; D-06 pauses after the Python-level FOR SHARE, so it cannot show the trigger-level lock works alone | Recorded. K1e E-03 compares full HTTP bodies; a trigger-only race is optional later |
| IR-11 | Note | `0046:12`; `stripe_contracts.py:17-19`; `record_event` | `secret_ref` permits `.` and `/` (a key store must treat it as an opaque key); `ApiVersion` `\d` matches Unicode digits but SQL and the policy equality make it harmless; a `conflict` disposition is silent | Recorded. Counting conflicts without IDs is a later observability item |

## Checked by the reviewer, nothing found

Signature parsing and freshness (symmetric ±300 s, constant-time SDK comparison over unmodified
bytes, size limits, payload-free errors); trust order and commit-before-return; RLS forced on all
six tables, privileges, the attestation trigger's refusal of runtime members through
`session_user`, no SECURITY DEFINER, `search_path=pg_catalog` in every K trigger function, no NULL
hole in 0044–0046; guard coverage and packaged expected sources; bootstrap password handling;
race tests with real `pg_locks` waits; refusal tests asserting zero rows; the only data check in
0044–0046 (`0046:111-121`) under a temporary owner policy.
