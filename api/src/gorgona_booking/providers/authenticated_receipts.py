"""Internal isolated verifier boundary. No HTTP, provider client or payment authority.

An owner-provisioned route selects the company and connection; the active verification
config names which server-held key may check the raw bytes. A compromised writer can lie;
SQL does not verify the MAC. Operational admission is an independent future gate.
"""

from collections.abc import Mapping
from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from psycopg.pq import TransactionStatus
from pydantic import SecretStr

from gorgona_booking.business.contracts import Versioned
from gorgona_booking.db.pool import RuntimeConnection, RuntimePool, set_tenant_context
from gorgona_booking.db.provider_receipt_guard import assert_provider_receipt_ready
from gorgona_booking.providers.inbox import ReceiptBindingRejectedError, ReceiptResult, record_event
from gorgona_booking.providers.stripe_contracts import Sha256, SignedStripeEvent, StripeEventPolicy
from gorgona_booking.providers.stripe_events import verify_stripe_event

LOCK_TIMEOUT_MS = 5_000
STATEMENT_TIMEOUT_MS = 10_000
MAX_TIMEOUT_MS = 60_000


class UnsafeReceiptWriterRoleError(RuntimeError):
    """A writer credential is shared with the application or has excessive rights."""


class ReceiptAuthority(Versioned):
    """Read from owner-provisioned rows inside the receipt transaction, never from a request."""

    tenant_id: UUID
    connection_id: UUID
    book_id: UUID
    verification_config_id: UUID
    secret_ref: str
    policy: StripeEventPolicy


