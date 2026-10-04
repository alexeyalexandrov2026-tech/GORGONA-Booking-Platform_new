"""Tenant context from identity -> active membership -> tenant (ADR-0009).

The salon named in a URL is only a request. Access is decided here, inside the
same transaction as the operation, so authorization and work cannot diverge.
Reviewed operational handlers may also admit an employee of another business
through a current delegation grant (ADR-0016).
"""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import Any, Literal
from uuid import UUID

from psycopg.types.json import Jsonb

from gorgona_booking.auth.permissions import (
    DELEGABLE_PERMISSIONS,
    PLATFORM_ADMIN_PERMISSIONS,
    ROLE_PERMISSIONS,
    Permission,
)
from gorgona_booking.auth.principal import Principal, set_user_context
from gorgona_booking.business.delegations import lock_grant
from gorgona_booking.db.pool import RuntimeConnection, RuntimePool, set_tenant_context
from gorgona_booking.db.schema_guard import assert_access_boundaries_ready
from gorgona_booking.errors import DomainError

_DENIED = "You do not have access to this salon"


class TenantAccessDeniedError(DomainError):
    code = "TENANT_ACCESS_DENIED"


class TenantSuspendedError(DomainError):
    code = "TENANT_SUSPENDED"


class PermissionDeniedError(DomainError):
    code = "PERMISSION_DENIED"


@dataclass(frozen=True, slots=True)
class DelegationContext:
    """The grant revision that admitted a delegated request."""

    grant_id: UUID
    revision: int
    serving_business_id: UUID
    permissions: frozenset[Permission]


@dataclass(frozen=True, slots=True)
class TenantAccess:
    conn: RuntimeConnection
    tenant_id: UUID
    principal: Principal
    role: str | None
    via: Literal["membership", "platform", "delegation"]
    location_id: UUID | None = None
    delegation: DelegationContext | None = None

    @property
    def actor(self) -> str:
        """Who acted, for audit and created-by values. Idempotency stays keyed to the user."""
        if self.delegation is None:
            return self.principal.actor
        return (
            f"delegate:{self.principal.user_id}@{self.delegation.serving_business_id}"
            f"/grant:{self.delegation.grant_id}"
        )

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

    `allow_delegation` admits a designated employee of another business only on
    handlers reviewed for operational, delegated work.
    """
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
        # A delegated grant already verified the boundaries before it was confirmed.
        if access.location_id is not None and access.delegation is None:
            await assert_access_boundaries_ready(conn)
        await conn.execute(
            "select pg_catalog.set_config('gba.location_id', %s, true), "
            "pg_catalog.set_config('gba.delegation_grant_id', %s, true), "
            "pg_catalog.set_config('gba.actor', %s, true)",
            (
                str(access.location_id) if access.location_id else "",
                str(access.delegation.grant_id) if access.delegation else "",
                access.actor,
            ),
        )
        yield access


async def _authorize(
    conn: RuntimeConnection,
    principal: Principal,
    salon_id: UUID,
    permission: Permission,
    *,
    allow_location_scope: bool,
    allow_delegation: bool,
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
    else:
        if tenant is not None and allow_delegation and permission in DELEGABLE_PERMISSIONS:
            delegated = await _delegated_access(
                conn,
                principal,
                salon_id,
                permission,
                str(tenant[0]),
                allow_location_scope=allow_location_scope,
            )
            if delegated is not None:
                return delegated
        if tenant is None or not platform_admin:
            raise TenantAccessDeniedError(_DENIED)
        if not platform_may:
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


# --- Delegation between independent businesses (ADR-0016) ---------------------------------

_CANDIDATES = """
select d.tenant_id, d.id, d.membership_id, g.id, v.permissions, v.location_id
from gba.delegation_designations d
join gba.delegation_grants g on g.tenant_id = d.grantor_business_id and g.id = d.grant_id
join lateral (select permissions, location_id, state, valid_from, valid_until
              from gba.delegation_grant_versions
              where tenant_id = g.tenant_id and grant_id = g.id
              order by revision desc limit 1) v on true
where d.grantor_business_id = %s and d.user_id = %s and d.status = 'active'
  and v.state = 'active' and v.valid_from <= now() and now() < v.valid_until
