"""Global tenant-isolated B2B record search across core and financial modules."""

from __future__ import annotations

from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Query, Request
from psycopg.rows import dict_row
from pydantic import BaseModel, ConfigDict

from gorgona_booking.api.businesses import CurrentPrincipal
from gorgona_booking.api.deps import runtime_pool
from gorgona_booking.api.request_id import get_request_id
from gorgona_booking.auth.permissions import Permission
from gorgona_booking.db.pool import RuntimeConnection
from gorgona_booking.tenancy.authorization import authorized_tenant

router = APIRouter(tags=["search"])

SearchHitKind = Literal[
    "counterparty",
    "document",
    "invoice",
    "service",
    "payment",
    "quote",
    "purchase_order",
    "mrp_material",
    "eam_asset",
    "inbox_thread",
    "payroll_profile",
    "fx_entry",
]


class SearchHit(BaseModel):
    model_config = ConfigDict(frozen=True)
    kind: SearchHitKind
    id: str
    title: str
    subtitle: str
    path: str
    status: str | None = None


class BusinessSearchResponse(BaseModel):
    model_config = ConfigDict(frozen=True)
    query: str
    total: int
    hits: list[SearchHit]


def escape_like_pattern(raw: str) -> str:
    escaped = raw.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{escaped}%"


