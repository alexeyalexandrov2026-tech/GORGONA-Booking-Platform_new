"""R-09: customers accept explicitly issued agreement changes under a live grant."""

from datetime import UTC, datetime
from typing import Annotated, Literal, Self
from uuid import UUID

from psycopg.errors import CheckViolation
from psycopg.types.json import Jsonb
from pydantic import AwareDatetime, BaseModel, Field, model_validator

from gorgona_booking.booking import idempotency
from gorgona_booking.booking.idempotency import IdempotencyScope
from gorgona_booking.booking.models import IdempotencyKeyReusedError
from gorgona_booking.business import rental_agreements as agreements
from gorgona_booking.business import rental_extensions as extensions
from gorgona_booking.business.module_gate import RENTAL_MODULE, module_writes
from gorgona_booking.business.rental import Strict, fingerprint, require_rental
from gorgona_booking.business.rental_customer_answer import (
    RentalProposalStaleError,
    ReviewHash,
    authorized_binding,
)
from gorgona_booking.business.rental_customer_company import (
    CustomerCompanyView,
    load_customer_company,
)
from gorgona_booking.business.rental_rates import QuoteExtraInput, QuoteView, load_card, priced
from gorgona_booking.db.pool import RuntimeConnection
from gorgona_booking.errors import NotFoundError
from gorgona_booking.tenancy.authorization import DelegationScope, PermissionDeniedError

Revision = Annotated[int, Field(ge=1, le=2_147_483_647)]


class ProposedPeriod(Strict):
    starts_at: AwareDatetime
    ends_at: AwareDatetime

    @model_validator(mode="after")
    def _valid_period(self) -> Self:
        if self.ends_at <= self.starts_at or self.ends_at - self.starts_at > extensions.LONGEST:
            raise ValueError("A period ends after it starts and lasts at most 366 days")
        return self


class OfferInput(Strict):
    schema_version: Literal[1]
    expected_previous_offer_revision: int = Field(ge=0, le=2_147_483_646)
    expected_agreement_version: Revision
    expected_binding_revision: Revision
    period: ProposedPeriod | None = None
    extras: Annotated[list[QuoteExtraInput], Field(max_length=50)]
    reason: agreements.Reason

    @model_validator(mode="after")
    def _distinct(self) -> Self:
        if len({line.code for line in self.extras}) != len(self.extras):
            raise ValueError("Every extra is chosen once")
        return self


class OfferTerms(BaseModel):
    schema_version: Literal[1] = 1
    booking_id: UUID
    revision: Revision
    agreement_version: Revision
    binding_revision: Revision
    quote: QuoteView
    reason: str


class Offer(OfferTerms):
    status: Literal["pending"] = "pending"
    review_hash: ReviewHash


class OfferForCustomer(Offer):
    pickup_timezone: str
    extra_names: dict[str, str]


class ChangeAnswerInput(Strict):
    schema_version: Literal[1]
    review_hash: ReviewHash
    signatory: agreements.Name


class ChangeReceipt(BaseModel):
    schema_version: Literal[1] = 1
    status: Literal["accepted"] = "accepted"
    booking_id: UUID
    agreement_id: UUID
    revision: Revision
    agreement_version: Revision
    review_hash: ReviewHash
    accepted_at: datetime


async def _find_offer(
    conn: RuntimeConnection, booking_id: UUID, revision: int | None = None
) -> Offer | None:
    row = await (
        await conn.execute(
            "select revision, agreement_version, binding_revision, quote, reason, review_hash "
            "from gba.rental_customer_change_offers where booking_id = %s "
            "and (%s::integer is null or revision = %s) order by revision desc limit 1",
            (booking_id, revision, revision),
        )
    ).fetchone()
    if row is None:
        return None
    return Offer(
        booking_id=booking_id,
        revision=row[0],
        agreement_version=row[1],
        binding_revision=row[2],
        quote=QuoteView.model_validate(row[3]),
        reason=row[4],
        review_hash=row[5],
    )


async def current_offer(conn: RuntimeConnection, booking_id: UUID) -> Offer | None:
    await load_customer_company(conn, booking_id)
    return await _find_offer(conn, booking_id)


async def _open_agreement(conn: RuntimeConnection, booking_id: UUID) -> agreements.AgreementView:
    await agreements.open_booking(conn, booking_id)
    settled = await (
        await conn.execute(
            "select 1 from gba.rental_settlements where booking_id = %s", (booking_id,)
        )
    ).fetchone()
    if settled is not None:
        raise agreements.RentalAgreementSettledError("The rental agreement is already settled")
    return await agreements.load_agreement(conn, booking_id)