order by (v.location_id is not null), g.id
"""


async def _delegated_access(
    conn: RuntimeConnection,
    principal: Principal,
    owner_id: UUID,
    permission: Permission,
    owner_status: str,
    *,
    allow_location_scope: bool,
    serving_business_id: UUID | None = None,
) -> TenantAccess | None:
    """None when the caller holds no current designation for this owner business."""
    suspended = await (
        await conn.execute(
            "select 1 from gba.memberships "
            "where tenant_id = %s and user_id = %s and status = 'suspended'",
            (owner_id, principal.user_id),
        )
    ).fetchone()
    if suspended is not None:
        # The owner suspended this person; another company cannot restore their access.
        raise TenantAccessDeniedError(_DENIED)
    rows = await (await conn.execute(_CANDIDATES, (owner_id, principal.user_id))).fetchall()
    if serving_business_id is not None:
        rows = [row for row in rows if row[0] == serving_business_id]
    if not rows:
        return None
    granting = [row for row in rows if str(permission) in row[4]]
    usable = [row for row in granting if row[5] is None or allow_location_scope]
    if not usable:
        if granting:
            raise PermissionDeniedError(
                "This operation requires business-wide access; your delegation is location-limited"
            )
        raise PermissionDeniedError("Your delegation does not allow this action")
    if owner_status != "active":
        raise TenantSuspendedError("This salon is suspended")
    # Fail closed before any delegated work if a scope or delegation definition changed.
    await assert_access_boundaries_ready(conn)
    for row in usable:
        access = await _confirm_delegation(
            conn,
            principal,
            owner_id,
            permission,
            row,
            allow_location_scope=allow_location_scope,
        )
        if access is not None:
            return access
    raise TenantAccessDeniedError(_DENIED)


async def group_report_delegation(
    conn: RuntimeConnection, principal: Principal, owner_id: UUID, operator_id: UUID
) -> TenantAccess | None:
    """Force a current grant to this operator on the report's existing transaction.

    The caller already authorized the operator, locked the invitation and checked
    the participant's consent. Direct membership and platform support cannot substitute
    for a designated employee's report permission. Restore scopes after each participant.
    """
    await set_tenant_context(conn, owner_id)
    try:
        tenant = await (
            await conn.execute("select status from gba.tenants where id = %s", (owner_id,))
        ).fetchone()
        if tenant is None:
            return None
        try:
            access = await _delegated_access(
                conn,
                principal,
                owner_id,
                Permission.REPORT_BOOKING_READ,
                str(tenant[0]),
                allow_location_scope=True,
                serving_business_id=operator_id,
            )
        except TenantAccessDeniedError, PermissionDeniedError, TenantSuspendedError:
            return None
        if access is not None:
            await conn.execute(
                "select set_config('gba.location_id', %s, true), "
                "set_config('gba.delegation_grant_id', %s, true), "
                "set_config('gba.actor', %s, true)",
                (
                    str(access.location_id) if access.location_id else "",
                    str(access.delegation.grant_id) if access.delegation else "",
                    access.actor,
                ),
            )
        return access
    except BaseException:
        await clear_group_report_context(conn, principal, operator_id)
        raise


async def clear_group_report_context(
    conn: RuntimeConnection, principal: Principal, operator_id: UUID
) -> None:
    await conn.execute(
        "select set_config('gba.location_id', '', true), "
        "set_config('gba.delegation_grant_id', '', true), "
        "set_config('gba.actor', %s, true)",
        (principal.actor,),
    )
    await set_tenant_context(conn, operator_id)


async def _confirm_delegation(
    conn: RuntimeConnection,
    principal: Principal,
    owner_id: UUID,
    permission: Permission,
    candidate: tuple[Any, ...],
    *,
    allow_location_scope: bool,
) -> TenantAccess | None:
    serving_id, designation_id, membership_id, grant_id = candidate[:4]
    # Serving business: the employee is still an active member there and still designated.
    # FOR SHARE makes a concurrent removal, suspension or revocation wait for this request.
    await set_tenant_context(conn, serving_id)
    member = await (
        await conn.execute(
            "select 1 from gba.memberships where tenant_id = %s and id = %s and user_id = %s "
            "and status = 'active' for share",
            (serving_id, membership_id, principal.user_id),
        )
    ).fetchone()
    designation = await (
        await conn.execute(
            "select 1 from gba.delegation_designations where tenant_id = %s and id = %s "
            "and status = 'active' for share",
            (serving_id, designation_id),
        )
    ).fetchone()
    serving = await (
        await conn.execute("select status from gba.tenants where id = %s", (serving_id,))
    ).fetchone()
    await set_tenant_context(conn, owner_id)
    if member is None or designation is None or serving is None or serving[0] != "active":
        return None

    # Owner business: the current revision, read after any concurrent change committed.
    await lock_grant(conn, owner_id, grant_id, shared=True)
    current = await (
        await conn.execute(
            "select revision, permissions, location_id, "
            "state = 'active' and valid_from <= now() and now() < valid_until "
            "from gba.delegation_grant_versions where tenant_id = %s and grant_id = %s "
            "order by revision desc limit 1",
            (owner_id, grant_id),
        )
    ).fetchone()
    if (
        current is None
        or current[3] is not True
        or str(permission) not in current[1]
        or (current[2] is not None and not allow_location_scope)
    ):
        return None
    access = TenantAccess(
        conn,
        owner_id,
        principal,
        None,
        "delegation",
        current[2],
        DelegationContext(
            grant_id=grant_id,
            revision=current[0],
            serving_business_id=serving_id,
            permissions=frozenset(Permission(item) for item in current[1]),
        ),
    )
    await conn.execute(
        "insert into gba.audit_events (tenant_id, actor, action, target_type, target_id, "
        "details, request_id) values (%s, %s, 'delegation.access', 'delegation_grant', %s, %s, "
        "nullif(pg_catalog.current_setting('gba.request_id', true), ''))",
        (
            owner_id,
            access.actor,
            str(grant_id),
            Jsonb(
                {
                    "revision": current[0],
                    "serving_business_id": str(serving_id),
                    "permission": str(permission),
                    "location_id": str(current[2]) if current[2] else None,
                }
            ),
        ),
    )
    return access
