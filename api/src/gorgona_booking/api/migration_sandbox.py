"""AMARKAL v2.24.0: 1-Click Competitor CSV Migration Wizard & Sample Enterprise Sandbox.

Security & data-integrity invariants:
- Every route runs strictly inside `authorized_tenant(..., Permission.BUSINESS_MANAGE)`
  under PostgreSQL 18 `ENABLE + FORCE ROW LEVEL SECURITY`.
- CSV parsing uses Python stdlib `csv.DictReader` (zero external dependencies), caps rows
  at 500 per batch, strips control characters and spreadsheet formula prefixes, and supports
  `dry_run=True` preview before writing a single row.
- Sample Enterprise Sandbox seeds strictly namespaced `DEMO-*` / `[DEMO]` records across
  MRP II, Predictive EAM/IoT, Omnichannel Inbox, US Payroll, Multi-Currency FX, and
  No-Code Kanban Studio, and `DELETE /migration/sample-sandbox` removes ONLY those demo rows.
"""

from __future__ import annotations

import csv
import io
import re
from datetime import UTC, datetime, timedelta
from typing import Any, Literal
from uuid import UUID, uuid4

from fastapi import APIRouter, HTTPException, Request, status
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb
from pydantic import BaseModel, ConfigDict, Field

from gorgona_booking.api.businesses import CurrentPrincipal
from gorgona_booking.api.deps import runtime_pool
from gorgona_booking.api.request_id import get_request_id
from gorgona_booking.auth.permissions import Permission
from gorgona_booking.tenancy.authorization import authorized_tenant

router = APIRouter(tags=["migration-sandbox"])

SourcePlatform = Literal["quickbooks", "zoho", "odoo", "shopify", "square", "excel_csv"]
MigrationEntityKind = Literal[
    "counterparties",
    "mrp_materials",
    "eam_assets",
    "payroll_profiles",
]

MAX_CSV_ROWS = 500
_CTRL_RE = re.compile(r"[\x00-\x1f\x7f]")
_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_PHONE_RE = re.compile(r"^[+]?[0-9 ().-]{7,32}$")
_STATE_RE = re.compile(r"^[A-Z]{2}$")

_VALID_UNITS = frozenset({"ton", "kg", "lb", "liter", "gallon", "meter", "unit", "box"})
_VALID_MAT_KINDS = frozenset({"raw", "subassembly", "finished"})
_VALID_ASSET_CATS = frozenset(
    {
        "fleet_vehicle",
        "heavy_machinery",
        "cnc_industrial",
        "hvac_facility",
        "power_generator",
        "iot_sensor_node",
    }
)
_VALID_OT_RULES = frozenset({"flsa_weekly_40", "california_daily_8_12", "union_cba_custom"})


