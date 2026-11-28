"""AMARKAL v2.31.0: Matrix RBAC / ABAC Policy Engine, Field Masking & Time-Window Guards.

Design invariants:
- Strictly additive restrictive overlay over ADR-0008 ROLE_PERMISSIONS (PERMISSIONS_VERSION = 25).
- An ABAC policy can NEVER elevate a user above their base membership role; it only narrows
  effective permissions, scopes records by region, masks sensitive PII/financial fields,
  enforces local-timezone write windows, or caps financial transaction amounts.
- Zero external dependencies; pure stdlib `zoneinfo` + deterministic evaluation.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, tzinfo
from typing import Any
from uuid import UUID
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from psycopg import errors as pg_errors
from psycopg.rows import dict_row

from gorgona_booking.auth.permissions import Permission
from gorgona_booking.db.pool import RuntimeConnection

ALLOWED_BASE_ROLES: frozenset[str] = frozenset({"artist", "front_desk", "manager", "owner"})

ALLOWED_MASKED_FIELDS: frozenset[str] = frozenset(
    {
        "phone",
        "email",
        "tax_id",
        "bank_account",
        "compensation",
        "unit_cost",
        "contract_value",
    }
)

ALL_PERMISSION_VALUES: frozenset[str] = frozenset(str(p) for p in Permission)

_WRITE_PERMISSION_SUFFIXES: tuple[str, ...] = (
    ".manage",
    ".manage_admins",
    ".write",
    ".close",
    ".approve",
    ".assign",
    ".plan",
    ".work",
    ".events",
    ".broker",
    ".tender",
    ".kitchen",
    ".service",
    ".customer_answer",
    ".contractor_work",
    ".go_live",
    ".tenant_status",
)

_FIELD_ALIASES: dict[str, frozenset[str]] = {
    "phone": frozenset({"phone", "phone_number", "contact_phone", "mobile", "telephone"}),
    "email": frozenset({"email", "contact_email", "work_email", "billing_email"}),
    "tax_id": frozenset({"tax_id", "ein", "ssn", "tin", "vat_number", "tax_id_masked"}),
    "bank_account": frozenset(
        {"bank_account", "account_number", "iban", "routing_number", "account_mask"}
    ),
    "compensation": frozenset(
        {
            "compensation",
            "salary",
            "hourly_rate",
            "base_rate_cents",
            "gross_pay_cents",
            "net_pay_cents",
        }
    ),
    "unit_cost": frozenset({"unit_cost", "unit_cost_cents", "cost_cents", "cogs_cents"}),
    "contract_value": frozenset(
        {"contract_value", "contract_value_cents", "total_cents", "amount_cents"}
    ),
}

_WEEKDAY_LABELS: dict[int, str] = {
    1: "Mon",
    2: "Tue",
    3: "Wed",
    4: "Thu",
    5: "Fri",
    6: "Sat",
    7: "Sun",
}

_DIGITS_RE = re.compile(r"\d")


def is_write_permission(permission: Permission | str) -> bool:
    """Return True if the permission mutates business data rather than reading it."""
    val = str(permission)
    return val.endswith(_WRITE_PERMISSION_SUFFIXES)


def validate_timezone_name(tz_name: str) -> str:
    """Validate an IANA timezone name via stdlib zoneinfo."""
    cleaned = tz_name.strip()
    try:
        ZoneInfo(cleaned)
    except (ZoneInfoNotFoundError, KeyError, ValueError) as exc:
        raise ValueError(f"Unsupported IANA timezone: {tz_name!r}") from exc
    return cleaned


def format_minute_hhmm(minute: int) -> str:
    """Format minute offset 0..1440 as HH:MM."""
    clamped = max(0, min(1440, int(minute)))
    return f"{clamped // 60:02d}:{clamped % 60:02d}"


def format_weekdays(days: Iterable[int]) -> str:
    ordered = sorted({d for d in days if 1 <= d <= 7})
    if ordered == [1, 2, 3, 4, 5]:
        return "Mon-Fri"
    if ordered == [1, 2, 3, 4, 5, 6, 7]:
        return "Daily"
    return ",".join(_WEEKDAY_LABELS[d] for d in ordered) if ordered else "None"


@dataclass(frozen=True, slots=True)
class WriteWindowRule:
    policy_code: str
    timezone: str
    start_minute: int
    end_minute: int
    days: frozenset[int]
    permissions: frozenset[str]


@dataclass(frozen=True, slots=True)
class AbacPolicySpec:
    policy_code: str
    display_name: str
    base_role: str
    denied_permissions: frozenset[str]
    allowed_regions: frozenset[str]
    masked_fields: frozenset[str]
    write_window_enabled: bool
    write_window_timezone: str
    write_window_start_minute: int
    write_window_end_minute: int
    write_window_days: frozenset[int]
    write_window_permissions: frozenset[str]
    max_financial_amount_cents: int | None


@dataclass(frozen=True, slots=True)
class EffectiveAbacOverlay:
    """Merged least-privilege overlay across all active ABAC policies assigned to a user."""

    policy_codes: tuple[str, ...]
    denied_permissions: frozenset[str]
    allowed_regions: frozenset[str]
    region_conflict: bool
    masked_fields: frozenset[str]
    write_windows: tuple[WriteWindowRule, ...]
    max_financial_amount_cents: int | None


@dataclass(frozen=True, slots=True)
class AbacEvaluationResult:
    allowed: bool
    reason: str
    blocked_by: str | None
    policy_codes: tuple[str, ...]
    masked_fields: tuple[str, ...]
    effective_regions: tuple[str, ...]
    max_financial_amount_cents: int | None
    evaluated_local_time: str


def _normalize_regions(regions: Iterable[str]) -> frozenset[str]:
    return frozenset(r.strip().upper() for r in regions if r and r.strip())


def merge_abac_policies(policies: Sequence[AbacPolicySpec]) -> EffectiveAbacOverlay | None:
    """Merge multiple ABAC policies under strict least-privilege semantics."""
    if not policies:
        return None

    denied: set[str] = set()
    masked: set[str] = set()
    region_sets: list[frozenset[str]] = []
    windows: list[WriteWindowRule] = []
    max_amounts: list[int] = []

    for policy in policies:
        denied.update(policy.denied_permissions)
        masked.update(policy.masked_fields)
        norm_regions = _normalize_regions(policy.allowed_regions)
        if norm_regions:
            region_sets.append(norm_regions)
        if policy.write_window_enabled:
            windows.append(
                WriteWindowRule(
                    policy_code=policy.policy_code,
                    timezone=policy.write_window_timezone,
                    start_minute=policy.write_window_start_minute,
                    end_minute=policy.write_window_end_minute,
                    days=policy.write_window_days,
                    permissions=policy.write_window_permissions,
                )
            )
        if policy.max_financial_amount_cents is not None:
            max_amounts.append(policy.max_financial_amount_cents)

    allowed_regions: frozenset[str] = frozenset()
    region_conflict = False
    if region_sets:
        intersected = set(region_sets[0])
        for reg_set in region_sets[1:]:
            intersected &= reg_set
        if not intersected:
            region_conflict = True
        else:
            allowed_regions = frozenset(intersected)

    return EffectiveAbacOverlay(
        policy_codes=tuple(p.policy_code for p in policies),
        denied_permissions=frozenset(denied),
        allowed_regions=allowed_regions,
        region_conflict=region_conflict,
        masked_fields=frozenset(masked),
        write_windows=tuple(windows),
        max_financial_amount_cents=min(max_amounts) if max_amounts else None,
    )


def evaluate_abac_access(
    overlay: EffectiveAbacOverlay | None,
    permission: Permission | str,
    *,
    at_utc: datetime | None = None,
    record_region: str | None = None,
    amount_cents: int | None = None,
) -> AbacEvaluationResult:
    """Evaluate an action against a user's merged ABAC overlay."""
    now_utc = (at_utc or datetime.now(UTC)).astimezone(UTC)
    if overlay is None:
        return AbacEvaluationResult(
            allowed=True,
            reason="No ABAC overlay assigned; standard role permissions apply.",
            blocked_by=None,
            policy_codes=(),
            masked_fields=(),
            effective_regions=(),
            max_financial_amount_cents=None,
            evaluated_local_time=now_utc.strftime("%Y-%m-%d %H:%M UTC"),
        )

    perm_str = str(permission)
    masked_tuple = tuple(sorted(overlay.masked_fields))
    regions_tuple = tuple(sorted(overlay.allowed_regions))
    default_tz_label = now_utc.strftime("%Y-%m-%d %H:%M UTC")

    if perm_str in overlay.denied_permissions:
        return AbacEvaluationResult(
            allowed=False,
            reason=f"ABAC policy denies permission '{perm_str}'.",
            blocked_by="denied_permission",
            policy_codes=overlay.policy_codes,
            masked_fields=masked_tuple,
            effective_regions=regions_tuple,
            max_financial_amount_cents=overlay.max_financial_amount_cents,
            evaluated_local_time=default_tz_label,
        )

    if overlay.region_conflict:
        return AbacEvaluationResult(
            allowed=False,
            reason="Conflicting regional ABAC policies leave zero allowed regions (fail-closed).",
            blocked_by="region_conflict",
            policy_codes=overlay.policy_codes,
            masked_fields=masked_tuple,
            effective_regions=(),
            max_financial_amount_cents=overlay.max_financial_amount_cents,
            evaluated_local_time=default_tz_label,
        )

    if overlay.allowed_regions and record_region is not None:
        normalized_region = record_region.strip().upper()
        if normalized_region and normalized_region not in overlay.allowed_regions:
            return AbacEvaluationResult(
                allowed=False,
                reason=(
                    f"Region '{record_region}' is outside allowed ABAC regions "
                    f"({', '.join(regions_tuple)})."
                ),
                blocked_by="region_scope",
                policy_codes=overlay.policy_codes,
                masked_fields=masked_tuple,
                effective_regions=regions_tuple,
                max_financial_amount_cents=overlay.max_financial_amount_cents,
                evaluated_local_time=default_tz_label,
            )

    evaluated_label = default_tz_label
    for window in overlay.write_windows:
        applies = (
            perm_str in window.permissions if window.permissions else is_write_permission(perm_str)
        )
        tz: tzinfo
        try:
            tz = ZoneInfo(window.timezone)
        except ZoneInfoNotFoundError, KeyError, ValueError:
            tz = UTC
        local_dt = now_utc.astimezone(tz)
        evaluated_label = f"{local_dt.strftime('%Y-%m-%d %H:%M')} {window.timezone}"
        if not applies:
            continue
        minute_of_day = local_dt.hour * 60 + local_dt.minute
        weekday = local_dt.isoweekday()
        if weekday not in window.days or not (
            window.start_minute <= minute_of_day < window.end_minute
        ):
            schedule = (
                f"{format_weekdays(window.days)} "
                f"{format_minute_hhmm(window.start_minute)}-"
                f"{format_minute_hhmm(window.end_minute)} {window.timezone}"
            )
            return AbacEvaluationResult(
                allowed=False,
                reason=(
                    f"Write permission '{perm_str}' is restricted to {schedule} "
                    f"(evaluated at {evaluated_label})."
                ),
                blocked_by="time_window",
                policy_codes=overlay.policy_codes,
                masked_fields=masked_tuple,
                effective_regions=regions_tuple,
                max_financial_amount_cents=overlay.max_financial_amount_cents,
                evaluated_local_time=evaluated_label,
            )

    if (
        overlay.max_financial_amount_cents is not None
        and amount_cents is not None
        and amount_cents > overlay.max_financial_amount_cents
    ):
        limit_usd = overlay.max_financial_amount_cents / 100
        actual_usd = amount_cents / 100
        return AbacEvaluationResult(
            allowed=False,
            reason=(f"Amount ${actual_usd:,.2f} exceeds ABAC policy ceiling of ${limit_usd:,.2f}."),
            blocked_by="financial_limit",
            policy_codes=overlay.policy_codes,
            masked_fields=masked_tuple,
            effective_regions=regions_tuple,
            max_financial_amount_cents=overlay.max_financial_amount_cents,
            evaluated_local_time=evaluated_label,
        )

    return AbacEvaluationResult(
        allowed=True,
        reason="Action permitted under active ABAC policy matrix.",
        blocked_by=None,
        policy_codes=overlay.policy_codes,
        masked_fields=masked_tuple,
        effective_regions=regions_tuple,
        max_financial_amount_cents=overlay.max_financial_amount_cents,
        evaluated_local_time=evaluated_label,
    )


