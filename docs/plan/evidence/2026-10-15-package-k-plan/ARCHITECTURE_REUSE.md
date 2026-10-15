# Package K — current architecture and reuse evidence

Inspected 2026-10-15 at source baseline `df88c20687333668d39fe76a26eabca691e62cb0`.
This is planning evidence. No provider runtime, admission, schema or deployment was changed.
[Plan](../../PACKAGE_K_PLAN_2026-10-15.md), [ADR-0027](../../../adr/0027-provider-events-and-reconciliation.md).

## Source candidates and decisions

| Existing source | Observed behavior | Proposed reuse or required extension |
|---|---|---|
| [provider_admission_contracts.py](../../../../api/src/gorgona_booking/business/provider_admission_contracts.py) | AdmissionAssessment has only not_checked/suspended/unsupported; OperationalCapabilities accepts false only | Preserve declarations; introduce separately verified connection evidence, not a positive manual flag |
| [provider_admission.py](../../../../api/src/gorgona_booking/business/provider_admission.py) and [route](../../../../api/src/gorgona_booking/api/provider_admission.py) | Company-wide finance access, insert-only versions/evidence, ledger lock and durable recovery | Reuse access/version/recovery patterns for operator actions; not an already verified provider connection |
| [0031_provider_admission.sql](../../../../api/src/gorgona_booking/db/migrations/0031_provider_admission.sql), [guard](../../../../api/src/gorgona_booking/db/provider_admission_guard.py) | SQL false-capability constraints and fail-closed runtime schema checks | Keep 0031 immutable; a new capability/provenance path needs forward schema and guard tests |
| [settlement_contracts.py](../../../../api/src/gorgona_booking/business/settlement_contracts.py) | PaymentConfirmInput requires literal manual_attestation and a user-selected allocation/date/cash account | Do not pass provider facts through this public input; preserve H compatibility |
| [settlements.py](../../../../api/src/gorgona_booking/business/settlements.py) | confirm checks revision, reserve, actual date, amount and external identity; writes payment, allocation and journal atomically | Extract a narrow posting primitive only for a real provider caller, keeping SQL cap and lineage parity |
| [ledger.py](../../../../api/src/gorgona_booking/business/ledger.py), [0024_external_payments.sql](../../../../api/src/gorgona_booking/db/migrations/0024_external_payments.sql) | Existing ledger lock, immutable entries and managed payment-source checks | Reuse the single G book; extend legitimate provider provenance, not a parallel money ledger |
| [commands.py](../../../../api/src/gorgona_booking/business/commands.py) and [idempotency.py](../../../../api/src/gorgona_booking/booking/idempotency.py) | Typed command replay/fingerprint and same-transaction audit | Reuse for human commands; permanent provider dedup must be separate from receipt expiry |
| [pool.py](../../../../api/src/gorgona_booking/db/pool.py), [authorization.py](../../../../api/src/gorgona_booking/tenancy/authorization.py) | Transaction-local tenant context and explicit actor permissions | Reuse RLS isolation; define a scoped service principal rather than impersonating a staff member |
| [resolver.py](../../../../api/src/gorgona_booking/tenancy/resolver.py), [0001_tenancy.sql](../../../../api/src/gorgona_booking/db/migrations/0001_tenancy.sql) | Minimal readable host-routing table; live customer-site resolver | Minimal-routing design candidate only; do not require booking storefront readiness for provider callbacks |
| [app.py](../../../../api/src/gorgona_booking/api/app.py), [pyproject.toml](../../../../api/pyproject.toml) | Existing app factory; Python 3.14, FastAPI/Pydantic/psycopg; no Stripe dependency | Add a bounded adapter/route after K1 checks; no new app/framework or dependency in this planning slice |
| [Booking integration tests](../../../../api/tests/integration), [container test](../../../../api/tests/container/test_container_image.py), [CI](../../../../.github/workflows/ci.yml) | Actual PostgreSQL, browser/axe and production-image gates | Reuse harnesses with new disposable clusters and controlled provider fixtures; actual Stripe acceptance is separate |

Search of `api/src` and `api/tests` for inbox/outbox/webhook/Stripe found no provider
implementation. Filename inventory found only shared command/idempotency helpers;
the separate `ai/src/gorgona_ai/jobs/runtime.py` is not a reusable payment worker.
[RELEASE_PLAN](../../../architecture/RELEASE_PLAN.md) describes a future M6 inbox/outbox.
[Azure architecture](../../../architecture/AZURE_ARCHITECTURE.md) remains the hosting
authority; proposed PostgreSQL processing does not authorize cloud infrastructure.
Historical OCI wording in TARGET_ARCHITECTURE is subordinate to accepted ADR-0012.

## Current primary-source checks

Checked through public documentation only on 2026-10-15; no authenticated Dashboard,
CLI login, account discovery, key creation or provider operation was performed.

- [Stripe webhook guide](https://docs.stripe.com/webhooks): raw bytes are needed for
  signature validation; deliveries can repeat or arrive out of order, and distinct
  event IDs can describe the same object operation. Stripe recommends asynchronous
  handling. K's proposed durable receipt and separate financial-operation identity
  are engineering responses to those documented behaviors, not provider guarantees
  of exactly-once delivery. Event timestamps are not used as an ordering cursor.
- [Connect webhooks](https://docs.stripe.com/connect/webhooks): connected-account
  events identify an account, and resource retrieval needs that account context.
  Endpoint environment alone is insufficient: live/test delivery behavior and
  sandbox scope need explicit verification. This supports the proposed account,
  namespace and mode binding. It does not establish this owner's eligibility.
- [Event object](https://docs.stripe.com/api/events/object): event/object identities,
  mode and API-version information inform the versioned decoder boundary. An
  opaque metadata tenant ID is not an authorization mechanism.
- [Currency rules](https://docs.stripe.com/currencies): payment and payout currency
  rules need an explicit mapping to the book's exact minor units. No blanket two
  decimal conversion or unverified provider support is assumed.
- [Official stripe-python repository](https://github.com/stripe/stripe-python):
  verified upstream candidate for the adapter. No package/version was installed;
  Python 3.14 compatibility, license and API-format pinning remain K1 adoption checks.
- [Stripe testing guide](https://docs.stripe.com/testing): future provider checks
  must use the explicitly selected test environment. Local signed fixtures are
  labeled synthetic and cannot count as authenticated merchant admission evidence.

## Acceptance of this planning slice

The planning validator must require: only the declared documentation files changed;
api/web/schema/dependencies/readiness/workflows unchanged; every local document/source
link resolves; UTF-8/JSON and whitespace checks pass; K-01–K-14 are all NOT TESTED;
ADR-0027 is Proposed; no K publication/CI/admission is claimed. Source file digests
and exact commands are retained in CHECKS.json and the external run directory.

No functional, performance or concurrency test is necessary for this documentation
change. Baseline CI 158 is historical evidence for inherited source, not CI of the
new K planning commit. Code phases will require failing tests before fixes, focused
checks before full gates, observed lock waits and an independent review before acceptance.
