"""MARKET-01 Slice 2 (ADR-0040): Multi-seller basket split into strictly single-seller orders
& FIN-03 receivable invoices (no shared/commingled multi-seller payment), customer refund
credit notes, and separate seller-billed operator commercial fees (zero GORGONA commission).
"""

from collections import defaultdict
from datetime import date
from typing import Any, Literal
from uuid import UUID, uuid7

from pydantic import AwareDatetime, Field, field_validator

from gorgona_booking.booking.idempotency import IdempotencyScope
from gorgona_booking.business import commands, credit_notes, financial_documents
from gorgona_booking.business.contracts import Strict, Versioned
from gorgona_booking.business.financial_contracts import (
    CreditDraftInput,
    CreditLineInput,
    InvoiceDraftInput,
    InvoiceIssueInput,
    InvoiceLineInput,
)
from gorgona_booking.business.ledger_contracts import CURRENCY_PATTERN, from_minor
from gorgona_booking.business.market_storefronts import (
    STOREFRONTS_MODULE,
    MarketStateError,
    _check_ready,
    _clean_line,
)
from gorgona_booking.business.module_gate import module_writes, require_module
from gorgona_booking.db.pool import RuntimeConnection
from gorgona_booking.errors import InvalidReferenceError, NotFoundError

MarketOrderStatus = Literal["confirmed", "fulfilled", "partially_refunded", "refunded"]


class BasketItemInput(Strict):
    listing_id: UUID
    quantity: int = Field(ge=1, le=999_999_999_999)


class SellerSettlementConfig(Strict):
    storefront_id: UUID
    book_id: UUID
    control_account_id: UUID
    revenue_account_id: UUID
    seller_counterparty_id: UUID | None = None


class BasketCheckoutInput(Versioned):
    location_id: UUID
    customer_counterparty_id: UUID
    marketplace_id: UUID | None = None
    currency: str = Field(pattern=CURRENCY_PATTERN)
    order_date: date
    items: list[BasketItemInput] = Field(min_length=1, max_length=100)
    seller_configs: list[SellerSettlementConfig] = Field(min_length=1, max_length=50)


class MarketOrderLineView(Strict):
    schema_version: Literal[1] = 1
    order_line_id: UUID
    order_id: UUID
    line_no: int
    listing_id: UUID
    quantity: int
    unit_price_minor: int
    line_total_minor: int


class MarketOrderView(Strict):
    schema_version: Literal[1] = 1
    order_id: UUID
    location_id: UUID
    basket_id: UUID
    storefront_id: UUID
    legal_entity_id: UUID
    customer_counterparty_id: UUID
    marketplace_id: UUID | None
    order_number: str
    currency: str
    total_minor: int
    refunded_minor: int
    status: MarketOrderStatus
    book_id: UUID
    control_account_id: UUID
    revenue_account_id: UUID
    invoice_document_id: UUID
    invoice_line_id: UUID
    obligation_id: UUID
    credit_note_document_id: UUID | None
    revision: int
    recorded_by: UUID
    recorded_at: AwareDatetime
    lines: list[MarketOrderLineView]


class MarketOrderList(Strict):
    schema_version: Literal[1] = 1
    items: list[MarketOrderView]


class BasketCheckoutView(Strict):
    schema_version: Literal[1] = 1
    basket_id: UUID
    location_id: UUID
    customer_counterparty_id: UUID
    marketplace_id: UUID | None
    currency: str
    split_order_count: int
    orders: list[MarketOrderView]


class MarketOrderRefundInput(Versioned):
    refund_minor: int = Field(ge=1, le=999_999_999_999_999)
    refund_date: date
    reason: str

    @field_validator("reason")
    @classmethod
    def valid_reason(cls, value: str) -> str:
        return _clean_line(value, 300)


class OperatorFeeView(Strict):
    schema_version: Literal[1] = 1
    fee_id: UUID
    location_id: UUID
    marketplace_id: UUID
    order_id: UUID
    seller_counterparty_id: UUID
    currency: str
    gorgona_commission_minor: Literal[0] = 0
    operator_fee_minor: int
    status: Literal["accrued", "invoiced", "waived"]
    recorded_by: UUID
    recorded_at: AwareDatetime


class OperatorFeeList(Strict):
    schema_version: Literal[1] = 1
    items: list[OperatorFeeView]