def mask_field_value(field_kind: str, value: Any) -> Any:
    """Deterministically mask a single sensitive value according to its field category."""
    if value is None:
        return None
    if field_kind in ("compensation", "unit_cost", "contract_value"):
        return "[REDACTED]"

    text = str(value).strip()
    if not text:
        return ""

    if field_kind == "phone":
        digits = "".join(_DIGITS_RE.findall(text))
        suffix = digits[-4:] if len(digits) >= 4 else "****"
        return f"***-***-{suffix}"

    if field_kind == "email":
        if "@" in text:
            local, domain = text.split("@", 1)
            prefix = local[0] if local else "*"
            return f"{prefix}***@{domain}"
        return "***@***"

    if field_kind == "tax_id":
        alnum = "".join(ch for ch in text if ch.isalnum())
        suffix = alnum[-4:] if len(alnum) >= 4 else "****"
        return f"**-***{suffix}"

    if field_kind == "bank_account":
        alnum = "".join(ch for ch in text if ch.isalnum())
        suffix = alnum[-4:] if len(alnum) >= 4 else "****"
        return f"••••{suffix}"

    return "[REDACTED]"


def apply_abac_field_masking(
    payload: dict[str, Any],
    masked_fields: Iterable[str],
) -> dict[str, Any]:
    """Return a copy of `payload` with all keys matching `masked_fields` redacted."""
    active_kinds = {f for f in masked_fields if f in ALLOWED_MASKED_FIELDS}
    if not active_kinds:
        return dict(payload)

    key_to_kind: dict[str, str] = {}
    for kind in active_kinds:
        for alias in _FIELD_ALIASES.get(kind, ()):
            key_to_kind[alias] = kind

    def _transform(obj: Any) -> Any:
        if isinstance(obj, dict):
            out: dict[str, Any] = {}
            for k, v in obj.items():
                lower_k = str(k).lower()
                if lower_k in key_to_kind:
                    out[k] = mask_field_value(key_to_kind[lower_k], v)
                else:
                    out[k] = _transform(v)
            return out
        if isinstance(obj, list):
            return [_transform(item) for item in obj]
        return obj

    masked = _transform(payload)
    return masked if isinstance(masked, dict) else dict(payload)


