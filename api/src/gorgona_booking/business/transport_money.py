"""M7a: transport money through FIN-03 (package M, ADR-0033).

Design docs/plan/PACKAGE_M7A_DESIGN_2026-10-25.md. An order's agreed rate is kept as insert-only
versions; the order is invoiced once, as a FIN-03 receivable draft, when nothing is open. A trip's
pay components are registered once (one per recipient and role) and each accrues once as a FIN-03
payable manual accrual on a closed trip; FIN-03 settlements keep every payment within the open
balance.
"""

import hashlib
import json
from datetime import date, datetime
from decimal import ROUND_HALF_UP, Decimal
from typing import Any, Literal, Self
from uuid import UUID, uuid7

from psycopg.errors import CheckViolation, ForeignKeyViolation, UniqueViolation
from pydantic import BaseModel, ConfigDict, Field, model_validator

from gorgona_booking.booking import idempotency
from gorgona_booking.booking.idempotency import IdempotencyScope
from gorgona_booking.booking.models import IdempotencyKeyReusedError
from gorgona_booking.business import financial_documents, settlements
from gorgona_booking.business.financial_contracts import (
    InvoiceDocumentView,
    InvoiceDraftInput,
    InvoiceLineInput,
)
from gorgona_booking.business.module_gate import TRANSPORT_MODULE, module_writes
from gorgona_booking.business.settlement_contracts import ObligationView
from gorgona_booking.business.transport import TransportRevisionConflictError, require_transport
from gorgona_booking.db.pool import RuntimeConnection
from gorgona_booking.errors import (
    ConflictError,
    DomainError,
    InvalidReferenceError,
    NotFoundError,
)

_AMOUNT = r"^(0|[1-9][0-9]{0,16})(\.[0-9]{1,3})?$"
_MILES = r"^(0|[1-9][0-9]{0,6})(\.[0-9])?$"
_PERCENT = r"^(0|[1-9][0-9]{0,2})(\.[0-9]{1,2})?$"
_CLOSING = ("delivered", "refused", "damaged")


class TransportOrderInvoicedError(ConflictError):
    code = "TRANSPORT_ORDER_INVOICED"


class TransportOrderRateMissingError(ConflictError):
    code = "TRANSPORT_ORDER_RATE_MISSING"


class TransportOrderNotBillableError(ConflictError):
    code = "TRANSPORT_ORDER_NOT_BILLABLE"


class TransportMilesRequiredError(DomainError):
    code = "TRANSPORT_MILES_REQUIRED"


class TransportPayComponentConflictError(ConflictError):
    code = "TRANSPORT_PAY_COMPONENT_CONFLICT"


class TransportTripNotClosedError(ConflictError):
    code = "TRANSPORT_TRIP_NOT_CLOSED"


class TransportAlreadyAccruedError(ConflictError):
    code = "TRANSPORT_ALREADY_ACCRUED"


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


def _positive(value: str | None) -> str | None:
    if value is not None and Decimal(value) <= 0:
        raise ValueError("an amount is greater than zero")
    return value


class RateInput(_Strict):
    schema_version: Literal[1]
    expected_revision: int = Field(ge=0, le=2_147_483_647)
    currency: str = Field(pattern=r"^[A-Z]{3}$")
    basis: Literal["fixed", "per_mile"]
    # The whole order's amount, or the amount per mile.
    amount: str = Field(min_length=1, max_length=24, pattern=_AMOUNT)

    @model_validator(mode="after")
    def _amount(self) -> Self:
        _positive(self.amount)
        return self


class RateVersion(BaseModel):
    revision: int
    currency: str
    basis: str
    amount: str
    created_at: datetime


class RateView(BaseModel):
    order_id: UUID
    current: RateVersion | None
    versions: list[RateVersion]


