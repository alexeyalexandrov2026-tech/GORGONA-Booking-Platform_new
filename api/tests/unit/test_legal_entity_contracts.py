"""Legal-entity drafts reject ambiguous identifiers and ownership supplied by clients."""

import pytest
from pydantic import ValidationError

from gorgona_booking.business.legal_entity_contracts import LegalEntityInput


@pytest.mark.parametrize(
    "changes",
    [
        {"schema_version": True},
        {"schema_version": "1"},
        {"schema_version": 2},
        {"expected_revision": True},
        {"expected_revision": "0"},
        {"expected_revision": -1},
        {"code": "main"},
        {"code": "MAIN ENTITY"},
        {"code": ""},
        {"legal_name": " \t\n "},
        {"legal_name": "FAKE\nCompany"},
        {"legal_name": "x" * 201},
        {"business_id": "client-selected-owner"},
        {"state": "active"},
    ],
)
def test_invalid_legal_entity_drafts_are_rejected(changes: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        LegalEntityInput.model_validate(
            {"expected_revision": 0, "code": "MAIN", "legal_name": "FAKE Company LLC", **changes}
        )


def test_owner_provided_name_is_trimmed_without_inventing_registration_facts() -> None:
    body = LegalEntityInput(expected_revision=0, code="MAIN", legal_name=" FAKE Company LLC ")
    assert body.legal_name == "FAKE Company LLC"
    assert body.model_dump() == {
        "schema_version": 1,
        "expected_revision": 0,
        "code": "MAIN",
        "legal_name": "FAKE Company LLC",
    }