async def load_effective_abac_overlay(
    conn: RuntimeConnection,
    tenant_id: UUID,
    user_id: UUID,
) -> EffectiveAbacOverlay | None:
    """Load and merge all active ABAC policies assigned to `(tenant_id, user_id)`.

    Runs inside a SAVEPOINT so pre-0168 schemas degrade gracefully without aborting
    the enclosing authorization transaction.
    """
    try:
        async with conn.transaction(), conn.cursor(row_factory=dict_row) as cur:
            await cur.execute(
                """
                SELECT p.policy_code,
                       p.display_name,
                       p.base_role,
                       p.denied_permissions,
                       p.allowed_regions,
                       p.masked_fields,
                       p.write_window_enabled,
                       p.write_window_timezone,
                       p.write_window_start_minute,
                       p.write_window_end_minute,
                       p.write_window_days,
                       p.write_window_permissions,
                       p.max_financial_amount_cents,
                       a.assigned_regions_override
                FROM gba.abac_user_assignments a
                JOIN gba.abac_policies p
                  ON p.id = a.policy_id AND p.tenant_id = a.tenant_id
                WHERE a.tenant_id = %s
                  AND a.user_id = %s
                  AND a.is_active = true
                  AND p.is_active = true
                ORDER BY p.policy_code ASC
                """,
                (tenant_id, user_id),
            )
            rows = await cur.fetchall()
    except pg_errors.UndefinedTable:
        return None

    if not rows:
        return None

    specs: list[AbacPolicySpec] = []
    for row in rows:
        override_regions = list(row["assigned_regions_override"] or [])
        base_regions = list(row["allowed_regions"] or [])
        effective_regions = override_regions if override_regions else base_regions
        specs.append(
            AbacPolicySpec(
                policy_code=str(row["policy_code"]),
                display_name=str(row["display_name"]),
                base_role=str(row["base_role"]),
                denied_permissions=frozenset(str(x) for x in (row["denied_permissions"] or [])),
                allowed_regions=frozenset(str(x) for x in effective_regions),
                masked_fields=frozenset(str(x) for x in (row["masked_fields"] or [])),
                write_window_enabled=bool(row["write_window_enabled"]),
                write_window_timezone=str(row["write_window_timezone"]),
                write_window_start_minute=int(row["write_window_start_minute"]),
                write_window_end_minute=int(row["write_window_end_minute"]),
                write_window_days=frozenset(int(x) for x in (row["write_window_days"] or [])),
                write_window_permissions=frozenset(
                    str(x) for x in (row["write_window_permissions"] or [])
                ),
                max_financial_amount_cents=(
                    int(row["max_financial_amount_cents"])
                    if row["max_financial_amount_cents"] is not None
                    else None
                ),
            )
        )
    return merge_abac_policies(specs)