async def search_business_records(
    conn: RuntimeConnection,
    *,
    tenant_id: UUID,
    query: str,
    limit_per_kind: int = 5,
) -> list[SearchHit]:
    clean = query.strip()
    if len(clean) < 2:
        return []
    pattern = escape_like_pattern(clean)
    lim = max(1, min(limit_per_kind, 10))
    hits: list[SearchHit] = []

    async with conn.cursor(row_factory=dict_row) as cur:
        # 1. Counterparties (latest version per counterparty)
        await cur.execute(
            """
            SELECT sub.id, sub.display_name, sub.legal_name, sub.email, sub.state
            FROM (
                SELECT DISTINCT ON (c.id)
                    c.id, v.display_name, v.legal_name, v.email, v.state
                FROM gba.counterparties c
                JOIN gba.counterparty_versions v
                  ON v.tenant_id = c.tenant_id AND v.counterparty_id = c.id
                WHERE c.tenant_id = %s
                ORDER BY c.id, v.revision DESC
            ) sub
            WHERE sub.state != 'merged'
              AND (
                  sub.display_name ILIKE %s ESCAPE '\\'
                  OR coalesce(sub.legal_name, '') ILIKE %s ESCAPE '\\'
                  OR coalesce(sub.email, '') ILIKE %s ESCAPE '\\'
              )
            ORDER BY sub.display_name ASC
            LIMIT %s
            """,
            (tenant_id, pattern, pattern, pattern, lim),
        )
        for row in await cur.fetchall():
            subtitle_parts = [p for p in (row["legal_name"], row["email"]) if p]
            hits.append(
                SearchHit(
                    kind="counterparty",
                    id=str(row["id"]),
                    title=str(row["display_name"]),
                    subtitle=" · ".join(str(p) for p in subtitle_parts) or "Counterparty",
                    path="/counterparties/",
                    status=str(row["state"]),
                )
            )

        # 2. Documents (latest version per document)
        await cur.execute(
            """
            SELECT sub.id, sub.title, sub.category, sub.archived
            FROM (
                SELECT DISTINCT ON (d.id)
                    d.id, v.title, v.category, v.archived
                FROM gba.documents d
                JOIN gba.document_versions v
                  ON v.tenant_id = d.tenant_id AND v.document_id = d.id
                WHERE d.tenant_id = %s
                ORDER BY d.id, v.revision DESC
            ) sub
            WHERE sub.title ILIKE %s ESCAPE '\\'
               OR sub.category ILIKE %s ESCAPE '\\'
            ORDER BY sub.title ASC
            LIMIT %s
            """,
            (tenant_id, pattern, pattern, lim),
        )
        for row in await cur.fetchall():
            hits.append(
                SearchHit(
                    kind="document",
                    id=str(row["id"]),
                    title=str(row["title"]),
                    subtitle=f"Document · {row['category']}",
                    path="/documents/",
                    status="archived" if row["archived"] else "active",
                )
            )

        # 3. FIN-03 Financial documents (latest version)
        await cur.execute(
            """
            SELECT sub.document_id, sub.number, sub.title, sub.direction,
                   sub.state, sub.currency, sub.principal_minor
            FROM (
                SELECT DISTINCT ON (v.book_id, v.document_id)
                    v.document_id, v.number, v.title, v.direction,
                    v.state, v.currency, v.principal_minor
                FROM gba.financial_document_versions v
                WHERE v.tenant_id = %s
                ORDER BY v.book_id, v.document_id, v.revision DESC
            ) sub
            WHERE sub.number ILIKE %s ESCAPE '\\'
               OR sub.title ILIKE %s ESCAPE '\\'
            ORDER BY sub.number ASC
            LIMIT %s
            """,
            (tenant_id, pattern, pattern, lim),
        )
        for row in await cur.fetchall():
            amt = int(row["principal_minor"]) / 100
            hits.append(
                SearchHit(
                    kind="invoice",
                    id=str(row["document_id"]),
                    title=f"{row['number']} · {row['title']}",
                    subtitle=f"FIN-03 {row['direction']} · {row['currency']} {amt:,.2f}",
                    path="/finance/",
                    status=str(row["state"]),
                )
            )

        # 4. Catalog services & variants
        await cur.execute(
            """
            SELECT s.id, s.code, s.name,
                   coalesce(min(v.price_cents), 0) AS min_price_cents,
                   coalesce(min(v.currency), 'USD') AS currency
            FROM gba.services s
            LEFT JOIN gba.service_variants v
              ON v.tenant_id = s.tenant_id AND v.service_id = s.id
            WHERE s.tenant_id = %s
              AND (
                  s.name ILIKE %s ESCAPE '\\'
                  OR s.code ILIKE %s ESCAPE '\\'
              )
            GROUP BY s.id, s.code, s.name
            ORDER BY s.name ASC
            LIMIT %s
            """,
            (tenant_id, pattern, pattern, lim),
        )
        for row in await cur.fetchall():
            amt = int(row["min_price_cents"]) / 100
            hits.append(
                SearchHit(
                    kind="service",
                    id=str(row["id"]),
                    title=str(row["name"]),
                    subtitle=f"Catalog {row['code']} · {row['currency']} {amt:,.2f}",
                    path="/services/",
                )
            )

        # 5. Stripe payment sessions
        await cur.execute(
            """
            SELECT id, description, customer_name, reference_id, status, amount_cents, currency
            FROM gba.payment_sessions
            WHERE tenant_id = %s
              AND (
                  description ILIKE %s ESCAPE '\\'
                  OR coalesce(customer_name, '') ILIKE %s ESCAPE '\\'
                  OR coalesce(reference_id, '') ILIKE %s ESCAPE '\\'
              )
            ORDER BY created_at DESC
            LIMIT %s
            """,
            (tenant_id, pattern, pattern, pattern, lim),
        )
        for row in await cur.fetchall():
            amt = int(row["amount_cents"]) / 100
            ref = f" · #{row['reference_id']}" if row["reference_id"] else ""
            hits.append(
                SearchHit(
                    kind="payment",
                    id=str(row["id"]),
                    title=str(row["description"]),
                    subtitle=f"Stripe {row['currency']} {amt:,.2f}{ref}",
                    path="/integrations/",
                    status=str(row["status"]),
                )
            )

        # 6. Commercial Quotes (CPQ)
        await cur.execute(
            """
            SELECT id, quote_number, title, counterparty_name, total_cents, status
            FROM gba.commercial_quotes
            WHERE tenant_id = %s
              AND (
                  quote_number ILIKE %s ESCAPE '\\'
                  OR title ILIKE %s ESCAPE '\\'
                  OR counterparty_name ILIKE %s ESCAPE '\\'
              )
            ORDER BY created_at DESC
            LIMIT %s
            """,
            (tenant_id, pattern, pattern, pattern, lim),
        )
        for row in await cur.fetchall():
            amt = int(row["total_cents"]) / 100
            hits.append(
                SearchHit(
                    kind="quote",
                    id=str(row["id"]),
                    title=f"{row['quote_number']} · {row['title']}",
                    subtitle=f"{row['counterparty_name']} · USD {amt:,.2f}",
                    path="/commercial/",
                    status=str(row["status"]),
                )
            )

        # 7. Purchase Orders (Procurement & 3-Way Match)
        await cur.execute(
            """
            SELECT id, po_number, title, vendor_name, total_cents, status, three_way_match_status
            FROM gba.purchase_orders
            WHERE tenant_id = %s
              AND (
                  po_number ILIKE %s ESCAPE '\\'
                  OR title ILIKE %s ESCAPE '\\'
                  OR vendor_name ILIKE %s ESCAPE '\\'
              )
            ORDER BY created_at DESC
            LIMIT %s
            """,
            (tenant_id, pattern, pattern, pattern, lim),
        )
        for row in await cur.fetchall():
            amt = int(row["total_cents"]) / 100
            hits.append(
                SearchHit(
                    kind="purchase_order",
                    id=str(row["id"]),
                    title=f"{row['po_number']} · {row['title']}",
                    subtitle=(
                        f"{row['vendor_name']} · USD {amt:,.2f} · 3-way: "
                        f"{row['three_way_match_status']}"
                    ),
                    path="/commercial/",
                    status=str(row["status"]),
                )
            )

        # 8. MRP II Materials & SKUs
        await cur.execute(
            """
            SELECT id, sku, name, material_kind, unit,
                   on_hand_milli, reserved_milli, preferred_vendor_name
            FROM gba.mrp_materials
            WHERE tenant_id = %s
              AND (
                  sku ILIKE %s ESCAPE '\\'
                  OR name ILIKE %s ESCAPE '\\'
                  OR preferred_vendor_name ILIKE %s ESCAPE '\\'
              )
            ORDER BY sku ASC
            LIMIT %s
            """,
            (tenant_id, pattern, pattern, pattern, lim),
        )
        for row in await cur.fetchall():
            avail = (int(row["on_hand_milli"]) - int(row["reserved_milli"])) / 1000
            hits.append(
                SearchHit(
                    kind="mrp_material",
                    id=str(row["id"]),
                    title=f"{row['sku']} · {row['name']}",
                    subtitle=(f"MRP {row['material_kind']} · {avail:,.2f} {row['unit']} available"),
                    path="/industrial/",
                    status=str(row["material_kind"]),
                )
            )

        # 9. Predictive EAM & IoT Assets
        await cur.execute(
            """
            SELECT id, asset_tag, name, serial_number, location_label, status, health_score
            FROM gba.eam_assets
            WHERE tenant_id = %s
              AND (
                  asset_tag ILIKE %s ESCAPE '\\'
                  OR name ILIKE %s ESCAPE '\\'
                  OR serial_number ILIKE %s ESCAPE '\\'
                  OR location_label ILIKE %s ESCAPE '\\'
              )
            ORDER BY asset_tag ASC
            LIMIT %s
            """,
            (tenant_id, pattern, pattern, pattern, pattern, lim),
        )
        for row in await cur.fetchall():
            loc = f" · {row['location_label']}" if row["location_label"] else ""
            hits.append(
                SearchHit(
                    kind="eam_asset",
                    id=str(row["id"]),
                    title=f"{row['asset_tag']} · {row['name']}",
                    subtitle=f"IoT Asset · Health {row['health_score']}/100{loc}",
                    path="/industrial/",
                    status=str(row["status"]),
                )
            )

        # 10. Omnichannel Client Inbox Threads
        await cur.execute(
            """
            SELECT id, contact_name, contact_email, primary_channel,
                   subject, status, unread_count
            FROM gba.omnichannel_threads
            WHERE tenant_id = %s
              AND (
                  contact_name ILIKE %s ESCAPE '\\'
                  OR coalesce(contact_email, '') ILIKE %s ESCAPE '\\'
                  OR subject ILIKE %s ESCAPE '\\'
                  OR last_message_preview ILIKE %s ESCAPE '\\'
              )
            ORDER BY last_message_at DESC
            LIMIT %s
            """,
            (tenant_id, pattern, pattern, pattern, pattern, lim),
        )
        for row in await cur.fetchall():
            unread = f" · {row['unread_count']} unread" if int(row["unread_count"]) > 0 else ""
            subject = str(row["subject"]) or "Conversation"
            hits.append(
                SearchHit(
                    kind="inbox_thread",
                    id=str(row["id"]),
                    title=f"{row['contact_name']} · {subject}",
                    subtitle=f"Client Inbox ({row['primary_channel']}){unread}",
                    path="/inbox/",
                    status=str(row["status"]),
                )
            )

        # 11. US Payroll Employee Profiles
        await cur.execute(
            """
            SELECT id, employee_code, full_name, work_state,
                   overtime_rule, union_local_code, is_active
            FROM gba.payroll_profiles
            WHERE tenant_id = %s
              AND (
                  employee_code ILIKE %s ESCAPE '\\'
                  OR full_name ILIKE %s ESCAPE '\\'
                  OR union_local_code ILIKE %s ESCAPE '\\'
              )
            ORDER BY employee_code ASC
            LIMIT %s
            """,
            (tenant_id, pattern, pattern, pattern, lim),
        )
        for row in await cur.fetchall():
            union_str = f" · {row['union_local_code']}" if row["union_local_code"] else ""
            hits.append(
                SearchHit(
                    kind="payroll_profile",
                    id=str(row["id"]),
                    title=f"{row['employee_code']} · {row['full_name']}",
                    subtitle=(
                        f"US Payroll ({row['work_state']}) · {row['overtime_rule']}{union_str}"
                    ),
                    path="/global-finance/",
                    status="active" if row["is_active"] else "inactive",
                )
            )

        # 12. Multi-Currency FX Ledger Entries
        await cur.execute(
            """
            SELECT id, entry_number, description, counterparty_name, currency,
                   amount_minor, status, fx_gain_loss_cents, realized_fx_gain_loss_cents
            FROM gba.fx_ledger_entries
            WHERE tenant_id = %s
              AND (
                  entry_number ILIKE %s ESCAPE '\\'
                  OR description ILIKE %s ESCAPE '\\'
                  OR counterparty_name ILIKE %s ESCAPE '\\'
                  OR currency ILIKE %s ESCAPE '\\'
              )
            ORDER BY entry_date DESC, created_at DESC
            LIMIT %s
            """,
            (tenant_id, pattern, pattern, pattern, pattern, lim),
        )
        for row in await cur.fetchall():
            amt = int(row["amount_minor"]) / 100
            pnl_cents = (
                int(row["realized_fx_gain_loss_cents"])
                if row["status"] == "settled"
                else int(row["fx_gain_loss_cents"])
            )
            hits.append(
                SearchHit(
                    kind="fx_entry",
                    id=str(row["id"]),
                    title=f"{row['entry_number']} · {row['description']}",
                    subtitle=(f"{row['currency']} {amt:,.2f} · FX P&L ${pnl_cents / 100:+,.2f}"),
                    path="/global-finance/",
                    status=str(row["status"]),
                )
            )

    return hits


@router.get("/v1/businesses/{business_id}/search", response_model=BusinessSearchResponse)
@router.get("/v1/salons/{business_id}/search", response_model=BusinessSearchResponse)
async def get_business_search(
    business_id: UUID,
    request: Request,
    principal: CurrentPrincipal,
    q: Annotated[str, Query(min_length=2, max_length=120)],
    limit: Annotated[int, Query(ge=1, le=10)] = 5,
) -> BusinessSearchResponse:
    """Fast tenant-isolated B2B search powering Cmd+K and MCP search_business_records."""
    async with authorized_tenant(
        runtime_pool(request),
        principal,
        business_id,
        Permission.BUSINESS_READ,
        request_id=get_request_id(request),
    ) as session:
        hits = await search_business_records(
            session.conn,
            tenant_id=business_id,
            query=q,
            limit_per_kind=limit,
        )
    return BusinessSearchResponse(query=q.strip(), total=len(hits), hits=hits)
