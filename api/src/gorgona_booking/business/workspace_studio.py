"""AMARKAL v2.16.0: No-Code Workspace Studio — Custom Fields, Kanban Boards & Brand Theme.

Preserves strict NAICS core schemas and FORCE ROW LEVEL SECURITY while giving every
organization Monday.com/Odoo-class flexibility:
- Typed custom fields attached to counterparties, quotes, POs, bookings, assets, and matters.
- Drag-and-Drop Kanban workflow boards with lanes, priorities, USD amounts, and due dates.
- Tenant Brand Themes with deterministic WCAG 2.1 AA contrast validation (>= 4.5:1 on white)
  so custom accent colors never break accessibility.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any, Literal
from uuid import UUID

from psycopg import errors as pg_errors
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from gorgona_booking.db.pool import RuntimeConnection

EntityKind = Literal[
    "counterparty",
    "commercial_quote",
    "purchase_order",
    "booking",
    "asset",
    "project_matter",
]
BoardEntityKind = Literal[
    "general",
    "counterparty",
    "commercial_quote",
    "purchase_order",
    "booking",
    "asset",
    "project_matter",
]
CustomFieldType = Literal["text", "number", "currency_usd", "date", "select", "boolean"]
CardPriority = Literal["low", "medium", "high", "urgent"]
SurfacePreset = Literal["monolith_light", "warm_stone", "slate_enterprise"]

ALLOWED_DASHBOARD_WIDGETS = frozenset(
    {"kpis", "launchpad", "unit_economics", "copilot", "smart_autonomy", "schedule"}
)
DEFAULT_DASHBOARD_WIDGETS = [
    "kpis",
    "launchpad",
    "unit_economics",
    "copilot",
    "smart_autonomy",
    "schedule",
]
DEFAULT_KANBAN_LANES: list[dict[str, str]] = [
    {"id": "backlog", "title": "Backlog", "color_hex": "#4b5563"},
    {"id": "in_progress", "title": "In Progress", "color_hex": "#1d4ed8"},
    {"id": "review", "title": "Review / Approval", "color_hex": "#b45309"},
    {"id": "done", "title": "Completed", "color_hex": "#15803d"},
]

_FIELD_KEY_RE = re.compile(r"^[a-z][a-z0-9_]{1,47}$")
_SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{1,62}$")
_HEX_RE = re.compile(r"^#[0-9A-Fa-f]{6}$")
_LANE_ID_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{1,48}$")


@dataclass(frozen=True)
class CustomFieldDefinitionView:
    id: UUID
    entity_kind: EntityKind
    field_key: str
    label: str
    field_type: CustomFieldType
    options: list[str]
    is_required: bool
    display_order: int
    created_at: datetime


@dataclass(frozen=True)
class CustomFieldValueView:
    id: UUID
    definition_id: UUID
    field_key: str
    label: str
    field_type: CustomFieldType
    entity_kind: EntityKind
    entity_id: str
    value: Any
    updated_at: datetime


@dataclass(frozen=True)
class WorkspaceBoardView:
    id: UUID
    slug: str
    title: str
    entity_kind: BoardEntityKind
    lanes: list[dict[str, str]]
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True)
class WorkspaceBoardCardView:
    id: UUID
    board_id: UUID
    lane_id: str
    title: str
    description: str
    priority: CardPriority
    amount_cents: int | None
    due_date: date | None
    position: int
    custom_fields: dict[str, Any]
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True)
class BrandThemeView:
    tenant_id: UUID
    brand_display_name: str | None
    logo_url: str | None
    accent_hex: str
    accent_contrast_on_white: float
    surface_preset: SurfacePreset
    dashboard_widgets: list[str]
    updated_at: datetime | None


def _srgb_channel(c: int) -> float:
    s = c / 255.0
    return s / 12.92 if s <= 0.03928 else ((s + 0.055) / 1.055) ** 2.4


def relative_luminance(hex_color: str) -> float:
    clean = hex_color.strip()
    if not _HEX_RE.match(clean):
        raise ValueError("Color must be a 6-digit hex code like #111111.")
    r = int(clean[1:3], 16)
    g = int(clean[3:5], 16)
    b = int(clean[5:7], 16)
    return 0.2126 * _srgb_channel(r) + 0.7152 * _srgb_channel(g) + 0.0722 * _srgb_channel(b)


def wcag_contrast_ratio(fg_hex: str, bg_hex: str = "#FFFFFF") -> float:
    """Compute exact WCAG 2.1 contrast ratio between two hex colors (1.0 .. 21.0)."""
    l1 = relative_luminance(fg_hex)
    l2 = relative_luminance(bg_hex)
    lighter, darker = max(l1, l2), min(l1, l2)
    return round((lighter + 0.05) / (darker + 0.05), 2)


def validate_wcag_accent_hex(accent_hex: str) -> tuple[str, float]:
    clean = accent_hex.strip().upper()
    ratio = wcag_contrast_ratio(clean, "#FFFFFF")
    if ratio < 4.5:
        raise ValueError(
            f"Accent color {clean} has {ratio}:1 contrast against white; "
            "WCAG 2.1 AA requires at least 4.5:1 for legible white button text."
        )
    return clean, ratio


def validate_custom_field_value(
    field_type: CustomFieldType, options: list[str], raw_value: Any
) -> Any:
    """Validate and normalize a custom field value against its typed schema."""
    if raw_value is None:
        raise ValueError("Custom field value cannot be null.")
    if field_type == "text":
        val = str(raw_value).strip()
        if len(val) > 500:
            raise ValueError("Text field value cannot exceed 500 characters.")
        return val
    if field_type in ("number", "currency_usd"):
        if isinstance(raw_value, bool):
            raise ValueError("Numeric field cannot be a boolean.")
        try:
            num = float(raw_value)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"Expected numeric value for '{field_type}' field.") from exc
        return round(num, 2) if field_type == "currency_usd" else num
    if field_type == "date":
        text = str(raw_value).strip()
        try:
            parsed = date.fromisoformat(text)
        except ValueError as exc:
            raise ValueError("Date field must use ISO format YYYY-MM-DD.") from exc
        return parsed.isoformat()
    if field_type == "boolean":
        if isinstance(raw_value, bool):
            return raw_value
        if str(raw_value).strip().lower() in ("true", "1", "yes"):
            return True
        if str(raw_value).strip().lower() in ("false", "0", "no"):
            return False
        raise ValueError("Boolean field must be true or false.")
    if field_type == "select":
        choice = str(raw_value).strip()
        if options and choice not in options:
            raise ValueError(f"Select value must be one of: {', '.join(options)}.")
        return choice
    raise ValueError(f"Unsupported field type: {field_type}")


def _validate_lanes(raw_lanes: list[dict[str, str]] | None) -> list[dict[str, str]]:
    if not raw_lanes:
        return list(DEFAULT_KANBAN_LANES)
    if not (2 <= len(raw_lanes) <= 8):
        raise ValueError("Kanban board must have between 2 and 8 lanes.")
    seen: set[str] = set()
    cleaned: list[dict[str, str]] = []
    for lane in raw_lanes:
        lid = str(lane.get("id") or "").strip().lower()
        title = str(lane.get("title") or "").strip()[:60]
        color = str(lane.get("color_hex") or "#111111").strip().upper()
        if not _LANE_ID_RE.match(lid) or lid in seen:
            raise ValueError(f"Invalid or duplicate lane id: '{lid}'.")
        if len(title) < 2:
            raise ValueError("Each lane title must be at least 2 characters.")
        if not _HEX_RE.match(color):
            color = "#111111"
        seen.add(lid)
        cleaned.append({"id": lid, "title": title, "color_hex": color})
    return cleaned


async def list_custom_field_definitions(
    conn: RuntimeConnection, *, tenant_id: UUID, entity_kind: EntityKind | None = None
) -> list[CustomFieldDefinitionView]:
    async with conn.cursor(row_factory=dict_row) as cur:
        if entity_kind is not None:
            await cur.execute(
                """
                SELECT id, entity_kind, field_key, label, field_type, options,
                       is_required, display_order, created_at
                FROM gba.custom_field_definitions
                WHERE tenant_id = %s AND entity_kind = %s
                ORDER BY display_order ASC, created_at ASC
                """,
                (tenant_id, entity_kind),
            )
        else:
            await cur.execute(
                """
                SELECT id, entity_kind, field_key, label, field_type, options,
                       is_required, display_order, created_at
                FROM gba.custom_field_definitions
                WHERE tenant_id = %s
                ORDER BY entity_kind ASC, display_order ASC, created_at ASC
                """,
                (tenant_id,),
            )
        rows = await cur.fetchall()
    return [
        CustomFieldDefinitionView(
            id=UUID(str(r["id"])),
            entity_kind=r["entity_kind"],
            field_key=str(r["field_key"]),
            label=str(r["label"]),
            field_type=r["field_type"],
            options=list(r["options"] or []),
            is_required=bool(r["is_required"]),
            display_order=int(r["display_order"]),
            created_at=r["created_at"],
        )
        for r in rows
    ]


async def create_custom_field_definition(
    conn: RuntimeConnection,
    *,
    tenant_id: UUID,
    entity_kind: EntityKind,
    field_key: str,
    label: str,
    field_type: CustomFieldType,
    options: list[str],
    is_required: bool,
    display_order: int,
    user_id: UUID | None,
) -> CustomFieldDefinitionView:
    clean_key = field_key.strip().lower()
    if not _FIELD_KEY_RE.match(clean_key):
        raise ValueError(
            "Field key must be 2-48 lowercase chars (a-z, 0-9, _) starting with a letter."
        )
    clean_label = label.strip()[:80]
    if len(clean_label) < 2:
        raise ValueError("Field label must be at least 2 characters.")
    clean_opts = [o.strip()[:60] for o in options if o.strip()][:25]
    if field_type == "select" and not clean_opts:
        raise ValueError("Select field must include at least one dropdown option.")
    try:
        async with conn.cursor(row_factory=dict_row) as cur:
            await cur.execute(
                """
                INSERT INTO gba.custom_field_definitions
                    (tenant_id, entity_kind, field_key, label, field_type, options,
                     is_required, display_order, created_by_user_id)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING id, entity_kind, field_key, label, field_type, options,
                          is_required, display_order, created_at
                """,
                (
                    tenant_id,
                    entity_kind,
                    clean_key,
                    clean_label,
                    field_type,
                    clean_opts,
                    is_required,
                    max(0, min(display_order, 1000)),
                    user_id,
                ),
            )
            r = await cur.fetchone()
    except pg_errors.UniqueViolation as exc:
        raise ValueError(f"Custom field '{clean_key}' already exists on '{entity_kind}'.") from exc
    if r is None:
        raise RuntimeError("Failed to create custom field definition.")
    return CustomFieldDefinitionView(
        id=UUID(str(r["id"])),
        entity_kind=r["entity_kind"],
        field_key=str(r["field_key"]),
        label=str(r["label"]),
        field_type=r["field_type"],
        options=list(r["options"] or []),
        is_required=bool(r["is_required"]),
        display_order=int(r["display_order"]),
        created_at=r["created_at"],
    )


async def delete_custom_field_definition(
    conn: RuntimeConnection, *, tenant_id: UUID, definition_id: UUID
) -> bool:
    cur = await conn.execute(
        "DELETE FROM gba.custom_field_definitions WHERE tenant_id = %s AND id = %s",
        (tenant_id, definition_id),
    )
    return cur.rowcount > 0


async def upsert_custom_field_value(
    conn: RuntimeConnection,
    *,
    tenant_id: UUID,
    definition_id: UUID,
    entity_id: str,
    raw_value: Any,
    user_id: UUID | None,
) -> CustomFieldValueView:
    clean_eid = entity_id.strip()[:120]
    if not clean_eid:
        raise ValueError("Entity ID is required.")
    async with conn.cursor(row_factory=dict_row) as cur:
        await cur.execute(
            """
            SELECT id, entity_kind, field_key, label, field_type, options
            FROM gba.custom_field_definitions
            WHERE tenant_id = %s AND id = %s
            """,
            (tenant_id, definition_id),
        )
        defn = await cur.fetchone()
    if defn is None:
        raise LookupError("Custom field definition not found.")
    normalized = validate_custom_field_value(
        defn["field_type"], list(defn["options"] or []), raw_value
    )
    async with conn.cursor(row_factory=dict_row) as cur:
        await cur.execute(
            """
            INSERT INTO gba.custom_field_values
                (tenant_id, definition_id, entity_kind, entity_id, value_json, updated_by_user_id)
            VALUES (%s, %s, %s, %s, %s, %s)
            ON CONFLICT (tenant_id, definition_id, entity_id) DO UPDATE SET
                value_json = EXCLUDED.value_json,
                updated_by_user_id = EXCLUDED.updated_by_user_id,
                updated_at = now()
            RETURNING id, updated_at
            """,
            (tenant_id, definition_id, defn["entity_kind"], clean_eid, Jsonb(normalized), user_id),
        )
        row = await cur.fetchone()
    if row is None:
        raise RuntimeError("Failed to save custom field value.")
    return CustomFieldValueView(
        id=UUID(str(row["id"])),
        definition_id=definition_id,
        field_key=str(defn["field_key"]),
        label=str(defn["label"]),
        field_type=defn["field_type"],
        entity_kind=defn["entity_kind"],
        entity_id=clean_eid,
        value=normalized,
        updated_at=row["updated_at"],
    )


async def list_custom_field_values(
    conn: RuntimeConnection, *, tenant_id: UUID, entity_kind: EntityKind, entity_id: str
) -> list[CustomFieldValueView]:
    async with conn.cursor(row_factory=dict_row) as cur:
        await cur.execute(
            """
            SELECT v.id, v.definition_id, d.field_key, d.label, d.field_type,
                   v.entity_kind, v.entity_id, v.value_json, v.updated_at
            FROM gba.custom_field_values v
            JOIN gba.custom_field_definitions d
              ON d.tenant_id = v.tenant_id AND d.id = v.definition_id
            WHERE v.tenant_id = %s AND v.entity_kind = %s AND v.entity_id = %s
            ORDER BY d.display_order ASC, d.created_at ASC
            """,
            (tenant_id, entity_kind, entity_id.strip()),
        )
        rows = await cur.fetchall()
    return [
        CustomFieldValueView(
            id=UUID(str(r["id"])),
            definition_id=UUID(str(r["definition_id"])),
            field_key=str(r["field_key"]),
            label=str(r["label"]),
            field_type=r["field_type"],
            entity_kind=r["entity_kind"],
            entity_id=str(r["entity_id"]),
            value=r["value_json"],
            updated_at=r["updated_at"],
        )
        for r in rows
    ]


async def list_workspace_boards(
    conn: RuntimeConnection, *, tenant_id: UUID
) -> list[WorkspaceBoardView]:
    async with conn.cursor(row_factory=dict_row) as cur:
        await cur.execute(
            """
            SELECT id, slug, title, entity_kind, lanes, created_at, updated_at
            FROM gba.workspace_boards
            WHERE tenant_id = %s
            ORDER BY created_at ASC
            """,
            (tenant_id,),
        )
        rows = await cur.fetchall()
    return [
        WorkspaceBoardView(
            id=UUID(str(r["id"])),
            slug=str(r["slug"]),
            title=str(r["title"]),
            entity_kind=r["entity_kind"],
            lanes=list(r["lanes"] or []),
            created_at=r["created_at"],
            updated_at=r["updated_at"],
        )
        for r in rows
    ]


async def create_workspace_board(
    conn: RuntimeConnection,
    *,
    tenant_id: UUID,
    slug: str,
    title: str,
    entity_kind: BoardEntityKind,
    lanes: list[dict[str, str]] | None,
    user_id: UUID | None,
) -> WorkspaceBoardView:
    clean_slug = slug.strip().lower()
    if not _SLUG_RE.match(clean_slug):
        raise ValueError("Board slug must be 2-63 lowercase chars (a-z, 0-9, _ or -).")
    clean_title = title.strip()[:120]
    if len(clean_title) < 2:
        raise ValueError("Board title must be at least 2 characters.")
    clean_lanes = _validate_lanes(lanes)
    try:
        async with conn.cursor(row_factory=dict_row) as cur:
            await cur.execute(
                """
                INSERT INTO gba.workspace_boards
                    (tenant_id, slug, title, entity_kind, lanes, created_by_user_id)
                VALUES (%s, %s, %s, %s, %s, %s)
                RETURNING id, slug, title, entity_kind, lanes, created_at, updated_at
                """,
                (tenant_id, clean_slug, clean_title, entity_kind, Jsonb(clean_lanes), user_id),
            )
            r = await cur.fetchone()
    except pg_errors.UniqueViolation as exc:
        raise ValueError(f"Board with slug '{clean_slug}' already exists.") from exc
    if r is None:
        raise RuntimeError("Failed to create workspace board.")
    return WorkspaceBoardView(
        id=UUID(str(r["id"])),
        slug=str(r["slug"]),
        title=str(r["title"]),
        entity_kind=r["entity_kind"],
        lanes=list(r["lanes"] or []),
        created_at=r["created_at"],
        updated_at=r["updated_at"],
    )


async def delete_workspace_board(
    conn: RuntimeConnection, *, tenant_id: UUID, board_id: UUID
) -> bool:
    cur = await conn.execute(
        "DELETE FROM gba.workspace_boards WHERE tenant_id = %s AND id = %s",
        (tenant_id, board_id),
    )
    return cur.rowcount > 0


async def list_board_cards(
    conn: RuntimeConnection, *, tenant_id: UUID, board_id: UUID
) -> list[WorkspaceBoardCardView]:
    async with conn.cursor(row_factory=dict_row) as cur:
        await cur.execute(
            """
            SELECT id, board_id, lane_id, title, description, priority,
                   amount_cents, due_date, position, custom_fields, created_at, updated_at
            FROM gba.workspace_board_cards
            WHERE tenant_id = %s AND board_id = %s
            ORDER BY lane_id ASC, position ASC, created_at ASC
            """,
            (tenant_id, board_id),
        )
        rows = await cur.fetchall()
    return [_row_to_card(dict(r)) for r in rows]


def _row_to_card(r: dict[str, Any]) -> WorkspaceBoardCardView:
    return WorkspaceBoardCardView(
        id=UUID(str(r["id"])),
        board_id=UUID(str(r["board_id"])),
        lane_id=str(r["lane_id"]),
        title=str(r["title"]),
        description=str(r["description"] or ""),
        priority=r["priority"],
        amount_cents=int(r["amount_cents"]) if r["amount_cents"] is not None else None,
        due_date=r["due_date"],
        position=int(r["position"]),
        custom_fields=dict(r["custom_fields"] or {}),
        created_at=r["created_at"],
        updated_at=r["updated_at"],
    )


async def create_board_card(
    conn: RuntimeConnection,
    *,
    tenant_id: UUID,
    board_id: UUID,
    lane_id: str,
    title: str,
    description: str,
    priority: CardPriority,
    amount_cents: int | None,
    due_date: date | None,
    custom_fields: dict[str, Any],
    user_id: UUID | None,
) -> WorkspaceBoardCardView:
    async with conn.cursor(row_factory=dict_row) as cur:
        await cur.execute(
            "SELECT lanes FROM gba.workspace_boards WHERE tenant_id = %s AND id = %s",
            (tenant_id, board_id),
        )
        board = await cur.fetchone()
    if board is None:
        raise LookupError("Workspace board not found.")
    valid_lanes = {str(x.get("id")) for x in (board["lanes"] or []) if isinstance(x, dict)}
    clean_lane = lane_id.strip().lower()
    if clean_lane not in valid_lanes:
        raise ValueError(f"Lane '{clean_lane}' does not exist on this board.")
    clean_title = title.strip()[:180]
    if len(clean_title) < 2:
        raise ValueError("Card title must be at least 2 characters.")
    async with conn.cursor(row_factory=dict_row) as cur:
        await cur.execute(
            """
            SELECT coalesce(max(position), -1) + 1 AS next_pos
            FROM gba.workspace_board_cards
            WHERE tenant_id = %s AND board_id = %s AND lane_id = %s
            """,
            (tenant_id, board_id, clean_lane),
        )
        pos_row = await cur.fetchone() or {"next_pos": 0}
        await cur.execute(
            """
            INSERT INTO gba.workspace_board_cards
                (tenant_id, board_id, lane_id, title, description, priority,
                 amount_cents, due_date, position, custom_fields, created_by_user_id)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING id, board_id, lane_id, title, description, priority,
                      amount_cents, due_date, position, custom_fields, created_at, updated_at
            """,
            (
                tenant_id,
                board_id,
                clean_lane,
                clean_title,
                description.strip()[:1000],
                priority,
                amount_cents,
                due_date,
                int(pos_row["next_pos"]),
                Jsonb(custom_fields),
                user_id,
            ),
        )
        row = await cur.fetchone()
    if row is None:
        raise RuntimeError("Failed to create Kanban card.")
    return _row_to_card(dict(row))


async def move_board_card(
    conn: RuntimeConnection,
    *,
    tenant_id: UUID,
    board_id: UUID,
    card_id: UUID,
    target_lane_id: str,
    target_position: int,
) -> WorkspaceBoardCardView:
    async with conn.cursor(row_factory=dict_row) as cur:
        await cur.execute(
            "SELECT lanes FROM gba.workspace_boards WHERE tenant_id = %s AND id = %s",
            (tenant_id, board_id),
        )
        board = await cur.fetchone()
    if board is None:
        raise LookupError("Workspace board not found.")
    valid_lanes = {str(x.get("id")) for x in (board["lanes"] or []) if isinstance(x, dict)}
    clean_lane = target_lane_id.strip().lower()
    if clean_lane not in valid_lanes:
        raise ValueError(f"Target lane '{clean_lane}' does not exist on this board.")
    async with conn.cursor(row_factory=dict_row) as cur:
        await cur.execute(
            """
            UPDATE gba.workspace_board_cards
            SET lane_id = %s,
                position = %s,
                updated_at = now()
            WHERE tenant_id = %s AND board_id = %s AND id = %s
            RETURNING id, board_id, lane_id, title, description, priority,
                      amount_cents, due_date, position, custom_fields, created_at, updated_at
            """,
            (clean_lane, max(0, target_position), tenant_id, board_id, card_id),
        )
        row = await cur.fetchone()
    if row is None:
        raise LookupError("Kanban card not found.")
    return _row_to_card(dict(row))


async def delete_board_card(
    conn: RuntimeConnection, *, tenant_id: UUID, board_id: UUID, card_id: UUID
) -> bool:
    cur = await conn.execute(
        """
        DELETE FROM gba.workspace_board_cards
        WHERE tenant_id = %s AND board_id = %s AND id = %s
        """,
        (tenant_id, board_id, card_id),
    )
    return cur.rowcount > 0


async def get_brand_theme(conn: RuntimeConnection, *, tenant_id: UUID) -> BrandThemeView:
    async with conn.cursor(row_factory=dict_row) as cur:
        await cur.execute(
            """
            SELECT tenant_id, brand_display_name, logo_url, accent_hex,
                   surface_preset, dashboard_widgets, updated_at
            FROM gba.tenant_brand_themes
            WHERE tenant_id = %s
            """,
            (tenant_id,),
        )
        row = await cur.fetchone()
    if row is None:
        return BrandThemeView(
            tenant_id=tenant_id,
            brand_display_name=None,
            logo_url=None,
            accent_hex="#111111",
            accent_contrast_on_white=wcag_contrast_ratio("#111111", "#FFFFFF"),
            surface_preset="monolith_light",
            dashboard_widgets=list(DEFAULT_DASHBOARD_WIDGETS),
            updated_at=None,
        )
    accent = str(row["accent_hex"]).upper()
    return BrandThemeView(
        tenant_id=tenant_id,
        brand_display_name=str(row["brand_display_name"]) if row["brand_display_name"] else None,
        logo_url=str(row["logo_url"]) if row["logo_url"] else None,
        accent_hex=accent,
        accent_contrast_on_white=wcag_contrast_ratio(accent, "#FFFFFF"),
        surface_preset=row["surface_preset"],
        dashboard_widgets=list(row["dashboard_widgets"] or DEFAULT_DASHBOARD_WIDGETS),
        updated_at=row["updated_at"],
    )


async def upsert_brand_theme(
    conn: RuntimeConnection,
    *,
    tenant_id: UUID,
    brand_display_name: str | None,
    logo_url: str | None,
    accent_hex: str,
    surface_preset: SurfacePreset,
    dashboard_widgets: list[str],
    user_id: UUID | None,
) -> BrandThemeView:
    clean_accent, ratio = validate_wcag_accent_hex(accent_hex)
    clean_name = brand_display_name.strip()[:120] if brand_display_name else None
    if clean_name == "":
        clean_name = None
    clean_logo: str | None = None
    if logo_url and logo_url.strip():
        cand = logo_url.strip()
        if not cand.startswith("https://") or len(cand) > 500:
            raise ValueError("Logo URL must start with https:// (up to 500 chars).")
        clean_logo = cand
    clean_widgets = [w for w in dashboard_widgets if w in ALLOWED_DASHBOARD_WIDGETS]
    if not clean_widgets:
        clean_widgets = list(DEFAULT_DASHBOARD_WIDGETS)
    async with conn.cursor(row_factory=dict_row) as cur:
        await cur.execute(
            """
            INSERT INTO gba.tenant_brand_themes
                (tenant_id, brand_display_name, logo_url, accent_hex,
                 surface_preset, dashboard_widgets, updated_by_user_id)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (tenant_id) DO UPDATE SET
                brand_display_name = EXCLUDED.brand_display_name,
                logo_url = EXCLUDED.logo_url,
                accent_hex = EXCLUDED.accent_hex,
                surface_preset = EXCLUDED.surface_preset,
                dashboard_widgets = EXCLUDED.dashboard_widgets,
                updated_by_user_id = EXCLUDED.updated_by_user_id,
                updated_at = now()
            RETURNING updated_at
            """,
            (
                tenant_id,
                clean_name,
                clean_logo,
                clean_accent,
                surface_preset,
                clean_widgets,
                user_id,
            ),
        )
        row = await cur.fetchone()
    if row is None:
        raise RuntimeError("Failed to save tenant brand theme.")
    return BrandThemeView(
        tenant_id=tenant_id,
        brand_display_name=clean_name,
        logo_url=clean_logo,
        accent_hex=clean_accent,
        accent_contrast_on_white=ratio,
        surface_preset=surface_preset,
        dashboard_widgets=clean_widgets,
        updated_at=row["updated_at"],
    )
