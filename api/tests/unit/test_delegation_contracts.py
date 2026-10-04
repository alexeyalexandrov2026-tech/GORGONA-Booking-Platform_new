"""Delegation contracts reject unsafe terms and ownership supplied by clients (ADR-0016)."""

from datetime import UTC, datetime, timedelta, timezone
from uuid import uuid7

import pytest
from pydantic import ValidationError

from gorgona_booking.auth.permissions import (
    DELEGABLE_PERMISSIONS,
    DELEGATION_DEPENDENCIES,
    PERMISSIONS_VERSION,
    PLATFORM_ADMIN_PERMISSIONS,
    PLATFORM_SUPPORT_PERMISSIONS,
    ROLE_PERMISSIONS,
    Permission,
)
from gorgona_booking.business.delegation_contracts import (
    DelegationGrantInput,
    DelegationRevokeInput,
)

_START = datetime(2031, 3, 1, 9, 30, tzinfo=timezone(timedelta(hours=-5)))


def _terms(**changes: object) -> dict[str, object]:
    return {
        "expected_revision": 0,
        "grantee_business_id": str(uuid7()),
        "purpose": "FAKE call-centre bookings",
        "permissions": ["booking.read", "catalog.read", "staff.read"],
        "valid_from": _START.isoformat(),
        "valid_until": (_START + timedelta(days=30)).isoformat(),
        **changes,
    }


@pytest.mark.parametrize(
    "changes",
    [
        {"schema_version": True},
        {"schema_version": "1"},
        {"schema_version": 2},
        {"expected_revision": True},
        {"expected_revision": "0"},
        {"expected_revision": -1},
        {"grantee_business_id": "another-company"},
        {"purpose": " \t "},
        {"purpose": "FAKE\npurpose"},
        {"purpose": "x" * 201},
        {"permissions": []},
        {"permissions": ["booking.read", "booking.read"]},
        {"permissions": ["business.manage"]},
        {"permissions": ["members.manage"]},
        {"permissions": ["delegation.manage"]},
        {"permissions": ["booking.write"]},
        {"permissions": ["booking.write", "booking.read", "catalog.read"]},
        {"valid_from": "2031-03-01T09:30:00"},
        {"valid_until": 1_900_000_000},
        {"valid_until": _START.isoformat()},
        {"valid_until": (_START - timedelta(minutes=1)).isoformat()},
        {"valid_until": (_START + timedelta(days=366, seconds=1)).isoformat()},
        {"business_id": str(uuid7())},
        {"tenant_id": str(uuid7())},
        {"state": "active"},
        {"delegates": []},
    ],
)
def test_unsafe_delegation_terms_are_rejected(changes: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        DelegationGrantInput.model_validate(_terms(**changes))


def test_terms_are_canonical_without_assumed_business_facts() -> None:
    body = DelegationGrantInput.model_validate(
        _terms(
            purpose="  FAKE call-centre bookings  ",
            permissions=["staff.read", "booking.write", "catalog.read", "booking.read"],
            valid_until=(_START + timedelta(days=366)).isoformat(),
        )
    )
    assert body.purpose == "FAKE call-centre bookings"
    assert body.permissions == ("booking.read", "booking.write", "catalog.read", "staff.read")
    assert body.valid_from == _START.astimezone(UTC)
    assert body.valid_from.tzinfo is UTC
    assert body.location_id is None
    assert "location_id" in body.model_dump()


@pytest.mark.parametrize(
    "changes",
    [{"expected_revision": 0}, {"expected_revision": True}, {"schema_version": "1"}, {"x": 1}],
)
def test_revocation_requires_the_revision_being_revoked(changes: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        DelegationRevokeInput.model_validate({"expected_revision": 1, **changes})


def test_only_operational_permissions_can_be_delegated() -> None:
    assert PERMISSIONS_VERSION == 4
    assert {
        Permission.BOOKING_READ,
        Permission.BOOKING_WRITE,
        Permission.CATALOG_READ,
        Permission.STAFF_READ,
        Permission.REPORT_BOOKING_READ,
    } == DELEGABLE_PERMISSIONS
    never = {
        Permission.BUSINESS_READ,
        Permission.BUSINESS_MANAGE,
        Permission.CATALOG_MANAGE,
        Permission.STAFF_MANAGE,
        Permission.MEMBERS_MANAGE,
        Permission.MEMBERS_MANAGE_ADMINS,
        Permission.DELEGATION_MANAGE,
        Permission.GROUP_MANAGE,
        Permission.SETTINGS_MANAGE,
        Permission.READINESS_READ,
        *(PLATFORM_ADMIN_PERMISSIONS - PLATFORM_SUPPORT_PERMISSIONS),
    }
    assert not never & DELEGABLE_PERMISSIONS
    for permission, required in DELEGATION_DEPENDENCIES.items():
        assert permission in DELEGABLE_PERMISSIONS
        assert required <= DELEGABLE_PERMISSIONS


def test_granting_access_to_another_business_is_an_owner_decision() -> None:
    assert Permission.DELEGATION_MANAGE in ROLE_PERMISSIONS["owner"]
    for role in ("manager", "front_desk", "artist"):
        assert Permission.DELEGATION_MANAGE not in ROLE_PERMISSIONS[role]
    assert Permission.DELEGATION_MANAGE not in PLATFORM_ADMIN_PERMISSIONS
