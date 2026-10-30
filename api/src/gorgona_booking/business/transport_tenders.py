"""N2: tenders of trip legs to other carriers (package N).

Design docs/plan/PACKAGE_N2_DESIGN_2026-10-27.md. A tender is an insert-only offer of some legs of a
trip to one carrier for a carrier rate; answers are insert-only facts with a source. The state is
derived, never stored. Offering and accepting need an eligible broker and carrier on the date of the
offer or acceptance in the time zone of the trip's first stop; a leg has at most one accepted
tender, kept by the trip-tender lock and the answer trigger of migration 0082.
"""

from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any, Literal, Self
from uuid import UUID
from zoneinfo import ZoneInfo

from psycopg.errors import CheckViolation, ForeignKeyViolation, UniqueViolation
from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator

from gorgona_booking.booking import idempotency
from gorgona_booking.booking.idempotency import IdempotencyScope
from gorgona_booking.booking.models import IdempotencyKeyReusedError
from gorgona_booking.business import transport_brokerage as brokerage
from gorgona_booking.business import transport_carrier_companies as carriers
from gorgona_booking.business.module_gate import TRANSPORT_MODULE, module_writes
from gorgona_booking.business.transport import require_transport
from gorgona_booking.business.transport_money import (
    _AMOUNT,
    TransportAlreadyAccruedError,
    _exact,
    _text,
    _units,
)
from gorgona_booking.db.pool import RuntimeConnection
from gorgona_booking.errors import ConflictError, DomainError, InvalidReferenceError, NotFoundError


class TransportTenderConflictError(ConflictError):
    code = "TRANSPORT_TENDER_CONFLICT"


class TransportTenderClosedError(ConflictError):
    code = "TRANSPORT_TENDER_CLOSED"


class TransportLegTenderedError(ConflictError):
    code = "TRANSPORT_LEG_TENDERED"


class TransportBrokerNotEligibleError(ConflictError):
    code = "TRANSPORT_BROKER_NOT_ELIGIBLE"


class TransportCarrierNotEligibleError(ConflictError):
    code = "TRANSPORT_CARRIER_NOT_ELIGIBLE"


class TransportTenderTimeError(DomainError):
    code = "TRANSPORT_TENDER_TIME"


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class TenderInput(_Strict):
    schema_version: Literal[1]
    trip_id: UUID
    legs: list[int] = Field(min_length=1, max_length=100)
    counterparty_id: UUID
    currency: str = Field(pattern=r"^[A-Z]{3}$")
    basis: Literal["fixed", "per_mile"]
    amount: str = Field(min_length=1, max_length=24, pattern=_AMOUNT)
    terms: str = Field(min_length=1, max_length=2000)
    offered_at: AwareDatetime
    expires_at: AwareDatetime

    @model_validator(mode="after")
    def _facts(self) -> Self:
        if len(set(self.legs)) != len(self.legs) or any(not 1 <= n <= 100 for n in self.legs):
            raise ValueError("legs are distinct positions of the trip")
        if Decimal(self.amount) <= 0:
            raise ValueError("an amount is greater than zero")
        if not self.terms.strip():
            raise ValueError("terms have visible text")
        if self.expires_at <= self.offered_at:
            raise ValueError("an offer expires after it is made")
        return self


class AnswerInput(_Strict):
    schema_version: Literal[1]
    kind: Literal["accepted", "declined", "withdrawn"]
    source: Literal["email", "phone", "load_board", "other"]
    occurred_at: AwareDatetime


class CarrierAnswerInput(_Strict):
    """N4: the carrier's own answer, given in its company through a grant.

    N8 (RN-05): it is recorded at the server's time; the carrier never states the time.
    """

    schema_version: Literal[1]
    kind: Literal["accepted", "declined"]


class AnswerView(BaseModel):
    kind: str
    source: str
    occurred_at: datetime


class TenderView(BaseModel):
    tender_id: UUID
    trip_id: UUID
    legs: list[int]
    counterparty_id: UUID
    currency: str
    basis: str
    amount: str
    terms: str
    offered_at: datetime
    expires_at: datetime
    state: Literal["offered", "accepted", "declined", "withdrawn", "expired"]
    answers: list[AnswerView]


