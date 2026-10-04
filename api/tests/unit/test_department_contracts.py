"""Department drafts reject ambiguous identifiers, implicit links and client ownership."""

from uuid import uuid7

import pytest
from pydantic import ValidationError

from gorgona_booking.business.department_contracts import DepartmentInput

_VALID: dict[str, object] = {
    "expected_revision": 0,
    "code": "OPS",
    "name": "FAKE Operations",
    "parent_department_id": None,
    "legal_entity_id": None,
    "location_id": None,
    "archived": False,
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
        {"code": "ops"},
        {"code": "OPS TEAM"},
        {"code": ""},
        {"name": " \t\n "},
        {"name": "FAKE\nOperations"},
        {"name": "x" * 201},
        {"archived": "false"},
        {"archived": 0},
        {"parent_department_id": "not-a-department"},
        {"legal_entity_id": "not-an-entity"},
        {"location_id": 7},
        {"business_id": "client-selected-owner"},
        {"state": "published"},
        {"head_user_id": "invented-head"},
    ],
)
def test_invalid_department_drafts_are_rejected(changes: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        DepartmentInput.model_validate({**_VALID, **changes})


@pytest.mark.parametrize(
    "missing", ["parent_department_id", "legal_entity_id", "location_id", "archived"]
)
def test_every_link_and_archive_state_must_be_stated(missing: str) -> None:
    # A full replacement must not silently drop a link the client did not send.
    with pytest.raises(ValidationError):
        DepartmentInput.model_validate({k: v for k, v in _VALID.items() if k != missing})


def test_owner_provided_name_is_trimmed_and_links_stay_explicit() -> None:
    location_id = uuid7()
    body = DepartmentInput.model_validate(
        {**_VALID, "name": " FAKE Operations ", "location_id": str(location_id)}
    )
    assert body.name == "FAKE Operations"
    assert body.model_dump(mode="json") == {
        "schema_version": 1,
        "expected_revision": 0,
        "code": "OPS",
        "name": "FAKE Operations",
        "parent_department_id": None,
        "legal_entity_id": None,
        "location_id": str(location_id),
        "archived": False,
    }
