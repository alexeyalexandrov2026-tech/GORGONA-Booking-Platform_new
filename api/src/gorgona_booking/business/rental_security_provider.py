"""R5b (package R, RENT-01): provider evidence for a rental card hold, sandbox only.

docs/plan/PACKAGE_R5B_DESIGN_2026-11-07.md. A recorded security event names the signature-checked
test-mode receipt that shows it; the database checks the receipt's facts. Nothing is sent to the
provider and nothing changes a charge, a payment or the security figures.
"""

from typing import Literal
from uuid import UUID

from psycopg.errors import CheckViolation, UniqueViolation

from gorgona_booking.booking import idempotency
from gorgona_booking.booking.idempotency import IdempotencyScope
from gorgona_booking.booking.models import IdempotencyKeyReusedError
from gorgona_booking.business.module_gate import RENTAL_MODULE, module_writes
from gorgona_booking.business.rental import Strict, fingerprint, require_rental
from gorgona_booking.business.rental_bookings import load_booking
from gorgona_booking.business.rental_security import SecurityView, load_security
from gorgona_booking.db.pool import RuntimeConnection
from gorgona_booking.errors import ConflictError, NotFoundError


class RentalSecurityEvidenceError(ConflictError):
    """R5b decisions 2-3: the receipt does not show the event, or the event is already linked."""

    code = "RENTAL_SECURITY_EVIDENCE"


class EvidenceInput(Strict):
    schema_version: Literal[1]
    receipt_id: UUID


async def event_kind(conn: RuntimeConnection, booking_id: UUID, sequence: int) -> str:
    """The kind of a recorded event of the booking's security, or not found."""
    if await load_booking(conn, booking_id) is None:
        raise NotFoundError("Booking not found", booking_id=str(booking_id))
    security = await load_security(conn, booking_id)
    for e in security.events:
        if e.sequence == sequence:
            return e.kind
    raise NotFoundError("Security event not found", sequence=sequence)


async def link_receipt(
    conn: RuntimeConnection,
    business: UUID,
    booking_id: UUID,
    sequence: int,
    *,
    user_id: UUID,
    actor: str,
    key: str,
    body: EvidenceInput,
) -> SecurityView:
    """Name the sandbox receipt that shows a recorded security event (decisions 1-3)."""
    await require_rental(conn, business)
    scope = IdempotencyScope(business, actor, "rental.security_provider", key)
    request = fingerprint(f"{booking_id}:{sequence}", body)
    stored = await idempotency.claim(conn, scope, request)
    if stored is not None:
        if stored.request_hash != request:
            raise IdempotencyKeyReusedError("Key was used for another request")
        return await load_security(conn, booking_id)
    await event_kind(conn, booking_id, sequence)
    security = await load_security(conn, booking_id)
    receipt = await (
        await conn.execute(
            "select facts->'resource'->>'object', facts->'resource'->>'id', "
            "facts->'resource'->>'payment_intent_id' from gba.provider_event_inbox where id = %s",
            (body.receipt_id,),
        )
    ).fetchone()
    if receipt is None:
        raise NotFoundError("Receipt not found", receipt_id=str(body.receipt_id))
    intent = receipt[2] if receipt[0] == "charge" else receipt[1]
    if not isinstance(intent, str) or not intent.startswith("pi_"):
        raise RentalSecurityEvidenceError("The receipt names no payment intent")
    try:
        async with module_writes(RENTAL_MODULE), conn.transaction():
            await conn.execute(
                "insert into gba.rental_security_provider_links (tenant_id, security_id, "
                "sequence, receipt_id, intent, linked_by) values (%s, %s, %s, %s, %s, %s)",
                (business, security.security_id, sequence, body.receipt_id, intent, user_id),
            )
    except UniqueViolation as exc:
        raise RentalSecurityEvidenceError("The event already names its receipt") from exc
    except CheckViolation as exc:
        if (exc.diag.constraint_name or "").startswith("rental_security_provider_links_"):
            raise RentalSecurityEvidenceError(
                "The receipt does not show the security event"
            ) from exc
        raise
    await idempotency.complete(conn, scope, 200, {"booking_id": str(booking_id)})
    return await load_security(conn, booking_id)
