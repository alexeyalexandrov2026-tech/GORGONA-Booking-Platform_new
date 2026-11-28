"""AMARKAL v2.31.0: Matrix RBAC / ABAC Access Control, PII Field Masking & Time-Window API.

Security & Clean Core invariants:
- Strictly additive restrictive overlay over ADR-0008 ROLE_PERMISSIONS (PERMISSIONS_VERSION = 25).
- Runs under PostgreSQL 18 `ENABLE + FORCE ROW LEVEL SECURITY`; zero SECURITY DEFINER.
- Prevents owner self-lockout from settings/member recovery permissions.
- Every policy change and user assignment writes an immutable entry to `gba.audit_events`.
"""

from __future__ import annotations

import re
from datetime import UTC, datetime
from typing import Any, Literal
from uuid import UUID

from fastapi import APIRouter, HTTPException, Request, status
from psycopg import errors as pg_errors
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from gorgona_booking.api.businesses import CurrentPrincipal
from gorgona_booking.api.deps import runtime_pool
from gorgona_booking.api.request_id import get_request_id
from gorgona_booking.auth.abac import (
    ABAC_PRESET_TEMPLATES,
    ALL_PERMISSION_VALUES,
    ALLOWED_BASE_ROLES,
    ALLOWED_MASKED_FIELDS,
    AbacPolicySpec,
    apply_abac_field_masking,
    evaluate_abac_access,
    format_minute_hhmm,
    format_weekdays,
    load_effective_abac_overlay,
    merge_abac_policies,
    validate_timezone_name,
)
from gorgona_booking.auth.permissions import ROLE_PERMISSIONS, Permission
from gorgona_booking.db.pool import RuntimeConnection
from gorgona_booking.tenancy.authorization import authorized_tenant

router = APIRouter(
    prefix="/v1/businesses/{business_id}/access-control",
    tags=["access-control-abac"],
)

BaseRole = Literal["artist", "front_desk", "manager", "owner"]
_CODE_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{2,62}$")
_CTRL_RE = re.compile(r"[\x00-\x1f\x7f]")

_OWNER_LOCKOUT_PERMS = frozenset(
    {
        str(Permission.SETTINGS_MANAGE),
        str(Permission.MEMBERS_MANAGE),
        str(Permission.MEMBERS_MANAGE_ADMINS),
    }
)


def _clean_text(value: str) -> str:
    cleaned = _CTRL_RE.sub("", value).strip()
    return cleaned


def _dedupe_clean(items: list[str], *, uppercase: bool = False) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for raw in items:
        item = _clean_text(raw)
        if not item:
            continue
        key = item.upper() if uppercase else item
        if key not in seen:
            seen.add(key)
            out.append(item)
    return out


class AbacPolicyView(BaseModel):
    model_config = ConfigDict(frozen=True)
    id: UUID
    policy_code: str
    display_name: str
    description: str
    base_role: BaseRole
    is_active: bool
    denied_permissions: list[str]
    allowed_regions: list[str]
    masked_fields: list[str]
    write_window_enabled: bool
    write_window_timezone: str
    write_window_start_minute: int
    write_window_end_minute: int
    write_window_days: list[int]
    write_window_permissions: list[str]
    write_window_summary: str
    max_financial_amount_cents: int | None
    assigned_member_count: int
    created_at: datetime
    updated_at: datetime


class AbacAssignmentView(BaseModel):
    model_config = ConfigDict(frozen=True)
    id: UUID
    policy_id: UUID
    policy_code: str
    policy_name: str
    user_id: UUID
    member_name: str
    member_email_masked: str | None
    member_role: str
    assigned_regions_override: list[str]
    is_active: bool
    assigned_at: datetime


class AbacMemberSummary(BaseModel):
    model_config = ConfigDict(frozen=True)
    user_id: UUID
    display_name: str
    email_masked: str | None
    role: str
    location_id: UUID | None


class AbacPresetTemplateView(BaseModel):
    model_config = ConfigDict(frozen=True)
    policy_code: str
    display_name: str
    description: str
    base_role: BaseRole
    denied_permissions: list[str]
    allowed_regions: list[str]
    masked_fields: list[str]
    write_window_enabled: bool
    write_window_timezone: str
    write_window_start_minute: int
    write_window_end_minute: int
    write_window_days: list[int]
    write_window_permissions: list[str]
    max_financial_amount_cents: int | None
    installed: bool


class AbacRoleCeilingView(BaseModel):
    model_config = ConfigDict(frozen=True)
    role: BaseRole
    permission_count: int
    sample_permissions: list[str]