class ExtraLine(_Strict):
    """A named extra (detention, lumper, …) to a named account (decision 2)."""

    description: str = Field(min_length=1, max_length=500)
    amount: str = Field(min_length=1, max_length=24, pattern=_AMOUNT)
    account_id: UUID

    @model_validator(mode="after")
    def _amount(self) -> Self:
        _positive(self.amount)
        return self


class OrderInvoiceInput(_Strict):
    schema_version: Literal[1]
    book_id: UUID
    control_account_id: UUID
    revenue_account_id: UUID
    invoice_date: date
    due_date: date | None = None
    number: str = Field(min_length=1, max_length=64)
    title: str = Field(default="Freight", min_length=1, max_length=200)
    # Needed exactly when the rate is per mile.
    miles: str | None = Field(default=None, pattern=_MILES)
    extra_lines: list[ExtraLine] = Field(default_factory=list, max_length=20)

    @model_validator(mode="after")
    def _miles(self) -> Self:
        _positive(self.miles)
        return self


class OrderInvoiceView(BaseModel):
    order_id: UUID
    book_id: UUID
    document_id: UUID
    rate_revision: int
    miles: str | None
    invoice: InvoiceDocumentView
    obligation: ObligationView | None


Role = Literal["driver", "owner_operator", "dispatch_fee", "other"]
ROLE_NAMES: dict[str, str] = {
    "driver": "Driver pay",
    "owner_operator": "Owner-operator pay",
    "dispatch_fee": "Dispatch fee",
    "other": "Trip pay",
}


class ComponentInput(_Strict):
    schema_version: Literal[1]
    counterparty_id: UUID
    role: Role
    currency: str = Field(pattern=r"^[A-Z]{3}$")
    basis: Literal["fixed", "per_mile", "percent"]
    amount: str | None = Field(default=None, max_length=24, pattern=_AMOUNT)
    rate: str | None = Field(default=None, max_length=24, pattern=_AMOUNT)
    percent: str | None = Field(default=None, max_length=6, pattern=_PERCENT)
    base: str | None = Field(default=None, max_length=24, pattern=_AMOUNT)

    @model_validator(mode="after")
    def _formula(self) -> Self:
        given = {
            name
            for name in ("amount", "rate", "percent", "base")
            if getattr(self, name) is not None
        }
        needed = {"fixed": {"amount"}, "per_mile": {"rate"}, "percent": {"percent", "base"}}
        if given != needed[self.basis]:
            raise ValueError(f"a {self.basis} component gives exactly {sorted(needed[self.basis])}")
        for value in (self.amount, self.rate, self.percent, self.base):
            _positive(value)
        if self.percent is not None and Decimal(self.percent) > 100:
            raise ValueError("a percentage is at most 100")
        return self


class AccrueInput(_Strict):
    schema_version: Literal[1]
    book_id: UUID
    expense_account_id: UUID
    payable_account_id: UUID
    accrual_date: date
    number: str = Field(min_length=1, max_length=64)
    title: str = Field(default="Trip pay", min_length=1, max_length=200)
    # Needed exactly when the component is per mile.
    miles: str | None = Field(default=None, pattern=_MILES)

    @model_validator(mode="after")
    def _miles(self) -> Self:
        _positive(self.miles)
        return self


class AccrualView(BaseModel):
    book_id: UUID
    document_id: UUID
    miles: str | None
    accrual: InvoiceDocumentView
    obligation: ObligationView | None


class ComponentView(BaseModel):
    component_id: UUID
    trip_id: UUID
    counterparty_id: UUID
    role: str
    currency: str
    basis: str
    amount: str | None
    rate: str | None
    percent: str | None
    base: str | None
    accrual: AccrualView | None


class PayView(BaseModel):
    trip_id: UUID
    components: list[ComponentView]


def _text(value: Decimal, places: int) -> str:
    """At least the currency's minor units, more only when the value has them."""
    text = format(value.normalize(), "f")
    whole, _, fraction = text.partition(".")
    fraction = fraction.ljust(places, "0")
    return f"{whole}.{fraction}" if fraction else whole


