"""Self-service business registration and workspace setup (zero admin involvement).

Any authenticated OIDC caller with a verified identity can register a new company,
select one or more of the 39 industries, configure its initial branch and timezone,
and receive an active owner workspace with a validated, published v1 configuration
containing only technically verified modules.
"""

import hashlib
import json
from typing import Literal
from uuid import UUID, uuid7

from psycopg import errors as pg
from psycopg.types.json import Jsonb
from pydantic import BaseModel, ConfigDict, Field, field_validator

from gorgona_booking.auth.principal import (
    linked_user_id,
    set_identity_context,
    set_user_context,
)
from gorgona_booking.auth.verifier import VerifiedToken
from gorgona_booking.booking.models import IdempotencyKeyReusedError
from gorgona_booking.business import configurations
from gorgona_booking.business.catalog import CATALOG_VERSION, INDUSTRY_IDS, BusinessFormat
from gorgona_booking.business.configuration_contracts import (
    ConfigurationCommand,
    ConfigurationDraftInput,
)
from gorgona_booking.business.contracts import ProfileInput
from gorgona_booking.business.modules import CORE_MODULE_IDS, MODULES_BY_ID
from gorgona_booking.business.onboarding_presets import resolve_onboarding_modules
from gorgona_booking.business.service import save_profile
from gorgona_booking.db.pool import RuntimeConnection, RuntimePool, set_tenant_context
from gorgona_booking.db.provisioning import normalize_email
from gorgona_booking.errors import ConflictError, DomainError
from gorgona_booking.onboarding.ai_architect import (
    BlueprintHoursItem,
    BlueprintResourceItem,
    BlueprintServiceItem,
)

SLUG_PATTERN = r"^[a-z0-9]+(-[a-z0-9]+)*$"


class SelfServiceOnboardingError(DomainError):
    code = "ONBOARDING_INVALID"


