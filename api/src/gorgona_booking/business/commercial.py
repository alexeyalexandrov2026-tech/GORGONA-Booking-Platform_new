"""AMARKAL v2.10.0 Deal-to-Cash B2B Engine: CPQ Quotes, Purchase Orders & 3-Way Match,
Approval Workflows, and Tokenized External B2B Portal (FORCE RLS, zero SECURITY DEFINER).
"""

from __future__ import annotations

import hashlib
import json
import secrets
from datetime import UTC, date, datetime, timedelta
from typing import Any, Literal
from uuid import UUID, uuid7

from psycopg.rows import dict_row
from pydantic import BaseModel, ConfigDict, Field

from gorgona_booking.db.pool import RuntimeConnection

PaymentTerms = Literal["Due on receipt", "Net 15", "Net 30", "Net 45", "Net 60"]
QuoteStatus = Literal[
    "draft",
    "pending_approval",
    "approved",
    "sent",
    "accepted",
    "declined",
    "converted",
    "void",
]
PurchaseOrderStatus = Literal[
    "draft",
    "pending_approval",
    "approved",
    "issued",
    "acknowledged",
    "partially_received",
    "received",
    "matched",
    "cancelled",
]
ThreeWayMatchStatus = Literal["unmatched", "variance", "matched"]
PolicyEntityKind = Literal["quote", "purchase_order"]

DEFAULT_APPROVAL_THRESHOLD_CENTS = 250_000  # $2,500.00 USD
THREE_WAY_TOLERANCE_CENTS = 100  # $1.00 rounding tolerance