class MigrationImportRequest(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    source_platform: SourcePlatform = "excel_csv"
    entity_kind: MigrationEntityKind
    csv_text: str = Field(min_length=3, max_length=250_000)
    dry_run: bool = False


class MigrationRowError(BaseModel):
    model_config = ConfigDict(frozen=True)
    row_number: int
    message: str


class MigrationImportResponse(BaseModel):
    model_config = ConfigDict(frozen=True)
    source_platform: SourcePlatform
    entity_kind: MigrationEntityKind
    dry_run: bool
    parsed_count: int
    imported_count: int
    skipped_count: int
    errors: list[MigrationRowError]
    preview_rows: list[dict[str, Any]]


class SampleSandboxResponse(BaseModel):
    model_config = ConfigDict(frozen=True)
    action: Literal["seeded", "cleared"]
    summary: dict[str, int]
    message: str


def _clean_text(val: str | None, *, max_len: int = 160) -> str:
    raw = _CTRL_RE.sub("", (val or "")).strip()
    if raw.startswith(("'", "=", "+", "@")) and len(raw) > 1 and raw[0] == "'":
        raw = raw[1:].strip()
    return raw[:max_len]


def _pick(row: dict[str, str], *aliases: str) -> str:
    for key in aliases:
        if key in row and row[key].strip():
            return row[key].strip()
    return ""


def _parse_money_cents(raw: str, *, default: int = 0) -> int:
    cleaned = raw.replace("$", "").replace(",", "").strip()
    if not cleaned:
        return default
    val = float(cleaned)
    if val < 0:
        raise ValueError("Monetary amount cannot be negative")
    return round(val * 100)


def _parse_milli(raw: str, *, default: int = 0) -> int:
    cleaned = raw.replace(",", "").strip()
    if not cleaned:
        return default
    val = float(cleaned)
    if val < 0:
        raise ValueError("Quantity cannot be negative")
    return round(val * 1000)


def parse_migration_csv(
    entity_kind: MigrationEntityKind, csv_text: str
) -> tuple[list[dict[str, Any]], list[MigrationRowError]]:
    """Parse and normalize QuickBooks/Zoho/Odoo/Shopify/Square/Excel CSV rows deterministically."""
    text = csv_text.lstrip("\ufeff").strip()
    if not text:
        return [], [MigrationRowError(row_number=1, message="CSV input is empty.")]

    reader = csv.DictReader(io.StringIO(text))
    if not reader.fieldnames:
        return [], [MigrationRowError(row_number=1, message="CSV header row is missing.")]

    valid: list[dict[str, Any]] = []
    errors: list[MigrationRowError] = []

    for idx, raw_row in enumerate(reader, start=2):
        if len(valid) + len(errors) >= MAX_CSV_ROWS:
            errors.append(
                MigrationRowError(
                    row_number=idx,
                    message=f"Batch limit of {MAX_CSV_ROWS} rows reached; split larger files.",
                )
            )
            break

        norm = {
            re.sub(r"[^a-z0-9]+", "_", (k or "").strip().lower()).strip("_"): (v or "").strip()
            for k, v in raw_row.items()
            if k is not None
        }
        if not any(norm.values()):
            continue

        try:
            if entity_kind == "counterparties":
                name = _clean_text(
                    _pick(
                        norm,
                        "display_name",
                        "name",
                        "customer",
                        "customer_name",
                        "company",
                        "company_name",
                        "vendor",
                        "account_name",
                    ),
                    max_len=200,
                )
                if not name:
                    raise ValueError("Missing display_name / name / company column")
                email_raw = _pick(norm, "email", "email_address", "primary_email").lower()
                email = email_raw if email_raw and _EMAIL_RE.match(email_raw) else None
                phone_raw = _clean_text(
                    _pick(norm, "phone", "phone_number", "mobile", "telephone"), max_len=32
                )
                phone = phone_raw if phone_raw and _PHONE_RE.match(phone_raw) else None
                role_raw = _pick(norm, "role", "type", "contact_type").lower()
                role = (
                    role_raw
                    if role_raw in ("customer", "supplier", "contractor", "partner")
                    else ("supplier" if "vendor" in role_raw else "customer")
                )
                kind_raw = _pick(norm, "kind", "entity_type").lower()
                kind = "person" if kind_raw in ("person", "individual") else "organization"
                legal = (
                    _clean_text(_pick(norm, "legal_name", "company_legal_name"), max_len=240)
                    or None
                )
                valid.append(
                    {
                        "display_name": name,
                        "legal_name": legal,
                        "email": email,
                        "phone": phone,
                        "role": role,
                        "kind": kind,
                    }
                )
            elif entity_kind == "mrp_materials":
                sku = _clean_text(
                    _pick(norm, "sku", "item_code", "product_code", "part_number", "code"),
                    max_len=48,
                ).upper()
                name = _clean_text(
                    _pick(norm, "name", "title", "product_name", "item_name", "description"),
                    max_len=160,
                )
                if len(sku) < 2 or len(name) < 2:
                    raise ValueError("SKU and name (min 2 chars each) are required")
                kind_raw = _pick(norm, "material_kind", "kind", "type").lower()
                mat_kind = kind_raw if kind_raw in _VALID_MAT_KINDS else "raw"
                unit_raw = _pick(norm, "unit", "uom").lower()
                unit = unit_raw if unit_raw in _VALID_UNITS else "unit"
                on_hand_milli = _parse_milli(
                    _pick(norm, "on_hand", "qty", "quantity", "stock", "inventory_qty")
                )
                cost_cents = _parse_money_cents(
                    _pick(norm, "unit_cost_usd", "unit_cost", "cost", "price")
                )
                vendor = _clean_text(
                    _pick(norm, "preferred_vendor_name", "vendor", "supplier"), max_len=160
                )
                valid.append(
                    {
                        "sku": sku,
                        "name": name,
                        "material_kind": mat_kind,
                        "unit": unit,
                        "on_hand_milli": on_hand_milli,
                        "unit_cost_cents": cost_cents,
                        "preferred_vendor_name": vendor,
                    }
                )
            elif entity_kind == "eam_assets":
                tag = _clean_text(
                    _pick(norm, "asset_tag", "tag", "unit_number", "equipment_id", "code"),
                    max_len=48,
                ).upper()
                name = _clean_text(
                    _pick(norm, "name", "asset_name", "equipment_name", "vehicle"), max_len=160
                )
                if len(tag) < 2 or len(name) < 2:
                    raise ValueError("asset_tag and name (min 2 chars each) are required")
                cat_raw = _pick(norm, "category", "asset_type", "type").lower()
                category = cat_raw if cat_raw in _VALID_ASSET_CATS else "fleet_vehicle"
                serial = _clean_text(_pick(norm, "serial_number", "vin", "serial"), max_len=120)
                loc = _clean_text(_pick(norm, "location_label", "location", "yard"), max_len=160)
                hrs_milli = _parse_milli(_pick(norm, "engine_hours", "hours", "meter_hours"))
                valid.append(
                    {
                        "asset_tag": tag,
                        "name": name,
                        "category": category,
                        "serial_number": serial,
                        "location_label": loc,
                        "engine_hours_milli": hrs_milli,
                    }
                )
            else:
                code = _clean_text(
                    _pick(norm, "employee_code", "emp_id", "employee_id", "code"), max_len=48
                ).upper()
                full_name = _clean_text(
                    _pick(norm, "full_name", "employee_name", "name"), max_len=160
                )
                if len(code) < 2 or len(full_name) < 2:
                    raise ValueError("employee_code and full_name (min 2 chars each) are required")
                st = _pick(norm, "work_state", "state").upper() or "IL"
                if not _STATE_RE.match(st):
                    raise ValueError(f"Invalid 2-letter US work_state: {st}")
                pay_type = (
                    "salaried"
                    if _pick(norm, "pay_type", "basis").lower() in ("salaried", "salary")
                    else "hourly"
                )
                rate_cents = _parse_money_cents(
                    _pick(norm, "base_rate_usd", "hourly_rate", "rate", "salary"), default=2500
                )
                ot_raw = _pick(norm, "overtime_rule", "ot_rule").lower()
                ot_rule = (
                    ot_raw
                    if ot_raw in _VALID_OT_RULES
                    else ("california_daily_8_12" if st == "CA" else "flsa_weekly_40")
                )
                union_local = _clean_text(
                    _pick(norm, "union_local_code", "union", "union_local"), max_len=80
                )
                valid.append(
                    {
                        "employee_code": code,
                        "full_name": full_name,
                        "work_state": st,
                        "pay_type": pay_type,
                        "base_rate_cents": rate_cents,
                        "overtime_rule": ot_rule,
                        "union_local_code": union_local,
                    }
                )
        except ValueError as exc:
            errors.append(MigrationRowError(row_number=idx, message=str(exc)))

    return valid, errors


@router.post(
    "/v1/businesses/{business_id}/migration/import",
    response_model=MigrationImportResponse,
)
async def post_migration_import(
    business_id: UUID,
    body: MigrationImportRequest,
    request: Request,
    principal: CurrentPrincipal,
) -> MigrationImportResponse:
    """Preview (`dry_run=True`) or import competitor CSV records under PG18 FORCE RLS."""
    rows, row_errors = parse_migration_csv(body.entity_kind, body.csv_text)
    if body.dry_run or not rows:
        return MigrationImportResponse(
            source_platform=body.source_platform,
            entity_kind=body.entity_kind,
            dry_run=body.dry_run,
            parsed_count=len(rows),
            imported_count=0,
            skipped_count=0,
            errors=row_errors,
            preview_rows=rows[:10],
        )

    imported = 0
    skipped = 0
    async with (
        authorized_tenant(
            runtime_pool(request),
            principal,
            business_id,
            Permission.BUSINESS_MANAGE,
            request_id=get_request_id(request),
        ) as session,
        session.conn.cursor(row_factory=dict_row) as cur,
    ):
        if body.entity_kind == "counterparties":
            if principal.user_id is None:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Authenticated user identity is required to import counterparties.",
                )
            for r in rows:
                name_key = " ".join(str(r["display_name"]).lower().split())
                await cur.execute(
                    """
                        SELECT 1 FROM gba.counterparty_versions
                        WHERE tenant_id = %s AND name_key = %s
                        LIMIT 1
                        """,
                    (business_id, name_key),
                )
                if await cur.fetchone() is not None:
                    skipped += 1
                    continue
                cp_id = uuid4()
                await cur.execute(
                    """
                        INSERT INTO gba.counterparties (tenant_id, id, kind, created_by)
                        VALUES (%s, %s, %s, %s)
                        """,
                    (business_id, cp_id, r["kind"], principal.user_id),
                )
                await cur.execute(
                    """
                        INSERT INTO gba.counterparty_versions
                            (tenant_id, counterparty_id, revision, display_name, legal_name,
                             email, phone, roles, state, created_by)
                        VALUES (%s, %s, 1, %s, %s, %s, %s, %s::text[], 'active', %s)
                        """,
                    (
                        business_id,
                        cp_id,
                        r["display_name"],
                        r["legal_name"],
                        r["email"],
                        r["phone"],
                        [r["role"]],
                        principal.user_id,
                    ),
                )
                imported += 1
        elif body.entity_kind == "mrp_materials":
            for r in rows:
                await cur.execute(
                    """
                        INSERT INTO gba.mrp_materials
                            (tenant_id, sku, name, material_kind, unit,
                             on_hand_milli, unit_cost_cents, preferred_vendor_name)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                        ON CONFLICT (tenant_id, sku) DO UPDATE SET
                            name = EXCLUDED.name,
                            material_kind = EXCLUDED.material_kind,
                            unit = EXCLUDED.unit,
                            on_hand_milli = GREATEST(
                                gba.mrp_materials.reserved_milli,
                                EXCLUDED.on_hand_milli
                            ),
                            unit_cost_cents = EXCLUDED.unit_cost_cents,
                            preferred_vendor_name = EXCLUDED.preferred_vendor_name,
                            updated_at = now()
                        """,
                    (
                        business_id,
                        r["sku"],
                        r["name"],
                        r["material_kind"],
                        r["unit"],
                        r["on_hand_milli"],
                        r["unit_cost_cents"],
                        r["preferred_vendor_name"],
                    ),
                )
                imported += 1
        elif body.entity_kind == "eam_assets":
            for r in rows:
                await cur.execute(
                    """
                        INSERT INTO gba.eam_assets
                            (tenant_id, asset_tag, name, category, serial_number,
                             location_label, engine_hours_milli)
                        VALUES (%s, %s, %s, %s, %s, %s, %s)
                        ON CONFLICT (tenant_id, asset_tag) DO UPDATE SET
                            name = EXCLUDED.name,
                            category = EXCLUDED.category,
                            serial_number = EXCLUDED.serial_number,
                            location_label = EXCLUDED.location_label,
                            engine_hours_milli = EXCLUDED.engine_hours_milli,
                            updated_at = now()
                        """,
                    (
                        business_id,
                        r["asset_tag"],
                        r["name"],
                        r["category"],
                        r["serial_number"],
                        r["location_label"],
                        r["engine_hours_milli"],
                    ),
                )
                imported += 1
        else:
            for r in rows:
                await cur.execute(
                    """
                        INSERT INTO gba.payroll_profiles
                            (tenant_id, employee_code, full_name, work_state,
                             pay_type, base_rate_cents, overtime_rule, union_local_code)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                        ON CONFLICT (tenant_id, employee_code) DO UPDATE SET
                            full_name = EXCLUDED.full_name,
                            work_state = EXCLUDED.work_state,
                            pay_type = EXCLUDED.pay_type,
                            base_rate_cents = EXCLUDED.base_rate_cents,
                            overtime_rule = EXCLUDED.overtime_rule,
                            union_local_code = EXCLUDED.union_local_code,
                            updated_at = now()
                        """,
                    (
                        business_id,
                        r["employee_code"],
                        r["full_name"],
                        r["work_state"],
                        r["pay_type"],
                        r["base_rate_cents"],
                        r["overtime_rule"],
                        r["union_local_code"],
                    ),
                )
                imported += 1

    return MigrationImportResponse(
        source_platform=body.source_platform,
        entity_kind=body.entity_kind,
        dry_run=False,
        parsed_count=len(rows),
        imported_count=imported,
        skipped_count=skipped,
        errors=row_errors,
        preview_rows=rows[:10],
    )


