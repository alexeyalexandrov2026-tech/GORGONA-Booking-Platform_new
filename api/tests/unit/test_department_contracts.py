"""Departments reject ambiguous revisions and fabricated ownership fields."""

import pytest
from pydantic import ValidationError

from gorgona_booking.business.department_contracts import DepartmentInput


@pytest.mark.parametrize(
    "changes",
    [
        {"schema_version": True},
        {"schema_version": "1"},
        {"schema_version": 2},
        {"expected_revision": True},
        {"expected_revision": "0"},
        {"expected_revision": -1},
        {"expected_revision": 2_147_483_647},
        {"code": "main"},
        {"code": "MAIN DEPARTMENT"},
        {"name": " \t\n "},
        {"name": "FAKE\nCompany"},
        {"name": "x" * 201},
        {"parent_department_id": "bad-id"},
        {"location_id": "bad-id"},
        {"legal_entity_id": "bad-id"},
        {"business_id": "client-selected-owner"},
        {"state": "published"},
    ],
)
def test_invalid_department_commands_are_rejected(changes: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        DepartmentInput.model_validate(
            {"expected_revision": 0, "code": "MAIN", "name": "FAKE Department", **changes}
        )


def test_optional_links_are_explicitly_empty_and_name_is_trimmed() -> None:
    body = DepartmentInput(expected_revision=0, code="MAIN", name=" FAKE Department ")
    assert body.name == "FAKE Department"
    assert body.parent_department_id is body.location_id is body.legal_entity_id is None