class QuoteLineInput(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    description: str = Field(min_length=1, max_length=240)
    sku: str | None = Field(default=None, max_length=64)
    quantity: int = Field(ge=1, le=100_000)
    unit_price_cents: int = Field(ge=0, le=99_999_999)


class QuoteLineItem(BaseModel):
    model_config = ConfigDict(frozen=True)
    description: str
    sku: str | None = None
    quantity: int
    unit_price_cents: int
    line_total_cents: int


class CreateQuoteRequest(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    quote_number: str | None = Field(default=None, max_length=48)
    title: str = Field(min_length=2, max_length=200)
    counterparty_id: UUID | None = None
    counterparty_name: str = Field(min_length=1, max_length=160)
    counterparty_email: str | None = Field(default=None, max_length=160)
    items: list[QuoteLineInput] = Field(min_length=1, max_length=100)
    discount_cents: int = Field(default=0, ge=0, le=99_999_999)
    tax_rate_bps: int = Field(default=0, ge=0, le=2500)
    payment_terms: PaymentTerms = "Net 30"
    valid_until: date | None = None
    notes: str = Field(default="", max_length=2000)


class QuoteView(BaseModel):
    model_config = ConfigDict(frozen=True)
    id: UUID
    quote_number: str
    title: str
    counterparty_id: UUID | None
    counterparty_name: str
    counterparty_email: str | None
    currency: Literal["USD"]
    items: list[QuoteLineItem]
    subtotal_cents: int
    discount_cents: int
    tax_cents: int
    total_cents: int
    payment_terms: PaymentTerms
    valid_until: date | None
    notes: str
    status: QuoteStatus
    approval_required: bool
    approved_at: datetime | None
    accepted_by_name: str | None
    accepted_at: datetime | None
    declined_reason: str | None
    payment_session_id: UUID | None
    converted_invoice_ref: str | None
    created_at: datetime
    updated_at: datetime


class PurchaseOrderLineInput(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    description: str = Field(min_length=1, max_length=240)
    sku: str | None = Field(default=None, max_length=64)
    quantity_ordered: int = Field(ge=1, le=100_000)
    unit_cost_cents: int = Field(ge=0, le=99_999_999)


class PurchaseOrderLineItem(BaseModel):
    model_config = ConfigDict(frozen=True)
    description: str
    sku: str | None = None
    quantity_ordered: int
    quantity_received: int
    unit_cost_cents: int
    line_total_cents: int


class CreatePurchaseOrderRequest(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    po_number: str | None = Field(default=None, max_length=48)
    title: str = Field(min_length=2, max_length=200)
    vendor_counterparty_id: UUID | None = None
    vendor_name: str = Field(min_length=1, max_length=160)
    vendor_email: str | None = Field(default=None, max_length=160)
    items: list[PurchaseOrderLineInput] = Field(min_length=1, max_length=100)
    payment_terms: PaymentTerms = "Net 30"
    expected_delivery_date: date | None = None
    notes: str = Field(default="", max_length=2000)


class RecordReceiptRequest(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    received_quantities: list[int] = Field(min_length=1, max_length=100)


class MatchVendorBillRequest(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    vendor_bill_number: str = Field(min_length=1, max_length=80)
    vendor_bill_cents: int = Field(ge=0, le=99_999_999)


class PurchaseOrderView(BaseModel):
    model_config = ConfigDict(frozen=True)
    id: UUID
    po_number: str
    title: str
    vendor_counterparty_id: UUID | None
    vendor_name: str
    vendor_email: str | None
    currency: Literal["USD"]
    items: list[PurchaseOrderLineItem]
    total_cents: int
    payment_terms: PaymentTerms
    expected_delivery_date: date | None
    notes: str
    status: PurchaseOrderStatus
    received_total_cents: int
    vendor_bill_number: str | None
    vendor_bill_cents: int | None
    three_way_match_status: ThreeWayMatchStatus
    variance_cents: int
    approval_required: bool
    approved_at: datetime | None
    vendor_acknowledged_by: str | None
    vendor_acknowledged_at: datetime | None
    created_at: datetime
    updated_at: datetime


class ApprovalPolicyView(BaseModel):
    model_config = ConfigDict(frozen=True)
    entity_kind: PolicyEntityKind
    threshold_cents: int
    require_owner_above_threshold: bool
    auto_approve_below_threshold: bool
    updated_at: datetime | None = None


class UpdateApprovalPolicyRequest(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    threshold_cents: int = Field(ge=0, le=99_999_999)
    require_owner_above_threshold: bool = True
    auto_approve_below_threshold: bool = True


class PortalShareResponse(BaseModel):
    model_config = ConfigDict(frozen=True)
    entity_kind: PolicyEntityKind
    entity_id: UUID
    portal_url: str
    token_prefix: str
    expires_at: datetime


class CommercialSummaryView(BaseModel):
    model_config = ConfigDict(frozen=True)
    currency: Literal["USD"]
    quotes_open_count: int
    quotes_pipeline_cents: int
    quotes_accepted_count: int
    quotes_accepted_cents: int
    quotes_pending_approval_count: int
    po_open_count: int
    po_committed_cents: int
    po_pending_approval_count: int
    po_matched_count: int
    po_variance_count: int


class PortalPublicDocument(BaseModel):
    model_config = ConfigDict(frozen=True)
    entity_kind: PolicyEntityKind
    business_name: str
    expires_at: datetime
    responded_at: datetime | None
    quote: QuoteView | None = None
    purchase_order: PurchaseOrderView | None = None
    checkout_url: str | None = None


class PortalRespondRequest(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    action: Literal["accept", "decline", "acknowledge"]
    actor_name: str = Field(min_length=2, max_length=160)
    reason: str | None = Field(default=None, max_length=500)


class CommercialError(Exception):
    def __init__(self, code: str, message: str, *, status_code: int = 400) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code


def calculate_quote_totals(
    items: list[QuoteLineInput],
    *,
    discount_cents: int = 0,
    tax_rate_bps: int = 0,
) -> tuple[list[QuoteLineItem], int, int, int, int]:
    """Compute exact integer USD cent totals for a B2B quote."""
    lines: list[QuoteLineItem] = []
    subtotal = 0
    for item in items:
        line_total = item.quantity * item.unit_price_cents
        subtotal += line_total
        lines.append(
            QuoteLineItem(
                description=item.description.strip(),
                sku=item.sku.strip() if item.sku else None,
                quantity=item.quantity,
                unit_price_cents=item.unit_price_cents,
                line_total_cents=line_total,
            )
        )
    applied_discount = min(max(0, discount_cents), subtotal)
    taxable = subtotal - applied_discount
    tax_cents = (taxable * max(0, tax_rate_bps) + 5000) // 10_000
    total = taxable + tax_cents
    return lines, subtotal, applied_discount, tax_cents, total


def evaluate_approval_requirement(
    total_cents: int,
    *,
    threshold_cents: int,
    auto_approve_below_threshold: bool,
) -> bool:
    """Return True if the commercial document requires explicit approval before sending/issuing."""
    if total_cents > threshold_cents:
        return True
    return not auto_approve_below_threshold


def evaluate_three_way_match(
    *,
    po_total_cents: int,
    received_total_cents: int,
    vendor_bill_cents: int | None,
    tolerance_cents: int = THREE_WAY_TOLERANCE_CENTS,
) -> tuple[ThreeWayMatchStatus, int]:
    """Compare Purchase Order total, Goods Receipt total, and Vendor Bill total."""
    if vendor_bill_cents is None:
        return ("unmatched", 0)
    # Variance is measured against received goods once received, otherwise against PO total.
    baseline = received_total_cents if received_total_cents > 0 else po_total_cents
    variance = vendor_bill_cents - baseline
    if (
        received_total_cents > 0
        and abs(vendor_bill_cents - received_total_cents) <= tolerance_cents
        and abs(vendor_bill_cents - po_total_cents) <= tolerance_cents
    ):
        return ("matched", variance)
    return ("variance", variance)


def generate_portal_token() -> tuple[str, str, str]:
    """Return (raw_token, token_prefix, sha256_hex) for an external B2B portal link."""
    raw = f"amk_ptl_{secrets.token_urlsafe(24)}"
    prefix = raw[:14]
    return raw, prefix, hash_portal_token(raw)


def hash_portal_token(raw_token: str) -> str:
    return hashlib.sha256(raw_token.strip().encode("utf-8")).hexdigest()


def _parse_quote_row(row: dict[str, Any]) -> QuoteView:
    raw_items = row.get("items") or []
    items = [QuoteLineItem.model_validate(i) for i in raw_items]
    return QuoteView(
        id=row["id"],
        quote_number=str(row["quote_number"]),
        title=str(row["title"]),
        counterparty_id=row["counterparty_id"],
        counterparty_name=str(row["counterparty_name"]),
        counterparty_email=row["counterparty_email"],
        currency="USD",
        items=items,
        subtotal_cents=int(row["subtotal_cents"]),
        discount_cents=int(row["discount_cents"]),
        tax_cents=int(row["tax_cents"]),
        total_cents=int(row["total_cents"]),
        payment_terms=row["payment_terms"],
        valid_until=row["valid_until"],
        notes=str(row["notes"] or ""),
        status=row["status"],
        approval_required=bool(row["approval_required"]),
        approved_at=row["approved_at"],
        accepted_by_name=row["accepted_by_name"],
        accepted_at=row["accepted_at"],
        declined_reason=row["declined_reason"],
        payment_session_id=row["payment_session_id"],
        converted_invoice_ref=row["converted_invoice_ref"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


def _parse_po_row(row: dict[str, Any]) -> PurchaseOrderView:
    raw_items = row.get("items") or []
    items = [PurchaseOrderLineItem.model_validate(i) for i in raw_items]
    return PurchaseOrderView(
        id=row["id"],
        po_number=str(row["po_number"]),
        title=str(row["title"]),
        vendor_counterparty_id=row["vendor_counterparty_id"],
        vendor_name=str(row["vendor_name"]),
        vendor_email=row["vendor_email"],
        currency="USD",
        items=items,
        total_cents=int(row["total_cents"]),
        payment_terms=row["payment_terms"],
        expected_delivery_date=row["expected_delivery_date"],
        notes=str(row["notes"] or ""),
        status=row["status"],
        received_total_cents=int(row["received_total_cents"]),
        vendor_bill_number=row["vendor_bill_number"],
        vendor_bill_cents=(
            int(row["vendor_bill_cents"]) if row["vendor_bill_cents"] is not None else None
        ),
        three_way_match_status=row["three_way_match_status"],
        variance_cents=int(row["variance_cents"]),
        approval_required=bool(row["approval_required"]),
        approved_at=row["approved_at"],
        vendor_acknowledged_by=row["vendor_acknowledged_by"],
        vendor_acknowledged_at=row["vendor_acknowledged_at"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


async def load_approval_policy(
    conn: RuntimeConnection, *, tenant_id: UUID, entity_kind: PolicyEntityKind
) -> ApprovalPolicyView:
    async with conn.cursor(row_factory=dict_row) as cur:
        await cur.execute(
            """
            SELECT entity_kind, threshold_cents, require_owner_above_threshold,
                   auto_approve_below_threshold, updated_at
            FROM gba.approval_policies
            WHERE tenant_id = %s AND entity_kind = %s
            """,
            (tenant_id, entity_kind),
        )
        row = await cur.fetchone()
    if row is None:
        return ApprovalPolicyView(
            entity_kind=entity_kind,
            threshold_cents=DEFAULT_APPROVAL_THRESHOLD_CENTS,
            require_owner_above_threshold=True,
            auto_approve_below_threshold=True,
            updated_at=None,
        )
    return ApprovalPolicyView(
        entity_kind=row["entity_kind"],
        threshold_cents=int(row["threshold_cents"]),
        require_owner_above_threshold=bool(row["require_owner_above_threshold"]),
        auto_approve_below_threshold=bool(row["auto_approve_below_threshold"]),
        updated_at=row["updated_at"],
    )


async def list_approval_policies(
    conn: RuntimeConnection, *, tenant_id: UUID
) -> list[ApprovalPolicyView]:
    quote_pol = await load_approval_policy(conn, tenant_id=tenant_id, entity_kind="quote")
    po_pol = await load_approval_policy(conn, tenant_id=tenant_id, entity_kind="purchase_order")
    return [quote_pol, po_pol]


async def upsert_approval_policy(
    conn: RuntimeConnection,
    *,
    tenant_id: UUID,
    entity_kind: PolicyEntityKind,
    body: UpdateApprovalPolicyRequest,
    user_id: UUID | None,
) -> ApprovalPolicyView:
    async with conn.cursor(row_factory=dict_row) as cur:
        await cur.execute(
            """
            INSERT INTO gba.approval_policies (
                tenant_id, entity_kind, threshold_cents,
                require_owner_above_threshold, auto_approve_below_threshold,
                updated_by_user_id, updated_at
            )
            VALUES (%s, %s, %s, %s, %s, %s, now())
            ON CONFLICT (tenant_id, entity_kind) DO UPDATE SET
                threshold_cents = EXCLUDED.threshold_cents,
                require_owner_above_threshold = EXCLUDED.require_owner_above_threshold,
                auto_approve_below_threshold = EXCLUDED.auto_approve_below_threshold,
                updated_by_user_id = EXCLUDED.updated_by_user_id,
                updated_at = now()
            RETURNING entity_kind, threshold_cents, require_owner_above_threshold,
                      auto_approve_below_threshold, updated_at
            """,
            (
                tenant_id,
                entity_kind,
                body.threshold_cents,
                body.require_owner_above_threshold,
                body.auto_approve_below_threshold,
                user_id,
            ),
        )
        row = await cur.fetchone()
    if row is None:
        raise RuntimeError("approval policy upsert returned no row")
    return ApprovalPolicyView(
        entity_kind=row["entity_kind"],
        threshold_cents=int(row["threshold_cents"]),
        require_owner_above_threshold=bool(row["require_owner_above_threshold"]),
        auto_approve_below_threshold=bool(row["auto_approve_below_threshold"]),
        updated_at=row["updated_at"],
    )


async def get_commercial_summary(
    conn: RuntimeConnection, *, tenant_id: UUID
) -> CommercialSummaryView:
    async with conn.cursor(row_factory=dict_row) as cur:
        await cur.execute(
            """
            SELECT
                count(*) FILTER (
                    WHERE status IN ('draft', 'pending_approval', 'approved', 'sent')
                ) AS quotes_open_count,
                coalesce(sum(total_cents) FILTER (
                    WHERE status IN ('draft', 'pending_approval', 'approved', 'sent')
                ), 0) AS quotes_pipeline_cents,
                count(*) FILTER (
                    WHERE status IN ('accepted', 'converted')
                ) AS quotes_accepted_count,
                coalesce(sum(total_cents) FILTER (
                    WHERE status IN ('accepted', 'converted')
                ), 0) AS quotes_accepted_cents,
                count(*) FILTER (
                    WHERE status = 'pending_approval'
                ) AS quotes_pending_approval_count
            FROM gba.commercial_quotes
            WHERE tenant_id = %s
            """,
            (tenant_id,),
        )
        q = await cur.fetchone()
        await cur.execute(
            """
            SELECT
                count(*) FILTER (
                    WHERE status IN (
                        'draft', 'pending_approval', 'approved',
                        'issued', 'acknowledged', 'partially_received', 'received'
                    )
                ) AS po_open_count,
                coalesce(sum(total_cents) FILTER (
                    WHERE status NOT IN ('cancelled')
                ), 0) AS po_committed_cents,
                count(*) FILTER (WHERE status = 'pending_approval') AS po_pending_approval_count,
                count(*) FILTER (WHERE three_way_match_status = 'matched') AS po_matched_count,
                count(*) FILTER (WHERE three_way_match_status = 'variance') AS po_variance_count
            FROM gba.purchase_orders
            WHERE tenant_id = %s
            """,
            (tenant_id,),
        )
        p = await cur.fetchone()
    if q is None or p is None:
        raise RuntimeError("commercial summary aggregate returned no row")
    return CommercialSummaryView(
        currency="USD",
        quotes_open_count=int(q["quotes_open_count"]),
        quotes_pipeline_cents=int(q["quotes_pipeline_cents"]),
        quotes_accepted_count=int(q["quotes_accepted_count"]),
        quotes_accepted_cents=int(q["quotes_accepted_cents"]),
        quotes_pending_approval_count=int(q["quotes_pending_approval_count"]),
        po_open_count=int(p["po_open_count"]),
        po_committed_cents=int(p["po_committed_cents"]),
        po_pending_approval_count=int(p["po_pending_approval_count"]),
        po_matched_count=int(p["po_matched_count"]),
        po_variance_count=int(p["po_variance_count"]),
    )


async def list_quotes(
    conn: RuntimeConnection, *, tenant_id: UUID, limit: int = 50
) -> list[QuoteView]:
    lim = max(1, min(limit, 100))
    async with conn.cursor(row_factory=dict_row) as cur:
        await cur.execute(
            """
            SELECT * FROM gba.commercial_quotes
            WHERE tenant_id = %s
            ORDER BY created_at DESC
            LIMIT %s
            """,
            (tenant_id, lim),
        )
        rows = await cur.fetchall()
    return [_parse_quote_row(r) for r in rows]


async def create_quote(
    conn: RuntimeConnection,
    *,
    tenant_id: UUID,
    body: CreateQuoteRequest,
    user_id: UUID | None,
) -> QuoteView:
    lines, subtotal, discount, tax, total = calculate_quote_totals(
        body.items, discount_cents=body.discount_cents, tax_rate_bps=body.tax_rate_bps
    )
    policy = await load_approval_policy(conn, tenant_id=tenant_id, entity_kind="quote")
    needs_approval = evaluate_approval_requirement(
        total,
        threshold_cents=policy.threshold_cents,
        auto_approve_below_threshold=policy.auto_approve_below_threshold,
    )
    initial_status: QuoteStatus = "pending_approval" if needs_approval else "approved"
    qid = uuid7()
    number = (body.quote_number or "").strip() or f"Q-{str(qid)[-6:].upper()}"
    async with conn.cursor(row_factory=dict_row) as cur:
        await cur.execute(
            """
            INSERT INTO gba.commercial_quotes (
                id, tenant_id, quote_number, title, counterparty_id,
                counterparty_name, counterparty_email, currency, items,
                subtotal_cents, discount_cents, tax_cents, total_cents,
                payment_terms, valid_until, notes, status,
                approval_required, approved_by_user_id, approved_at,
                created_by_user_id
            )
            VALUES (
                %s, %s, %s, %s, %s,
                %s, %s, 'USD', %s::jsonb,
                %s, %s, %s, %s,
                %s, %s, %s, %s,
                %s, %s, %s,
                %s
            )
            RETURNING *
            """,
            (
                qid,
                tenant_id,
                number,
                body.title.strip(),
                body.counterparty_id,
                body.counterparty_name.strip(),
                body.counterparty_email.strip() if body.counterparty_email else None,
                json.dumps([line.model_dump() for line in lines]),
                subtotal,
                discount,
                tax,
                total,
                body.payment_terms,
                body.valid_until,
                body.notes.strip(),
                initial_status,
                needs_approval,
                None if needs_approval else user_id,
                None if needs_approval else datetime.now(UTC),
                user_id,
            ),
        )
        row = await cur.fetchone()
    if row is None:
        raise RuntimeError("quote insert returned no row")
    return _parse_quote_row(row)


async def approve_quote(
    conn: RuntimeConnection,
    *,
    tenant_id: UUID,
    quote_id: UUID,
    user_id: UUID | None,
) -> QuoteView:
    async with conn.cursor(row_factory=dict_row) as cur:
        await cur.execute(
            """
            UPDATE gba.commercial_quotes
            SET status = 'approved',
                approved_by_user_id = %s,
                approved_at = now(),
                updated_at = now()
            WHERE tenant_id = %s
              AND id = %s
              AND status IN ('draft', 'pending_approval')
            RETURNING *
            """,
            (user_id, tenant_id, quote_id),
        )
        row = await cur.fetchone()
    if row is None:
        raise CommercialError(
            "QUOTE_NOT_APPROVABLE",
            "Quote not found or is already past the approval stage.",
            status_code=409,
        )
    return _parse_quote_row(row)


async def create_portal_share_link(
    conn: RuntimeConnection,
    *,
    tenant_id: UUID,
    entity_kind: PolicyEntityKind,
    entity_id: UUID,
    base_url: str,
    user_id: UUID | None,
    ttl_days: int = 30,
) -> PortalShareResponse:
    table = "gba.commercial_quotes" if entity_kind == "quote" else "gba.purchase_orders"
    async with conn.cursor(row_factory=dict_row) as cur:
        await cur.execute(
            f"SELECT * FROM {table} WHERE tenant_id = %s AND id = %s",  # noqa: S608
            (tenant_id, entity_id),
        )
        doc = await cur.fetchone()
        if doc is None:
            raise CommercialError("NOT_FOUND", f"{entity_kind} not found.", status_code=404)
        if doc["status"] in ("draft", "pending_approval"):
            raise CommercialError(
                "APPROVAL_REQUIRED",
                "Approve this document before sharing it on the B2B portal.",
                status_code=409,
            )
        if entity_kind == "quote" and doc["status"] == "approved":
            await cur.execute(
                """
                UPDATE gba.commercial_quotes
                SET status = 'sent', updated_at = now()
                WHERE tenant_id = %s AND id = %s
                """,
                (tenant_id, entity_id),
            )
        elif entity_kind == "purchase_order" and doc["status"] == "approved":
            await cur.execute(
                """
                UPDATE gba.purchase_orders
                SET status = 'issued', updated_at = now()
                WHERE tenant_id = %s AND id = %s
                """,
                (tenant_id, entity_id),
            )

        raw_token, prefix, token_hash = generate_portal_token()
        expires_at = datetime.now(UTC) + timedelta(days=max(1, min(ttl_days, 90)))
        recipient_name = (
            str(doc["counterparty_name"]) if entity_kind == "quote" else str(doc["vendor_name"])
        )
        recipient_email = (
            doc["counterparty_email"] if entity_kind == "quote" else doc["vendor_email"]
        )
        await cur.execute(
            """
            INSERT INTO gba.b2b_portal_links (
                tenant_id, entity_kind, entity_id, token_prefix, token_hash,
                recipient_name, recipient_email, expires_at, created_by_user_id
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                tenant_id,
                entity_kind,
                entity_id,
                prefix,
                token_hash,
                recipient_name,
                recipient_email,
                expires_at,
                user_id,
            ),
        )
    return PortalShareResponse(
        entity_kind=entity_kind,
        entity_id=entity_id,
        portal_url=f"{base_url.rstrip('/')}/portal/?token={raw_token}",
        token_prefix=prefix,
        expires_at=expires_at,
    )


async def list_purchase_orders(
    conn: RuntimeConnection, *, tenant_id: UUID, limit: int = 50
) -> list[PurchaseOrderView]:
    lim = max(1, min(limit, 100))
    async with conn.cursor(row_factory=dict_row) as cur:
        await cur.execute(
            """
            SELECT * FROM gba.purchase_orders
            WHERE tenant_id = %s
            ORDER BY created_at DESC
            LIMIT %s
            """,
            (tenant_id, lim),
        )
        rows = await cur.fetchall()
    return [_parse_po_row(r) for r in rows]


async def create_purchase_order(
    conn: RuntimeConnection,
    *,
    tenant_id: UUID,
    body: CreatePurchaseOrderRequest,
    user_id: UUID | None,
) -> PurchaseOrderView:
    lines: list[PurchaseOrderLineItem] = []
    total_cents = 0
    for item in body.items:
        line_total = item.quantity_ordered * item.unit_cost_cents
        total_cents += line_total
        lines.append(
            PurchaseOrderLineItem(
                description=item.description.strip(),
                sku=item.sku.strip() if item.sku else None,
                quantity_ordered=item.quantity_ordered,
                quantity_received=0,
                unit_cost_cents=item.unit_cost_cents,
                line_total_cents=line_total,
            )
        )
    policy = await load_approval_policy(conn, tenant_id=tenant_id, entity_kind="purchase_order")
    needs_approval = evaluate_approval_requirement(
        total_cents,
        threshold_cents=policy.threshold_cents,
        auto_approve_below_threshold=policy.auto_approve_below_threshold,
    )
    initial_status: PurchaseOrderStatus = "pending_approval" if needs_approval else "approved"
    poid = uuid7()
    number = (body.po_number or "").strip() or f"PO-{str(poid)[-6:].upper()}"
    async with conn.cursor(row_factory=dict_row) as cur:
        await cur.execute(
            """
            INSERT INTO gba.purchase_orders (
                id, tenant_id, po_number, title, vendor_counterparty_id,
                vendor_name, vendor_email, currency, items, total_cents,
                payment_terms, expected_delivery_date, notes, status,
                approval_required, approved_by_user_id, approved_at,
                created_by_user_id
            )
            VALUES (
                %s, %s, %s, %s, %s,
                %s, %s, 'USD', %s::jsonb, %s,
                %s, %s, %s, %s,
                %s, %s, %s,
                %s
            )
            RETURNING *
            """,
            (
                poid,
                tenant_id,
                number,
                body.title.strip(),
                body.vendor_counterparty_id,
                body.vendor_name.strip(),
                body.vendor_email.strip() if body.vendor_email else None,
                json.dumps([line.model_dump() for line in lines]),
                total_cents,
                body.payment_terms,
                body.expected_delivery_date,
                body.notes.strip(),
                initial_status,
                needs_approval,
                None if needs_approval else user_id,
                None if needs_approval else datetime.now(UTC),
                user_id,
            ),
        )
        row = await cur.fetchone()
    if row is None:
        raise RuntimeError("purchase order insert returned no row")
    return _parse_po_row(row)


async def approve_purchase_order(
    conn: RuntimeConnection,
    *,
    tenant_id: UUID,
    po_id: UUID,
    user_id: UUID | None,
) -> PurchaseOrderView:
    async with conn.cursor(row_factory=dict_row) as cur:
        await cur.execute(
            """
            UPDATE gba.purchase_orders
            SET status = 'approved',
                approved_by_user_id = %s,
                approved_at = now(),
                updated_at = now()
            WHERE tenant_id = %s
              AND id = %s
              AND status IN ('draft', 'pending_approval')
            RETURNING *
            """,
            (user_id, tenant_id, po_id),
        )
        row = await cur.fetchone()
    if row is None:
        raise CommercialError(
            "PO_NOT_APPROVABLE",
            "Purchase order not found or already approved.",
            status_code=409,
        )
    return _parse_po_row(row)


async def record_po_receipt(
    conn: RuntimeConnection,
    *,
    tenant_id: UUID,
    po_id: UUID,
    body: RecordReceiptRequest,
) -> PurchaseOrderView:
    async with conn.cursor(row_factory=dict_row) as cur:
        await cur.execute(
            "SELECT * FROM gba.purchase_orders WHERE tenant_id = %s AND id = %s FOR UPDATE",
            (tenant_id, po_id),
        )
        row = await cur.fetchone()
        if row is None:
            raise CommercialError("PO_NOT_FOUND", "Purchase order not found.", status_code=404)
        po = _parse_po_row(row)
        if len(body.received_quantities) != len(po.items):
            raise CommercialError(
                "RECEIPT_LINE_MISMATCH",
                "Provide received quantity for every PO line item.",
                status_code=400,
            )
        updated_items: list[PurchaseOrderLineItem] = []
        received_total = 0
        all_received = True
        for item, qty in zip(po.items, body.received_quantities, strict=True):
            if qty < 0 or qty > item.quantity_ordered * 2:
                raise CommercialError(
                    "INVALID_QUANTITY",
                    "Received quantity is out of range.",
                    status_code=400,
                )
            if qty < item.quantity_ordered:
                all_received = False
            received_total += qty * item.unit_cost_cents
            updated_items.append(
                PurchaseOrderLineItem(
                    description=item.description,
                    sku=item.sku,
                    quantity_ordered=item.quantity_ordered,
                    quantity_received=qty,
                    unit_cost_cents=item.unit_cost_cents,
                    line_total_cents=item.line_total_cents,
                )
            )
        match_status, variance = evaluate_three_way_match(
            po_total_cents=po.total_cents,
            received_total_cents=received_total,
            vendor_bill_cents=po.vendor_bill_cents,
        )
        next_status: PurchaseOrderStatus = (
            "matched"
            if match_status == "matched"
            else ("received" if all_received else "partially_received")
        )
        await cur.execute(
            """
            UPDATE gba.purchase_orders
            SET items = %s::jsonb,
                received_total_cents = %s,
                three_way_match_status = %s,
                variance_cents = %s,
                status = %s,
                updated_at = now()
            WHERE tenant_id = %s AND id = %s
            RETURNING *
            """,
            (
                json.dumps([i.model_dump() for i in updated_items]),
                received_total,
                match_status,
                variance,
                next_status,
                tenant_id,
                po_id,
            ),
        )
        updated = await cur.fetchone()
    if updated is None:
        raise RuntimeError("purchase order update returned no row")
    return _parse_po_row(updated)


async def match_po_vendor_bill(
    conn: RuntimeConnection,
    *,
    tenant_id: UUID,
    po_id: UUID,
    body: MatchVendorBillRequest,
) -> PurchaseOrderView:
    async with conn.cursor(row_factory=dict_row) as cur:
        await cur.execute(
            "SELECT * FROM gba.purchase_orders WHERE tenant_id = %s AND id = %s FOR UPDATE",
            (tenant_id, po_id),
        )
        row = await cur.fetchone()
        if row is None:
            raise CommercialError("PO_NOT_FOUND", "Purchase order not found.", status_code=404)
        po = _parse_po_row(row)
        match_status, variance = evaluate_three_way_match(
            po_total_cents=po.total_cents,
            received_total_cents=po.received_total_cents,
            vendor_bill_cents=body.vendor_bill_cents,
        )
        next_status: PurchaseOrderStatus = "matched" if match_status == "matched" else po.status
        await cur.execute(
            """
            UPDATE gba.purchase_orders
            SET vendor_bill_number = %s,
                vendor_bill_cents = %s,
                three_way_match_status = %s,
                variance_cents = %s,
                status = %s,
                updated_at = now()
            WHERE tenant_id = %s AND id = %s
            RETURNING *
            """,
            (
                body.vendor_bill_number.strip(),
                body.vendor_bill_cents,
                match_status,
                variance,
                next_status,
                tenant_id,
                po_id,
            ),
        )
        updated = await cur.fetchone()
    if updated is None:
        raise RuntimeError("purchase order update returned no row")
    return _parse_po_row(updated)


async def resolve_portal_token(conn: RuntimeConnection, *, raw_token: str) -> dict[str, Any] | None:
    """Resolve one active, unexpired B2B portal token strictly under FORCE RLS."""
    token_hash = hash_portal_token(raw_token)
    async with conn.cursor(row_factory=dict_row) as cur:
        await cur.execute("SELECT set_config('gba.portal_token_hash', %s, true)", (token_hash,))
        await cur.execute(
            """
            SELECT id, tenant_id, entity_kind, entity_id, expires_at, responded_at
            FROM gba.b2b_portal_links
            WHERE token_hash = %s
              AND revoked_at IS NULL
              AND expires_at > now()
            LIMIT 1
            """,
            (token_hash,),
        )
        return await cur.fetchone()
