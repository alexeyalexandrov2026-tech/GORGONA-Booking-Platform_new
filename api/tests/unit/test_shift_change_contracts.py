"""External I2 inputs must be versioned, bounded and type-correct."""

from uuid import uuid7

import pytest
from pydantic import ValidationError

from gorgona_booking.business.shift_change_contracts import ChangeEventInput, ChangeInput


@pytest.mark.parametrize("revision", [True, 1.0, "1"])
def test_revision_types_are_not_coerced(revision: object) -> None:
    with pytest.raises(ValidationError):
        ChangeEventInput.model_validate({"action": "accept", "expected_revision": revision})
    with pytest.raises(ValidationError):
        ChangeInput.model_validate(
            {
                "kind": "handover",
                "shift_id": uuid7(),
                "target_profile_id": uuid7(),
                "expected_shift_revision": revision,
            }
        )


@pytest.mark.parametrize(
    "extra",
    [
        {"kind": "unknown"},
        {"schema_version": 2},
        {"expected_shift_revision": 0},
        {"expected_shift_revision": 2147483647},
        {"other_shift_id": uuid7()},
        {"kind": "swap"},
        {"ignored": True},
    ],
)
def test_change_requires_a_valid_shape(extra: dict[str, object]) -> None:
    value = {
        "kind": "handover",
        "shift_id": uuid7(),
        "target_profile_id": uuid7(),
        "expected_shift_revision": 1,
        **extra,
    }
    with pytest.raises(ValidationError):
        ChangeInput.model_validate(value)


@pytest.mark.parametrize(
    "extra",
    [
        {"action": "propose"},
        {"expected_revision": 0},
        {"expected_revision": 2147483647},
        {"schema_version": 2},
        {"actor": str(uuid7())},
    ],
)
def test_event_is_an_explicit_current_revision_command(extra: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        ChangeEventInput.model_validate({"action": "accept", "expected_revision": 1, **extra})
