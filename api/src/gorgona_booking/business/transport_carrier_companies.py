"""N4: a carrier on the platform answers in its own company (ADR-0017; package N).

docs/plan/PACKAGE_N4_DESIGN_2026-10-28.md: the broker links a carrier counterparty to that
company in insert-only versions; the company's delegates answer the tenders addressed to the
carrier and record stop events only on the legs tendered to it and accepted.
"""

from datetime import datetime
from typing import Literal
from uuid import UUID

from psycopg.errors import CheckViolation, ForeignKeyViolation
from pydantic import BaseModel, ConfigDict, Field

from gorgona_booking.booking import idempotency
from gorgona_booking.booking.idempotency import IdempotencyScope
from gorgona_booking.booking.models import IdempotencyKeyReusedError
from gorgona_booking.business import transport_brokerage as brokerage
from gorgona_booking.business.module_gate import TRANSPORT_MODULE, module_writes
from gorgona_booking.business.transport import require_transport
from gorgona_booking.db.pool import RuntimeConnection
from gorgona_booking.errors import ConflictError, DomainError, InvalidReferenceError
from gorgona_booking.tenancy.authorization import PermissionDeniedError


class TransportCarrierCompanyConflictError(ConflictError):
    code = "TRANSPORT_CARRIER_COMPANY_CONFLICT"


class TransportCarrierCompanyInvalidError(DomainError):
    code = "TRANSPORT_CARRIER_COMPANY_INVALID"


class LinkInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal[1]
    expected_revision: int = Field(ge=0, le=2_147_483_646)
    carrier_business_id: UUID | None


class LinkVersion(BaseModel):
    revision: int
    carrier_business_id: UUID | None
    created_at: datetime


class LinkView(BaseModel):
    counterparty_id: UUID
    revision: int
    carrier_business_id: UUID | None
    versions: list[LinkVersion]


async def load_link(conn: RuntimeConnection, counterparty: UUID) -> LinkView | None:
    """The carrier's company links, oldest first; None for no such carrier."""
    if not await brokerage._counterparty_exists(conn, counterparty):
        return None
    rows = await (
        await conn.execute(
            "select revision, carrier_business_id, created_at "
            "from gba.transport_carrier_companies where counterparty_id = %s order by revision",
            (counterparty,),
        )
    ).fetchall()
    versions = [LinkVersion(revision=r[0], carrier_business_id=r[1], created_at=r[2]) for r in rows]
    last = versions[-1] if versions else None
    return LinkView(
        counterparty_id=counterparty,
        revision=last.revision if last else 0,
        carrier_business_id=last.carrier_business_id if last else None,
        versions=versions,
    )


async def save_link(
    conn: RuntimeConnection,
    business: UUID,
    counterparty: UUID,
    *,
    user_id: UUID,
    actor: str,
    key: str,
    body: LinkInput,
) -> LinkView | None:
    """A new version of the carrier's company link; None for no such carrier."""
    await require_transport(conn, business)
    scope = IdempotencyScope(business, actor, "transport.carrier_company", key)
    fingerprint = brokerage._fingerprint(counterparty, body)
    stored = await idempotency.claim(conn, scope, fingerprint)
    if stored is not None:
        if stored.request_hash != fingerprint:
            raise IdempotencyKeyReusedError("Key was used for another request")
        return await load_link(conn, counterparty)
    view = await load_link(conn, counterparty)
    if view is None:
        return None
    if body.carrier_business_id == business:
        raise TransportCarrierCompanyInvalidError("A carrier is another company than the broker")
    if body.expected_revision != view.revision:
        raise TransportCarrierCompanyConflictError(
            "The carrier's company changed meanwhile",
            expected=body.expected_revision,
            current=view.revision,
        )
    try:
        async with module_writes(TRANSPORT_MODULE), conn.transaction():
            await conn.execute(
                "insert into gba.transport_carrier_companies (tenant_id, counterparty_id, "
                "revision, carrier_business_id, created_by) values (%s, %s, %s, %s, %s)",
                (business, counterparty, view.revision + 1, body.carrier_business_id, user_id),
            )
    except ForeignKeyViolation as exc:
        raise InvalidReferenceError("The carrier's company is not on the platform") from exc
    except CheckViolation as exc:
        if exc.diag.constraint_name == "transport_carrier_companies_own_check":
            raise TransportCarrierCompanyInvalidError(
                "A carrier is another company than the broker"
            ) from exc
        if exc.diag.constraint_name in (
            "transport_carrier_companies_revision_check",
            "transport_carrier_companies_business_check",
        ):
            raise TransportCarrierCompanyConflictError(
                str(exc.diag.message_primary or "The link is refused")
            ) from exc
        raise
    view = await load_link(conn, counterparty)
    await idempotency.complete(conn, scope, 200, {"counterparty_id": str(counterparty)})
    return view


async def linked_carrier(conn: RuntimeConnection, servicer: UUID) -> UUID | None:
    """The carrier counterparty the servicing company is linked to now, if any."""
    row = await (
        await conn.execute(
            "select counterparty_id from (select distinct on (counterparty_id) counterparty_id, "
            "carrier_business_id from gba.transport_carrier_companies "
            "order by counterparty_id, revision desc) latest where carrier_business_id = %s",
            (servicer,),
        )
    ).fetchone()
    return None if row is None else row[0]


async def require_carrier(conn: RuntimeConnection, counterparty: UUID, servicer: UUID) -> None:
    """Refuse a company that is not now linked to this carrier."""
    if await linked_carrier(conn, servicer) != counterparty:
        raise PermissionDeniedError("Your company answers only the tenders addressed to it")


async def tendered_legs(conn: RuntimeConnection, trip: UUID, counterparty: UUID) -> set[int]:
    """The legs of the trip tendered to the carrier and accepted, not withdrawn."""
    rows = await (
        await conn.execute(
            "select distinct unnest(t.legs) from gba.transport_tenders t "
            "where t.trip_id = %s and t.counterparty_id = %s "
            "and exists (select 1 from gba.transport_tender_answers a "
            "where a.tender_id = t.id and a.kind = 'accepted') "
            "and not exists (select 1 from gba.transport_tender_answers a "
            "where a.tender_id = t.id and a.kind = 'withdrawn')",
            (trip, counterparty),
        )
    ).fetchall()
    return {int(row[0]) for row in rows}
