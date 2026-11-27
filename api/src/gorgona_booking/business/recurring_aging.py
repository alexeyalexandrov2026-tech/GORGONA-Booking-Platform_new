"""AMARKAL v2.12.0 B2B Financial Automation: Recurring Retainers / Schedules,
AR/AP Aging Analytics, and CPA-Ready CSV Journal Export (FORCE RLS).
"""

from __future__ import annotations

import calendar
import csv
import io
from datetime import UTC, date, datetime, timedelta
from typing import Any, Literal
from uuid import UUID, uuid7

from psycopg.rows import dict_row
from pydantic import BaseModel, ConfigDict, Field

from gorgona_booking.business.commercial import (
    CommercialError,
    CreateQuoteRequest,
    PaymentTerms,
    QuoteLineInput,
    QuoteView,
    create_quote,
)
from gorgona_booking.db.pool import RuntimeConnection

BillingCadence = Literal["weekly", "biweekly", "monthly", "quarterly", "annual"]
RecurringStatus = Literal["active", "paused", "completed", "cancelled"]
AgingBucket = Literal["current", "1_30", "31_60", "61_90", "90_plus"]


class CreateRecurringScheduleRequest(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    schedule_code: str | None = Field(default=None, max_length=48)
    title: str = Field(min_length=2, max_length=200)
    counterparty_id: UUID | None = None
    counterparty_name: str = Field(min_length=1, max_length=160)
    counterparty_email: str | None = Field(default=None, max_length=160)
    amount_cents: int = Field(ge=50, le=99_999_999)
    cadence: BillingCadence = "monthly"
    payment_terms: PaymentTerms = "Net 30"
    next_run_date: date
    auto_email_client: bool = True
    notes: str = Field(default="", max_length=2000)


class RecurringScheduleView(BaseModel):
    model_config = ConfigDict(frozen=True)
    id: UUID
    schedule_code: str
    title: str
    counterparty_id: UUID | None
    counterparty_name: str
    counterparty_email: str | None
    currency: Literal["USD"]
    amount_cents: int
    cadence: BillingCadence
    payment_terms: PaymentTerms
    next_run_date: date
    last_run_at: datetime | None
    runs_count: int
    auto_email_client: bool
    status: RecurringStatus
    notes: str
    created_at: datetime
    updated_at: datetime


class RecurringRunResult(BaseModel):
    model_config = ConfigDict(frozen=True)
    schedule: RecurringScheduleView
    generated_quote: QuoteView
    email_status: str | None = None
    portal_url: str | None = None


class AgingBucketsSummary(BaseModel):
    model_config = ConfigDict(frozen=True)
    current_cents: int = 0
    days_1_30_cents: int = 0
    days_31_60_cents: int = 0
    days_61_90_cents: int = 0
    days_90_plus_cents: int = 0
    total_cents: int = 0
    open_count: int = 0


class AgingItemView(BaseModel):
    model_config = ConfigDict(frozen=True)
    side: Literal["AR", "AP"]
    doc_type: str
    reference_number: str
    counterparty_name: str
    status: str
    issued_date: date
    due_date: date
    days_past_due: int
    bucket: AgingBucket
    amount_cents: int


class AgingReportView(BaseModel):
    model_config = ConfigDict(frozen=True)
    currency: Literal["USD"]
    as_of: date
    ar: AgingBucketsSummary
    ap: AgingBucketsSummary
    items: list[AgingItemView]


def payment_terms_days(terms: str) -> int:
    mapping = {
        "Due on receipt": 0,
        "Net 15": 15,
        "Net 30": 30,
        "Net 45": 45,
        "Net 60": 60,
    }
    return mapping.get(terms, 30)


def _add_months(d: date, months: int) -> date:
    total_months = (d.year * 12 + (d.month - 1)) + months
    year, zero_month = divmod(total_months, 12)
    month = zero_month + 1
    last_day = calendar.monthrange(year, month)[1]
    return date(year, month, min(d.day, last_day))


def advance_run_date(current: date, cadence: BillingCadence) -> date:
    """Compute the next billing run date with exact calendar month clamping."""
    if cadence == "weekly":
        return current + timedelta(days=7)
    if cadence == "biweekly":
        return current + timedelta(days=14)
    if cadence == "monthly":
        return _add_months(current, 1)
    if cadence == "quarterly":
        return _add_months(current, 3)
    return _add_months(current, 12)


def classify_aging_bucket(due_date: date, *, as_of: date) -> tuple[AgingBucket, int]:
    """Return (bucket, days_past_due) relative to as_of."""
    delta = (as_of - due_date).days
    if delta <= 0:
        return ("current", 0)
    if delta <= 30:
        return ("1_30", delta)
    if delta <= 60:
        return ("31_60", delta)
    if delta <= 90:
        return ("61_90", delta)
    return ("90_plus", delta)


def summarize_aging_items(
    items: list[AgingItemView], side: Literal["AR", "AP"]
) -> AgingBucketsSummary:
    cur = d30 = d60 = d90 = d90p = total = count = 0
    for item in items:
        if item.side != side:
            continue
        count += 1
        total += item.amount_cents
        if item.bucket == "current":
            cur += item.amount_cents
        elif item.bucket == "1_30":
            d30 += item.amount_cents
        elif item.bucket == "31_60":
            d60 += item.amount_cents
        elif item.bucket == "61_90":
            d90 += item.amount_cents
        else:
            d90p += item.amount_cents
    return AgingBucketsSummary(
        current_cents=cur,
        days_1_30_cents=d30,
        days_31_60_cents=d60,
        days_61_90_cents=d90,
        days_90_plus_cents=d90p,
        total_cents=total,
        open_count=count,
    )


def render_cpa_aging_csv(items: list[AgingItemView]) -> str:
    """Render a clean, US CPA-ready CSV (QuickBooks/Xero/Excel compatible)."""
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(
        [
            "Side",
            "DocumentType",
            "ReferenceNumber",
            "Counterparty",
            "Status",
            "IssuedDate",
            "DueDate",
            "DaysPastDue",
            "AgingBucket",
            "AmountUSD",
            "Currency",
        ]
    )
    for item in items:
        writer.writerow(
            [
                item.side,
                item.doc_type,
                item.reference_number,
                item.counterparty_name,
                item.status,
                item.issued_date.isoformat(),
                item.due_date.isoformat(),
                item.days_past_due,
                item.bucket,
                f"{item.amount_cents / 100:.2f}",
                "USD",
            ]
        )
    return buf.getvalue()


def _parse_schedule(row: dict[str, Any]) -> RecurringScheduleView:
    return RecurringScheduleView(
        id=row["id"],
        schedule_code=str(row["schedule_code"]),
        title=str(row["title"]),
        counterparty_id=row["counterparty_id"],
        counterparty_name=str(row["counterparty_name"]),
        counterparty_email=row["counterparty_email"],
        currency="USD",
        amount_cents=int(row["amount_cents"]),
        cadence=row["cadence"],
        payment_terms=row["payment_terms"],
        next_run_date=row["next_run_date"],
        last_run_at=row["last_run_at"],
        runs_count=int(row["runs_count"]),
        auto_email_client=bool(row["auto_email_client"]),
        status=row["status"],
        notes=str(row["notes"] or ""),
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


async def list_recurring_schedules(
    conn: RuntimeConnection, *, tenant_id: UUID, limit: int = 50
) -> list[RecurringScheduleView]:
    lim = max(1, min(limit, 100))
    async with conn.cursor(row_factory=dict_row) as cur:
        await cur.execute(
            """
            SELECT * FROM gba.recurring_schedules
            WHERE tenant_id = %s
            ORDER BY next_run_date ASC, created_at DESC
            LIMIT %s
            """,
            (tenant_id, lim),
        )
        rows = await cur.fetchall()
    return [_parse_schedule(r) for r in rows]


async def create_recurring_schedule(
    conn: RuntimeConnection,
    *,
    tenant_id: UUID,
    body: CreateRecurringScheduleRequest,
    user_id: UUID | None,
) -> RecurringScheduleView:
    sid = uuid7()
    code = (body.schedule_code or "").strip() or f"REC-{str(sid)[-6:].upper()}"
    async with conn.cursor(row_factory=dict_row) as cur:
        await cur.execute(
            """
            INSERT INTO gba.recurring_schedules (
                id, tenant_id, schedule_code, title, counterparty_id,
                counterparty_name, counterparty_email, currency, amount_cents,
                cadence, payment_terms, next_run_date, auto_email_client,
                status, notes, created_by_user_id
            )
            VALUES (
                %s, %s, %s, %s, %s,
                %s, %s, 'USD', %s,
                %s, %s, %s, %s,
                'active', %s, %s
            )
            RETURNING *
            """,
            (
                sid,
                tenant_id,
                code,
                body.title.strip(),
                body.counterparty_id,
                body.counterparty_name.strip(),
                body.counterparty_email.strip() if body.counterparty_email else None,
                body.amount_cents,
                body.cadence,
                body.payment_terms,
                body.next_run_date,
                body.auto_email_client,
                body.notes.strip(),
                user_id,
            ),
        )
        row = await cur.fetchone()
    if row is None:
        raise RuntimeError("recurring schedule insert returned no row")
    return _parse_schedule(row)


async def toggle_recurring_schedule(
    conn: RuntimeConnection, *, tenant_id: UUID, schedule_id: UUID
) -> RecurringScheduleView:
    async with conn.cursor(row_factory=dict_row) as cur:
        await cur.execute(
            """
            UPDATE gba.recurring_schedules
            SET status = CASE WHEN status = 'active' THEN 'paused' ELSE 'active' END,
                updated_at = now()
            WHERE tenant_id = %s
              AND id = %s
              AND status IN ('active', 'paused')
            RETURNING *
            """,
            (tenant_id, schedule_id),
        )
        row = await cur.fetchone()
    if row is None:
        raise CommercialError(
            "SCHEDULE_NOT_FOUND", "Recurring schedule not found or closed.", status_code=404
        )
    return _parse_schedule(row)


async def execute_recurring_cycle(
    conn: RuntimeConnection,
    *,
    tenant_id: UUID,
    schedule_id: UUID,
    user_id: UUID | None,
) -> tuple[RecurringScheduleView, QuoteView]:
    async with conn.cursor(row_factory=dict_row) as cur:
        await cur.execute(
            "SELECT * FROM gba.recurring_schedules WHERE tenant_id = %s AND id = %s FOR UPDATE",
            (tenant_id, schedule_id),
        )
        row = await cur.fetchone()
        if row is None:
            raise CommercialError(
                "SCHEDULE_NOT_FOUND", "Recurring schedule not found.", status_code=404
            )
        sched = _parse_schedule(row)
        if sched.status != "active":
            raise CommercialError(
                "SCHEDULE_NOT_ACTIVE",
                "Resume this recurring schedule before running a billing cycle.",
                status_code=409,
            )

        next_num = f"{sched.schedule_code}-C{sched.runs_count + 1:02d}"
        generated_quote = await create_quote(
            conn,
            tenant_id=tenant_id,
            body=CreateQuoteRequest(
                quote_number=next_num,
                title=f"{sched.title} ({sched.next_run_date.isoformat()})",
                counterparty_id=sched.counterparty_id,
                counterparty_name=sched.counterparty_name,
                counterparty_email=sched.counterparty_email,
                items=[
                    QuoteLineInput(
                        description=f"{sched.title} — {sched.cadence} retainer",
                        sku=sched.schedule_code,
                        quantity=1,
                        unit_price_cents=sched.amount_cents,
                    )
                ],
                payment_terms=sched.payment_terms,
                valid_until=sched.next_run_date
                + timedelta(days=max(7, payment_terms_days(sched.payment_terms))),
                notes=sched.notes,
            ),
            user_id=user_id,
        )
        next_date = advance_run_date(sched.next_run_date, sched.cadence)
        await cur.execute(
            """
            UPDATE gba.recurring_schedules
            SET next_run_date = %s,
                last_run_at = now(),
                runs_count = runs_count + 1,
                updated_at = now()
            WHERE tenant_id = %s AND id = %s
            RETURNING *
            """,
            (next_date, tenant_id, schedule_id),
        )
        updated = await cur.fetchone()
    if updated is None:
        raise RuntimeError("recurring schedule update returned no row")
    return _parse_schedule(updated), generated_quote


async def build_tenant_aging_report(
    conn: RuntimeConnection, *, tenant_id: UUID, as_of: date | None = None
) -> AgingReportView:
    today = as_of or datetime.now(UTC).date()
    items: list[AgingItemView] = []

    async with conn.cursor(row_factory=dict_row) as cur:
        # AR: open / sent / accepted quotes awaiting settlement
        await cur.execute(
            """
            SELECT quote_number, counterparty_name, status, payment_terms,
                   total_cents, created_at
            FROM gba.commercial_quotes
            WHERE tenant_id = %s
              AND status IN ('approved', 'sent', 'accepted')
            ORDER BY created_at ASC
            LIMIT 250
            """,
            (tenant_id,),
        )
        for r in await cur.fetchall():
            issued = r["created_at"].date()
            due = issued + timedelta(days=payment_terms_days(str(r["payment_terms"])))
            bucket, past_due = classify_aging_bucket(due, as_of=today)
            items.append(
                AgingItemView(
                    side="AR",
                    doc_type="Commercial Quote",
                    reference_number=str(r["quote_number"]),
                    counterparty_name=str(r["counterparty_name"]),
                    status=str(r["status"]),
                    issued_date=issued,
                    due_date=due,
                    days_past_due=past_due,
                    bucket=bucket,
                    amount_cents=int(r["total_cents"]),
                )
            )

        # AR: open Stripe payment sessions
        await cur.execute(
            """
            SELECT coalesce(reference_id, left(provider_session_id, 18)) AS ref_no,
                   coalesce(nullif(customer_name, ''), description) AS party_name,
                   status, amount_cents, created_at
            FROM gba.payment_sessions
            WHERE tenant_id = %s
              AND status = 'open'
            ORDER BY created_at ASC
            LIMIT 250
            """,
            (tenant_id,),
        )
        for r in await cur.fetchall():
            issued = r["created_at"].date()
            due = issued + timedelta(days=15)
            bucket, past_due = classify_aging_bucket(due, as_of=today)
            items.append(
                AgingItemView(
                    side="AR",
                    doc_type="Stripe Payment Link",
                    reference_number=str(r["ref_no"]),
                    counterparty_name=str(r["party_name"]),
                    status=str(r["status"]),
                    issued_date=issued,
                    due_date=due,
                    days_past_due=past_due,
                    bucket=bucket,
                    amount_cents=int(r["amount_cents"]),
                )
            )

        # AP: issued / acknowledged / received / matched purchase orders
        await cur.execute(
            """
            SELECT po_number, vendor_name, status, payment_terms,
                   coalesce(vendor_bill_cents, total_cents) AS payable_cents,
                   created_at
            FROM gba.purchase_orders
            WHERE tenant_id = %s
              AND status IN (
                  'approved', 'issued', 'acknowledged',
                  'partially_received', 'received', 'matched'
              )
            ORDER BY created_at ASC
            LIMIT 250
            """,
            (tenant_id,),
        )
        for r in await cur.fetchall():
            issued = r["created_at"].date()
            due = issued + timedelta(days=payment_terms_days(str(r["payment_terms"])))
            bucket, past_due = classify_aging_bucket(due, as_of=today)
            items.append(
                AgingItemView(
                    side="AP",
                    doc_type="Purchase Order",
                    reference_number=str(r["po_number"]),
                    counterparty_name=str(r["vendor_name"]),
                    status=str(r["status"]),
                    issued_date=issued,
                    due_date=due,
                    days_past_due=past_due,
                    bucket=bucket,
                    amount_cents=int(r["payable_cents"]),
                )
            )

    return AgingReportView(
        currency="USD",
        as_of=today,
        ar=summarize_aging_items(items, "AR"),
        ap=summarize_aging_items(items, "AP"),
        items=items,
    )
