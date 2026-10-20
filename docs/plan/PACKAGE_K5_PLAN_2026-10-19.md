# Package K5 — FIN-02 evidence plan: K0, independent review, CI (2026-10-19)

**Owner decision 2026-10-20: K0c is postponed** — no Stripe registration for now («без страйп обойтись»). FIN-02 stays `planned`; manual payments (H) remain the way money is recorded. Meanwhile the open K5a review findings 6, 8, 9, 12, 15 and the UTC default of the manual editors are fixed locally, without a provider.

**Update 2026-10-20: K0a done** ([design and the owner's answers](PACKAGE_K0A_DESIGN_2026-10-20.md),
all defaults) **and K0b done locally** (admission 0057, money gate 0058, ingress and worker
processes; [validation](evidence/2026-10-20-k0b-entry-points/VALIDATION.md)). The admission
migration is 0057, not 0055 as written in step 3 below. **K0c, the owner's real Stripe test run, is
next** ([handoff](NEXT_AGENT_PACKAGE_K0B_2026-10-20.md)).

**Status: owner decisions received 2026-10-19; K5a done** (review
[recorded](evidence/2026-10-19-k5a-review/REVIEW.md); K5a-fix locally implemented in `76f7764`,
[validation](evidence/2026-10-19-k5a-review-fixes/VALIDATION.md)). **K0a next; migrations from
0057.** Docs only. Nothing here is executed: no provider account, credential, Azure action, publication or
readiness change happens without the owner's separate word for that action.

## Owner decisions (2026-10-19)

The owner took the four defaults below:

1. The real test runs **on this computer**, with the Stripe CLI forwarding test events to the local
   ingress; no Azure action and no public URL.
2. The owner's own Stripe test sandbox acts as a **Connect platform with one connected test
   account**.
3. **One read-only independent review** (K5a) runs before any real event. Running it still needs
   the agent itself, which this answer authorizes for K5a only.
4. The signing secret goes into a **local environment variable** set by the owner; the process
   reads it by name and nobody prints it.

Each provider step (Stripe login, `stripe listen`, triggers) is still done by the owner; agents
never enter credentials.

## Goal

Plan slice K5 is "complete FIN-02 evidence and a separately authorized readiness decision"
([K plan](PACKAGE_K_PLAN_2026-10-15.md), acceptance K-14): actual admitted Stripe test execution,
the full disposable PostgreSQL suite, static, web and container gates, an independent review and
published exact-head CI. K1f–K4b and K3b are locally verified with **synthetic** events only;
K-01–K-14 stay NOT TESTED against a real provider. This plan says what is still missing and in
which order, so the owner can decide each step.

## Where FIN-02 stands (inspected, 2026-10-19)

| Part | State |
|---|---|
| Receipt storage, routing, attestations, decisions, money, screen, review, links | PASS locally (synthetic); branches K4a, K4b, K3b CI SUCCESS |
| HTTP receipt ingress | Code exists as an app factory (`providers/receipt_ingress.py`); **not mounted or run anywhere**; tests pass the signing key in code |
| Receipt worker | `process_batch` exists; **no process entry point or schedule** |
| Connection admission | `provider_receipt_connections.admission` accepts only `not_admitted` (0044); there is no admitted state |
| Real Stripe test events | NOT TESTED (K0 BLOCKED by the owner's credential and provider boundary) |
| Provider retrieval for ambiguous facts (K2b) | BLOCKED, needs K0 |
| Container image gate | NOT TESTED locally (3 skips); to be confirmed in CI logs |
| Independent review of K1f–K3b | NOT DONE |
| Readiness `FIN-02` | `planned` ("No accepted payment integration") |

Two current facts (Stripe documentation, checked 2026-10-19): events of a **connected account**
carry a top-level `account` field, which the K1 fact schema requires (`acct_…`); and
`stripe listen --forward-connect-to localhost:<port>/<path>` forwards test events of connected
accounts to a local endpoint without a public URL and prints its own signing secret (sandbox
retries are three attempts over a few hours).

## Proposed steps

1. **K5a — independent review (before any real event).** One read-only review agent over
   `main..codex/package-k3b-provider-links` (K1f–K3b), focused on money and SQL guards: the
   provenance and link triggers, RLS and grants, races, refusal paths, and the browser surfaces.
   Findings are reported, verified, and fixed in small slices with tests; nothing is merged.
2. **K0a — test environment and admission contract (owner decisions).** Where the real test runs
   (Question 1), which Stripe test account (Question 2), how the signing secret reaches the
   process (Question 4), USD only, direct payments and refunds only, test mode only.
3. **K0b — the missing code, still without any provider access.**
   - a process entry point that serves the receipt ingress with a key store read from the chosen
     secret source (never logged; `secret_ref` names it, the value never enters Git or chat);
   - a worker entry point (one batch per run, or a loop with a bounded interval);
   - migration **0055**: an admitted connection state that only an owner-recorded admission can
     set (who, when, environment, account), with guards and refusals;
   - tests with synthetic events through the real entry points.
4. **K0c — the actual Stripe test run (owner-operated steps).** The owner logs in to their own
   Stripe test sandbox, runs `stripe listen --forward-connect-to` against the local ingress and
   keeps the printed secret in the agreed place; triggers a successful payment, a failed payment
   and a refund for one connected test account; the worker decides them; a finance user applies
   one payment and one refund on the screen. Evidence: event IDs, decisions, payments and
   journals from the database and a redacted record; no payload, secret or customer data in Git.
5. **K5b — exact-head CI and the evidence record.** Publish the final branch for CI only, read the
   result once, confirm whether the container job ran; write VALIDATION with K-01–K-14 each PASS,
   FAIL, BLOCKED or NOT TESTED.
6. **K5c — readiness decision (owner).** Whether `FIN-02` stays planned, becomes limited
   ("test mode, USD, one connection"), or ready. A PR and merge to `main` are separate words.

## Acceptance criteria for K5

| id | Requirement |
|---|---|
| E-01 | Review findings are listed with severity, verified, and each fixed or explicitly accepted by the owner |
| E-02 | The ingress and worker run as processes; the signing secret never appears in logs, Git, chat or the browser |
| E-03 | Only an owner-recorded admission admits a connection; everything else stays refused |
| E-04 | Real Stripe test events (success, failure, refund) arrive signed, are attested, decided and shown; one payment and one refund are applied with provenance |
| E-05 | Duplicate and retried deliveries from Stripe create no second effect |
| E-06 | Full disposable PostgreSQL, static, web and browser gates pass at the final head; the container gate is PASS or explicitly NOT TESTED with the reason |
| E-07 | Exact-head CI SUCCESS on the published final branch |
| E-08 | VALIDATION states K-01–K-14 honestly; readiness changes only by the owner's decision |

## Questions for the owner

1. **Where the real test runs.** Default: on this computer with the Stripe CLI forwarding test
   events to the local ingress (no Azure, no public URL). Alternative: the Azure staging window
   (needs separate Azure actions and a public HTTPS endpoint).
2. **Which Stripe test account.** Default: your own Stripe test sandbox acting as a Connect
   platform with one connected test account; its events carry `account`, as the design expects.
   Alternative: a plain account without Connect (its events have no `account`; a code change to
   the fact schema is needed first).
3. **Independent review.** Default: one read-only review agent before any real event (K5a).
   Alternatives: after K0c, or no separate review.
4. **The signing secret.** Default: you put it into a local environment variable yourself; the
   process reads it by name and I never see or print it. Alternative: Azure Key Vault (needs the
   staging environment and separate Azure actions).

## Out of scope

Live mode or real money, checkout or payment creation, fees, payouts, disputes, other currencies,
automatic linking, deployment to production, and any merge to `main` without the owner's word.