class AuthenticatedReceiptResult(Versioned):
    event_id: UUID
    connection_id: UUID
    book_id: UUID
    verification_config_id: UUID
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
    and not pg_catalog.pg_has_role(r.oid,'gba_receipt_worker','MEMBER')
    and not pg_catalog.has_schema_privilege(r.oid,'gba','CREATE')
    and not exists (
        select 1 from pg_catalog.pg_namespace n where n.nspname='gba'
          and pg_catalog.pg_has_role(r.oid,n.nspowner,'MEMBER'))
    and not exists (
        select 1 from pg_catalog.pg_class c join pg_catalog.pg_namespace n on n.oid=c.relnamespace
        where n.nspname='gba' and (
            pg_catalog.pg_has_role(r.oid,c.relowner,'MEMBER') or
            (c.relname<>all(array['provider_receipt_connections','provider_event_inbox',
                'provider_event_deliveries','provider_event_attestations',
                'provider_verification_configs','provider_receipt_routes']) and (
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


_ACTIVE_AUTHORITY = (
    "select v.id,v.secret_ref,c.book_id,c.namespace,c.account_id,c.api_version "
    "from gba.provider_verification_configs v join gba.provider_receipt_connections c "
    "on c.tenant_id=v.tenant_id and c.id=v.connection_id "
    "where v.tenant_id=%s and v.connection_id=%s and not v.revoked and not c.revoked"
)


async def _read_authority(conn: RuntimeConnection, ingress_id: UUID) -> ReceiptAuthority:
    """Route first, then its company context, then the active config and binding, unlocked.

    Only authority rows are read here: no inbox, ledger or other business data, no row lock
    and no catalog guard, so an unauthenticated caller costs these indexed reads alone.
    """
    route = await (
        await conn.execute(
            "select tenant_id,connection_id from gba.provider_receipt_routes where ingress_id=%s",
            (ingress_id,),
        )
    ).fetchone()
    if route is None:
        raise ReceiptBindingRejectedError()
    tenant_id, connection_id = route
    await set_tenant_context(conn, tenant_id)
    row = await (await conn.execute(_ACTIVE_AUTHORITY, (tenant_id, connection_id))).fetchone()
    if row is None:
        raise ReceiptBindingRejectedError()
    return _authority(tenant_id, connection_id, row)


async def _confirm_authority(conn: RuntimeConnection, authority: ReceiptAuthority) -> None:
    """After the signature: the same active config and binding, share-locked until commit."""
    row = await (
        await conn.execute(
            _ACTIVE_AUTHORITY
            + " and current_setting('transaction_isolation')='read committed' for share of v,c",
            (authority.tenant_id, authority.connection_id),
        )
    ).fetchone()
    if row is None or _authority(authority.tenant_id, authority.connection_id, row) != authority:
        raise ReceiptBindingRejectedError()


def _authority(tenant_id: UUID, connection_id: UUID, row: tuple[Any, ...]) -> ReceiptAuthority:
    config_id, secret_ref, book_id, namespace, account_id, api_version = row
    return ReceiptAuthority(
        tenant_id=tenant_id,
        connection_id=connection_id,
        book_id=book_id,
        verification_config_id=config_id,
        secret_ref=secret_ref,
        policy=StripeEventPolicy(
            namespace=namespace, account_id=account_id, api_version=api_version
        ),
    )


async def _attest_event(
    conn: RuntimeConnection,
    authority: ReceiptAuthority,
    event: SignedStripeEvent,
    result: ReceiptResult,
) -> None:
    await conn.execute(
        "insert into gba.provider_event_attestations "
        "(tenant_id,event_id,delivery_sha256,verification_config_id) values (%s,%s,%s,%s) "
        "on conflict do nothing",
        (
            authority.tenant_id,
            result.event_id,
            event.delivery_sha256,
            authority.verification_config_id,
        ),
    )


async def receive_routed_receipt(
    pool: RuntimePool,
    ingress_id: UUID,
    payload: bytes,
    signature: str | None,
    *,
    key_store: Mapping[str, SecretStr],
    now: datetime | None = None,
    lock_timeout_ms: int = LOCK_TIMEOUT_MS,
    statement_timeout_ms: int = STATEMENT_TIMEOUT_MS,
) -> AuthenticatedReceiptResult:
    """Resolve server-owned authority, verify raw bytes, then archive and attest in one commit.

    The ingress ID is the only routing input; company, connection, book, account policy and
    key come from owner-provisioned rows and the server-held key store. Before the signature
    check only a cheap writer-membership check runs and nothing is locked; after it the full
    guards run and the same active config and binding are share-locked before any write.
    Every lock wait and statement is
    bounded by the transaction-local timeouts. Return only after the transaction commits. A
    verified conflicting variant is retained, not applied. No original archive row is
    retroactively trusted, overwritten or relabeled. No raw bytes or keys are stored. The
    writer is a trusted verifier, not a financial worker.
    """
    if not (1 <= lock_timeout_ms <= MAX_TIMEOUT_MS and 1 <= statement_timeout_ms <= MAX_TIMEOUT_MS):
        raise ValueError("Receipt timeouts are out of range")
    async with pool.connection() as conn:
        if conn.info.transaction_status is not TransactionStatus.IDLE:
            raise ReceiptBindingRejectedError()
        async with conn.transaction():
            writer = await (
                await conn.execute(
                    "select pg_catalog.set_config('lock_timeout',%s,true),"
                    "pg_catalog.set_config('statement_timeout',%s,true),"
                    "pg_catalog.pg_has_role(current_user,'gba_receipt_writer','USAGE') "
                    "and not pg_catalog.pg_has_role(session_user,'gba_runtime','MEMBER')",
                    (str(lock_timeout_ms), str(statement_timeout_ms)),
                )
            ).fetchone()
            if writer is None or writer[2] is not True:
                # Fail fast for the ordinary runtime; the full role scan follows the signature.
                raise UnsafeReceiptWriterRoleError("Receipt writer database role is unsafe")
            authority = await _read_authority(conn, ingress_id)
            key = key_store.get(authority.secret_ref)
            if key is None:
                raise ReceiptBindingRejectedError()
            event = verify_stripe_event(
                payload, signature, policy=authority.policy, signing_keys=(key,), now=now
            )
            await assert_safe_receipt_writer_role(conn)
            await _confirm_authority(conn, authority)
            result = await record_event(conn, authority.connection_id, event)
            if result.book_id != authority.book_id:
                raise ReceiptBindingRejectedError()
            await _attest_event(conn, authority, event, result)
    return AuthenticatedReceiptResult(
        event_id=result.event_id,
        connection_id=result.connection_id,
        book_id=result.book_id,
        verification_config_id=authority.verification_config_id,
        delivery_sha256=event.delivery_sha256,
        disposition=result.disposition,
    )
