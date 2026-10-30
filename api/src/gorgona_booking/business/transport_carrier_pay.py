"""N5: the carrier's pay per accepted tender and the margin per order (package N, ADR-0033).

docs/plan/PACKAGE_N5_DESIGN_2026-10-28.md: an accepted tender with closed legs accrues once as a
FIN-03 payable manual accrual to its carrier for the rate confirmation in force; the margin of an
order is derived from its invoice and its own tenders' accruals and is never stored.
"""

from decimal import Decimal
from uuid import UUID, uuid7

from psycopg.errors import UniqueViolation
from pydantic import BaseModel, Field

from gorgona_booking.booking import idempotency
from gorgona_booking.booking.idempotency import IdempotencyScope
from gorgona_booking.booking.models import IdempotencyKeyReusedError
from gorgona_booking.business import financial_documents, settlements
from gorgona_booking.business import transport_money as money
from gorgona_booking.business import transport_rate_confirmations as confirmations
from gorgona_booking.business import transport_tenders as tenders
from gorgona_booking.business.financial_contracts import (
    InvoiceDocumentView,
    InvoiceDraftInput,
    InvoiceLineInput,
)
from gorgona_booking.business.module_gate import TRANSPORT_MODULE, module_writes
from gorgona_booking.business.settlement_contracts import ObligationView
from gorgona_booking.business.transport import require_transport
from gorgona_booking.business.transport_tenders import TransportTenderClosedError, load_tender
from gorgona_booking.db.pool import RuntimeConnection
from gorgona_booking.errors import NotFoundError


class CarrierPayInput(money.AccrueInput):
    title: str = Field(default="Carrier pay", min_length=1, max_length=200)


class CarrierPayView(BaseModel):
    tender_id: UUID
    revision: int
    miles: str | None
    book_id: UUID
    document_id: UUID
    accrual: InvoiceDocumentView
    obligation: ObligationView | None


class MarginLine(BaseModel):
    tender_id: UUID
    amount: str


class MarginView(BaseModel):
    order_id: UUID
    currency: str | None
    revenue: str | None
    carrier_cost: str | None
    margin: str | None
    # N8 (RN-08): amounts in different currencies are never added together.
    currencies_differ: bool = False
    tenders: list[MarginLine]
    shared: list[MarginLine]


_OPEN_TENDERED = money._OPEN + "where l.trip_id = %s and l.position = any(%s)" + money._GROUP


async def load_pay(conn: RuntimeConnection, business: UUID, tender: UUID) -> CarrierPayView | None:
    row = await (
        await conn.execute(
            "select revision, miles, book_id, document_id from gba.transport_tender_accruals "
            "where tender_id = %s",
            (tender,),
        )
    ).fetchone()
    if row is None:
        return None
    accrual = await financial_documents.load_invoice(
        conn, business, row[2], row[3], kind="manual_accrual"
    )
    if accrual is None:
        raise NotFoundError("Accrual not found", document_id=str(row[3]))
    obligation = (
        await settlements.load_obligation(conn, business, row[2], accrual.obligation_id)
        if accrual.obligation_id is not None
        else None
    )
    return CarrierPayView(
        tender_id=tender,
        revision=row[0],
        miles=money._miles(row[1]),
        book_id=row[2],
        document_id=row[3],
        accrual=accrual,
        obligation=obligation,
    )


