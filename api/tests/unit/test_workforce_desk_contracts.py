"""I4 references are strict and carry identifiers only."""

from uuid import uuid7

import pytest
from pydantic import ValidationError

from gorgona_booking.business.workforce_desk_contracts import (
    CancelledCommand,
    CommandReference,
    CommandStatus,
    DeskView,
    LocationSettingInput,
    LocationSettingView,
)


def _reference(**changes: object) -> dict[str, object]:
    return {
        "schema_version": 1,
        "operation": "time.event",
        "subject_id": str(uuid7()),
        "revision": 2,
        **changes,
    }


def test_reference_accepts_only_known_operations_and_identifiers() -> None:
    assert CommandReference.model_validate(_reference()).skill_id is None
    assert CommandReference.model_validate(_reference(operation="profile", revision=0))
    assert CommandReference.model_validate(_reference(operation="location_setting"))
    for wrong in (
        {"operation": "payroll"},
        {"operation": "workforce.time.event"},
        {"revision": -1},
        {"revision": "2"},
        {"revision": 2147483648},
        {"subject_id": "FAKE"},
        {"schema_version": 2},
        {"reason": "FAKE private reason"},
        {"starts_at": "2031-06-02T10:00:00Z"},
    ):
        with pytest.raises(ValidationError):
            CommandReference.model_validate(_reference(**wrong))


def test_cancellation_marker_keeps_the_reference_and_nothing_else() -> None:
    reference = CommandReference.model_validate(_reference(skill_id=str(uuid7())))
    marker = CancelledCommand(**reference.model_dump())
    assert marker.model_dump(mode="json") == {
        **reference.model_dump(mode="json"),
        "cancelled": True,
    }
    with pytest.raises(ValidationError):
        CancelledCommand.model_validate({**_reference(), "cancelled": False})


def test_status_and_desk_are_closed_enumerations() -> None:
    business = uuid7()
    desk = DeskView(business_id=business, writes="open", profile=None, colleague_shifts="visible")
    assert desk.profile is None
    with pytest.raises(ValidationError):
        DeskView.model_validate({**desk.model_dump(mode="json"), "colleague_shifts": "private"})
    with pytest.raises(ValidationError):
        DeskView.model_validate({**desk.model_dump(mode="json"), "writes": "closed"})
    with pytest.raises(ValidationError):
        CommandStatus.model_validate(
            {
                "schema_version": 1,
                "business_id": str(business),
                "key": "FAKE-key-1",
                "operation": "time.event",
                "state": "pending",
            }
        )


def test_branch_setting_is_a_strict_boolean_with_an_expected_version() -> None:
    body = LocationSettingInput.model_validate(
        {"schema_version": 1, "expected_revision": 0, "colleague_shifts_visible": False}
    )
    assert body.colleague_shifts_visible is False
    for wrong in (
        {"colleague_shifts_visible": "false"},
        {"colleague_shifts_visible": 0},
        {"colleague_shifts_visible": None},
        {"expected_revision": -1},
        {"expected_revision": 2147483647},
        {"schema_version": 2},
        {"reason": "FAKE private"},
    ):
        with pytest.raises(ValidationError):
            LocationSettingInput.model_validate({**body.model_dump(mode="json"), **wrong})
    with pytest.raises(ValidationError):
        LocationSettingInput.model_validate({"schema_version": 1, "expected_revision": 0})
    untouched = LocationSettingView(
        business_id=uuid7(),
        location_id=uuid7(),
        revision=0,
        colleague_shifts_visible=True,
        changed_by=None,
        changed_at=None,
    )
    assert untouched.model_dump(mode="json")["changed_at"] is None
