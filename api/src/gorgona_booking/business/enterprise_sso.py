"""ENTERPRISE-01 Slice 1 (ADR-0041): Corporate SSO identity providers, SCIM-style employee
directory links, and atomic employee lifecycle deprovisioning that immediately suspends
business membership and revokes active delegations.
"""

from typing import Any, Literal
from uuid import UUID, uuid7

from psycopg import errors
from psycopg.types.json import Jsonb
from pydantic import AwareDatetime, Field, field_validator

from gorgona_booking.booking.idempotency import IdempotencyScope
from gorgona_booking.business import commands, modules
from gorgona_booking.business.contracts import Strict, Versioned
from gorgona_booking.business.module_gate import module_writes, require_module
from gorgona_booking.business.readiness_registry import at_least
from gorgona_booking.db.pool import RuntimeConnection
from gorgona_booking.errors import ConflictError, InvalidReferenceError, NotFoundError

ANALYTICS_MODULE = "analytics"

SsoProtocol = Literal["oidc", "saml"]
SsoProviderStatus = Literal["active", "disabled"]
DirectoryLinkStatus = Literal["active", "deprovisioned"]
LifecycleEventKind = Literal["provisioned", "deprovisioned"]


class EnterpriseNotReadyError(ConflictError):
    code = "MODULE_NOT_READY"


class EnterpriseRevisionConflictError(ConflictError):
    code = "ENTERPRISE_REVISION_CONFLICT"


class EnterpriseStateError(ConflictError):
    code = "ENTERPRISE_STATE_INVALID"


def _check_ready() -> None:
    mod = modules.MODULES_BY_ID[ANALYTICS_MODULE]
    if not mod.enableable or not at_least(mod.readiness, modules.MINIMUM_READINESS):
        raise EnterpriseNotReadyError(
            "Analytics/Enterprise module is not enabled for production writes",
            module_id=ANALYTICS_MODULE,
        )


def _clean_code(value: str) -> str:
    clean = value.strip().upper()
    if len(clean) < 2 or len(clean) > 64:
        raise ValueError("Code must be 2..64 characters")
    if not clean[0].isalnum() or not all(c.isalnum() or c in "_-" for c in clean):
        raise ValueError("Code must use uppercase alphanumeric, _ or -")
    return clean


def _clean_line(value: str, max_len: int) -> str:
    clean = value.strip()
    if not clean or len(clean) > max_len or "\n" in clean or "\r" in clean:
        raise ValueError(f"Expected non-empty single-line text up to {max_len} chars")
    return clean


def _clean_domain(value: str) -> str:
    clean = value.strip().lower()
    if (
        len(clean) < 4
        or len(clean) > 120
        or "." not in clean
        or " " in clean
        or not clean[0].isalnum()
    ):
        raise ValueError("Invalid corporate email domain")
    return clean


class SsoProviderInput(Versioned):
    expected_revision: int = Field(ge=0, le=1_000_000)
    location_id: UUID | None = None
    code: str
    display_name: str
    protocol: SsoProtocol = "oidc"
    issuer_url: str
    email_domain: str
    status: SsoProviderStatus = "active"

    @field_validator("code")
    @classmethod
    def valid_code(cls, value: str) -> str:
        return _clean_code(value)

    @field_validator("display_name")
    @classmethod
    def valid_name(cls, value: str) -> str:
        return _clean_line(value, 200)

    @field_validator("issuer_url")
    @classmethod
    def valid_issuer(cls, value: str) -> str:
        clean = _clean_line(value, 300)
        if not (clean.startswith("https://") or clean.startswith("http://")) or " " in clean:
            raise ValueError("Issuer URL must start with http:// or https://")
        return clean

    @field_validator("email_domain")
    @classmethod
    def valid_domain(cls, value: str) -> str:
        return _clean_domain(value)


class SsoProviderView(Strict):
    schema_version: Literal[1] = 1
    provider_id: UUID
    location_id: UUID | None
    code: str
    display_name: str
    protocol: SsoProtocol
    issuer_url: str
    email_domain: str
    status: SsoProviderStatus
    revision: int
    recorded_by: UUID
    recorded_at: AwareDatetime


