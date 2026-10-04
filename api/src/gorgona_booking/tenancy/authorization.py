"""Tenant context from identity -> active membership -> tenant (ADR-0009).

The salon named in a URL is only a request. Access is decided here, inside the
same transaction as the operation, so authorization and work cannot diverge.
"""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import Literal
from uuid import UUID

from psycopg.types.json import Jsonb

from gorgona_booking.auth.permissions import (
    DELEGABLE_PERMISSIONS,
    PLATFORM_ADMIN_PERMISSIONS,
    ROLE_PERMISSIONS,
    Permission,
)
from gorgona_booking.auth.principal import Principal, set_user_context
from gorgona_booking.db.pool import RuntimeConnection, RuntimePool, set_tenant_context
from gorgona_booking.db.schema_guard import assert_location_scope_ready
from gorgona_booking.errors import DomainError

_DENIED = "You do not have access to this salon"


class TenantAccessDeniedError(DomainError):
    code = "TENANT_ACCESS_DENIED"


class TenantSuspendedError(DomainError):
    code = "TENANT_SUSPENDED"


class PermissionDeniedError(DomainError):
    code = "PERMISSION_DENIED"


@dataclass(frozen=True, slots=True)
class DelegationScope:
    """The active grant a servicing business's employee works under (ADR-0017)."""

    grant_id: UUID
    servicer_business_id: UUID
    revision: int


@dataclass(frozen=True, slots=True)
class TenantAccess:
    conn: RuntimeConnection
    tenant_id: UUID
    principal: Principal
    role: str | None
    via: Literal["membership", "platform", "delegation"]
    location_id: UUID | None = None
    delegation: DelegationScope | None = None

    def require_location(self, location_id: UUID) -> None:
        """Validate explicit references and receipts before exposing their contents."""
        if self.location_id is not None and location_id != self.location_id:
            raise PermissionDeniedError("This action is outside your location access")


@asynccontextmanager
async def authorized_tenant(
    pool: RuntimePool,
    principal: Principal,
    salon_id: UUID,
    permission: Permission,
    *,
    request_id: str | None = None,
    exclusive: str | None = None,
    allow_location_scope: bool = False,
    allow_delegation: bool = False,
) -> AsyncIterator[TenantAccess]:
    """Yield a connection scoped to `salon_id` only if `principal` may use `permission`.

    Any failure raises before the caller runs and rolls the transaction back, so the
    candidate tenant context never outlives the check.

    `exclusive` names a per-salon critical section (e.g. "members"). Its advisory
    lock is taken *before* the membership row lock, so two requests that change each
    other's memberships queue instead of deadlocking.

    `allow_delegation` admits an employee of a servicing business under an active grant.
    A grant may be limited to one location, so only location-scoped handlers may opt in.
    """
    if allow_delegation and not allow_location_scope:
        raise ValueError("Delegated handlers must support location scope")
    async with pool.connection() as conn, conn.transaction():
        if exclusive is not None:
            await conn.execute(
                "select pg_catalog.pg_advisory_xact_lock(pg_catalog.hashtextextended(%s, 0))",
                (f"gba:{exclusive}:{salon_id}",),
            )
        await set_tenant_context(conn, salon_id)
        await set_user_context(conn, principal.user_id, request_id=request_id)
        access = await _authorize(
            conn,
            principal,
            salon_id,
            permission,
            allow_location_scope=allow_location_scope,
            allow_delegation=allow_delegation,
        )
        if access.location_id is not None:
            await assert_location_scope_ready(conn)
        await conn.execute(
            "select pg_catalog.set_config('gba.location_id', %s, true)",
            (str(access.location_id) if access.location_id else "",),
        )
        yield access


async def _authorize(
    conn: RuntimeConnection,
    principal: Principal,
    salon_id: UUID,
    permission: Permission,
    *,
    allow_location_scope: bool,
    allow_delegation: bool = False,
) -> TenantAccess:
    # FOR SHARE: a concurrent suspend/revoke waits until this request finishes.
    membership = await (
        await conn.execute(
            "select role, location_id from gba.memberships "
            "where tenant_id = %s and user_id = %s and status = 'active' for share",
            (salon_id, principal.user_id),
        )
    ).fetchone()
    tenant = await (
        await conn.execute("select status from gba.tenants where id = %s", (salon_id,))
    ).fetchone()
    platform_admin = principal.is_platform_admin and await _is_platform_admin(conn, principal)
    platform_may = platform_admin and permission in PLATFORM_ADMIN_PERMISSIONS

    if membership is not None and tenant is not None:
        role = str(membership[0])
        # Only handlers that use the location RLS boundary may admit a scoped grant.
        if not platform_may and not allow_location_scope:
            require_unrestricted_membership(membership[1])
        if tenant[0] != "active" and not platform_may:
            raise TenantSuspendedError("This salon is suspended")
        if (
            (membership[1] is None or allow_location_scope)
            and permission in ROLE_PERMISSIONS[role]
            and tenant[0] == "active"
        ):
            return TenantAccess(conn, salon_id, principal, role, "membership", membership[1])
        if not platform_may:
            raise PermissionDeniedError("Your role does not allow this action")
    elif (
        tenant is not None
        and allow_delegation
        and (delegated := await _delegated_access(conn, principal, salon_id, permission, tenant[0]))
        is not None
    ):
        return delegated
    elif tenant is None or not platform_admin:
        raise TenantAccessDeniedError(_DENIED)
    elif not platform_may:
        raise PermissionDeniedError("Platform support access is read-only")

    await conn.execute(
        "insert into gba.audit_events (tenant_id, actor, action, target_type, target_id, "
        "details, request_id) values (%s, %s, 'platform.tenant_access', 'tenant', %s, %s, "
        "nullif(pg_catalog.current_setting('gba.request_id', true), ''))",
        (salon_id, principal.actor, str(salon_id), Jsonb({"permission": str(permission)})),
    )
    return TenantAccess(
        conn, salon_id, principal, str(membership[0]) if membership else None, "platform"
    )


