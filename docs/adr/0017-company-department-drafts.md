# ADR-0017: Company-owned department drafts

- Status: Accepted for this implementation phase (2026-10-04).
- Scope: master plan organizational structure; no employee assignment or group reporting.

## Decision

A department belongs to the existing business/tenant. Its stable identity and
internal code are separate from append-only named revisions. Codes are unique
within a business; equal names do not merge records. Nothing is provisioned by
default. An owner or unrestricted manager supplies the name and any links.

Each draft version may reference one parent department, one branch and one
legal entity of the same business, or leave each link empty. These links describe
structure and confer no authorization. They do not assert registration, payment
readiness, branch ownership or a published configuration. Multiple branch links
and staff assignments require a later explicit design.

Reuse the legal-entity pattern (ADR-0015): typed schema version 1,
expected revision, idempotency receipt, paginated reads/history and audit in one
authorized transaction. The existing business-structure advisory lock is held
before membership locks. A PostgreSQL trigger takes the same structure lock for
direct version inserts, enforces consecutive revisions and walks the latest parent
chain to reject self-parenting, missing saved parents and cycles. Writes require
READ COMMITTED: Repeatable Read can retain an old snapshot after waiting for the
lock, so the trigger rejects other isolation levels. The service returns an
unavailable error and rolls the entire command back. This assumption is explicit
and supported by [PostgreSQL 18 isolation documentation](https://www.postgresql.org/docs/18/transaction-iso.html).
Concurrent reparenting cannot commit a cycle. Composite foreign keys enforce tenant ownership
for every reference. Identities and versions reject updates and deletes.

Use the existing business.read/business.manage permissions. Company-wide read
does not imply edit rights; platform support remains read-only. Branch-scoped
and delegated requests are refused by the existing authorization boundary.
Both tables enable and force RLS, with tenant isolation and restrictive branch
and delegation policies. Schema readiness verifies the four new restrictive
definitions and fails closed when they are missing or changed.

The interface uses the existing business page, management API and strict response
validation. Failed uncertain saves retain their identity/key/body for replay;
stale edits retain the form until a deliberate reload. Linked choices are read
from the same company's data. No new service, runtime or dependency is introduced.

## Verification and rollback

See [acceptance evidence](../plan/evidence/2026-10-04-departments/ACCEPTANCE.md).
Exercise revisions, repeat/conflicting commands, foreign references, hierarchy
cycles, concurrent reparenting, rollback, direct SQL immutability, both restricted
scopes, schema damage and desktop/mobile browser persistence.

Migration 0012 is additive. Existing booking and legal-entity data are unchanged.
Production migration is separately gated. After deployment, disabling the feature
retains its data; do not roll back by deleting tables or rewriting applied migrations.