class SsoProviderList(Strict):
    schema_version: Literal[1] = 1
    items: list[SsoProviderView]


class DirectoryLinkInput(Versioned):
    expected_revision: int = Field(ge=0, le=1_000_000)
    location_id: UUID | None = None
    provider_id: UUID
    user_id: UUID
    external_subject: str
    employee_code: str

    @field_validator("external_subject")
    @classmethod
    def valid_sub(cls, value: str) -> str:
        return _clean_line(value, 200)

    @field_validator("employee_code")
    @classmethod
    def valid_emp(cls, value: str) -> str:
        return _clean_line(value, 64)


class DirectoryLinkView(Strict):
    schema_version: Literal[1] = 1
    link_id: UUID
    location_id: UUID | None
    provider_id: UUID
    user_id: UUID
    external_subject: str
    employee_code: str
    status: DirectoryLinkStatus
    deprovisioned_at: AwareDatetime | None
    deprovision_reason: str | None
    revision: int
    recorded_by: UUID
    recorded_at: AwareDatetime


class DirectoryLinkList(Strict):
    schema_version: Literal[1] = 1
    items: list[DirectoryLinkView]


class DeprovisionInput(Versioned):
    reason: str

    @field_validator("reason")
    @classmethod
    def valid_reason(cls, value: str) -> str:
        return _clean_line(value, 300)


class LifecycleEventView(Strict):
    schema_version: Literal[1] = 1
    event_id: UUID
    location_id: UUID | None
    directory_link_id: UUID
    user_id: UUID
    event_kind: LifecycleEventKind
    reason: str | None
    memberships_suspended: int
    delegations_removed: int
    recorded_by: UUID
    recorded_at: AwareDatetime


class LifecycleEventList(Strict):
    schema_version: Literal[1] = 1
    items: list[LifecycleEventView]


class DeprovisionResultView(Strict):
    schema_version: Literal[1] = 1
    link: DirectoryLinkView
    event: LifecycleEventView


def _provider_view(r: tuple[Any, ...]) -> SsoProviderView:
    return SsoProviderView(
        provider_id=r[0],
        location_id=r[1],
        code=str(r[2]),
        display_name=str(r[3]),
        protocol=r[4],
        issuer_url=str(r[5]),
        email_domain=str(r[6]),
        status=r[7],
        revision=int(r[8]),
        recorded_by=r[9],
        recorded_at=r[10],
    )


def _link_view(r: tuple[Any, ...]) -> DirectoryLinkView:
    return DirectoryLinkView(
        link_id=r[0],
        location_id=r[1],
        provider_id=r[2],
        user_id=r[3],
        external_subject=str(r[4]),
        employee_code=str(r[5]),
        status=r[6],
        deprovisioned_at=r[7],
        deprovision_reason=r[8],
        revision=int(r[9]),
        recorded_by=r[10],
        recorded_at=r[11],
    )


def _event_view(r: tuple[Any, ...]) -> LifecycleEventView:
    return LifecycleEventView(
        event_id=r[0],
        location_id=r[1],
        directory_link_id=r[2],
        user_id=r[3],
        event_kind=r[4],
        reason=r[5],
        memberships_suspended=int(r[6]),
        delegations_removed=int(r[7]),
        recorded_by=r[8],
        recorded_at=r[9],
    )


async def list_sso_providers(conn: RuntimeConnection, business: UUID) -> SsoProviderList:
    await require_module(conn, business, ANALYTICS_MODULE)
    rows = await (
        await conn.execute(
            "select id, location_id, code, display_name, protocol, issuer_url, email_domain, "
            "status, revision, recorded_by, recorded_at from gba.enterprise_sso_providers "
            "where tenant_id = %s order by code, id",
            (business,),
        )
    ).fetchall()
    return SsoProviderList(items=[_provider_view(r) for r in rows])


