"""Tenant-scoped receipt storage; the caller owns commit and acknowledgement.

Only trusted code may pass a signature-checked envelope. PostgreSQL stores typed
facts, not a cryptographic attestation. No HTTP route, operational admission,
worker or financial effect is supplied here. H4 cannot provision these bindings.
"""

from typing import Literal
from uuid import UUID, uuid7

from psycopg.pq import TransactionStatus
from psycopg.types.json import Jsonb

from gorgona_booking.business.contracts import Versioned
from gorgona_booking.db.pool import RuntimeConnection
from gorgona_booking.db.provider_receipt_guard import assert_provider_receipt_ready
from gorgona_booking.errors import DomainError
from gorgona_booking.providers.stripe_contracts import SignedStripeEvent


class ReceiptBindingRejectedError(DomainError):
    code = "PROVIDER_RECEIPT_REFUSED"

    def __init__(self) -> None:
        super().__init__("Provider receipt was refused")


class ReceiptResult(Versioned):
    event_id: UUID
    connection_id: UUID
    book_id: UUID
    disposition: Literal["recorded", "duplicate", "conflict"]
    authority: Literal["receipt_only_not_admitted"] = "receipt_only_not_admitted"


async def record_event(
    conn: RuntimeConnection, connection_id: UUID, event: SignedStripeEvent
) -> ReceiptResult:
    """Write within the caller's tenant transaction. A result does not imply commit.

    INSERT ON CONFLICT waits on an uncommitted identity; the following statement
    sees the winner at READ COMMITTED. Distinct raw digests keep their normalized
    variants, while exact retries consume no new rows. Revocation serializes with
    receipt insertion via a shared connection-row lock held until transaction end.
    """
    if conn.info.transaction_status is not TransactionStatus.INTRANS:
        raise ReceiptBindingRejectedError()
    await assert_provider_receipt_ready(conn)
    binding = await (
        await conn.execute(
            "select tenant_id,book_id,namespace,account_id,api_version,revoked "
            "from gba.provider_receipt_connections where id=%s "
            "and current_setting('transaction_isolation')='read committed' for share",
            (connection_id,),
        )
    ).fetchone()
    if (
        binding is None
        or binding[5]
        or binding[2:5]
        != (
            event.namespace,
            event.account_id,
            event.api_version,
        )
    ):
        raise ReceiptBindingRejectedError()
    tenant, book, *_ = binding
    facts = event.model_dump(mode="json", exclude={"delivery_sha256"})
    inserted = await (
        await conn.execute(
            "insert into gba.provider_event_inbox (tenant_id,id,connection_id,facts) "
            "values (%s,%s,%s,%s) on conflict (namespace,account_id,provider_event_id) "
            "do nothing returning id",
            (tenant, uuid7(), connection_id, Jsonb(facts)),
        )
    ).fetchone()
    original = await (
        await conn.execute(
            "select id,connection_id,facts from gba.provider_event_inbox "
            "where namespace=%s and account_id=%s and provider_event_id=%s",
            (event.namespace, event.account_id, event.event_id),
        )
    ).fetchone()
    if original is None or original[1] != connection_id:
        raise ReceiptBindingRejectedError()
    await conn.execute(
        "insert into gba.provider_event_deliveries (tenant_id,event_id,delivery_sha256,facts) "
        "values (%s,%s,%s,%s) on conflict do nothing",
        (tenant, original[0], event.delivery_sha256, Jsonb(facts)),
    )
    delivery = await (
        await conn.execute(
            "select facts from gba.provider_event_deliveries "
            "where tenant_id=%s and event_id=%s and delivery_sha256=%s",
            (tenant, original[0], event.delivery_sha256),
        )
    ).fetchone()
    if delivery is None or delivery[0] != facts:
        raise ReceiptBindingRejectedError()
    return ReceiptResult(
        event_id=original[0],
        connection_id=connection_id,
        book_id=book,
        disposition="conflict" if original[2] != facts else "recorded" if inserted else "duplicate",
    )