async def accrue(
    conn: RuntimeConnection,
    business: UUID,
    tender: UUID,
    *,
    user_id: UUID,
    actor: str,
    key: str,
    body: CarrierPayInput,
) -> CarrierPayView:
    """The tender's one FIN-03 payable accrual to its carrier, once its legs are closed."""
    await require_transport(conn, business)
    scope = IdempotencyScope(business, actor, "transport.carrier_pay", key)
    fingerprint = money._fingerprint(tender, body)
    stored = await idempotency.claim(conn, scope, fingerprint)
    if stored is not None:
        if stored.request_hash != fingerprint:
            raise IdempotencyKeyReusedError("Key was used for another request")
        replay = await load_pay(conn, business, tender)
        if replay is None:
            raise NotFoundError("Tender not found", tender_id=str(tender))
        return replay
    view = await load_tender(conn, tender)
    if view is None:
        raise NotFoundError("Tender not found", tender_id=str(tender))
    # N8 (RN-04): the accrual waits for any answer or new rate on the trip, then reads the
    # tender's answers again, so a withdrawal and the payable never pass each other.
    await tenders._lock(conn, view.trip_id)
    view = await load_tender(conn, tender)
    assert view is not None  # noqa: S101 - tenders are insert-only
    trip = await (
        await conn.execute(
            "select reference from gba.transport_trips where id = %s for update", (view.trip_id,)
        )
    ).fetchone()
    assert trip is not None  # noqa: S101 - a tender refers to its trip
    if await load_pay(conn, business, tender) is not None:
        raise money.TransportAlreadyAccruedError("This tender is already accrued")
    kinds = {answer.kind for answer in view.answers}
    if "accepted" not in kinds or "withdrawn" in kinds:
        raise TransportTenderClosedError("Only an accepted tender is paid")
    confirmation = await confirmations.load_confirmation(conn, tender)
    version = None if confirmation is None else confirmation.in_force
    if version is None:
        raise TransportTenderClosedError("The tender has no agreed rate")
    rows = await (
        await conn.execute(_OPEN_TENDERED, (list(money._CLOSING), view.trip_id, view.legs))
    ).fetchall()
    if len(rows) != len(view.legs) or any(int(row[0]) != 0 for row in rows):
        raise money.TransportTripNotClosedError("The tendered legs still have open quantities")
    units = await money._units(conn, view.currency)
    name = f"Carrier pay {trip[0]}"
    if version.basis == "per_mile":
        if body.miles is None:
            raise money.TransportMilesRequiredError("A per-mile rate needs the miles")
        amount = money._bounded(
            money._minor(Decimal(version.amount) * Decimal(body.miles), units), units
        )
        name += f" ({body.miles} mi at {version.amount})"
    else:
        amount = money._bounded(money._minor(Decimal(version.amount), units), units)
    document = uuid7()
    await financial_documents.save_draft(
        conn,
        business_id=business,
        book_id=body.book_id,
        document_id=document,
        user_id=user_id,
        actor=actor,
        key=key,
        body=InvoiceDraftInput(
            expected_revision=0,
            direction="payable",
            counterparty_id=view.counterparty_id,
            counterparty_revision=await money._party_revision(conn, view.counterparty_id),
            currency=view.currency,
            invoice_date=body.accrual_date,
            control_account_id=body.payable_account_id,
            title=body.title,
            number=body.number,
            lines=(
                InvoiceLineInput(
                    line_id=uuid7(),
                    counter_account_id=body.expense_account_id,
                    description=name,
                    amount=money._money(amount, units),
                ),
            ),
        ),
        kind="manual_accrual",
    )
    try:
        async with module_writes(TRANSPORT_MODULE), conn.transaction():
            await conn.execute(
                "insert into gba.transport_tender_accruals (tenant_id, tender_id, revision, "
                "miles, book_id, document_id, created_by) values (%s, %s, %s, %s, %s, %s, %s)",
                (
                    business,
                    tender,
                    version.revision,
                    Decimal(body.miles) if version.basis == "per_mile" and body.miles else None,
                    body.book_id,
                    document,
                    user_id,
                ),
            )
    except UniqueViolation as exc:
        raise money.TransportAlreadyAccruedError("This tender is already accrued") from exc
    accrued = await load_pay(conn, business, tender)
    assert accrued is not None  # noqa: S101 - linked above
    await idempotency.complete(conn, scope, 200, {"tender_id": str(tender)})
    return accrued


async def load_margin(conn: RuntimeConnection, business: UUID, order: UUID) -> MarginView | None:
    """Revenue less the accrued pay of the order's own tenders; a shared tender is listed only."""
    exists = await (
        await conn.execute("select 1 from gba.transport_orders where id = %s", (order,))
    ).fetchone()
    if exists is None:
        return None
    rows = await (
        await conn.execute(
            "select a.tender_id, a.book_id, a.document_id, bool_and(x.order_id = %s) "
            "from gba.transport_tender_accruals a "
            "join gba.transport_tenders t on t.tenant_id = a.tenant_id and t.id = a.tender_id "
            "join gba.transport_legs l on l.tenant_id = t.tenant_id and l.trip_id = t.trip_id "
            "and l.position = any(t.legs) "
            "join gba.transport_loads x on x.tenant_id = l.tenant_id and x.id = l.load_id "
            "group by a.tender_id, a.book_id, a.document_id "
            "having bool_or(x.order_id = %s) order by a.tender_id",
            (order, order),
        )
    ).fetchall()
    invoice = await money.load_order_invoice(conn, business, order)
    currencies: set[str] = set()
    units = 2
    if invoice is not None:
        currencies.add(invoice.invoice.currency)
        units = invoice.invoice.minor_units
    own: list[MarginLine] = []
    shared: list[MarginLine] = []
    cost = Decimal(0)
    for tender, book, document, whole in rows:
        accrual = await financial_documents.load_invoice(
            conn, business, book, document, kind="manual_accrual"
        )
        if accrual is None:
            raise NotFoundError("Accrual not found", document_id=str(document))
        if invoice is None and not currencies:
            units = accrual.minor_units
        currencies.add(accrual.currency)
        line = MarginLine(tender_id=tender, amount=accrual.total)
        if whole:
            own.append(line)
            cost += Decimal(accrual.total)
        else:
            shared.append(line)
    single = len(currencies) <= 1
    revenue = None if invoice is None else invoice.invoice.total
    return MarginView(
        order_id=order,
        currency=next(iter(currencies)) if single and currencies else None,
        revenue=revenue,
        carrier_cost=f"{cost:.{units}f}" if single else None,
        margin=(f"{Decimal(revenue) - cost:.{units}f}" if revenue is not None and single else None),
        tenders=own,
        shared=shared,
        currencies_differ=not single,
    )