class AbacOverviewResponse(BaseModel):
    model_config = ConfigDict(frozen=True)
    policies: list[AbacPolicyView]
    assignments: list[AbacAssignmentView]
    members: list[AbacMemberSummary]
    presets: list[AbacPresetTemplateView]
    role_ceilings: list[AbacRoleCeilingView]
    available_permissions: list[str]
    available_masked_fields: list[str]


class MyEffectivePolicyResponse(BaseModel):
    model_config = ConfigDict(frozen=True)
    base_role: str | None
    has_abac_overlay: bool
    policy_codes: list[str]
    denied_permissions: list[str]
    allowed_regions: list[str]
    masked_fields: list[str]
    write_windows: list[str]
    max_financial_amount_cents: int | None


class CreateAbacPolicyRequest(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    policy_code: str = Field(min_length=3, max_length=63)
    display_name: str = Field(min_length=2, max_length=120)
    description: str = Field(default="", max_length=500)
    base_role: BaseRole = "manager"
    is_active: bool = True
    denied_permissions: list[str] = Field(default_factory=list, max_length=80)
    allowed_regions: list[str] = Field(default_factory=list, max_length=60)
    masked_fields: list[str] = Field(default_factory=list, max_length=16)
    write_window_enabled: bool = False
    write_window_timezone: str = Field(default="America/Chicago", min_length=3, max_length=64)
    write_window_start_minute: int = Field(default=540, ge=0, le=1439)
    write_window_end_minute: int = Field(default=1080, ge=1, le=1440)
    write_window_days: list[int] = Field(default_factory=lambda: [1, 2, 3, 4, 5], max_length=7)
    write_window_permissions: list[str] = Field(default_factory=list, max_length=80)
    max_financial_amount_cents: int | None = Field(default=None, ge=0, le=100_000_000_000)

    @field_validator("policy_code")
    @classmethod
    def check_code(cls, v: str) -> str:
        code = v.strip().lower()
        if not _CODE_RE.fullmatch(code):
            raise ValueError("policy_code must match ^[a-z0-9][a-z0-9_-]{2,62}$")
        return code

    @field_validator("display_name")
    @classmethod
    def check_name(cls, v: str) -> str:
        cleaned = _clean_text(v)
        if len(cleaned) < 2:
            raise ValueError("display_name must have at least 2 characters")
        return cleaned

    @field_validator("description")
    @classmethod
    def check_desc(cls, v: str) -> str:
        return _clean_text(v)

    @field_validator("write_window_timezone")
    @classmethod
    def check_tz(cls, v: str) -> str:
        return validate_timezone_name(v)

    @field_validator("denied_permissions", "write_window_permissions")
    @classmethod
    def check_permissions(cls, v: list[str]) -> list[str]:
        cleaned = _dedupe_clean(v)
        unknown = [p for p in cleaned if p not in ALL_PERMISSION_VALUES]
        if unknown:
            raise ValueError(f"Unknown permissions: {', '.join(unknown[:5])}")
        return cleaned

    @field_validator("masked_fields")
    @classmethod
    def check_masked_fields(cls, v: list[str]) -> list[str]:
        cleaned = _dedupe_clean(v)
        unknown = [f for f in cleaned if f not in ALLOWED_MASKED_FIELDS]
        if unknown:
            raise ValueError(f"Unsupported masked fields: {', '.join(unknown[:5])}")
        return cleaned

    @field_validator("allowed_regions")
    @classmethod
    def check_regions(cls, v: list[str]) -> list[str]:
        cleaned = _dedupe_clean(v, uppercase=True)
        for item in cleaned:
            if len(item) > 40:
                raise ValueError("Each region label must be at most 40 characters")
        return cleaned

    @field_validator("write_window_days")
    @classmethod
    def check_days(cls, v: list[int]) -> list[int]:
        days = sorted({int(d) for d in v})
        if any(d < 1 or d > 7 for d in days):
            raise ValueError("write_window_days must contain ISO weekdays 1..7")
        return days

    @model_validator(mode="after")
    def check_window_bounds(self) -> CreateAbacPolicyRequest:
        if self.write_window_end_minute <= self.write_window_start_minute:
            raise ValueError("write_window_end_minute must be greater than start minute")
        if self.write_window_enabled and not self.write_window_days:
            raise ValueError("Select at least one weekday when write_window_enabled is true")
        return self


class UpdateAbacPolicyRequest(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    display_name: str | None = Field(default=None, min_length=2, max_length=120)
    description: str | None = Field(default=None, max_length=500)
    is_active: bool | None = None
    denied_permissions: list[str] | None = Field(default=None, max_length=80)
    allowed_regions: list[str] | None = Field(default=None, max_length=60)
    masked_fields: list[str] | None = Field(default=None, max_length=16)
    write_window_enabled: bool | None = None
    write_window_timezone: str | None = Field(default=None, min_length=3, max_length=64)
    write_window_start_minute: int | None = Field(default=None, ge=0, le=1439)
    write_window_end_minute: int | None = Field(default=None, ge=1, le=1440)
    write_window_days: list[int] | None = Field(default=None, max_length=7)
    write_window_permissions: list[str] | None = Field(default=None, max_length=80)
    max_financial_amount_cents: int | None = Field(default=None, ge=0, le=100_000_000_000)
    clear_financial_limit: bool = False

    @field_validator("write_window_timezone")
    @classmethod
    def check_tz(cls, v: str | None) -> str | None:
        return None if v is None else validate_timezone_name(v)

    @field_validator("denied_permissions", "write_window_permissions")
    @classmethod
    def check_permissions(cls, v: list[str] | None) -> list[str] | None:
        if v is None:
            return None
        cleaned = _dedupe_clean(v)
        unknown = [p for p in cleaned if p not in ALL_PERMISSION_VALUES]
        if unknown:
            raise ValueError(f"Unknown permissions: {', '.join(unknown[:5])}")
        return cleaned

    @field_validator("masked_fields")
    @classmethod
    def check_masked_fields(cls, v: list[str] | None) -> list[str] | None:
        if v is None:
            return None
        cleaned = _dedupe_clean(v)
        unknown = [f for f in cleaned if f not in ALLOWED_MASKED_FIELDS]
        if unknown:
            raise ValueError(f"Unsupported masked fields: {', '.join(unknown[:5])}")
        return cleaned

    @field_validator("allowed_regions")
    @classmethod
    def check_regions(cls, v: list[str] | None) -> list[str] | None:
        if v is None:
            return None
        return _dedupe_clean(v, uppercase=True)

    @field_validator("write_window_days")
    @classmethod
    def check_days(cls, v: list[int] | None) -> list[int] | None:
        if v is None:
            return None
        days = sorted({int(d) for d in v})
        if any(d < 1 or d > 7 for d in days):
            raise ValueError("write_window_days must contain ISO weekdays 1..7")
        return days


class AssignAbacPolicyRequest(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    policy_id: UUID
    user_id: UUID
    assigned_regions_override: list[str] = Field(default_factory=list, max_length=60)

    @field_validator("assigned_regions_override")
    @classmethod
    def check_regions(cls, v: list[str]) -> list[str]:
        return _dedupe_clean(v, uppercase=True)


class SimulateAbacRequest(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    policy_id: UUID
    permission: str = Field(min_length=3, max_length=80)
    simulated_at_utc: datetime | None = None
    record_region: str | None = Field(default=None, max_length=64)
    amount_cents: int | None = Field(default=None, ge=0, le=100_000_000_000)
    sample_record: dict[str, Any] = Field(
        default_factory=lambda: {
            "client_name": "Midwest Steel Fabricators LLC",
            "region": "Midwest",
            "phone": "+1 (312) 555-4821",
            "email": "cfo@midweststeel.us",
            "tax_id": "36-4829104",
            "bank_account": "US0988124321",
            "contract_value_cents": 4200000,
        }
    )

    @field_validator("permission")
    @classmethod
    def check_perm(cls, v: str) -> str:
        cleaned = v.strip()
        if cleaned not in ALL_PERMISSION_VALUES:
            raise ValueError(f"Unknown permission: {cleaned}")
        return cleaned


class SimulateAbacResponse(BaseModel):
    model_config = ConfigDict(frozen=True)
    policy_code: str
    base_role: BaseRole
    base_role_allows: bool
    allowed: bool
    blocked_by: str | None
    reason: str
    evaluated_local_time: str
    masked_fields: list[str]
    effective_regions: list[str]
    max_financial_amount_cents: int | None
    raw_preview: dict[str, Any]
    masked_preview: dict[str, Any]


def _mask_email_preview(email: str | None) -> str | None:
    if not email or "@" not in email:
        return email
    local, domain = email.split("@", 1)
    prefix = local[0] if local else "*"
    return f"{prefix}***@{domain}"


async def _fetch_all(
    conn: RuntimeConnection,
    sql: str,
    params: tuple[Any, ...],
) -> list[dict[str, Any]]:
    async with conn.cursor(row_factory=dict_row) as cur:
        await cur.execute(sql, params)
        rows = await cur.fetchall()
    return [dict(r) for r in rows]


async def _fetch_one(
    conn: RuntimeConnection,
    sql: str,
    params: tuple[Any, ...],
) -> dict[str, Any] | None:
    async with conn.cursor(row_factory=dict_row) as cur:
        await cur.execute(sql, params)
        row = await cur.fetchone()
    return dict(row) if row is not None else None


def _window_summary(row: dict[str, Any]) -> str:
    if not row["write_window_enabled"]:
        return "24/7 (no time lock)"
    days_label = format_weekdays(row["write_window_days"] or [])
    start_s = format_minute_hhmm(int(row["write_window_start_minute"]))
    end_s = format_minute_hhmm(int(row["write_window_end_minute"]))
    return f"{days_label} {start_s}-{end_s} {row['write_window_timezone']}"


def _row_to_policy_view(row: dict[str, Any]) -> AbacPolicyView:
    role_str = str(row["base_role"])
    base_role: BaseRole = role_str if role_str in ALLOWED_BASE_ROLES else "manager"  # type: ignore[assignment]
    return AbacPolicyView(
        id=row["id"],
        policy_code=str(row["policy_code"]),
        display_name=str(row["display_name"]),
        description=str(row["description"] or ""),
        base_role=base_role,
        is_active=bool(row["is_active"]),
        denied_permissions=[str(x) for x in (row["denied_permissions"] or [])],
        allowed_regions=[str(x) for x in (row["allowed_regions"] or [])],
        masked_fields=[str(x) for x in (row["masked_fields"] or [])],
        write_window_enabled=bool(row["write_window_enabled"]),
        write_window_timezone=str(row["write_window_timezone"]),
        write_window_start_minute=int(row["write_window_start_minute"]),
        write_window_end_minute=int(row["write_window_end_minute"]),
        write_window_days=[int(x) for x in (row["write_window_days"] or [])],
        write_window_permissions=[str(x) for x in (row["write_window_permissions"] or [])],
        write_window_summary=_window_summary(row),
        max_financial_amount_cents=(
            int(row["max_financial_amount_cents"])
            if row["max_financial_amount_cents"] is not None
            else None
        ),
        assigned_member_count=int(row.get("assigned_member_count") or 0),
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


def _row_to_spec(row: dict[str, Any]) -> AbacPolicySpec:
    return AbacPolicySpec(
        policy_code=str(row["policy_code"]),
        display_name=str(row["display_name"]),
        base_role=str(row["base_role"]),
        denied_permissions=frozenset(str(x) for x in (row["denied_permissions"] or [])),
        allowed_regions=frozenset(str(x) for x in (row["allowed_regions"] or [])),
        masked_fields=frozenset(str(x) for x in (row["masked_fields"] or [])),
        write_window_enabled=bool(row["write_window_enabled"]),
        write_window_timezone=str(row["write_window_timezone"]),
        write_window_start_minute=int(row["write_window_start_minute"]),
        write_window_end_minute=int(row["write_window_end_minute"]),
        write_window_days=frozenset(int(x) for x in (row["write_window_days"] or [])),
        write_window_permissions=frozenset(str(x) for x in (row["write_window_permissions"] or [])),
        max_financial_amount_cents=(
            int(row["max_financial_amount_cents"])
            if row["max_financial_amount_cents"] is not None
            else None
        ),
    )


@router.get("/overview", response_model=AbacOverviewResponse)
async def get_access_control_overview(
    business_id: UUID,
    request: Request,
    principal: CurrentPrincipal,
) -> AbacOverviewResponse:
    async with authorized_tenant(
        runtime_pool(request),
        principal,
        business_id,
        Permission.SETTINGS_MANAGE,
        request_id=get_request_id(request),
    ) as access:
        policy_rows = await _fetch_all(
            access.conn,
            """
            SELECT p.*,
                   (SELECT COUNT(*)
                      FROM gba.abac_user_assignments a
                     WHERE a.tenant_id = p.tenant_id
                       AND a.policy_id = p.id
                       AND a.is_active = true) AS assigned_member_count
            FROM gba.abac_policies p
            WHERE p.tenant_id = %s
            ORDER BY p.is_active DESC, p.updated_at DESC
            """,
            (business_id,),
        )

        assignment_rows = await _fetch_all(
            access.conn,
            """
            SELECT a.id,
                   a.policy_id,
                   p.policy_code,
                   p.display_name AS policy_name,
                   a.user_id,
                   COALESCE(u.display_name, 'Team Member') AS member_name,
                   u.email_normalized AS member_email,
                   COALESCE(m.role, 'member') AS member_role,
                   a.assigned_regions_override,
                   a.is_active,
                   a.assigned_at
            FROM gba.abac_user_assignments a
            JOIN gba.abac_policies p
              ON p.id = a.policy_id AND p.tenant_id = a.tenant_id
            LEFT JOIN gba.users u ON u.id = a.user_id
            LEFT JOIN gba.memberships m
              ON m.tenant_id = a.tenant_id AND m.user_id = a.user_id AND m.status = 'active'
            WHERE a.tenant_id = %s
            ORDER BY a.assigned_at DESC
            """,
            (business_id,),
        )

        member_rows = await _fetch_all(
            access.conn,
            """
            SELECT m.user_id,
                   COALESCE(u.display_name, 'Team Member') AS display_name,
                   u.email_normalized AS email_normalized,
                   m.role,
                   m.location_id
            FROM gba.memberships m
            LEFT JOIN gba.users u ON u.id = m.user_id
            WHERE m.tenant_id = %s AND m.status = 'active'
            ORDER BY m.created_at ASC
            """,
            (business_id,),
        )

    policies = [_row_to_policy_view(dict(r)) for r in policy_rows]
    installed_codes = {p.policy_code for p in policies}

    assignments = [
        AbacAssignmentView(
            id=r["id"],
            policy_id=r["policy_id"],
            policy_code=str(r["policy_code"]),
            policy_name=str(r["policy_name"]),
            user_id=r["user_id"],
            member_name=str(r["member_name"]),
            member_email_masked=_mask_email_preview(r["member_email"]),
            member_role=str(r["member_role"]),
            assigned_regions_override=[str(x) for x in (r["assigned_regions_override"] or [])],
            is_active=bool(r["is_active"]),
            assigned_at=r["assigned_at"],
        )
        for r in assignment_rows
    ]

    members = [
        AbacMemberSummary(
            user_id=r["user_id"],
            display_name=str(r["display_name"]),
            email_masked=_mask_email_preview(r["email_normalized"]),
            role=str(r["role"]),
            location_id=r["location_id"],
        )
        for r in member_rows
    ]

    presets = [
        AbacPresetTemplateView(
            policy_code=str(tpl["policy_code"]),
            display_name=str(tpl["display_name"]),
            description=str(tpl["description"]),
            base_role=tpl["base_role"],
            denied_permissions=list(tpl["denied_permissions"]),
            allowed_regions=list(tpl["allowed_regions"]),
            masked_fields=list(tpl["masked_fields"]),
            write_window_enabled=bool(tpl["write_window_enabled"]),
            write_window_timezone=str(tpl["write_window_timezone"]),
            write_window_start_minute=int(tpl["write_window_start_minute"]),
            write_window_end_minute=int(tpl["write_window_end_minute"]),
            write_window_days=list(tpl["write_window_days"]),
            write_window_permissions=list(tpl["write_window_permissions"]),
            max_financial_amount_cents=tpl["max_financial_amount_cents"],
            installed=str(tpl["policy_code"]) in installed_codes,
        )
        for tpl in ABAC_PRESET_TEMPLATES
    ]

    role_ceilings = [
        AbacRoleCeilingView(
            role=role_name,
            permission_count=len(ROLE_PERMISSIONS[role_name]),
            sample_permissions=sorted(str(p) for p in ROLE_PERMISSIONS[role_name])[:10],
        )
        for role_name in ("artist", "front_desk", "manager", "owner")
    ]

    return AbacOverviewResponse(
        policies=policies,
        assignments=assignments,
        members=members,
        presets=presets,
        role_ceilings=role_ceilings,
        available_permissions=sorted(ALL_PERMISSION_VALUES),
        available_masked_fields=sorted(ALLOWED_MASKED_FIELDS),
    )


@router.get("/my-effective-policy", response_model=MyEffectivePolicyResponse)
async def get_my_effective_policy(
    business_id: UUID,
    request: Request,
    principal: CurrentPrincipal,
) -> MyEffectivePolicyResponse:
    async with authorized_tenant(
        runtime_pool(request),
        principal,
        business_id,
        Permission.BUSINESS_READ,
        request_id=get_request_id(request),
        allow_location_scope=True,
    ) as access:
        overlay = access.abac or await load_effective_abac_overlay(
            access.conn, business_id, principal.user_id
        )
        base_role = access.role

    if overlay is None:
        return MyEffectivePolicyResponse(
            base_role=base_role,
            has_abac_overlay=False,
            policy_codes=[],
            denied_permissions=[],
            allowed_regions=[],
            masked_fields=[],
            write_windows=[],
            max_financial_amount_cents=None,
        )

    windows = [
        (
            f"{format_weekdays(w.days)} "
            f"{format_minute_hhmm(w.start_minute)}-{format_minute_hhmm(w.end_minute)} "
            f"{w.timezone}"
        )
        for w in overlay.write_windows
    ]
    return MyEffectivePolicyResponse(
        base_role=base_role,
        has_abac_overlay=True,
        policy_codes=list(overlay.policy_codes),
        denied_permissions=sorted(overlay.denied_permissions),
        allowed_regions=sorted(overlay.allowed_regions),
        masked_fields=sorted(overlay.masked_fields),
        write_windows=windows,
        max_financial_amount_cents=overlay.max_financial_amount_cents,
    )


@router.post("/policies", response_model=AbacPolicyView, status_code=status.HTTP_201_CREATED)
async def create_abac_policy(
    business_id: UUID,
    body: CreateAbacPolicyRequest,
    request: Request,
    principal: CurrentPrincipal,
) -> AbacPolicyView:
    async with authorized_tenant(
        runtime_pool(request),
        principal,
        business_id,
        Permission.SETTINGS_MANAGE,
        request_id=get_request_id(request),
    ) as access:
        try:
            row = await _fetch_one(
                access.conn,
                """
                INSERT INTO gba.abac_policies (
                    tenant_id, policy_code, display_name, description, base_role,
                    is_active, denied_permissions, allowed_regions, masked_fields,
                    write_window_enabled, write_window_timezone,
                    write_window_start_minute, write_window_end_minute,
                    write_window_days, write_window_permissions,
                    max_financial_amount_cents, created_by_user_id
                ) VALUES (
                    %s, %s, %s, %s, %s,
                    %s, %s, %s, %s,
                    %s, %s,
                    %s, %s,
                    %s, %s,
                    %s, %s
                )
                RETURNING *, 0::bigint AS assigned_member_count
                """,
                (
                    business_id,
                    body.policy_code,
                    body.display_name,
                    body.description,
                    body.base_role,
                    body.is_active,
                    body.denied_permissions,
                    body.allowed_regions,
                    body.masked_fields,
                    body.write_window_enabled,
                    body.write_window_timezone,
                    body.write_window_start_minute,
                    body.write_window_end_minute,
                    body.write_window_days,
                    body.write_window_permissions,
                    body.max_financial_amount_cents,
                    access.principal.user_id,
                ),
            )
        except pg_errors.UniqueViolation as exc:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"ABAC policy code '{body.policy_code}' already exists.",
            ) from exc

        assert row is not None  # noqa: S101
        await access.conn.execute(
            """
            INSERT INTO gba.audit_events (
                tenant_id, actor, action, target_type, target_id, details, request_id
            ) VALUES (
                %s, %s, 'abac.policy_created', 'abac_policy', %s, %s,
                nullif(pg_catalog.current_setting('gba.request_id', true), '')
            )
            """,
            (
                business_id,
                access.principal.actor,
                str(row["id"]),
                Jsonb({"policy_code": body.policy_code, "base_role": body.base_role}),
            ),
        )
        return _row_to_policy_view(dict(row))


@router.post("/presets/{preset_code}", response_model=AbacPolicyView, status_code=201)
async def install_abac_preset(
    business_id: UUID,
    preset_code: str,
    request: Request,
    principal: CurrentPrincipal,
) -> AbacPolicyView:
    template = next(
        (tpl for tpl in ABAC_PRESET_TEMPLATES if tpl["policy_code"] == preset_code),
        None,
    )
    if template is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Unknown ABAC preset '{preset_code}'.",
        )
    req_body = CreateAbacPolicyRequest.model_validate(template)
    return await create_abac_policy(business_id, req_body, request, principal)


@router.patch("/policies/{policy_id}", response_model=AbacPolicyView)
async def update_abac_policy(
    business_id: UUID,
    policy_id: UUID,
    body: UpdateAbacPolicyRequest,
    request: Request,
    principal: CurrentPrincipal,
) -> AbacPolicyView:
    async with authorized_tenant(
        runtime_pool(request),
        principal,
        business_id,
        Permission.SETTINGS_MANAGE,
        request_id=get_request_id(request),
    ) as access:
        existing = await _fetch_one(
            access.conn,
            "SELECT * FROM gba.abac_policies WHERE tenant_id = %s AND id = %s FOR UPDATE",
            (business_id, policy_id),
        )
        if existing is None:
            raise HTTPException(status_code=404, detail="ABAC policy not found.")

        new_start = (
            body.write_window_start_minute
            if body.write_window_start_minute is not None
            else int(existing["write_window_start_minute"])
        )
        new_end = (
            body.write_window_end_minute
            if body.write_window_end_minute is not None
            else int(existing["write_window_end_minute"])
        )
        if new_end <= new_start:
            raise HTTPException(
                status_code=422,
                detail="write_window_end_minute must be greater than write_window_start_minute.",
            )

        new_limit = (
            None
            if body.clear_financial_limit
            else (
                body.max_financial_amount_cents
                if body.max_financial_amount_cents is not None
                else existing["max_financial_amount_cents"]
            )
        )

        row = await _fetch_one(
            access.conn,
            """
            UPDATE gba.abac_policies
            SET display_name = %s,
                description = %s,
                is_active = %s,
                denied_permissions = %s,
                allowed_regions = %s,
                masked_fields = %s,
                write_window_enabled = %s,
                write_window_timezone = %s,
                write_window_start_minute = %s,
                write_window_end_minute = %s,
                write_window_days = %s,
                write_window_permissions = %s,
                max_financial_amount_cents = %s,
                updated_at = now()
            WHERE tenant_id = %s AND id = %s
            RETURNING *,
                      (SELECT COUNT(*)
                         FROM gba.abac_user_assignments a
                        WHERE a.tenant_id = gba.abac_policies.tenant_id
                          AND a.policy_id = gba.abac_policies.id
                          AND a.is_active = true) AS assigned_member_count
            """,
            (
                _clean_text(body.display_name)
                if body.display_name is not None
                else existing["display_name"],
                _clean_text(body.description)
                if body.description is not None
                else existing["description"],
                body.is_active if body.is_active is not None else existing["is_active"],
                (
                    body.denied_permissions
                    if body.denied_permissions is not None
                    else existing["denied_permissions"]
                ),
                (
                    body.allowed_regions
                    if body.allowed_regions is not None
                    else existing["allowed_regions"]
                ),
                (
                    body.masked_fields
                    if body.masked_fields is not None
                    else existing["masked_fields"]
                ),
                (
                    body.write_window_enabled
                    if body.write_window_enabled is not None
                    else existing["write_window_enabled"]
                ),
                (
                    body.write_window_timezone
                    if body.write_window_timezone is not None
                    else existing["write_window_timezone"]
                ),
                new_start,
                new_end,
                (
                    body.write_window_days
                    if body.write_window_days is not None
                    else existing["write_window_days"]
                ),
                (
                    body.write_window_permissions
                    if body.write_window_permissions is not None
                    else existing["write_window_permissions"]
                ),
                new_limit,
                business_id,
                policy_id,
            ),
        )
        assert row is not None  # noqa: S101
        return _row_to_policy_view(dict(row))


@router.delete("/policies/{policy_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_abac_policy(
    business_id: UUID,
    policy_id: UUID,
    request: Request,
    principal: CurrentPrincipal,
) -> None:
    async with authorized_tenant(
        runtime_pool(request),
        principal,
        business_id,
        Permission.SETTINGS_MANAGE,
        request_id=get_request_id(request),
    ) as access:
        cur = await access.conn.execute(
            "DELETE FROM gba.abac_policies WHERE tenant_id = %s AND id = %s",
            (business_id, policy_id),
        )
        if cur.rowcount == 0:
            raise HTTPException(status_code=404, detail="ABAC policy not found.")


@router.post("/assignments", response_model=AbacAssignmentView, status_code=201)
async def assign_abac_policy(
    business_id: UUID,
    body: AssignAbacPolicyRequest,
    request: Request,
    principal: CurrentPrincipal,
) -> AbacAssignmentView:
    async with authorized_tenant(
        runtime_pool(request),
        principal,
        business_id,
        Permission.SETTINGS_MANAGE,
        request_id=get_request_id(request),
    ) as access:
        policy = await _fetch_one(
            access.conn,
            "SELECT id, policy_code, display_name, denied_permissions "
            "FROM gba.abac_policies WHERE tenant_id = %s AND id = %s",
            (business_id, body.policy_id),
        )
        if policy is None:
            raise HTTPException(status_code=404, detail="ABAC policy not found.")

        member = await _fetch_one(
            access.conn,
            """
            SELECT m.user_id,
                   m.role,
                   COALESCE(u.display_name, 'Team Member') AS display_name,
                   u.email_normalized
            FROM gba.memberships m
            LEFT JOIN gba.users u ON u.id = m.user_id
            WHERE m.tenant_id = %s AND m.user_id = %s AND m.status = 'active'
            """,
            (business_id, body.user_id),
        )
        if member is None:
            raise HTTPException(status_code=404, detail="Active team member not found.")

        denied_set = {str(x) for x in (policy["denied_permissions"] or [])}
        if (
            body.user_id == access.principal.user_id
            and str(member["role"]) == "owner"
            and bool(denied_set & _OWNER_LOCKOUT_PERMS)
        ):
            raise HTTPException(
                status_code=409,
                detail="Cannot assign a policy that blocks your own owner recovery permissions.",
            )

        row = await _fetch_one(
            access.conn,
            """
            INSERT INTO gba.abac_user_assignments (
                tenant_id, policy_id, user_id, assigned_regions_override,
                is_active, assigned_by_user_id
            ) VALUES (%s, %s, %s, %s, true, %s)
            ON CONFLICT (tenant_id, policy_id, user_id)
            DO UPDATE SET
                assigned_regions_override = EXCLUDED.assigned_regions_override,
                is_active = true,
                updated_at = now()
            RETURNING id, policy_id, user_id, assigned_regions_override, is_active, assigned_at
            """,
            (
                business_id,
                body.policy_id,
                body.user_id,
                body.assigned_regions_override,
                access.principal.user_id,
            ),
        )
        assert row is not None  # noqa: S101

        await access.conn.execute(
            """
            INSERT INTO gba.audit_events (
                tenant_id, actor, action, target_type, target_id, details, request_id
            ) VALUES (
                %s, %s, 'abac.policy_assigned', 'abac_assignment', %s, %s,
                nullif(pg_catalog.current_setting('gba.request_id', true), '')
            )
            """,
            (
                business_id,
                access.principal.actor,
                str(row["id"]),
                Jsonb(
                    {
                        "policy_code": str(policy["policy_code"]),
                        "target_user_id": str(body.user_id),
                    }
                ),
            ),
        )

        return AbacAssignmentView(
            id=row["id"],
            policy_id=row["policy_id"],
            policy_code=str(policy["policy_code"]),
            policy_name=str(policy["display_name"]),
            user_id=row["user_id"],
            member_name=str(member["display_name"]),
            member_email_masked=_mask_email_preview(member["email_normalized"]),
            member_role=str(member["role"]),
            assigned_regions_override=[str(x) for x in (row["assigned_regions_override"] or [])],
            is_active=bool(row["is_active"]),
            assigned_at=row["assigned_at"],
        )


@router.delete("/assignments/{assignment_id}", status_code=status.HTTP_204_NO_CONTENT)
async def revoke_abac_assignment(
    business_id: UUID,
    assignment_id: UUID,
    request: Request,
    principal: CurrentPrincipal,
) -> None:
    async with authorized_tenant(
        runtime_pool(request),
        principal,
        business_id,
        Permission.SETTINGS_MANAGE,
        request_id=get_request_id(request),
    ) as access:
        cur = await access.conn.execute(
            "DELETE FROM gba.abac_user_assignments WHERE tenant_id = %s AND id = %s",
            (business_id, assignment_id),
        )
        if cur.rowcount == 0:
            raise HTTPException(status_code=404, detail="ABAC assignment not found.")


@router.post("/simulate", response_model=SimulateAbacResponse)
async def simulate_abac_policy(
    business_id: UUID,
    body: SimulateAbacRequest,
    request: Request,
    principal: CurrentPrincipal,
) -> SimulateAbacResponse:
    async with authorized_tenant(
        runtime_pool(request),
        principal,
        business_id,
        Permission.SETTINGS_MANAGE,
        request_id=get_request_id(request),
    ) as access:
        row = await _fetch_one(
            access.conn,
            "SELECT * FROM gba.abac_policies WHERE tenant_id = %s AND id = %s",
            (business_id, body.policy_id),
        )
        if row is None:
            raise HTTPException(status_code=404, detail="ABAC policy not found.")

    spec = _row_to_spec(dict(row))
    base_role_str = spec.base_role
    base_role: BaseRole = base_role_str if base_role_str in ALLOWED_BASE_ROLES else "manager"  # type: ignore[assignment]
    perm_enum = Permission(body.permission)
    base_allows = perm_enum in ROLE_PERMISSIONS[base_role]
    overlay = merge_abac_policies([spec])
    sim_time = body.simulated_at_utc or datetime.now(UTC)

    if not base_allows:
        return SimulateAbacResponse(
            policy_code=spec.policy_code,
            base_role=base_role,
            base_role_allows=False,
            allowed=False,
            blocked_by="base_role_ceiling",
            reason=(
                f"Base role '{base_role}' does not grant '{body.permission}' "
                "(ABAC overlays can only narrow, never elevate base permissions)."
            ),
            evaluated_local_time=sim_time.astimezone(UTC).strftime("%Y-%m-%d %H:%M UTC"),
            masked_fields=sorted(spec.masked_fields),
            effective_regions=sorted(spec.allowed_regions),
            max_financial_amount_cents=spec.max_financial_amount_cents,
            raw_preview=dict(body.sample_record),
            masked_preview=apply_abac_field_masking(body.sample_record, spec.masked_fields),
        )

    decision = evaluate_abac_access(
        overlay,
        perm_enum,
        at_utc=sim_time,
        record_region=body.record_region,
        amount_cents=body.amount_cents,
    )
    masked_preview = apply_abac_field_masking(body.sample_record, decision.masked_fields)
    return SimulateAbacResponse(
        policy_code=spec.policy_code,
        base_role=base_role,
        base_role_allows=True,
        allowed=decision.allowed,
        blocked_by=decision.blocked_by,
        reason=decision.reason,
        evaluated_local_time=decision.evaluated_local_time,
        masked_fields=list(decision.masked_fields),
        effective_regions=list(decision.effective_regions),
        max_financial_amount_cents=decision.max_financial_amount_cents,
        raw_preview=dict(body.sample_record),
        masked_preview=masked_preview,
    )