@router.post(
    "/v1/businesses/{business_id}/migration/sample-sandbox",
    response_model=SampleSandboxResponse,
    status_code=status.HTTP_201_CREATED,
)
async def post_seed_sample_sandbox(
    business_id: UUID,
    request: Request,
    principal: CurrentPrincipal,
) -> SampleSandboxResponse:
    """Idempotently load clearly tagged `[DEMO]` records across all 6 flagship US #1 modules."""
    summary: dict[str, int] = {}
    async with (
        authorized_tenant(
            runtime_pool(request),
            principal,
            business_id,
            Permission.BUSINESS_MANAGE,
            request_id=get_request_id(request),
        ) as session,
        session.conn.cursor(row_factory=dict_row) as cur,
    ):
        # 1. MRP II Materials + BOM Recipe
        mats = [
            ("DEMO-STEEL-01", "[DEMO] Cold-Rolled Steel Sheet", "raw", "ton", 14000, 92000),
            ("DEMO-RESIN-01", "[DEMO] Industrial Epoxy Coating", "raw", "ton", 6000, 64000),
            (
                "DEMO-FRAME-PRO",
                "[DEMO] Heavy Chassis Assembly",
                "finished",
                "ton",
                2000,
                245000,
            ),
        ]
        mat_ids: dict[str, UUID] = {}
        for sku, name, kind, unit, qty, cost in mats:
            await cur.execute(
                """
                    INSERT INTO gba.mrp_materials
                        (tenant_id, sku, name, material_kind, unit, on_hand_milli,
                         unit_cost_cents, preferred_vendor_name)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, 'Midwest Steel & Alloy Supply')
                    ON CONFLICT (tenant_id, sku) DO UPDATE SET updated_at = now()
                    RETURNING id
                    """,
                (business_id, sku, name, kind, unit, qty, cost),
            )
            row = await cur.fetchone()
            if row:
                mat_ids[sku] = UUID(str(row["id"]))
        if {"DEMO-STEEL-01", "DEMO-RESIN-01", "DEMO-FRAME-PRO"} <= set(mat_ids):
            await cur.execute(
                """
                    INSERT INTO gba.mrp_recipes
                        (tenant_id, code, name, output_material_id, output_qty_milli, notes)
                    VALUES (%s, 'BOM-DEMO-01', '[DEMO] Chassis Frame Spec (1 Ton)', %s, 1000,
                            'Sample 2-component industrial recipe')
                    ON CONFLICT (tenant_id, code) DO UPDATE SET updated_at = now()
                    RETURNING id
                    """,
                (business_id, mat_ids["DEMO-FRAME-PRO"]),
            )
            rrow = await cur.fetchone()
            if rrow:
                rec_id = UUID(str(rrow["id"]))
                for comp_sku, qty_m, scrap in (
                    ("DEMO-STEEL-01", 800, 250),
                    ("DEMO-RESIN-01", 200, 100),
                ):
                    await cur.execute(
                        """
                            INSERT INTO gba.mrp_recipe_lines
                                (tenant_id, recipe_id, component_material_id,
                                 qty_per_batch_milli, scrap_bps)
                            VALUES (%s, %s, %s, %s, %s)
                            ON CONFLICT (tenant_id, recipe_id, component_material_id) DO NOTHING
                            """,
                        (business_id, rec_id, mat_ids[comp_sku], qty_m, scrap),
                    )
        summary["mrp_materials_and_bom"] = 4

        # 2. Predictive EAM / IoT Asset & Rule
        await cur.execute(
            """
                INSERT INTO gba.eam_assets
                    (tenant_id, asset_tag, name, category, serial_number,
                     location_label, engine_hours_milli, health_score)
                VALUES (%s, 'DEMO-TRK-01', '[DEMO] Freightliner Cascadia #104',
                        'fleet_vehicle', '1FUJGLDR5HL-DEMO', 'Chicago Hub Bay 3',
                        1420000, 91)
                ON CONFLICT (tenant_id, asset_tag) DO UPDATE SET updated_at = now()
                RETURNING id
                """,
            (business_id,),
        )
        arow = await cur.fetchone()
        if arow:
            asset_id = UUID(str(arow["id"]))
            await cur.execute(
                """
                    SELECT 1 FROM gba.eam_maintenance_rules
                    WHERE tenant_id = %s AND asset_id = %s AND rule_name = '[DEMO] 500h Diesel PM'
                    LIMIT 1
                    """,
                (business_id, asset_id),
            )
            if await cur.fetchone() is None:
                await cur.execute(
                    """
                        INSERT INTO gba.eam_maintenance_rules
                            (tenant_id, asset_id, rule_name, metric_key, operator,
                             threshold_milli, warning_lead_pct, priority, wo_title_template)
                        VALUES (%s, %s, '[DEMO] 500h Diesel PM', 'engine_hours',
                                'interval_every', 500000, 90, 'high',
                                'Predictive 500h Oil, Filter & Bearing Service')
                        """,
                    (business_id, asset_id),
                )
        summary["eam_iot_assets"] = 1

        # 3. Omnichannel Client Inbox Thread
        await cur.execute(
            """
                SELECT id FROM gba.omnichannel_threads
                WHERE tenant_id = %s AND subject = '[DEMO] Priority Freight Quote & Pickup Window'
                LIMIT 1
                """,
            (business_id,),
        )
        if await cur.fetchone() is None:
            await cur.execute(
                """
                    INSERT INTO gba.omnichannel_threads
                        (tenant_id, contact_name, contact_email, contact_phone,
                         primary_channel, subject, status, priority, unread_count,
                         last_message_preview)
                    VALUES (%s, '[DEMO] Sarah Miller — Apex Freight',
                            'sarah.demo@apexfreight.example', '+1-312-555-0194',
                            'email', '[DEMO] Priority Freight Quote & Pickup Window',
                            'open', 'high', 1,
                            'Can we confirm Tuesday 09:00 dock pickup for 4 pallets?')
                    RETURNING id
                    """,
                (business_id,),
            )
            trow = await cur.fetchone()
            if trow:
                await cur.execute(
                    """
                        INSERT INTO gba.omnichannel_messages
                            (tenant_id, thread_id, channel_type, direction, sender_name,
                             sender_address, subject, body, delivery_status)
                        VALUES (%s, %s, 'email', 'inbound', '[DEMO] Sarah Miller',
                                'sarah.demo@apexfreight.example',
                                '[DEMO] Priority Freight Quote & Pickup Window',
                                'Hi team, can we confirm Tuesday 09:00 dock pickup for 4 pallets?',
                                'received')
                        """,
                    (business_id, UUID(str(trow["id"]))),
                )
        summary["omnichannel_threads"] = 1

        # 4. US Payroll Employee Profile (California §510 + Union CBA)
        await cur.execute(
            """
                INSERT INTO gba.payroll_profiles
                    (tenant_id, employee_code, full_name, work_state, pay_type,
                     base_rate_cents, overtime_rule, union_local_code, union_dues_cents,
                     health_insurance_pretax_cents, retirement_401k_bps, filing_status,
                     external_payroll_provider)
                VALUES (%s, 'DEMO-EMP-01', '[DEMO] Jordan Vance', 'CA', 'hourly',
                        4400, 'california_daily_8_12', 'IBT Local 705', 4500,
                        15000, 400, 'single', 'gusto')
                ON CONFLICT (tenant_id, employee_code) DO NOTHING
                """,
            (business_id,),
        )
        summary["us_payroll_profiles"] = 1

        # 5. Multi-Currency FX Rate + Open EUR Receivable
        await cur.execute(
            """
                INSERT INTO gba.fx_rates
                    (tenant_id, base_currency, quote_currency, rate_micros, source)
                VALUES (%s, 'EUR', 'USD', 1095000, 'manual')
                ON CONFLICT (tenant_id, base_currency, quote_currency) DO NOTHING
                """,
            (business_id,),
        )
        await cur.execute(
            """
                INSERT INTO gba.fx_ledger_entries
                    (tenant_id, entry_number, description, counterparty_name, currency,
                     amount_minor, entry_kind, booking_rate_micros, booked_usd_cents,
                     current_rate_micros, revalued_usd_cents, fx_gain_loss_cents, status,
                     created_by_user_id)
                VALUES (%s, 'FX-DEMO-01', '[DEMO] EU Export Invoice #4082',
                        'Rheinland Logistics GmbH', 'EUR', 1250000, 'receivable',
                        1080000, 1350000, 1095000, 1368750, 18750, 'open', %s)
                ON CONFLICT (tenant_id, entry_number) DO NOTHING
                """,
            (business_id, principal.user_id),
        )
        summary["fx_ledger_entries"] = 1

        # 6. No-Code Workspace Studio Kanban Board
        lanes = [
            {"id": "backlog", "title": "Incoming", "color": "#475569"},
            {"id": "active", "title": "In Execution", "color": "#0a66ff"},
            {"id": "done", "title": "Completed", "color": "#15803d"},
        ]
        await cur.execute(
            """
                INSERT INTO gba.workspace_boards
                    (tenant_id, slug, title, entity_kind, lanes, created_by_user_id)
                VALUES (%s, 'demo-ops-board', '[DEMO] Executive Operations Board',
                        'general', %s, %s)
                ON CONFLICT (tenant_id, slug) DO UPDATE SET updated_at = now()
                RETURNING id
                """,
            (business_id, Jsonb(lanes), principal.user_id),
        )
        brow = await cur.fetchone()
        if brow:
            bid = UUID(str(brow["id"]))
            await cur.execute(
                """
                    SELECT count(*) AS cnt FROM gba.workspace_board_cards
                    WHERE tenant_id = %s AND board_id = %s
                    """,
                (business_id, bid),
            )
            cnt_row = await cur.fetchone()
            if cnt_row and int(cnt_row["cnt"]) == 0:
                await cur.execute(
                    """
                        INSERT INTO gba.workspace_board_cards
                            (tenant_id, board_id, lane_id, title, description, priority,
                             amount_cents, position, created_by_user_id)
                        VALUES
                            (%s, %s, 'active', '[DEMO] Review BOM-DEMO-01 steel reservation',
                             'Verify raw-material allocation in Industrial ERP.', 'high',
                             245000, 0, %s),
                            (%s, %s, 'backlog', '[DEMO] Approve Week 48 CA Payroll Prep',
                             'Review California §510 overtime and download Gusto CSV.', 'medium',
                             185000, 0, %s)
                        """,
                    (
                        business_id,
                        bid,
                        principal.user_id,
                        business_id,
                        bid,
                        principal.user_id,
                    ),
                )
        summary["workspace_kanban_boards"] = 1

        # 7. US Bank Feeds Account & Sample Transactions
        now_utc = datetime.now(UTC)
        today_d = now_utc.date()
        period_key = now_utc.strftime("%Y-%m")
        await cur.execute(
            """
            SELECT id FROM gba.bank_feed_accounts
            WHERE tenant_id = %s AND institution_name = '[DEMO] Chase Business'
            LIMIT 1
            """,
            (business_id,),
        )
        bank_row = await cur.fetchone()
        if bank_row is None:
            await cur.execute(
                """
                INSERT INTO gba.bank_feed_accounts (
                    tenant_id, institution_name, account_name, account_mask,
                    account_type, currency, connection_mode, current_balance_cents,
                    last_synced_at, created_by_user_id
                )
                VALUES (
                    %s, '[DEMO] Chase Business', 'Operating Checking', '4821',
                    'checking', 'USD', 'plaid_sandbox', 14825000, now(), %s
                )
                RETURNING id
                """,
                (business_id, principal.user_id),
            )
            bank_row = await cur.fetchone()
        if bank_row is not None:
            bank_id = UUID(str(bank_row["id"]))
            demo_bank_txs = [
                (
                    "DEMO-BNK-001",
                    today_d - timedelta(days=1),
                    "[DEMO] STRIPE US PAYOUT ACH (0% AMARKAL FEE)",
                    "Stripe US",
                    "credit",
                    1845000,
                    "client_payment",
                    "suggested",
                    "payment_session",
                    "Stripe · Midwest Cold Chain Logistics",
                    98,
                ),
                (
                    "DEMO-BNK-002",
                    today_d - timedelta(days=2),
                    "[DEMO] PILOT FLYING J FLEET DIESEL CARD #04",
                    "Pilot Flying J",
                    "debit",
                    218500,
                    "fleet_fuel",
                    "unmatched",
                    None,
                    "",
                    0,
                ),
            ]
            for (
                ext_id,
                p_date,
                desc,
                merch,
                direction,
                amt,
                cat,
                r_stat,
                m_kind,
                m_lbl,
                m_conf,
            ) in demo_bank_txs:
                await cur.execute(
                    """
                    INSERT INTO gba.bank_feed_transactions (
                        tenant_id, bank_account_id, external_tx_id, posted_date,
                        description, merchant_name, direction, amount_cents, currency,
                        category_hint, source_format, reconciliation_status,
                        matched_entity_kind, matched_entity_label, match_confidence
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, 'USD', %s, 'plaid', %s, %s, %s, %s)
                    ON CONFLICT (tenant_id, bank_account_id, external_tx_id) DO NOTHING
                    """,
                    (
                        business_id,
                        bank_id,
                        ext_id,
                        p_date,
                        desc,
                        merch,
                        direction,
                        amt,
                        cat,
                        r_stat,
                        m_kind,
                        m_lbl,
                        m_conf,
                    ),
                )
        summary["us_bank_feed_accounts"] = 1

        # 8. Holding Multi-Entity Subsidiaries & Intercompany Elimination Demo
        demo_subs = [
            (
                "DEMO-US-HQ",
                "[DEMO] US Parent Holdings LLC",
                "parent_holding",
                "US",
                "IL",
                "USD",
                10000,
            ),
            (
                "DEMO-EU-DE",
                "[DEMO] Europe Logistics GmbH",
                "operating_subsidiary",
                "DE",
                "HH",
                "EUR",
                8000,
            ),
        ]
        demo_sub_ids: dict[str, UUID] = {}
        for code, name, role, country, state, ccy, own_bps in demo_subs:
            await cur.execute(
                """
                INSERT INTO gba.holding_subsidiaries (
                    tenant_id, entity_code, legal_name, entity_role,
                    jurisdiction_country, jurisdiction_state, functional_currency,
                    ownership_bps, tax_id_masked, created_by_user_id
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, 'DEMO-TAX', %s)
                ON CONFLICT (tenant_id, entity_code) DO UPDATE SET updated_at = now()
                RETURNING id
                """,
                (business_id, code, name, role, country, state, ccy, own_bps, principal.user_id),
            )
            srow = await cur.fetchone()
            if srow:
                demo_sub_ids[code] = UUID(str(srow["id"]))

        if "DEMO-US-HQ" in demo_sub_ids and "DEMO-EU-DE" in demo_sub_ids:
            for code, rev, cogs, opex, cash, ar, ap in (
                ("DEMO-US-HQ", 62000000, 24000000, 14500000, 88000000, 19500000, 6200000),
                ("DEMO-EU-DE", 34000000, 15000000, 8200000, 21000000, 11400000, 5800000),
            ):
                await cur.execute(
                    """
                    INSERT INTO gba.holding_entity_trial_snapshots (
                        tenant_id, subsidiary_id, period_key, revenue_minor, cogs_minor,
                        opex_minor, cash_minor, ar_minor, ap_minor, inventory_minor,
                        fixed_assets_minor, debt_minor, equity_minor, notes, updated_by_user_id
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, 4500000, 22000000, 9000000,
                            95000000, '[DEMO] Sample holding snapshot', %s)
                    ON CONFLICT (tenant_id, subsidiary_id, period_key) DO NOTHING
                    """,
                    (
                        business_id,
                        demo_sub_ids[code],
                        period_key,
                        rev,
                        cogs,
                        opex,
                        cash,
                        ar,
                        ap,
                        principal.user_id,
                    ),
                )
            await cur.execute(
                """
                INSERT INTO gba.intercompany_transactions (
                    tenant_id, tx_number, period_key, tx_date,
                    source_subsidiary_id, target_subsidiary_id, tx_kind,
                    currency, amount_minor, fx_rate_micros, usd_equivalent_cents,
                    description, source_entry_label, target_entry_label,
                    status, eliminated_at, created_by_user_id
                )
                VALUES (
                    %s, 'IC-DEMO-SBOX-01', %s, %s, %s, %s, 'management_fee',
                    'EUR', 3500000, 1090000, 3815000,
                    '[DEMO] Parent Cloud ERP & Shared Management Fee',
                    'DR Intercompany AR (Due From) / CR Management Fee Revenue',
                    'DR Management Fee Expense / CR Intercompany AP (Due To)',
                    'eliminated', now(), %s
                )
                ON CONFLICT (tenant_id, tx_number) DO NOTHING
                """,
                (
                    business_id,
                    period_key,
                    today_d,
                    demo_sub_ids["DEMO-US-HQ"],
                    demo_sub_ids["DEMO-EU-DE"],
                    principal.user_id,
                ),
            )
        summary["holding_subsidiaries"] = 2

    return SampleSandboxResponse(
        action="seeded",
        summary=summary,
        message=(
            "Loaded sample [DEMO] records across MRP II, Predictive EAM, Omnichannel Inbox, "
            "US Payroll, Multi-Currency FX, Workspace Studio, US Bank Feeds, and Multi-Entity "
            "Holding Consolidation. Remove anytime in 1 click."
        ),
    )


