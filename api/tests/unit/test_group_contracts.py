"""Group commands fail before ambiguous or invented business facts enter storage."""

import pytest
from pydantic import ValidationError

from gorgona_booking.auth.permissions import (
    PLATFORM_ADMIN_PERMISSIONS,
    ROLE_PERMISSIONS,
    Permission,
)
from gorgona_booking.business.group_contracts import ConsentInput, GroupInput, InvitationInput


@pytest.mark.parametrize(
    "changes",
    [
        {"schema_version": True},
        {"schema_version": "1"},
        {"expected_revision": True},
        {"expected_revision": -1},
        {"name": " "},
        {"name": "FAKE\nname"},
        {"code": "bad code"},
        {"location_id": "invented"},
    ],
)
def test_invalid_group_commands(changes: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        GroupInput.model_validate(
            {"expected_revision": 0, "code": "FAKE", "name": "FAKE group", **changes}
        )


def test_only_owner_may_manage_relationships_and_report_grant_is_not_booking_read() -> None:
    assert Permission.GROUP_MANAGE in ROLE_PERMISSIONS["owner"]
    for role in ("manager", "front_desk", "artist"):
        assert Permission.GROUP_MANAGE not in ROLE_PERMISSIONS[role]
    assert Permission.GROUP_MANAGE not in PLATFORM_ADMIN_PERMISSIONS
    assert Permission.REPORT_BOOKING_READ not in ROLE_PERMISSIONS["owner"]


@pytest.mark.parametrize(
    "payload",
    [
        {"expected_revision": True, "state": "accepted"},
        {"expected_revision": 0, "state": "active"},
        {"expected_revision": 0, "state": "accepted", "operator": "fake"},
    ],
)
def test_consent_is_strict(payload: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        ConsentInput.model_validate(payload)


def test_invitation_cannot_include_consent() -> None:
    with pytest.raises(ValidationError):
        InvitationInput.model_validate(
            {"participant_business_id": "a1111111-1111-4111-8111-111111111111", "state": "accepted"}
        )