def _order_line_view(r: tuple[Any, ...]) -> MarketOrderLineView:
    return MarketOrderLineView(
        order_line_id=r[0],
        order_id=r[1],
        line_no=int(r[2]),
        listing_id=r[3],
        quantity=int(r[4]),
        unit_price_minor=int(r[5]),
        line_total_minor=int(r[6]),
    )


def _operator_fee_view(r: tuple[Any, ...]) -> OperatorFeeView:
    return OperatorFeeView(
        fee_id=r[0],
        location_id=r[1],
        marketplace_id=r[2],
        order_id=r[3],
        seller_counterparty_id=r[4],
        currency=str(r[5]),
        gorgona_commission_minor=0,
        operator_fee_minor=int(r[7]),
        status=r[8],
        recorded_by=r[9],
        recorded_at=r[10],
    )


async def get_market_order(
    conn: RuntimeConnection,
    business: UUID,
    order_id: UUID,
) -> MarketOrderView:
    await require_module(conn, business, STOREFRONTS_MODULE)
    hdr = await (
        await conn.execute(
            "select id, location_id, basket_id, storefront_id, legal_entity_id, "
            "customer_counterparty_id, marketplace_id, order_number, currency, total_minor, "
            "refunded_minor, status, book_id, control_account_id, revenue_account_id, "
            "invoice_document_id, invoice_line_id, obligation_id, credit_note_document_id, "
            "revision, recorded_by, recorded_at from gba.market_orders "
            "where tenant_id = %s and id = %s",
            (business, order_id),
        )
    ).fetchone()
    if hdr is None:
        raise NotFoundError("Marketplace order not found")
    lines = await (
        await conn.execute(
            "select id, order_id, line_no, listing_id, quantity, "
            "unit_price_minor, line_total_minor from gba.market_order_lines "
            "where tenant_id = %s and order_id = %s order by line_no",
            (business, order_id),
        )
    ).fetchall()
    return MarketOrderView(
        order_id=hdr[0],
        location_id=hdr[1],
        basket_id=hdr[2],
        storefront_id=hdr[3],
        legal_entity_id=hdr[4],
        customer_counterparty_id=hdr[5],
        marketplace_id=hdr[6],
        order_number=str(hdr[7]),
        currency=str(hdr[8]),
        total_minor=int(hdr[9]),
        refunded_minor=int(hdr[10]),
        status=hdr[11],
        book_id=hdr[12],
        control_account_id=hdr[13],
        revenue_account_id=hdr[14],
        invoice_document_id=hdr[15],
        invoice_line_id=hdr[16],
        obligation_id=hdr[17],
        credit_note_document_id=hdr[18],
        revision=int(hdr[19]),
        recorded_by=hdr[20],
        recorded_at=hdr[21],
        lines=[_order_line_view(r) for r in lines],
    )


async def list_market_orders(
    conn: RuntimeConnection,
    business: UUID,
    *,
    storefront_id: UUID | None = None,
    basket_id: UUID | None = None,
) -> MarketOrderList:
    await require_module(conn, business, STOREFRONTS_MODULE)
    rows = await (
        await conn.execute(
            "select id from gba.market_orders where tenant_id = %s "
            "and (%s::uuid is null or storefront_id = %s) "
            "and (%s::uuid is null or basket_id = %s) "
            "order by recorded_at desc, order_number, id",
            (business, storefront_id, storefront_id, basket_id, basket_id),
        )
    ).fetchall()
    return MarketOrderList(items=[await get_market_order(conn, business, r[0]) for r in rows])


async def list_operator_fees(
    conn: RuntimeConnection,
    business: UUID,
    *,
    marketplace_id: UUID | None = None,
) -> OperatorFeeList:
    await require_module(conn, business, STOREFRONTS_MODULE)
    rows = await (
        await conn.execute(
            "select id, location_id, marketplace_id, order_id, "
            "seller_counterparty_id, currency, gorgona_commission_minor, operator_fee_minor, "
            "status, recorded_by, recorded_at from gba.market_operator_fees "
            "where tenant_id = %s and (%s::uuid is null or marketplace_id = %s) "
            "order by recorded_at desc, id",
            (business, marketplace_id, marketplace_id),
        )
    ).fetchall()
    return OperatorFeeList(items=[_operator_fee_view(r) for r in rows])


