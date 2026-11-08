"""R6b (package R, RENT-01): overdue time and meter excess of a rental booking, derived on read.

docs/plan/PACKAGE_R6B_DESIGN_2026-11-07.md. The latest agreement version (its period, its whole
rental days and its rate card's meter allowance and excess rate) and the R6a inspections give the
state, the overdue time and the meter excess. Nothing is stored and nothing is charged; R7 settles.
"""

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel

from gorgona_booking.business.rental_bookings import load_booking
from gorgona_booking.db.pool import RuntimeConnection
from gorgona_booking.errors import NotFoundError

State = Literal["not_handed_over", "out", "returned"]


class UsageFigures(BaseModel):
    state: State
    period_end: datetime
    rental_days: int
    as_of: datetime
    overdue_seconds: int
    overdue_hours: int
    distance: int | None
    allowance: int | None
    excess: int | None
    excess_amount: int | None


class UsageView(UsageFigures):
    booking_id: UUID
    currency: str


def derive_usage(
    *,
    period_end: datetime,
    rental_days: int,
    meter_kind: str,
    allowance_per_day: int | None,
    excess_rate: int | None,
    handed_at: datetime | None,
    handover_meter: int | None,
    returned_at: datetime | None,
    return_meter: int | None,
    as_of: datetime,
) -> UsageFigures:
    """Decisions 2-4: the state, the overdue time to the return (or the read) and the meter
    excess."""
    if handed_at is None:
        state: State = "not_handed_over"
        end = None
    elif returned_at is None:
        state, end = "out", as_of
    else:
        state, end = "returned", returned_at
    seconds = 0 if end is None else max(0, int((end - period_end).total_seconds()))
    metered = meter_kind != "none"
    allowance = (
        allowance_per_day * rental_days if metered and allowance_per_day is not None else None
    )
    distance = (
        return_meter - handover_meter
        if metered and return_meter is not None and handover_meter is not None
        else None
    )
    excess = None if distance is None or allowance is None else max(0, distance - allowance)
    return UsageFigures(
        state=state,
        period_end=period_end,
        rental_days=rental_days,
        as_of=as_of,
        overdue_seconds=seconds,
        overdue_hours=-(-seconds // 3600),
        distance=distance,
        allowance=allowance,
        excess=excess,
        excess_amount=None if excess is None or excess_rate is None else excess * excess_rate,
    )


async def load_usage(conn: RuntimeConnection, booking_id: UUID) -> UsageView:
    """Decisions 1 and 5: read the frozen terms and the inspections; not found outside the scope."""
    if await load_booking(conn, booking_id) is None:
        raise NotFoundError("Booking not found", booking_id=str(booking_id))
    terms = await (
        await conn.execute(
            "select v.ends_at, v.rental_days, c.meter_kind, r.meter_allowance_per_day, "
            "r.excess_rate, r.currency, now() from gba.rental_agreements a "
            "join gba.rental_agreement_versions v on v.tenant_id = a.tenant_id "
            "and v.agreement_id = a.id "
            "join gba.rental_rate_cards r on r.tenant_id = v.tenant_id and r.id = v.rate_card_id "
            "join gba.rental_classes c on c.tenant_id = r.tenant_id and c.id = r.class_id "
            "where a.booking_id = %s order by v.version desc limit 1",
            (booking_id,),
        )
    ).fetchone()
    if terms is None:
        raise NotFoundError("Agreement not found", booking_id=str(booking_id))
    seen = {
        row[0]: (row[1], row[2])
        for row in await (
            await conn.execute(
                "select kind, inspected_at, meter from gba.rental_inspections "
                "where booking_id = %s",
                (booking_id,),
            )
        ).fetchall()
    }
    handover = seen.get("handover", (None, None))
    returned = seen.get("return", (None, None))
    figures = derive_usage(
        period_end=terms[0],
        rental_days=terms[1],
        meter_kind=terms[2],
        allowance_per_day=terms[3],
        excess_rate=terms[4],
        handed_at=handover[0],
        handover_meter=handover[1],
        returned_at=returned[0],
        return_meter=returned[1],
        as_of=terms[6],
    )
    return UsageView(booking_id=booking_id, currency=terms[5], **figures.model_dump())
