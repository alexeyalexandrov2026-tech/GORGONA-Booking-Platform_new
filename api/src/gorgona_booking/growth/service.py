"""Universal growth settings and smart waitlist service (all 39 industries, FORCE RLS)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from decimal import ROUND_HALF_UP, Decimal
from typing import Any, Literal
from uuid import UUID

from psycopg import AsyncConnection
from psycopg.rows import dict_row

from gorgona_booking.notifications.service import (
    dispatch_notification,
    enqueue_notification,
    validate_and_mask_recipient,
)

AssistantTone = Literal["warm_professional", "concise_direct", "executive_hospitality"]
PreferredWindow = Literal["any", "morning", "afternoon", "evening"]
WaitlistStatus = Literal["waiting", "offered", "booked", "expired", "cancelled"]

# The platform is US-only: every unit-economics figure is whole US cents.
UNIT_ECONOMICS_CURRENCY: Literal["USD"] = "USD"
UNIT_ECONOMICS_WINDOW_DAYS = 30


@dataclass(frozen=True)
class GrowthSettingsRecord:
    tenant_id: UUID
    google_review_url: str | None
    reminder_hours_before: int
    review_delay_hours: int
    rebooking_days_after: int
    waitlist_auto_offer: bool
    ai_assistant_enabled: bool
    ai_assistant_tone: str
    updated_at: datetime | None


@dataclass(frozen=True)
class WaitlistEntryRecord:
    id: UUID
    tenant_id: UUID
    location_id: UUID
    location_name: str
    variant_id: UUID
    variant_name: str
    service_name: str
    price_cents: int
    currency: str
    preferred_resource_id: UUID | None
    preferred_day: date
    preferred_window: str
    customer_name: str
    contact_channel: str
    contact_masked: str
    notes: str
    status: str
    offered_at: datetime | None
    offer_notification_id: UUID | None
    created_at: datetime


@dataclass(frozen=True)
class UnitEconomicsRecord:
    """Live trailing-window unit economics of one business, in whole US cents."""

    tenant_id: UUID
    window_days: int
    currency: Literal["USD"]
    bookings_count_30d: int
    gross_revenue_cents: int
    average_ticket_cents: int
    material_cogs_cents: int
    net_margin_cents: int
    margin_percent: float


def _default_growth_settings(tenant_id: UUID) -> GrowthSettingsRecord:
    return GrowthSettingsRecord(
        tenant_id=tenant_id,
        google_review_url=None,
        reminder_hours_before=24,
        review_delay_hours=2,
        rebooking_days_after=28,
        waitlist_auto_offer=True,
        ai_assistant_enabled=True,
        ai_assistant_tone="warm_professional",
        updated_at=None,
    )


def _row_to_settings(row: dict[str, Any]) -> GrowthSettingsRecord:
    return GrowthSettingsRecord(
        tenant_id=row["tenant_id"],
        google_review_url=row["google_review_url"],
        reminder_hours_before=int(row["reminder_hours_before"]),
        review_delay_hours=int(row["review_delay_hours"]),
        rebooking_days_after=int(row["rebooking_days_after"]),
        waitlist_auto_offer=bool(row["waitlist_auto_offer"]),
        ai_assistant_enabled=bool(row["ai_assistant_enabled"]),
        ai_assistant_tone=str(row["ai_assistant_tone"]),
        updated_at=row["updated_at"],
    )


def _row_to_waitlist(row: dict[str, Any]) -> WaitlistEntryRecord:
    return WaitlistEntryRecord(
        id=row["id"],
        tenant_id=row["tenant_id"],
        location_id=row["location_id"],
        location_name=str(row.get("location_name") or ""),
        variant_id=row["variant_id"],
        variant_name=str(row.get("variant_name") or ""),
        service_name=str(row.get("service_name") or ""),
        price_cents=int(row.get("price_cents") or 0),
        currency=str(row.get("currency") or "USD"),
        preferred_resource_id=row["preferred_resource_id"],
        preferred_day=row["preferred_day"],
        preferred_window=str(row["preferred_window"]),
        customer_name=str(row["customer_name"]),
        contact_channel=str(row["contact_channel"]),
        contact_masked=str(row["contact_masked"]),
        notes=str(row["notes"]),
        status=str(row["status"]),
        offered_at=row["offered_at"],
        offer_notification_id=row["offer_notification_id"],
        created_at=row["created_at"],
    )


async def get_growth_settings(
    conn: AsyncConnection[Any], *, tenant_id: UUID
) -> GrowthSettingsRecord:
    async with conn.cursor(row_factory=dict_row) as cur:
        await cur.execute(
            "SELECT * FROM gba.growth_settings WHERE tenant_id = %s",
            (tenant_id,),
        )
        row = await cur.fetchone()
    if row is None:
        return _default_growth_settings(tenant_id)
    return _row_to_settings(row)


async def upsert_growth_settings(
    conn: AsyncConnection[Any],
    *,
    tenant_id: UUID,
    google_review_url: str | None,
    reminder_hours_before: int,
    review_delay_hours: int,
    rebooking_days_after: int,
    waitlist_auto_offer: bool,
    ai_assistant_enabled: bool,
    ai_assistant_tone: str,
    updated_by_user_id: UUID | None,
) -> GrowthSettingsRecord:
    clean_url = google_review_url.strip() if google_review_url else None
    if clean_url == "":
        clean_url = None
    if clean_url is not None and not clean_url.startswith("https://"):
        raise ValueError("google_review_url must start with https://")
    async with conn.cursor(row_factory=dict_row) as cur:
        await cur.execute(
            """
            INSERT INTO gba.growth_settings (
                tenant_id, google_review_url, reminder_hours_before, review_delay_hours,
                rebooking_days_after, waitlist_auto_offer, ai_assistant_enabled,
                ai_assistant_tone, updated_by_user_id, updated_at
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, now())
            ON CONFLICT (tenant_id) DO UPDATE SET
                google_review_url = EXCLUDED.google_review_url,
                reminder_hours_before = EXCLUDED.reminder_hours_before,
                review_delay_hours = EXCLUDED.review_delay_hours,
                rebooking_days_after = EXCLUDED.rebooking_days_after,
                waitlist_auto_offer = EXCLUDED.waitlist_auto_offer,
                ai_assistant_enabled = EXCLUDED.ai_assistant_enabled,
                ai_assistant_tone = EXCLUDED.ai_assistant_tone,
                updated_by_user_id = EXCLUDED.updated_by_user_id,
                updated_at = now()
            RETURNING *
            """,
            (
                tenant_id,
                clean_url,
                reminder_hours_before,
                review_delay_hours,
                rebooking_days_after,
                waitlist_auto_offer,
                ai_assistant_enabled,
                ai_assistant_tone,
                updated_by_user_id,
            ),
        )
        row = await cur.fetchone()
    if row is None:
        raise RuntimeError("Failed to persist growth settings")
    return _row_to_settings(row)


async def join_waitlist(
    conn: AsyncConnection[Any],
    *,
    tenant_id: UUID,
    location_id: UUID,
    variant_id: UUID,
    preferred_resource_id: UUID | None,
    preferred_day: date,
    preferred_window: str,
    customer_name: str,
    contact_channel: str,
    contact_value: str,
    notes: str = "",
) -> WaitlistEntryRecord:
    masked, contact_hash = validate_and_mask_recipient(contact_channel, contact_value)
    clean_name = customer_name.strip()
    if not clean_name or any(ord(c) < 32 for c in clean_name):
        raise ValueError("Customer name must be non-empty without control characters")
    async with conn.cursor(row_factory=dict_row) as cur:
        await cur.execute(
            """
            SELECT l.name AS location_name, v.name AS variant_name, s.name AS service_name,
                   v.price_cents, v.currency
            FROM gba.locations l
            JOIN gba.service_variants v ON v.tenant_id = l.tenant_id AND v.id = %s
            JOIN gba.services s ON s.tenant_id = v.tenant_id AND s.id = v.service_id
            WHERE l.tenant_id = %s AND l.id = %s
              AND v.status = 'published' AND v.is_bookable
            """,
            (variant_id, tenant_id, location_id),
        )
        meta = await cur.fetchone()
        if meta is None:
            raise LookupError("Location or bookable service not found for this business")
        if preferred_resource_id is not None:
            await cur.execute(
                "SELECT 1 FROM gba.resources WHERE tenant_id = %s AND id = %s AND is_active",
                (tenant_id, preferred_resource_id),
            )
            if await cur.fetchone() is None:
                raise LookupError("Preferred specialist/resource not found")
        await cur.execute(
            """
            INSERT INTO gba.waitlist_entries (
                tenant_id, location_id, variant_id, preferred_resource_id,
                preferred_day, preferred_window, customer_name,
                contact_channel, contact_masked, contact_hash, notes
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING *
            """,
            (
                tenant_id,
                location_id,
                variant_id,
                preferred_resource_id,
                preferred_day,
                preferred_window,
                clean_name,
                contact_channel,
                masked,
                contact_hash,
                notes.strip()[:400],
            ),
        )
        inserted = await cur.fetchone()
    if inserted is None:
        raise RuntimeError("Failed to create waitlist entry")
    return _row_to_waitlist({**inserted, **meta})


async def list_waitlist(
    conn: AsyncConnection[Any],
    *,
    tenant_id: UUID,
    status_filter: str | None = None,
    limit: int = 50,
) -> list[WaitlistEntryRecord]:
    async with conn.cursor(row_factory=dict_row) as cur:
        await cur.execute(
            """
            SELECT w.*,
                   l.name AS location_name,
                   v.name AS variant_name,
                   s.name AS service_name,
                   v.price_cents,
                   v.currency
            FROM gba.waitlist_entries w
            JOIN gba.locations l ON l.tenant_id = w.tenant_id AND l.id = w.location_id
            JOIN gba.service_variants v ON v.tenant_id = w.tenant_id AND v.id = w.variant_id
            JOIN gba.services s ON s.tenant_id = v.tenant_id AND s.id = v.service_id
            WHERE w.tenant_id = %s
              AND (%s::text IS NULL OR w.status = %s)
            ORDER BY
                CASE w.status WHEN 'waiting' THEN 0 WHEN 'offered' THEN 1 ELSE 2 END,
                w.preferred_day ASC,
                w.created_at ASC
            LIMIT %s
            """,
            (tenant_id, status_filter, status_filter, max(1, min(limit, 200))),
        )
        rows = await cur.fetchall()
    return [_row_to_waitlist(r) for r in rows]


async def update_waitlist_status(
    conn: AsyncConnection[Any],
    *,
    tenant_id: UUID,
    entry_id: UUID,
    new_status: WaitlistStatus,
) -> WaitlistEntryRecord:
    async with conn.cursor(row_factory=dict_row) as cur:
        await cur.execute(
            """
            UPDATE gba.waitlist_entries w
            SET status = %s,
                updated_at = now()
            WHERE w.tenant_id = %s AND w.id = %s
            RETURNING w.*
            """,
            (new_status, tenant_id, entry_id),
        )
        updated = await cur.fetchone()
        if updated is None:
            raise LookupError("Waitlist entry not found")
        await cur.execute(
            """
            SELECT l.name AS location_name, v.name AS variant_name, s.name AS service_name,
                   v.price_cents, v.currency
            FROM gba.locations l
            JOIN gba.service_variants v ON v.tenant_id = l.tenant_id AND v.id = %s
            JOIN gba.services s ON s.tenant_id = v.tenant_id AND s.id = v.service_id
            WHERE l.tenant_id = %s AND l.id = %s
            """,
            (updated["variant_id"], tenant_id, updated["location_id"]),
        )
        meta = await cur.fetchone() or {}
    return _row_to_waitlist({**updated, **meta})


async def offer_waitlist_slot(
    conn: AsyncConnection[Any],
    *,
    tenant_id: UUID,
    entry_id: UUID,
    recipient: str,
    starts_at: str,
    business_name: str,
    action_url: str,
    created_by_user_id: UUID | None,
) -> tuple[WaitlistEntryRecord, UUID]:
    async with conn.cursor(row_factory=dict_row) as cur:
        await cur.execute(
            """
            SELECT w.*,
                   l.name AS location_name,
                   v.name AS variant_name,
                   s.name AS service_name,
                   v.price_cents,
                   v.currency
            FROM gba.waitlist_entries w
            JOIN gba.locations l ON l.tenant_id = w.tenant_id AND l.id = w.location_id
            JOIN gba.service_variants v ON v.tenant_id = w.tenant_id AND v.id = w.variant_id
            JOIN gba.services s ON s.tenant_id = v.tenant_id AND s.id = v.service_id
            WHERE w.tenant_id = %s AND w.id = %s
            FOR UPDATE OF w
            """,
            (tenant_id, entry_id),
        )
        row = await cur.fetchone()
        if row is None:
            raise LookupError("Waitlist entry not found")
        _, expected_hash = validate_and_mask_recipient(row["contact_channel"], recipient)
        if expected_hash != row["contact_hash"]:
            raise ValueError("Recipient does not match the customer's registered waitlist contact")

        notif = await enqueue_notification(
            conn,
            tenant_id=tenant_id,
            channel=row["contact_channel"],
            template_code="waitlist_slot_available",
            recipient=recipient,
            variables={
                "business_name": business_name,
                "service_name": f"{row['service_name']} — {row['variant_name']}",
                "starts_at": starts_at,
                "action_url": action_url,
            },
            idempotency_key=f"waitlist-offer-{entry_id}-{starts_at[:16]}",
            created_by_user_id=created_by_user_id,
        )
        notif = await dispatch_notification(
            conn,
            tenant_id=tenant_id,
            notification_id=notif.id,
            recipient=recipient,
        )
        await cur.execute(
            """
            UPDATE gba.waitlist_entries
            SET status = 'offered',
                offered_at = now(),
                offer_notification_id = %s,
                updated_at = now()
            WHERE tenant_id = %s AND id = %s
            RETURNING *
            """,
            (notif.id, tenant_id, entry_id),
        )
        updated = await cur.fetchone()
    if updated is None:
        raise RuntimeError("Failed to mark waitlist entry as offered")
    merged = {
        **updated,
        "location_name": row["location_name"],
        "variant_name": row["variant_name"],
        "service_name": row["service_name"],
        "price_cents": row["price_cents"],
        "currency": row["currency"],
    }
    return _row_to_waitlist(merged), notif.id


def build_unit_economics(
    *,
    tenant_id: UUID,
    bookings_count: int,
    gross_revenue_cents: int,
    material_cogs_cents: int,
    window_days: int = UNIT_ECONOMICS_WINDOW_DAYS,
) -> UnitEconomicsRecord:
    """Derive margin and average ticket from the two live sums (whole cents, no float money)."""
    net_margin_cents = gross_revenue_cents - material_cogs_cents
    if gross_revenue_cents > 0:
        percent = (Decimal(net_margin_cents) * 100 / Decimal(gross_revenue_cents)).quantize(
            Decimal("0.1"), rounding=ROUND_HALF_UP
        )
        # `or 0.0` turns a negative zero (a margin that rounds to -0.0) into plain 0.0.
        margin_percent = float(percent) or 0.0
    else:
        margin_percent = 0.0
    if bookings_count > 0:
        # Half-up integer division: the ticket stays in whole cents.
        average_ticket_cents = (2 * gross_revenue_cents + bookings_count) // (2 * bookings_count)
    else:
        average_ticket_cents = 0
    return UnitEconomicsRecord(
        tenant_id=tenant_id,
        window_days=window_days,
        currency=UNIT_ECONOMICS_CURRENCY,
        bookings_count_30d=bookings_count,
        gross_revenue_cents=gross_revenue_cents,
        average_ticket_cents=average_ticket_cents,
        material_cogs_cents=material_cogs_cents,
        net_margin_cents=net_margin_cents,
        margin_percent=margin_percent,
    )


async def get_unit_economics(conn: AsyncConnection[Any], *, tenant_id: UUID) -> UnitEconomicsRecord:
    """Trailing-30-day revenue, material cost and margin, read live from PostgreSQL.

    Revenue is every CONFIRMED booking that started inside the window (a booking in the
    future is not yet earned, so the window is closed at now()). Material cost is what left
    inventory through write-offs (used, damaged, lost, expired, other) at the moving-average
    value; returns to a supplier also move stock out but are not a cost, so they are left out.
    Amounts of stock valuations are visible to company-wide members only (restrictive RLS), and
    the route requires such a member. Every statement filters by tenant on top of FORCE RLS.
    """
    async with conn.cursor(row_factory=dict_row) as cur:
        await cur.execute(
            """
            SELECT count(*) AS bookings_count,
                   coalesce(sum(total_cents), 0) AS gross_revenue_cents
            FROM gba.bookings
            WHERE tenant_id = %s
              AND status = 'CONFIRMED'
              AND starts_at >= now() - (%s::int * interval '1 day')
              AND starts_at < now()
            """,
            (tenant_id, UNIT_ECONOMICS_WINDOW_DAYS),
        )
        revenue = await cur.fetchone()
        await cur.execute(
            """
            SELECT coalesce(sum(v.amount_minor), 0) AS material_cogs_cents
            FROM gba.stock_valuations v
            JOIN gba.stock_documents d
              ON d.tenant_id = v.tenant_id AND d.id = v.document_id
            WHERE v.tenant_id = %s
              AND v.direction = 'out'
              AND d.kind = 'write_off'
              AND d.document_date >= current_date - %s::int
            """,
            (tenant_id, UNIT_ECONOMICS_WINDOW_DAYS),
        )
        cogs = await cur.fetchone()
    if revenue is None or cogs is None:
        raise RuntimeError("Failed to read unit economics")
    return build_unit_economics(
        tenant_id=tenant_id,
        bookings_count=int(revenue["bookings_count"]),
        gross_revenue_cents=int(revenue["gross_revenue_cents"]),
        material_cogs_cents=int(cogs["material_cogs_cents"]),
    )
