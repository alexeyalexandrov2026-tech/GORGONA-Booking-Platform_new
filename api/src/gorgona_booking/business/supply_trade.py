"""SUPPLY-01 Slice 3 (ADR-0039): Channel & contract price lists, retail/wholesale & 3PL
fulfillment orders, owner-isolated lot/serial shipments (posting STOCK-01 COGS write_off
+ FIN-03 receivable invoice), and customer returns (posting STOCK-01 return + FIN-03
credit note draft while restoring exact lot/serial balance and cost).
"""

from datetime import date
from typing import Any, Literal, Self
from uuid import UUID, uuid7

from psycopg import errors
from pydantic import AwareDatetime, Field, field_validator, model_validator

from gorgona_booking.booking.idempotency import IdempotencyScope
from gorgona_booking.business import commands, credit_notes, financial_documents, stock
from gorgona_booking.business.contracts import Strict, Versioned
from gorgona_booking.business.financial_contracts import (
    CreditDraftInput,
    CreditLineInput,
    InvoiceDraftInput,
    InvoiceIssueInput,
    InvoiceLineInput,
)
from gorgona_booking.business.ledger_contracts import CURRENCY_PATTERN, from_minor
from gorgona_booking.business.module_gate import module_writes, require_module
from gorgona_booking.business.stock_contracts import (
    ReturnInput,
    ReturnLine,
    WriteOffInput,
    WriteOffLine,
)
from gorgona_booking.business.supply_wms import (
    SUPPLY_MODULE,
    SupplyInsufficientLotError,
    SupplyOwnerMismatchError,
    SupplyRevisionConflictError,
    SupplyStateError,
    _check_ready,
    _clean_code,
    _clean_single_line,
    _item_quantity_text,
    _verify_owner_lot_bin,
)
from gorgona_booking.db.pool import RuntimeConnection
from gorgona_booking.errors import InvalidReferenceError, NotFoundError

PriceChannel = Literal["retail", "wholesale", "contract_b2b"]
TradeOrderKind = Literal["retail_sale", "wholesale_sale", "3pl_fulfillment"]
TradeOrderStatus = Literal[
    "draft",
    "confirmed",
    "partially_shipped",
    "shipped",
    "returned",
    "cancelled",
]


class PriceListItemInput(Strict):
    item_id: UUID
    min_quantity: int = Field(default=1, ge=1, le=999_999_999_999)
    unit_price_minor: int = Field(ge=0, le=999_999_999_999_999)


class PriceListInput(Versioned):
    expected_revision: int = Field(ge=0, le=1_000_000)
    location_id: UUID
    code: str
    title: str
    channel: PriceChannel
    currency: str = Field(pattern=CURRENCY_PATTERN)
    counterparty_id: UUID | None = None
    is_active: bool = True
    items: list[PriceListItemInput] = Field(min_length=1, max_length=200)

    @field_validator("code")
    @classmethod
    def valid_code(cls, value: str) -> str:
        return _clean_code(value, 64)

    @field_validator("title")
    @classmethod
    def valid_title(cls, value: str) -> str:
        return _clean_single_line(value, 200)

    @model_validator(mode="after")
    def unique_tiers(self) -> Self:
        keys = [(i.item_id, i.min_quantity) for i in self.items]
        if len(set(keys)) != len(keys):
            raise ValueError("Duplicate (item_id, min_quantity) tier in price list")
        return self


class PriceListItemView(Strict):
    schema_version: Literal[1] = 1
    price_list_item_id: UUID
    price_list_id: UUID
    item_id: UUID
    min_quantity: int
    unit_price_minor: int


class PriceListView(Strict):
    schema_version: Literal[1] = 1
    price_list_id: UUID
    location_id: UUID
    code: str
    title: str
    channel: PriceChannel
    currency: str
    counterparty_id: UUID | None
    is_active: bool
    revision: int
    recorded_by: UUID
    recorded_at: AwareDatetime
    items: list[PriceListItemView]


class PriceListCollection(Strict):
    schema_version: Literal[1] = 1
    items: list[PriceListView]


class TradeOrderLineInput(Strict):
    item_id: UUID
    ordered_quantity: int = Field(ge=1, le=999_999_999_999)
    unit_price_minor: int | None = Field(default=None, ge=0, le=999_999_999_999_999)


class TradeOrderInput(Versioned):
    expected_revision: int = Field(ge=0, le=1_000_000)
    location_id: UUID
    code: str
    order_kind: TradeOrderKind
    goods_owner_id: UUID
    customer_counterparty_id: UUID
    price_list_id: UUID | None = None
    currency: str = Field(pattern=CURRENCY_PATTERN)
    book_id: UUID | None = None
    control_account_id: UUID | None = None
    revenue_account_id: UUID | None = None
    status: Literal["draft", "confirmed", "cancelled"] = "confirmed"
    lines: list[TradeOrderLineInput] = Field(min_length=1, max_length=100)

    @field_validator("code")
    @classmethod
    def valid_code(cls, value: str) -> str:
        return _clean_code(value, 64)

    @model_validator(mode="after")
    def unique_items_and_accounts(self) -> Self:
        item_ids = [line.item_id for line in self.lines]
        if len(set(item_ids)) != len(item_ids):
            raise ValueError("Duplicate item_id in trade order lines")
        fin_fields = (self.book_id, self.control_account_id, self.revenue_account_id)
        if any(f is not None for f in fin_fields) and not all(f is not None for f in fin_fields):
            raise ValueError(
                "book_id, control_account_id, and revenue_account_id must be provided together"
            )
        return self


class TradeOrderLineView(Strict):
    schema_version: Literal[1] = 1
    order_line_id: UUID
    order_id: UUID
    line_no: int
    item_id: UUID
    ordered_quantity: int
    shipped_quantity: int
    returned_quantity: int
    unit_price_minor: int
    line_total_minor: int


class TradeOrderView(Strict):
    schema_version: Literal[1] = 1
    order_id: UUID
    location_id: UUID
    code: str
    order_kind: TradeOrderKind
    goods_owner_id: UUID
    customer_counterparty_id: UUID
    price_list_id: UUID | None
    currency: str
    book_id: UUID | None
    control_account_id: UUID | None
    revenue_account_id: UUID | None
    status: TradeOrderStatus
    total_ordered_minor: int
    total_shipped_minor: int
    total_returned_minor: int
    revision: int
    recorded_by: UUID
    recorded_at: AwareDatetime
    lines: list[TradeOrderLineView]


class TradeOrderList(Strict):
    schema_version: Literal[1] = 1
    items: list[TradeOrderView]