async def checkout_basket(
    conn: RuntimeConnection,
    business: UUID,
    *,
    user_id: UUID,
    actor: str,
    key: str,
    body: BasketCheckoutInput,
) -> BasketCheckoutView:
    """Split a customer basket strictly by seller storefront into independent single-seller
    orders, each issuing its own FIN-03 receivable invoice in the seller's own ledger book.
    """
    _check_ready()
    await require_module(conn, business, STOREFRONTS_MODULE)
    scope = IdempotencyScope(business, actor, "market.basket.checkout", key)
    replay = await commands.claim(
        conn,
        scope,
        commands.fingerprint(body.model_dump(mode="json")),
        BasketCheckoutView,
    )
    if replay is not None:
        return replay

    cp_row = await (
        await conn.execute(
            "select max(revision) from gba.counterparty_versions "
            "where tenant_id = %s and counterparty_id = %s",
            (business, body.customer_counterparty_id),
        )
    ).fetchone()
    curr_row = await (
        await conn.execute(
            "select minor_units from gba.currencies where code = %s",
            (body.currency,),
        )
    ).fetchone()
    if cp_row is None or cp_row[0] is None or curr_row is None:
        raise InvalidReferenceError("Customer counterparty or currency not found")
    cp_rev = int(cp_row[0])
    scale = int(curr_row[0])

    operator_fee_bps = 0
    if body.marketplace_id is not None:
        mp_row = await (
            await conn.execute(
                "select operator_fee_bps, is_active from gba.marketplaces "
                "where tenant_id = %s and location_id = %s and id = %s",
                (business, body.location_id, body.marketplace_id),
            )
        ).fetchone()
        if mp_row is None:
            raise InvalidReferenceError("Marketplace not found in this branch")
        if not mp_row[1]:
            raise MarketStateError("Marketplace is inactive")
        operator_fee_bps = int(mp_row[0])

    cfg_by_sf = {c.storefront_id: c for c in body.seller_configs}

    # Resolve & group listings strictly by (storefront_id, legal_entity_id)
    grouped: dict[tuple[UUID, UUID], list[tuple[UUID, int, int, str]]] = defaultdict(list)
    for item in body.items:
        row = await (
            await conn.execute(
                "select l.storefront_id, l.legal_entity_id, l.price_minor, l.currency, "
                "l.available_quantity, l.moderation_status, l.title, s.is_published "
                "from gba.market_listings l "
                "join gba.market_storefronts s "
                "on s.tenant_id = l.tenant_id and s.id = l.storefront_id "
                "where l.tenant_id = %s and l.location_id = %s and l.id = %s for update of l",
                (business, body.location_id, item.listing_id),
            )
        ).fetchone()
        if row is None:
            raise InvalidReferenceError(f"Listing {item.listing_id} not found in this branch")
        sf_id, le_id, price_minor, lst_curr, avail, mod_status, title, sf_pub = (
            row[0],
            row[1],
            int(row[2]),
            str(row[3]),
            int(row[4]),
            str(row[5]),
            str(row[6]),
            bool(row[7]),
        )
        if not sf_pub or mod_status != "published":
            raise MarketStateError(f"Listing {item.listing_id} is not published")
        if lst_curr != body.currency:
            raise MarketStateError("Listing currency does not match basket currency")
        if avail < item.quantity:
            raise MarketStateError(f"Insufficient available quantity for listing {item.listing_id}")
        if sf_id not in cfg_by_sf:
            raise InvalidReferenceError(f"Seller settlement config missing for storefront {sf_id}")
        grouped[(sf_id, le_id)].append((item.listing_id, item.quantity, price_minor, title))

    basket_id = uuid7()
    created_order_ids: list[UUID] = []

    # Issue one independent FIN-03 receivable invoice per seller storefront
    seller_invoices: dict[tuple[UUID, UUID], tuple[UUID, UUID, UUID, UUID, int, str]] = {}
    for idx, ((sf_id, le_id), items_list) in enumerate(grouped.items(), start=1):
        cfg = cfg_by_sf[sf_id]
        # Verify book belongs to this seller's legal_entity_id (no commingled books!)
        bk_row = await (
            await conn.execute(
                "select legal_entity_id from gba.ledger_books where tenant_id = %s and id = %s",
                (business, cfg.book_id),
            )
        ).fetchone()
        if bk_row is None or bk_row[0] != le_id:
            raise InvalidReferenceError(
                "Seller book_id must belong exclusively to the seller's legal_entity_id"
            )
        total_minor = sum(q * p for _, q, p, _ in items_list)
        order_id = uuid7()
        order_num = f"MKT-{basket_id.hex[-8:].upper()}-S{idx}-{order_id.hex[-6:].upper()}"[:64]
        inv_doc_id = uuid7()
        inv_line_id = uuid7()
        await financial_documents.save_draft(
            conn,
            business_id=business,
            book_id=cfg.book_id,
            document_id=inv_doc_id,
            user_id=user_id,
            actor=actor,
            key=f"mkt-inv-dr-{idx}-{key}"[:120],
            body=InvoiceDraftInput(
                expected_revision=0,
                direction="receivable",
                counterparty_id=body.customer_counterparty_id,
                counterparty_revision=cp_rev,
                currency=body.currency,
                invoice_date=body.order_date,
                due_date=body.order_date,
                control_account_id=cfg.control_account_id,
                title=f"Marketplace order {order_num}",
                number=order_num,
                lines=(
                    InvoiceLineInput(
                        line_id=inv_line_id,
                        counter_account_id=cfg.revenue_account_id,
                        description=f"Single-seller order {order_num} ({len(items_list)} line(s))",
                        amount=from_minor(total_minor, scale),
                    ),
                ),
            ),
        )
        issued = await financial_documents.issue_document(
            conn,
            business_id=business,
            book_id=cfg.book_id,
            document_id=inv_doc_id,
            user_id=user_id,
            actor=actor,
            key=f"mkt-inv-is-{idx}-{key}"[:120],
            body=InvoiceIssueInput(
                expected_revision=1,
                entry_date=body.order_date,
                attestation="confirmed_account_treatment",
            ),
        )
        if issued.obligation_id is None:
            raise MarketStateError("Issued seller invoice did not create an obligation")
        seller_invoices[(sf_id, le_id)] = (
            order_id,
            inv_doc_id,
            inv_line_id,
            issued.obligation_id,
            total_minor,
            order_num,
        )

    async with module_writes(STOREFRONTS_MODULE):
        await conn.execute(
            "insert into gba.market_baskets ("
            "id, tenant_id, location_id, customer_counterparty_id, marketplace_id, "
            "currency, split_order_count, recorded_by"
            ") values (%s, %s, %s, %s, %s, %s, %s, %s)",
            (
                basket_id,
                business,
                body.location_id,
                body.customer_counterparty_id,
                body.marketplace_id,
                body.currency,
                len(grouped),
                user_id,
            ),
        )
        for (sf_id, le_id), items_list in grouped.items():
            cfg = cfg_by_sf[sf_id]
            order_id, inv_doc_id, inv_line_id, obligation_id, total_minor, order_num = (
                seller_invoices[(sf_id, le_id)]
            )
            created_order_ids.append(order_id)
            await conn.execute(
                "insert into gba.market_orders ("
                "id, tenant_id, location_id, basket_id, storefront_id, legal_entity_id, "
                "customer_counterparty_id, marketplace_id, order_number, currency, total_minor, "
                "status, book_id, control_account_id, revenue_account_id, invoice_document_id, "
                "invoice_line_id, obligation_id, revision, recorded_by"
                ") values ("
                "%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 'confirmed', "
                "%s, %s, %s, %s, %s, %s, 1, %s"
                ")",
                (
                    order_id,
                    business,
                    body.location_id,
                    basket_id,
                    sf_id,
                    le_id,
                    body.customer_counterparty_id,
                    body.marketplace_id,
                    order_num,
                    body.currency,
                    total_minor,
                    cfg.book_id,
                    cfg.control_account_id,
                    cfg.revenue_account_id,
                    inv_doc_id,
                    inv_line_id,
                    obligation_id,
                    user_id,
                ),
            )
            for line_no, (listing_id, qty, unit_price, _title) in enumerate(items_list, start=1):
                await conn.execute(
                    "insert into gba.market_order_lines ("
                    "id, tenant_id, location_id, order_id, storefront_id, legal_entity_id, "
                    "line_no, listing_id, quantity, unit_price_minor, line_total_minor"
                    ") values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
                    (
                        uuid7(),
                        business,
                        body.location_id,
                        order_id,
                        sf_id,
                        le_id,
                        line_no,
                        listing_id,
                        qty,
                        unit_price,
                        qty * unit_price,
                    ),
                )
                await conn.execute(
                    "update gba.market_listings set available_quantity = available_quantity - %s "
                    "where tenant_id = %s and id = %s",
                    (qty, business, listing_id),
                )
            if (
                body.marketplace_id is not None
                and operator_fee_bps > 0
                and cfg.seller_counterparty_id is not None
            ):
                fee_minor = (total_minor * operator_fee_bps + 5000) // 10_000
                await conn.execute(
                    "insert into gba.market_operator_fees ("
                    "id, tenant_id, location_id, marketplace_id, order_id, "
                    "seller_counterparty_id, currency, gorgona_commission_minor, "
                    "operator_fee_minor, status, recorded_by"
                    ") values (%s, %s, %s, %s, %s, %s, %s, 0, %s, 'accrued', %s)",
                    (
                        uuid7(),
                        business,
                        body.location_id,
                        body.marketplace_id,
                        order_id,
                        cfg.seller_counterparty_id,
                        body.currency,
                        fee_minor,
                        user_id,
                    ),
                )

        orders = [await get_market_order(conn, business, oid) for oid in created_order_ids]
        view = BasketCheckoutView(
            basket_id=basket_id,
            location_id=body.location_id,
            customer_counterparty_id=body.customer_counterparty_id,
            marketplace_id=body.marketplace_id,
            currency=body.currency,
            split_order_count=len(orders),
            orders=orders,
        )
        await commands.complete(conn, scope, view)
        return view