class TenderListView(BaseModel):
    items: list[TenderView]


_TENDERS = (
    "select t.id, t.trip_id, t.legs, t.counterparty_id, t.currency, t.basis, t.amount, t.terms, "
    "t.offered_at, t.expires_at, c.minor_units from gba.transport_tenders t "
    "join gba.currencies c on c.code = t.currency "
)
_ANSWERS = (
    "select tender_id, kind, source, occurred_at from gba.transport_tender_answers "
    "where tender_id = any(%s) order by occurred_at, created_at"
)


def _state(answers: list[AnswerView], expires_at: datetime, now: datetime) -> Any:
    kinds = {a.kind for a in answers}
    for kind in ("withdrawn", "declined", "accepted"):
        if kind in kinds:
            return kind
    return "expired" if now > expires_at else "offered"


async def _views(conn: RuntimeConnection, where: str, args: tuple[Any, ...]) -> list[TenderView]:
    rows = await (await conn.execute(_TENDERS + where + " order by t.id", args)).fetchall()
    if not rows:
        return []
    answers: dict[UUID, list[AnswerView]] = {}
    for row in await (await conn.execute(_ANSWERS, ([r[0] for r in rows],))).fetchall():
        answers.setdefault(row[0], []).append(
            AnswerView(kind=row[1], source=row[2], occurred_at=row[3])
        )
    now = datetime.now(UTC)
    return [
        TenderView(
            tender_id=row[0],
            trip_id=row[1],
            legs=list(row[2]),
            counterparty_id=row[3],
            currency=row[4],
            basis=row[5],
            amount=_text(row[6], int(row[10])),
            terms=row[7],
            offered_at=row[8],
            expires_at=row[9],
            state=_state(answers.get(row[0], []), row[9], now),
            answers=answers.get(row[0], []),
        )
        for row in rows
    ]


async def load_tender(conn: RuntimeConnection, tender: UUID) -> TenderView | None:
    views = await _views(conn, "where t.id = %s", (tender,))
    return views[0] if views else None


async def _required(conn: RuntimeConnection, tender: UUID) -> TenderView:
    view = await load_tender(conn, tender)
    if view is None:
        raise NotFoundError("Tender not found", tender_id=str(tender))
    return view


async def list_tenders(conn: RuntimeConnection, trip: UUID) -> TenderListView | None:
    found = await (
        await conn.execute("select 1 from gba.transport_trips where id = %s", (trip,))
    ).fetchone()
    if found is None:
        return None
    return TenderListView(items=await _views(conn, "where t.trip_id = %s", (trip,)))


async def _lock(conn: RuntimeConnection, trip: UUID) -> None:
    await conn.execute(
        "select pg_catalog.pg_advisory_xact_lock("
        "pg_catalog.hashtextextended('gba:trip-tender:' || %s::text, 0))",
        (trip,),
    )


async def server_time(conn: RuntimeConnection) -> datetime:
    """N8 (RN-05): the time a platform answer is recorded, never stated by the carrier."""
    row = await (await conn.execute("select pg_catalog.statement_timestamp()")).fetchone()
    assert row is not None  # noqa: S101 - the function always returns a row
    when: datetime = row[0]
    return when


async def _not_accrued(conn: RuntimeConnection, tender: UUID) -> None:
    """N8 (RN-04): once paid, a tender is neither withdrawn nor repriced."""
    row = await (
        await conn.execute(
            "select 1 from gba.transport_tender_accruals where tender_id = %s", (tender,)
        )
    ).fetchone()
    if row is not None:
        raise TransportAlreadyAccruedError(
            "The carrier's pay is accrued; the tender keeps its terms", tender_id=str(tender)
        )


class TransportLegStartedError(ConflictError):
    code = "TRANSPORT_LEG_STARTED"


async def _local_date(conn: RuntimeConnection, trip: UUID, at: datetime) -> date:
    """The date of an instant in the time zone of the trip's first stop."""
    row = await (
        await conn.execute(
            "select time_zone from gba.transport_stops where trip_id = %s "
            "order by position limit 1",
            (trip,),
        )
    ).fetchone()
    if row is None:
        raise InvalidReferenceError("The trip has no stops", field="trip_id")
    return at.astimezone(ZoneInfo(row[0])).date()