class OrderShipmentInput(Versioned):
    order_line_id: UUID
    bin_id: UUID
    lot_id: UUID
    quantity: int = Field(ge=1, le=999_999_999_999)
    serial_codes: list[str] = Field(default_factory=list, max_length=500)
    document_date: date
    invoice_number: str | None = None

    @field_validator("serial_codes")
    @classmethod
    def valid_serials(cls, value: list[str]) -> list[str]:
        cleaned = [_clean_code(s, 128) for s in value]
        if len(set(cleaned)) != len(cleaned):
            raise ValueError("Duplicate serial_code in serial_codes")
        return cleaned

    @field_validator("invoice_number")
    @classmethod
    def valid_invoice_number(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return _clean_single_line(value, 64)


class OrderShipmentView(Strict):
    schema_version: Literal[1] = 1
    shipment_id: UUID
    order_id: UUID
    order_line_id: UUID
    location_id: UUID
    goods_owner_id: UUID
    place_id: UUID
    bin_id: UUID
    item_id: UUID
    lot_id: UUID
    quantity: int
    returned_quantity: int
    unit_price_minor: int
    revenue_minor: int
    cogs_minor: int
    returned_cogs_minor: int
    wms_movement_id: UUID
    stock_document_id: UUID | None
    stock_line_no: int | None
    book_id: UUID | None
    invoice_document_id: UUID | None
    invoice_line_id: UUID | None
    obligation_id: UUID | None
    recorded_by: UUID
    recorded_at: AwareDatetime


class OrderShipmentList(Strict):
    schema_version: Literal[1] = 1
    items: list[OrderShipmentView]


class OrderReturnInput(Versioned):
    shipment_id: UUID
    bin_id: UUID
    quantity: int = Field(ge=1, le=999_999_999_999)
    serial_codes: list[str] = Field(default_factory=list, max_length=500)
    document_date: date
    reason: str
    credit_note_number: str | None = None

    @field_validator("serial_codes")
    @classmethod
    def valid_serials(cls, value: list[str]) -> list[str]:
        cleaned = [_clean_code(s, 128) for s in value]
        if len(set(cleaned)) != len(cleaned):
            raise ValueError("Duplicate serial_code in serial_codes")
        return cleaned

    @field_validator("reason")
    @classmethod
    def valid_reason(cls, value: str) -> str:
        return _clean_single_line(value, 300)

    @field_validator("credit_note_number")
    @classmethod
    def valid_credit_number(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return _clean_single_line(value, 64)


class OrderReturnView(Strict):
    schema_version: Literal[1] = 1
    return_id: UUID
    order_id: UUID
    order_line_id: UUID
    shipment_id: UUID
    location_id: UUID
    goods_owner_id: UUID
    place_id: UUID
    bin_id: UUID
    item_id: UUID
    lot_id: UUID
    quantity: int
    refund_minor: int
    cogs_restored_minor: int
    wms_movement_id: UUID
    stock_return_document_id: UUID | None
    stock_return_line_no: int | None
    book_id: UUID | None
    credit_note_document_id: UUID | None
    reason: str
    recorded_by: UUID
    recorded_at: AwareDatetime


class OrderReturnList(Strict):
    schema_version: Literal[1] = 1
    items: list[OrderReturnView]


def _shipment_from_row(r: tuple[Any, ...]) -> OrderShipmentView:
    return OrderShipmentView(
        shipment_id=r[0],
        order_id=r[1],
        order_line_id=r[2],
        location_id=r[3],
        goods_owner_id=r[4],
        place_id=r[5],
        bin_id=r[6],
        item_id=r[7],
        lot_id=r[8],
        quantity=int(r[9]),
        returned_quantity=int(r[10]),
        unit_price_minor=int(r[11]),
        revenue_minor=int(r[12]),
        cogs_minor=int(r[13]),
        returned_cogs_minor=int(r[14]),
        wms_movement_id=r[15],
        stock_document_id=r[16],
        stock_line_no=int(r[17]) if r[17] is not None else None,
        book_id=r[18],
        invoice_document_id=r[19],
        invoice_line_id=r[20],
        obligation_id=r[21],
        recorded_by=r[22],
        recorded_at=r[23],
    )


def _return_from_row(r: tuple[Any, ...]) -> OrderReturnView:
    return OrderReturnView(
        return_id=r[0],
        order_id=r[1],
        order_line_id=r[2],
        shipment_id=r[3],
        location_id=r[4],
        goods_owner_id=r[5],
        place_id=r[6],
        bin_id=r[7],
        item_id=r[8],
        lot_id=r[9],
        quantity=int(r[10]),
        refund_minor=int(r[11]),
        cogs_restored_minor=int(r[12]),
        wms_movement_id=r[13],
        stock_return_document_id=r[14],
        stock_return_line_no=int(r[15]) if r[15] is not None else None,
        book_id=r[16],
        credit_note_document_id=r[17],
        reason=str(r[18]),
        recorded_by=r[19],
        recorded_at=r[20],
    )


# ---------------------------------------------------------------------------
# Price Lists
# ---------------------------------------------------------------------------


async def get_price_list(
    conn: RuntimeConnection,
    business: UUID,
    price_list_id: UUID,
) -> PriceListView:
    await require_module(conn, business, SUPPLY_MODULE)
    hdr = await (
        await conn.execute(
            "select id, location_id, code, title, channel, currency, "
            "counterparty_id, is_active, revision, recorded_by, recorded_at "
            "from gba.supply_price_lists where tenant_id = %s and id = %s",
            (business, price_list_id),
        )
    ).fetchone()
    if hdr is None:
        raise NotFoundError("Supply price list not found")
    item_rows = await (
        await conn.execute(
            "select id, price_list_id, item_id, min_quantity, unit_price_minor "
            "from gba.supply_price_list_items "
            "where tenant_id = %s and price_list_id = %s "
            "order by item_id, min_quantity, id",
            (business, price_list_id),
        )
    ).fetchall()
    return PriceListView(
        price_list_id=hdr[0],
        location_id=hdr[1],
        code=str(hdr[2]),
        title=str(hdr[3]),
        channel=hdr[4],
        currency=str(hdr[5]),
        counterparty_id=hdr[6],
        is_active=bool(hdr[7]),
        revision=int(hdr[8]),
        recorded_by=hdr[9],
        recorded_at=hdr[10],
        items=[
            PriceListItemView(
                price_list_item_id=r[0],
                price_list_id=r[1],
                item_id=r[2],
                min_quantity=int(r[3]),
                unit_price_minor=int(r[4]),
            )
            for r in item_rows
        ],
    )


async def list_price_lists(
    conn: RuntimeConnection,
    business: UUID,
    *,
    location_id: UUID | None = None,
) -> PriceListCollection:
    await require_module(conn, business, SUPPLY_MODULE)
    rows = await (
        await conn.execute(
            "select id from gba.supply_price_lists "
            "where tenant_id = %s and (%s::uuid is null or location_id = %s) "
            "order by code, id",
            (business, location_id, location_id),
        )
    ).fetchall()
    return PriceListCollection(items=[await get_price_list(conn, business, row[0]) for row in rows])


async def save_price_list(
    conn: RuntimeConnection,
    business: UUID,
    price_list_id: UUID,
    *,
    user_id: UUID,
    actor: str,
    key: str,
    body: PriceListInput,
) -> PriceListView:
    _check_ready()
    await require_module(conn, business, SUPPLY_MODULE)
    scope = IdempotencyScope(business, actor, "supply.price_list.save", key)
    replay = await commands.claim(
        conn,
        scope,
        commands.fingerprint({"price_list_id": str(price_list_id), **body.model_dump(mode="json")}),
        PriceListView,
    )
    if replay is not None:
        return replay

    async with module_writes(SUPPLY_MODULE):
        existing = await (
            await conn.execute(
                "select revision, location_id from gba.supply_price_lists "
                "where tenant_id = %s and id = %s for update",
                (business, price_list_id),
            )
        ).fetchone()
        try:
            if existing is None:
                if body.expected_revision != 0:
                    raise SupplyRevisionConflictError(
                        "Price list does not exist yet; expected_revision must be 0"
                    )
                await conn.execute(
                    "insert into gba.supply_price_lists ("
                    "id, tenant_id, location_id, code, title, channel, currency, "
                    "counterparty_id, is_active, revision, recorded_by"
                    ") values (%s, %s, %s, %s, %s, %s, %s, %s, %s, 1, %s)",
                    (
                        price_list_id,
                        business,
                        body.location_id,
                        body.code,
                        body.title,
                        body.channel,
                        body.currency,
                        body.counterparty_id,
                        body.is_active,
                        user_id,
                    ),
                )
            else:
                curr_rev, curr_loc = int(existing[0]), existing[1]
                if body.expected_revision != curr_rev:
                    raise SupplyRevisionConflictError("Price list revision mismatch")
                if body.location_id != curr_loc:
                    raise InvalidReferenceError("Price list location_id cannot be changed")
                await conn.execute(
                    "update gba.supply_price_lists set code = %s, title = %s, channel = %s, "
                    "currency = %s, counterparty_id = %s, is_active = %s, "
                    "revision = revision + 1, recorded_by = %s, recorded_at = clock_timestamp() "
                    "where tenant_id = %s and id = %s",
                    (
                        body.code,
                        body.title,
                        body.channel,
                        body.currency,
                        body.counterparty_id,
                        body.is_active,
                        user_id,
                        business,
                        price_list_id,
                    ),
                )
                await conn.execute(
                    "delete from gba.supply_price_list_items "
                    "where tenant_id = %s and price_list_id = %s",
                    (business, price_list_id),
                )
            for item in body.items:
                await conn.execute(
                    "insert into gba.supply_price_list_items ("
                    "id, tenant_id, location_id, price_list_id, item_id, "
                    "min_quantity, unit_price_minor"
                    ") values (%s, %s, %s, %s, %s, %s, %s)",
                    (
                        uuid7(),
                        business,
                        body.location_id,
                        price_list_id,
                        item.item_id,
                        item.min_quantity,
                        item.unit_price_minor,
                    ),
                )
        except errors.UniqueViolation as exc:
            raise SupplyRevisionConflictError(
                "Price list code or item tier already exists in this branch"
            ) from exc
        except errors.ForeignKeyViolation as exc:
            raise InvalidReferenceError(
                "Referenced location, counterparty, or item not found"
            ) from exc

        view = await get_price_list(conn, business, price_list_id)
        await commands.complete(conn, scope, view)
        return view


# ---------------------------------------------------------------------------
# Trade & 3PL Fulfillment Orders
# ---------------------------------------------------------------------------


async def get_trade_order(
    conn: RuntimeConnection,
    business: UUID,
    order_id: UUID,
) -> TradeOrderView:
    await require_module(conn, business, SUPPLY_MODULE)
    hdr = await (
        await conn.execute(
            "select id, location_id, code, order_kind, goods_owner_id, "
            "customer_counterparty_id, price_list_id, currency, book_id, "
            "control_account_id, revenue_account_id, status, total_ordered_minor, "
            "total_shipped_minor, total_returned_minor, revision, recorded_by, recorded_at "
            "from gba.supply_trade_orders where tenant_id = %s and id = %s",
            (business, order_id),
        )
    ).fetchone()
    if hdr is None:
        raise NotFoundError("Supply trade order not found")
    line_rows = await (
        await conn.execute(
            "select id, order_id, line_no, item_id, ordered_quantity, "
            "shipped_quantity, returned_quantity, unit_price_minor, line_total_minor "
            "from gba.supply_trade_order_lines "
            "where tenant_id = %s and order_id = %s order by line_no",
            (business, order_id),
        )
    ).fetchall()
    return TradeOrderView(
        order_id=hdr[0],
        location_id=hdr[1],
        code=str(hdr[2]),
        order_kind=hdr[3],
        goods_owner_id=hdr[4],
        customer_counterparty_id=hdr[5],
        price_list_id=hdr[6],
        currency=str(hdr[7]),
        book_id=hdr[8],
        control_account_id=hdr[9],
        revenue_account_id=hdr[10],
        status=hdr[11],
        total_ordered_minor=int(hdr[12]),
        total_shipped_minor=int(hdr[13]),
        total_returned_minor=int(hdr[14]),
        revision=int(hdr[15]),
        recorded_by=hdr[16],
        recorded_at=hdr[17],
        lines=[
            TradeOrderLineView(
                order_line_id=r[0],
                order_id=r[1],
                line_no=int(r[2]),
                item_id=r[3],
                ordered_quantity=int(r[4]),
                shipped_quantity=int(r[5]),
                returned_quantity=int(r[6]),
                unit_price_minor=int(r[7]),
                line_total_minor=int(r[8]),
            )
            for r in line_rows
        ],
    )


async def list_trade_orders(
    conn: RuntimeConnection,
    business: UUID,
    *,
    location_id: UUID | None = None,
    goods_owner_id: UUID | None = None,
) -> TradeOrderList:
    await require_module(conn, business, SUPPLY_MODULE)
    rows = await (
        await conn.execute(
            "select id from gba.supply_trade_orders "
            "where tenant_id = %s "
            "and (%s::uuid is null or location_id = %s) "
            "and (%s::uuid is null or goods_owner_id = %s) "
            "order by recorded_at desc, code, id",
            (business, location_id, location_id, goods_owner_id, goods_owner_id),
        )
    ).fetchall()
    return TradeOrderList(items=[await get_trade_order(conn, business, row[0]) for row in rows])


async def _resolve_line_unit_price(
    conn: RuntimeConnection,
    business: UUID,
    *,
    price_list_id: UUID | None,
    item_id: UUID,
    ordered_quantity: int,
    explicit_price: int | None,
) -> int:
    if explicit_price is not None:
        return explicit_price
    if price_list_id is None:
        raise InvalidReferenceError(
            "unit_price_minor is required when order does not reference a price_list_id"
        )
    row = await (
        await conn.execute(
            "select unit_price_minor from gba.supply_price_list_items "
            "where tenant_id = %s and price_list_id = %s and item_id = %s "
            "and min_quantity <= %s order by min_quantity desc limit 1",
            (business, price_list_id, item_id, ordered_quantity),
        )
    ).fetchone()
    if row is None:
        raise InvalidReferenceError("No matching price list tier found for ordered item/quantity")
    return int(row[0])


async def save_trade_order(
    conn: RuntimeConnection,
    business: UUID,
    order_id: UUID,
    *,
    user_id: UUID,
    actor: str,
    key: str,
    body: TradeOrderInput,
) -> TradeOrderView:
    _check_ready()
    await require_module(conn, business, SUPPLY_MODULE)
    scope = IdempotencyScope(business, actor, "supply.order.save", key)
    replay = await commands.claim(
        conn,
        scope,
        commands.fingerprint({"order_id": str(order_id), **body.model_dump(mode="json")}),
        TradeOrderView,
    )
    if replay is not None:
        return replay

    owner_row = await (
        await conn.execute(
            "select owner_kind, is_active from gba.supply_goods_owners "
            "where tenant_id = %s and location_id = %s and id = %s",
            (business, body.location_id, body.goods_owner_id),
        )
    ).fetchone()
    if owner_row is None:
        raise InvalidReferenceError("Goods owner not found in this branch")
    if not owner_row[1]:
        raise SupplyStateError("Goods owner is inactive")
    owner_kind = str(owner_row[0])
    if body.order_kind in ("retail_sale", "wholesale_sale") and owner_kind != "company_entity":
        raise SupplyOwnerMismatchError(
            "Retail and wholesale sale orders require a company_entity goods owner"
        )
    if body.order_kind == "3pl_fulfillment" and owner_kind != "counterparty_3pl":
        raise SupplyOwnerMismatchError(
            "3PL fulfillment orders require a counterparty_3pl goods owner"
        )
    if body.order_kind in ("retail_sale", "wholesale_sale") and body.book_id is None:
        raise InvalidReferenceError(
            "Company retail/wholesale sale orders require book_id, control_account_id, "
            "and revenue_account_id"
        )

    resolved_lines: list[tuple[int, UUID, int, int, int]] = []
    total_ordered_minor = 0
    for idx, line in enumerate(body.lines, start=1):
        unit_price = await _resolve_line_unit_price(
            conn,
            business,
            price_list_id=body.price_list_id,
            item_id=line.item_id,
            ordered_quantity=line.ordered_quantity,
            explicit_price=line.unit_price_minor,
        )
        line_total = line.ordered_quantity * unit_price
        total_ordered_minor += line_total
        resolved_lines.append((idx, line.item_id, line.ordered_quantity, unit_price, line_total))

    async with module_writes(SUPPLY_MODULE):
        existing = await (
            await conn.execute(
                "select revision, location_id, goods_owner_id, status, total_shipped_minor "
                "from gba.supply_trade_orders where tenant_id = %s and id = %s for update",
                (business, order_id),
            )
        ).fetchone()
        try:
            if existing is None:
                if body.expected_revision != 0:
                    raise SupplyRevisionConflictError(
                        "Trade order does not exist yet; expected_revision must be 0"
                    )
                await conn.execute(
                    "insert into gba.supply_trade_orders ("
                    "id, tenant_id, location_id, code, order_kind, goods_owner_id, "
                    "customer_counterparty_id, price_list_id, currency, book_id, "
                    "control_account_id, revenue_account_id, status, total_ordered_minor, "
                    "revision, recorded_by"
                    ") values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 1, %s)",
                    (
                        order_id,
                        business,
                        body.location_id,
                        body.code,
                        body.order_kind,
                        body.goods_owner_id,
                        body.customer_counterparty_id,
                        body.price_list_id,
                        body.currency,
                        body.book_id,
                        body.control_account_id,
                        body.revenue_account_id,
                        body.status,
                        total_ordered_minor,
                        user_id,
                    ),
                )
            else:
                curr_rev, curr_loc, curr_owner, curr_status, shipped_minor = (
                    int(existing[0]),
                    existing[1],
                    existing[2],
                    str(existing[3]),
                    int(existing[4]),
                )
                if body.expected_revision != curr_rev:
                    raise SupplyRevisionConflictError("Trade order revision mismatch")
                if body.location_id != curr_loc or body.goods_owner_id != curr_owner:
                    raise SupplyOwnerMismatchError(
                        "Trade order location_id and goods_owner_id cannot be changed"
                    )
                if curr_status in ("partially_shipped", "shipped", "returned") or shipped_minor > 0:
                    raise SupplyStateError(
                        "Trade order already has shipments and cannot have its lines replaced"
                    )
                await conn.execute(
                    "update gba.supply_trade_orders set code = %s, order_kind = %s, "
                    "customer_counterparty_id = %s, price_list_id = %s, currency = %s, "
                    "book_id = %s, control_account_id = %s, revenue_account_id = %s, "
                    "status = %s, total_ordered_minor = %s, revision = revision + 1, "
                    "recorded_by = %s, recorded_at = clock_timestamp() "
                    "where tenant_id = %s and id = %s",
                    (
                        body.code,
                        body.order_kind,
                        body.customer_counterparty_id,
                        body.price_list_id,
                        body.currency,
                        body.book_id,
                        body.control_account_id,
                        body.revenue_account_id,
                        body.status,
                        total_ordered_minor,
                        user_id,
                        business,
                        order_id,
                    ),
                )
                await conn.execute(
                    "delete from gba.supply_trade_order_lines "
                    "where tenant_id = %s and order_id = %s",
                    (business, order_id),
                )
            for line_no, item_id, qty, unit_price, line_total in resolved_lines:
                await conn.execute(
                    "insert into gba.supply_trade_order_lines ("
                    "id, tenant_id, location_id, order_id, line_no, item_id, "
                    "ordered_quantity, unit_price_minor, line_total_minor"
                    ") values (%s, %s, %s, %s, %s, %s, %s, %s, %s)",
                    (
                        uuid7(),
                        business,
                        body.location_id,
                        order_id,
                        line_no,
                        item_id,
                        qty,
                        unit_price,
                        line_total,
                    ),
                )
        except errors.UniqueViolation as exc:
            raise SupplyRevisionConflictError(
                "Trade order code already exists in this branch"
            ) from exc
        except errors.ForeignKeyViolation as exc:
            raise InvalidReferenceError(
                "Referenced customer counterparty, price list, book, or item not found"
            ) from exc

        view = await get_trade_order(conn, business, order_id)
        await commands.complete(conn, scope, view)
        return view


# ---------------------------------------------------------------------------
# Owner-Isolated Lot/Serial Allocation & Shipment
# ---------------------------------------------------------------------------


async def list_order_shipments(
    conn: RuntimeConnection,
    business: UUID,
    order_id: UUID,
) -> OrderShipmentList:
    await require_module(conn, business, SUPPLY_MODULE)
    rows = await (
        await conn.execute(
            "select id, order_id, order_line_id, location_id, goods_owner_id, "
            "place_id, bin_id, item_id, lot_id, quantity, returned_quantity, "
            "unit_price_minor, revenue_minor, cogs_minor, returned_cogs_minor, "
            "wms_movement_id, stock_document_id, stock_line_no, book_id, "
            "invoice_document_id, invoice_line_id, obligation_id, recorded_by, recorded_at "
            "from gba.supply_order_shipments "
            "where tenant_id = %s and order_id = %s order by recorded_at, id",
            (business, order_id),
        )
    ).fetchall()
    return OrderShipmentList(items=[_shipment_from_row(r) for r in rows])


async def post_order_shipment(
    conn: RuntimeConnection,
    business: UUID,
    order_id: UUID,
    *,
    user_id: UUID,
    actor: str,
    key: str,
    body: OrderShipmentInput,
) -> OrderShipmentView:
    _check_ready()
    await require_module(conn, business, SUPPLY_MODULE)
    scope = IdempotencyScope(business, actor, "supply.order.ship", key)
    replay = await commands.claim(
        conn,
        scope,
        commands.fingerprint({"order_id": str(order_id), **body.model_dump(mode="json")}),
        OrderShipmentView,
    )
    if replay is not None:
        return replay

    ord_row = await (
        await conn.execute(
            "select location_id, code, order_kind, goods_owner_id, customer_counterparty_id, "
            "currency, book_id, control_account_id, revenue_account_id, status "
            "from gba.supply_trade_orders where tenant_id = %s and id = %s for update",
            (business, order_id),
        )
    ).fetchone()
    if ord_row is None:
        raise NotFoundError("Supply trade order not found")
    (
        loc_id,
        ord_code,
        _ord_kind,
        owner_id,
        customer_cp_id,
        currency,
        book_id,
        control_acct_id,
        revenue_acct_id,
        status,
    ) = (
        ord_row[0],
        str(ord_row[1]),
        str(ord_row[2]),
        ord_row[3],
        ord_row[4],
        str(ord_row[5]),
        ord_row[6],
        ord_row[7],
        ord_row[8],
        str(ord_row[9]),
    )
    if status not in ("confirmed", "partially_shipped"):
        raise SupplyStateError(f"Cannot ship trade order in status {status}")

    line_row = await (
        await conn.execute(
            "select item_id, ordered_quantity, shipped_quantity, unit_price_minor "
            "from gba.supply_trade_order_lines "
            "where tenant_id = %s and order_id = %s and id = %s for update",
            (business, order_id, body.order_line_id),
        )
    ).fetchone()
    if line_row is None:
        raise InvalidReferenceError("Order line does not belong to this trade order")
    item_id, ordered_qty, shipped_qty, unit_price_minor = (
        line_row[0],
        int(line_row[1]),
        int(line_row[2]),
        int(line_row[3]),
    )
    if shipped_qty + body.quantity > ordered_qty:
        raise SupplyStateError("Shipment quantity exceeds remaining unshipped order line quantity")

    owner_kind, legal_entity_id, place_id, _lot_status = await _verify_owner_lot_bin(
        conn,
        business,
        location_id=loc_id,
        goods_owner_id=owner_id,
        item_id=item_id,
        lot_id=body.lot_id,
        bin_id=body.bin_id,
    )

    bal_row = await (
        await conn.execute(
            "select id, quantity from gba.supply_lot_balances "
            "where tenant_id = %s and bin_id = %s and goods_owner_id = %s "
            "and item_id = %s and lot_id = %s for update",
            (business, body.bin_id, owner_id, item_id, body.lot_id),
        )
    ).fetchone()
    if bal_row is None or int(bal_row[1]) < body.quantity:
        raise SupplyInsufficientLotError(
            "Insufficient available lot balance in bin for this order's goods owner"
        )
    bal_id = bal_row[0]

    if body.serial_codes and len(body.serial_codes) != body.quantity:
        raise SupplyStateError(
            "When serial_codes are provided on shipment, count must equal quantity"
        )

    revenue_minor = body.quantity * unit_price_minor
    stock_doc_id: UUID | None = None
    stock_line_no: int | None = None
    cogs_minor = 0
    inv_book_id: UUID | None = None
    inv_doc_id: UUID | None = None
    inv_line_id: UUID | None = None
    obligation_id: UUID | None = None

    if owner_kind == "company_entity":
        if legal_entity_id is None:
            raise SupplyOwnerMismatchError("Company goods owner requires legal_entity_id")
        if book_id is None or control_acct_id is None or revenue_acct_id is None:
            raise InvalidReferenceError(
                "Company sale shipment requires book_id, control_account_id, and revenue_account_id"
            )
        qty_text = await _item_quantity_text(conn, business, item_id, body.quantity)
        stock_doc_id = uuid7()
        await stock.post_document(
            conn,
            business,
            stock_doc_id,
            user=user_id,
            actor=actor,
            key=f"sup-shp-stk-{key}"[:120],
            body=WriteOffInput(
                kind="write_off",
                reason="used",
                legal_entity_id=legal_entity_id,
                place_id=place_id,
                document_date=body.document_date,
                lines=(WriteOffLine(item_id=item_id, quantity=qty_text),),
            ),
        )
        stock_line_no = 1
        val_row = await (
            await conn.execute(
                "select amount_minor from gba.stock_valuations "
                "where tenant_id = %s and document_id = %s and line_no = 1",
                (business, stock_doc_id),
            )
        ).fetchone()
        cogs_minor = int(val_row[0]) if val_row is not None else 0

        if revenue_minor > 0:
            cp_row = await (
                await conn.execute(
                    "select max(revision) from gba.counterparty_versions "
                    "where tenant_id = %s and counterparty_id = %s",
                    (business, customer_cp_id),
                )
            ).fetchone()
            curr_row = await (
                await conn.execute(
                    "select minor_units from gba.currencies where code = %s",
                    (currency,),
                )
            ).fetchone()
            if cp_row is None or cp_row[0] is None or curr_row is None:
                raise InvalidReferenceError("Customer counterparty or currency not found")
            cp_rev = int(cp_row[0])
            scale = int(curr_row[0])
            inv_book_id = book_id
            inv_doc_id = uuid7()
            inv_line_id = uuid7()
            inv_num = body.invoice_number or f"{ord_code}-SHP-{str(inv_doc_id)[:8].upper()}"[:64]
            await financial_documents.save_draft(
                conn,
                business_id=business,
                book_id=book_id,
                document_id=inv_doc_id,
                user_id=user_id,
                actor=actor,
                key=f"sup-shp-inv-dr-{key}"[:120],
                body=InvoiceDraftInput(
                    expected_revision=0,
                    direction="receivable",
                    counterparty_id=customer_cp_id,
                    counterparty_revision=cp_rev,
                    currency=currency,
                    invoice_date=body.document_date,
                    due_date=body.document_date,
                    control_account_id=control_acct_id,
                    title=f"Trade order {ord_code} shipment",
                    number=inv_num,
                    lines=(
                        InvoiceLineInput(
                            line_id=inv_line_id,
                            counter_account_id=revenue_acct_id,
                            description=f"Order {ord_code} shipment ({body.quantity} units)",
                            amount=from_minor(revenue_minor, scale),
                        ),
                    ),
                ),
            )
            issued = await financial_documents.issue_document(
                conn,
                business_id=business,
                book_id=book_id,
                document_id=inv_doc_id,
                user_id=user_id,
                actor=actor,
                key=f"sup-shp-inv-is-{key}"[:120],
                body=InvoiceIssueInput(
                    expected_revision=1,
                    entry_date=body.document_date,
                    attestation="confirmed_account_treatment",
                ),
            )
            obligation_id = issued.obligation_id

    shipment_id = uuid7()
    wms_movement_id = uuid7()
    async with module_writes(SUPPLY_MODULE):
        await conn.execute(
            "update gba.supply_lot_balances set quantity = quantity - %s, "
            "updated_at = clock_timestamp() where tenant_id = %s and id = %s",
            (body.quantity, business, bal_id),
        )
        for scode in body.serial_codes:
            s_row = await (
                await conn.execute(
                    "select id, state, bin_id from gba.supply_serial_units "
                    "where tenant_id = %s and location_id = %s and goods_owner_id = %s "
                    "and item_id = %s and lot_id = %s and serial_code = %s for update",
                    (business, loc_id, owner_id, item_id, body.lot_id, scode),
                )
            ).fetchone()
            if s_row is None:
                raise InvalidReferenceError(
                    f"Serial unit {scode} not found for this goods owner and lot"
                )
            if str(s_row[1]) != "in_stock" or s_row[2] != body.bin_id:
                raise SupplyStateError(f"Serial unit {scode} is not in_stock in the specified bin")
            await conn.execute(
                "update gba.supply_serial_units set state = 'shipped' "
                "where tenant_id = %s and id = %s",
                (business, s_row[0]),
            )

        await conn.execute(
            "insert into gba.supply_wms_movements ("
            "tenant_id, id, location_id, place_id, bin_id, goods_owner_id, item_id, lot_id, "
            "movement_kind, direction, quantity, stock_document_id, stock_line_no, "
            "reference_code, recorded_by"
            ") values ("
            "%s, %s, %s, %s, %s, %s, %s, %s, 'outbound_pick', 'out', %s, %s, %s, %s, %s"
            ")",
            (
                business,
                wms_movement_id,
                loc_id,
                place_id,
                body.bin_id,
                owner_id,
                item_id,
                body.lot_id,
                body.quantity,
                stock_doc_id,
                stock_line_no,
                ord_code,
                user_id,
            ),
        )
        await conn.execute(
            "insert into gba.supply_order_shipments ("
            "id, tenant_id, location_id, order_id, order_line_id, goods_owner_id, place_id, "
            "bin_id, item_id, lot_id, quantity, unit_price_minor, revenue_minor, cogs_minor, "
            "wms_movement_id, stock_document_id, stock_line_no, book_id, invoice_document_id, "
            "invoice_line_id, obligation_id, recorded_by"
            ") values ("
            "%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, "
            "%s, %s, %s, %s, %s, %s, %s, %s"
            ")",
            (
                shipment_id,
                business,
                loc_id,
                order_id,
                body.order_line_id,
                owner_id,
                place_id,
                body.bin_id,
                item_id,
                body.lot_id,
                body.quantity,
                unit_price_minor,
                revenue_minor,
                cogs_minor,
                wms_movement_id,
                stock_doc_id,
                stock_line_no,
                inv_book_id,
                inv_doc_id,
                inv_line_id,
                obligation_id,
                user_id,
            ),
        )
        await conn.execute(
            "update gba.supply_trade_order_lines set shipped_quantity = shipped_quantity + %s "
            "where tenant_id = %s and id = %s",
            (body.quantity, business, body.order_line_id),
        )
        rem_row = await (
            await conn.execute(
                "select sum(ordered_quantity - shipped_quantity) "
                "from gba.supply_trade_order_lines where tenant_id = %s and order_id = %s",
                (business, order_id),
            )
        ).fetchone()
        remaining = int(rem_row[0]) if rem_row and rem_row[0] is not None else 0
        next_status = "shipped" if remaining == 0 else "partially_shipped"
        await conn.execute(
            "update gba.supply_trade_orders set "
            "total_shipped_minor = total_shipped_minor + %s, "
            "status = %s, revision = revision + 1, recorded_by = %s, "
            "recorded_at = clock_timestamp() where tenant_id = %s and id = %s",
            (revenue_minor, next_status, user_id, business, order_id),
        )

        row = await (
            await conn.execute(
                "select id, order_id, order_line_id, location_id, goods_owner_id, "
                "place_id, bin_id, item_id, lot_id, quantity, returned_quantity, "
                "unit_price_minor, revenue_minor, cogs_minor, returned_cogs_minor, "
                "wms_movement_id, stock_document_id, stock_line_no, book_id, "
                "invoice_document_id, invoice_line_id, obligation_id, recorded_by, recorded_at "
                "from gba.supply_order_shipments where tenant_id = %s and id = %s",
                (business, shipment_id),
            )
        ).fetchone()
        if row is None:
            raise NotFoundError("Saved shipment not found")
        view = _shipment_from_row(row)
        await commands.complete(conn, scope, view)
        return view


# ---------------------------------------------------------------------------
# Customer Return (Restores Lot/Serial Balance, STOCK-01 Return & FIN-03 Credit Note)
# ---------------------------------------------------------------------------


async def list_order_returns(
    conn: RuntimeConnection,
    business: UUID,
    order_id: UUID,
) -> OrderReturnList:
    await require_module(conn, business, SUPPLY_MODULE)
    rows = await (
        await conn.execute(
            "select id, order_id, order_line_id, shipment_id, location_id, "
            "goods_owner_id, place_id, bin_id, item_id, lot_id, quantity, refund_minor, "
            "cogs_restored_minor, wms_movement_id, stock_return_document_id, "
            "stock_return_line_no, book_id, credit_note_document_id, reason, "
            "recorded_by, recorded_at "
            "from gba.supply_order_returns "
            "where tenant_id = %s and order_id = %s order by recorded_at, id",
            (business, order_id),
        )
    ).fetchall()
    return OrderReturnList(items=[_return_from_row(r) for r in rows])


async def post_order_return(
    conn: RuntimeConnection,
    business: UUID,
    order_id: UUID,
    *,
    user_id: UUID,
    actor: str,
    key: str,
    body: OrderReturnInput,
) -> OrderReturnView:
    _check_ready()
    await require_module(conn, business, SUPPLY_MODULE)
    scope = IdempotencyScope(business, actor, "supply.order.return", key)
    replay = await commands.claim(
        conn,
        scope,
        commands.fingerprint({"order_id": str(order_id), **body.model_dump(mode="json")}),
        OrderReturnView,
    )
    if replay is not None:
        return replay

    ord_row = await (
        await conn.execute(
            "select location_id, code, customer_counterparty_id, currency, revenue_account_id "
            "from gba.supply_trade_orders where tenant_id = %s and id = %s for update",
            (business, order_id),
        )
    ).fetchone()
    if ord_row is None:
        raise NotFoundError("Supply trade order not found")
    loc_id, ord_code, customer_cp_id, currency, revenue_acct_id = (
        ord_row[0],
        str(ord_row[1]),
        ord_row[2],
        str(ord_row[3]),
        ord_row[4],
    )

    shp_row = await (
        await conn.execute(
            "select order_line_id, goods_owner_id, place_id, item_id, lot_id, quantity, "
            "returned_quantity, unit_price_minor, stock_document_id, stock_line_no, "
            "book_id, invoice_document_id, invoice_line_id, obligation_id "
            "from gba.supply_order_shipments "
            "where tenant_id = %s and order_id = %s and id = %s for update",
            (business, order_id, body.shipment_id),
        )
    ).fetchone()
    if shp_row is None:
        raise InvalidReferenceError("Shipment does not belong to this trade order")
    (
        order_line_id,
        owner_id,
        shp_place_id,
        item_id,
        lot_id,
        shipped_qty,
        already_returned_qty,
        unit_price_minor,
        src_stock_doc_id,
        src_stock_line_no,
        shp_book_id,
        shp_inv_doc_id,
        shp_inv_line_id,
        shp_obligation_id,
    ) = (
        shp_row[0],
        shp_row[1],
        shp_row[2],
        shp_row[3],
        shp_row[4],
        int(shp_row[5]),
        int(shp_row[6]),
        int(shp_row[7]),
        shp_row[8],
        int(shp_row[9]) if shp_row[9] is not None else None,
        shp_row[10],
        shp_row[11],
        shp_row[12],
        shp_row[13],
    )
    if already_returned_qty + body.quantity > shipped_qty:
        raise SupplyStateError("Return quantity exceeds remaining unreturned shipment quantity")

    if body.serial_codes and len(body.serial_codes) != body.quantity:
        raise SupplyStateError(
            "When serial_codes are provided on return, count must equal quantity"
        )

    owner_kind, legal_entity_id, bin_place_id, _lot_status = await _verify_owner_lot_bin(
        conn,
        business,
        location_id=loc_id,
        goods_owner_id=owner_id,
        item_id=item_id,
        lot_id=lot_id,
        bin_id=body.bin_id,
    )
    if bin_place_id != shp_place_id:
        raise InvalidReferenceError("Return bin must belong to the shipment's STOCK-01 place")

    refund_minor = body.quantity * unit_price_minor
    stock_return_doc_id: UUID | None = None
    stock_return_line_no: int | None = None
    cogs_restored_minor = 0
    credit_book_id: UUID | None = None
    credit_doc_id: UUID | None = None

    if (
        owner_kind == "company_entity"
        and src_stock_doc_id is not None
        and src_stock_line_no is not None
    ):
        if legal_entity_id is None:
            raise SupplyOwnerMismatchError("Company goods owner requires legal_entity_id")
        qty_text = await _item_quantity_text(conn, business, item_id, body.quantity)
        stock_return_doc_id = uuid7()
        await stock.post_document(
            conn,
            business,
            stock_return_doc_id,
            user=user_id,
            actor=actor,
            key=f"sup-ret-stk-{key}"[:120],
            body=ReturnInput(
                kind="return",
                reason="unused",
                legal_entity_id=legal_entity_id,
                place_id=shp_place_id,
                source_document_id=src_stock_doc_id,
                document_date=body.document_date,
                lines=(ReturnLine(source_line_no=src_stock_line_no, quantity=qty_text),),
            ),
        )
        stock_return_line_no = 1
        val_row = await (
            await conn.execute(
                "select amount_minor from gba.stock_valuations "
                "where tenant_id = %s and document_id = %s and line_no = 1",
                (business, stock_return_doc_id),
            )
        ).fetchone()
        cogs_restored_minor = int(val_row[0]) if val_row is not None else 0

        if (
            refund_minor > 0
            and shp_book_id is not None
            and shp_inv_doc_id is not None
            and shp_inv_line_id is not None
            and shp_obligation_id is not None
            and revenue_acct_id is not None
        ):
            cp_row = await (
                await conn.execute(
                    "select max(revision) from gba.counterparty_versions "
                    "where tenant_id = %s and counterparty_id = %s",
                    (business, customer_cp_id),
                )
            ).fetchone()
            curr_row = await (
                await conn.execute(
                    "select minor_units from gba.currencies where code = %s",
                    (currency,),
                )
            ).fetchone()
            if cp_row is None or cp_row[0] is None or curr_row is None:
                raise InvalidReferenceError("Customer counterparty or currency not found")
            cp_rev = int(cp_row[0])
            scale = int(curr_row[0])
            credit_book_id = shp_book_id
            credit_doc_id = uuid7()
            cn_num = (
                body.credit_note_number or f"{ord_code}-CR-{str(credit_doc_id)[:8].upper()}"[:64]
            )
            await credit_notes.save_draft(
                conn,
                business_id=business,
                book_id=shp_book_id,
                document_id=credit_doc_id,
                user_id=user_id,
                actor=actor,
                key=f"sup-ret-cn-dr-{key}"[:120],
                body=CreditDraftInput(
                    expected_revision=0,
                    credited_obligation_id=shp_obligation_id,
                    counterparty_revision=cp_rev,
                    credit_date=body.document_date,
                    due_date=body.document_date,
                    title=f"Trade order {ord_code} return credit note",
                    number=cn_num,
                    lines=(
                        CreditLineInput(
                            line_id=uuid7(),
                            credited_line_id=shp_inv_line_id,
                            counter_account_id=revenue_acct_id,
                            description=f"Order {ord_code} return ({body.quantity} units)",
                            amount=from_minor(refund_minor, scale),
                        ),
                    ),
                ),
            )

    return_id = uuid7()
    wms_movement_id = uuid7()
    async with module_writes(SUPPLY_MODULE):
        bal_row = await (
            await conn.execute(
                "select id from gba.supply_lot_balances "
                "where tenant_id = %s and bin_id = %s and goods_owner_id = %s "
                "and item_id = %s and lot_id = %s for update",
                (business, body.bin_id, owner_id, item_id, lot_id),
            )
        ).fetchone()
        if bal_row is None:
            await conn.execute(
                "insert into gba.supply_lot_balances ("
                "tenant_id, id, location_id, place_id, bin_id, goods_owner_id, "
                "item_id, lot_id, quantity"
                ") values (%s, %s, %s, %s, %s, %s, %s, %s, %s)",
                (
                    business,
                    uuid7(),
                    loc_id,
                    shp_place_id,
                    body.bin_id,
                    owner_id,
                    item_id,
                    lot_id,
                    body.quantity,
                ),
            )
        else:
            await conn.execute(
                "update gba.supply_lot_balances set quantity = quantity + %s, "
                "updated_at = clock_timestamp() where tenant_id = %s and id = %s",
                (body.quantity, business, bal_row[0]),
            )

        for scode in body.serial_codes:
            s_row = await (
                await conn.execute(
                    "select id, state from gba.supply_serial_units "
                    "where tenant_id = %s and location_id = %s and goods_owner_id = %s "
                    "and item_id = %s and lot_id = %s and serial_code = %s for update",
                    (business, loc_id, owner_id, item_id, lot_id, scode),
                )
            ).fetchone()
            if s_row is None:
                raise InvalidReferenceError(
                    f"Serial unit {scode} not found for this goods owner and lot"
                )
            if str(s_row[1]) != "shipped":
                raise SupplyStateError(f"Serial unit {scode} is not in shipped status")
            await conn.execute(
                "update gba.supply_serial_units set state = 'in_stock', bin_id = %s, "
                "place_id = %s where tenant_id = %s and id = %s",
                (body.bin_id, shp_place_id, business, s_row[0]),
            )

        await conn.execute(
            "insert into gba.supply_wms_movements ("
            "tenant_id, id, location_id, place_id, bin_id, goods_owner_id, item_id, lot_id, "
            "movement_kind, direction, quantity, stock_document_id, stock_line_no, "
            "reference_code, recorded_by"
            ") values ("
            "%s, %s, %s, %s, %s, %s, %s, %s, 'return_putaway', 'in', %s, %s, %s, %s, %s"
            ")",
            (
                business,
                wms_movement_id,
                loc_id,
                shp_place_id,
                body.bin_id,
                owner_id,
                item_id,
                lot_id,
                body.quantity,
                stock_return_doc_id,
                stock_return_line_no,
                ord_code,
                user_id,
            ),
        )
        await conn.execute(
            "insert into gba.supply_order_returns ("
            "id, tenant_id, location_id, order_id, order_line_id, shipment_id, "
            "goods_owner_id, place_id, bin_id, item_id, lot_id, quantity, refund_minor, "
            "cogs_restored_minor, wms_movement_id, stock_return_document_id, "
            "stock_return_line_no, book_id, credit_note_document_id, reason, recorded_by"
            ") values ("
            "%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, "
            "%s, %s, %s, %s, %s, %s, %s"
            ")",
            (
                return_id,
                business,
                loc_id,
                order_id,
                order_line_id,
                body.shipment_id,
                owner_id,
                shp_place_id,
                body.bin_id,
                item_id,
                lot_id,
                body.quantity,
                refund_minor,
                cogs_restored_minor,
                wms_movement_id,
                stock_return_doc_id,
                stock_return_line_no,
                credit_book_id,
                credit_doc_id,
                body.reason,
                user_id,
            ),
        )
        await conn.execute(
            "update gba.supply_order_shipments set "
            "returned_quantity = returned_quantity + %s, "
            "returned_cogs_minor = returned_cogs_minor + %s "
            "where tenant_id = %s and id = %s",
            (body.quantity, cogs_restored_minor, business, body.shipment_id),
        )
        await conn.execute(
            "update gba.supply_trade_order_lines set "
            "returned_quantity = returned_quantity + %s "
            "where tenant_id = %s and id = %s",
            (body.quantity, business, order_line_id),
        )
        line_totals = await (
            await conn.execute(
                "select sum(shipped_quantity), sum(returned_quantity) "
                "from gba.supply_trade_order_lines where tenant_id = %s and order_id = %s",
                (business, order_id),
            )
        ).fetchone()
        tot_shp = int(line_totals[0]) if line_totals and line_totals[0] is not None else 0
        tot_ret = int(line_totals[1]) if line_totals and line_totals[1] is not None else 0
        await conn.execute(
            "update gba.supply_trade_orders set "
            "total_returned_minor = total_returned_minor + %s, "
            "status = case when %s > 0 and %s = %s then 'returned' else status end, "
            "revision = revision + 1, recorded_by = %s, recorded_at = clock_timestamp() "
            "where tenant_id = %s and id = %s",
            (refund_minor, tot_shp, tot_ret, tot_shp, user_id, business, order_id),
        )

        row = await (
            await conn.execute(
                "select id, order_id, order_line_id, shipment_id, location_id, "
                "goods_owner_id, place_id, bin_id, item_id, lot_id, quantity, refund_minor, "
                "cogs_restored_minor, wms_movement_id, stock_return_document_id, "
                "stock_return_line_no, book_id, credit_note_document_id, reason, "
                "recorded_by, recorded_at "
                "from gba.supply_order_returns where tenant_id = %s and id = %s",
                (business, return_id),
            )
        ).fetchone()
        if row is None:
            raise NotFoundError("Saved return not found")
        view = _return_from_row(row)
        await commands.complete(conn, scope, view)
        return view