async def _delegated_access(
    conn: RuntimeConnection,
    principal: Principal,
    salon_id: UUID,
    permission: Permission,
    tenant_status: str,
) -> TenantAccess | None:
    """Admit a named delegate of an active, unexpired grant; None if there is no grant.

    Checks both accounts in this transaction: the grant and delegate rows of the owner
    business, then the delegate's company-wide membership of the servicing business.
    Row locks keep a concurrent revocation from completing until this request ends.
    """
    if permission not in DELEGABLE_PERMISSIONS:
        return None
    grants = await (
        await conn.execute(
            "select g.id, g.servicer_tenant_id, g.permissions, g.location_id, g.revision "
            "from gba.delegation_grants g join gba.delegation_grant_members m "
            "on m.owner_tenant_id = g.owner_tenant_id and m.grant_id = g.id "
            "where g.owner_tenant_id = %s and m.user_id = %s and m.removed_at is null "
            "and g.status = 'active' and g.expires_at > pg_catalog.statement_timestamp() "
            "order by g.id for share of g, m",
            (salon_id, principal.user_id),
        )
    ).fetchall()
    if not grants:
        return None
    if tenant_status != "active":
        raise TenantSuspendedError("This salon is suspended")
    # A person the owner suspended cannot return through another company's grant.
    suspended = await (
        await conn.execute(
            "select 1 from gba.memberships "
            "where tenant_id = %s and user_id = %s and status = 'suspended'",
            (salon_id, principal.user_id),
        )
    ).fetchone()
    if suspended is not None:
        raise PermissionDeniedError("Your access to this business is suspended")
    for grant_id, servicer_id, permissions, location_id, revision in grants:
        if str(permission) not in permissions:
            continue
        # Membership rows are locked under their own company's context, then restored.
        await set_tenant_context(conn, servicer_id)
        servicer = await (
            await conn.execute(
                "select m.role, m.location_id, t.status from gba.memberships m "
                "join gba.tenants t on t.id = m.tenant_id "
                "where m.tenant_id = %s and m.user_id = %s and m.status = 'active' "
                "for share of m",
                (servicer_id, principal.user_id),
            )
        ).fetchone()
        await set_tenant_context(conn, salon_id)
        if (
            servicer is None
            or servicer[1] is not None
            or servicer[2] != "active"
            or permission not in ROLE_PERMISSIONS[str(servicer[0])]
        ):
            continue
        await conn.execute(
            "insert into gba.audit_events (tenant_id, actor, action, target_type, target_id, "
            "details, request_id) values (%s, %s, 'delegation.access', 'delegation_grant', %s, "
            "%s, nullif(pg_catalog.current_setting('gba.request_id', true), ''))",
            (
                salon_id,
                principal.actor,
                str(grant_id),
                Jsonb(
                    {
                        "servicer_business_id": str(servicer_id),
                        "permission": str(permission),
                        "grant_revision": revision,
                    }
                ),
            ),
        )
        return TenantAccess(
            conn,
            salon_id,
            principal,
            None,
            "delegation",
            location_id,
            DelegationScope(grant_id, servicer_id, revision),
        )
    raise PermissionDeniedError("Your delegated access does not allow this action")


def require_unrestricted_membership(location_id: UUID | None) -> None:
    if location_id is not None:
        raise PermissionDeniedError(
            "This operation requires business-wide access; your membership is location-limited"
        )


async def _is_platform_admin(conn: RuntimeConnection, principal: Principal) -> bool:
    """Re-checked in the request transaction: a revoked grant stops working at once."""
    row = await (
        await conn.execute(
            "select 1 from gba.platform_roles "
            "where user_id = %s and role = 'platform_admin' and revoked_at is null",
            (principal.user_id,),
        )
    ).fetchone()
    return row is not None
