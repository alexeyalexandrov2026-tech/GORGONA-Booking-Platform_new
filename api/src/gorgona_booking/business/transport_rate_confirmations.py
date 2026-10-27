"""N3: rate confirmations of accepted tenders (package N).

Design docs/plan/PACKAGE_N3_DESIGN_2026-10-27.md. Version 1 is written by the acceptance with the
tender's rate and terms. A change is a new version the broker proposes; it is in force only once the
carrier's agreement is recorded, and a declined proposal leaves the previous version in force.
Nothing is edited; migration 0083 keeps the order of versions and answers.
"""

from datetime import datetime
from decimal import Decimal
from typing import Literal, Self
from uuid import UUID

from psycopg.errors import CheckViolation, ForeignKeyViolation, UniqueViolation
from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator

from gorgona_booking.booking import idempotency
from gorgona_booking.booking.idempotency import IdempotencyScope
from gorgona_booking.booking.models import IdempotencyKeyReusedError
from gorgona_booking.business import transport_brokerage as brokerage
from gorgona_booking.business.module_gate import TRANSPORT_MODULE, module_writes
from gorgona_booking.business.transport import require_transport
from gorgona_booking.business.transport_money import _AMOUNT, _exact, _text, _units
from gorgona_booking.business.transport_tenders import (
    TransportTenderClosedError,
    TransportTenderTimeError,
    load_tender,
)
from gorgona_booking.db.pool import RuntimeConnection
from gorgona_booking.errors import ConflictError, DomainError, InvalidReferenceError


class TransportRateConfirmationConflictError(ConflictError):
    code = "TRANSPORT_RATE_CONFIRMATION_CONFLICT"


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class ProposalInput(_Strict):
    schema_version: Literal[1]
    expected_revision: int = Field(ge=0, le=2_147_483_647)
    basis: Literal["fixed", "per_mile"]
    amount: str = Field(min_length=1, max_length=24, pattern=_AMOUNT)
    terms: str = Field(min_length=1, max_length=2000)
    document_id: UUID | None = None
    proposed_at: AwareDatetime

    @model_validator(mode="after")
    def _facts(self) -> Self:
        if Decimal(self.amount) <= 0:
            raise ValueError("an amount is greater than zero")
        if not self.terms.strip():
            raise ValueError("terms have visible text")
        return self


class ConfirmationAnswerInput(_Strict):
    schema_version: Literal[1]
    kind: Literal["agreed", "declined"]
    source: Literal["email", "phone", "load_board", "other"]
    occurred_at: AwareDatetime


class ConfirmationAnswerView(BaseModel):
    kind: str
    source: str
    occurred_at: datetime


class ConfirmationVersion(BaseModel):
    revision: int
    basis: str
    amount: str
    terms: str
    document_id: UUID | None
    proposed_at: datetime
    state: Literal["proposed", "agreed", "declined"]
    answer: ConfirmationAnswerView | None


class RateConfirmationView(BaseModel):
    tender_id: UUID
    currency: str
    in_force: ConfirmationVersion | None
    versions: list[ConfirmationVersion]


_VERSIONS = (
    "select c.revision, c.basis, c.amount, c.terms, c.document_id, c.proposed_at, x.kind, "
    "x.source, "
    "x.occurred_at, t.currency, u.minor_units from gba.transport_rate_confirmations c "
    "join gba.transport_tenders t on t.tenant_id = c.tenant_id and t.id = c.tender_id "
    "join gba.currencies u on u.code = t.currency "
    "left join gba.transport_rate_confirmation_answers x on x.tenant_id = c.tenant_id "
    "and x.tender_id = c.tender_id and x.revision = c.revision "
    "where c.tender_id = %s order by c.revision"
)


async def load_confirmation(conn: RuntimeConnection, tender: UUID) -> RateConfirmationView | None:
    rows = await (await conn.execute(_VERSIONS, (tender,))).fetchall()
    if not rows:
        return None
    versions = [
        ConfirmationVersion(
            revision=row[0],
            basis=row[1],
            amount=_text(row[2], int(row[10])),
            terms=row[3],
            document_id=row[4],
            proposed_at=row[5],
            state="proposed" if row[6] is None else row[6],
            answer=None
            if row[6] is None
            else ConfirmationAnswerView(kind=row[6], source=row[7], occurred_at=row[8]),
        )
        for row in rows
    ]
    agreed = [v for v in versions if v.state == "agreed"]
    return RateConfirmationView(
        tender_id=tender,
        currency=rows[0][9],
        in_force=agreed[-1] if agreed else None,
        versions=versions,
    )