ABAC_PRESET_TEMPLATES: tuple[dict[str, Any], ...] = (
    {
        "policy_code": "regional-sales-manager-pii-guard",
        "display_name": "Regional Sales Manager (Midwest · Masked Phones · 09:00-18:00)",
        "description": (
            "Restricts counterparty visibility to Midwest/IL/OH/WI, masks client phone numbers "
            "and tax IDs, enforces Mon-Fri 09:00-18:00 America/Chicago contract edits, and caps "
            "self-approved deals at $50,000."
        ),
        "base_role": "manager",
        "denied_permissions": ["finance.close", "members.manage_admins", "settings.manage"],
        "allowed_regions": ["Midwest", "IL", "OH", "WI"],
        "masked_fields": ["phone", "tax_id"],
        "write_window_enabled": True,
        "write_window_timezone": "America/Chicago",
        "write_window_start_minute": 540,
        "write_window_end_minute": 1080,
        "write_window_days": [1, 2, 3, 4, 5],
        "write_window_permissions": ["counterparties.manage", "documents.manage"],
        "max_financial_amount_cents": 5_000_000,
    },
    {
        "policy_code": "ap-clerk-dual-control",
        "display_name": "AP Specialist (Dual Control · $10k Limit · Business Hours)",
        "description": (
            "Prevents period closing and admin edits, masks employee compensation and bank "
            "accounts, limits financial edits to Mon-Fri 08:00-17:00 Eastern, caps POs at $10k."
        ),
        "base_role": "manager",
        "denied_permissions": [
            "finance.close",
            "members.manage",
            "members.manage_admins",
            "settings.manage",
        ],
        "allowed_regions": [],
        "masked_fields": ["compensation", "bank_account"],
        "write_window_enabled": True,
        "write_window_timezone": "America/New_York",
        "write_window_start_minute": 480,
        "write_window_end_minute": 1020,
        "write_window_days": [1, 2, 3, 4, 5],
        "write_window_permissions": ["finance.manage", "documents.manage"],
        "max_financial_amount_cents": 1_000_000,
    },
    {
        "policy_code": "field-dispatch-afterhours-lock",
        "display_name": "Regional Field & Fleet Dispatcher (South · Cost Masked)",
        "description": (
            "Scopes fleet/workforce visibility to South/TX/LA, hides unit cost, payroll "
            "compensation and contract values, and blocks accounting mutations."
        ),
        "base_role": "manager",
        "denied_permissions": [
            "finance.manage",
            "finance.close",
            "members.manage",
            "settings.manage",
        ],
        "allowed_regions": ["South", "TX", "LA"],
        "masked_fields": ["tax_id", "compensation", "unit_cost", "contract_value"],
        "write_window_enabled": False,
        "write_window_timezone": "America/Chicago",
        "write_window_start_minute": 480,
        "write_window_end_minute": 1200,
        "write_window_days": [1, 2, 3, 4, 5, 6],
        "write_window_permissions": [],
        "max_financial_amount_cents": None,
    },
    {
        "policy_code": "external-cpa-audit-readonly",
        "display_name": "External CPA & Auditor (Read-Only · Masked PII)",
        "description": (
            "Grants audit read access across ledger, banking and holding reports while denying "
            "all mutations and masking personal phone numbers and bank account numbers."
        ),
        "base_role": "manager",
        "denied_permissions": [
            "business.manage",
            "counterparties.manage",
            "documents.manage",
            "finance.manage",
            "finance.close",
            "inventory.manage",
            "members.manage",
            "settings.manage",
        ],
        "allowed_regions": [],
        "masked_fields": ["phone", "bank_account"],
        "write_window_enabled": False,
        "write_window_timezone": "America/New_York",
        "write_window_start_minute": 540,
        "write_window_end_minute": 1080,
        "write_window_days": [1, 2, 3, 4, 5],
        "write_window_permissions": [],
        "max_financial_amount_cents": None,
    },
)
