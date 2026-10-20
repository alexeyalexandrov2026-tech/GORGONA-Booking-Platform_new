# K0a — admission, entry points and the owner's Stripe test run: design and questions (2026-10-20)

**Status: owner answered 2026-10-20 — «i trust you» to the seven questions below, so every
default is taken (owner records the admission with the `gba-db` command; H4 link optional; worker
loop every 5 s plus `--once`; `127.0.0.1:8787`; no new dependency; the agent reads the database
after the owner's run; a suspended connection may get a new `test_access` revision). K0b is next.**
Nothing here is built or executed. Code starts in K0b, on a new branch, after the answers, with failing tests first. No
provider account, credential, Azure action, publication or readiness change happens without the
owner's separate word. Parent: `d03ae53` (K5a-fix handoff). Next migration: **0057**.

Frame: [K5 plan](PACKAGE_K5_PLAN_2026-10-19.md) (criteria E-01–E-08), master plan §11 and §11.2.1,
[ADR-0027](../adr/0027-provider-events-and-reconciliation.md),
[K5a-fix handoff](NEXT_AGENT_PACKAGE_K5A_FIX_2026-10-19.md).

## What exists today (inspected 2026-10-20)

| Part | Where | Gap for a real test run |
|---|---|---|
| Ingress app | `providers/receipt_ingress.py`, `create_receipt_ingress_app(pool, key_store)`, route `POST /v1/provider-events/stripe/{ingress_id}` | Not mounted or run; tests pass the key in code |
| Worker | `providers/receipt_worker.py`, `process_batch(pool, limit, lease_seconds)` | No process entry point |
| Connection admission | 0044: `provider_receipt_connections.admission` accepts only `not_admitted` | No admitted state; nothing gates ingress, worker or money on admission |
| Company declaration | H4 (0031): `provider_admission_versions`, states `draft/submitted/withdrawn`, assessment `not_checked/suspended/unsupported`, every capability forced false | A declaration only; never an admission |
| Key reference | 0046: `secret_ref` = `store:name`, secret-like values refused | No store is resolved in a process yet |
| Roles | `db/bootstrap.py`: groups `gba_runtime`, `gba_receipt_writer`, `gba_receipt_worker`; optional writer and worker logins | Logins exist only in tests |
| Owner tooling | `db/cli.py` (`gba-db`): owner connection from `GBA_MIGRATION_DATABASE_URL`, operator `operator:<OS user>` | No admission command |
| API process | `python -m gorgona_booking` (`__main__.py`: uvicorn in a selector loop on Windows) | Pattern to copy for the new processes |

Supported Stripe event types (K1a): `payment_intent.{succeeded,payment_failed,processing,canceled}`,
`charge.{succeeded,failed,pending,refunded}`, `refund.{created,updated,failed}`.

## Proposed design (defaults; alternatives in the questions)

### 1. Admission record — migration 0057

A new append-only table `gba.provider_connection_admissions`, the only authority that admits a
receipt connection. The 0044 column `admission` stays `not_admitted` (immutable migration) and is
documented as "no admission on the row itself".

- Columns: `tenant_id`, `connection_id`, `revision` (1, 2, … per connection), `state`,
  `environment`, `operations`, `currency`, `account_id`, `evidence`, `h4_request_id` (optional),
  `recorded_by` (session login), `recorded_at`.
- States follow §11.2.1. 0057 accepts only **`test_access`** and **`suspended`**; no row means
  "not checked". `approved` and production are refused by a check until the owner decides
  otherwise in a later migration.
- `environment = 'test'`, `operations` ⊆ {`charge`, `refund`} (both for this run), `currency = 'USD'`.
- A trigger requires `account_id` and the connection's namespace to equal the connection's, a
  live (not revoked) connection, the next revision, and company scope; `recorded_by` and
  `recorded_at` are set by the trigger. Rows are permanent (no update or delete).
- Grants: no insert for `gba_runtime`, `gba_receipt_writer` or `gba_receipt_worker`; select for
  the three to check the gate. Added to the receipt guard's table list with direct-SQL denial
  tests.
- **Gate:** the latest revision must be `test_access` with the needed operation, checked in the
  same transaction as each step: ingress attestation, worker decision and money application.
  Without it each step refuses; history stays readable. Suspension takes effect on the next
  transaction (same lock pattern as revocation in 0048).
- Recorded only by the owner: `gba-db admit-receipt-connection --tenant … --connection …
  --state test_access --evidence "<short text>"` over `GBA_MIGRATION_DATABASE_URL`, in the
  company's context (`owner_tenant_transaction`). Also `--state suspended`.

### 2. Ingress entry point

`python -m gorgona_booking.providers.ingress_main` (same pattern as `__main__.py`):

- Database: `GBA_RECEIPT_WRITER_DATABASE_URL` (the writer login only; the process refuses an
  unsafe role at start through the existing role check).
- Keys: `GBA_RECEIPT_SECRET_REFS` lists the references to load, e.g. `env:GBA_STRIPE_TEST_WEBHOOK_SECRET`.
  Only the `env:` store is supported in K0; each named variable must be set and non-empty or the
  process stops before listening. Values live only in memory as `SecretStr` and are never logged.
- Listens on **`127.0.0.1` only**, port `GBA_RECEIPT_PORT` (default **8787**); refuses any other
  host. Logs: request ID, route template, status, timing; no body, header or ingress ID.

### 3. Worker entry point

`python -m gorgona_booking.providers.worker_main`:

- Database: `GBA_RECEIPT_WORKER_DATABASE_URL` (worker login only, role check at start).
- Default **loop**: one `process_batch` every 5 seconds (bounded 1–300), stops cleanly on Ctrl+C
  or SIGTERM after the current batch. `--once` runs a single batch and exits.
- Logs: counts and outcomes per batch (`observed`, `needs_review`, reasons); no payload, account
  or customer data.

### 4. Tests (K0b)

Failing first, then green; synthetic signed events through the real entry points (in-process
server on a free port):

- missing, empty, wrong and rotated secret; secret never in captured logs or responses;
- no admission, suspended, wrong operation, other company's connection: refused, nothing stored;
- `test_access`: payment success, failure and refund are attested and decided; duplicate and
  retried deliveries create no second effect (E-05);
- direct SQL: runtime, writer and worker cannot record or change an admission; schema-drift guard;
- worker loop stops cleanly; `--once` exits; host other than `127.0.0.1` refused;
- upgrade 0056 → 0057 on a nonempty database (existing connections stay unadmitted).

Then the usual gates: focused, static, full, record before the code commit.

### 5. The owner's run (K0c)

All provider steps are the owner's; the agent never sees the secret. In order:

1. Agent (before): provisions on the local database the company's connection, config
   (`secret_ref = env:GBA_STRIPE_TEST_WEBHOOK_SECRET`), route and prints the ingress URL path.
2. Owner: `stripe login` (test sandbox, Connect platform with one connected test account).
3. Owner: `stripe listen --forward-connect-to localhost:8787/v1/provider-events/stripe/<ingress_id> --events payment_intent.succeeded,payment_intent.payment_failed,charge.refunded,refund.created,refund.updated`
   — it prints a signing secret; the owner sets it in their own terminal as
   `GBA_STRIPE_TEST_WEBHOOK_SECRET` and starts the ingress and the worker from that terminal.
4. Owner: `gba-db admit-receipt-connection … --state test_access`.
5. Owner: `stripe trigger payment_intent.succeeded --stripe-account acct_…`, then
   `payment_intent.payment_failed`, then `charge.refunded` for the same account.
6. A finance user applies one payment and one refund on the screen.
7. Agent (after): read-only queries in the company's context; a redacted record with event IDs,
   decisions, payment and journal IDs and amounts — no payload, secret or customer data. Then
   suspension is shown to refuse a further event.

The connection's `api_version` must equal the connected account's API version; the owner reads
it in the Stripe Dashboard (step 1 uses that value).

## Questions for the owner (each has a default)

1. **Who records the admission and how?** Default: you, with the `gba-db admit-receipt-connection`
   command on this computer (owner database login). Alternative: a SQL script you run.
2. **Link to the company's H4 declaration?** Default: optional for this test run. Alternative:
   required — the company must first submit an H4 request for charge and refund.
3. **Worker mode?** Default: a loop every 5 seconds with a clean stop, plus `--once`.
   Alternative: only `--once`, started by hand after each trigger.
4. **Port and path?** Default: `127.0.0.1:8787`, path `/v1/provider-events/stripe/<ingress_id>`.
5. **New dependency?** Default: none (standard library, existing uvicorn and Starlette).
6. **Evidence of your Stripe run?** Default: I read the database after your run and write a
   redacted record; you send me only the event IDs Stripe printed, if any are missing.
7. **Suspension undo?** Default: after `suspended` a new `test_access` revision is allowed (both
   recorded). Alternative: a suspended connection stays suspended; a new connection is needed.

## Out of scope

Live mode, real money, checkout or payment creation, fees, payouts, disputes, other currencies,
Azure, public URLs, production deployment, readiness changes, and any merge to `main`.
