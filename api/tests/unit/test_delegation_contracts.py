"""Delegation terms are explicit, bounded and limited to booking work (ADR-0017)."""

import asyncio
from pathlib import Path
from uuid import uuid7

import pytest
from pydantic import ValidationError

from gorgona_booking.api import salons
from gorgona_booking.auth.permissions import DELEGABLE_PERMISSIONS, ROLE_PERMISSIONS, Permission
from gorgona_booking.business.delegation_contracts import DelegateSelection, DelegationIssue
from gorgona_booking.tenancy.authorization import authorized_tenant

_ISSUE: dict[str, object] = {
    "servicer_business_id": str(uuid7()),
    "permissions": ["booking.write", "booking.read"],
    "location_id": None,
    "expires_at": "2031-06-02T12:00:00Z",
}


@pytest.mark.parametrize(
    "changes",
    [
        {"schema_version": "1"},
        {"permissions": []},
        {"permissions": ["booking.read", "booking.read"]},
        {"permissions": ["members.manage"]},
        {"permissions": ["business.manage"]},
        {"permissions": ["settings.manage"]},
        {"permissions": ["business.read"]},
        {"expires_at": "2031-06-02T12:00:00"},
        {"servicer_business_id": "not-a-business"},
        {"owner_business_id": str(uuid7())},
        {"status": "active"},
    ],
)
def test_invalid_delegation_terms_are_rejected(changes: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        DelegationIssue.model_validate({**_ISSUE, **changes})


@pytest.mark.parametrize("missing", ["location_id", "expires_at", "permissions"])
def test_every_term_must_be_stated(missing: str) -> None:
    with pytest.raises(ValidationError):
        DelegationIssue.model_validate({k: v for k, v in _ISSUE.items() if k != missing})


def test_terms_are_canonical() -> None:
    body = DelegationIssue.model_validate(_ISSUE)
    assert body.permissions == ("booking.read", "booking.write")


@pytest.mark.parametrize(
    "changes",
    [
        {"delegate_user_ids": []},
        {"expected_revision": 0},
        {"expected_revision": True},
        {"delegate_user_ids": ["not-a-user"]},
    ],
)
def test_invalid_delegate_selection_is_rejected(changes: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        DelegateSelection.model_validate(
            {"expected_revision": 1, "delegate_user_ids": [str(uuid7())], **changes}
        )


def test_duplicate_delegates_are_rejected() -> None:
    user = str(uuid7())
    with pytest.raises(ValidationError):
        DelegateSelection.model_validate(
            {"expected_revision": 1, "delegate_user_ids": [user, user]}
        )


def test_only_booking_work_is_delegable() -> None:
    assert {
        Permission.BOOKING_READ,
        Permission.BOOKING_WRITE,
        Permission.CATALOG_READ,
        Permission.STAFF_READ,
    } == DELEGABLE_PERMISSIONS
    for never in (
        Permission.BUSINESS_READ,
        Permission.BUSINESS_MANAGE,
        Permission.CATALOG_MANAGE,
        Permission.STAFF_MANAGE,
        Permission.MEMBERS_MANAGE,
        Permission.MEMBERS_MANAGE_ADMINS,
        Permission.SETTINGS_MANAGE,
        Permission.READINESS_READ,
    ):
        assert never not in DELEGABLE_PERMISSIONS
    # Every delegable permission is one a servicer role can hold; the role still limits it.
    assert ROLE_PERMISSIONS["front_desk"] >= DELEGABLE_PERMISSIONS
    assert Permission.BOOKING_WRITE not in ROLE_PERMISSIONS["artist"]


def test_delegated_handlers_must_support_location_scope() -> None:
    async def misuse() -> None:
        async with authorized_tenant(
            None,  # type: ignore[arg-type]  # rejected before the pool is used
            None,  # type: ignore[arg-type]
            uuid7(),
            Permission.BOOKING_READ,
            allow_delegation=True,
        ):
            pass

    with pytest.raises(ValueError, match="location scope"):
        asyncio.run(misuse())


def test_delegated_routes_are_exactly_the_booking_workspace() -> None:
    # Any new delegated route needs an explicit review; settings, clients, audit and
    # staff/catalog changes stay with the owner business.
    source = Path(salons.__file__).read_text(encoding="utf-8")
    delegated = {
        block.split(")", 1)[0]
        for block in source.split("@router.")[1:]
        if "allow_delegation=True" in block
    }
    assert delegated == {
        'get("/salons/{salon_id}/workspace"',
        'get("/salons/{salon_id}/overview"',
        'post("/salons/{salon_id}/availability"',
        'get("/salons/{salon_id}/bookings"',
        'post("/salons/{salon_id}/bookings", status_code=201',
        'post("/salons/{salon_id}/bookings/{booking_id}/reschedule"',
        'post("/salons/{salon_id}/bookings/{booking_id}/cancel"',
        'get("/salons/{salon_id}/services"',
        'get("/salons/{salon_id}/staff"',
        'get("/salons/{salon_id}/staff/{resource_id}/schedule"',
        'get("/salons/{salon_id}/bookings/{booking_id}"',
    }
