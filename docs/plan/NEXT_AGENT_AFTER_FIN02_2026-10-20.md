# Next agent — after FIN-02 technical acceptance, 2026-10-20

Read this whole file before any command. It replaces the [K5b handoff](NEXT_AGENT_PACKAGE_K5B_2026-10-20.md)
as the current entry point; that file still holds the K0c procedure and the Stripe rules. The
ready-to-paste prompt is [NEXT_AGENT_AFTER_FIN02_PROMPT_2026-10-20.md](NEXT_AGENT_AFTER_FIN02_PROMPT_2026-10-20.md).

## 0. The goal (owner, 2026-10-20)

Production is **all 39 directions of the master plan at once**, one launch; any business of any
direction signs up and works. Never plan or estimate a salon-only or one-industry launch (master plan
top block, §1 point 13, §13, §14.3; `AGENTS.md`).

## 1. State (verified 2026-10-20)

Checkout `C:/Users/alexa/.codex/worktrees/package-j-review2-fixes/Gorgona Booking`. The stack of local
branches, each built on the previous:

| Branch | Head | Published | Content |
|---|---|---|---|
| `codex/package-k5b-open-findings` | `e03c678` | yes, CI SUCCESS (run 39502582514) | K5b fixes, K0c real Stripe run |
| `codex/package-k5r-review-fixes` | `2b640e2` | yes, CI SUCCESS (run 39523031370) | final review and K5r fixes (0061, 0062) |
| `codex/package-k5c-fin02-readiness` | code `ea74bec` + docs `1a8a180` | yes, CI SUCCESS (run 39527769354) | FIN-02 `technically_verified` |
| `codex/package-stock01-readiness` | code `3f68e3f` + docs | see the STOCK-01 checkpoint | STOCK-01 `technically_verified`, inventory enableable |

- `main` was fast-forwarded on the owner's word to `1a8a180` (packages J and K, FIN-02); CI on `main`
  SUCCESS (run 39536393894). Further merges to `main` need the owner's word.
- Migrations 0001–0062 are immutable; the next is **0063**.
- FIN-02 is `technically_verified` (test mode, USD, one connection; K-05 and K-12 partial; no live mode,
  no production approval): [acceptance](evidence/2026-10-20-fin-02-acceptance/ACCEPTANCE.md).
  STOCK-01 is `technically_verified` since 2026-10-21 on the owner's «ok»:
  [record](evidence/2026-10-20-stock-01-readiness/RECORD.md); the `inventory` module may be enabled.
- Stripe: CLI 1.54.1 authorized for the owner's sandbox `acct_1UJtGO0mkpVWlKYX`; connected test account
  `acct_1USjOo0mkpWSHVnd`; the K0c driver is kept in
  `docs/plan/evidence/2026-10-20-k0c-stripe-sandbox/test_k0c_run.py.txt`.

## 2. Rules

As in the K5b handoff section 3: no push of a new branch, PR, merge, `main`, rebase, amend, reset,
clean, force-push, Azure, production or live-mode provider action without the owner's word (the owner
delegated publishing these K branches for CI and the FIN-02 readiness decision: «делай, как ты
считаешь нужным… я доверяю тебе»). The owner alone signs in and accepts terms in Stripe; never enter a
password, SSN or key. One executor and one own disposable cluster; races only with an observed
`pg_locks` wait; failing tests first; never hide a failure; write to the owner in Russian, simply; the
owner is they/them. GateGuard denies the first write of each file: state the facts, then retry.

## 3. Lessons from this stretch

- Under FORCE RLS a condition on a function that is not leakproof cannot be an index condition: store
  the value (a generated column) and index the column. Measure at volume; a plan test with
  `enable_seqscan=off` can pass while the real plan is a sequential scan.
- On Windows the selector event loop that psycopg needs cannot spawn subprocesses; run them in threads.
- Git Bash mangles `/v1/...` arguments for native programs; set `MSYS_NO_PATHCONV=1`.
- `*.log` is ignored by Git; force-add a redacted log that a record links to.

## 4. What is next (choose with the owner)

1. **Merge plan.** Done: `main` is `1a8a180`. The STOCK-01 branch is one step ahead; ask the owner
   before it goes into `main`.
2. **FIN-02 gaps** (optional before live): provider retrieval for missing objects (K-05), a
   dead-letter queue and reconciliation (K-12), a refund of a linked parent.
3. **STOCK-01 record.** Done (`3f68e3f`).
4. **The road to one launch of all 39 directions** (master plan §13): the industry modules of stages
   3–8 and the stage 9 operations in Azure (each Azure action needs the owner's consent).

## Update 2026-10-22 — package K6 (FIN-02 gaps) done

Stacked branches, all published for CI only (no PR, `main` untouched): `codex/package-k6a-bounded-retries`
(0063 bounded retries and parked events), `codex/package-k6b-event-backfill` (0064 read-only event
backfill from the Stripe API), `codex/package-k6b2-screen` (delivery source, stalled marker),
`codex/package-k6c-sandbox` (real sandbox run with lost webhooks), `codex/package-k6r-review-fixes`
(0065, fixes of the independent K6 review), `codex/package-k6s-fin02-record` (FIN-02 record: K-05 and
K-12 PASS, status unchanged). CI SUCCESS on the K6a–K6r heads. `main` is still `1a8a180`; the STOCK-01
record (`fba651e`) sits under K6 in this stack. Migrations 0001–0065 immutable; next **0066**.
Lessons: a new K table with a company policy must join `test_location_access`'s migration list and
the upgrade tests' K table lists, and `copy_fixture_data` must omit row values an older schema refuses;
the JSON log formatter drops any field not on its allowlist; this computer's clock runs a few seconds
ahead of Stripe's; `stripe events resend` refuses events created while no CLI listened (and exits 0).
Next, with the owner: merging the stack into `main` (needs their word), the restricted test key for one
real call of the product's HTTP client (their action), or the industry modules toward one launch of all
39 directions.
