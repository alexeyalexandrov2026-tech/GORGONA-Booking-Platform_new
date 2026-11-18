"""Versioned booking-to-customer-company binding for RENT-01 R-09."""

from datetime import datetime
from typing import Literal
from uuid import UUID

from psycopg.errors import CheckViolation, ForeignKeyViolation
from pydantic import BaseModel, Field

from gorgona_booking.booking import idempotency
from gorgona_booking.booking.idempotency import IdempotencyScope
from gorgona_booking.booking.models import IdempotencyKeyReusedError
from gorgona_booking.business.module_gate import RENTAL_MODULE, module_writes
from gorgona_booking.business.rental import (
    RentalRevisionConflictError,
    Strict,
    fingerprint,
    require_rental,
)
from gorgona_booking.business.rental_agreements import open_booking
from gorgona_booking.db.pool import RuntimeConnection
from gorgona_booking.errors import InvalidReferenceError, NotFoundError


class CustomerCompanyInput(Strict):
    schema_version: Literal[1]
    expected_revision: int = Field(ge=0, le=2_147_483_646)
    company_id: UUID | None


class CustomerCompanyVersion(BaseModel):
    revision: int
    company_id: UUID | None
    recorded_at: datetime


class CustomerCompanyView(BaseModel):
    schema_version: Literal[1] = 1
    booking_id: UUID
    customer_id: UUID
    revision: int
    company_id: UUID | None
    versions: list[CustomerCompanyVersion]


async def load_customer_company(conn: RuntimeConnection, booking_id: UUID) -> CustomerCompanyView:
    rows = await (
        await conn.execute(
            "select b.customer_id, c.revision, c.company_id, c.created_at "
            "from gba.rental_bookings b left join gba.rental_customer_companies c "
            "on (b.tenant_id, b.id) = (c.tenant_id, c.booking_id) "
            "where b.id = %s order by c.revision",
            (booking_id,),
        )
    ).fetchall()
    if not rows:
        raise NotFoundError("Booking not found", booking_id=str(booking_id))
    customer_id, revision, company_id, _ = rows[-1]
    return CustomerCompanyView(
        booking_id=booking_id,
        customer_id=customer_id,
        revision=revision or 0,
        company_id=company_id,
        versions=[
            CustomerCompanyVersion(revision=row[1], company_id=row[2], recorded_at=row[3])
            for row in rows
            if row[1] is not None
        ],
    )


async def save_customer_company(
    conn: RuntimeConnection,
    business: UUID,
    booking_id: UUID,
    *,
    user_id: UUID,
    actor: str,
    key: str,
    body: CustomerCompanyInput,
) -> CustomerCompanyView:
    await require_rental(conn, business)
    scope = IdempotencyScope(business, actor, "rental.customer_company", key)
    request = fingerprint(str(booking_id), body)
    stored = await idempotency.claim(conn, scope, request)
    if stored is not None:
        if stored.request_hash != request:
            raise IdempotencyKeyReusedError("Key was used for another request")
        return await load_customer_company(conn, booking_id)

    await conn.execute("select gba.lock_rental_booking_class(%s, %s)", (business, booking_id))
    booking = await open_booking(conn, booking_id)
    current = await load_customer_company(conn, booking_id)
    if body.expected_revision != current.revision:
        raise RentalRevisionConflictError(
            "The customer company changed since it was read", revision=current.revision
        )
    if body.company_id == business:
        raise InvalidReferenceError("The customer company must be separate", field="company_id")

    try:
        async with module_writes(RENTAL_MODULE), conn.transaction():
            await conn.execute(
                "insert into gba.rental_customer_companies "
                "(tenant_id, booking_id, revision, customer_id, company_id, created_by) "
                "values (%s, %s, %s, %s, %s, %s)",
                (
                    business,
                    booking_id,
                    current.revision + 1,
                    booking.customer_id,
                    body.company_id,
                    user_id,
                ),
            )
    except ForeignKeyViolation as exc:
        if exc.diag.constraint_name == "rental_customer_company_recipient":
            raise InvalidReferenceError("Customer company not found", field="company_id") from exc
        raise
    except CheckViolation as exc:
        if exc.diag.constraint_name == "rental_customer_company_revision":
            raise RentalRevisionConflictError("The customer company changed") from exc
        raise
    await idempotency.complete(conn, scope, 200, {"booking_id": str(booking_id)})
    return await load_customer_company(conn, booking_id)
