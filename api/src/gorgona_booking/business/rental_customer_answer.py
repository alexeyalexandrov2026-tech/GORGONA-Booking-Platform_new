"""R-09: a live customer grant can accept the booking's initial base quote."""

import unicodedata
from datetime import UTC, datetime
from typing import Annotated, Literal
from uuid import UUID

from psycopg.errors import CheckViolation
from pydantic import AfterValidator, BaseModel, Field

from gorgona_booking.booking import idempotency
from gorgona_booking.booking.idempotency import IdempotencyScope
from gorgona_booking.booking.models import IdempotencyKeyReusedError
from gorgona_booking.business import rental_agreements as agreements
from gorgona_booking.business.rental import (
    RentalRevisionConflictError,
    Strict,
    fingerprint,
    require_rental,
)
from gorgona_booking.business.rental_customer_company import (
    CustomerCompanyView,
    load_customer_company,
)
from gorgona_booking.business.rental_rates import QuoteView, RateCardView, in_force, priced
from gorgona_booking.db.pool import RuntimeConnection
from gorgona_booking.errors import ConflictError, NotFoundError
from gorgona_booking.tenancy.authorization import DelegationScope, PermissionDeniedError


class RentalProposalStaleError(ConflictError):
    code = "RENTAL_PROPOSAL_STALE"


ReviewHash = Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]


def plain_line(value: str) -> str:
    """R-09 one-line text has no NUL or other control character (422, not a database error)."""
    if any(unicodedata.category(char) == "Cc" for char in value):
        raise ValueError("text without control characters")
    return value


def plain_text(value: str) -> str:
    """R-09 free text keeps line breaks and tabs but no NUL or other control character."""
    if any(unicodedata.category(char) == "Cc" and char not in "\t\n\r" for char in value):
        raise ValueError("text without control characters other than line breaks and tabs")
    return value


Signatory = Annotated[agreements.Name, AfterValidator(plain_line)]


class CustomerAnswerInput(Strict):
    schema_version: Literal[1]
    binding_revision: int = Field(ge=1, le=2_147_483_647)
    review_hash: ReviewHash
    signatory: Signatory


class ProposalLocation(BaseModel):
    name: str
    timezone: str


class ProposalTerms(BaseModel):
    schema_version: Literal[1] = 1
    booking_id: UUID
    pickup_location_id: UUID
    return_location_id: UUID
    binding_revision: int
    class_name: str
    pickup: ProposalLocation
    return_location: ProposalLocation | None
    quote: QuoteView


class ProposalView(ProposalTerms):
    status: Literal["pending"] = "pending"
    review_hash: ReviewHash


class Receipt(BaseModel):
    schema_version: Literal[1] = 1
    booking_id: UUID
    agreement_id: UUID
    version: Literal[1] = 1
    status: Literal["accepted"] = "accepted"
    review_hash: ReviewHash
    accepted_at: datetime


async def authorized_binding(
    conn: RuntimeConnection,
    business: UUID,
    booking_id: UUID,
    delegation: DelegationScope,
    *,
    lock: bool,
) -> CustomerCompanyView:
    """The booking's customer binding, when it names the grant's company.

    Authorization has already locked the grant and the delegate row. A write (`lock`) then
    takes the booking class lock, so writes lock the grant first and the class second; a
    read takes no class lock and does not queue behind writes on other bookings of the class.
    """
    await require_rental(conn, business)
    if lock:
        await conn.execute("select gba.lock_rental_booking_class(%s, %s)", (business, booking_id))
    # The class lock can wait, so check the deadline after it and before reading or returning data.
    row = await (
        await conn.execute("select %s > pg_catalog.statement_timestamp()", (delegation.expires_at,))
    ).fetchone()
    if row is None or not row[0]:
        raise PermissionDeniedError("The customer grant has expired")
    binding = await load_customer_company(conn, booking_id)
    if binding.company_id != delegation.servicer_business_id:
        raise NotFoundError("Booking not found", booking_id=str(booking_id))
    return binding