def _miles(value: Decimal | None) -> str | None:
    return None if value is None else f"{value:.1f}"


def _minor(value: Decimal, units: int) -> int:
    """Half up to the currency's minor units (ADR-0033 decision 2)."""
    return int((value * 10**units).quantize(Decimal(1), rounding=ROUND_HALF_UP))


def _money(minor: int, units: int) -> str:
    whole, fraction = divmod(minor, 10**units)
    return str(whole) if units == 0 else f"{whole}.{fraction:0{units}d}"


def _fingerprint(subject: UUID, body: BaseModel) -> str:
    return hashlib.sha256(
        json.dumps(
            {"subject": str(subject), "body": body.model_dump(mode="json")},
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
    ).hexdigest()


async def _units(conn: RuntimeConnection, currency: str) -> int:
    row = await (
        await conn.execute("select minor_units from gba.currencies where code = %s", (currency,))
    ).fetchone()
    if row is None:
        raise InvalidReferenceError("Unknown currency", field="currency")
    return int(row[0])


async def _party_revision(conn: RuntimeConnection, counterparty: UUID) -> int:
    row = await (
        await conn.execute(
            "select max(revision) from gba.counterparty_versions where counterparty_id = %s",
            (counterparty,),
        )
    ).fetchone()
    if row is None or row[0] is None:
        raise InvalidReferenceError("Unknown counterparty", field="counterparty_id")
    return int(row[0])


_OPEN = (
    "select l.quantity - coalesce(sum(q.quantity) filter (where e.kind = any(%s)), 0) "
    "from gba.transport_legs l "
    "left join gba.transport_event_quantities q on q.tenant_id = l.tenant_id "
    "and q.trip_id = l.trip_id and q.leg_position = l.position "
    "left join gba.transport_stop_events e on e.tenant_id = q.tenant_id and e.id = q.event_id "
)
_GROUP = " group by l.trip_id, l.position, l.quantity"
OPEN_BY_ORDER = (
    _OPEN + "where l.load_id in (select x.id from gba.transport_loads x "  # noqa: S608 - constants
    "where x.order_id = %s and not x.removed)" + _GROUP
)
OPEN_BY_TRIP = _OPEN + "where l.trip_id = %s" + _GROUP


async def _open_legs(conn: RuntimeConnection, query: str, value: object) -> list[int]:
    """Per leg, what is still open: planned less delivered, refused and damaged."""
    rows = await (await conn.execute(query, (list(_CLOSING), value))).fetchall()
    return [int(row[0]) for row in rows]


# Rates ------------------------------------------------------------------------------


async def load_rate(conn: RuntimeConnection, order_id: UUID) -> RateView | None:
    order = await (
        await conn.execute("select 1 from gba.transport_orders where id = %s", (order_id,))
    ).fetchone()
    if order is None:
        return None
    rows = await (
        await conn.execute(
            "select r.revision, r.currency, r.basis, r.amount, r.created_at, c.minor_units "
            "from gba.transport_order_rates r join gba.currencies c on c.code = r.currency "
            "where r.order_id = %s order by r.revision",
            (order_id,),
        )
    ).fetchall()
    versions = [
        RateVersion(
            revision=row[0],
            currency=row[1],
            basis=row[2],
            amount=_text(row[3], int(row[5])),
            created_at=row[4],
        )
        for row in rows
    ]
    current = versions[-1] if versions else None
    return RateView(order_id=order_id, current=current, versions=versions)


async def _invoiced(conn: RuntimeConnection, order_id: UUID) -> bool:
    row = await (
        await conn.execute(
            "select 1 from gba.transport_order_invoices where order_id = %s", (order_id,)
        )
    ).fetchone()
    return row is not None


async def save_rate(
    conn: RuntimeConnection,
    business: UUID,
    order_id: UUID,
    *,
    user_id: UUID,
    actor: str,
    key: str,
    body: RateInput,
) -> RateView:
    """A new version of the order's agreed rate, with the expected revision (decision 1)."""
    await require_transport(conn, business)
    scope = IdempotencyScope(business, actor, "transport.rate", key)
    fingerprint = _fingerprint(order_id, body)
    stored = await idempotency.claim(conn, scope, fingerprint)
    if stored is not None:
        if stored.request_hash != fingerprint:
            raise IdempotencyKeyReusedError("Key was used for another request")
        view = await load_rate(conn, order_id)
        if view is None:
            raise NotFoundError("Order not found", order_id=str(order_id))
        return view
    view = await load_rate(conn, order_id)
    if view is None:
        raise NotFoundError("Order not found", order_id=str(order_id))
    if await _invoiced(conn, order_id):
        raise TransportOrderInvoicedError("An invoiced order keeps its rate")
    current = view.current.revision if view.current else 0
    if body.expected_revision != current:
        raise TransportRevisionConflictError(
            "The rate changed meanwhile", expected=body.expected_revision, current=current
        )
    await _units(conn, body.currency)
    try:
        async with module_writes(TRANSPORT_MODULE), conn.transaction():
            await conn.execute(
                "insert into gba.transport_order_rates (tenant_id, order_id, revision, currency, "
                "basis, amount, created_by) values (%s, %s, %s, %s, %s, %s, %s)",
                (
                    business,
                    order_id,
                    current + 1,
                    body.currency,
                    body.basis,
                    Decimal(body.amount),
                    user_id,
                ),
            )
    except CheckViolation as exc:
        if exc.diag.constraint_name == "transport_order_rates_invoiced_check":
            raise TransportOrderInvoicedError("An invoiced order keeps its rate") from exc
        raise TransportRevisionConflictError("The rate changed meanwhile") from exc
    except UniqueViolation as exc:
        raise TransportRevisionConflictError("The rate changed meanwhile") from exc
    view = await load_rate(conn, order_id)
    assert view is not None  # noqa: S101 - written above
    await idempotency.complete(conn, scope, 200, {"order_id": str(order_id)})
    return view


# The customer invoice ---------------------------------------------------------------


async def load_order_invoice(
    conn: RuntimeConnection, business: UUID, order_id: UUID
) -> OrderInvoiceView | None:
    link = await (
        await conn.execute(
            "select book_id, document_id, rate_revision, miles "
            "from gba.transport_order_invoices where order_id = %s",
            (order_id,),
        )
    ).fetchone()
    if link is None:
        return None
    invoice = await financial_documents.load_invoice(conn, business, link[0], link[1])
    if invoice is None:
        raise NotFoundError("Invoice not found", document_id=str(link[1]))
    obligation = (
        await settlements.load_obligation(conn, business, link[0], invoice.obligation_id)
        if invoice.obligation_id is not None
        else None
    )
    return OrderInvoiceView(
        order_id=order_id,
        book_id=link[0],
        document_id=link[1],
        rate_revision=link[2],
        miles=_miles(link[3]),
        invoice=invoice,
        obligation=obligation,
    )


async def _billable(conn: RuntimeConnection, order_id: UUID) -> bool:
    """Every load fully planned and nothing open on the legs that carry them (decision 2)."""
    loads = await (
        await conn.execute(
            "select l.quantity, coalesce((select sum(g.quantity) from gba.transport_legs g "
            "where g.tenant_id = l.tenant_id and g.load_id = l.id), 0) "
            "from gba.transport_loads l where l.order_id = %s and not l.removed",
            (order_id,),
        )
    ).fetchall()
    if not loads or any(int(row[0]) != int(row[1]) for row in loads):
        return False
    open_quantities = await _open_legs(conn, OPEN_BY_ORDER, order_id)
    return all(quantity == 0 for quantity in open_quantities)


async def invoice_order(
    conn: RuntimeConnection,
    business: UUID,
    order_id: UUID,
    *,
    user_id: UUID,
    actor: str,
    key: str,
    body: OrderInvoiceInput,
) -> OrderInvoiceView:
    """The order's one FIN-03 receivable draft from its current rate (decision 2)."""
    await require_transport(conn, business)
    scope = IdempotencyScope(business, actor, "transport.order_invoice", key)
    fingerprint = _fingerprint(order_id, body)
    stored = await idempotency.claim(conn, scope, fingerprint)
    if stored is not None:
        if stored.request_hash != fingerprint:
            raise IdempotencyKeyReusedError("Key was used for another request")
        view = await load_order_invoice(conn, business, order_id)
        if view is None:
            raise NotFoundError("Invoice not found", order_id=str(order_id))
        return view
    order = await (
        await conn.execute(
            "select customer_id, reference from gba.transport_orders where id = %s for update",
            (order_id,),
        )
    ).fetchone()
    if order is None:
        raise NotFoundError("Order not found", order_id=str(order_id))
    if await _invoiced(conn, order_id):
        raise TransportOrderInvoicedError("This order already has its invoice")
    rate = await load_rate(conn, order_id)
    if rate is None or rate.current is None:
        raise TransportOrderRateMissingError("The order has no agreed rate")
    if not await _billable(conn, order_id):
        raise TransportOrderNotBillableError(
            "Every load must be planned and nothing may be open on its legs"
        )
    current = rate.current
    units = await _units(conn, current.currency)
    if current.basis == "per_mile":
        if body.miles is None:
            raise TransportMilesRequiredError("A per-mile rate needs the billed miles")
        freight = _minor(Decimal(current.amount) * Decimal(body.miles), units)
        description = f"Freight {order[1]} ({body.miles} mi at {current.amount})"
    else:
        freight = _minor(Decimal(current.amount), units)
        description = f"Freight {order[1]}"
    lines = [
        InvoiceLineInput(
            line_id=uuid7(),
            counter_account_id=body.revenue_account_id,
            description=description,
            amount=_money(freight, units),
        ),
        *(
            InvoiceLineInput(
                line_id=uuid7(),
                counter_account_id=extra.account_id,
                description=extra.description,
                amount=_money(_minor(Decimal(extra.amount), units), units),
            )
            for extra in body.extra_lines
        ),
    ]
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
            direction="receivable",
            counterparty_id=order[0],
            counterparty_revision=await _party_revision(conn, order[0]),
            currency=current.currency,
            invoice_date=body.invoice_date,
            due_date=body.due_date,
            control_account_id=body.control_account_id,
            title=body.title,
            number=body.number,
            lines=tuple(lines),
        ),
    )
    try:
        async with module_writes(TRANSPORT_MODULE), conn.transaction():
            await conn.execute(
                "insert into gba.transport_order_invoices (tenant_id, order_id, rate_revision, "
                "miles, book_id, document_id, created_by) values (%s, %s, %s, %s, %s, %s, %s)",
                (
                    business,
                    order_id,
                    current.revision,
                    Decimal(body.miles) if body.miles is not None else None,
                    body.book_id,
                    document,
                    user_id,
                ),
            )
    except CheckViolation as exc:
        raise TransportRevisionConflictError("The rate changed meanwhile") from exc
    except UniqueViolation as exc:
        raise TransportOrderInvoicedError("This order already has its invoice") from exc
    view = await load_order_invoice(conn, business, order_id)
    assert view is not None  # noqa: S101 - linked above
    await idempotency.complete(conn, scope, 200, {"order_id": str(order_id)})
    return view


