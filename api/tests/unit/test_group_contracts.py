"""Group commands state only parties and names; membership carries no permissions."""

import pytest
from pydantic import ValidationError

from gorgona_booking.business.group_contracts import GroupCreate, GroupDecision, GroupInvite


@pytest.mark.parametrize(
    "changes",
    [
        {"schema_version": "1"},
        {"code": "holding"},
        {"code": ""},
        {"name": " \t "},
        {"name": "FAKE\nGroup"},
        {"name": "x" * 201},
        {"organizer_business_id": "client-selected"},
        {"permissions": ["booking.read"]},
    ],
)
def test_invalid_groups_are_rejected(changes: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        GroupCreate.model_validate({"code": "HOLDING", "name": "FAKE Holding", **changes})


def test_invitations_and_decisions_cannot_carry_access() -> None:
    for body in ({"permissions": ["booking.read"]}, {"role": "owner"}):
        with pytest.raises(ValidationError):
            GroupInvite.model_validate(body)
    with pytest.raises(ValidationError):
        GroupDecision.model_validate({"expected_revision": 0})
    assert GroupCreate(code="HOLDING", name=" FAKE Holding ").name == "FAKE Holding"