async def _eligible(conn: RuntimeConnection, trip: UUID, carrier: UUID, at: datetime) -> None:
    on = await _local_date(conn, trip, at)
    broker = brokerage.authority_eligibility(await brokerage.load_authority(conn), on)
    if not broker.eligible:
        raise TransportBrokerNotEligibleError(
            "The business may not tender on this date", on=str(on), reasons=broker.reasons
        )
    profile = await brokerage.load_profile(conn, carrier)
    if profile is None:
        raise InvalidReferenceError("Unknown carrier", field="counterparty_id")
    checked = brokerage.carrier_eligibility(profile, on)
    if not checked.eligible:
        raise TransportCarrierNotEligibleError(
            "The carrier may not be tendered to on this date", on=str(on), reasons=checked.reasons
        )


def _same(view: TenderView, body: TenderInput) -> bool:
    return (
        view.trip_id == body.trip_id
        and view.legs == body.legs
        and view.counterparty_id == body.counterparty_id
        and view.currency == body.currency
        and view.basis == body.basis
        and Decimal(view.amount) == Decimal(body.amount)
        and view.terms == body.terms.strip()
        and view.offered_at == body.offered_at
        and view.expires_at == body.expires_at
    )


async def save_tender(
    conn: RuntimeConnection,
    business: UUID,
    tender: UUID,
    *,
    user_id: UUID,
    actor: str,
    key: str,
    body: TenderInput,
) -> TenderView:
    """Offer some legs of a trip to one carrier; a repeat with the same body is the same tender."""
    await require_transport(conn, business)
    scope = IdempotencyScope(business, actor, "transport.tender", key)
    fingerprint = brokerage._fingerprint(tender, body)
    stored = await idempotency.claim(conn, scope, fingerprint)
    if stored is not None:
        if stored.request_hash != fingerprint:
            raise IdempotencyKeyReusedError("Key was used for another request")
        return await _required(conn, tender)
    existing = await load_tender(conn, tender)
    if existing is not None:
        if not _same(existing, body):
            raise TransportTenderConflictError("Another tender has this id", tender_id=str(tender))
        await idempotency.complete(conn, scope, 200, {"tender_id": str(tender)})
        return existing
    trip = await (
        await conn.execute("select status from gba.transport_trips where id = %s", (body.trip_id,))
    ).fetchone()
    if trip is None:
        raise NotFoundError("Trip not found", trip_id=str(body.trip_id))
    if trip[0] != "planned":
        # N8 (RN-09): a leg the trip already runs is never tendered and paid twice.
        raise TransportLegStartedError("A started trip is not tendered", trip_id=str(body.trip_id))
    legs = await (
        await conn.execute(
            "select position from gba.transport_legs where trip_id = %s "
            "and position = any(%s::smallint[])",
            (body.trip_id, body.legs),
        )
    ).fetchall()
    if len(legs) != len(body.legs):
        raise InvalidReferenceError("A leg is not part of the trip", field="legs")
    units = await _units(conn, body.currency)
    if body.basis == "fixed":
        _exact(body.amount, units)
    await _eligible(conn, body.trip_id, body.counterparty_id, body.offered_at)
    try:
        async with module_writes(TRANSPORT_MODULE), conn.transaction():
            await _lock(conn, body.trip_id)
            await conn.execute(
                "insert into gba.transport_tenders (tenant_id, id, trip_id, legs, counterparty_id, "
                "currency, basis, amount, terms, offered_at, expires_at, created_by) "
                "values (%s, %s, %s, %s::smallint[], %s, %s, %s, %s, %s, %s, %s, %s)",
                (
                    business,
                    tender,
                    body.trip_id,
                    body.legs,
                    body.counterparty_id,
                    body.currency,
                    body.basis,
                    Decimal(body.amount),
                    body.terms.strip(),
                    body.offered_at,
                    body.expires_at,
                    user_id,
                ),
            )
    except ForeignKeyViolation as exc:
        raise InvalidReferenceError("Unknown trip or carrier", field="trip_id") from exc
    except UniqueViolation:
        existing = await load_tender(conn, tender)
        if existing is None or not _same(existing, body):
            raise TransportTenderConflictError(
                "Another tender has this id", tender_id=str(tender)
            ) from None
        await idempotency.complete(conn, scope, 200, {"tender_id": str(tender)})
        return existing
    view = await _required(conn, tender)
    await idempotency.complete(conn, scope, 200, {"tender_id": str(tender)})
    return view