async def _pending_offer(
    conn: RuntimeConnection, booking_id: UUID, binding_revision: int
) -> tuple[ProposalView, RateCardView]:
    booking = await agreements.open_booking(conn, booking_id)
    existing = await (
        await conn.execute(
            "select 1 from gba.rental_agreements where booking_id = %s", (booking_id,)
        )
    ).fetchone()
    if existing is not None:
        raise agreements.RentalAgreementExistsError("The booking already has an agreement")
    card = await in_force(conn, booking.class_id, booking.pickup_location_id, booking.booked_at)
    details = await (
        await conn.execute(
            "select c.name, pickup.name, pickup.timezone, returned.name, returned.timezone "
            "from gba.rental_bookings b "
            "join gba.rental_classes c on (c.tenant_id, c.id) = (b.tenant_id, b.class_id) "
            "join gba.locations pickup on (pickup.tenant_id, pickup.id) = "
            "(b.tenant_id, b.pickup_location_id) "
            "left join gba.locations returned on (returned.tenant_id, returned.id) = "
            "(b.tenant_id, b.return_location_id) where b.id = %s",
            (booking_id,),
        )
    ).fetchone()
    if details is None:
        raise NotFoundError("Booking not found", booking_id=str(booking_id))
    class_name, pickup_name, pickup_zone, return_name, return_zone = details
    terms = ProposalTerms(
        booking_id=booking_id,
        pickup_location_id=booking.pickup_location_id,
        return_location_id=booking.return_location_id,
        binding_revision=binding_revision,
        class_name=class_name,
        pickup=ProposalLocation(name=pickup_name, timezone=pickup_zone),
        return_location=(
            ProposalLocation(name=return_name, timezone=return_zone)
            if return_name is not None
            else None
        ),
        quote=priced(card, booking.starts_at, booking.ends_at, []),
    )
    review_hash = fingerprint("rental.initial_base_quote.v1", terms)
    return ProposalView(
        booking_id=terms.booking_id,
        pickup_location_id=terms.pickup_location_id,
        return_location_id=terms.return_location_id,
        binding_revision=terms.binding_revision,
        class_name=terms.class_name,
        pickup=terms.pickup,
        return_location=terms.return_location,
        quote=terms.quote,
        review_hash=review_hash,
    ), card


async def load_proposal(
    conn: RuntimeConnection, business: UUID, booking_id: UUID, delegation: DelegationScope
) -> ProposalView | Receipt:
    binding = await authorized_binding(conn, business, booking_id, delegation, lock=False)
    # The receipt belongs to the agreement, the company and the grant that accepted it; a later
    # re-save of the company binding does not hide it.
    accepted = await (
        await conn.execute(
            "select a.id, v.customer_review_hash, v.accepted_at from gba.rental_agreements a "
            "join gba.rental_agreement_versions v on (v.tenant_id, v.agreement_id) = "
            "(a.tenant_id, a.id) and v.version = 1 where a.booking_id = %s "
            "and v.source = 'platform' and v.customer_company_id = %s "
            "and v.customer_grant_id = %s",
            (booking_id, delegation.servicer_business_id, delegation.grant_id),
        )
    ).fetchone()
    if accepted is not None:
        return Receipt(
            booking_id=booking_id,
            agreement_id=accepted[0],
            review_hash=accepted[1],
            accepted_at=accepted[2].astimezone(UTC),
        )
    view, _ = await _pending_offer(conn, booking_id, binding.revision)
    return view


async def accept_proposal(
    conn: RuntimeConnection,
    business: UUID,
    booking_id: UUID,
    delegation: DelegationScope,
    *,
    user_id: UUID,
    actor: str,
    key: str,
    body: CustomerAnswerInput,
) -> Receipt:
    binding = await authorized_binding(conn, business, booking_id, delegation, lock=True)
    # A retry returns the stored answer before the revision and offer checks, so a later
    # re-save of the binding cannot block it.
    scope = IdempotencyScope(business, actor, "rental.customer_answer", key)
    request = fingerprint(f"{booking_id}:{delegation.grant_id}", body)
    stored = await idempotency.claim(conn, scope, request)
    if stored is not None:
        if stored.request_hash != request:
            raise IdempotencyKeyReusedError("Key was used for another request")
        return Receipt.model_validate(stored.body)
    if body.binding_revision != binding.revision:
        raise RentalRevisionConflictError("The customer company changed since the offer was read")

    offer, card = await _pending_offer(conn, booking_id, binding.revision)
    if offer.review_hash != body.review_hash:
        raise RentalProposalStaleError("Review the current offer before accepting it")
    clock = await (await conn.execute("select now()")).fetchone()
    if clock is None:
        raise RuntimeError("PostgreSQL did not return the transaction time")
    accepted_at: datetime = clock[0].astimezone(UTC)
    proof = agreements.PlatformAcceptance(
        accepted_by=body.signatory,
        accepted_at=accepted_at,
        company_id=delegation.servicer_business_id,
        grant_id=delegation.grant_id,
        binding_revision=binding.revision,
        review_hash=body.review_hash,
    )
    try:
        agreement_id = await agreements.create_initial_agreement(
            conn, business, booking_id, card, offer.quote, proof, user_id
        )
    except CheckViolation as exc:
        if exc.diag.constraint_name == "rental_agreement_customer_scope":
            raise PermissionDeniedError("Customer grant does not authorize this booking") from exc
        raise
    receipt = Receipt(
        booking_id=booking_id,
        agreement_id=agreement_id,
        review_hash=body.review_hash,
        accepted_at=accepted_at,
    )
    await idempotency.complete(conn, scope, 200, receipt.model_dump(mode="json"))
    return receipt
