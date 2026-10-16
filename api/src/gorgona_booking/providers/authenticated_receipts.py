"""Internal isolated verifier boundary. No HTTP, provider client or payment authority.

The caller must supply server-owned binding/key configuration and a dedicated
writer pool inaccessible to the ordinary API. A compromised writer can lie; SQL
does not verify the MAC. Operational admission is an independent future gate.
"""

from datetime import datetime
from typing import Literal
from uuid import UUID

from psycopg.pq import TransactionStatus
from pydantic import SecretStr

from gorgona_booking.business.contracts import Versioned
from gorgona_booking.db.pool import RuntimeConnection, RuntimePool, set_tenant_context
from gorgona_booking.db.provider_receipt_guard import assert_provider_receipt_ready
from gorgona_booking.providers.inbox import ReceiptBindingRejectedError, ReceiptResult, record_event
from gorgona_booking.providers.stripe_contracts import Sha256, SignedStripeEvent, StripeEventPolicy
from gorgona_booking.providers.stripe_events import verify_stripe_event


class UnsafeReceiptWriterRoleError(RuntimeError):
    """A writer credential is shared with the application or has excessive rights."""


class ReceiptVerifierBinding(Versioned):
    """Trusted server configuration; none of these fields may come from request metadata."""

    tenant_id: UUID
    connection_id: UUID
    book_id: UUID
    verification_config_id: UUID
    policy: StripeEventPolicy


class AuthenticatedReceiptResult(Versioned):
    event_id: UUID
    connection_id: UUID
    book_id: UUID
    delivery_sha256: Sha256
    disposition: Literal["recorded", "duplicate", "conflict"]
    authority: Literal["signature_checked_not_admitted"] = "signature_checked_not_admitted"


async def assert_safe_receipt_writer_role(conn: RuntimeConnection) -> None:
    row = await (
        await conn.execute("""
select bool_and(not (r.rolsuper or r.rolbypassrls or r.rolcreaterole
    or r.rolcreatedb or r.rolreplication)
    and pg_catalog.pg_has_role(r.oid,'gba_receipt_writer','USAGE')
    and not pg_catalog.pg_has_role(r.oid,'gba_runtime','MEMBER')
    and not pg_catalog.has_schema_privilege(r.oid,'gba','CREATE')
    and not exists (
        select 1 from pg_catalog.pg_namespace n where n.nspname='gba'
          and pg_catalog.pg_has_role(r.oid,n.nspowner,'MEMBER'))
    and not exists (
        select 1 from pg_catalog.pg_class c join pg_catalog.pg_namespace n on n.oid=c.relnamespace
        where n.nspname='gba' and (
            pg_catalog.pg_has_role(r.oid,c.relowner,'MEMBER') or
            (c.relname<>all(array['provider_receipt_connections','provider_event_inbox',
                'provider_event_deliveries','provider_event_attestations']) and (
                pg_catalog.has_table_privilege(r.oid,c.oid,
                    'SELECT,INSERT,UPDATE,DELETE,TRUNCATE,REFERENCES,TRIGGER')
                or pg_catalog.has_any_column_privilege(r.oid,c.oid,
                    'SELECT,INSERT,UPDATE,REFERENCES'))))))
from pg_catalog.pg_roles r where r.rolname in (current_user,session_user)
    or pg_catalog.pg_has_role(session_user,r.oid,'MEMBER')
""")
    ).fetchone()
    if row is None or row[0] is not True:
        raise UnsafeReceiptWriterRoleError("Receipt writer database role is unsafe")
    await assert_provider_receipt_ready(conn)


async def _attest_event(
    conn: RuntimeConnection,
    scope: ReceiptVerifierBinding,
    event: SignedStripeEvent,
    result: ReceiptResult,
) -> None:
    await conn.execute(
        "insert into gba.provider_event_attestations "
        "(tenant_id,event_id,delivery_sha256,verification_config_id) values (%s,%s,%s,%s) "
        "on conflict do nothing",
        (scope.tenant_id, result.event_id, event.delivery_sha256, scope.verification_config_id),
    )


async def receive_signed_receipt(
    pool: RuntimePool,
    scope: ReceiptVerifierBinding,
    payload: bytes,
    signature: str | None,
    *,
    signing_keys: tuple[SecretStr, ...],
    now: datetime | None = None,
) -> AuthenticatedReceiptResult:
    """Verify raw bytes first; return only after the scoped transaction commits.

    A verified conflicting variant is retained, not applied. No original archive
    row is retroactively trusted, overwritten or relabeled. No raw bytes/keys are
    stored. The configured writer is a trusted verifier, not a financial worker.
    """
    event = verify_stripe_event(
        payload, signature, policy=scope.policy, signing_keys=signing_keys, now=now
    )
    async with pool.connection() as conn:
        if conn.info.transaction_status is not TransactionStatus.IDLE:
            raise ReceiptBindingRejectedError()
        async with conn.transaction():
            await set_tenant_context(conn, scope.tenant_id)
            await assert_safe_receipt_writer_role(conn)
            result = await record_event(conn, scope.connection_id, event)
            if result.book_id != scope.book_id:
                raise ReceiptBindingRejectedError()
            await _attest_event(conn, scope, event, result)
    return AuthenticatedReceiptResult(
        event_id=result.event_id,
        connection_id=result.connection_id,
        book_id=result.book_id,
        delivery_sha256=event.delivery_sha256,
        disposition=result.disposition,
    )