async def issue(
    conn: RuntimeConnection,
    business: UUID,
    booking_id: UUID,
    *,
    user_id: UUID,
    actor: str,
    key: str,
    body: OfferInput,
) -> Offer:
    await require_rental(conn, business)
    scope = IdempotencyScope(business, actor, "rental.issue_customer_change", key)
    request = fingerprint(str(booking_id), body)
    stored = await idempotency.claim(conn, scope, request)
    if stored is not None:
        if stored.request_hash != request:
            raise IdempotencyKeyReusedError("Key was used for another request")
        return Offer.model_validate(stored.body)

    await conn.execute("select gba.lock_rental_booking_class(%s, %s)", (business, booking_id))
    current = await _open_agreement(conn, booking_id)
    binding = await load_customer_company(conn, booking_id)
    previous = await _find_offer(conn, booking_id)
    previous_revision = previous.revision if previous else 0
    if (
        binding.company_id is None
        or body.expected_binding_revision != binding.revision
        or body.expected_agreement_version != current.current_version
        or body.expected_previous_offer_revision != previous_revision
    ):
        raise RentalProposalStaleError("Reload the rental agreement and its customer binding")
    latest = current.versions[-1]
    card = await load_card(conn, latest.rate_card_id)
    if card is None:
        raise NotFoundError("Rate card not found", rate_card_id=str(latest.rate_card_id))
    quote = priced(
        card,
        body.period.starts_at if body.period else latest.starts_at,
        body.period.ends_at if body.period else latest.ends_at,
        body.extras,
    )
    terms = OfferTerms(
        booking_id=booking_id,
        revision=previous_revision + 1,
        agreement_version=current.current_version,
        binding_revision=binding.revision,
        quote=quote,
        reason=body.reason,
    )
    digest = fingerprint("rental.customer_change.v1", terms)
    offer = Offer(
        booking_id=terms.booking_id,
        revision=terms.revision,
        agreement_version=terms.agreement_version,
        binding_revision=terms.binding_revision,
        quote=terms.quote,
        reason=terms.reason,
        review_hash=digest,
    )
    async with module_writes(RENTAL_MODULE):
        await conn.execute(
            "insert into gba.rental_customer_change_offers "
            "(tenant_id, booking_id, revision, agreement_id, agreement_version, binding_revision, "
            "company_id, quote, reason, review_hash, created_by) "
            "values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
            (
                business,
                booking_id,
                offer.revision,
                current.agreement_id,
                offer.agreement_version,
                offer.binding_revision,
                binding.company_id,
                Jsonb(quote.model_dump(mode="json")),
                offer.reason,
                offer.review_hash,
                user_id,
            ),
        )
    await idempotency.complete(conn, scope, 200, offer.model_dump(mode="json"))
    return offer


async def _allowed_offer(
    conn: RuntimeConnection, booking_id: UUID, revision: int, binding: CustomerCompanyView
) -> Offer:
    offer = await _find_offer(conn, booking_id, revision)
    if offer is None or offer.binding_revision != binding.revision:
        raise NotFoundError("Rental change offer not found")
    return offer


async def _accepted(
    conn: RuntimeConnection, offer: Offer, delegation: DelegationScope
) -> ChangeReceipt | None:
    row = await (
        await conn.execute(
            "select a.id, v.version, v.accepted_at from gba.rental_agreements a "
            "join gba.rental_agreement_versions v on (v.tenant_id, v.agreement_id) = "
            "(a.tenant_id, a.id) where a.booking_id = %s and v.customer_change_offer_revision = %s "
            "and v.customer_company_id = %s and v.customer_grant_id = %s "
            "and v.customer_binding_revision = %s and v.customer_review_hash = %s",
            (
                offer.booking_id,
                offer.revision,
                delegation.servicer_business_id,
                delegation.grant_id,
                offer.binding_revision,
                offer.review_hash,
            ),
        )
    ).fetchone()
    if row is None:
        return None
    return ChangeReceipt(
        booking_id=offer.booking_id,
        agreement_id=row[0],
        revision=offer.revision,
        agreement_version=row[1],
        review_hash=offer.review_hash,
        accepted_at=row[2].astimezone(UTC),
    )


async def _current_agreement(conn: RuntimeConnection, offer: Offer) -> agreements.AgreementView:
    current = await _open_agreement(conn, offer.booking_id)
    latest_offer = await _find_offer(conn, offer.booking_id)
    if (
        latest_offer is None
        or latest_offer.revision != offer.revision
        or current.current_version != offer.agreement_version
    ):
        raise RentalProposalStaleError("Review the latest rental change before accepting it")
    return current