# Pay components ---------------------------------------------------------------------


_COMPONENT = (
    "select c.id, c.trip_id, c.counterparty_id, c.role, c.currency, c.basis, c.amount, c.rate, "
    "c.percent, c.base, u.minor_units, a.book_id, a.document_id, a.miles "
    "from gba.transport_pay_components c join gba.currencies u on u.code = c.currency "
    "left join gba.transport_pay_accruals a on a.tenant_id = c.tenant_id "
    "and a.component_id = c.id "
)


async def _component(conn: RuntimeConnection, business: UUID, row: Any) -> ComponentView:
    units = int(row[10])
    accrual = None
    if row[11] is not None:
        document = await financial_documents.load_invoice(
            conn, business, row[11], row[12], kind="manual_accrual"
        )
        if document is None:
            raise NotFoundError("Accrual not found", document_id=str(row[12]))
        obligation = (
            await settlements.load_obligation(conn, business, row[11], document.obligation_id)
            if document.obligation_id is not None
            else None
        )
        accrual = AccrualView(
            book_id=row[11],
            document_id=row[12],
            miles=_miles(row[13]),
            accrual=document,
            obligation=obligation,
        )
    return ComponentView(
        component_id=row[0],
        trip_id=row[1],
        counterparty_id=row[2],
        role=row[3],
        currency=row[4],
        basis=row[5],
        amount=None if row[6] is None else _text(row[6], units),
        rate=None if row[7] is None else _text(row[7], units),
        percent=None if row[8] is None else _text(row[8], 0),
        base=None if row[9] is None else _text(row[9], units),
        accrual=accrual,
    )