_ANSWER_ERRORS: dict[str, type[DomainError]] = {
    "transport_tender_answers_state_check": TransportTenderClosedError,
    "transport_tenders_accrued_check": TransportAlreadyAccruedError,
    "transport_tender_answers_leg_check": TransportLegTenderedError,
    "transport_tender_answers_time_check": TransportTenderTimeError,
}


async def answer_tender(
    conn: RuntimeConnection,
    business: UUID,
    tender: UUID,
    *,
    user_id: UUID,
    actor: str,
    key: str,
    body: AnswerInput | CarrierAnswerInput,
    servicer: UUID | None = None,
) -> TenderView | None:
    """Record the carrier's answer or the broker's withdrawal; None for no tender.

    N4: with `servicer`, the carrier's own company answers through its grant (source platform).
    """
    await require_transport(conn, business)
    action = "transport.tender_answer" if servicer is None else "transport.tender_carrier_answer"
    scope = IdempotencyScope(business, actor, action, key)
    source = "platform" if isinstance(body, CarrierAnswerInput) else body.source
    fingerprint = brokerage._fingerprint(tender, body)
    stored = await idempotency.claim(conn, scope, fingerprint)
    if stored is not None:
        if stored.request_hash != fingerprint:
            raise IdempotencyKeyReusedError("Key was used for another request")
        return await load_tender(conn, tender)
    view = await load_tender(conn, tender)
    if view is None:
        return None
    if servicer is not None:
        await carriers.require_carrier(conn, view.counterparty_id, servicer)
    try:
        async with module_writes(TRANSPORT_MODULE), conn.transaction():
            await _lock(conn, view.trip_id)
            view = await _required(conn, tender)
            occurred = (
                body.occurred_at if isinstance(body, AnswerInput) else await server_time(conn)
            )
            same = [a for a in view.answers if a.kind == body.kind]
            if same:
                # A carrier's repeat is the same answer whatever the clock now reads.
                if same[0].source != source or (
                    isinstance(body, AnswerInput) and same[0].occurred_at != occurred
                ):
                    raise TransportTenderClosedError("The tender already has this answer")
            else:
                if body.kind == "withdrawn":
                    await _not_accrued(conn, tender)
                if body.kind == "accepted" and occurred >= view.offered_at:
                    await _eligible(conn, view.trip_id, view.counterparty_id, occurred)
                await conn.execute(
                    "insert into gba.transport_tender_answers (tenant_id, tender_id, kind, "
                    "source, servicer_business_id, occurred_at, created_by) "
                    "values (%s, %s, %s, %s, %s, %s, %s)",
                    (business, tender, body.kind, source, servicer, occurred, user_id),
                )
                if body.kind == "accepted":
                    # N3: the acceptance agrees version 1 of the rate confirmation.
                    await conn.execute(
                        "insert into gba.transport_rate_confirmations (tenant_id, tender_id, "
                        "revision, basis, amount, terms, proposed_at, created_by) "
                        "select tenant_id, id, 1, basis, amount, terms, %s, %s "
                        "from gba.transport_tenders where id = %s",
                        (occurred, user_id, tender),
                    )
                    await conn.execute(
                        "insert into gba.transport_rate_confirmation_answers (tenant_id, "
                        "tender_id, revision, kind, source, servicer_business_id, occurred_at, "
                        "created_by) values (%s, %s, 1, 'agreed', %s, %s, %s, %s)",
                        (business, tender, source, servicer, occurred, user_id),
                    )
    except CheckViolation as exc:
        error = _ANSWER_ERRORS.get(exc.diag.constraint_name or "")
        if error is None:
            raise
        raise error(str(exc.diag.message_primary or "The answer is refused")) from exc
    view = await load_tender(conn, tender)
    await idempotency.complete(conn, scope, 200, {"tender_id": str(tender)})
    return view
