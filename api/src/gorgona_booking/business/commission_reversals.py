"""L9b (package L): what a refund of a visit reverses of its commission.

Design docs/plan/PACKAGE_L9_DESIGN_2026-10-23.md decisions 81-82. A refund is an issued, unvoided
FIN-03 credit note of the visit invoice that is not a prepaid redemption. Only service lines (with
their add-ons) change the commission; fees and tips do not.
"""

from typing import Any
from uuid import UUID

from gorgona_booking.business.financial_contracts import InvoiceDocumentView
from gorgona_booking.business.visit_billing import catalog_minor, load_visit_invoice
from gorgona_booking.db.pool import RuntimeConnection

# For each refund not yet reversed: the amount it reverses on each commission line.
Plan = list[tuple[UUID, dict[UUID, int]]]


def minor_of(text: str, units: int) -> int:
    whole, _, fraction = text.partition(".")
    scale: int = 10**units
    return int(whole) * scale + int(fraction.ljust(units, "0") or "0")


async def credits_of(
    conn: RuntimeConnection, book_id: UUID, obligation_id: UUID, *, refunds_only: bool
) -> list[UUID]:
    """Issued, unvoided credit notes of an obligation; refunds leave redemptions out."""
    rows = await (
        await conn.execute(
            "select d.id from gba.financial_documents d join lateral ("
            "select x.state, x.credited_obligation_id, x.voided_on "
            "from gba.financial_document_versions x where x.tenant_id = d.tenant_id "
            "and x.book_id = d.book_id and x.document_id = d.id order by x.revision desc limit 1"
            ") v on true where d.book_id = %s and d.kind = 'credit_note' "
            "and v.credited_obligation_id = %s and v.state = 'issued' and v.voided_on is null "
            "and (not %s or not exists (select 1 from gba.prepaid_redemptions r "
            "where r.book_id = d.book_id and r.credit_document_id = d.id)) order by d.id",
            (book_id, obligation_id, refunds_only),
        )
    ).fetchall()
    return [row[0] for row in rows]


async def credited_lines(
    conn: RuntimeConnection, book_id: UUID, documents: list[UUID]
) -> dict[UUID, int]:
    """What the credit notes take off each credited line, in minor units."""
    if not documents:
        return {}
    rows = await (
        await conn.execute(
            "select l.credited_line_id, sum(l.amount_minor) from gba.financial_document_lines l "
            "where l.book_id = %s and l.document_id = any(%s) and l.revision = ("
            "select max(x.revision) from gba.financial_document_versions x "
            "where x.tenant_id = l.tenant_id and x.book_id = l.book_id "
            "and x.document_id = l.document_id) group by l.credited_line_id",
            (book_id, documents),
        )
    ).fetchall()
    return {row[0]: int(row[1]) for row in rows}


async def reversal_plan(
    conn: RuntimeConnection,
    tenant_id: UUID,
    booking_id: UUID,
    book_id: UUID,
    accrual: InvoiceDocumentView,
) -> Plan:
    """For each refund not yet reversed, what it reverses on each commission line.

    The cumulative reversal of a line is the line times the refunded share of its service (the
    service line and its add-ons), half up; each refund takes what the cumulative target adds.
    """
    billed = await load_visit_invoice(conn, tenant_id, booking_id)
    if billed is None or billed.invoice.obligation_id is None:
        return []
    refunds = await credits_of(conn, book_id, billed.invoice.obligation_id, refunds_only=True)
    done = {
        row[0]
        for row in await (
            await conn.execute(
                "select refund_document_id from gba.visit_commission_reversals "
                "where booking_id = %s",
                (booking_id,),
            )
        ).fetchall()
    }
    pending = [document for document in refunds if document not in done]
    if not pending:
        return []
    row = await (
        await conn.execute("select quote from gba.bookings where id = %s", (booking_id,))
    ).fetchone()
    assert row is not None  # noqa: S101 - the commission names its booking
    quote: dict[str, Any] = row[0]
    units = billed.invoice.minor_units
    # Invoice line -> service of the quote, in the order the visit was billed (L8 decision 55).
    service_of: dict[UUID, int] = {}
    invoiced: dict[int, int] = {}
    names: list[str] = []
    lines = iter(billed.invoice.lines)
    for line in quote.get("lines") or []:
        if line.get("kind") == "variant":
            names.append(str(line["name"]))
        minor = catalog_minor(int(line["price_cents"]), units)
        if minor > 0 and names:
            service = len(names) - 1
            service_of[next(lines).line_id] = service
            invoiced[service] = invoiced.get(service, 0) + minor
    # Commission lines are named after their service, in quote order (L5 decision 29).
    commission_of: dict[UUID, tuple[int, int]] = {}
    service = 0
    for line in accrual.lines:
        while service < len(names) and line.description != f"Commission: {names[service]}":
            service += 1
        if service < len(names):
            commission_of[line.line_id] = (service, minor_of(line.amount, units))
            service += 1
    reduced: dict[UUID, int] = {}
    if accrual.obligation_id is not None:
        reductions = await credits_of(conn, book_id, accrual.obligation_id, refunds_only=False)
        reduced = await credited_lines(conn, book_id, reductions)
    already = {line: reduced.get(line, 0) for line in commission_of}
    plan: Plan = []
    counted = [document for document in refunds if document in done]
    for document in pending:
        counted.append(document)
        credited: dict[int, int] = {}
        for invoice_line, minor in (await credited_lines(conn, book_id, counted)).items():
            if invoice_line in service_of:
                group = service_of[invoice_line]
                credited[group] = credited.get(group, 0) + minor
        deltas: dict[UUID, int] = {}
        for line, (group, amount) in commission_of.items():
            whole = invoiced.get(group, 0)
            if whole <= 0:
                continue
            target = min(amount, (2 * amount * credited.get(group, 0) + whole) // (2 * whole))
            if target > already[line]:
                deltas[line] = target - already[line]
                already[line] = target
        plan.append((document, deltas))
    return plan
