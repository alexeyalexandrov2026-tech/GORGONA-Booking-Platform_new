"""I1 boundary validation and non-delegable, version-six role permissions."""

from datetime import UTC, datetime, timedelta
from uuid import uuid7

import pytest
from pydantic import ValidationError

from gorgona_booking.auth.permissions import (
    DELEGABLE_PERMISSIONS,
    PERMISSIONS_VERSION,
    PLATFORM_SUPPORT_PERMISSIONS,
    ROLE_PERMISSIONS,
    Permission,
)
from gorgona_booking.business.workforce_contracts import ShiftInput
from gorgona_booking.db.workforce_guard import _expression


def test_workforce_permissions_are_explicit_and_private() -> None:
    assert PERMISSIONS_VERSION == 11
    rights = {Permission.WORKFORCE_SELF, Permission.WORKFORCE_READ, Permission.WORKFORCE_MANAGE}
    assert not rights & DELEGABLE_PERMISSIONS
    assert not rights & PLATFORM_SUPPORT_PERMISSIONS
    for role, permissions in ROLE_PERMISSIONS.items():
        assert Permission.WORKFORCE_SELF in permissions
        assert (Permission.WORKFORCE_MANAGE in permissions) == (role in {"owner", "manager"})
        assert (Permission.WORKFORCE_READ in permissions) == (role in {"owner", "manager"})


def test_schema_approval_preserves_quoted_identifier_and_literal_semantics() -> None:
    assert _expression(" a = 'A' ") == _expression("a='A'")
    assert _expression("a='A '") != _expression("a='A'")
    assert _expression('gba."CURRENT_LOCATION_ID"()') != _expression("gba.current_location_id()")
    assert _expression("code ~ '^[A-Z ]$'") != _expression("code ~ '^[A-Z]$'")


@pytest.mark.parametrize(
    "change",
    [
        {"schema_version": 2},
        {"expected_revision": -1},
        {"position": "\x00"},
        {"status": "draft", "staff_profile_id": uuid7()},
        {"required_skill_ids": [uuid7()] * 2},
        {"starts_at": "2026-10-09T10:00:00"},
        {"ends_at": datetime(2026, 10, 8, tzinfo=UTC)},
        {
            "starts_at": datetime(9999, 12, 20, tzinfo=UTC),
            "ends_at": datetime(9999, 12, 21, tzinfo=UTC),
        },
        {"unknown": "field"},
    ],
)
def test_workforce_rejects_invalid_external_contracts(change: dict[str, object]) -> None:
    start = datetime(2026, 10, 9, tzinfo=UTC)
    with pytest.raises(ValidationError):
        ShiftInput.model_validate(
            {
                "expected_revision": 0,
                "location_id": uuid7(),
                "position": "FAKE",
                "starts_at": start,
                "ends_at": start + timedelta(hours=1),
                **change,
            }
        )