async def load_component(
    conn: RuntimeConnection, business: UUID, component_id: UUID
) -> ComponentView | None:
    row = await (await conn.execute(_COMPONENT + "where c.id = %s", (component_id,))).fetchone()
    return None if row is None else await _component(conn, business, row)


async def load_pay(conn: RuntimeConnection, business: UUID, trip_id: UUID) -> PayView | None:
    trip = await (
        await conn.execute("select 1 from gba.transport_trips where id = %s", (trip_id,))
    ).fetchone()
    if trip is None:
        return None
    rows = await (
        await conn.execute(
            _COMPONENT + "where c.trip_id = %s order by c.created_at, c.id", (trip_id,)
        )
    ).fetchall()
    return PayView(
        trip_id=trip_id, components=[await _component(conn, business, row) for row in rows]
    )


def _same(view: ComponentView, trip_id: UUID, body: ComponentInput) -> bool:
    def number(value: str | None) -> Decimal | None:
        return None if value is None else Decimal(value)

    return (
        view.trip_id == trip_id
        and (view.counterparty_id, view.role, view.currency, view.basis)
        == (body.counterparty_id, body.role, body.currency, body.basis)
        and all(
            number(getattr(view, name)) == number(getattr(body, name))
            for name in ("amount", "rate", "percent", "base")
        )
    )