_ERRORS: dict[str, type[DomainError]] = {
    "transport_rate_confirmations_state_check": TransportTenderClosedError,
    "transport_rate_confirmations_revision_check": TransportRateConfirmationConflictError,
    "transport_rate_confirmations_time_check": TransportTenderTimeError,
    "transport_rate_confirmation_answers_revision_check": TransportRateConfirmationConflictError,
    "transport_rate_confirmation_answers_time_check": TransportTenderTimeError,
}


def _refused(exc: CheckViolation) -> DomainError | None:
    error = _ERRORS.get(exc.diag.constraint_name or "")
    return None if error is None else error(str(exc.diag.message_primary or "Refused"))


async def propose(
    conn: RuntimeConnection,
    business: UUID,
    tender: UUID,
    *,
    user_id: UUID,
    actor: str,
    key: str,
    body: ProposalInput,
) -> RateConfirmationView | None:
    """A new version of the rate confirmation; None for no tender."""
    await require_transport(conn, business)
    scope = IdempotencyScope(business, actor, "transport.rate_confirmation", key)
    fingerprint = brokerage._fingerprint(tender, body)
    stored = await idempotency.claim(conn, scope, fingerprint)
    if stored is not None:
        if stored.request_hash != fingerprint:
            raise IdempotencyKeyReusedError("Key was used for another request")
        return await load_confirmation(conn, tender)
    offered = await load_tender(conn, tender)
    if offered is None:
        return None
    if offered.state != "accepted":
        raise TransportTenderClosedError("Only an accepted tender has rate confirmations")
    view = await load_confirmation(conn, tender)
    current = view.versions[-1].revision if view else 0
    if body.expected_revision != current:
        raise TransportRateConfirmationConflictError(
            "The rate confirmation changed meanwhile",
            expected=body.expected_revision,
            current=current,
        )
    if view is not None and view.versions[-1].state == "proposed":
        raise TransportRateConfirmationConflictError("A proposal is waiting for the carrier")
    if body.basis == "fixed":
        _exact(body.amount, await _units(conn, offered.currency))
    try:
        async with module_writes(TRANSPORT_MODULE), conn.transaction():
            await conn.execute(
                "insert into gba.transport_rate_confirmations (tenant_id, tender_id, revision, "
                "basis, amount, terms, document_id, proposed_at, created_by) "
                "values (%s, %s, %s, %s, %s, %s, %s, %s, %s)",
                (
                    business,
                    tender,
                    current + 1,
                    body.basis,
                    Decimal(body.amount),
                    body.terms.strip(),
                    body.document_id,
                    body.proposed_at,
                    user_id,
                ),
            )
    except ForeignKeyViolation as exc:
        raise InvalidReferenceError("Unknown document", field="document_id") from exc
    except UniqueViolation as exc:
        raise TransportRateConfirmationConflictError(
            "The rate confirmation changed meanwhile"
        ) from exc
    except CheckViolation as exc:
        refused = _refused(exc)
        if refused is None:
            raise
        raise refused from exc
    view = await load_confirmation(conn, tender)
    await idempotency.complete(conn, scope, 200, {"revision": current + 1})
    return view


async def answer(
    conn: RuntimeConnection,
    business: UUID,
    tender: UUID,
    revision: int,
    *,
    user_id: UUID,
    actor: str,
    key: str,
    body: ConfirmationAnswerInput,
) -> RateConfirmationView | None:
    """The carrier's answer to one version; None for no such version."""
    await require_transport(conn, business)
    scope = IdempotencyScope(business, actor, "transport.rate_confirmation_answer", key)
    fingerprint = brokerage._fingerprint(f"{tender}/{revision}", body)
    stored = await idempotency.claim(conn, scope, fingerprint)
    if stored is not None:
        if stored.request_hash != fingerprint:
            raise IdempotencyKeyReusedError("Key was used for another request")
        return await load_confirmation(conn, tender)
    view = await load_confirmation(conn, tender)
    if view is None or not any(v.revision == revision for v in view.versions):
        return None
    try:
        async with module_writes(TRANSPORT_MODULE), conn.transaction():
            await conn.execute(
                "insert into gba.transport_rate_confirmation_answers (tenant_id, tender_id, "
                "revision, kind, source, occurred_at, created_by) "
                "values (%s, %s, %s, %s, %s, %s, %s)",
                (business, tender, revision, body.kind, body.source, body.occurred_at, user_id),
            )
    except UniqueViolation as exc:
        raise TransportRateConfirmationConflictError("This version is already answered") from exc
    except CheckViolation as exc:
        refused = _refused(exc)
        if refused is None:
            raise
        raise refused from exc
    view = await load_confirmation(conn, tender)
    await idempotency.complete(conn, scope, 200, {"revision": revision})
    return view