async def save_sso_provider(
    conn: RuntimeConnection,
    business: UUID,
    provider_id: UUID,
    *,
    user_id: UUID,
    actor: str,
    key: str,
    body: SsoProviderInput,
) -> SsoProviderView:
    _check_ready()
    await require_module(conn, business, ANALYTICS_MODULE)
    scope = IdempotencyScope(business, actor, "enterprise.sso.provider.save", key)
    replay = await commands.claim(
        conn,
        scope,
        commands.fingerprint({"provider_id": str(provider_id), **body.model_dump(mode="json")}),
        SsoProviderView,
    )
    if replay is not None:
        return replay

    async with module_writes(ANALYTICS_MODULE):
        existing = await (
            await conn.execute(
                "select revision from gba.enterprise_sso_providers "
                "where tenant_id = %s and id = %s for update",
                (business, provider_id),
            )
        ).fetchone()
        try:
            if existing is None:
                if body.expected_revision != 0:
                    raise EnterpriseRevisionConflictError(
                        "SSO provider does not exist yet; expected_revision must be 0"
                    )
                await conn.execute(
                    "insert into gba.enterprise_sso_providers ("
                    "id, tenant_id, location_id, code, display_name, protocol, issuer_url, "
                    "email_domain, status, revision, recorded_by"
                    ") values (%s, %s, %s, %s, %s, %s, %s, %s, %s, 1, %s)",
                    (
                        provider_id,
                        business,
                        body.location_id,
                        body.code,
                        body.display_name,
                        body.protocol,
                        body.issuer_url,
                        body.email_domain,
                        body.status,
                        user_id,
                    ),
                )
            else:
                if body.expected_revision != int(existing[0]):
                    raise EnterpriseRevisionConflictError("SSO provider revision mismatch")
                await conn.execute(
                    "update gba.enterprise_sso_providers set code = %s, display_name = %s, "
                    "protocol = %s, issuer_url = %s, email_domain = %s, status = %s, "
                    "revision = revision + 1, recorded_by = %s, recorded_at = now() "
                    "where tenant_id = %s and id = %s",
                    (
                        body.code,
                        body.display_name,
                        body.protocol,
                        body.issuer_url,
                        body.email_domain,
                        body.status,
                        user_id,
                        business,
                        provider_id,
                    ),
                )
        except errors.UniqueViolation as exc:
            raise EnterpriseRevisionConflictError(
                "SSO provider code or email_domain already exists"
            ) from exc
        except errors.ForeignKeyViolation as exc:
            raise InvalidReferenceError("Referenced location not found") from exc

        row = await (
            await conn.execute(
                "select id, location_id, code, display_name, protocol, issuer_url, email_domain, "
                "status, revision, recorded_by, recorded_at from gba.enterprise_sso_providers "
                "where tenant_id = %s and id = %s",
                (business, provider_id),
            )
        ).fetchone()
        if row is None:
            raise NotFoundError("Saved SSO provider not found")
        view = _provider_view(row)
        await commands.complete(conn, scope, view)
        return view


async def list_directory_links(conn: RuntimeConnection, business: UUID) -> DirectoryLinkList:
    await require_module(conn, business, ANALYTICS_MODULE)
    rows = await (
        await conn.execute(
            "select id, location_id, provider_id, user_id, external_subject, employee_code, "
            "status, deprovisioned_at, deprovision_reason, revision, recorded_by, recorded_at "
            "from gba.enterprise_directory_links where tenant_id = %s "
            "order by employee_code, id",
            (business,),
        )
    ).fetchall()
    return DirectoryLinkList(items=[_link_view(r) for r in rows])


async def list_lifecycle_events(conn: RuntimeConnection, business: UUID) -> LifecycleEventList:
    await require_module(conn, business, ANALYTICS_MODULE)
    rows = await (
        await conn.execute(
            "select id, location_id, directory_link_id, user_id, event_kind, reason, "
            "memberships_suspended, delegations_removed, recorded_by, recorded_at "
            "from gba.enterprise_lifecycle_events where tenant_id = %s "
            "order by recorded_at desc, id",
            (business,),
        )
    ).fetchall()
    return LifecycleEventList(items=[_event_view(r) for r in rows])


