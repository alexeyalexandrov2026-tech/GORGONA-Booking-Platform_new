"""Static, versioned role -> permission map (ADR-0008).

Roles come from server-side memberships and platform roles, never from token claims.
"""

from enum import StrEnum

PERMISSIONS_VERSION = 5


class Permission(StrEnum):
    BUSINESS_READ = "business.read"
    BUSINESS_MANAGE = "business.manage"
    COUNTERPARTIES_READ = "counterparties.read"
    COUNTERPARTIES_MANAGE = "counterparties.manage"
    DOCUMENTS_READ = "documents.read"
    DOCUMENTS_MANAGE = "documents.manage"
    FINANCE_READ = "finance.read"
    FINANCE_MANAGE = "finance.manage"
    FINANCE_CLOSE = "finance.close"
    BOOKING_READ = "booking.read"
    BOOKING_WRITE = "booking.write"
    CATALOG_READ = "catalog.read"
    CATALOG_MANAGE = "catalog.manage"
    STAFF_READ = "staff.read"
    STAFF_MANAGE = "staff.manage"
    MEMBERS_MANAGE = "members.manage"
    MEMBERS_MANAGE_ADMINS = "members.manage_admins"
    SETTINGS_MANAGE = "settings.manage"
    READINESS_READ = "readiness.read"
    PLATFORM_TENANT_STATUS = "platform.tenant_status"
    PLATFORM_GO_LIVE = "platform.go_live"


_STAFF = frozenset(
    {
        Permission.BUSINESS_READ,
        Permission.BOOKING_READ,
        Permission.CATALOG_READ,
        Permission.STAFF_READ,
    }
)
_FRONT_DESK = _STAFF | {Permission.BOOKING_WRITE}
_MANAGER = _FRONT_DESK | {
    Permission.COUNTERPARTIES_READ,
    Permission.COUNTERPARTIES_MANAGE,
    Permission.DOCUMENTS_READ,
    Permission.DOCUMENTS_MANAGE,
    # Owner decision 2026-10-06: managers may also close and reopen periods.
    Permission.FINANCE_READ,
    Permission.FINANCE_MANAGE,
    Permission.FINANCE_CLOSE,
    Permission.BUSINESS_MANAGE,
    Permission.CATALOG_MANAGE,
    Permission.STAFF_MANAGE,
    Permission.MEMBERS_MANAGE,
    Permission.SETTINGS_MANAGE,
    Permission.READINESS_READ,
}
_OWNER = _MANAGER | {Permission.MEMBERS_MANAGE_ADMINS}

ROLE_PERMISSIONS: dict[str, frozenset[Permission]] = {
    "artist": _STAFF,
    "front_desk": _FRONT_DESK,
    "manager": _MANAGER,
    "owner": _OWNER,
}

ADMIN_ROLES = frozenset({"owner", "manager"})

# What an owner business may delegate to a servicing business (ADR-0017): booking work
# only. Settings, members, structure and organization records are never delegated.
DELEGABLE_PERMISSIONS = frozenset(
    {
        Permission.BOOKING_READ,
        Permission.BOOKING_WRITE,
        Permission.CATALOG_READ,
        Permission.STAFF_READ,
    }
)

# What a platform admin may do inside a salon it is not a member of: read-only support.
PLATFORM_SUPPORT_PERMISSIONS = frozenset(
    {
        Permission.BUSINESS_READ,
        Permission.BOOKING_READ,
        Permission.CATALOG_READ,
        Permission.STAFF_READ,
        Permission.READINESS_READ,
    }
)
PLATFORM_ADMIN_PERMISSIONS = PLATFORM_SUPPORT_PERMISSIONS | {
    Permission.PLATFORM_TENANT_STATUS,
    Permission.PLATFORM_GO_LIVE,
}


def is_salon_admin(role: str) -> bool:
    return role in ADMIN_ROLES