async def refund_market_order(
    conn: RuntimeConnection,
    business: UUID,
    order_id: UUID,
    *,
    user_id: UUID,
    actor: str,
    key: str,
    body: MarketOrderRefundInput,
) -> MarketOrderView:
    """Create a seller-isolated FIN-03 credit note draft for a customer refund on one order."""
    _check_ready()
    await require_module(conn, business, STOREFRONTS_MODULE)
    scope = IdempotencyScope(business, actor, "market.order.refund", key)
    replay = await commands.claim(
        conn,
        scope,
        commands.fingerprint({"order_id": str(order_id), **body.model_dump(mode="json")}),
        MarketOrderView,
    )
    if replay is not None:
        return replay

    row = await (
        await conn.execute(
            "select order_number, customer_counterparty_id, currency, total_minor, refunded_minor, "
            "book_id, revenue_account_id, invoice_line_id, obligation_id "
            "from gba.market_orders where tenant_id = %s and id = %s for update",
            (business, order_id),
        )
    ).fetchone()
    if row is None:
        raise NotFoundError("Marketplace order not found")
    (
        order_num,
        customer_cp_id,
        currency,
        total_minor,
        already_refunded,
        book_id,
        rev_acct_id,
        inv_line_id,
        obligation_id,
    ) = (
        str(row[0]),
        row[1],
        str(row[2]),
        int(row[3]),
        int(row[4]),
        row[5],
        row[6],
        row[7],
        row[8],
    )
    if already_refunded + body.refund_minor > total_minor:
        raise MarketStateError("Refund exceeds remaining refundable order total")

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

    cn_doc_id = uuid7()
    await credit_notes.save_draft(
        conn,
        business_id=business,
        book_id=book_id,
        document_id=cn_doc_id,
        user_id=user_id,
        actor=actor,
        key=f"mkt-cn-dr-{key}"[:120],
        body=CreditDraftInput(
            expected_revision=0,
            credited_obligation_id=obligation_id,
            counterparty_revision=cp_rev,
            credit_date=body.refund_date,
            due_date=body.refund_date,
            title=f"Marketplace order {order_num} refund",
            number=f"{order_num}-CR-{cn_doc_id.hex[-8:].upper()}"[:64],
            lines=(
                CreditLineInput(
                    line_id=uuid7(),
                    credited_line_id=inv_line_id,
                    counter_account_id=rev_acct_id,
                    description=f"Order {order_num} refund: {body.reason}",
                    amount=from_minor(body.refund_minor, scale),
                ),
            ),
        ),
    )

    next_refunded = already_refunded + body.refund_minor
    next_status = "refunded" if next_refunded == total_minor else "partially_refunded"
    async with module_writes(STOREFRONTS_MODULE):
        await conn.execute(
            "update gba.market_orders set refunded_minor = %s, status = %s, "
            "credit_note_document_id = %s, revision = revision + 1, "
            "recorded_by = %s, recorded_at = now() where tenant_id = %s and id = %s",
            (next_refunded, next_status, cn_doc_id, user_id, business, order_id),
        )
        view = await get_market_order(conn, business, order_id)
        await commands.complete(conn, scope, view)
        return view