async def save_directory_link(
    conn: RuntimeConnection,
    business: UUID,
    link_id: UUID,
    *,
    user_id: UUID,
    actor: str,
    key: str,
    body: DirectoryLinkInput,
) -> DirectoryLinkView:
    _check_ready()
    await require_module(conn, business, ANALYTICS_MODULE)
    scope = IdempotencyScope(business, actor, "enterprise.directory.link.save", key)
    replay = await commands.claim(
        conn,
        scope,
        commands.fingerprint({"link_id": str(link_id), **body.model_dump(mode="json")}),
        DirectoryLinkView,
    )
    if replay is not None:
        return replay

    async with module_writes(ANALYTICS_MODULE):
        existing = await (
            await conn.execute(
                "select revision, status from gba.enterprise_directory_links "
                "where tenant_id = %s and id = %s for update",
                (business, link_id),
            )
        ).fetchone()
        try:
            if existing is None:
                if body.expected_revision != 0:
                    raise EnterpriseRevisionConflictError(
                        "Directory link does not exist yet; expected_revision must be 0"
                    )
                await conn.execute(
                    "insert into gba.enterprise_directory_links ("
                    "id, tenant_id, location_id, provider_id, user_id, external_subject, "
                    "employee_code, status, revision, recorded_by"
                    ") values (%s, %s, %s, %s, %s, %s, %s, 'active', 1, %s)",
                    (
                        link_id,
                        business,
                        body.location_id,
                        body.provider_id,
                        body.user_id,
                        body.external_subject,
                        body.employee_code,
                        user_id,
                    ),
                )
                await conn.execute(
                    "insert into gba.enterprise_lifecycle_events ("
                    "id, tenant_id, location_id, directory_link_id, user_id, event_kind, "
                    "reason, memberships_suspended, delegations_removed, recorded_by"
                    ") values (%s, %s, %s, %s, %s, 'provisioned', 'Directory link created', "
                    "0, 0, %s)",
                    (uuid7(), business, body.location_id, link_id, body.user_id, user_id),
                )
            else:
                if body.expected_revision != int(existing[0]):
                    raise EnterpriseRevisionConflictError("Directory link revision mismatch")
                if str(existing[1]) == "deprovisioned":
                    raise EnterpriseStateError("Deprovisioned directory link cannot be modified")
                await conn.execute(
                    "update gba.enterprise_directory_links set external_subject = %s, "
                    "employee_code = %s, revision = revision + 1, recorded_by = %s, "
                    "recorded_at = now() where tenant_id = %s and id = %s",
                    (body.external_subject, body.employee_code, user_id, business, link_id),
                )
        except errors.UniqueViolation as exc:
            raise EnterpriseRevisionConflictError(
                "Directory link external_subject or user_id already linked to this provider"
            ) from exc
        except errors.ForeignKeyViolation as exc:
            raise InvalidReferenceError(
                "Referenced SSO provider, location or user not found"
            ) from exc

        row = await (
            await conn.execute(
                "select id, location_id, provider_id, user_id, external_subject, employee_code, "
                "status, deprovisioned_at, deprovision_reason, revision, recorded_by, recorded_at "
                "from gba.enterprise_directory_links where tenant_id = %s and id = %s",
                (business, link_id),
            )
        ).fetchone()
        if row is None:
            raise NotFoundError("Saved directory link not found")
        view = _link_view(row)
        await commands.complete(conn, scope, view)
        return view