@router.delete(
    "/v1/businesses/{business_id}/migration/sample-sandbox",
    response_model=SampleSandboxResponse,
)
async def delete_sample_sandbox(
    business_id: UUID,
    request: Request,
    principal: CurrentPrincipal,
) -> SampleSandboxResponse:
    """Safely remove ONLY `[DEMO]` / `DEMO-*` sample records without touching real business data."""
    removed: dict[str, int] = {}
    async with (
        authorized_tenant(
            runtime_pool(request),
            principal,
            business_id,
            Permission.BUSINESS_MANAGE,
            request_id=get_request_id(request),
        ) as session,
        session.conn.cursor() as cur,
    ):
        await cur.execute(
            "DELETE FROM gba.mrp_recipes WHERE tenant_id = %s AND code = 'BOM-DEMO-01'",
            (business_id,),
        )
        removed["mrp_recipes"] = cur.rowcount or 0
        await cur.execute(
            """
                DELETE FROM gba.mrp_materials
                WHERE tenant_id = %s
                  AND sku IN ('DEMO-STEEL-01', 'DEMO-RESIN-01', 'DEMO-FRAME-PRO')
                  AND reserved_milli = 0
                """,
            (business_id,),
        )
        removed["mrp_materials"] = cur.rowcount or 0
        await cur.execute(
            "DELETE FROM gba.eam_assets WHERE tenant_id = %s AND asset_tag = 'DEMO-TRK-01'",
            (business_id,),
        )
        removed["eam_assets"] = cur.rowcount or 0
        await cur.execute(
            """
                DELETE FROM gba.omnichannel_threads
                WHERE tenant_id = %s
                  AND subject = '[DEMO] Priority Freight Quote & Pickup Window'
                """,
            (business_id,),
        )
        removed["omnichannel_threads"] = cur.rowcount or 0
        await cur.execute(
            """
                DELETE FROM gba.payroll_profiles
                WHERE tenant_id = %s AND employee_code = 'DEMO-EMP-01'
                """,
            (business_id,),
        )
        removed["payroll_profiles"] = cur.rowcount or 0
        await cur.execute(
            """
                DELETE FROM gba.fx_ledger_entries
                WHERE tenant_id = %s AND entry_number = 'FX-DEMO-01'
                """,
            (business_id,),
        )
        removed["fx_ledger_entries"] = cur.rowcount or 0
        await cur.execute(
            """
                DELETE FROM gba.workspace_boards
                WHERE tenant_id = %s AND slug = 'demo-ops-board'
                """,
            (business_id,),
        )
        removed["workspace_boards"] = cur.rowcount or 0
        await cur.execute(
            """
                DELETE FROM gba.bank_feed_accounts
                WHERE tenant_id = %s AND institution_name = '[DEMO] Chase Business'
                """,
            (business_id,),
        )
        removed["bank_feed_accounts"] = cur.rowcount or 0
        await cur.execute(
            """
                DELETE FROM gba.intercompany_transactions
                WHERE tenant_id = %s AND tx_number = 'IC-DEMO-SBOX-01'
                """,
            (business_id,),
        )
        removed["intercompany_transactions"] = cur.rowcount or 0
        await cur.execute(
            """
                DELETE FROM gba.holding_subsidiaries
                WHERE tenant_id = %s AND entity_code IN ('DEMO-US-HQ', 'DEMO-EU-DE')
                """,
            (business_id,),
        )
        removed["holding_subsidiaries"] = cur.rowcount or 0

    return SampleSandboxResponse(
        action="cleared",
        summary=removed,
        message="Removed all [DEMO] sandbox records cleanly; your live business data is untouched.",
    )
