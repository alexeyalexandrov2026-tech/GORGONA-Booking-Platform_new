"""Counterparty commands reject ambiguous input and privilege expansion."""

from uuid import uuid7

import pytest
from pydantic import TypeAdapter, ValidationError

from gorgona_booking.auth.permissions import (
    DELEGABLE_PERMISSIONS,
    PERMISSIONS_VERSION,
    PLATFORM_ADMIN_PERMISSIONS,
    ROLE_PERMISSIONS,
    Permission,
)
from gorgona_booking.business.counterparty_contracts import (
    BookingLinkInput,
    CounterpartyInput,
    MatchCheckInput,
    MatchDecisionInput,
)


@pytest.mark.parametrize(
    "invalid",
    [
        {"schema_version": True},
        {"schema_version": 2},
        {"extra": "unknown"},
        {"expected_revision": True},
        {"expected_revision": 1.5},
        {"expected_revision": -1},
        {"expected_revision": 2_147_483_647},
        {"display_name": "   "},
        {"display_name": "FAKE\x00Name"},
        {"display_name": "x" * 201},
        {"tax_id": "<script>"},
        {"email": "bad@address"},
        {"phone": "+  ().----"},
        {"roles": ["customer", "customer"]},
        {"roles": ["administrator"]},
        {"archived": "false"},
        {"contacts": [{"name": "FAKE", "is_admin": True}]},
        {"contacts": [{"name": "FAKE"}] * 21},
    ],
)
def test_card_rejects_invalid_or_unknown_input(invalid: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        CounterpartyInput.model_validate(
            {
                "expected_revision": 0,
                "kind": "person",
                "display_name": "FAKE Person",
                **invalid,
            }
        )


def test_optional_business_facts_stay_unknown_and_roles_are_canonical() -> None:
    card = CounterpartyInput(
        expected_revision=0,
        kind="organization",
        display_name=" FAKE Firm ",
        roles=("supplier", "customer"),
    )
    assert card.roles == ("customer", "supplier")
    assert card.display_name == "FAKE Firm"
    assert card.email is None
    assert card.phone is None
    assert card.tax_id is None
    assert card.contacts == ()


def test_commands_and_matching_are_typed_and_require_human_decisions() -> None:
    with pytest.raises(ValidationError):
        MatchCheckInput()
    with pytest.raises(ValidationError):
        TypeAdapter(MatchDecisionInput).validate_python(
            {"decision": "merge", "into_id": uuid7(), "expected_revision": 1}
        )
    with pytest.raises(ValidationError):
        TypeAdapter(BookingLinkInput).validate_python(
            {"action": "link", "booking_ids": [uuid7()] * 2}
        )
    with pytest.raises(ValidationError):
        TypeAdapter(BookingLinkInput).validate_python(
            {"action": "unlink", "booking_id": uuid7(), "expected_sequence": True}
        )


def test_new_permissions_are_company_owner_manager_only_and_not_delegable() -> None:
    assert PERMISSIONS_VERSION == 5
    rights = {
        Permission.COUNTERPARTIES_READ,
        Permission.COUNTERPARTIES_MANAGE,
        Permission.DOCUMENTS_READ,
        Permission.DOCUMENTS_MANAGE,
    }
    assert rights <= ROLE_PERMISSIONS["owner"]
    assert rights <= ROLE_PERMISSIONS["manager"]
    assert not rights & ROLE_PERMISSIONS["artist"]
    assert not rights & ROLE_PERMISSIONS["front_desk"]
    assert not rights & PLATFORM_ADMIN_PERMISSIONS
    assert not rights & DELEGABLE_PERMISSIONS