async def save_component(
    conn: RuntimeConnection,
    business: UUID,
    trip_id: UUID,
    component_id: UUID,
    *,
    user_id: UUID,
    actor: str,
    key: str,
    body: ComponentInput,
) -> ComponentView:
    """Register a pay component once with fixed details (decision 3)."""
    await require_transport(conn, business)
    scope = IdempotencyScope(business, actor, "transport.pay_component", key)
    fingerprint = _fingerprint(component_id, body)
    stored = await idempotency.claim(conn, scope, fingerprint)
    if stored is not None and stored.request_hash != fingerprint:
        raise IdempotencyKeyReusedError("Key was used for another request")
    view = await load_component(conn, business, component_id)
    if view is None:
        trip = await (
            await conn.execute("select 1 from gba.transport_trips where id = %s", (trip_id,))
        ).fetchone()
        if trip is None:
            raise NotFoundError("Trip not found", trip_id=str(trip_id))
        await _units(conn, body.currency)
        try:
            async with module_writes(TRANSPORT_MODULE), conn.transaction():
                await conn.execute(
                    "insert into gba.transport_pay_components (tenant_id, id, trip_id, "
                    "counterparty_id, role, currency, basis, amount, rate, percent, base, "
                    "created_by) values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
                    (
                        business,
                        component_id,
                        trip_id,
                        body.counterparty_id,
                        body.role,
                        body.currency,
                        body.basis,
                        *(
                            None if value is None else Decimal(value)
                            for value in (body.amount, body.rate, body.percent, body.base)
                        ),
                        user_id,
                    ),
                )
        except ForeignKeyViolation as exc:
            raise InvalidReferenceError("Unknown recipient", field="counterparty_id") from exc
        except UniqueViolation as exc:
            raise TransportPayComponentConflictError(
                "This recipient already has this component on the trip"
            ) from exc
        view = await load_component(conn, business, component_id)
        assert view is not None  # noqa: S101 - written above
    if not _same(view, trip_id, body):
        raise TransportPayComponentConflictError(
            "This component id is registered with other details"
        )
    if stored is None:
        await idempotency.complete(conn, scope, 200, {"component_id": str(component_id)})
    return view