async def read_for_customer(
    conn: RuntimeConnection,
    business: UUID,
    booking_id: UUID,
    revision: int,
    delegation: DelegationScope,
) -> OfferForCustomer | ChangeReceipt:
    binding = await authorized_binding(conn, business, booking_id, delegation)
    offer = await _allowed_offer(conn, booking_id, revision, binding)
    receipt = await _accepted(conn, offer, delegation)
    if receipt is not None:
        return receipt
    await _current_agreement(conn, offer)
    row = await (
        await conn.execute(
            "select l.timezone from gba.rental_bookings b join gba.locations l "
            "on (l.tenant_id, l.id) = (b.tenant_id, b.pickup_location_id) where b.id = %s",
            (booking_id,),
        )
    ).fetchone()
    if row is None:
        raise NotFoundError("Pickup location not found")
    card = await load_card(conn, offer.quote.rate_card_id)
    if card is None:
        raise NotFoundError("Rate card not found", rate_card_id=str(offer.quote.rate_card_id))
    chosen = {line.code for line in offer.quote.extras}
    return OfferForCustomer.model_validate(
        {
            **offer.model_dump(),
            "pickup_timezone": row[0],
            "extra_names": {
                extra.code: extra.name for extra in card.extras if extra.code in chosen
            },
        }
    )


async def accept(
    conn: RuntimeConnection,
    business: UUID,
    booking_id: UUID,
    revision: int,
    delegation: DelegationScope,
    *,
    user_id: UUID,
    actor: str,
    key: str,
    body: ChangeAnswerInput,
) -> ChangeReceipt:
    binding = await authorized_binding(conn, business, booking_id, delegation)
    offer = await _allowed_offer(conn, booking_id, revision, binding)
    scope = IdempotencyScope(business, actor, "rental.accept_customer_change", key)
    request = fingerprint(f"{booking_id}:{revision}:{delegation.grant_id}", body)
    stored = await idempotency.claim(conn, scope, request)
    if stored is not None:
        if stored.request_hash != request:
            raise IdempotencyKeyReusedError("Key was used for another request")
        return ChangeReceipt.model_validate(stored.body)
    if body.review_hash != offer.review_hash:
        raise RentalProposalStaleError("Review the current offer before accepting it")
    current = await _current_agreement(conn, offer)
    latest = current.versions[-1]
    card = await load_card(conn, latest.rate_card_id)
    if card is None:
        raise NotFoundError("Rate card not found", rate_card_id=str(latest.rate_card_id))
    quote = priced(
        card,
        offer.quote.starts_at,
        offer.quote.ends_at,
        [QuoteExtraInput(code=item.code, quantity=item.quantity) for item in offer.quote.extras],
    )
    if quote != offer.quote:
        raise RentalProposalStaleError("The price of the proposed rental terms changed")
    row = await (await conn.execute("select now()")).fetchone()
    if row is None:
        raise RuntimeError("PostgreSQL did not return the transaction time")
    accepted_at: datetime = row[0].astimezone(UTC)
    proof = agreements.PlatformAcceptance(
        accepted_by=body.signatory,
        accepted_at=accepted_at,
        company_id=delegation.servicer_business_id,
        grant_id=delegation.grant_id,
        binding_revision=offer.binding_revision,
        review_hash=offer.review_hash,
        offer_revision=offer.revision,
    )
    try:
        if (quote.starts_at, quote.ends_at) == (latest.starts_at, latest.ends_at):
            await agreements.record_terms_change(
                conn, business, current, card, quote, proof, offer.reason, user_id
            )
        else:
            await extensions.record_period_change(
                conn, business, booking_id, current, card, quote, proof, offer.reason, user_id
            )
    except CheckViolation as exc:
        if exc.diag.constraint_name == "rental_agreement_customer_scope":
            raise PermissionDeniedError("Customer grant does not authorize this booking") from exc
        if exc.diag.constraint_name == "rental_agreement_change_offer_scope":
            raise RentalProposalStaleError(
                "Review the latest rental change before accepting it"
            ) from exc
        raise
    receipt = ChangeReceipt(
        booking_id=booking_id,
        agreement_id=current.agreement_id,
        revision=offer.revision,
        agreement_version=current.current_version + 1,
        review_hash=offer.review_hash,
        accepted_at=accepted_at,
    )
    await idempotency.complete(conn, scope, 200, receipt.model_dump(mode="json"))
    return receipt