async def deprovision_directory_link(
    conn: RuntimeConnection,
    business: UUID,
    link_id: UUID,
    *,
    user_id: UUID,
    actor: str,
    key: str,
    body: DeprovisionInput,
) -> DeprovisionResultView:
    """Atomically deprovision an employee: mark directory link deprovisioned, suspend active
    business memberships, remove active delegation memberships, and write lifecycle + audit logs.
    """
    _check_ready()
    await require_module(conn, business, ANALYTICS_MODULE)
    scope = IdempotencyScope(business, actor, "enterprise.directory.link.deprovision", key)
    replay = await commands.claim(
        conn,
        scope,
        commands.fingerprint({"link_id": str(link_id), **body.model_dump(mode="json")}),
        DeprovisionResultView,
    )
    if replay is not None:
        return replay

    async with module_writes(ANALYTICS_MODULE):
        row = await (
            await conn.execute(
                "select location_id, user_id, status from gba.enterprise_directory_links "
                "where tenant_id = %s and id = %s for update",
                (business, link_id),
            )
        ).fetchone()
        if row is None:
            raise NotFoundError("Directory link not found")
        loc_id, target_user_id, status = row[0], row[1], str(row[2])
        if target_user_id == user_id:
            raise EnterpriseStateError("You cannot deprovision your own account")
        if status == "deprovisioned":
            raise EnterpriseStateError("Employee directory link is already deprovisioned")

        # Protect against suspending the last active unrestricted owner
        active_members = await (
            await conn.execute(
                "select id, role from gba.memberships "
                "where tenant_id = %s and user_id = %s and status = 'active' for update",
                (business, target_user_id),
            )
        ).fetchall()
        for mem_id, role in active_members:
            if str(role) == "owner":
                other_owners = await (
                    await conn.execute(
                        "select count(*) from gba.memberships where tenant_id = %s "
                        "and role = 'owner' and status = 'active' and location_id is null "
                        "and id <> %s",
                        (business, mem_id),
                    )
                ).fetchone()
                if other_owners is None or int(other_owners[0]) == 0:
                    raise EnterpriseStateError(
                        "Cannot deprovision the last active owner of the business"
                    )

        susp_cur = await conn.execute(
            "update gba.memberships set status = 'suspended' "
            "where tenant_id = %s and user_id = %s and status = 'active'",
            (business, target_user_id),
        )
        memberships_suspended = max(susp_cur.rowcount or 0, 0)

        del_cur = await conn.execute(
            "update gba.delegation_grant_members set removed_by = %s, removed_at = now() "
            "where owner_tenant_id = %s and user_id = %s and removed_at is null",
            (user_id, business, target_user_id),
        )
        delegations_removed = max(del_cur.rowcount or 0, 0)

        await conn.execute(
            "update gba.enterprise_directory_links set status = 'deprovisioned', "
            "deprovisioned_at = now(), deprovision_reason = %s, revision = revision + 1, "
            "recorded_by = %s, recorded_at = now() where tenant_id = %s and id = %s",
            (body.reason, user_id, business, link_id),
        )
        event_id = uuid7()
        await conn.execute(
            "insert into gba.enterprise_lifecycle_events ("
            "id, tenant_id, location_id, directory_link_id, user_id, event_kind, reason, "
            "memberships_suspended, delegations_removed, recorded_by"
            ") values (%s, %s, %s, %s, %s, 'deprovisioned', %s, %s, %s, %s)",
            (
                event_id,
                business,
                loc_id,
                link_id,
                target_user_id,
                body.reason,
                memberships_suspended,
                delegations_removed,
                user_id,
            ),
        )
        await conn.execute(
            "insert into gba.audit_events "
            "(tenant_id, actor, action, target_type, target_id, details, request_id) "
            "values (%s, %s, 'enterprise.employee.deprovisioned', 'user', %s, %s, "
            "nullif(pg_catalog.current_setting('gba.request_id', true), ''))",
            (
                business,
                actor,
                str(target_user_id),
                Jsonb(
                    {
                        "directory_link_id": str(link_id),
                        "reason": body.reason,
                        "memberships_suspended": memberships_suspended,
                        "delegations_removed": delegations_removed,
                    }
                ),
            ),
        )

        link_row = await (
            await conn.execute(
                "select id, location_id, provider_id, user_id, external_subject, employee_code, "
                "status, deprovisioned_at, deprovision_reason, revision, recorded_by, recorded_at "
                "from gba.enterprise_directory_links where tenant_id = %s and id = %s",
                (business, link_id),
            )
        ).fetchone()
        ev_row = await (
            await conn.execute(
                "select id, location_id, directory_link_id, user_id, event_kind, reason, "
                "memberships_suspended, delegations_removed, recorded_by, recorded_at "
                "from gba.enterprise_lifecycle_events where tenant_id = %s and id = %s",
                (business, event_id),
            )
        ).fetchone()
        assert link_row is not None  # noqa: S101
        assert ev_row is not None  # noqa: S101
        result = DeprovisionResultView(link=_link_view(link_row), event=_event_view(ev_row))
        await commands.complete(conn, scope, result)
        return result