async def accrue_component(
    conn: RuntimeConnection,
    business: UUID,
    trip_id: UUID,
    component_id: UUID,
    *,
    user_id: UUID,
    actor: str,
    key: str,
    body: AccrueInput,
) -> ComponentView:
    """The component's one FIN-03 payable accrual on a closed trip (decision 4)."""
    await require_transport(conn, business)
    scope = IdempotencyScope(business, actor, "transport.pay_accrual", key)
    fingerprint = _fingerprint(component_id, body)
    stored = await idempotency.claim(conn, scope, fingerprint)
    if stored is not None:
        if stored.request_hash != fingerprint:
            raise IdempotencyKeyReusedError("Key was used for another request")
        replay = await load_component(conn, business, component_id)
        if replay is None:
            raise NotFoundError("Component not found", component_id=str(component_id))
        return replay
    trip = await (
        await conn.execute(
            "select reference from gba.transport_trips where id = %s for update", (trip_id,)
        )
    ).fetchone()
    view = await load_component(conn, business, component_id)
    if trip is None or view is None or view.trip_id != trip_id:
        raise NotFoundError("Component not found", component_id=str(component_id))
    if view.accrual is not None:
        raise TransportAlreadyAccruedError("This component is already accrued")
    open_quantities = await _open_legs(conn, OPEN_BY_TRIP, trip_id)
    if not open_quantities or any(quantity != 0 for quantity in open_quantities):
        raise TransportTripNotClosedError("The trip still has open quantities")
    units = await _units(conn, view.currency)
    name = f"{ROLE_NAMES[view.role]} {trip[0]}"
    if view.basis == "per_mile":
        if body.miles is None or view.rate is None:
            raise TransportMilesRequiredError("A per-mile component needs the miles")
        amount = _minor(Decimal(view.rate) * Decimal(body.miles), units)
        name += f" ({body.miles} mi at {view.rate})"
    elif view.basis == "percent" and view.percent is not None and view.base is not None:
        amount = _minor(Decimal(view.percent) * Decimal(view.base) / 100, units)
        name += f" ({view.percent}% of {view.base})"
    else:
        amount = _minor(Decimal(view.amount or "0"), units)
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
            counterparty_revision=await _party_revision(conn, view.counterparty_id),
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
                    amount=_money(amount, units),
                ),
            ),
        ),
        kind="manual_accrual",
    )
    try:
        async with module_writes(TRANSPORT_MODULE), conn.transaction():
            await conn.execute(
                "insert into gba.transport_pay_accruals (tenant_id, component_id, miles, "
                "book_id, document_id, created_by) values (%s, %s, %s, %s, %s, %s)",
                (
                    business,
                    component_id,
                    Decimal(body.miles) if view.basis == "per_mile" and body.miles else None,
                    body.book_id,
                    document,
                    user_id,
                ),
            )
    except UniqueViolation as exc:
        raise TransportAlreadyAccruedError("This component is already accrued") from exc
    accrued = await load_component(conn, business, component_id)
    assert accrued is not None  # noqa: S101 - linked above
    await idempotency.complete(conn, scope, 200, {"component_id": str(component_id)})
    return accrued