class SelfServiceBusinessInput(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    business_name: str = Field(min_length=1, max_length=200)
    slug: str = Field(min_length=2, max_length=63, pattern=SLUG_PATTERN)
    location_name: str = Field(min_length=1, max_length=200)
    timezone: str = Field(min_length=3, max_length=100)
    industry_ids: tuple[int, ...] = Field(min_length=1, max_length=39)
    business_formats: tuple[BusinessFormat, ...] = Field(
        default=(BusinessFormat.B2C,), max_length=5
    )
    custom_activity_name: str | None = Field(default=None, max_length=200)
    module_ids: tuple[str, ...] | None = None
    starter_services: tuple[BlueprintServiceItem, ...] = Field(default=(), max_length=12)
    starter_resources: tuple[BlueprintResourceItem, ...] = Field(default=(), max_length=8)
    starter_hours: tuple[BlueprintHoursItem, ...] = Field(default=(), max_length=7)
    cancellation_summary: str | None = Field(default=None, max_length=300)

    @field_validator("business_name", "location_name")
    @classmethod
    def _non_blank(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("must not be blank")
        return stripped

    @field_validator("custom_activity_name")
    @classmethod
    def _clean_custom(cls, value: str | None) -> str | None:
        if value is None:
            return None
        stripped = value.strip()
        if not stripped:
            raise ValueError("custom_activity_name must not be blank")
        return stripped

    @field_validator("industry_ids")
    @classmethod
    def _valid_industries(cls, value: tuple[int, ...]) -> tuple[int, ...]:
        if len(set(value)) != len(value):
            raise ValueError("duplicate industry_ids are not allowed")
        unknown = [i for i in value if i not in INDUSTRY_IDS]
        if unknown:
            raise ValueError(f"unknown industry_ids: {unknown}")
        return tuple(sorted(value))

    @field_validator("business_formats")
    @classmethod
    def _unique_formats(cls, value: tuple[BusinessFormat, ...]) -> tuple[BusinessFormat, ...]:
        if len(set(value)) != len(value):
            raise ValueError("duplicate business_formats are not allowed")
        return value

    @field_validator("module_ids")
    @classmethod
    def _valid_modules(cls, value: tuple[str, ...] | None) -> tuple[str, ...] | None:
        if value is None:
            return None
        if len(set(value)) != len(value):
            raise ValueError("duplicate module_ids are not allowed")
        for mid in value:
            mod = MODULES_BY_ID.get(mid)
            if mod is None:
                raise ValueError(f"unknown module_id: {mid}")
            if mid in CORE_MODULE_IDS:
                raise ValueError(f"core module {mid} is always enabled and should not be listed")
            if not mod.enableable:
                raise ValueError(f"module {mid} is {mod.readiness.value} and cannot be enabled yet")
        return tuple(sorted(value))


class OnboardingMembershipSummary(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    business_id: UUID
    business_name: str
    role: str
    status: str


class OnboardingStatusView(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    linked: bool
    user_id: UUID | None
    display_name: str
    email: str | None
    can_create_business: bool
    businesses: tuple[OnboardingMembershipSummary, ...]


class SelfServiceBusinessResult(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    schema_version: Literal[1] = 1
    business_id: UUID
    slug: str
    business_name: str
    location_id: UUID
    location_name: str
    timezone: str
    user_id: UUID
    membership_id: UUID
    role: Literal["owner"] = "owner"
    profile_revision: int
    configuration_version: int
    industry_ids: tuple[int, ...]
    effective_module_ids: tuple[str, ...]
    pending_module_ids: tuple[str, ...]
    created_services_count: int = 0
    created_resources_count: int = 0
    created_hours_count: int = 0


def _request_hash(body: SelfServiceBusinessInput) -> str:
    payload = body.model_dump(mode="json")
    payload["industry_ids"] = sorted(body.industry_ids)
    payload["business_formats"] = sorted(str(f) for f in body.business_formats)
    if body.module_ids is not None:
        payload["module_ids"] = sorted(body.module_ids)
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode("utf-8")).hexdigest()


class _IdentityRaceError(Exception):
    pass


async def _ensure_user(conn: RuntimeConnection, token: VerifiedToken) -> UUID:
    existing = await linked_user_id(conn, token)
    if existing is not None:
        return existing
    user_id = uuid7()
    display = (token.name or (token.email or "").split("@")[0] or "Business Owner")[:200]
    try:
        async with conn.transaction():
            await set_user_context(conn, user_id)
            await conn.execute(
                "insert into gba.users (id, display_name, email_normalized) values (%s, %s, %s)",
                (user_id, display, normalize_email(token.email) if token.email else None),
            )
            cur = await conn.execute(
                "insert into gba.user_identities (user_id, issuer, subject) values (%s, %s, %s) "
                "on conflict (issuer, subject) do nothing",
                (user_id, token.issuer, token.subject),
            )
            if cur.rowcount != 1:
                raise _IdentityRaceError
    except _IdentityRaceError:
        raced = await linked_user_id(conn, token)
        if raced is None:
            raise ConflictError("Sign-in could not be linked; please retry") from None
        return raced
    return user_id


async def get_onboarding_status(pool: RuntimePool, token: VerifiedToken) -> OnboardingStatusView:
    async with pool.connection() as conn, conn.transaction():
        user_id = await linked_user_id(conn, token)
        if user_id is None:
            display = (token.name or (token.email or "").split("@")[0] or "New user")[:200]
            return OnboardingStatusView(
                linked=False,
                user_id=None,
                display_name=display,
                email=token.email,
                can_create_business=True,
                businesses=(),
            )
        await set_user_context(conn, user_id)
        u_row = await (
            await conn.execute("select display_name from gba.users where id = %s", (user_id,))
        ).fetchone()
        display = str(u_row[0]) if u_row else (token.name or "User")
        rows = await (
            await conn.execute(
                "select m.tenant_id, t.display_name, m.role, m.status "
                "from gba.memberships m join gba.tenants t on t.id = m.tenant_id "
                "where m.user_id = %s and m.status = 'active' order by m.created_at",
                (user_id,),
            )
        ).fetchall()
        businesses = tuple(
            OnboardingMembershipSummary(
                business_id=UUID(str(r[0])),
                business_name=str(r[1]),
                role=str(r[2]),
                status=str(r[3]),
            )
            for r in rows
        )
        return OnboardingStatusView(
            linked=True,
            user_id=user_id,
            display_name=display,
            email=token.email,
            can_create_business=True,
            businesses=businesses,
        )


async def register_business(
    pool: RuntimePool,
    token: VerifiedToken,
    *,
    body: SelfServiceBusinessInput,
    key: str,
    request_id: str | None = None,
) -> SelfServiceBusinessResult:
    req_hash = _request_hash(body)
    preset = resolve_onboarding_modules(body.industry_ids)
    selected_modules = (
        body.module_ids if body.module_ids is not None else preset.enableable_module_ids
    )
    pending_modules = preset.pending_module_ids

    async with pool.connection() as conn, conn.transaction():
        await set_identity_context(conn, token)
        # Serialize concurrent onboarding calls for the same caller + key
        await conn.execute(
            "select pg_catalog.pg_advisory_xact_lock(pg_catalog.hashtextextended(%s, 0))",
            (f"gba:self-service:{token.issuer}:{token.subject}:{key}",),
        )
        prev = await (
            await conn.execute(
                "select request_hash, response_body from gba.self_service_signups "
                "where issuer = %s and subject = %s and idempotency_key = %s",
                (token.issuer, token.subject, key),
            )
        ).fetchone()
        if prev is not None:
            if str(prev[0]) != req_hash:
                raise IdempotencyKeyReusedError(
                    "This idempotency key was already used with different business details"
                )
            if prev[1] is not None:
                return SelfServiceBusinessResult.model_validate(prev[1])

        user_id = await _ensure_user(conn, token)
        actor = f"user:{user_id}"
        tenant_id = uuid7()
        location_id = uuid7()

        await set_user_context(conn, user_id, request_id=request_id)
        await set_tenant_context(conn, tenant_id)

        # Record the self-service signup row first so the RESTRICTIVE RLS policy on
        # gba.tenants validates caller ownership without elevated privileges.
        await conn.execute(
            "insert into gba.self_service_signups "
            "(issuer, subject, idempotency_key, request_hash, user_id, tenant_id, location_id) "
            "values (%s, %s, %s, %s, %s, %s, %s)",
            (token.issuer, token.subject, key, req_hash, user_id, tenant_id, location_id),
        )

        try:
            async with conn.transaction():
                await conn.execute(
                    "insert into gba.tenants (id, slug, display_name, status, booking_state) "
                    "values (%s, %s, %s, 'active', 'not_live')",
                    (tenant_id, body.slug, body.business_name),
                )
        except pg.UniqueViolation:
            raise ConflictError(
                "This business slug is already taken. Choose a different URL slug."
            ) from None

        try:
            async with conn.transaction():
                await conn.execute(
                    "insert into gba.locations (tenant_id, id, name, timezone) "
                    "values (%s, %s, %s, %s)",
                    (tenant_id, location_id, body.location_name, body.timezone),
                )
        except pg.InvalidParameterValue, pg.CheckViolation:
            raise SelfServiceOnboardingError(f"Invalid IANA timezone: {body.timezone}") from None

        mem_row = await (
            await conn.execute(
                "insert into gba.memberships (tenant_id, user_id, role, status, location_id) "
                "values (%s, %s, 'owner', 'active', null) returning id",
                (tenant_id, user_id),
            )
        ).fetchone()
        assert mem_row is not None  # noqa: S101
        membership_id = UUID(str(mem_row[0]))

        # Save v1 business profile with all selected industries & formats
        profile = await save_profile(
            conn,
            business_id=tenant_id,
            user_id=user_id,
            actor=actor,
            key=f"ss-prof-{key}"[:120],
            body=ProfileInput(
                expected_revision=0,
                catalog_version=CATALOG_VERSION,
                industry_ids=body.industry_ids,
                business_formats=body.business_formats,
                custom_activity_name=body.custom_activity_name,
            ),
        )

        # Draft, validate, and publish v1 configuration with only verified modules
        drafted = await configurations.save_draft(
            conn,
            business_id=tenant_id,
            user_id=user_id,
            actor=actor,
            key=f"ss-draft-{key}"[:120],
            body=ConfigurationDraftInput(
                expected_version=0,
                profile_revision=profile.revision,
                module_ids=selected_modules,
            ),
        )
        validated = await configurations.validate_version(
            conn,
            business_id=tenant_id,
            version=drafted.version,
            user_id=user_id,
            actor=actor,
            key=f"ss-val-{key}"[:120],
            body=ConfigurationCommand(expected_revision=drafted.revision),
        )
        published = await configurations.publish_version(
            conn,
            business_id=tenant_id,
            version=drafted.version,
            user_id=user_id,
            actor=actor,
            key=f"ss-pub-{key}"[:120],
            body=ConfigurationCommand(expected_revision=validated.revision),
        )

        effective = (*CORE_MODULE_IDS, *sorted(selected_modules))

        # Apply human-approved AI Architect starter blueprint inside the same atomic PG18 tx
        created_service_ids: list[UUID] = []
        created_resource_ids: list[UUID] = []
        created_hours_count = 0
        for svc in body.starter_services:
            service_id = uuid7()
            variant_id = uuid7()
            await conn.execute(
                "insert into gba.services (tenant_id, id, code, name) values (%s, %s, %s, %s)",
                (tenant_id, service_id, svc.code, svc.name),
            )
            await conn.execute(
                "insert into gba.service_variants "
                "(tenant_id, id, service_id, code, name, status, price_cents, currency, "
                "booking_duration_minutes, is_bookable) "
                "values (%s, %s, %s, %s, %s, 'published', %s, %s, %s, true)",
                (
                    tenant_id,
                    variant_id,
                    service_id,
                    f"{svc.code[:58]}_STD",
                    f"{svc.name} (Standard)"[:200],
                    svc.price_cents,
                    svc.currency,
                    svc.duration_minutes,
                ),
            )
            created_service_ids.append(service_id)

        for res_item in body.starter_resources:
            res_id = uuid7()
            await conn.execute(
                "insert into gba.resources (tenant_id, id, location_id, kind, display_name) "
                "values (%s, %s, %s, %s, %s)",
                (tenant_id, res_id, location_id, res_item.kind, res_item.display_name),
            )
            created_resource_ids.append(res_id)

        for res_id in created_resource_ids:
            for service_id in created_service_ids:
                await conn.execute(
                    "insert into gba.resource_services (tenant_id, resource_id, service_id) "
                    "values (%s, %s, %s) on conflict do nothing",
                    (tenant_id, res_id, service_id),
                )

        for hr in body.starter_hours:
            if hr.closes_minute <= hr.opens_minute:
                continue
            await conn.execute(
                "insert into gba.business_hours "
                "(tenant_id, id, location_id, weekday, opens_minute, closes_minute) "
                "values (%s, %s, %s, %s, %s, %s)",
                (tenant_id, uuid7(), location_id, hr.weekday, hr.opens_minute, hr.closes_minute),
            )
            created_hours_count += 1
            for res_id in created_resource_ids:
                await conn.execute(
                    "insert into gba.resource_hours "
                    "(tenant_id, resource_id, weekday, opens_minute, closes_minute) "
                    "values (%s, %s, %s, %s, %s)",
                    (tenant_id, res_id, hr.weekday, hr.opens_minute, hr.closes_minute),
                )

        if body.cancellation_summary and body.cancellation_summary.strip():
            await conn.execute(
                "insert into gba.salon_policies (tenant_id, cancellation_policy) "
                "values (%s, %s) "
                "on conflict (tenant_id) do update set "
                "cancellation_policy = excluded.cancellation_policy, updated_at = now()",
                (
                    tenant_id,
                    Jsonb({"version": 1, "summary": body.cancellation_summary.strip()}),
                ),
            )

        await conn.execute(
            "insert into gba.audit_events "
            "(tenant_id, actor, action, target_type, target_id, details, request_id) "
            "values (%s, %s, 'onboarding.business_registered', 'tenant', %s, %s, "
            "nullif(pg_catalog.current_setting('gba.request_id', true), ''))",
            (
                tenant_id,
                actor,
                str(tenant_id),
                Jsonb(
                    {
                        "slug": body.slug,
                        "industry_ids": list(body.industry_ids),
                        "effective_module_ids": list(effective),
                        "pending_module_ids": list(pending_modules),
                        "created_services_count": len(created_service_ids),
                        "created_resources_count": len(created_resource_ids),
                        "created_hours_count": created_hours_count,
                    }
                ),
            ),
        )

        result = SelfServiceBusinessResult(
            business_id=tenant_id,
            slug=body.slug,
            business_name=body.business_name,
            location_id=location_id,
            location_name=body.location_name,
            timezone=body.timezone,
            user_id=user_id,
            membership_id=membership_id,
            profile_revision=profile.revision,
            configuration_version=published.version,
            industry_ids=body.industry_ids,
            effective_module_ids=effective,
            pending_module_ids=pending_modules,
            created_services_count=len(created_service_ids),
            created_resources_count=len(created_resource_ids),
            created_hours_count=created_hours_count,
        )
        await conn.execute(
            "update gba.self_service_signups set response_body = %s "
            "where issuer = %s and subject = %s and idempotency_key = %s",
            (Jsonb(result.model_dump(mode="json")), token.issuer, token.subject, key),
        )
        return result
